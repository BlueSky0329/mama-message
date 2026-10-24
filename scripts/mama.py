#!/usr/bin/env python3
"""
妈妈的消息 · 一条命令跑完。Agent 和人都从这里进；底下还是 parse_export / validate / stats / brief /
lint_narrative / render / compare 那几个脚本，单独跑也行。

  python scripts/mama.py run 导出文件 --call 妈妈 [--her 记录里的名字] [--pronoun 他] [--last-days 180]
                         [--her-birthday MM-DD] [--my-birthday MM-DD] [--today YYYY-MM-DD]
                         [--tz +08:00] [--shot-date YYYY-MM-DD] [--dir mama-out]
      解析 → 校验 → 算数 → 写作素材包。产出 mama-out/ 下的 messages.json、stats.json、brief.md。
      （然后 AI 读 brief.md，按 references/writing-rules.md 写 mama-out/narrative.json）
  python scripts/mama.py run --wechat 妈 --call 妈妈 [--last-days 365] [其余同上]
      不导出：直接读本机微信（Alpha 的只读接口，见 wechat_live.py），其余步骤一样。
  python scripts/mama.py finish [--dir mama-out] [--png] [--force]
      检查 narrative.json（lint）→ 出报告和卡片到 mama-out/reports/。lint 有 ✗ 就不出（--force 硬出）。
  python scripts/mama.py explain 短回复|没回|开口|自己|收尾|没事|追问|信号|节日|主题 吃饭 [--dir mama-out] [--all]
      列出某个数字背后的那些消息。用户问"这个怎么算的""为什么这条算没回"，照这个答。
  python scripts/mama.py compare mama-out/妈 mama-out/朋友 --labels 你妈 朋友 [--mode friend|papa] [--png]
      对照组 / 偏心报告 + 对照卡。两份记录各自先 run 到不同的 --dir。
  python scripts/mama.py practice 练习记录.txt [--dir mama-out]
      练习模式打分：你在练习里回的话（一行一条，或者"我："开头）→ 短回复、问句、带具体信息的、和记录里一模一样的那句。
  python scripts/mama.py status [--dir mama-out]
      做到哪一步了，下一步干什么。

产物都在 --dir（默认 ./mama-out）里，删掉这个文件夹就什么都不剩。只用标准库；唯一的连接是 --wechat 连本机 127.0.0.1。
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from typing import NoReturn

from _common import (MODES, NARRATIVE_REQUIRED, SCHEMA_VERSION, dump_json, fmt_delta, load_json, load_lexicon, mode_of,
                     setup_utf8)

setup_utf8()

DEFAULT_DIR = "mama-out"


def die(msg) -> NoReturn:
    print(msg)
    sys.exit(1)


def paths(d):
    return {k: os.path.join(d, v) for k, v in (("messages", "messages.json"), ("stats", "stats.json"), ("brief", "brief.md"),
                                                ("narrative", "narrative.json"), ("run", "run.json"), ("reports", "reports"))}


# ---------- run ----------

def cmd_run(a):
    import brief
    import parse_export
    import stats
    import validate
    P = paths(a.dir)
    live = bool(a.wechat or a.wechat_id)
    if live == bool(a.path):
        die("给一个导出文件，或者用 --wechat 妈 直接读本机微信（二选一）")
    os.makedirs(a.dir, exist_ok=True)
    # 记录从哪来：文件用绝对路径，本机微信记成 wechat:会话
    source = f"wechat:{a.wechat_id or a.wechat}" if live else os.path.abspath(a.path)
    # 上一次跑的是另一份记录：它的 narrative.json 不能拿来配这次的数字，改名留着
    prev = load_json(P["run"]).get("input") if os.path.exists(P["run"]) else None
    same = prev and source in (prev, os.path.abspath(P["messages"]))
    if os.path.exists(P["narrative"]) and prev and not same:
        os.replace(P["narrative"], P["narrative"][:-5] + ".old.json")
        print(f"（{a.dir} 里上一次的 narrative.json 是给 {prev if prev.startswith('wechat:') else os.path.basename(prev)} 写的，已改名成 narrative.old.json）")
    try:
        today = date.fromisoformat(a.today) if a.today else date.today()
    except ValueError:
        die(f"--today 要写成 2026-08-30 这样的日期，现在是 {a.today!r}")
    for f in ("since", "until"):
        v = getattr(a, f)
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                die(f"--{f} 要写成 2026-01-01 这样的日期，现在是 {v!r}")
    print("① 读本机微信" if live else "① 解析")
    try:
        if live:
            import wechat_live
            data, report = wechat_live.fetch(a.wechat, a.wechat_id, call=a.call, me=a.me, pronoun=a.pronoun, since=a.since,
                                             until=a.until, last_days=a.last_days, tz=a.tz,
                                             progress=lambda k: print(f"\r  已读 {k} 条", end="", flush=True))
            print()
        else:
            data, report = parse_export.convert(a.path, her=a.her, me=a.me, call=a.call, pronoun=a.pronoun, since=a.since,
                                                until=a.until, last_days=a.last_days, tz=a.tz, shot_date=a.shot_date)
    except parse_export.ParseError as e:
        die(str(e))
    for line in report:
        print("  " + line.strip())
    dump_json(data, P["messages"])

    print("\n② 校验")
    errors, warnings, s = validate.check(data)
    if s:
        print(f"  {s['total']} 条：{s['her_name']} {s['her']} 条 / {s['me_name']} {s['me']} 条 · 有时间戳 {s['with_ts']} 条"
              + (f" · {s['first']} → {s['last']}" if s.get("first") else ""))
    for w in warnings:
        print(f"  ⚠ {w}")
    for e in errors:
        print(f"  ✗ {e}")
    if errors:
        die(f"\n{len(errors)} 个错误，stats.py 会算错。改好 {P['messages']} 再跑：python scripts/mama.py run {P['messages']}")

    print("\n③ 算数")
    try:
        lex = load_lexicon(a.lexicon)
        S = stats.compute(data, today=today, her_birthday=a.her_birthday, my_birthday=a.my_birthday, lexicon=lex)
    except (ValueError, FileNotFoundError) as e:
        die(f"✗ {e}")
    S["today"] = today.isoformat()
    dump_json(S, P["stats"])
    print(stats.summary_md(S))

    print("\n④ 写作素材包")
    text = brief.make_brief(S, data, lex)
    with open(P["brief"], "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    dump_json({"schema": SCHEMA_VERSION, "input": prev if same else source, "at": datetime.now().isoformat(timespec="seconds"),
               "today": today.isoformat(), "her_birthday": a.her_birthday, "my_birthday": a.my_birthday,
               "lexicon": os.path.abspath(a.lexicon) if a.lexicon else None}, P["run"])
    sug = S["sensitivity"].get("suggest")
    print(f"  → {P['brief']}（{len(text)} 字）")
    print(f"\n产物在 {os.path.abspath(a.dir)}，删掉这个文件夹就什么都不剩。")
    print("下一步：先把三个指数和鉴定给用户看，问那三个问题；再读 brief.md，按 references/writing-rules.md 写 "
          f"{P['narrative']}" + (f"（建议口吻 {sug}，看 brief.md 第 10 节）" if sug else "") + f"；然后 python scripts/mama.py finish --dir {a.dir}")


# ---------- finish ----------

def cmd_finish(a):
    import lint_narrative
    import render
    P = paths(a.dir)
    if not os.path.exists(P["stats"]):
        die(f"{P['stats']} 不存在，先跑 python scripts/mama.py run 导出文件 --dir {a.dir}")
    S = load_json(P["stats"])
    M = load_json(P["messages"]) if os.path.exists(P["messages"]) else None
    if not os.path.exists(P["narrative"]):
        if not a.force:
            die(f"{P['narrative']} 还没写。读 {P['brief']} 写好再 finish；只想先看数字版加 --force。")
        N = {}
    else:
        try:
            N = load_json(P["narrative"])
        except json.JSONDecodeError as e:
            die(f"✗ {P['narrative']} 不是合法的 JSON：{e}")
        errors, warnings = lint_narrative.lint(N, S, M)
        for w in warnings:
            print(f"⚠ {w}")
        for e in errors:
            print(f"✗ {e}")
        if errors and not a.force:
            die(f"\n{len(errors)} 个问题，改好 narrative.json 再 finish（--force 可以硬出，不建议）")
        if not errors:
            print("✓ 文字部分过了规矩" + (f"（{len(warnings)} 个提醒）" if warnings else ""))
    try:
        res = render.render_all(S, N, P["reports"], png=a.png)
    except ValueError as e:
        die(f"✗ {e}")
    for v in list(res["files"].values()) + list(res["png"].values()):
        print(f"→ {v}")
    mode = mode_of(N)
    if res["skipped"]:
        print(f"{MODES[mode]['cn']}口吻，没出：" + "、".join(res["skipped"]))
    if res["png_error"]:
        print(f"⚠ 没出 PNG：{res['png_error']}（HTML 已经好了，浏览器打开截图也一样）")
    if res["missing"]:
        print("还缺：" + "、".join(res["missing"]) + "（报告里显示为〔待写〕）")
    if "card-send" in res["files"]:
        print(f"\n发给{S['pronoun']}的卡（mama-message-card-send）是这份报告真正的出口——只推荐一个就推荐它。")


# ---------- explain ----------

EXPLAIN = {
    "短回复": "short", "short": "short", "没回": "unanswered", "unanswered": "unanswered", "开口": "opens", "opens": "opens",
    "自己": "self", "self": "self", "收尾": "shrink", "shrink": "shrink", "没事": "nothing", "nothing": "nothing",
    "追问": "chase", "chase": "chase", "信号": "signals", "signals": "signals", "节日": "festivals", "festivals": "festivals",
    "主题": "topic", "topic": "topic", "回复": "reply", "reply": "reply",
}


def _load_ctx(d):
    import stats
    P = paths(d)
    for k in ("messages", "stats"):
        if not os.path.exists(P[k]):
            die(f"{P[k]} 不存在，先跑 python scripts/mama.py run 导出文件 --dir {d}")
    data = load_json(P["messages"])
    S0 = load_json(P["stats"])
    run = load_json(P["run"]) if os.path.exists(P["run"]) else {}
    today = date.fromisoformat(S0.get("today") or run.get("today") or date.today().isoformat())
    lex = load_lexicon(run.get("lexicon"))
    S, ctx = stats.compute_with_ctx(data, today=today, her_birthday=run.get("her_birthday"), my_birthday=run.get("my_birthday"),
                                    lexicon=lex)
    return S, ctx


def cmd_explain(a):
    import stats
    what = EXPLAIN.get(a.what)
    if not what:
        die("能解释的：" + " / ".join(k for k in EXPLAIN if not k.isascii()) + "（主题后面跟主题名，比如：主题 吃饭）")
    S, ctx = _load_ctx(a.dir)
    p, msgs, D = S["pronoun"], ctx.msgs, ctx.d
    lim = None if a.all else 30

    def who(m):
        return p if m["sender"] == "her" else "你"

    def show(m):
        t = m["_dt"].strftime("%m-%d %H:%M") if m["_dt"] else "（无时间）"
        return f"{t} {who(m)}：" + (f"“{m['content']}”" if m["type"] in ("text", "link") else stats.type_label(m))

    def listing(items, fmt):
        items = list(items)
        shown = items if lim is None else items[-lim:]
        if lim is not None and len(items) > lim:
            print(f"（一共 {len(items)} 条，下面是最近的 {lim} 条；看全部加 --all）")
        for x in shown:
            print(fmt(x))

    if what == "short":
        print(f"短回复 {S['short']['count']} 条 / {S['short']['replies']} 条回复：你紧跟在{p}后面、24 小时内回的文字里，"
              f"≤ {stats.SHORT_MAX_CHARS} 个字的（不算表情，含“谢 / 爱 / 想”或以“妈 / 爸”结尾的不算）。\n")

        def fmt(m):
            prev = next((x for x in reversed(msgs[:m["_i"]]) if x["sender"] == "her"), None)
            return (f"  {show(prev)}\n    → " if prev else "  ") + show(m)
        listing(D["shorts"], fmt)
    elif what == "unanswered":
        print(f"没回 {S['unanswered']['count']} / {S['unanswered']['turns']} 段。一段 = {p}连着发的（相邻隔不到 {stats.OPEN_GAP_H} 小时）；"
              f"之后没人说话且过了一天、或者下一条还是{p}、或者你 {stats.REPLY_WINDOW_H} 小时以后才回，算没接上；"
              f"没接上的段里，{p}本来是在回你、又没问你什么的（{S['unanswered'].get('natural_end', 0)} 段），是对话自然说完了，不算没回。\n")

        def fmt(m):
            nxt = msgs[m["_i"] + 1] if m["_i"] + 1 < len(msgs) else None
            why = ("之后没人再说话" if nxt is None else
                   (f"下一条还是{p}：{show(nxt)}" if nxt["sender"] == "her" else
                    f"你隔了 {fmt_delta((nxt['_dt'] - m['_dt']).total_seconds()) if (nxt['_dt'] and m['_dt']) else '很久'}才回：{show(nxt)}"))
            return f"  {show(m)}\n    {why}"
        listing(D["unanswered"], fmt)
    elif what == "opens":
        print(f"谁先开口：{p} {S['opens']['her']} 次 / 你 {S['opens']['me']} 次。和上一条隔了 ≥ {stats.OPEN_GAP_H} 小时的消息算开启一次新对话。\n")
        print(f"你开的头：")
        listing(D["my_opens"], lambda m: "  " + show(m))
        print(f"\n{p}开的头：")
        listing(D["her_opens"], lambda m: "  " + show(m))
    elif what == "reply":
        r = S["reply"]["me"]
        print(f"你回{p}，中位 {r['median']}（{r['n']} 对）：{p}发一条、你紧接着回的那一条，两条都有时间戳才算。下面是隔得最久的：\n")
        pairs = [(m, msgs[m["_i"] + 1]) for m in ctx.dated if m["sender"] == "her" and m["_i"] + 1 < len(msgs)
                 and msgs[m["_i"] + 1]["sender"] == "me" and msgs[m["_i"] + 1]["_dt"]]
        pairs.sort(key=lambda x: (x[1]["_dt"] - x[0]["_dt"]).total_seconds())
        listing(pairs, lambda x: f"  {show(x[0])}\n    → 隔 {fmt_delta((x[1]['_dt'] - x[0]['_dt']).total_seconds())}：{show(x[1])}")
    elif what == "self":
        sf = S["self"]
        print(f"{p}说起自己的事 {sf['count']} 次：不是在问你、也不是在叮嘱你，说的是{p}自己的身体、心情、家里（词表 self_words）。\n")

        def fmt(m):
            r = stats.first_reply(ctx, m)
            return f"  {show(m)}\n    → " + (show(r) if r else "你没有回")
        listing(D["self"], fmt)
    elif what in ("shrink", "nothing", "chase"):
        names = {"shrink": "用“打扰你了 / 你忙吧”这类话收尾", "nothing": "说“没事”", "chase": "追问“怎么不回”"}
        key = {"shrink": "self_shrink", "nothing": "nothing", "chase": "chase"}[what]
        print(f"{p}{names[what]} {S['phrases'][key]} 次（词表 {key}）：\n")

        def fmt(m):
            prev = msgs[m["_i"] - 1] if m["_i"] else None
            return (f"  前一条 {show(prev)}\n    → " if prev else "  ") + show(m)
        listing(D[what], fmt)
    elif what == "signals":
        R = stats.SIGNAL_RULES
        print("该打电话了。阈值在 stats.py 的 SIGNAL_RULES，定义在 references/metrics.md「该打电话了」：")
        print(f"  🔴 {p}提到自己的身体（不是在问你），你没回或回了 ≤ {R['health_reply_chars']} 个字")
        print(f"  🔴 {p} ≥ {R['self_shrink_min']} 次用收尾语结束对话 · 🔴 最近一个月表情包占比涨到之前的 {R['sticker_mult']} 倍以上且 ≥ {round(100 * R['sticker_min'])}%")
        print(f"  🟡 {p}主动开口少了 {abs(R['opens_drop_pct'])}% 以上 · 🟡 通话时长少一半以上 · 🟡 “没事” ≥ {R['nothing_min']} 次 · 🟡 你上次主动开口 ≥ {R['my_open_gap_days']} 天前\n")
        for s in S["signals"]:
            print(f"  {'🔴' if s['level'] == 'red' else '🟡'} {s['text']}")
        if not S["signals"]:
            print("  这份记录一个都没触发。")
    elif what == "festivals":
        print("节日那天谁先发的（记录范围内的元旦、春节、除夕、母亲节/父亲节、中秋、国庆、重阳、生日）：\n")
        for f in S["festivals"]:
            print(f"  {f['name']} {f['date']}：" + ("那天没说话" if not f["first"] else
                  f"{p if f['first'] == 'her' else '你'} {f['time']} 先发“{f['content']}”，{p} {f['count_her']} 条 / 你 {f['count_me']} 条"))
    elif what == "topic":
        if not a.arg:
            die("主题后面跟名字：" + " / ".join(t["topic"] for t in S["topics"]))
        ms = [m for m in ctx.her_text if a.arg in m["_topics"]]
        kws = ctx.lex["topics"].get(a.arg)
        if kws is None:
            die(f"没有“{a.arg}”这个主题。有：" + " / ".join(ctx.lex["topics"]))
        print(f"{p}说“{a.arg}”{len(ms)} 次。关键词（references/lexicon.json）：{' / '.join(kws)}\n")
        listing(ms, lambda m: "  " + show(m))


# ---------- compare ----------

def cmd_compare(a):
    import compare
    try:
        A, B = compare.load_side(a.a), compare.load_side(a.b)
    except (ValueError, OSError) as e:
        die(f"✗ {e}")
    la, lb = a.labels
    out = compare.compare(A, B, (la, lb), a.mode)
    d = a.out or os.path.join(DEFAULT_DIR, "compare")
    os.makedirs(d, exist_ok=True)
    w = max(len(r["name"]) for r in out["rows"]) + 2
    print(f"{'':{w}}{la:>12}{lb:>12}")
    for r in out["rows"]:
        print(f"{r['name']:{w}}{str(r['a']):>12}{str(r['b']):>12}")
    print("\n" + out["verdict"])
    dump_json(out, os.path.join(d, "compare.json"))
    card = compare.write_card(out, A, B, os.path.join(d, "mama-message-card-compare.html"))
    print(f"→ {os.path.join(d, 'compare.json')}\n→ {card}")
    if a.png:
        import snap
        try:
            print(f"→ {snap.html_to_png(card, card[:-5] + '.png')}")
        except snap.SnapError as e:
            print(f"⚠ 没出 PNG：{e}")


# ---------- practice ----------

SPECIFIC_RE = re.compile(r"\d|今晚|今天|明天|后天|周[一二三四五六日天末]|星期|点|号|月|上午|下午|晚上|早上|中午")


def practice_replies(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    labeled = [re.match(r"^(我|自己)\s*[：:]\s*(.+)$", l) for l in lines]
    if any(labeled):
        return [m.group(2).strip() for m in labeled if m]
    return [l for l in lines if not re.match(r"^\S{1,6}\s*[：:]", l)]


def score_practice(replies, S=None, data=None, lex=None):
    """练习里的回复 → 分数字典。S / data 给了就和记录比。"""
    import stats
    lex = lex or load_lexicon()
    norm = lambda s: re.sub(r"[\s，。！？、,.!?~～…]+", "", s or "")
    shorts = [r for r in replies if stats.is_short({"content": r}, lex)]
    asks = [r for r in replies if stats.is_question(r, lex)]
    specific = [r for r in replies if SPECIFIC_RE.search(r) or len(norm(r)) >= 10]
    out = {"n": len(replies), "short": len(shorts), "short_ratio": round(len(shorts) / len(replies), 3) if replies else None,
           "asked": len(asks), "specific": len(specific), "avg_chars": round(sum(len(norm(r)) for r in replies) / len(replies), 1) if replies else 0,
           "same_as_record": []}
    if S:
        out["record_short_ratio"] = S["short"]["ratio"]
    if data:
        seen = {}
        for m in data.get("messages") or []:
            if m.get("sender") == "me" and (m.get("type") or "text") == "text" and norm(m.get("content")):
                seen.setdefault(norm(m["content"]), m.get("ts"))
        for r in replies:
            if norm(r) in seen and len(norm(r)) >= 2:
                out["same_as_record"].append({"reply": r, "ts": seen[norm(r)]})
    return out


def cmd_practice(a):
    P = paths(a.dir)
    with open(a.path, encoding="utf-8") as f:
        replies = practice_replies(f.read())
    if not replies:
        die("没读到你的回复：一行一条，或者“我：”开头")
    S = load_json(P["stats"]) if os.path.exists(P["stats"]) else None
    data = load_json(P["messages"]) if os.path.exists(P["messages"]) else None
    sc = score_practice(replies, S, data)
    p = S["pronoun"] if S else "她"
    print(f"你回了 {sc['n']} 条：短回复 {sc['short']} 条，问了{p} {sc['asked']} 次，带具体信息的 {sc['specific']} 条，平均 {sc['avg_chars']} 字。")
    for x in sc["same_as_record"][:3]:
        when = f"{int(x['ts'][5:7])} 月 {int(x['ts'][8:10])} 日" if x["ts"] else "记录里"
        print(f"你回的“{x['reply']}”——和{when}那次一模一样。")
    if sc.get("record_short_ratio") is not None and sc["short_ratio"] is not None:
        a_, b_ = round(100 * sc["record_short_ratio"]), round(100 * sc["short_ratio"])
        print(f"记录里短回复占 {a_}%，今天 {b_}%。" + ("比记录里的你好一点。" if b_ < a_ else ("和记录里差不多。" if b_ == a_ else "")))
    print("（“下次试试”只给一个，由陪练的 AI 根据上面这些写。）")


# ---------- status ----------

def cmd_status(a):
    import lint_narrative
    P = paths(a.dir)
    if not os.path.exists(P["messages"]):
        print(f"{a.dir} 里还没有东西。第一步：python scripts/mama.py run 导出文件 --call 妈妈 --dir {a.dir}")
        return
    M = load_json(P["messages"])
    print(f"messages.json：{len(M.get('messages') or [])} 条（{M.get('source_detail') or M.get('source') or '来源未知'}）")
    if not os.path.exists(P["stats"]):
        print(f"下一步：python scripts/mama.py run {P['messages']} --dir {a.dir}")
        return
    S = load_json(P["stats"])
    print(f"stats.json：牵挂 {S['index']['care']['score']} · 嗯哦好 {S['index']['short']['score']} · 不计较 {S['index']['forgive']['score']}"
          f" · {S['rating']['label']}（今天按 {S.get('today')}）" + ("" if S.get("schema") == SCHEMA_VERSION else " ⚠ 旧版，重跑 run"))
    print("brief.md：" + ("有" if os.path.exists(P["brief"]) else f"没有（重跑 run）"))
    if not os.path.exists(P["narrative"]):
        print(f"下一步：读 {P['brief']}，写 {P['narrative']}（必填：{'、'.join(NARRATIVE_REQUIRED)}），然后 finish")
        return
    try:
        N = load_json(P["narrative"])
    except json.JSONDecodeError as e:
        print(f"narrative.json 不是合法的 JSON：{e}")
        return
    errors, warnings = lint_narrative.lint(N, S, M)
    print(f"narrative.json：口吻 {mode_of(N)} · {len(errors)} 个问题 · {len(warnings)} 个提醒")
    reps = sorted(os.listdir(P["reports"])) if os.path.isdir(P["reports"]) else []
    print("reports/：" + ("、".join(reps) if reps else "还没出"))
    if errors:
        print(f"下一步：改 narrative.json（python scripts/lint_narrative.py {P['narrative']} --stats {P['stats']} --messages {P['messages']} 看问题）")
    elif not reps or os.path.getmtime(P["narrative"]) > max(os.path.getmtime(os.path.join(P["reports"], r)) for r in reps):
        print(f"下一步：python scripts/mama.py finish --dir {a.dir}")
    else:
        print("都好了。把 reports/ 里的卡发出去——发给她的那张是出口。")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="解析 → 校验 → 算数 → 写作素材包")
    r.add_argument("path", nargs="?", default=None, help="导出文件 / 截图转录稿 / messages.json（用 --wechat 时不填）")
    r.add_argument("--wechat", default=None, help="不导出，直接读本机微信（Alpha 服务）：她在你微信里的备注，如 妈")
    r.add_argument("--wechat-id", default=None, help="同名的私聊有好几个时，用会话 id（wxid_…）")
    for k, h in (("--her", "对方在记录里的名字"), ("--me", "你在记录里的名字"), ("--call", "报告里怎么称呼对方（妈妈 / 老爸 / 外婆）"),
                 ("--pronoun", "她 / 他"), ("--since", "YYYY-MM-DD"), ("--until", "YYYY-MM-DD"), ("--her-birthday", "MM-DD"),
                 ("--my-birthday", "MM-DD"), ("--today", "YYYY-MM-DD，默认今天"), ("--tz", "如 +08:00"),
                 ("--shot-date", "截图转录稿：截图那天"), ("--lexicon", "换一份词表")):
        r.add_argument(k, default=None, help=h)
    r.add_argument("--last-days", type=int, default=None, help="只要最后一条往前 N 天")
    r.add_argument("--dir", default=DEFAULT_DIR, help="产物放哪（默认 mama-out）")

    f = sub.add_parser("finish", help="lint narrative.json → 出报告和卡片")
    f.add_argument("--dir", default=DEFAULT_DIR)
    f.add_argument("--png", action="store_true", help="卡片再出 PNG（本机 Chrome / Edge）")
    f.add_argument("--force", action="store_true", help="lint 有问题也出")

    e = sub.add_parser("explain", help="列出某个数字背后的消息")
    e.add_argument("what", help="短回复 / 没回 / 开口 / 回复 / 自己 / 收尾 / 没事 / 追问 / 信号 / 节日 / 主题")
    e.add_argument("arg", nargs="?", default=None, help="主题名（主题 吃饭）")
    e.add_argument("--dir", default=DEFAULT_DIR)
    e.add_argument("--all", action="store_true", help="全部列出（默认最近 30 条）")

    c = sub.add_parser("compare", help="对照组 / 偏心报告")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--labels", nargs=2, default=["你妈", "朋友"])
    c.add_argument("--mode", choices=["friend", "papa"], default="friend")
    c.add_argument("--out", default=None, help="输出目录（默认 mama-out/compare）")
    c.add_argument("--png", action="store_true")

    p = sub.add_parser("practice", help="练习模式打分")
    p.add_argument("path", help="练习里你回的话（一行一条，或“我：”开头）")
    p.add_argument("--dir", default=DEFAULT_DIR)

    s = sub.add_parser("status", help="做到哪一步了")
    s.add_argument("--dir", default=DEFAULT_DIR)

    a = ap.parse_args()
    if not a.cmd:
        ap.print_help()
        return
    {"run": cmd_run, "finish": cmd_finish, "explain": cmd_explain, "compare": cmd_compare,
     "practice": cmd_practice, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
