#!/usr/bin/env python3
"""
妈妈的消息 · 统计引擎

用法:
  python scripts/stats.py messages.json [--out stats.json] [--today 2026-08-30]
                          [--her-birthday 03-15] [--my-birthday 11-02] [--lexicon 词表.json] [--quiet]

输入 messages.json 的格式见 SKILL.md「工作表」一节。
输出 stats.json（所有数字都在这里，报告里的每个数字都能追溯到这个文件），
同时在终端打印一份 Markdown 摘要。

结构：Ctx 整理输入（不改写原数据）→ 一组 sec_xxx(ctx, S) 各算一块 → compute() 组装。
词表在 references/lexicon.json（--lexicon 可换），公式和阈值在本文件顶部（FORMULA / *_RULES），
每个数字的定义在 references/metrics.md。改了公式或阈值要同步 metrics.md、types.md、
prompts/普通用户版.md，tests/test_docs_sync.py 会检查。

只用标准库，不联网，不写任何东西到别的地方。
"""
import argparse
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

from _common import (SCHEMA_VERSION, TYPE_CN, dump_json, fmt_delta, has_any, load_json, load_lexicon,
                     parse_mmdd, parse_ts, safe_date, setup_utf8)

setup_utf8()

# ---------- 公式与阈值（改这里 = 改口径，三处同步） ----------

MIN_MSGS = 20          # 记录不到 20 条只出基础数字
OPEN_GAP_H = 6         # 相邻消息隔 ≥ 6 小时 → 后一条算开启新对话；她连续发的一段（turn）也按这个断
REPLY_WINDOW_H = 24    # 你在她之后 24 小时内发的才算"回复"；隔 24 小时以上她那段算"没回"
SHORT_MAX_CHARS = 3    # 短回复：≤ 3 字（不是表情，不含谢/爱/想，不以妈/爸结尾）
PEAK_MIN_MSGS = 20     # 一方的消息不到 20 条不出"最常在几点"
TREND_MIN_SPAN_DAYS = 60   # 跨度 ≥ 60 天才算趋势：最近 30 天 vs 之前 90 天
HOUR_RULES = {"early": (4, 8), "late_from": 22, "offhour_before": 8, "me_late_from": 23, "me_late_until": 5}

FORMULA = {
    # 💛 牵挂 = 100 × (0.35·她开启对话占比 + 0.30·关心类主题比例 + 0.15·非常规时段比例 + 0.20·min(日均条数/4, 1))
    "care":    {"her_open_ratio": 0.35, "care_ratio": 0.30, "offhour_ratio": 0.15, "density": 0.20, "density_per_day": 4},
    # 🧊 嗯哦好 = 100 × (0.45·短回复占比 + 0.35·没回占比 + 0.20·min(回复中位小时/12, 1))
    "short":   {"short_ratio": 0.45, "unanswered_ratio": 0.35, "latency": 0.20, "latency_cap_h": 12},
    # 🕰️ 不计较 = 100 × (0.6·之后她先开口的比例 + 0.4·(1 − 追问比例))
    "forgive": {"reopen_ratio": 0.6, "no_chase": 0.4},
}
RATING_BANDS = ((25, "模范子女"), (45, "还行"), (65, "欠一个电话"), (80, "欠一顿饭"), (None, "欠一次回家"))
RED_WEIGHT = 10        # 评级分 = 嗯哦好指数 + 10 × 红灯数

MOTHER_RULES = {"wait_open_ratio": 0.35, "wait_fast_s": 600, "secondary_min": 0.08, "silent_text_ratio": 0.4}
CHILD_RULES = {"short_ratio": 0.4, "unanswered_ratio": 0.3, "fast_h": 10 / 60, "fast_short_ratio": 0.3,
               "late_ratio": 0.3, "weekend_ratio": 0.6, "weekend_min_opens": 5, "body_asks": 3}
SIGNAL_RULES = {"health_reply_chars": 4, "self_shrink_min": 2, "sticker_mult": 1.8, "sticker_min": 0.3,
                "opens_drop_pct": -35, "call_drop_ratio": 0.5, "nothing_min": 3, "my_open_gap_days": 14}

EMOJI_RE = re.compile(r"\[([^\[\]]{1,6})\]")

# 固定日期表（农历节日没法用标准库算，先查表；表外年份进 warnings）
LUNAR = {
    "春节": {2022: "02-01", 2023: "01-22", 2024: "02-10", 2025: "01-29", 2026: "02-17", 2027: "02-06", 2028: "01-26", 2029: "02-13", 2030: "02-03"},
    "中秋": {2022: "09-10", 2023: "09-29", 2024: "09-17", 2025: "10-06", 2026: "09-25", 2027: "09-15", 2028: "10-03", 2029: "09-22", 2030: "09-12"},
    "重阳": {2022: "10-04", 2023: "10-23", 2024: "10-11", 2025: "10-29", 2026: "10-18", 2027: "10-08", 2028: "10-26", 2029: "10-16", 2030: "10-05"},
}


# ---------- 工具 ----------

def nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (n - 1))


def festival_dates(years):
    out = []
    for y in years:
        out.append(("元旦", date(y, 1, 1)))
        out.append(("母亲节", nth_weekday(y, 5, 6, 2)))
        out.append(("父亲节", nth_weekday(y, 6, 6, 3)))
        out.append(("国庆", date(y, 10, 1)))
        for name, table in LUNAR.items():
            if y in table:
                m, d = table[y].split("-")
                out.append((name, date(y, int(m), int(d))))
                if name == "春节":
                    out.append(("除夕", date(y, int(m), int(d)) - timedelta(days=1)))
    return sorted(out, key=lambda x: x[1])


def topic_of(text, lex):
    """一条消息命中的主题列表（按词表顺序；一条可以命中多个）。"""
    ex = lex.get("exclude", {})
    return [t for t, kws in lex["topics"].items() if has_any(text, kws, ex.get(t))]


def type_label(m, limit=40):
    """文字/链接给原文，其他类型给 [语音] 这样的标记。"""
    return m["content"][:limit] if m["type"] in ("text", "link") else f"[{TYPE_CN.get(m['type'], m['type'])}]"


def is_short(m, lex):
    c = m["content"].strip()
    ex = lex["short_reply_exclude"]
    if any(w in c for w in ex["contains"]) or any(c.endswith(s) for s in ex["endswith"]):
        return False
    return 0 < len(c) <= SHORT_MAX_CHARS and not EMOJI_RE.search(c)


class Ctx:
    """整理好的输入。sec_xxx() 只读它；段与段之间要传的中间量放在 ctx.d 里。"""

    def __init__(self, data, lex, today=None, her_birthday=None, my_birthday=None):
        self.her_name = data.get("her", "妈妈")
        self.pronoun = data.get("her_pronoun", "她")
        self.lex = lex
        self.today = today
        self.her_birthday = her_birthday      # (月, 日) 或 None
        self.my_birthday = my_birthday
        raw = data.get("messages") or []
        self.n_unknown = sum(1 for m in raw if m.get("sender") not in ("her", "me"))
        self.msgs = []
        for m in raw:
            if m.get("sender") not in ("her", "me"):
                continue
            c = dict(m)                        # 复制一份，不改写调用方的数据
            c["type"] = c.get("type") or "text"
            c["content"] = c.get("content") or ""
            c["_i"] = len(self.msgs)
            c["_dt"] = parse_ts(c.get("ts"))
            c["_chars"] = len(c["content"].strip()) if c["type"] == "text" else 0
            c["_topics"] = topic_of(c["content"], lex) if (c["sender"] == "her" and c["type"] == "text") else []
            self.msgs.append(c)
        self.her = [m for m in self.msgs if m["sender"] == "her"]
        self.me = [m for m in self.msgs if m["sender"] == "me"]
        self.dated = [m for m in self.msgs if m["_dt"]]
        self.her_text = [m for m in self.her if m["type"] == "text"]
        self.me_text = [m for m in self.me if m["type"] == "text"]
        self.d = {}


# ---------- 各段计算（顺序有依赖：后面的段读 ctx.d 和 S 里前面的结果） ----------

def sec_warnings(ctx, S):
    W = []
    if len(ctx.msgs) < MIN_MSGS:
        W.append(f"记录不到 {MIN_MSGS} 条，只出基础数字，不写解读。")
    if ctx.n_unknown:
        W.append(f"有 {ctx.n_unknown} 条消息的 sender 不是 her / me，已忽略。")
    if len(ctx.msgs) >= MIN_MSGS and len(ctx.dated) < len(ctx.msgs) * 0.5:
        W.append(f"{len(ctx.msgs) - len(ctx.dated)} 条没有时间戳（占 {round(100 * (1 - len(ctx.dated) / len(ctx.msgs)))}%），"
                 "谁先开口、回复间隔、时段、没回这几项不稳，报告的数据说明里要写明。")
    backwards = sum(1 for x, y in zip(ctx.dated, ctx.dated[1:]) if y["_dt"] < x["_dt"])
    if backwards:
        W.append(f"有 {backwards} 处时间倒序，messages.json 可能没按时间排好；先跑 scripts/validate.py 看一下。")
    return W


def sec_basics(ctx, S):
    dated = ctx.dated
    first = dated[0]["_dt"] if dated else None
    last = dated[-1]["_dt"] if dated else None
    span_days = (last.date() - first.date()).days + 1 if first else None
    active_days = len({m["_dt"].date() for m in dated})
    ctx.d.update(first=first, last=last, span_days=span_days, active_days=active_days)
    return {"total": len(ctx.msgs), "her": len(ctx.her), "me": len(ctx.me),
            "her_text": len(ctx.her_text), "me_text": len(ctx.me_text),
            "first": first.strftime("%Y-%m-%d") if first else None,
            "last": last.strftime("%Y-%m-%d") if last else None,
            "span_days": span_days, "active_days": active_days,
            "with_ts": len(dated), "without_ts": len(ctx.msgs) - len(dated)}


def sec_opens(ctx, S):
    """对话开启：相邻两条隔 ≥ OPEN_GAP_H 小时，后一条算开启一次新对话。"""
    opens, prev = [], None
    for m in ctx.dated:
        if prev is None or (m["_dt"] - prev["_dt"]) >= timedelta(hours=OPEN_GAP_H):
            opens.append(m)
        prev = m
    her_opens = [m for m in opens if m["sender"] == "her"]
    my_opens = [m for m in opens if m["sender"] == "me"]
    ctx.d.update(her_opens=her_opens, my_opens=my_opens)
    out = {"her": len(her_opens), "me": len(my_opens),
           "her_ratio": round(len(her_opens) / len(opens), 3) if opens else None,
           "my_last_open": my_opens[-1]["_dt"].strftime("%Y-%m-%d") if my_opens else None,
           "her_last_open": her_opens[-1]["_dt"].strftime("%Y-%m-%d") if her_opens else None}
    if ctx.today and my_opens:
        out["days_since_my_last_open"] = (ctx.today - my_opens[-1]["_dt"].date()).days
    if ctx.today and her_opens:
        out["days_since_her_last_open"] = (ctx.today - her_opens[-1]["_dt"].date()).days
    return out


def sec_reply(ctx, S):
    """回复间隔：只用有时间戳的相邻异方消息对，报告用中位数。"""
    dated = ctx.dated

    def latencies(from_side, to_side):
        out = []
        for i, m in enumerate(dated[:-1]):
            if m["sender"] != from_side:
                continue
            nxt = dated[i + 1]
            if nxt["sender"] == to_side:
                out.append(((nxt["_dt"] - m["_dt"]).total_seconds(), m, nxt))
        return out

    def summary(lats):
        if not lats:
            return {"n": 0, "median_s": None, "median": "—", "max_s": None, "max": "—", "max_msg": None}
        secs = [x[0] for x in lats]
        mx = max(lats, key=lambda x: x[0])
        return {"n": len(lats), "median_s": statistics.median(secs), "median": fmt_delta(statistics.median(secs)),
                "max_s": mx[0], "max": fmt_delta(mx[0]),
                "max_msg": {"date": mx[1]["_dt"].strftime("%m-%d"), "content": type_label(mx[1]), "type": mx[1]["type"]}}

    return {"me": summary(latencies("her", "me")), "her": summary(latencies("me", "her"))}


def sec_longest(ctx, S):
    """她最长的一条 vs 你的回复。她没有文字消息时返回 None（stats.json 里不出这个键）。"""
    if not ctx.her_text:
        return None
    longest = max(ctx.her_text, key=lambda m: m["_chars"])
    msgs = ctx.msgs
    reply = next((m for m in msgs[longest["_i"] + 1:] if m["sender"] == "me"), None)
    if reply:
        # 中间她又发了超过 2 条，视为你没回那条
        between = [m for m in msgs[longest["_i"] + 1:reply["_i"]] if m["sender"] == "her"]
        if len(between) > 2:
            reply = None
    return {"chars": longest["_chars"], "content": longest["content"][:60],
            "date": longest["_dt"].strftime("%m-%d") if longest["_dt"] else None,
            "reply_chars": reply["_chars"] if reply and reply["type"] == "text" else (0 if reply is None else None),
            "reply": (reply["content"][:40] if reply and reply["type"] == "text"
                      else (f"[{TYPE_CN.get(reply['type'], reply['type'])}]" if reply else None))}


def sec_short(ctx, S):
    """短回复。"回复" = 紧跟在她消息后面（你连着发的几条都算）、且没隔到 REPLY_WINDOW_H 小时以上的你的消息。
    你自己先开口的（"在吗""妈我到了"）不是回复。她早上发、你晚上回的"嗯"隔了 12 小时，仍然是回复。"""
    reply_flag, prev = {}, None
    for m in ctx.msgs:
        if m["sender"] == "me":
            if prev is None:
                reply_flag[m["_i"]] = False
            elif prev["sender"] == "her":
                reply_flag[m["_i"]] = not (m["_dt"] and prev["_dt"]) or (m["_dt"] - prev["_dt"]) < timedelta(hours=REPLY_WINDOW_H)
            else:
                reply_flag[m["_i"]] = reply_flag.get(prev["_i"], False)
        prev = m
    me_replies = [m for m in ctx.me_text if reply_flag.get(m["_i"])]
    shorts = [m for m in me_replies if is_short(m, ctx.lex)]
    return {"count": len(shorts), "replies": len(me_replies),
            "ratio": round(len(shorts) / len(me_replies), 3) if me_replies else None,
            "top": Counter(m["content"].strip() for m in shorts).most_common(5)}


def sec_topics(ctx, S):
    counter, example = Counter(), {}
    for m in ctx.her_text:
        for t in m["_topics"]:
            counter[t] += 1
            example.setdefault(t, m["content"][:30])
    ctx.d["topic_counter"] = counter
    return [{"topic": t, "count": c, "example": example[t]} for t, c in counter.most_common()]


def sec_care_ratio(ctx, S):
    care = set(ctx.lex["care_topics"])
    hits = sum(1 for m in ctx.her_text if any(t in care for t in m["_topics"]))
    return round(hits / len(ctx.her_text), 3) if ctx.her_text else 0


def sec_hours(ctx, S):
    def hist(side):
        h = [0] * 24
        for m in ctx.dated:
            if m["sender"] == side:
                h[m["_dt"].hour] += 1
        return h

    def peak2(h):
        best = max(range(24), key=lambda i: h[i] + h[(i + 1) % 24])
        return f"{best:02d}:00–{(best + 2) % 24:02d}:00"

    R = HOUR_RULES
    her_h, me_h = hist("her"), hist("me")
    her_dated = [m for m in ctx.dated if m["sender"] == "her"]
    me_dated = [m for m in ctx.dated if m["sender"] == "me"]
    ctx.d["her_dated"] = her_dated
    e0, e1 = R["early"]
    return {"her": her_h, "me": me_h,
            "her_peak": peak2(her_h) if sum(her_h) >= PEAK_MIN_MSGS else None,
            "me_peak": peak2(me_h) if sum(me_h) >= PEAK_MIN_MSGS else None,
            "her_offhour_ratio": round(sum(1 for m in her_dated if m["_dt"].hour < R["offhour_before"] or m["_dt"].hour >= R["late_from"]) / len(her_dated), 3) if her_dated else 0,
            "her_early_count": sum(1 for m in her_dated if e0 <= m["_dt"].hour < e1),
            "her_late_count": sum(1 for m in her_dated if m["_dt"].hour >= R["late_from"] or m["_dt"].hour < e0),
            "me_late_ratio": round(sum(1 for m in me_dated if m["_dt"].hour >= R["me_late_from"] or m["_dt"].hour < R["me_late_until"]) / len(me_dated), 3) if me_dated else 0}


def sec_unanswered(ctx, S):
    """她发了你没回（turn 级）。turn = 她连续发的一段（相邻间隔 < OPEN_GAP_H 小时）。
    没回：turn 之后没人再说话且已过了一天；或下一条还是她自己隔了 6 小时以上又开的口；或你 24 小时后才回。"""
    msgs = ctx.msgs
    turns, i = [], 0
    while i < len(msgs):
        if msgs[i]["sender"] == "her":
            j = i
            while (j + 1 < len(msgs) and msgs[j + 1]["sender"] == "her"
                   and not (msgs[j]["_dt"] and msgs[j + 1]["_dt"] and msgs[j + 1]["_dt"] - msgs[j]["_dt"] >= timedelta(hours=OPEN_GAP_H))):
                j += 1
            turns.append((i, j))
            i = j + 1
        else:
            i += 1
    unanswered, reopen_her = [], 0
    for (a, b) in turns:
        lastm = msgs[b]
        nxt = msgs[b + 1] if b + 1 < len(msgs) else None
        if nxt is None:
            if lastm["_dt"] and ctx.today and (ctx.today - lastm["_dt"].date()).days >= 1:
                unanswered.append(lastm)
            continue
        if nxt["sender"] == "her":
            unanswered.append(lastm)
            reopen_her += 1
        elif lastm["_dt"] and nxt["_dt"] and nxt["_dt"] - lastm["_dt"] >= timedelta(hours=REPLY_WINDOW_H):
            unanswered.append(lastm)
    ctx.d["unanswered"] = unanswered
    return {"count": len(unanswered), "turns": len(turns),
            "ratio": round(len(unanswered) / len(turns), 3) if turns else None,
            "items": [{"date": m["_dt"].strftime("%m-%d %H:%M") if m["_dt"] else "—",
                       "content": type_label(m), "type": m["type"]} for m in unanswered[-8:]],
            "reopened_by_her": reopen_her,
            "reopen_ratio": round(reopen_her / len(unanswered), 3) if unanswered else None}


def sec_phrases(ctx, S):
    lex, ex = ctx.lex, ctx.lex.get("exclude", {})
    chase = [m for m in ctx.her_text if has_any(m["content"], lex["chase"], ex.get("chase"))]
    shrink = [m for m in ctx.her_text if has_any(m["content"], lex["self_shrink"], ex.get("self_shrink"))]
    nothing = [m for m in ctx.her_text if has_any(m["content"], lex["nothing"], ex.get("nothing"))]
    ctx.d.update(chase=chase, shrink=shrink, nothing=nothing)
    return {"chase": len(chase), "self_shrink": len(shrink),
            "self_shrink_examples": [m["content"][:30] for m in shrink[-3:]], "nothing": len(nothing)}


def sec_extras(ctx, S):
    her, me = ctx.her, ctx.me
    her_voice = [m for m in her if m["type"] == "voice"]
    calls = [m for m in ctx.msgs if m["type"] in ("call_voice", "call_video")]
    ctx.d.update(her_voice=her_voice, calls=calls)
    return {"her_voice_count": len(her_voice), "her_voice_total_s": sum((m.get("dur") or 0) for m in her_voice),
            "me_voice_count": sum(1 for m in me if m["type"] == "voice"),
            "call_count": len(calls), "call_total_s": sum((m.get("dur") or 0) for m in calls),
            "her_transfer_count": sum(1 for m in her if m["type"] == "transfer"),
            "me_transfer_count": sum(1 for m in me if m["type"] == "transfer"),
            "her_image_count": sum(1 for m in her if m["type"] == "image"),
            "her_link_count": sum(1 for m in her if m["type"] == "link"),
            "her_sticker_count": sum(1 for m in her if m["type"] == "sticker"),
            "her_recall_count": sum(1 for m in her if m["type"] == "recall")}


def sec_composition(ctx, S):
    comp = Counter()
    for m in ctx.her:
        if m["type"] == "text":
            comp[m["_topics"][0] if m["_topics"] else "其他文字"] += 1
        elif m["type"] == "link":
            comp["转发文章"] += 1
        elif m["type"] == "voice":
            comp["语音"] += 1
        elif m["type"] == "sticker":
            comp["表情包"] += 1
        elif m["type"] in ("image", "video"):
            comp["照片视频"] += 1
        else:
            comp["其他"] += 1
    return [{"name": k, "count": v, "pct": round(100 * v / len(ctx.her), 1)} for k, v in comp.most_common()] if ctx.her else []


def sec_emoji(ctx, S):
    def top(side):
        c = Counter()
        for m in side:
            for e in EMOJI_RE.findall(m["content"]):
                c[e] += 1
        return c.most_common(5)
    return {"her": top(ctx.her), "me": top(ctx.me)}


def sec_catchphrases(ctx, S):
    """口头禅：先找重复 ≥ 2 次的整句（2–10 字），再补 2–4 字的高频片段（≥ 3 次，去掉被更长片段覆盖的）。
    n-gram 粗糙，但不用装分词库。"""
    stop = set(ctx.lex["stopwords"])

    def phrases(side_text, topn=5):
        clean = lambda t: re.sub(r"[^一-鿿]", "", EMOJI_RE.sub("", t))
        exact = Counter(clean(m["content"]) for m in side_text)
        exact = [(g, n) for g, n in exact.most_common() if 2 <= len(g) <= 10 and n >= 2]
        c = Counter()
        for m in side_text:
            t = re.sub(r"[^一-鿿]", " ", EMOJI_RE.sub("", m["content"]))
            for chunk in t.split():
                seen = set()
                for n in (2, 3, 4):
                    for k in range(len(chunk) - n + 1):
                        g = chunk[k:k + n]
                        if g in seen or g[0] in stop or g[-1] in stop:
                            continue
                        seen.add(g)
                        c[g] += 1
        grams = [(g, n) for g, n in c.most_common(80) if n >= 3]
        keep = []
        for g, n in grams:
            if any(g != h and g in h and m >= n * 0.7 for h, m in grams):
                continue
            if any(g in e for e, _ in exact[:topn]):
                continue
            keep.append((g, n))
        return (exact[:topn] + keep)[:topn]

    return {"her": phrases(ctx.her_text), "me": phrases(ctx.me_text)}


def sec_forwards(ctx, S):
    lex, ex = ctx.lex, ctx.lex.get("exclude", {})
    links = [m for m in ctx.her if m["type"] == "link"]
    msgs = ctx.msgs
    return {"count": len(links),
            "health": sum(1 for m in links if has_any(m["content"], lex["health_link"], ex.get("health_link"))),
            "news": sum(1 for m in links if has_any(m["content"], lex["news_link"], ex.get("news_link"))),
            "titles": [m["content"][:30] for m in links[-6:]],
            "my_reply_count": sum(1 for m in links if m["_i"] + 1 < len(msgs) and msgs[m["_i"] + 1]["sender"] == "me")}


def sec_weekly(ctx, S):
    weekly = defaultdict(lambda: [0, 0])
    for m in ctx.dated:
        weekly[m["_dt"].strftime("%G-W%V")][0 if m["sender"] == "her" else 1] += 1
    return [{"week": k, "her": v[0], "me": v[1]} for k, v in sorted(weekly.items())]


def sec_trend(ctx, S):
    """趋势：以最后一条为基准，最近 30 天 vs 之前 90 天。跨度不足 TREND_MIN_SPAN_DAYS 天不算。"""
    d = ctx.d
    first, last, span_days = d["first"], d["last"], d["span_days"]
    if not (last and span_days and span_days >= TREND_MIN_SPAN_DAYS):
        ctx.d["trend"] = None
        return None
    cut = last - timedelta(days=30)
    prev_start = cut - timedelta(days=90)
    recent = [o for o in d["her_opens"] if o["_dt"] > cut]
    prior = [o for o in d["her_opens"] if prev_start < o["_dt"] <= cut]
    prior_days = min(90, (cut - max(prev_start, first)).days) or 1
    r_rate, p_rate = len(recent) / 30, len(prior) / prior_days
    trend = {"her_opens_recent_30d": len(recent), "her_opens_prior_per30d": round(p_rate * 30, 1),
             "change_pct": round(100 * (r_rate - p_rate) / p_rate) if p_rate else None}
    rec_her = [m for m in d["her_dated"] if m["_dt"] > cut]
    pri_her = [m for m in d["her_dated"] if prev_start < m["_dt"] <= cut]

    def sticker_ratio(ms):
        return sum(1 for m in ms if m["type"] == "sticker") / len(ms) if ms else 0

    trend["sticker_ratio_recent"] = round(sticker_ratio(rec_her), 3)
    trend["sticker_ratio_prior"] = round(sticker_ratio(pri_her), 3)
    rc = [m for m in d["calls"] if m["_dt"] and m["_dt"] > cut]
    pc = [m for m in d["calls"] if m["_dt"] and prev_start < m["_dt"] <= cut]
    trend["call_s_recent"] = sum((m.get("dur") or 0) for m in rc)
    trend["call_s_prior_per30d"] = round(sum((m.get("dur") or 0) for m in pc) / prior_days * 30)
    ctx.d["trend"] = trend
    return trend


def sec_festivals(ctx, S):
    """节日记分牌：记录范围内每个节日那天谁先发的、几点、内容、各发了几条。"""
    first, last, p = ctx.d["first"], ctx.d["last"], ctx.pronoun
    check_years = set(range(first.year, last.year + 1)) if first and last else set()
    if ctx.today:
        check_years.add(ctx.today.year)
    missing_years = sorted(y for y in check_years if y not in LUNAR["春节"])
    if missing_years:
        S["warnings"].append("、".join(map(str, missing_years)) + " 年不在农历节日表里，春节 / 中秋 / 重阳没算；在 stats.py 的 LUNAR 表补上日期即可。")
    board = []
    if first and last:
        years = range(first.year, last.year + 1)
        fests = festival_dates(years)
        for name, bd in ((f"{p}的生日", ctx.her_birthday), ("你的生日", ctx.my_birthday)):
            if bd:
                for y in years:
                    dd = safe_date(y, bd[0], bd[1])
                    if dd:
                        fests.append((name, dd))
        fests.sort(key=lambda x: x[1])
        skip = "父亲节" if p == "她" else "母亲节"
        for name, dd in fests:
            if name == skip or not (first.date() <= dd <= last.date()):
                continue
            day_msgs = [m for m in ctx.dated if m["_dt"].date() == dd]
            if not day_msgs:
                board.append({"name": name, "date": dd.isoformat(), "first": None})
                continue
            f = day_msgs[0]
            other = next((m for m in day_msgs if m["sender"] != f["sender"]), None)
            board.append({"name": name, "date": dd.isoformat(),
                          "first": "her" if f["sender"] == "her" else "me",
                          "time": f["_dt"].strftime("%H:%M"),
                          "content": type_label(f, 20),
                          "other_replied": other is not None,
                          "count_her": sum(1 for m in day_msgs if m["sender"] == "her"),
                          "count_me": sum(1 for m in day_msgs if m["sender"] == "me")})
    return board


def sec_countdown(ctx, S):
    """从今天起最近的两个节日（不含元旦、除夕、重阳，母亲节/父亲节按人选）。"""
    if not ctx.today:
        return []
    today, p = ctx.today, ctx.pronoun
    cands = festival_dates([today.year, today.year + 1])
    if ctx.her_birthday:
        for y in (today.year, today.year + 1):
            dd = safe_date(y, ctx.her_birthday[0], ctx.her_birthday[1])
            if dd:
                cands.append((f"{p}的生日", dd))
    skip = ("父亲节" if p == "她" else "母亲节", "元旦", "除夕", "重阳")
    cands = sorted([c for c in cands if c[1] >= today and c[0] not in skip], key=lambda x: x[1])
    return [{"name": name, "date": dd.isoformat(), "days": (dd - today).days} for name, dd in cands[:2]]


def sec_signals(ctx, S):
    """该打电话了：🔴 / 🟡。定义见 metrics.md，阈值在 SIGNAL_RULES。"""
    R, p, lex = SIGNAL_RULES, ctx.pronoun, ctx.lex
    ex = lex.get("exclude", {})
    d = ctx.d
    signals = []
    for m in ctx.her_text:
        c = m["content"]
        # 她提到自己的身体（不是在问你），你没回或回了 ≤ 4 个字
        if (has_any(c, lex["health_red"], ex.get("health_red")) and "你" not in c
                and not any(q in c for q in ("吗", "没", "？", "?")) and not re.search(r"(.)不\1", c)):
            reply = next((x for x in ctx.msgs[m["_i"] + 1:m["_i"] + 4] if x["sender"] == "me"), None)
            if reply is None or (reply["type"] == "text" and reply["_chars"] <= R["health_reply_chars"]):
                signals.append({"level": "red", "kind": "health_short_reply",
                                "text": f"{m['_dt'].strftime('%m-%d') if m['_dt'] else ''} {p}说“{m['content'][:20]}”，你"
                                        + (f"回了“{reply['content'][:10]}”{reply['_chars']} 个字" if reply else "没有回")})
                break
    shrink, nothing, trend = d["shrink"], d["nothing"], d["trend"]
    if len(shrink) >= R["self_shrink_min"]:
        signals.append({"level": "red", "kind": "self_shrink",
                        "text": f"{p}有 {len(shrink)} 次用“{shrink[-1]['content'][:8]}”这类话收尾——{p}在把自己缩小"})
    if trend and trend["sticker_ratio_prior"] > 0 and trend["sticker_ratio_recent"] >= trend["sticker_ratio_prior"] * R["sticker_mult"] \
            and trend["sticker_ratio_recent"] >= R["sticker_min"]:
        signals.append({"level": "red", "kind": "text_to_sticker",
                        "text": f"{p}最近一个月发表情包的比例从 {round(100 * trend['sticker_ratio_prior'])}% 涨到 {round(100 * trend['sticker_ratio_recent'])}%——文字变少了，不是不想说"})
    if trend and trend["change_pct"] is not None and trend["change_pct"] <= R["opens_drop_pct"]:
        signals.append({"level": "yellow", "kind": "her_opens_drop",
                        "text": f"{p}主动找你的次数比之前少了 {abs(trend['change_pct'])}%——不是不想找，是在等你"})
    if trend and trend["call_s_prior_per30d"] > 0 and trend["call_s_recent"] <= trend["call_s_prior_per30d"] * R["call_drop_ratio"]:
        signals.append({"level": "yellow", "kind": "call_drop",
                        "text": f"通话时长比之前少了一半以上（最近 30 天 {trend['call_s_recent'] // 60} 分钟）"})
    if len(nothing) >= R["nothing_min"]:
        signals.append({"level": "yellow", "kind": "nothing", "text": f"{p}说了 {len(nothing)} 次“没事”"})
    if S["opens"].get("days_since_my_last_open", 0) >= R["my_open_gap_days"]:
        signals.append({"level": "yellow", "kind": "my_open_gap",
                        "text": f"你上一次主动开口是 {S['opens']['days_since_my_last_open']} 天前"})
    return signals


def sec_index(ctx, S):
    """三个指数（0–100）。权重在 FORMULA，定义在 metrics.md。"""
    F = FORMULA
    active_days = ctx.d["active_days"]
    A = S["opens"]["her_ratio"] or 0
    B = S["care_ratio"]
    C = S["hours"]["her_offhour_ratio"]
    D = min((len(ctx.her) / active_days) / F["care"]["density_per_day"], 1) if active_days else 0
    fc = F["care"]
    index = {"care": {"score": round(100 * (fc["her_open_ratio"] * A + fc["care_ratio"] * B + fc["offhour_ratio"] * C + fc["density"] * D)),
                      "parts": {"her_open_ratio": A, "care_ratio": B, "offhour_ratio": C, "density": round(D, 3)}}}
    sr = S["short"]["ratio"] or 0
    ur = S["unanswered"]["ratio"] or 0
    lat_h = (S["reply"]["me"]["median_s"] or 0) / 3600
    L = min(lat_h / F["short"]["latency_cap_h"], 1)
    fs = F["short"]
    index["short"] = {"score": round(100 * (fs["short_ratio"] * sr + fs["unanswered_ratio"] * ur + fs["latency"] * L)),
                      "parts": {"short_ratio": sr, "unanswered_ratio": ur, "latency_score": round(L, 3)}}
    unanswered, chase = ctx.d["unanswered"], ctx.d["chase"]
    if unanswered:
        rr = S["unanswered"]["reopen_ratio"] or 0
        cr = min(len(chase) / len(unanswered), 1)
        ff = F["forgive"]
        index["forgive"] = {"score": round(100 * (ff["reopen_ratio"] * rr + ff["no_chase"] * (1 - cr))),
                            "parts": {"reopen_ratio": rr, "chase_ratio": round(cr, 3)}}
    else:
        index["forgive"] = {"score": None, "parts": {}, "note": "没有被晾过 24 小时以上的记录"}
    ctx.d.update(sr=sr, ur=ur, lat_h=lat_h, A=A)
    return index


def sec_mother_type(ctx, S):
    """她的类型（10 型）。分数最高的是主型，第二且 > secondary_min 的是副型。"""
    R, d = MOTHER_RULES, ctx.d
    tc = d["topic_counter"]
    n_ht = max(len(ctx.her_text), 1)
    her_n = max(len(ctx.her), 1)
    her_fast = (S["reply"]["her"]["median_s"] or 1e9) < R["wait_fast_s"]
    scores = {
        "三餐监督型": tc.get("吃饭", 0) / n_ht,
        "天气预报型": tc.get("天气", 0) / n_ht,
        "养生转发型": S["forwards"]["health"] / her_n * 2,
        "查岗型": tc.get("查岗", 0) / n_ht,
        "钱够不够型": tc.get("钱", 0) / n_ht + S["extras"]["her_transfer_count"] / her_n,
        "语音轰炸型": len(d["her_voice"]) / her_n,
        "催婚型": tc.get("对象结婚", 0) / n_ht * 1.5,
        "等你先开口型": (0.6 if (d["A"] < R["wait_open_ratio"] and her_fast) else 0),
        "沉默守望型": ((S["extras"]["her_sticker_count"] + S["extras"]["her_image_count"]) / her_n) if len(ctx.her_text) / her_n < R["silent_text_ratio"] else 0,
        "新闻联播型": S["forwards"]["news"] / her_n * 2,
    }
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return {"primary": ranked[0][0] if ranked[0][1] > 0 else "还看不出来",
            "secondary": ranked[1][0] if ranked[1][1] > R["secondary_min"] else None,
            "scores": {k: round(v, 3) for k, v in ranked}}


def sec_child_type(ctx, S):
    """你的类型（6 型）。阈值在 CHILD_RULES，定义在 types.md。"""
    R, d, lex = CHILD_RULES, ctx.d, ctx.lex
    tc, my_opens = d["topic_counter"], d["my_opens"]
    my_neg = sum(1 for m in ctx.me_text if has_any(m["content"], lex["my_negative"], lex.get("exclude", {}).get("my_negative")))
    my_open_weekend = sum(1 for o in my_opens if o["_dt"].weekday() >= 5) / len(my_opens) if my_opens else 0
    sr, ur, lat_h = d["sr"], d["ur"], d["lat_h"]
    ctype = []
    if sr >= R["short_ratio"]:
        ctype.append(("嗯哦好选手", sr))
    if ur >= R["unanswered_ratio"]:
        ctype.append(("已读不回选手", ur))
    if lat_h < R["fast_h"] and sr >= R["fast_short_ratio"]:
        ctype.append(("秒回三个字型", sr))
    if S["hours"]["me_late_ratio"] >= R["late_ratio"]:
        ctype.append(("深夜忏悔型", S["hours"]["me_late_ratio"]))
    if my_open_weekend >= R["weekend_ratio"] and len(my_opens) >= R["weekend_min_opens"]:
        ctype.append(("周末选手", my_open_weekend))
    if my_neg == 0 and tc.get("身体", 0) >= R["body_asks"]:
        ctype.append(("报喜不报忧型", 0.5))
    ctype.sort(key=lambda x: -x[1])
    return {"primary": ctype[0][0] if ctype else "正常人类子女", "all": [c[0] for c in ctype]}


def sec_rating(ctx, S):
    red = sum(1 for s in S["signals"] if s["level"] == "red")
    score = S["index"]["short"]["score"] + RED_WEIGHT * red
    for upper, label in RATING_BANDS:
        if upper is None or score < upper:
            return {"label": label, "score": score}


def sec_bill(ctx, S):
    return {"her_sent": len(ctx.her), "me_sent": len(ctx.me), "balance": len(ctx.her) - len(ctx.me),
            "unanswered": len(ctx.d["unanswered"]), "calls": len(ctx.d["calls"])}


# ---------- 组装 ----------

def compute(data, today=None, her_birthday=None, my_birthday=None, lexicon=None):
    """messages.json 的内容 → stats 字典。today 是 date；生日是 "MM-DD"；lexicon 不给就读 references/lexicon.json。
    不改写传入的 data。"""
    lex = lexicon or load_lexicon()
    ctx = Ctx(data, lex, today=today,
              her_birthday=parse_mmdd(her_birthday) if her_birthday else None,
              my_birthday=parse_mmdd(my_birthday) if my_birthday else None)
    S = {"schema": SCHEMA_VERSION, "lexicon": lex.get("version"), "her_name": ctx.her_name, "pronoun": ctx.pronoun, "warnings": []}
    S["warnings"].extend(sec_warnings(ctx, S))
    S["basics"] = sec_basics(ctx, S)
    S["opens"] = sec_opens(ctx, S)
    S["reply"] = sec_reply(ctx, S)
    longest = sec_longest(ctx, S)
    if longest is not None:
        S["longest"] = longest
    S["longest_voice_s"] = max((m.get("dur") or 0) for m in ctx.her if m["type"] == "voice") if any(m["type"] == "voice" for m in ctx.her) else 0
    S["short"] = sec_short(ctx, S)
    S["topics"] = sec_topics(ctx, S)
    S["care_ratio"] = sec_care_ratio(ctx, S)
    S["hours"] = sec_hours(ctx, S)
    S["unanswered"] = sec_unanswered(ctx, S)
    S["phrases"] = sec_phrases(ctx, S)
    S["extras"] = sec_extras(ctx, S)
    S["composition"] = sec_composition(ctx, S)
    S["emoji"] = sec_emoji(ctx, S)
    S["catchphrases"] = sec_catchphrases(ctx, S)
    S["forwards"] = sec_forwards(ctx, S)
    S["weekly"] = sec_weekly(ctx, S)
    S["trend"] = sec_trend(ctx, S)
    S["festivals"] = sec_festivals(ctx, S)
    S["countdown"] = sec_countdown(ctx, S)
    S["signals"] = sec_signals(ctx, S)
    S["index"] = sec_index(ctx, S)
    S["mother_type"] = sec_mother_type(ctx, S)
    S["child_type"] = sec_child_type(ctx, S)
    S["rating"] = sec_rating(ctx, S)
    S["bill"] = sec_bill(ctx, S)
    return S


# ---------- Markdown 摘要 ----------

def summary_md(S):
    p = S["pronoun"]; b = S["basics"]; ix = S["index"]
    L = []
    L.append(f"# 妈妈的消息 · 统计摘要（{b['first'] or '—'} → {b['last'] or '—'}，{b['span_days'] or '—'} 天，{b['total']} 条）")
    L.append(f"{p} {b['her']} 条 / 你 {b['me']} 条 · 有时间戳 {b['with_ts']} 条")
    L.append("")
    def bar(s): return "█" * round(s / 10) + "░" * (10 - round(s / 10)) if s is not None else "——"
    L.append(f"💛 牵挂指数   {ix['care']['score']:>3} {bar(ix['care']['score'])}")
    L.append(f"🧊 嗯哦好指数 {ix['short']['score']:>3} {bar(ix['short']['score'])}")
    fs = ix['forgive']['score']
    L.append(f"🕰️ 不计较指数 {(fs if fs is not None else '—'):>3} {bar(fs)}")
    L.append("")
    L.append(f"- 谁先开口：{p} {S['opens']['her']} 次 / 你 {S['opens']['me']} 次")
    L.append(f"- 你回{p}：中位 {S['reply']['me']['median']}，最长 {S['reply']['me']['max']}" + (f"（{p}那条：“{S['reply']['me']['max_msg']['content']}”）" if S['reply']['me']['max_msg'] else ""))
    L.append(f"- {p}回你：中位 {S['reply']['her']['median']}")
    if S.get("longest"):
        lg = S["longest"]
        L.append(f"- {p}最长的一条：{lg['chars']} 字“{lg['content'][:30]}” / 你回：{lg['reply']}（{lg['reply_chars']} 字）")
    L.append(f"- 短回复：{S['short']['count']} 条，占你 {S['short'].get('replies', '—')} 条回复的 {round(100*(S['short']['ratio'] or 0))}% {S['short']['top']}")
    L.append(f"- 没回：{S['unanswered']['count']} / {S['unanswered']['turns']} 段，之后{p}先开口 {S['unanswered']['reopened_by_her']} 次")
    L.append(f"- {p}最常问：" + "、".join(f"{t['topic']}{t['count']}" for t in S['topics'][:3]))
    L.append(f"- 时段：{p} {S['hours']['her_peak'] or '记录不够'} / 你 {S['hours']['me_peak'] or '记录不够'}")
    L.append(f"- 成分表：" + " · ".join(f"{c['name']}{c['pct']}%" for c in S['composition'][:6]))
    L.append(f"- 表情：{p} {S['emoji']['her']} / 你 {S['emoji']['me']}")
    L.append(f"- 口头禅：{p} {[c[0] for c in S['catchphrases']['her']]} / 你 {[c[0] for c in S['catchphrases']['me']]}")
    L.append(f"- 转发：{S['forwards']['count']} 篇，养生 {S['forwards']['health']}，你回了 {S['forwards']['my_reply_count']} 篇")
    if S["festivals"]:
        L.append("- 节日：" + " · ".join(f"{f['name']}{'无' if not f['first'] else (p if f['first']=='her' else '你') + f['time']}" for f in S["festivals"][-6:]))
    L.append(f"- 倒计时：" + " · ".join(f"{c['name']} {c['days']} 天" for c in S["countdown"]))
    L.append(f"- 鉴定：{p} {S['mother_type']['primary']}" + (f"（副：{S['mother_type']['secondary']}）" if S['mother_type']['secondary'] else "") + f" / 你 {S['child_type']['primary']} / 评级 {S['rating']['label']}")
    for s in S["signals"]:
        L.append(f"- {'🔴' if s['level']=='red' else '🟡'} {s['text']}")
    for w in S["warnings"]:
        L.append(f"- ⚠️ {w}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("messages", help="messages.json")
    ap.add_argument("--out", default="stats.json")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD，算倒计时和多久没主动开口；默认今天")
    ap.add_argument("--her-birthday", default=None, help="MM-DD")
    ap.add_argument("--my-birthday", default=None, help="MM-DD")
    ap.add_argument("--lexicon", default=None, help="换一份词表（默认 references/lexicon.json），校准用")
    ap.add_argument("--quiet", action="store_true", help="不打印摘要")
    a = ap.parse_args()
    data = load_json(a.messages)
    try:
        today = date.fromisoformat(a.today) if a.today else date.today()
    except ValueError:
        print(f"--today 要写成 2026-08-30 这样的日期，现在是 {a.today!r}")
        sys.exit(1)
    try:
        lex = load_lexicon(a.lexicon)
        S = compute(data, today=today, her_birthday=a.her_birthday, my_birthday=a.my_birthday, lexicon=lex)
    except (ValueError, FileNotFoundError) as e:
        print(f"✗ {e}")
        sys.exit(1)
    S["today"] = today.isoformat()
    dump_json(S, a.out)
    if not a.quiet:
        print(summary_md(S))
        print(f"\n→ {a.out}")


if __name__ == "__main__":
    main()
