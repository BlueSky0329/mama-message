#!/usr/bin/env python3
"""
打包 mama-message.skill（zip，内含 mama-message/ 前缀），可选把发布物同步到另一个目录。

用法（在仓库根目录）:
  python tools/pack.py                       # 只打包，输出到上一级目录 mama-message.skill
  python tools/pack.py --out 路径.skill
  python tools/pack.py --sync-to ../..       # .skill 和 README / SKILL / 普通用户版 / 示例 HTML / HANDOFF 一起放到该目录
  python tools/pack.py --sync-to dist        # Release 用：目录不存在会建

不进包的：web/（浏览器版，skill 用不到）、tools/、docs/（README 截图和交接文档）、evals/（触发测试集）、.github/、
mama-out/（跑出来的产物）、__pycache__、.pyc、.git。
上级目录里的那些文件是发布副本，改源文件再同步，不要直接改它们。只用标准库。
"""
import argparse
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from _common import setup_utf8  # noqa: E402

setup_utf8()

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git", ".github", "web", "tools", "docs", "evals", "mama-out", ".snap-tmp"}
SYNC = {
    "README.md": "README.md",
    "SKILL.md": "SKILL.md",
    os.path.join("prompts", "普通用户版.md"): "普通用户版.md",
    os.path.join("docs", "HANDOFF.md"): "HANDOFF.md",
    os.path.join("examples", "reports", "mama-message-report.html"): "示例报告-模拟数据.html",
    os.path.join("examples", "reports", "mama-message-card-bill.html"): "示例卡片-亲情账单.html",
    os.path.join("examples", "reports", "mama-message-card-send.html"): "示例卡片-发给她.html",
    os.path.join("examples", "reports", "mama-message-card-compare.html"): "示例卡片-对照组.html",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None, help=".skill 输出路径")
    ap.add_argument("--sync-to", default=None, help="把 .skill 和发布副本一起放到这个目录")
    a = ap.parse_args()
    sync_dir = None
    if a.sync_to:
        sync_dir = a.sync_to if os.path.isabs(a.sync_to) else os.path.abspath(os.path.join(ROOT, a.sync_to))
        os.makedirs(sync_dir, exist_ok=True)
    out = a.out or os.path.join(sync_dir or os.path.dirname(ROOT), "mama-message.skill")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(ROOT):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for f in sorted(files):
                if f.endswith(".pyc") or f.endswith(".skill"):
                    continue
                p = os.path.join(root, f)
                z.write(p, "mama-message/" + os.path.relpath(p, ROOT).replace(os.sep, "/"))
                n += 1
    print(f"打包 {n} 个文件 → {out}（{os.path.getsize(out) // 1024} KB）")
    if sync_dir:
        for src, dst in SYNC.items():
            shutil.copyfile(os.path.join(ROOT, src), os.path.join(sync_dir, dst))
            print(f"同步 {dst}")


if __name__ == "__main__":
    main()
