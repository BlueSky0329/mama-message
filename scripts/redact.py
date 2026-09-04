#!/usr/bin/env python3
"""
一键打码。处理 txt / csv / json，输出 *.redacted.* 新文件（UTF-8），原文件不动。

打掉：手机号、身份证号、银行卡号、金额、邮箱、你指定的名字。
用法:
  python scripts/redact.py 文件 --map "张小明=我" --map "李秀兰=妈妈" [--names 王阿姨 表姐]
--map   把真名换成称呼（真名=称呼），报告里就只会出现称呼
--names 直接抹成 ** 的名字（亲戚朋友）
输入文件的编码自动识别（UTF-8 / GB18030 / UTF-16），输出一律 UTF-8。只用标准库。
"""
import argparse
import os
import re

from _common import read_text, setup_utf8

setup_utf8()

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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="要打码的文件")
    ap.add_argument("--map", action="append", default=[], help="真名=称呼，可多次")
    ap.add_argument("--names", nargs="*", default=[], help="直接抹掉的名字")
    a = ap.parse_args()
    mapping = {}
    for m in a.map:
        if "=" in m:
            k, v = m.split("=", 1)
            mapping[k.strip()] = v.strip()
    raw, enc = read_text(a.path)
    out = redact(raw, mapping, a.names)
    base, ext = os.path.splitext(a.path)
    dst = f"{base}.redacted{ext}"
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    changed = sum(1 for x, y in zip(raw.splitlines(), out.splitlines()) if x != y)
    print(f"已打码 → {dst}（改动了 {changed} 行；原文件编码 {enc}，输出 UTF-8）")
    print("自己再翻一遍，工具认不出的地址、单位、小名它不会打。")


if __name__ == "__main__":
    main()
