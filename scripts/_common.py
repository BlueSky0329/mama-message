#!/usr/bin/env python3
"""
scripts/ 共用的小工具：UTF-8 输出、JSON 读写、时间解析与格式化、消息类型枚举、
契约版本号、词表加载、文本编码嗅探。只用标准库，不联网。

其他脚本都 `from _common import ...`。`python scripts/xxx.py` 时 scripts/ 自动在 sys.path 里；
用 runpy 或从别的目录 import 时要先把 scripts/ 加进 sys.path（web/index.html 的 RUNNER、tests/ 都加了）。
"""
import json
import os
import sys
from datetime import date, datetime

# 三份契约（messages.json / stats.json / narrative.json）共用的版本号。字段改到不兼容时 +1，
# render.py 会拒绝旧版 stats.json 并提示重跑；messages.json / narrative.json 缺这个字段也能用。
SCHEMA_VERSION = 1

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCES = os.path.join(ROOT, "references")
ASSETS = os.path.join(ROOT, "assets")
LEXICON_PATH = os.path.join(REFERENCES, "lexicon.json")

# 消息类型枚举：messages.json 的 type 只能是这些。parse_export 把各家导出映射到这里，
# validate 按这里查，stats / render 按 TYPE_CN 显示。
TYPES = ("text", "voice", "image", "video", "sticker", "transfer", "link",
         "call_voice", "call_video", "recall", "location", "file", "other")
TYPE_CN = {"sticker": "表情包", "image": "图片", "voice": "语音", "link": "链接", "video": "视频", "transfer": "转账",
           "call_voice": "语音通话", "call_video": "视频通话", "recall": "撤回的消息", "location": "位置", "file": "文件",
           "other": "其他"}

TS_FORMATS = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M")


def setup_utf8():
    """Windows 默认控制台是 GBK，打不出 emoji；把输出切到 UTF-8（其他平台无影响）。"""
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(obj, path):
    """统一 UTF-8、LF、缩进 1，Windows 上也不会写出 CRLF。"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def parse_ts(s):
    """契约里的 ts（ISO 或 "YYYY-MM-DD HH:MM[:SS]"）→ datetime；空或认不出来 → None。"""
    if not s or not isinstance(s, str):
        return None
    s = s.strip().replace("/", "-")
    for fmt in TS_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def fmt_delta(seconds):
    """秒数 → "3 分钟" / "1 小时 30 分" / "3 天 2 小时"。None → "—"。"""
    if seconds is None:
        return "—"
    m = int(seconds // 60)
    if m < 60:
        return f"{m} 分钟"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h} 小时 {m} 分" if m else f"{h} 小时"
    d, h = divmod(h, 24)
    return f"{d} 天 {h} 小时" if h else f"{d} 天"


def epoch_to_local(t):
    """Unix 时间（秒或毫秒，int / float / 纯数字字符串）→ 本地时间 "YYYY-MM-DD HH:MM:SS"；认不出来 → None。
    毫秒按数量级判断（> 1e11 就是毫秒）。用的是本机时区，海外用户见 metrics.md「时区」。"""
    try:
        v = float(t)
    except (TypeError, ValueError):
        return None
    if v > 1e11:
        v /= 1000.0
    try:
        return datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return None


def read_text(path):
    """读文本文件，自动识别编码。返回 (文本, 编码名)。
    顺序：UTF-8 BOM → UTF-16 BOM → 严格 UTF-8 → GB18030（微信 3.x / QQ 的老导出常见）→ UTF-8 容错。"""
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace"), "utf-8-sig"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", "replace"), "utf-16"
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace"), "utf-8（有坏字节，已跳过）"


def parse_mmdd(s):
    """"10-20" → (10, 20)。写错了给人话错误，不让 date() 的英文栈回溯露出来。"""
    try:
        mm, dd = str(s).strip().split("-")
        m, d = int(mm), int(dd)
    except ValueError:
        raise ValueError(f"生日要写成 MM-DD，比如 10-20，现在是 {s!r}")
    if not (1 <= m <= 12 and 1 <= d <= 31):
        raise ValueError(f"生日 {s!r} 不是一个合法日期（月 1–12，日 1–31）")
    return m, d


def safe_date(y, m, d):
    """date(y, m, d)，日期不存在（非闰年的 2-29）→ None，调用方跳过那一年。"""
    try:
        return date(y, m, d)
    except ValueError:
        return None


_LEXICON_KEYS = ("topics", "care_topics", "self_shrink", "chase", "nothing", "health_red", "health_link",
                 "news_link", "my_negative", "stopwords", "short_reply_exclude", "exclude")


def load_lexicon(path=None):
    """读 references/lexicon.json（stats.py 的全部词表）。缺文件或缺键给人话错误。"""
    p = path or LEXICON_PATH
    if not os.path.exists(p):
        raise FileNotFoundError(f"找不到词表 {p}。stats.py 要和 references/lexicon.json 放在同一个仓库里，"
                                "或者用 --lexicon 指定路径。")
    lex = load_json(p)
    missing = [k for k in _LEXICON_KEYS if k not in lex]
    if missing:
        raise ValueError(f"词表 {p} 缺少字段：{'、'.join(missing)}")
    return lex


def strip_excluded(text, excludes):
    """把误判词（"冷静"里的"冷"）先从消息里抹掉，再做关键词匹配。"""
    for e in excludes or ():
        if e in text:
            text = text.replace(e, " ")
    return text


def has_any(text, words, excludes=None):
    if excludes:
        text = strip_excluded(text, excludes)
    return any(w in text for w in words)
