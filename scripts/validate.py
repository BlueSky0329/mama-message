#!/usr/bin/env python3
"""
检查 messages.json 能不能放心交给 stats.py。

截图转录是人（或 AI）手工做的，最容易出的错就这几种：sender 写错、时间格式不统一、
相邻截图重叠的消息记了两次、时间没排好、转账把金额写进去了。这个脚本把它们找出来，
并打印一份"条数 + 时间范围 + 类型分布"的摘要——SKILL 第三步要求转录完先给用户确认，就给这份。

用法:
  python scripts/validate.py messages.json
  python scripts/validate.py messages.json --strict     # 有警告也按失败退出（给 CI 用）

退出码：0 通过（可以有警告）；1 有错误（stats.py 会算错或崩）。只读，不改文件。只用标准库。
"""
import argparse
import json
import re
import sys
from collections import Counter

from _common import SCHEMA_VERSION, TYPES, parse_ts, setup_utf8

setup_utf8()

AMOUNT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:元|块|万|¥|￥)|[¥￥]\s*\d")


def check(data):
    """返回 (errors, warnings, summary)。errors 非空 = stats.py 会算错或崩。"""
    errors, warnings = [], []
    if not isinstance(data, dict):
        return ["顶层不是对象（应该是 {\"me\": …, \"her\": …, \"messages\": […]}）"], [], None
    schema = data.get("schema")
    if isinstance(schema, int) and schema > SCHEMA_VERSION:
        errors.append(f"这个文件是 schema {schema}，本版脚本只认到 {SCHEMA_VERSION}，更新一下仓库再跑")
    for k in ("me", "her", "messages"):
        if k not in data:
            errors.append(f"缺少顶层字段 {k}")
    if data.get("her_pronoun") not in (None, "她", "他"):
        warnings.append(f"her_pronoun 是 {data.get('her_pronoun')!r}，应该是“她”或“他”")
    if "her_pronoun" not in data:
        warnings.append("没写 her_pronoun，stats.py 会默认用“她”")
    msgs = data.get("messages")
    if not isinstance(msgs, list):
        errors.append("messages 不是数组")
        return errors, warnings, None
    if not msgs:
        errors.append("messages 是空的")
        return errors, warnings, None

    senders, types = Counter(), Counter()
    dated, undated, bad_ts = [], 0, []
    amounts, dups, missing_dur = [], [], 0
    prev_key = None
    for i, m in enumerate(msgs):
        if not isinstance(m, dict):
            errors.append(f"第 {i + 1} 条不是对象")
            continue
        s = m.get("sender")
        senders[s] += 1
        if s not in ("her", "me"):
            errors.append(f"第 {i + 1} 条 sender 是 {s!r}，只能是 her / me")
        t = m.get("type") or "text"
        types[t] += 1
        if t not in TYPES:
            warnings.append(f"第 {i + 1} 条 type 是 {t!r}，不在已知类型里，stats.py 会归到“其他”")
        c = m.get("content")
        if c is not None and not isinstance(c, str):
            errors.append(f"第 {i + 1} 条 content 不是字符串")
            c = str(c)
        c = c or ""
        if t == "text" and not c.strip():
            warnings.append(f"第 {i + 1} 条是 text 但内容为空")
        if t == "transfer" and AMOUNT_RE.search(c):
            amounts.append(i + 1)
        if t == "text" and re.search(r"(转账|转了|打了|红包)\s*\d", c) and AMOUNT_RE.search(c):
            amounts.append(i + 1)
        if t in ("voice", "call_voice", "call_video") and not m.get("dur"):
            missing_dur += 1
        ts = m.get("ts")
        if ts is None:
            undated += 1
        else:
            dt = parse_ts(ts)
            if dt is None:
                bad_ts.append((i + 1, ts))
            else:
                dated.append((i, dt))
        key = (s, t, c.strip(), ts)
        if key == prev_key and (c.strip() or ts):
            dups.append(i + 1)
        prev_key = key

    if bad_ts:
        errors.append(f"{len(bad_ts)} 条时间戳格式认不出来（要 2026-05-12T21:03:14 或 2026-05-12 21:03），例如第 {bad_ts[0][0]} 条：{bad_ts[0][1]!r}")
    backwards = [(msgs_i, dt) for (a, dt_a), (msgs_i, dt) in zip(dated, dated[1:]) if dt < dt_a]
    if backwards:
        errors.append(f"有 {len(backwards)} 处时间倒序（后一条比前一条早），第一处在第 {backwards[0][0] + 1} 条。"
                      "回复间隔和谁先开口都会算错——按时间重排，或者删掉误标的时间")
    if dups:
        warnings.append(f"有 {len(dups)} 条和上一条完全相同（sender、类型、内容、时间都一样），可能是相邻截图重叠没去掉：第 "
                        + "、".join(map(str, dups[:8])) + (" …" if len(dups) > 8 else "") + " 条")
    if amounts:
        warnings.append(f"第 {'、'.join(map(str, amounts[:5]))} 条疑似写了转账金额，规矩是只记次数不记金额，content 写“转账”就行")
    if missing_dur:
        warnings.append(f"{missing_dur} 条语音/通话没写 dur（秒数），语音轰炸型和通话时长会偏低")
    n = len(msgs)
    if n < 20:
        warnings.append(f"只有 {n} 条，stats.py 只会出基础数字，不写解读")
    if n >= 20 and undated > n / 2:
        warnings.append(f"{undated} 条没有时间戳（{round(100 * undated / n)}%），时间相关的项会不稳；截图上有时间的尽量都填")
    if senders["her"] == 0 or senders["me"] == 0:
        warnings.append("只有一方在说话，很多指标会是空的；确认一下 sender 有没有标反")
    if senders["her"] and senders["me"] and senders["me"] > senders["her"] * 2:
        warnings.append(f"你 {senders['me']} 条、对方 {senders['her']} 条——你说得比对方多一倍以上，确认一下 sender 有没有标反（微信右侧绿色是你）")

    summary = {
        "total": n, "her": senders["her"], "me": senders["me"],
        "with_ts": len(dated), "without_ts": undated,
        "first": min(dt for _, dt in dated).strftime("%Y-%m-%d %H:%M") if dated else None,
        "last": max(dt for _, dt in dated).strftime("%Y-%m-%d %H:%M") if dated else None,
        "types": types.most_common(),
        "her_name": data.get("her", "妈妈"), "me_name": data.get("me", "我"),
    }
    return errors, warnings, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="messages.json")
    ap.add_argument("--strict", action="store_true", help="有警告也失败")
    a = ap.parse_args()
    try:
        with open(a.path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"✗ 不是合法的 JSON：{e}")
        sys.exit(1)
    errors, warnings, s = check(data)
    if s:
        print(f"{s['total']} 条：{s['her_name']} {s['her']} 条 / {s['me_name']} {s['me']} 条 · 有时间戳 {s['with_ts']} 条，没有 {s['without_ts']} 条")
        if s["first"]:
            print(f"时间范围：{s['first']} → {s['last']}")
        print("类型：" + " · ".join(f"{k} {v}" for k, v in s["types"]))
    for w in warnings:
        print(f"⚠ {w}")
    for e in errors:
        print(f"✗ {e}")
    if errors:
        print(f"\n{len(errors)} 个错误，修好再跑 stats.py")
        sys.exit(1)
    if warnings and a.strict:
        sys.exit(1)
    print("\n✓ 可以跑 stats.py 了" + (f"（{len(warnings)} 个提醒，看一眼）" if warnings else ""))


if __name__ == "__main__":
    main()
