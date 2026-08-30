#!/usr/bin/env python3
"""
妈妈的消息 · 统计引擎

用法:
  python scripts/stats.py messages.json [--out stats.json] [--today 2026-08-30]
                          [--her-birthday 03-15] [--my-birthday 11-02]

输入 messages.json 的格式见 SKILL.md「工作表」一节。
输出 stats.json（所有数字都在这里，报告里的每个数字都能追溯到这个文件）
同时在终端打印一份 Markdown 摘要。

只用标准库，不联网，不写任何东西到别的地方。
"""
import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta

# Windows 默认控制台是 GBK，打不出 emoji；统一把输出切到 UTF-8（其他平台无影响）
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ---------- 词典（改这里就能调指标，报告里的定义要和 references/metrics.md 一致） ----------

SHORT_REPLIES = {"嗯", "哦", "好", "好的", "好吧", "行", "知道了", "嗯嗯", "哦哦", "在忙", "忙",
                 "没事", "收到", "ok", "OK", "Ok", "嗯好", "好嘞", "知道", "行吧", "好好", "嗯呢"}

TOPICS = {
    "吃饭":   ["吃饭", "吃了吗", "吃了没", "吃的什么", "吃啥", "早饭", "午饭", "晚饭", "别饿", "好好吃", "外卖", "做饭", "吃点"],
    "回家":   ["回家", "什么时候回", "啥时候回", "回来", "放假", "过年回", "车票", "到家", "回不回"],
    "身体":   ["身体", "感冒", "发烧", "医院", "检查", "吃药", "疼", "痛", "不舒服", "体检", "血压", "熬夜", "注意身体", "保重", "腰", "颈椎", "胃"],
    "天气":   ["天气", "降温", "下雨", "加衣", "多穿", "冷", "热", "台风", "下雪", "带伞", "变天", "穿厚"],
    "钱":     ["钱", "够不够", "生活费", "工资", "花钱", "省着", "转你", "打给你", "卡里"],
    "工作学习": ["工作", "上班", "加班", "考试", "学习", "面试", "公司", "领导", "项目", "论文", "忙不忙", "下班"],
    "对象结婚": ["对象", "男朋友", "女朋友", "相亲", "结婚", "谈了吗", "处对象", "介绍", "谈朋友"],
    "睡觉":   ["早点睡", "睡了吗", "早点休息", "别熬夜", "睡觉", "晚安", "睡吧"],
    "查岗":   ["在干嘛", "干什么呢", "到了吗", "到家了吗", "在哪", "忙吗", "在吗", "干嘛呢", "在不在"],
}
CARE_TOPICS = {"吃饭", "回家", "身体", "天气", "钱", "睡觉", "查岗"}

SELF_SHRINK = ["打扰你了", "你忙吧", "不打扰", "那你忙", "没事了", "不说了", "你忙你的", "不耽误你", "先不说了"]
CHASE = ["怎么不回", "不理我", "看到了吗", "咋不回", "不回我", "在不在啊", "回个话"]
NOTHING = ["没事", "没什么事", "没啥事"]
HEALTH_RED = ["腰", "疼", "痛", "医院", "检查", "血压", "头晕", "感冒", "住院", "手术", "体检", "不舒服", "摔", "骨", "药"]
HEALTH_LINK = ["养生", "健康", "医生", "癌", "血", "肝", "肾", "颈椎", "腰", "睡眠", "补", "食物", "菜", "水果", "熬夜", "秘方", "长寿"]
NEWS_LINK = ["新闻", "通知", "紧急", "转发", "扩散", "重要", "公告", "提醒", "注意"]
MY_NEGATIVE = ["累", "难受", "病", "不舒服", "压力", "哭", "烦", "崩溃", "失眠", "发烧", "感冒"]

STOPWORDS = set("的了我你她他是在吗呢啊吧也就都还有没不这那个和跟给到去说要会能把被让从对于但把很太又再才已经什么怎么这样那样一个我们你们他们自己没有可以知道现在今天明天昨天时候东西然后因为所以如果虽然或者而且".strip())

EMOJI_RE = re.compile(r"\[([^\[\]]{1,6})\]")
TYPE_CN = {"sticker": "表情包", "image": "图片", "voice": "语音", "link": "链接", "video": "视频", "transfer": "转账",
           "call_voice": "语音通话", "call_video": "视频通话", "recall": "撤回的消息", "location": "位置", "file": "文件", "other": "其他"}

# 固定日期表（农历节日没法用标准库算，先查表；表外年份跳过）
LUNAR = {
    "春节": {2022: "02-01", 2023: "01-22", 2024: "02-10", 2025: "01-29", 2026: "02-17", 2027: "02-06", 2028: "01-26", 2029: "02-13", 2030: "02-03"},
    "中秋": {2022: "09-10", 2023: "09-29", 2024: "09-17", 2025: "10-06", 2026: "09-25", 2027: "09-15", 2028: "10-03", 2029: "09-22", 2030: "09-12"},
    "重阳": {2022: "10-04", 2023: "10-23", 2024: "10-11", 2025: "10-29", 2026: "10-18", 2027: "10-08", 2028: "10-26", 2029: "10-16", 2030: "10-05"},
}


# ---------- 工具 ----------

def parse_ts(s):
    if not s:
        return None
    s = s.strip().replace("/", "-")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


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


def fmt_delta(seconds):
    if seconds is None:
        return "—"
    m = int(seconds // 60)
    if m < 60:
        return f"{m} 分钟"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h} 小时 {m} 分" if m else f"{h} 小时"
    d, h = divmod(h, 24)
    return f"{d} 天 {h} 小时" if h else f"{d} 天"


def has_any(text, words):
    return any(w in text for w in words)


def topic_of(text):
    hits = [t for t, kws in TOPICS.items() if has_any(text, kws)]
    return hits


# ---------- 主计算 ----------

def compute(data, today=None, her_birthday=None, my_birthday=None):
    her_name = data.get("her", "妈妈")
    pronoun = data.get("her_pronoun", "她")
    msgs = data["messages"]
    n_unknown = sum(1 for m in msgs if m.get("sender") not in ("her", "me"))
    if n_unknown:
        msgs = [m for m in msgs if m.get("sender") in ("her", "me")]
    for i, m in enumerate(msgs):
        m["_i"] = i
        m["_dt"] = parse_ts(m.get("ts"))
        m["type"] = m.get("type") or "text"
        m["content"] = m.get("content") or ""
        m["_chars"] = len(m["content"].strip()) if m["type"] == "text" else 0

    her = [m for m in msgs if m["sender"] == "her"]
    me = [m for m in msgs if m["sender"] == "me"]
    dated = [m for m in msgs if m["_dt"]]
    her_text = [m for m in her if m["type"] == "text"]
    me_text = [m for m in me if m["type"] == "text"]

    S = {"her_name": her_name, "pronoun": pronoun, "warnings": []}
    if len(msgs) < 20:
        S["warnings"].append("记录不到 20 条，只出基础数字，不写解读。")
    if n_unknown:
        S["warnings"].append(f"有 {n_unknown} 条消息的 sender 不是 her / me，已忽略。")
    if len(msgs) >= 20 and len(dated) < len(msgs) * 0.5:
        S["warnings"].append(f"{len(msgs) - len(dated)} 条没有时间戳（占 {round(100 * (1 - len(dated) / len(msgs)))}%），"
                             "谁先开口、回复间隔、时段、没回这几项不稳，报告的数据说明里要写明。")
    backwards = sum(1 for x, y in zip(dated, dated[1:]) if y["_dt"] < x["_dt"])
    if backwards:
        S["warnings"].append(f"有 {backwards} 处时间倒序，messages.json 可能没按时间排好；先跑 scripts/validate.py 看一下。")

    # --- 基础 ---
    first = dated[0]["_dt"] if dated else None
    last = dated[-1]["_dt"] if dated else None
    span_days = (last.date() - first.date()).days + 1 if first else None
    active_days = len({m["_dt"].date() for m in dated})
    S["basics"] = {
        "total": len(msgs), "her": len(her), "me": len(me),
        "her_text": len(her_text), "me_text": len(me_text),
        "first": first.strftime("%Y-%m-%d") if first else None,
        "last": last.strftime("%Y-%m-%d") if last else None,
        "span_days": span_days, "active_days": active_days,
        "with_ts": len(dated), "without_ts": len(msgs) - len(dated),
    }

    # --- 对话开启（间隔 ≥ 6 小时） ---
    opens = []
    prev = None
    for m in dated:
        if prev is None or (m["_dt"] - prev["_dt"]) >= timedelta(hours=6):
            opens.append(m)
        prev = m
    her_opens = [m for m in opens if m["sender"] == "her"]
    my_opens = [m for m in opens if m["sender"] == "me"]
    S["opens"] = {"her": len(her_opens), "me": len(my_opens),
                  "her_ratio": round(len(her_opens) / len(opens), 3) if opens else None,
                  "my_last_open": my_opens[-1]["_dt"].strftime("%Y-%m-%d") if my_opens else None,
                  "her_last_open": her_opens[-1]["_dt"].strftime("%Y-%m-%d") if her_opens else None}
    if today and my_opens:
        S["opens"]["days_since_my_last_open"] = (today - my_opens[-1]["_dt"].date()).days
    if today and her_opens:
        S["opens"]["days_since_her_last_open"] = (today - her_opens[-1]["_dt"].date()).days

    # --- 回复间隔（只用有时间戳的相邻异方消息对） ---
    def latencies(from_side, to_side):
        out = []
        for i, m in enumerate(dated[:-1]):
            if m["sender"] != from_side:
                continue
            nxt = dated[i + 1]
            if nxt["sender"] == to_side:
                out.append(((nxt["_dt"] - m["_dt"]).total_seconds(), m, nxt))
        return out
    my_lat = latencies("her", "me")
    her_lat = latencies("me", "her")

    def lat_summary(lats):
        if not lats:
            return {"n": 0, "median_s": None, "median": "—", "max_s": None, "max": "—", "max_msg": None}
        secs = [x[0] for x in lats]
        mx = max(lats, key=lambda x: x[0])
        return {"n": len(lats), "median_s": statistics.median(secs), "median": fmt_delta(statistics.median(secs)),
                "max_s": mx[0], "max": fmt_delta(mx[0]),
                "max_msg": {"date": mx[1]["_dt"].strftime("%m-%d"), "content": (mx[1]["content"][:40] if mx[1]["type"] in ("text", "link") else f"[{TYPE_CN.get(mx[1]['type'], mx[1]['type'])}]"), "type": mx[1]["type"]}}
    S["reply"] = {"me": lat_summary(my_lat), "her": lat_summary(her_lat)}

    # --- 她最长的一条 vs 我的回复 ---
    if her_text:
        longest = max(her_text, key=lambda m: m["_chars"])
        reply = next((m for m in msgs[longest["_i"] + 1:] if m["sender"] == "me"), None)
        # 如果中间又是她开了新话题就不算回复
        if reply:
            between = [m for m in msgs[longest["_i"] + 1:reply["_i"]] if m["sender"] == "her"]
            if len(between) > 2:
                reply = None
        S["longest"] = {"chars": longest["_chars"], "content": longest["content"][:60],
                        "date": longest["_dt"].strftime("%m-%d") if longest["_dt"] else None,
                        "reply_chars": reply["_chars"] if reply and reply["type"] == "text" else (0 if reply is None else None),
                        "reply": (reply["content"][:40] if reply and reply["type"] == "text" else (f"[{TYPE_CN.get(reply['type'], reply['type'])}]" if reply else None))}
    voices = [m for m in her if m["type"] == "voice"]
    S["longest_voice_s"] = max((m.get("dur") or 0) for m in voices) if voices else 0

    # --- 短回复 ---
    def is_short(m):
        c = m["content"].strip()
        if any(w in c for w in ("谢", "爱", "想")) or c.endswith("妈") or c.endswith("爸"):
            return False
        return c in SHORT_REPLIES or (0 < len(c) <= 3 and not EMOJI_RE.search(c))
    # "回复"= 你的消息里，紧跟在她的消息后面（你连着发的几条都算）、且没有隔到 24 小时以上的。
    # 隔了 24 小时以上她那段已经算"没回"，你那条是新开口；"在吗""妈我到了"这种自己先开口的也不是回复。
    # 注意不能用 6 小时的"开启对话"规则来判：她早上发、你晚上回的"嗯"隔了 12 小时，仍然是回复，而且正是要数的那种。
    reply_flag = {}
    prev = None
    for m in msgs:
        if m["sender"] == "me":
            if prev is None:
                reply_flag[m["_i"]] = False
            elif prev["sender"] == "her":
                reply_flag[m["_i"]] = not (m["_dt"] and prev["_dt"]) or (m["_dt"] - prev["_dt"]) < timedelta(hours=24)
            else:
                reply_flag[m["_i"]] = reply_flag.get(prev["_i"], False)
        prev = m
    me_replies = [m for m in me_text if reply_flag.get(m["_i"])]
    shorts = [m for m in me_replies if is_short(m)]
    S["short"] = {"count": len(shorts), "replies": len(me_replies),
                  "ratio": round(len(shorts) / len(me_replies), 3) if me_replies else None,
                  "top": Counter(m["content"].strip() for m in shorts).most_common(5)}

    # --- 她最常问的事 ---
    topic_counter = Counter()
    topic_example = {}
    for m in her_text:
        for t in topic_of(m["content"]):
            topic_counter[t] += 1
            topic_example.setdefault(t, m["content"][:30])
    S["topics"] = [{"topic": t, "count": c, "example": topic_example[t]} for t, c in topic_counter.most_common()]
    care_hits = sum(1 for m in her_text if any(t in CARE_TOPICS for t in topic_of(m["content"])))
    S["care_ratio"] = round(care_hits / len(her_text), 3) if her_text else 0

    # --- 时段 ---
    def hour_hist(side):
        h = [0] * 24
        for m in dated:
            if m["sender"] == side:
                h[m["_dt"].hour] += 1
        return h
    her_h, me_h = hour_hist("her"), hour_hist("me")
    def peak2(h):
        best = max(range(24), key=lambda i: h[i] + h[(i + 1) % 24])
        return f"{best:02d}:00–{(best + 2) % 24:02d}:00"
    S["hours"] = {"her": her_h, "me": me_h,
                  "her_peak": peak2(her_h) if sum(her_h) >= 20 else None,
                  "me_peak": peak2(me_h) if sum(me_h) >= 20 else None}
    her_dated = [m for m in dated if m["sender"] == "her"]
    me_dated = [m for m in dated if m["sender"] == "me"]
    S["hours"]["her_offhour_ratio"] = round(sum(1 for m in her_dated if m["_dt"].hour < 8 or m["_dt"].hour >= 22) / len(her_dated), 3) if her_dated else 0
    S["hours"]["her_early_count"] = sum(1 for m in her_dated if 4 <= m["_dt"].hour < 8)      # 早上 8 点前（4–8 点）
    S["hours"]["her_late_count"] = sum(1 for m in her_dated if m["_dt"].hour >= 22 or m["_dt"].hour < 4)  # 晚上 10 点后
    S["hours"]["me_late_ratio"] = round(sum(1 for m in me_dated if m["_dt"].hour >= 23 or m["_dt"].hour < 5) / len(me_dated), 3) if me_dated else 0

    # --- 她发了我没回（turn 级） ---
    # 一个 turn = 她连续发的一段（相邻两条间隔 < 6 小时）。
    # 判定没回：turn 之后要么没人再说话，要么下一条是她自己隔了 6 小时以上又开的口，要么我 24 小时后才回。
    turns = []
    i = 0
    while i < len(msgs):
        if msgs[i]["sender"] == "her":
            j = i
            while (j + 1 < len(msgs) and msgs[j + 1]["sender"] == "her"
                   and not (msgs[j]["_dt"] and msgs[j + 1]["_dt"] and msgs[j + 1]["_dt"] - msgs[j]["_dt"] >= timedelta(hours=6))):
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
            if lastm["_dt"] and today and (today - lastm["_dt"].date()).days >= 1:
                unanswered.append(lastm)
            continue
        if nxt["sender"] == "her":
            unanswered.append(lastm); reopen_her += 1
        elif lastm["_dt"] and nxt["_dt"] and nxt["_dt"] - lastm["_dt"] >= timedelta(hours=24):
            unanswered.append(lastm)
    S["unanswered"] = {
        "count": len(unanswered), "turns": len(turns),
        "ratio": round(len(unanswered) / len(turns), 3) if turns else None,
        "items": [{"date": m["_dt"].strftime("%m-%d %H:%M") if m["_dt"] else "—",
                   "content": m["content"][:40] if m["type"] in ("text", "link") else f"[{TYPE_CN.get(m['type'], m['type'])}]",
                   "type": m["type"]} for m in unanswered[-8:]],
        "reopened_by_her": reopen_her,
        "reopen_ratio": round(reopen_her / len(unanswered), 3) if unanswered else None,
    }

    # --- 她的措辞信号 ---
    chase = [m for m in her_text if has_any(m["content"], CHASE)]
    shrink = [m for m in her_text if has_any(m["content"], SELF_SHRINK)]
    nothing = [m for m in her_text if has_any(m["content"], NOTHING)]
    S["phrases"] = {"chase": len(chase), "self_shrink": len(shrink), "self_shrink_examples": [m["content"][:30] for m in shrink[-3:]],
                    "nothing": len(nothing)}

    # --- 附加统计 ---
    her_voice = [m for m in her if m["type"] == "voice"]
    calls = [m for m in msgs if m["type"] in ("call_voice", "call_video")]
    S["extras"] = {
        "her_voice_count": len(her_voice), "her_voice_total_s": sum((m.get("dur") or 0) for m in her_voice),
        "me_voice_count": sum(1 for m in me if m["type"] == "voice"),
        "call_count": len(calls), "call_total_s": sum((m.get("dur") or 0) for m in calls),
        "her_transfer_count": sum(1 for m in her if m["type"] == "transfer"),
        "me_transfer_count": sum(1 for m in me if m["type"] == "transfer"),
        "her_image_count": sum(1 for m in her if m["type"] == "image"),
        "her_link_count": sum(1 for m in her if m["type"] == "link"),
        "her_sticker_count": sum(1 for m in her if m["type"] == "sticker"),
        "her_recall_count": sum(1 for m in her if m["type"] == "recall"),
    }

    # --- 成分表 ---
    comp = Counter()
    for m in her:
        if m["type"] == "text":
            ts = topic_of(m["content"])
            key = ts[0] if ts else "其他文字"
            comp[key] += 1
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
    S["composition"] = [{"name": k, "count": v, "pct": round(100 * v / len(her), 1)} for k, v in comp.most_common()] if her else []

    # --- 表情符号 ---
    def emoji_top(side_text):
        c = Counter()
        for m in side_text:
            for e in EMOJI_RE.findall(m["content"]):
                c[e] += 1
        return c.most_common(5)
    S["emoji"] = {"her": emoji_top(her), "me": emoji_top(me)}

    # --- 口头禅（2-4 字片段频率，粗糙但不用装分词库） ---
    def catchphrases(side_text, topn=5):
        clean = lambda t: re.sub(r"[^\u4e00-\u9fff]", "", EMOJI_RE.sub("", t))
        exact = Counter(clean(m["content"]) for m in side_text)
        exact = [(g, n) for g, n in exact.most_common() if 2 <= len(g) <= 10 and n >= 2]
        c = Counter()
        for m in side_text:
            t = re.sub(r"[^\u4e00-\u9fff]", " ", EMOJI_RE.sub("", m["content"]))
            for chunk in t.split():
                seen = set()
                for n in (2, 3, 4):
                    for k in range(len(chunk) - n + 1):
                        g = chunk[k:k + n]
                        if g in seen or g[0] in STOPWORDS or g[-1] in STOPWORDS:
                            continue
                        seen.add(g); c[g] += 1
        grams = [(g, n) for g, n in c.most_common(80) if n >= 3]
        keep = []
        for g, n in grams:
            if any(g != h and g in h and m >= n * 0.7 for h, m in grams):
                continue
            if any(g in e for e, _ in exact[:topn]):
                continue
            keep.append((g, n))
        return (exact[:topn] + keep)[:topn]
    S["catchphrases"] = {"her": catchphrases(her_text), "me": catchphrases(me_text)}

    # --- 她转给你的 ---
    links = [m for m in her if m["type"] == "link"]
    S["forwards"] = {"count": len(links),
                     "health": sum(1 for m in links if has_any(m["content"], HEALTH_LINK)),
                     "news": sum(1 for m in links if has_any(m["content"], NEWS_LINK)),
                     "titles": [m["content"][:30] for m in links[-6:]],
                     "my_reply_count": sum(1 for m in links if m["_i"] + 1 < len(msgs) and msgs[m["_i"] + 1]["sender"] == "me")}

    # --- 每周量 & 趋势 ---
    weekly = defaultdict(lambda: [0, 0])
    for m in dated:
        wk = m["_dt"].strftime("%G-W%V")
        weekly[wk][0 if m["sender"] == "her" else 1] += 1
    S["weekly"] = [{"week": k, "her": v[0], "me": v[1]} for k, v in sorted(weekly.items())]
    trend = None
    if last and span_days and span_days >= 60:
        cut = last - timedelta(days=30)
        prev_start = cut - timedelta(days=90)
        recent = [o for o in her_opens if o["_dt"] > cut]
        prior = [o for o in her_opens if prev_start < o["_dt"] <= cut]
        prior_days = min(90, (cut - max(prev_start, first)).days) or 1
        r_rate, p_rate = len(recent) / 30, len(prior) / prior_days
        trend = {"her_opens_recent_30d": len(recent), "her_opens_prior_per30d": round(p_rate * 30, 1),
                 "change_pct": round(100 * (r_rate - p_rate) / p_rate) if p_rate else None}
        # 表情替代文字
        rec_her = [m for m in her_dated if m["_dt"] > cut]
        pri_her = [m for m in her_dated if prev_start < m["_dt"] <= cut]
        def sticker_ratio(ms):
            return sum(1 for m in ms if m["type"] == "sticker") / len(ms) if ms else 0
        trend["sticker_ratio_recent"] = round(sticker_ratio(rec_her), 3)
        trend["sticker_ratio_prior"] = round(sticker_ratio(pri_her), 3)
        rc = [m for m in calls if m["_dt"] and m["_dt"] > cut]
        pc = [m for m in calls if m["_dt"] and prev_start < m["_dt"] <= cut]
        trend["call_s_recent"] = sum((m.get("dur") or 0) for m in rc)
        trend["call_s_prior_per30d"] = round(sum((m.get("dur") or 0) for m in pc) / prior_days * 30)
    S["trend"] = trend

    # --- 节日记分牌 ---
    check_years = set(range(first.year, last.year + 1)) if first and last else set()
    if today:
        check_years.add(today.year)
    missing_years = sorted(y for y in check_years if y not in LUNAR["春节"])
    if missing_years:
        S["warnings"].append("、".join(map(str, missing_years)) + " 年不在农历节日表里，春节 / 中秋 / 重阳没算；在 stats.py 的 LUNAR 表补上日期即可。")
    board = []
    if first and last:
        years = range(first.year, last.year + 1)
        fests = festival_dates(years)
        if her_birthday:
            for y in years:
                mm, dd = her_birthday.split("-")
                fests.append((f"{pronoun}的生日", date(y, int(mm), int(dd))))
        if my_birthday:
            for y in years:
                mm, dd = my_birthday.split("-")
                fests.append(("你的生日", date(y, int(mm), int(dd))))
        fests.sort(key=lambda x: x[1])
        skip = "父亲节" if pronoun == "她" else "母亲节"
        for name, d in fests:
            if name == skip or not (first.date() <= d <= last.date()):
                continue
            day_msgs = [m for m in dated if m["_dt"].date() == d]
            if not day_msgs:
                board.append({"name": name, "date": d.isoformat(), "first": None})
                continue
            f = day_msgs[0]
            other = next((m for m in day_msgs if m["sender"] != f["sender"]), None)
            board.append({"name": name, "date": d.isoformat(),
                          "first": "her" if f["sender"] == "her" else "me",
                          "time": f["_dt"].strftime("%H:%M"),
                          "content": f["content"][:20] if f["type"] in ("text", "link") else f"[{TYPE_CN.get(f['type'], f['type'])}]",
                          "other_replied": other is not None,
                          "count_her": sum(1 for m in day_msgs if m["sender"] == "her"),
                          "count_me": sum(1 for m in day_msgs if m["sender"] == "me")})
    S["festivals"] = board

    # 倒计时
    countdown = []
    if today:
        cands = festival_dates([today.year, today.year + 1])
        if her_birthday:
            mm, dd = her_birthday.split("-")
            for y in (today.year, today.year + 1):
                cands.append((f"{pronoun}的生日", date(y, int(mm), int(dd))))
        cands = sorted([c for c in cands if c[1] >= today and c[0] not in ("父亲节" if pronoun == "她" else "母亲节", "元旦", "除夕", "重阳")], key=lambda x: x[1])
        for name, d in cands[:2]:
            countdown.append({"name": name, "date": d.isoformat(), "days": (d - today).days})
    S["countdown"] = countdown

    # --- 预警信号 ---
    signals = []
    for m in her_text:
        c = m["content"]
        if (has_any(c, HEALTH_RED) and "你" not in c
                and not any(q in c for q in ("吗", "没", "？", "?")) and not re.search(r"(.)不\1", c)):
            reply = next((x for x in msgs[m["_i"] + 1:m["_i"] + 4] if x["sender"] == "me"), None)
            if reply is None or (reply["type"] == "text" and reply["_chars"] <= 4):
                signals.append({"level": "red", "kind": "health_short_reply",
                                "text": f"{m['_dt'].strftime('%m-%d') if m['_dt'] else ''} {pronoun}说“{m['content'][:20]}”，你" + (f"回了“{reply['content'][:10]}”{reply['_chars']} 个字" if reply else "没有回")})
                break
    if len(shrink) >= 2:
        signals.append({"level": "red", "kind": "self_shrink", "text": f"{pronoun}有 {len(shrink)} 次用“{shrink[-1]['content'][:8]}”这类话收尾——{pronoun}在把自己缩小"})
    if trend and trend["sticker_ratio_prior"] > 0 and trend["sticker_ratio_recent"] >= trend["sticker_ratio_prior"] * 1.8 and trend["sticker_ratio_recent"] >= 0.3:
        signals.append({"level": "red", "kind": "text_to_sticker", "text": f"{pronoun}最近一个月发表情包的比例从 {round(100*trend['sticker_ratio_prior'])}% 涨到 {round(100*trend['sticker_ratio_recent'])}%——文字变少了，不是不想说"})
    if trend and trend["change_pct"] is not None and trend["change_pct"] <= -35:
        signals.append({"level": "yellow", "kind": "her_opens_drop", "text": f"{pronoun}主动找你的次数比之前少了 {abs(trend['change_pct'])}%——不是不想找，是在等你"})
    if trend and trend["call_s_prior_per30d"] > 0 and trend["call_s_recent"] <= trend["call_s_prior_per30d"] * 0.5:
        signals.append({"level": "yellow", "kind": "call_drop", "text": f"通话时长比之前少了一半以上（最近 30 天 {trend['call_s_recent']//60} 分钟）"})
    if len(nothing) >= 3:
        signals.append({"level": "yellow", "kind": "nothing", "text": f"{pronoun}说了 {len(nothing)} 次“没事”"})
    if S["opens"].get("days_since_my_last_open", 0) >= 14:
        signals.append({"level": "yellow", "kind": "my_open_gap", "text": f"你上一次主动开口是 {S['opens']['days_since_my_last_open']} 天前"})
    S["signals"] = signals

    # --- 指数 ---
    A = S["opens"]["her_ratio"] or 0
    B = S["care_ratio"]
    C = S["hours"]["her_offhour_ratio"]
    D = min((len(her) / active_days) / 4, 1) if active_days else 0
    S["index"] = {}
    S["index"]["care"] = {"score": round(100 * (0.35 * A + 0.30 * B + 0.15 * C + 0.20 * D)),
                          "parts": {"her_open_ratio": A, "care_ratio": B, "offhour_ratio": C, "density": round(D, 3)}}
    sr = S["short"]["ratio"] or 0
    ur = S["unanswered"]["ratio"] or 0
    lat_h = (S["reply"]["me"]["median_s"] or 0) / 3600
    L = min(lat_h / 12, 1)
    S["index"]["short"] = {"score": round(100 * (0.45 * sr + 0.35 * ur + 0.20 * L)),
                           "parts": {"short_ratio": sr, "unanswered_ratio": ur, "latency_score": round(L, 3)}}
    if unanswered:
        rr = S["unanswered"]["reopen_ratio"] or 0
        cr = min(len(chase) / len(unanswered), 1)
        S["index"]["forgive"] = {"score": round(100 * (0.6 * rr + 0.4 * (1 - cr))), "parts": {"reopen_ratio": rr, "chase_ratio": round(cr, 3)}}
    else:
        S["index"]["forgive"] = {"score": None, "parts": {}, "note": "没有被晾过 24 小时以上的记录"}

    # --- 类型鉴定 ---
    tc = {t: c for t, c in topic_counter.items()}
    n_ht = max(len(her_text), 1)
    her_n = max(len(her), 1)
    her_fast = (S["reply"]["her"]["median_s"] or 1e9) < 600
    mtype_scores = {
        "三餐监督型": tc.get("吃饭", 0) / n_ht,
        "天气预报型": tc.get("天气", 0) / n_ht,
        "养生转发型": S["forwards"]["health"] / her_n * 2,
        "查岗型": tc.get("查岗", 0) / n_ht,
        "钱够不够型": tc.get("钱", 0) / n_ht + S["extras"]["her_transfer_count"] / her_n,
        "语音轰炸型": len(her_voice) / her_n,
        "催婚型": tc.get("对象结婚", 0) / n_ht * 1.5,
        "等你先开口型": (0.6 if (A < 0.35 and her_fast) else 0),
        "沉默守望型": ((S["extras"]["her_sticker_count"] + S["extras"]["her_image_count"]) / her_n) if len(her_text) / her_n < 0.4 else 0,
        "新闻联播型": S["forwards"]["news"] / her_n * 2,
    }
    ranked = sorted(mtype_scores.items(), key=lambda x: -x[1])
    S["mother_type"] = {"primary": ranked[0][0] if ranked[0][1] > 0 else "还看不出来",
                        "secondary": ranked[1][0] if ranked[1][1] > 0.08 else None,
                        "scores": {k: round(v, 3) for k, v in ranked}}
    my_neg = sum(1 for m in me_text if has_any(m["content"], MY_NEGATIVE))
    my_open_weekend = sum(1 for o in my_opens if o["_dt"].weekday() >= 5) / len(my_opens) if my_opens else 0
    ctype = []
    if sr >= 0.4: ctype.append(("嗯哦好选手", sr))
    if ur >= 0.3: ctype.append(("已读不回选手", ur))
    if lat_h < 0.17 and sr >= 0.3: ctype.append(("秒回三个字型", sr))
    if S["hours"]["me_late_ratio"] >= 0.3: ctype.append(("深夜忏悔型", S["hours"]["me_late_ratio"]))
    if my_open_weekend >= 0.6 and len(my_opens) >= 5: ctype.append(("周末选手", my_open_weekend))
    if my_neg == 0 and tc.get("身体", 0) >= 3: ctype.append(("报喜不报忧型", 0.5))
    ctype.sort(key=lambda x: -x[1])
    S["child_type"] = {"primary": ctype[0][0] if ctype else "正常人类子女", "all": [c[0] for c in ctype]}

    # --- 评级 ---
    red = sum(1 for s in signals if s["level"] == "red")
    score = S["index"]["short"]["score"] + 10 * red
    if score < 25: rating = "模范子女"
    elif score < 45: rating = "还行"
    elif score < 65: rating = "欠一个电话"
    elif score < 80: rating = "欠一顿饭"
    else: rating = "欠一次回家"
    S["rating"] = {"label": rating, "score": score}

    # --- 账单 ---
    S["bill"] = {"her_sent": len(her), "me_sent": len(me), "balance": len(her) - len(me),
                 "unanswered": len(unanswered), "calls": len(calls)}

    for m in msgs:
        for k in ("_i", "_dt", "_chars"):
            m.pop(k, None)
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
    ap = argparse.ArgumentParser()
    ap.add_argument("messages")
    ap.add_argument("--out", default="stats.json")
    ap.add_argument("--today", default=None)
    ap.add_argument("--her-birthday", default=None, help="MM-DD")
    ap.add_argument("--my-birthday", default=None, help="MM-DD")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    data = json.load(open(a.messages, encoding="utf-8"))
    today = date.fromisoformat(a.today) if a.today else date.today()
    S = compute(data, today=today, her_birthday=a.her_birthday, my_birthday=a.my_birthday)
    S["today"] = today.isoformat()
    json.dump(S, open(a.out, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    if not a.quiet:
        print(summary_md(S))
        print(f"\n→ {a.out}")


if __name__ == "__main__":
    main()
