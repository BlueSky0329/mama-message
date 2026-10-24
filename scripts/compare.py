#!/usr/bin/env python3
"""
对照组 / 偏心报告：把两个人的记录并排，出 compare.json、终端表格和一张对照卡。

用法:
  python scripts/compare.py mama-stats.json friend-stats.json --labels 你妈 朋友 --mode friend
  python scripts/compare.py 妈.json 爸.json --labels 妈 爸 --mode papa --png
  python scripts/compare.py mama-out/妈 mama-out/朋友 --labels 你妈 朋友      # mama.py run 出的目录也行

两个输入可以是 stats.json、messages.json（会先算一遍，--today 给"今天"）或者 mama.py run 的输出目录。
friend 模式看的是"你对谁更上心"（回复速度、短回复、没回）；papa 模式再加"谁更主动找你"。
对照卡（card-compare.html）就是视频开头那一帧："你回朋友 3 分钟，回你妈 4 小时 12 分"。
--png 用本机 Chrome / Edge 把卡截成图（scripts/snap.py）。只用标准库。
"""
import argparse
import html
import os
import sys
from datetime import date

from _common import ASSETS, dump_json, fmt_delta, load_json, setup_utf8

setup_utf8()


def pct(x):
    return "—" if x is None else f"{round(100 * x)}%"


def load_side(path, today=None):
    """stats.json / messages.json / 输出目录 → stats dict。"""
    if os.path.isdir(path):
        sp = os.path.join(path, "stats.json")
        if not os.path.exists(sp):
            raise ValueError(f"{path} 里没有 stats.json，先跑 python scripts/mama.py run")
        path = sp
    data = load_json(path)
    if isinstance(data, dict) and "index" in data and "reply" in data:
        return data
    if isinstance(data, dict) and isinstance(data.get("messages"), list):
        import stats
        return stats.compute(data, today=today or date.today())
    raise ValueError(f"{path} 既不是 stats.json 也不是 messages.json")


def compare(A, B, labels, mode="friend"):
    """两份 stats → compare.json 的内容。A 一般是家人，B 是朋友（friend）或者另一位家人（papa）。"""
    la, lb = labels
    rows = [
        ("你回 TA，通常要", fmt_delta(A["reply"]["me"]["median_s"]), fmt_delta(B["reply"]["me"]["median_s"]), "median_reply_s",
         A["reply"]["me"]["median_s"], B["reply"]["me"]["median_s"]),
        ("你回 TA 最长一次", fmt_delta(A["reply"]["me"]["max_s"]), fmt_delta(B["reply"]["me"]["max_s"]), "max_reply_s",
         A["reply"]["me"]["max_s"], B["reply"]["me"]["max_s"]),
        ("你的短回复占比", pct(A["short"]["ratio"]), pct(B["short"]["ratio"]), "short_ratio", A["short"]["ratio"], B["short"]["ratio"]),
        ("TA 发了你没回", f"{A['unanswered']['count']} 次", f"{B['unanswered']['count']} 次", "unanswered", A["unanswered"]["count"], B["unanswered"]["count"]),
        ("谁先开口 · TA 占比", pct(A["opens"]["her_ratio"]), pct(B["opens"]["her_ratio"]), "their_open_ratio", A["opens"]["her_ratio"], B["opens"]["her_ratio"]),
        ("你主动开口次数", f"{A['opens']['me']} 次", f"{B['opens']['me']} 次", "my_opens", A["opens"]["me"], B["opens"]["me"]),
        ("嗯哦好指数", A["index"]["short"]["score"], B["index"]["short"]["score"], "short_index", A["index"]["short"]["score"], B["index"]["short"]["score"]),
    ]
    out = {"mode": mode, "labels": list(labels),
           "rows": [{"name": r[0], "a": r[1], "b": r[2], "key": r[3], "a_raw": r[4], "b_raw": r[5]} for r in rows]}

    # 一句话结论
    ma, mb = A["reply"]["me"]["median_s"], B["reply"]["me"]["median_s"]
    lines, ratio = [], None
    if ma and mb and mb > 0:
        ratio = ma / mb
        if ratio >= 2:
            lines.append(f"你回{lb}要 {fmt_delta(mb)}，回{la}要 {fmt_delta(ma)}，差了 {round(ratio)} 倍。")
        elif ratio <= 0.5:
            lines.append(f"你回{la}比回{lb}快 {round(1 / ratio)} 倍。")
        else:
            lines.append(f"你回{la}和回{lb}的速度差不多。")
    sa, sb = A["short"]["ratio"] or 0, B["short"]["ratio"] or 0
    if abs(sa - sb) >= 0.15:
        lines.append(f"短回复：对{la} {pct(sa)}，对{lb} {pct(sb)}。")
    if mode == "papa":
        lines.append(f"{la}主动找你 {A['opens']['her']} 次，{lb} {B['opens']['her']} 次。你主动找{la} {A['opens']['me']} 次，找{lb} {B['opens']['me']} 次。")
    out["verdict"] = "".join(lines)
    out["ratio"] = round(ratio, 2) if ratio else None
    return out


def card_values(out, A, B):
    la, lb = out["labels"]
    ma, mb = A["reply"]["me"]["median_s"], B["reply"]["me"]["median_s"]
    ratio = out.get("ratio")
    # friend 模式先摆朋友再摆家人（"回朋友 3 分钟 → 回你妈 4 小时"）；papa 模式按给的顺序
    sides = [(lb, mb, B), (la, ma, A)] if out["mode"] == "friend" else [(la, ma, A), (lb, mb, B)]
    slow = max((s for s in sides if s[1]), key=lambda s: s[1], default=None)
    if ratio and (ratio >= 2 or ratio <= 0.5):
        headline = f"差了 {round(ratio if ratio >= 2 else 1 / ratio)} 倍"
    elif ratio:
        headline = "差不多快"
    else:
        headline = "有一边的记录不够算回复间隔"
    keep = ("short_ratio", "unanswered", "my_opens") + (("their_open_ratio",) if out["mode"] == "papa" else ())
    order = [1, 0] if out["mode"] == "friend" else [0, 1]
    head = "<tr><th></th>" + "".join(f"<th>{html.escape(str(sides[k][0]))}</th>" for k in range(2)) + "</tr>"
    body = ""
    for r in out["rows"]:
        if r["key"] in keep:
            vals = [r["a"], r["b"]]
            body += f"<tr><td>{html.escape(r['name'].replace('TA', ''))}</td>" + "".join(f"<td><b>{html.escape(str(vals[k]))}</b></td>" for k in order) + "</tr>"
    return {
        "TITLE": "对照组" if out["mode"] == "friend" else "偏心报告",
        "EYEBROW": "对照组" if out["mode"] == "friend" else "偏心报告",
        "LEFT_LABEL": html.escape(f"你回{sides[0][0]}，通常要"), "LEFT_VALUE": html.escape(fmt_delta(sides[0][1])),
        "RIGHT_LABEL": html.escape(f"你回{sides[1][0]}，通常要"), "RIGHT_VALUE": html.escape(fmt_delta(sides[1][1])),
        "LEFT_CLASS": "slow" if slow is sides[0] and ratio and (ratio >= 2 or ratio <= 0.5) else "",
        "RIGHT_CLASS": "slow" if slow is sides[1] and ratio and (ratio >= 2 or ratio <= 0.5) else "",
        "HEADLINE": html.escape(headline), "ROWS": head + body, "VERDICT": html.escape(out["verdict"]),
    }


def write_card(out, A, B, path):
    with open(os.path.join(ASSETS, "card-compare.html"), encoding="utf-8") as f:
        t = f.read()
    for k, v in card_values(out, A, B).items():
        t = t.replace("{{" + k + "}}", str(v))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", help="第一份：stats.json / messages.json / mama.py 的输出目录（一般是家人）")
    ap.add_argument("b", help="第二份（朋友，或者另一位家人）")
    ap.add_argument("--labels", nargs=2, default=["A", "B"], help="两个人怎么称呼，如 你妈 朋友")
    ap.add_argument("--mode", choices=["friend", "papa"], default="friend")
    ap.add_argument("--out", default="compare.json")
    ap.add_argument("--card", default=None, help="对照卡 HTML 路径（默认和 compare.json 放一起：mama-message-card-compare.html）")
    ap.add_argument("--png", action="store_true", help="对照卡再出一张 PNG（要本机装了 Chrome 或 Edge）")
    ap.add_argument("--today", default=None, help="输入是 messages.json 时，以哪天为今天（YYYY-MM-DD）")
    args = ap.parse_args()
    try:
        today = date.fromisoformat(args.today) if args.today else None
        A, B = load_side(args.a, today), load_side(args.b, today)
    except (ValueError, OSError) as e:
        print(f"✗ {e}")
        sys.exit(1)
    la, lb = args.labels
    out = compare(A, B, (la, lb), args.mode)
    w = max(len(r["name"]) for r in out["rows"]) + 2
    print(f"{'':{w}}{la:>12}{lb:>12}")
    for r in out["rows"]:
        print(f"{r['name']:{w}}{str(r['a']):>12}{str(r['b']):>12}")
    print("\n" + out["verdict"])
    if os.path.dirname(args.out):
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
    dump_json(out, args.out)
    print(f"→ {args.out}")
    card = args.card or os.path.join(os.path.dirname(os.path.abspath(args.out)), "mama-message-card-compare.html")
    write_card(out, A, B, card)
    print(f"→ {card}")
    if args.png:
        import snap
        try:
            print(f"→ {snap.html_to_png(card, card[:-5] + '.png')}")
        except snap.SnapError as e:
            print(f"⚠ 没出 PNG：{e}")


if __name__ == "__main__":
    main()
