#!/usr/bin/env python3
"""
对照组 / 偏心报告：把两份 stats.json 并排。

用法:
  python scripts/compare.py mama-stats.json friend-stats.json --labels 你妈 朋友 --mode friend
  python scripts/compare.py mama-stats.json papa-stats.json  --labels 妈 爸   --mode papa

friend 模式看的是"你对谁更上心"（回复速度、短回复、没回）。
papa   模式看的是"你偏心谁"（同上，再加谁更主动找你）。
输出 compare.json 和终端表格。只用标准库。
"""
import argparse

from _common import dump_json, fmt_delta, load_json, setup_utf8

setup_utf8()


def pct(x):
    return "—" if x is None else f"{round(100 * x)}%"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", help="第一份 stats.json")
    ap.add_argument("b", help="第二份 stats.json")
    ap.add_argument("--labels", nargs=2, default=["A", "B"], help="两个人怎么称呼，如 你妈 朋友")
    ap.add_argument("--mode", choices=["friend", "papa"], default="friend")
    ap.add_argument("--out", default="compare.json")
    args = ap.parse_args()
    A, B = load_json(args.a), load_json(args.b)
    la, lb = args.labels

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
    out = {"mode": args.mode, "labels": args.labels, "rows": [{"name": r[0], "a": r[1], "b": r[2], "key": r[3], "a_raw": r[4], "b_raw": r[5]} for r in rows]}

    # 一句话结论
    ma, mb = A["reply"]["me"]["median_s"], B["reply"]["me"]["median_s"]
    lines = []
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
    if args.mode == "papa":
        lines.append(f"{la}主动找你 {A['opens']['her']} 次，{lb} {B['opens']['her']} 次。你主动找{la} {A['opens']['me']} 次，找{lb} {B['opens']['me']} 次。")
    out["verdict"] = " ".join(lines)

    w = max(len(r[0]) for r in rows) + 2
    print(f"{'':{w}}{la:>12}{lb:>12}")
    for r in rows:
        print(f"{r[0]:{w}}{str(r[1]):>12}{str(r[2]):>12}")
    print("\n" + out["verdict"])
    dump_json(out, args.out)
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
