#!/usr/bin/env python3
"""
把 stats.json（数字）和 narrative.json（AI 写的文字）合成 HTML 报告和两张卡片。

用法:
  python scripts/render.py stats.json narrative.json [--out reports/]

产出:
  reports/mama-message-report.html      完整报告
  reports/mama-message-card-bill.html   亲情账单卡（给自己发）
  reports/mama-message-card-send.html   发给她的卡

narrative.json 缺哪个字段就留一个明显的占位，不会报错。字段说明见 references/report-template.md。
"""
import argparse
import html
import json
import os
import sys

# Windows 默认控制台是 GBK，打不出 emoji；统一把输出切到 UTF-8（其他平台无影响）
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")


def esc(s):
    return html.escape(str(s if s is not None else ""))


def fill(template, values):
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", str(v))
    return template


def bar_w(score):
    return 2 if score is None else max(2, min(100, score))


def hours_svg(her, me):
    """24 列 × 2 行的热力条"""
    W, H, cell, gap, top = 720, 96, 27, 3, 22
    mh, mm = max(her) or 1, max(me) or 1
    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="PingFang SC,Noto Sans SC,sans-serif">']
    for i in range(24):
        x = i * (cell + gap)
        oh = 0.12 + 0.88 * her[i] / mh
        om = 0.12 + 0.88 * me[i] / mm
        parts.append(f'<rect x="{x}" y="{top}" width="{cell}" height="{cell}" rx="4" fill="#07C160" fill-opacity="{oh:.2f}"/>')
        parts.append(f'<rect x="{x}" y="{top + cell + gap}" width="{cell}" height="{cell}" rx="4" fill="#9A9A9A" fill-opacity="{om:.2f}"/>')
        if i % 3 == 0:
            parts.append(f'<text x="{x + cell/2}" y="14" font-size="11" fill="#7A7A7A" text-anchor="middle">{i}时</text>')
    parts.append("</svg>")
    return "".join(parts)


def weekly_svg(weekly):
    if not weekly:
        return ""
    W, H, pad = 720, 200, 24
    n = len(weekly)
    mx = max(max(w["her"], w["me"]) for w in weekly) or 1
    gw = (W - pad * 2) / n
    bw = max(2, gw * 0.38)
    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="PingFang SC,Noto Sans SC,sans-serif">']
    base = H - 28
    for i, w in enumerate(weekly):
        x = pad + i * gw
        hh = (base - 16) * w["her"] / mx
        hm = (base - 16) * w["me"] / mx
        parts.append(f'<rect x="{x:.1f}" y="{base - hh:.1f}" width="{bw:.1f}" height="{hh:.1f}" rx="2" fill="#07C160"/>')
        parts.append(f'<rect x="{x + bw + 1:.1f}" y="{base - hm:.1f}" width="{bw:.1f}" height="{hm:.1f}" rx="2" fill="#9A9A9A"/>')
        if n <= 30 or i % max(1, n // 12) == 0:
            parts.append(f'<text x="{x + bw:.1f}" y="{H - 8}" font-size="10" fill="#7A7A7A" text-anchor="middle">{w["week"][-3:]}</text>')
    parts.append(f'<line x1="{pad}" y1="{base}" x2="{W - pad}" y2="{base}" stroke="#DEDEDE"/>')
    parts.append("</svg>")
    return "".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stats")
    ap.add_argument("narrative", nargs="?", default=None)
    ap.add_argument("--out", default="reports")
    a = ap.parse_args()
    S = json.load(open(a.stats, encoding="utf-8"))
    N = json.load(open(a.narrative, encoding="utf-8")) if a.narrative and os.path.exists(a.narrative) else {}
    os.makedirs(a.out, exist_ok=True)

    p = S["pronoun"]; b = S["basics"]; ix = S["index"]
    her_name = S["her_name"]
    ph = lambda key: N.get(key) or f"〔待写：{key}〕"

    # 六个数字
    r = S["reply"]["me"]
    lg = S.get("longest") or {}
    six = [
        f"<li><span><b>谁先开口</b> —— {p} {S['opens']['her']} 次 / 你 {S['opens']['me']} 次</span></li>",
        f"<li><span><b>你回{p}，通常要</b> {esc(r['median'])}<small>最长的一次隔了 {esc(r['max'])}" + (f"，{p}那条是“{esc(r['max_msg']['content'])}”" if r.get("max_msg") else "") + "</small></span></li>",
        f"<li><span><b>{p}最长的一条</b> {lg.get('chars', '—')} 字：“{esc(lg.get('content', ''))}”<small>你回了 {lg.get('reply_chars') if lg.get('reply_chars') is not None else '—'} 字：“{esc(lg.get('reply') or '没有回复')}”</small></span></li>",
        f"<li><span><b>你的“嗯 / 好 / 知道了”</b> {S['short']['count']} 条，占你全部回复的 {round(100 * (S['short']['ratio'] or 0))}%<small>" + "、".join(f"{esc(t[0])}×{t[1]}" for t in S["short"]["top"][:4]) + "</small></span></li>",
        f"<li><span><b>{p}最常问的三件事</b><small>" + " ／ ".join(f"{esc(t['topic'])} {t['count']} 次“{esc(t['example'])}”" for t in S["topics"][:3]) + "</small></span></li>",
        f"<li><span><b>{p}最常在</b> {esc(S['hours']['her_peak'] or '记录不够')} 找你<small>你最常在 {esc(S['hours']['me_peak'] or '—')} 回</small></span></li>",
    ]

    comp = S["composition"][:8]
    mxp = max((c["pct"] for c in comp), default=1) or 1
    comp_rows = "".join(f'<tr><td class="k">{esc(c["name"])}</td><td class="v">{c["pct"]}%</td><td class="b"><i style="width:{max(2, 100 * c["pct"] / mxp):.0f}%"></i></td></tr>' for c in comp)
    emo = S["emoji"]["her"]
    emoji_line = (f"{p}最常发的表情：" + "、".join(f"[{esc(e)}] {n} 次" for e, n in emo[:4])) if emo else f"{p}的消息里没有内置表情"
    if S["catchphrases"]["her"]:
        emoji_line += f" · {p}的口头禅：" + "、".join(f"“{esc(c[0])}”" for c in S["catchphrases"]["her"][:3])

    tl = N.get("type_lines", {})
    dict_rows = "".join(f'<tr><td class="k">“{esc(d["her"])}”</td><td class="arrow">→</td><td class="m">{esc(d["means"])}</td></tr>' for d in N.get("dictionary", [])) or '<tr><td class="m">〔待写：dictionary〕</td></tr>'

    fest_rows = ""
    for f in S["festivals"]:
        if not f["first"]:
            fest_rows += f'<tr><td class="k">{esc(f["name"])}</td><td class="none" colspan="2">{f["date"][5:]} · 那天你们没说话</td></tr>'
        else:
            who = f'<span class="who-her">{p}</span>' if f["first"] == "her" else '<span class="who-me">你</span>'
            fest_rows += f'<tr><td class="k">{esc(f["name"])}</td><td>{who} {f["time"]} 先发的：“{esc(f["content"])}”</td><td style="text-align:right;color:var(--mute)">{p} {f["count_her"]} 条 / 你 {f["count_me"]} 条</td></tr>'
    if not fest_rows:
        fest_rows = '<tr><td class="none">记录范围里没有赶上节日</td></tr>'

    ua = S["unanswered"]["items"][-5:]
    bubbles = "".join(f'<div class="bubble"><time>{esc(u["date"])}</time>{esc(u["content"])}</div>' for u in ua) or '<div class="bubble">没有——你每条都回了</div>'

    fw = S["forwards"]
    forward_line = N.get("forward_insight") or (f"{p}转发了 {fw['count']} 篇文章，其中 {fw['health']} 篇是养生健康类，你回复了 {fw['my_reply_count']} 篇。" if fw["count"] else f"{p}没有给你转发过文章。")
    forward_titles = " · ".join(f"《{esc(t)}》" for t in fw["titles"][-5:])

    sig_rows = "".join(f'<li class="{s["level"]}">{esc(s["text"])}</li>' for s in S["signals"]) or '<li class="empty">没有触发任何信号，挺好的</li>'

    dsm = S["opens"].get("days_since_my_last_open", "—")
    dsh = S["opens"].get("days_since_her_last_open", "—")

    tonight = N.get("tonight") or []
    tonight_rows = "".join(f"<li>{esc(t)}</li>" for t in tonight) or "<li>〔待写：tonight〕</li>"
    reply_rows = "".join(f'<div class="reply"><div class="to">回 {esc(x["to"])}</div><div class="draft">{esc(x["draft"])}</div></div>' for x in N.get("replies", [])) or '<div class="reply">〔待写：replies〕</div>'
    openers = "".join(f"<li>{esc(o)}</li>" for o in N.get("call_openers", [])) or "<li>〔待写：call_openers〕</li>"

    bill = S["bill"]
    balance = N.get("bill_balance") or f"欠 {bill['unanswered']} 条回复、1 个电话"
    countdown = "".join(f'<span>{esc(c["name"])} 还有 {c["days"]} 天</span>' for c in S["countdown"])
    cd0 = S["countdown"][0] if S["countdown"] else None

    values = {
        "TITLE": esc(N.get("title") or f"你和{her_name}的聊天报告"),
        "PRONOUN": p,
        "RANGE_LINE": (f"{b['first']} 至 {b['last']} · {b['span_days']} 天 · " if b.get("first") else "时间范围未知（没有时间戳）· ") + f"共 {b['total']} 条（{p} {b['her']} / 你 {b['me']}）",
        "COUNTDOWN": countdown,
        "CARE_SCORE": ix["care"]["score"], "CARE_W": bar_w(ix["care"]["score"]), "CARE_LINE": esc(N.get("index_lines", {}).get("care") or f"{p}发起了 {round(100 * (S['opens']['her_ratio'] or 0))}% 的对话，{p}有 {S['hours']['her_early_count']} 条是早上 8 点前发的、{S['hours'].get('her_late_count', 0)} 条是晚上 10 点后发的"),
        "SHORT_SCORE": ix["short"]["score"], "SHORT_W": bar_w(ix["short"]["score"]), "SHORT_LINE": esc(N.get("index_lines", {}).get("short") or f"你 {S['short']['count']} 条回复不超过三个字，最长一次 {r['max']} 没回"),
        "FORGIVE_SCORE": ix["forgive"]["score"] if ix["forgive"]["score"] is not None else "—", "FORGIVE_W": bar_w(ix["forgive"]["score"]),
        "FORGIVE_LINE": esc(N.get("index_lines", {}).get("forgive") or (f"你没回的 {S['unanswered']['count']} 次里，有 {S['unanswered']['reopened_by_her']} 次是{p}自己先开口了下一次" if S["unanswered"]["count"] else f"{p}没有被你晾过一整天")),
        "SIX_ROWS": "".join(six),
        "COMPOSITION_ROWS": comp_rows, "EMOJI_LINE": emoji_line,
        "MOTHER_TYPE": esc(S["mother_type"]["primary"]), "MOTHER_TYPE_SUB": esc(f"副型：{S['mother_type']['secondary']}" if S["mother_type"]["secondary"] else ""),
        "MOTHER_TYPE_LINE": esc(tl.get("mother") or "〔待写：type_lines.mother〕"),
        "CHILD_TYPE": esc(S["child_type"]["primary"]), "CHILD_TYPE_SUB": esc("也符合：" + "、".join(S["child_type"]["all"][1:3]) if len(S["child_type"]["all"]) > 1 else ""),
        "CHILD_TYPE_LINE": esc(tl.get("child") or "〔待写：type_lines.child〕"),
        "RATING": esc(S["rating"]["label"]),
        "DICT_ROWS": dict_rows, "FESTIVAL_ROWS": fest_rows, "UNANSWERED_BUBBLES": bubbles,
        "FORWARD_LINE": esc(forward_line), "FORWARD_TITLES": forward_titles,
        "SIGNAL_ROWS": sig_rows,
        "HOURS_SVG": hours_svg(S["hours"]["her"], S["hours"]["me"]), "WEEKLY_SVG": weekly_svg(S["weekly"]),
        "DAYS_SINCE_MY_OPEN": dsm, "DAYS_SINCE_HER_OPEN": dsh,
        "SHE_MEANS": "".join(f"<p>{esc(para)}</p>" for para in str(ph("she_means")).split("\n") if para.strip()),
        "TONIGHT_ROWS": tonight_rows, "REPLY_ROWS": reply_rows, "CALL_OPENERS": openers,
        "BILL_HER": bill["her_sent"], "BILL_ME": bill["me_sent"], "BILL_UNANSWERED": bill["unanswered"], "BILL_CALLS": bill["calls"],
        "BILL_BALANCE": esc(balance), "SHORT_COUNT": S["short"]["count"],
        "SEND_TEXT": esc(ph("send_text")),
        "SEND_CTA": esc(N.get("send_cta") or (f"{cd0['name']}还有 {cd0['days']} 天" if cd0 else "")),
        "CHILD_CALL": esc(N.get("child_call") or "的孩子"),
        "CTA": esc(N.get("cta") or (tonight[0] if tonight else (f"{cd0['name']}还有 {cd0['days']} 天，先打个电话" if cd0 else "今晚回一条"))),
        "FOOTNOTE": esc(N.get("footnote") or f"基于 {b['total']} 条记录，其中 {b['with_ts']} 条有时间戳；回复间隔基于 {r['n']} 对有时间戳的消息，取中位数；语音不计字数；转账只记次数。这是一份统计，不是评判。"),
    }

    outs = {}
    for name, tpl in (("report", "report.html"), ("card-bill", "card-bill.html"), ("card-send", "card-send.html")):
        t = open(os.path.join(ASSETS, tpl), encoding="utf-8").read()
        dst = os.path.join(a.out, f"mama-message-{name}.html")
        open(dst, "w", encoding="utf-8", newline="\n").write(fill(t, values))
        outs[name] = dst
    missing = [k for k in ("she_means", "send_text", "dictionary", "tonight", "replies", "call_openers", "type_lines") if not N.get(k)]
    for k, v in outs.items():
        print(f"→ {v}")
    if missing:
        print("narrative.json 还缺：" + "、".join(missing) + "（报告里显示为〔待写〕）")


if __name__ == "__main__":
    main()
