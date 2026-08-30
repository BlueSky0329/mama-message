#!/usr/bin/env python3
"""
打包 mama-message.skill（zip，内含 mama-message/ 前缀），可选把发布物同步到另一个目录。

用法（在仓库根目录）:
  python tools/pack.py                       # 只打包，输出到上一级目录 mama-message.skill
  python tools/pack.py --out 路径.skill
  python tools/pack.py --sync-to ../..       # .skill 和 README / SKILL / 普通用户版 / 示例 HTML 一起放到该目录

不进包的：web/（浏览器版，skill 用不到）、tools/、docs/（README 截图）、__pycache__、.pyc、.git。只用标准库。
"""
import argparse
import os
import shutil
import sys
import zipfile

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git", "web", "tools", "docs"}
SYNC = {
    "README.md": "README.md",
    "SKILL.md": "SKILL.md",
    os.path.join("prompts", "普通用户版.md"): "普通用户版.md",
    os.path.join("examples", "reports", "mama-message-report.html"): "示例报告-模拟数据.html",
    os.path.join("examples", "reports", "mama-message-card-bill.html"): "示例卡片-亲情账单.html",
    os.path.join("examples", "reports", "mama-message-card-send.html"): "示例卡片-发给她.html",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--sync-to", default=None)
    a = ap.parse_args()
    sync_dir = None
    if a.sync_to:
        sync_dir = a.sync_to if os.path.isabs(a.sync_to) else os.path.abspath(os.path.join(ROOT, a.sync_to))
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
