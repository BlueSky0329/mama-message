#!/usr/bin/env python3
"""
一键打码。处理 txt / csv / json，输出 *.redacted.* 新文件，原文件不动。

打掉：手机号、身份证号、银行卡号、金额、你指定的名字。
用法:
  python scripts/redact.py 文件 --map "张小明=我" --map "李秀兰=妈妈" [--names 王阿姨 表姐]
--map   把真名换成称呼（真名=称呼），报告里就只会出现称呼
--names 直接抹成 ** 的名字（亲戚朋友）
"""
import argparse
import re
import os
import sys

# Windows 默认控制台是 GBK，打不出 emoji；统一把输出切到 UTF-8（其他平台无影响）
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

PATTERNS = [
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "1**********"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "******************"),
    (re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "****************"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(元|块|万)"), r"**\2"),
    (re.compile(r"[￥¥]\s*\d+(?:[,，]\d{3})*(?:\.\d+)?"), "￥**"),
    (re.compile(r"(转账|红包|转了|打了)\s*\d+(?:\.\d+)?"), r"\1 **"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "***@***"),
]


def redact(text, mapping, names):
    for real, alias in mapping.items():
        text = text.replace(real, alias)
    for n in names:
        text = text.replace(n, "**")
    for pat, rep in PATTERNS:
        text = pat.sub(rep, text)
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--map", action="append", default=[], help="真名=称呼，可多次")
    ap.add_argument("--names", nargs="*", default=[], help="直接抹掉的名字")
    a = ap.parse_args()
    mapping = {}
    for m in a.map:
        if "=" in m:
            k, v = m.split("=", 1)
            mapping[k.strip()] = v.strip()
    raw = open(a.path, encoding="utf-8", errors="ignore").read()
    out = redact(raw, mapping, a.names)
    base, ext = os.path.splitext(a.path)
    dst = f"{base}.redacted{ext}"
    open(dst, "w", encoding="utf-8", newline="\n").write(out)
    changed = sum(1 for x, y in zip(raw.splitlines(), out.splitlines()) if x != y)
    print(f"已打码 → {dst}（改动了 {changed} 行）")
    print("自己再翻一遍，工具认不出的地址、单位、小名它不会打。")


if __name__ == "__main__":
    main()
