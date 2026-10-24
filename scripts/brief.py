#!/usr/bin/env python3
"""
写作素材包：把 stats.json 的数字和 messages.json 里对应的原话，整理成一份给写文字的 AI 看的 brief.md。

为什么要它：narrative.json 里引号里的话必须是记录里一字不差有的，数字必须能在 stats.json 里找到
（lint_narrative.py 会核对）。几万条记录 AI 读不完，stats.json 里又几乎只有数字。brief.md 把"写得准"
要用的东西摆在一处，篇幅有上限（记录再长也就几千字）：关键数字、她说起自己的事和你的回复、
没回清单带上下文、她最常问的原话、她说过不止一次的话（带时间，翻译表用）、节日那天、她转给你的、
她和你的说话方式（练习模式用）、要不要收着、narrative.json 怎么写。

用法:
  python scripts/brief.py stats.json messages.json [--out brief.md] [--lexicon 词表.json]

stats.json 要是这一版 stats.py 的输出（stats.py 用了 --lexicon 的话这里也给同一份）。只读，只用标准库，不联网。
"""
import argparse
import sys
from collections import Counter, defaultdict

from _common import (MODES, NARRATIVE_REQUIRED, SCHEMA_VERSION, TYPE_CN, fmt_delta, load_json, load_lexicon,
                     required_fields, setup_utf8)
import stats as st

setup_utf8()

UNANSWERED_SHOW = 5
TOPICS_SHOW = 5
REPEATS_SHOW = 10
FESTIVALS_SHOW = 12
SAMPLE_SHOW = 12


def label(m):
    """一条消息的原话：文字和链接给原文，其他给 [语音 23 秒] 这样的标记。"""
    if m["type"] in ("text", "link"):
        return m["content"]
    t = TYPE_CN.get(m["type"], m["type"])
    if m["type"] in ("voice", "call_voice", "call_video") and m.get("dur"):
        return f"[{t} {m['dur']} 秒]"
    if m["type"] == "sticker" and m["content"]:
        return m["content"]
    return f"[{t}]"


def when(m, with_date=True):
    if not m.get("_dt"):
        return "（无时间）"
    return m["_dt"].strftime("%m-%d %H:%M" if with_date else "%H:%M")


class Brief:
    def __init__(self, S, data, lex):
        self.S, self.lex = S, lex
        self.p = S["pronoun"]
        self.her = S["her_name"]
        self.ctx = st.Ctx(data, lex)
        self.by_raw = {m["_raw"]: m for m in self.ctx.msgs}
        self.L = []

    # ---------- 小工具 ----------
    def who(self, m):
        return self.p if m["sender"] == "her" else "你"

    def line(self, m, quote=True):
        text = label(m)
        body = f"“{text}”" if (quote and m["type"] in ("text", "link")) else text
        return f"{when(m)} {self.who(m)}：{body}"

    def at(self, raw_i):
        return self.by_raw.get(raw_i)

    def turn_of(self, m):
        """她这一段（连续发的、相邻间隔 < OPEN_GAP_H 小时）里 m 之前的几条。"""
        msgs, k = self.ctx.msgs, m["_i"]
        start = k
        while start > 0 and msgs[start - 1]["sender"] == "her":
            a, b = msgs[start - 1], msgs[start]
            if a["_dt"] and b["_dt"] and (b["_dt"] - a["_dt"]).total_seconds() >= st.OPEN_GAP_H * 3600:
                break
            start -= 1
        return msgs[max(start, k - 3):k + 1]

    def h(self, title):
        self.L += ["", f"## {title}", ""]

    def add(self, *lines):
        self.L.extend(lines)

    # ---------- 各节 ----------
    def header(self):
        S, b = self.S, self.S["basics"]
        sens = S.get("sensitivity", {})
        rng = f"{b['first']} → {b['last']}，{b['span_days']} 天，" if b.get("first") else "没有时间戳，"
        self.add(f"# 写作素材包 · 你和{self.her}（{rng}{b['total']} 条）", "",
                 "写 narrative.json 只用这里的数字和原话。这里用“”引的都是记录里的原话，**从这里一字不差地复制**（标点和空格可以不同，字不能改；「」里的是说明，不是原话），"
                 "`lint_narrative.py` 会拿记录核对；这里没有的事不写，没有的数字不算。",
                 f"称呼：{self.her} / {self.p} · 节日按{self.p}选（{'母亲节' if self.p == '她' else '父亲节'}）"
                 + (f" · 时段按 UTC{b['tz']}" if b.get("tz") else " · 时段按导出电脑的时区")
                 + (f" · 来源：{S['source_detail']}" if S.get("source_detail") else ""),
                 f"建议口吻：**{sens.get('suggest') or 'normal'}**" + ("——" + "；".join(sens["reasons"]) if sens.get("reasons") else "")
                 + "。用户在对话里的语气优先（第 10 节）。")

    def numbers(self):
        S, p = self.S, self.p
        ix, o, r, sh, u, h = S["index"], S["opens"], S["reply"]["me"], S["short"], S["unanswered"], S["hours"]
        self.h("1. 数字（都在 stats.json 里，直接引用，不要心算）")
        cp = ix["care"]["parts"]
        self.add(f"- 💛 牵挂 {ix['care']['score']}：{p}开启对话 {round(100 * (cp.get('her_open_ratio') or 0))}% · 关心类主题 "
                 f"{round(100 * (cp.get('care_ratio') or 0))}% · 8 点前或 22 点后 {round(100 * (cp.get('offhour_ratio') or 0))}%"
                 f"（早上 8 点前 {h['her_early_count']} 条、晚上 10 点后 {h['her_late_count']} 条）")
        self.add(f"- 🧊 嗯哦好 {ix['short']['score']}：短回复 {sh['count']} 条 / {sh['replies']} 条回复（{round(100 * (sh['ratio'] or 0))}%）"
                 f" · 没回 {u['count']} / {u['turns']} 段 · 你回{p}中位 {r['median']}（{r['n']} 对）")
        fg = ix["forgive"]
        self.add(f"- 🕰️ 不计较 {fg['score'] if fg['score'] is not None else '—'}：你没回的 {u['count']} 次里，{p}自己先开口 {u['reopened_by_her']} 次"
                 f" · {p}追问「怎么不回」这类 {S['phrases']['chase']} 次")
        if "was_her_reply" in u:
            self.add(f"- 「没回」的口径提醒：{u['count']} 段里有 {u['was_her_reply']} 段本来是{p}在回你的话、说完对话就停了，"
                     f"{u['ended_with_closer']} 段最后一句本来就是收尾（表情、「你忙吧」、两三个字）。写「{p}发了你没回」时说「{u['count']} 段」可以，"
                     f"别说成「{u['count']} 个问题你都没回」")
        self.add(f"- 谁先开口：{p} {o['her']} / 你 {o['me']}"
                 + (f" · 你上一次主动开口 {o['days_since_my_last_open']} 天前" if o.get("days_since_my_last_open") is not None else "")
                 + (f" · {p}上一次主动 {o['days_since_her_last_open']} 天前" if o.get("days_since_her_last_open") is not None else ""))
        if r.get("max_msg"):
            self.add(f"- 你回{p}最长的一次隔了 {r['max']}，{p}那条是 {r['max_msg']['date']}“{r['max_msg']['content']}”")
        if S.get("longest"):
            lg = S["longest"]
            self.add(f"- {p}最长的一条 {lg['chars']} 字（{lg['date']}）“{lg['content']}” → 你回 "
                     + (f"{lg['reply_chars']} 字“{lg['reply']}”" if lg.get("reply") else "没有回"))
        tops = "、".join(f"{t['topic']} {t['count']}" for t in S["topics"][:5])
        meal = S.get("meal") or {}
        self.add(f"- {p}最常问：{tops}" + (f"（问吃饭 {meal['asks']} 次，饭点 {meal['at_meal']} 次、不在饭点 {meal['off_meal']} 次）" if meal.get("asks") else ""))
        self.add(f"- 时段：{p}最常在 {h['her_peak'] or '记录不够'} · 你最常在 {h['me_peak'] or '记录不够'}")
        ph = S["phrases"]
        self.add(f"- 收尾：{p}用「打扰你了 / 你忙吧」这类话收尾 {ph['self_shrink']} 次"
                 + (f"，其中 {ph['self_shrink_after_my_short']} 次前一条是你的短回复、{ph['self_shrink_after_her']} 次前一条是{p}自己的（你没接话）"
                    if "self_shrink_after_my_short" in ph else "")
                 + f" · 说「没事」这类 {ph['nothing']} 次")
        ex, fw = S["extras"], S["forwards"]
        self.add(f"- 其他：{p}发语音 {ex['her_voice_count']} 条（最长 {S.get('longest_voice_s', 0)} 秒）· 通话 {ex['call_count']} 次"
                 f" · {p}转发 {fw['count']} 篇（养生 {fw['health']}、新闻 {fw['news']}，你回了 {fw['my_reply_count']} 篇）"
                 f" · {p}转账 {ex['her_transfer_count']} 次（只记次数）")
        bl = S["bill"]
        self.add(f"- 账单：{p}发给你 {bl['her_sent']} 条 / 你回{p} {bl['me_sent']} 条 / {p}发了你没回 {bl['unanswered']} 次 / 通话 {bl['calls']} 次")
        mt, ct = S["mother_type"], S["child_type"]
        self.add(f"- 鉴定：{p} {mt['primary']}" + (f"（副 {mt['secondary']}）" if mt.get("secondary") else "")
                 + f" · 你 {ct['primary']}" + (f"（也符合：{'、'.join(ct['all'][1:3])}）" if len(ct.get("all", [])) > 1 else "")
                 + f" · 评级 {S['rating']['label']}（分 {S['rating']['score']}）")
        for s in S["signals"]:
            self.add(f"- {'🔴' if s['level'] == 'red' else '🟡'} {s['text']}")
        if S["countdown"]:
            self.add("- 倒计时：" + " · ".join(f"{c['name']}还有 {c['days']} 天（{c['date']}）" for c in S["countdown"]))

    def self_mentions(self):
        p, sf = self.p, self.S.get("self") or {"count": 0, "items": []}
        self.h(f"2. {p}说起自己的事（「唯一一次」从这里找，最扎的一段通常在这）")
        if not sf["items"]:
            self.add(f"记录里{p}没有说起过自己的事（身体、心情、家里）。不要替{p}编；「{p}其实想说的是」就从{p}问你的那些话里翻。")
            return
        self.add(f"{p}说起自己和家里的事 {sf['count']} 次，你没回或回了不超过 {st.SIGNAL_RULES['health_reply_chars']} 个字 {sf['short_or_none']} 次。")
        for k, it in enumerate(sf["items"], 1):
            m = self.at(it["i"])
            if not m:
                continue
            rp = it.get("reply")
            reply = (f"你 {rp['after']}后回：“{rp['content']}”（{rp['chars']} 字）" if rp and rp.get("after")
                     else (f"你回：“{rp['content']}”（{rp['chars']} 字）" if rp else "你没有回"))
            again = ""
            if it.get("words"):
                w = "、".join(f"「{x}」" for x in it["words"][:3])
                again = f" · 之后你再提{w} {it['i_mentioned_again']} 次 · {p}再说起 {it['she_mentioned_again']} 次"
            self.add(f"- [S{k}] {self.line(m)}", f"  → {reply}{again}")

    def unanswered(self):
        p, u = self.p, self.S["unanswered"]
        self.h(f"3. {p}发了，你没回（「帮你回」从最近 3 条挑；replies[].to 照这里写）")
        items = [it for it in u["items"] if "i" in it][-UNANSWERED_SHOW:]
        if not items:
            self.add("没有——你每条都回了。")
            return
        msgs = self.ctx.msgs
        for k, it in enumerate(reversed(items), 1):
            m = self.at(it["i"])
            if not m:
                continue
            turn = self.turn_of(m)
            self.add(f"- [U{k}] " + "／".join(self.line(x) if j == 0 else (f"{when(x, False)} “{label(x)}”" if x["type"] in ("text", "link") else f"{when(x, False)} {label(x)}")
                                            for j, x in enumerate(turn)))
            nxt = msgs[m["_i"] + 1] if m["_i"] + 1 < len(msgs) else None
            if nxt is None:
                self.add("  之后：没人再说话")
            elif nxt["sender"] == "her":
                self.add(f"  之后：{p}{('隔了 ' + fmt_delta((nxt['_dt'] - m['_dt']).total_seconds()) + ' ') if (nxt['_dt'] and m['_dt']) else ''}又自己开口：{self.line(nxt)}")
            else:
                gap = fmt_delta((nxt["_dt"] - m["_dt"]).total_seconds()) if (nxt["_dt"] and m["_dt"]) else "很久"
                self.add(f"  之后：你 {gap}后才说话：{self.line(nxt)}")
            target = next((x for x in reversed(turn) if x["type"] in ("text", "link")), m)
            self.add(f"  replies[].to 写：`{when(target)[:5]} “{label(target)[:30]}”`")

    def topics(self):
        p = self.p
        self.h(f"4. {p}最常问的（类型那句、翻译表的原话从这里挑）")
        groups = defaultdict(list)
        for m in self.ctx.her_text:
            for t in m["_topics"]:
                groups[t].append(m)
        meal = self.S.get("meal") or {}
        for t in self.S["topics"][:TOPICS_SHOW]:
            ms = groups.get(t["topic"], [])
            cnt = Counter(m["content"].strip() for m in ms)
            first_at = {}
            for m in ms:
                first_at.setdefault(m["content"].strip(), m)
            quotes = "、".join(f"“{c}”" + (f"×{n}" if n > 1 else "") + f"（{when(first_at[c])}）" for c, n in cnt.most_common(4))
            extra = ""
            if t["topic"] == "吃饭" and meal.get("asks"):
                offs = "、".join(f"{e['date']}“{e['content']}”" for e in meal.get("off_meal_examples", []))
                extra = f" · 饭点 {meal['at_meal']} 次、不在饭点 {meal['off_meal']} 次" + (f"，不在饭点的比如 {offs}" if offs else "")
            self.add(f"- {t['topic']} {t['count']} 次：{quotes}{extra}")

    def repeats(self):
        p = self.p
        self.h(f"5. {p}说过不止一次的话（黑话翻译表的候选；看时间再翻——「早点睡」是 23 点说的才能翻成「我也没睡」）")
        cnt = Counter(m["content"].strip() for m in self.ctx.her_text if m["content"].strip())
        times = defaultdict(list)
        for m in self.ctx.her_text:
            times[m["content"].strip()].append(m)
        rows = [(c, n) for c, n in cnt.most_common() if n >= 2][:REPEATS_SHOW]
        if not rows:
            self.add(f"没有重复出现的句子。翻译表从第 4 节{p}问过的话里挑，记录不够就少列。")
        for c, n in rows:
            ts = "、".join(when(m) for m in times[c][-3:])
            self.add(f"- “{c}” ×{n}（{ts}）")
        cps = [c for c, _ in self.S["catchphrases"]["her"]]
        if cps:
            self.add(f"- 口头禅片段：" + "、".join(f"“{c}”" for c in cps) + "（片段，引用时要引包含它的整句）")

    def mine(self):
        S = self.S
        self.h("6. 你的回复（你的类型那句、「帮你回」的口气照这里）")
        if S["short"]["top"]:
            self.add("- 你最常回：" + "、".join(f"“{c}”×{n}" for c, n in S["short"]["top"]))
        vm = (S.get("voice") or {}).get("me") or {}
        if vm.get("text_n"):
            self.add(f"- 你每条平均 {vm['avg_chars']} 字（中位 {vm['median_chars']}），带标点的 {round(100 * vm['punct_ratio'])}%，"
                     f"用空格断句的 {round(100 * vm['space_ratio'])}%")
            if vm.get("longest"):
                lg = vm["longest"]
                self.add(f"- 你说过最长的一条：{lg['date']}“{lg['content']}”（{lg['chars']} 字）")
        mine = [m for m in self.ctx.me_text if m["content"].strip()]
        long_ones = sorted({m["content"].strip() for m in mine if m["_chars"] >= 6}, key=lambda c: -len(c))[:5]
        if long_ones:
            self.add("- 你平时说过的整句（口气参考，引用要一字不差）：" + "、".join(f"“{c}”" for c in long_ones))

    def festivals(self):
        p = self.p
        fests = self.S["festivals"][-FESTIVALS_SHOW:]
        if not fests:
            return
        self.h("7. 节日那天")
        for f in fests:
            if not f.get("first"):
                self.add(f"- {f['name']} {f['date'][5:]}：那天你们没说话")
                continue
            m = self.at(f["i"]) if "i" in f else None
            first = self.line(m) if m else f"{'她' if f['first'] == 'her' else '你'} {f['time']}“{f['content']}”"
            other = None
            if m:
                other = next((x for x in self.ctx.msgs[m["_i"] + 1:] if x["_dt"] and x["_dt"].date() == m["_dt"].date()
                              and x["sender"] != m["sender"]), None)
            self.add(f"- {f['name']} {f['date'][5:]}：{first}" + (f"；{self.line(other)}" if other else "；对方那天没回")
                     + f" · {p} {f['count_her']} 条 / 你 {f['count_me']} 条")

    def forwards(self):
        p, fw = self.p, self.S["forwards"]
        links = [m for m in self.ctx.her if m["type"] == "link"]
        if not links:
            return
        self.h(f"8. {p}转给你的（forward_insight 用）")
        self.add(f"{fw['count']} 篇，养生 {fw['health']}、新闻 {fw['news']}，你回了 {fw['my_reply_count']} 篇。最近的：")
        msgs = self.ctx.msgs
        for m in links[-6:]:
            nxt = msgs[m["_i"] + 1] if m["_i"] + 1 < len(msgs) else None
            rep = f" → 你：“{label(nxt)}”" if (nxt and nxt["sender"] == "me") else " → 你没接"
            self.add(f"- {when(m)}《{m['content'][:40]}》{rep}")

    def voice(self):
        p, S = self.p, self.S
        vh = (S.get("voice") or {}).get("her") or {}
        self.h(f"9. {p}的说话方式（练习模式照这个扮，「帮你回」照这个预判{p}会怎么接）")
        if not vh.get("text_n"):
            self.add(f"{p}没有文字消息，扮不像。练习模式先别做。")
            return
        self.add(f"- 每条平均 {vh['avg_chars']} 字（中位 {vh['median_chars']}）· 带标点的 {round(100 * vh['punct_ratio'])}% · "
                 f"用空格断句的 {round(100 * vh['space_ratio'])}% · 一次连发 {vh.get('burst') or '—'} 条 · 文字里夹表情的 {round(100 * vh['emoji_ratio'])}%")
        emo = S["emoji"]["her"]
        if emo:
            self.add("- 最常发的表情：" + "、".join(f"[{e}]×{n}" for e, n in emo[:4]))
        for key, name in (("openers", "开口"), ("closers", "最后一句（之后很久没人说话）"), ("after_my_short", "你回了短回复之后，" + p + "通常接")):
            if vh.get(key):
                self.add(f"- {name}：" + "、".join(f"“{c}”×{n}" for c, n in vh[key]))
        ex = S["extras"]
        if ex["her_voice_count"]:
            self.add(f"- 语音 {ex['her_voice_count']} 条" + (f"，一共 {ex['her_voice_total_s']} 秒" if ex["her_voice_total_s"] else "（导出里没有秒数）"))
        sample = [m for m in self.ctx.her_text if m["content"].strip()][-SAMPLE_SHOW:]
        if sample:
            self.add(f"- {p}最近的 {len(sample)} 条文字，原样：" + " ｜ ".join(m["content"].strip() for m in sample))

    def care(self):
        S, p = self.S, self.p
        sens = S.get("sensitivity") or {}
        self.h("10. 要不要收着（writing-rules「什么时候要收着」；narrative.json 的 mode 字段）")
        self.add(f"- 建议：{sens.get('suggest') or 'normal'}" + ("。" + "；".join(sens["reasons"]) if sens.get("reasons") else "。记录里没看到要收着的迹象。"))
        for e in sens.get("conflict_examples") or []:
            self.add(f"  - {e['date']} {'她' if e['sender'] == 'her' else '你'}：“{e['content']}”")
        self.add("- 记录看不出来、只有用户自己知道的：用户说了内疚难受、和家里闹僵 → gentle；"
                 f"{p}已经不在了 → memorial（先回应人，再问要不要继续）；替别人分析 → third。")
        for k, v in MODES.items():
            hide = "、".join(v["hide"]) or "不去掉"
            self.add(f"  - `{k}` {v['cn']}：{v['when']}。去掉：{hide}")
        if S["warnings"]:
            self.add("- 数据说明里要照抄的（footnote 不写的话 render 会自动带上）：")
            for w in S["warnings"]:
                self.add(f"  - {w}")

    def spec(self):
        mode = (self.S.get("sensitivity") or {}).get("suggest") or "normal"
        req = required_fields(mode)
        self.h("11. narrative.json 怎么写")
        self.add(f"- 必填（{mode} 口吻）：" + "、".join(f"`{f}`" for f in req)
                 + ("；其余口吻见第 10 节，去掉的版块对应字段不用写" if set(req) != set(NARRATIVE_REQUIRED) else ""),
                 "- 字数：she_means 120–220 字 2–3 段（段之间用 \\n）· send_text 60–100 字、带具体时间、不道歉 · "
                 "dictionary 6–10 条、means ≤ 18 字 · replies 3 条、draft ≤ 40 字 · tonight 3 件 · call_openers 3 句",
                 "- 不用感叹号；不出现「敷衍 / 不孝 / 你应该 / 作为子女」；黑名单在 writing-rules.md；不写金额；"
                 f"称呼一律「{self.p}」，不要串成「{'他' if self.p == '她' else '她'}」",
                 "- 写完跑：`python scripts/lint_narrative.py narrative.json --stats stats.json --messages messages.json`，有 ✗ 改到没有")
        skel = ['{', f'  "schema": {SCHEMA_VERSION},', f'  "mode": "{mode}",', '  "title": "你和' + self.her + '的……",',
                '  "index_lines": {"care": "…", "short": "…", "forgive": "…"},',
                '  "type_lines": {"mother": "“原话”“原话”——数字", "child": "“你的回复”×次数……"},',
                '  "dictionary": [{"her": "第 5 节里的原话", "means": "≤ 18 字，她的第一人称"}],',
                '  "forward_insight": "…",', '  "she_means": "第一段\\n第二段",',
                '  "tonight": ["30 秒能做完的一件", "问她提过的一件事", "打电话 + 倒计时"],',
                '  "replies": [{"to": "第 3 节的 replies[].to", "draft": "≤ 40 字"}],',
                '  "call_openers": ["“…”——为什么", "…", "…"],',
                '  "send_text": "妈，我用了个软件……今晚 8 点打给你。",', '  "child_call": "的儿子 / 的女儿"', '}']
        self.add("", "```json", *skel, "```")

    def build(self):
        self.header()
        self.numbers()
        self.self_mentions()
        self.unanswered()
        self.topics()
        self.repeats()
        self.mine()
        self.festivals()
        self.forwards()
        self.voice()
        self.care()
        self.spec()
        return "\n".join(self.L).strip() + "\n"


def make_brief(S, data, lexicon=None):
    """stats dict + messages.json dict → brief.md 文本。"""
    if S.get("schema") != SCHEMA_VERSION or "self" not in S:
        raise ValueError("stats.json 是旧版 stats.py 算的（没有 self / voice 这些写作素材），先重跑：python scripts/stats.py messages.json --out stats.json")
    return Brief(S, data, lexicon or load_lexicon()).build()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stats", help="stats.py 的输出")
    ap.add_argument("messages", help="messages.json")
    ap.add_argument("--out", default="brief.md")
    ap.add_argument("--lexicon", default=None, help="stats.py 用了 --lexicon 的话，这里给同一份")
    a = ap.parse_args()
    try:
        text = make_brief(load_json(a.stats), load_json(a.messages), load_lexicon(a.lexicon))
    except (ValueError, FileNotFoundError) as e:
        print(f"✗ {e}")
        sys.exit(1)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"→ {a.out}（{len(text)} 字）。写 narrative.json 之前通读一遍，引用原话从这里复制。")


if __name__ == "__main__":
    main()
