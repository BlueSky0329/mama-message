#!/usr/bin/env python3
"""
一条命令把"改完算法之后要做的事"全跑一遍，并告诉你哪些示例数字变了、哪些文档要手工改。

  python tools/refresh.py              # 重生成示例 → 算数 → 校验 → 渲染 → lint → 测试 → 打包并同步上级目录
  python tools/refresh.py --no-sync    # 不打包不同步（只在仓库里跑，CI 用）
  python tools/refresh.py --snapshot   # 顺便用 Chrome 重出 docs/img（要 playwright）

步骤和 CLAUDE.md「每次改完跑」一致。跑完会打印示例基线（docs/HANDOFF.md 第 7 节那几行）并和跑之前对比；
变了的话要同步 examples/sample-narrative.json、README 示例块、docs/HANDOFF.md 第 7 节、CHANGELOG。
README 里的测试数量（徽章和"N 个测试"）会按实际数量自动改。只用标准库。
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from _common import load_json, setup_utf8  # noqa: E402

setup_utf8()
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
SAMPLE_ARGS = ["--today", "2026-08-30", "--her-birthday", "10-20", "--my-birthday", "06-03"]


def run(label, *cmd, check=True):
    print(f"\n▶ {label}\n  $ {' '.join(cmd)}")
    r = subprocess.run([sys.executable, *cmd], cwd=ROOT, env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout + r.stderr).strip()
    if out:
        print("  " + "\n  ".join(out.splitlines()[-12:]))
    if check and r.returncode != 0:
        print(f"\n✗ 这一步失败了（exit {r.returncode}），先修它再往下。")
        sys.exit(1)
    return r


def baseline(S):
    """HANDOFF 第 7 节那几行的数字，作为 (名字, 值) 列表，便于逐项对比。"""
    b, o, r, s, u, h, ix = S["basics"], S["opens"], S["reply"]["me"], S["short"], S["unanswered"], S["hours"], S["index"]
    return [
        ("她 条数", b["her"]), ("你 条数", b["me"]), ("跨度天数", b["span_days"]),
        ("谁先开口 她", o["her"]), ("谁先开口 你", o["me"]), ("你回她中位", r["median"]),
        ("短回复", s["count"]), ("回复数", s["replies"]), ("短回复占比", round(100 * (s["ratio"] or 0))),
        ("没回", u["count"]), ("turn 数", u["turns"]), ("之后她先开口", u["reopened_by_her"]),
        ("早上 8 点前", h["her_early_count"]), ("晚上 10 点后", h["her_late_count"]),
        ("牵挂", ix["care"]["score"]), ("嗯哦好", ix["short"]["score"]), ("不计较", ix["forgive"]["score"]),
        ("评级分", S["rating"]["score"]), ("评级", S["rating"]["label"]),
        ("她的类型", S["mother_type"]["primary"]), ("她的副型", S["mother_type"]["secondary"]), ("你的类型", S["child_type"]["primary"]),
        ("信号", " / ".join(f"{'🔴' if x['level'] == 'red' else '🟡'} {x['kind']}" for x in S["signals"])),
    ]


def baseline_block(S):
    B = dict(baseline(S))
    return "\n".join([
        f"她 {B['她 条数']} 条 / 你 {B['你 条数']} 条 · {B['跨度天数']} 天",
        f"谁先开口 她 {B['谁先开口 她']} / 你 {B['谁先开口 你']} · 你回她中位 {B['你回她中位']} · 短回复 {B['短回复']} 条 / {B['回复数']} 条回复 {B['短回复占比']}%",
        f"没回 {B['没回']} / {B['turn 数']} 段 · 之后她先开口 {B['之后她先开口']} · 早上 8 点前 {B['早上 8 点前']} 条 · 晚上 10 点后 {B['晚上 10 点后']} 条",
        f"牵挂 {B['牵挂']} · 嗯哦好 {B['嗯哦好']} · 不计较 {B['不计较']} · 评级分 {B['评级分']}（{B['评级']}）",
        f"她 {B['她的类型']}" + (f"（副 {B['她的副型']}）" if B["她的副型"] else "") + f" · 你 {B['你的类型']} · 评级 {B['评级']}",
        f"信号：{B['信号']}",
    ])


def update_readme_test_count(n):
    p = os.path.join(ROOT, "README.md")
    with open(p, encoding="utf-8") as f:
        text = f.read()
    new = re.sub(r"tests-\d+%20passing", f"tests-{n}%20passing", text)
    new = re.sub(r"\d+ 个测试", f"{n} 个测试", new)
    if new != text:
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(new)
        print(f"  README 里的测试数量已改成 {n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-sync", action="store_true", help="不打包 .skill、不同步上级目录")
    ap.add_argument("--snapshot", action="store_true", help="用 Chrome 重出 docs/img（要 playwright）")
    a = ap.parse_args()
    stats_path = os.path.join(ROOT, "examples", "sample-stats.json")
    old = load_json(stats_path) if os.path.exists(stats_path) else None

    run("重生成模拟数据", "examples/make_sample.py")
    run("算数", "scripts/stats.py", "examples/sample-messages.json", "--out", "examples/sample-stats.json", *SAMPLE_ARGS, "--quiet")
    run("校验 messages.json", "scripts/validate.py", "examples/sample-messages.json")
    run("渲染", "scripts/render.py", "examples/sample-stats.json", "examples/sample-narrative.json", "--out", "examples/reports")
    with open(os.path.join(ROOT, "examples", "reports", "mama-message-report.html"), encoding="utf-8") as f:
        if "〔待写" in f.read():
            print("✗ 示例报告里还有〔待写〕，examples/sample-narrative.json 缺字段")
            sys.exit(1)
    run("检查文字规矩", "scripts/lint_narrative.py", "examples/sample-narrative.json",
        "--stats", "examples/sample-stats.json", "--messages", "examples/sample-messages.json")
    r = run("跑测试", "-m", "unittest", "discover", "-s", "tests")
    m = re.search(r"Ran (\d+) tests", r.stdout + r.stderr)
    if m:
        update_readme_test_count(int(m.group(1)))
    if a.snapshot:
        run("重出截图", "tools/snapshot.py")
    if not a.no_sync:
        run("打包并同步上级目录", "tools/pack.py", "--sync-to", "../..")

    new = load_json(stats_path)
    print("\n" + "=" * 60 + "\n示例基线（贴到 docs/HANDOFF.md 第 7 节）：\n" + baseline_block(new))
    if old:
        changed = [(k, ov, nv) for (k, ov), (_, nv) in zip(baseline(old), baseline(new)) if ov != nv]
        if changed:
            print("\n⚠ 和上一次相比变了的数字：")
            for k, ov, nv in changed:
                print(f"  {k}: {ov} → {nv}")
            print("要手工同步：examples/sample-narrative.json、README.md 开头的示例块、docs/HANDOFF.md 第 7 节、CHANGELOG.md")
        else:
            print("\n✓ 基线数字没变，文档不用改")
    print("\n全部完成。")


if __name__ == "__main__":
    main()
