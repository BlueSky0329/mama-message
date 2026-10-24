#!/usr/bin/env python3
"""
把各种导出格式统一成 messages.json（SKILL.md「工作表」格式）。

认得的来源（按内容识别，扩展名不对也行）：
  WeFlow 详细 JSON / TXT / weclone CSV        微信 4.0+，字段从社区 fork 源码核对
  留痕 MemoTrace / WeChatMsg 的 CSV / JSON      IsSender / StrContent / StrTime / Type 列（按公开 schema 写的，还没在真实导出上验证）
  微信 / QQ 导出的 txt                          两行式、单行式、带方括号时间等常见写法
  截图转录稿                                    AI 照截图抄的"她：/ 我："格式（见 references/export-guide.md「截图转录格式」），
                                                相邻截图重叠的消息自动去掉，"昨天 21:30 / 星期二 / 下午 3:05"这类时间自动换算
  她不一样(she-love-me) / 本项目的 messages.json  直通（可以只切时间段、改称呼）
  任意 [{time, sender, content}] 形式的 JSON
文件编码自动识别：UTF-8 / GB18030 / UTF-16。

用法:
  python scripts/parse_export.py 导出文件 --her 妈妈 [--call 妈妈] [--me 我] [--pronoun 她] [--out messages.json]
  python scripts/parse_export.py 导出文件 --her 妈妈 --last-days 180     # 只要最近半年
  python scripts/parse_export.py 导出文件 --her 妈妈 --since 2026-01-01 --until 2026-06-30
  python scripts/parse_export.py 转录稿.txt --call 妈妈 --shot-date 2026-08-30   # 截图转录稿，截图是哪天截的
  python scripts/parse_export.py 导出文件 --peek                        # 认不出格式时先看它读到了什么

--her  填对方在记录里显示的名字（或备注）。不填会先列出记录里出现的名字让你选。转录稿里写"她 / 他 / 妈"的不用填。
--call 报告里怎么称呼对方；记录里是真名时用它，默认同 --her。
--peek 不写文件，只打印识别到的格式、编码、前 10 条的解析结果（时间、发送者、类型、内容）和发送者名单。
       文件格式怪、条数不对、名字对不上时先跑这个，一眼能看出是哪一步歪了。
--since / --until / --last-days
       只取一段时间。WeFlow、留痕这类工具导出的是全量记录，可能有几万条、跨好几年，
       报告会被稀释成"三年平均"；一般取最近 6–12 个月。--last-days 是相对**最后一条消息**
       算的（不是今天），所以老档案也能用。
--tz   Unix 秒 / 毫秒、UTC 时间换算到哪个时区（+08:00）。默认用这台电脑的时区；人在国外分析国内的记录时
       填 +08:00，"她几点找你"才对。记录里本来就是本地时间的（txt、留痕 StrTime）不换算，只把时区记进 messages.json。
--shot-date  截图转录稿里"昨天 / 星期二 / 只写了 21:30"这类相对时间，按这一天（截图那天）换算。
只用标准库。
"""
import argparse
import csv
import io
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta

from _common import SCHEMA_VERSION, dump_json, epoch_to_local, parse_tz, read_text, setup_utf8, tz_label

setup_utf8()

TS_RE = r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?)"
LINE_PATTERNS = [
    re.compile(r"^\[?" + TS_RE + r"\]?\s+(?P<who>[^:：\n]{1,30}?)(?:\(\d+\)|<[^>]+>)?\s*[:：]\s*(?P<body>.*)$"),  # 时间 名字: 内容
    re.compile(r"^(?P<who>[^:：\n]{1,30}?)\s+" + TS_RE + r"\s*[:：]?\s*(?P<body>.*)$"),                      # 名字 时间 内容
]
HEADER_PATTERN = re.compile(r"^\[?" + TS_RE + r"\]?\s+(?P<who>[^\n]{1,30}?)(?:\(\d+\)|<[^>]+>)?\s*$")   # 时间 名字（下一行是内容）

TYPE_MARKERS = [
    (re.compile(r"\[语音\s*(\d+)\s*(?:秒|[\"”″]|s)?\]"), "voice"),         # 转录稿：[语音 23秒]
    (re.compile(r"\[语音\]\s*(\d+)\s*[\"”秒s]?"), "voice"),
    (re.compile(r"\[语音(?:通话|聊天)[^\]]*\]"), "call_voice"),
    (re.compile(r"\[视频(?:通话|聊天)[^\]]*\]"), "call_video"),
    (re.compile(r"\[语音消息[^\]]*\]"), "voice"),
    (re.compile(r"\[语音\]"), "voice"),
    (re.compile(r"\[图片\]|\[照片\]"), "image"),
    (re.compile(r"\[视频\]"), "video"),
    (re.compile(r"\[动画表情\]|\[表情\]|\[表情包\]|\[贴图\]"), "sticker"),
    (re.compile(r"\[转账[^\]]*\]|\[红包[^\]]*\]|\[微信红包\]|\[微信转账\]"), "transfer"),
    (re.compile(r"\[链接\]|\[分享\]|\[文章\]|\[公众号\]|\[小程序\]"), "link"),
    (re.compile(r"撤回了一条消息|\[撤回\]"), "recall"),
    (re.compile(r"\[位置\]"), "location"),
    (re.compile(r"\[文件\]"), "file"),
]
CALL_DUR = re.compile(r"(?:通话时长|时长|通话|聊天)\s*(?:(\d+):)?(\d+):(\d+)")

# 微信原生类型码（留痕 CSV 的 Type 列、WeFlow JSON 的 localType）
WX_TYPE = {"1": "text", "3": "image", "34": "voice", "43": "video", "47": "sticker", "49": "link", "50": "call_voice",
           "10000": "system", "48": "location"}

FORMAT_CN = {"native": "本项目的 messages.json", "weflow-json": "WeFlow 详细 JSON", "weflow-txt": "WeFlow TXT",
             "weclone-csv": "WeFlow weclone CSV", "memotrace-csv": "留痕 / WeChatMsg CSV", "csv": "通用 CSV",
             "json": "通用 JSON", "txt": "文本", "transcript": "截图转录稿"}


class ParseError(Exception):
    """给用户看的错误（人话），CLI 打印后 exit 1。"""


def norm_ts(s, tz=None):
    """各种写法的时间 → ISO；认不出来返回 None（stats.py 会当无时间戳处理，不会崩）。
    带时区的（UTC ISO）换算到 tz（不给就是本机时区）。"""
    try:
        s = s.strip()
        if s.endswith("Z") or re.search(r"[+-]\d{2}:\d{2}$", s):
            # WeFlow weclone CSV 的 CreateTime 是 UTC ISO-8601，转回本地时间
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(tz).strftime("%Y-%m-%dT%H:%M:%S")
        s = s.replace("/", "-").replace("T", " ")
        parts = s.split(" ")
        d = parts[0].split("-")
        d = f"{int(d[0]):04d}-{int(d[1]):02d}-{int(d[2]):02d}"
        t = parts[1] if len(parts) > 1 else "00:00:00"
        if t.count(":") == 1:
            t += ":00"
        hh, mm, ss = t.split(":")[:3]
        iso = f"{d}T{int(hh):02d}:{int(mm):02d}:{int(ss):02d}"
        datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S")   # 2026-13-45 这种要拦下
        return iso
    except (ValueError, IndexError, AttributeError):
        return None


def classify(body):
    """根据内容里的标记判断类型，返回 (type, content, dur)"""
    body = body.strip()
    for pat, typ in TYPE_MARKERS:
        m = pat.search(body)
        if m:
            dur = None
            if typ == "voice" and m.groups() and m.group(1):
                dur = int(m.group(1))
            if typ in ("call_voice", "call_video"):
                cm = CALL_DUR.search(body)
                if cm:
                    h, mi, se = cm.groups()
                    dur = (int(h or 0) * 3600) + int(mi) * 60 + int(se)
            content = body if typ in ("link", "recall") else ("转账" if typ == "transfer" else "")
            if typ == "link":
                content = re.sub(r"\[[^\]]*\]", "", body).strip() or body
            return typ, content, dur
    if re.fullmatch(r"(\[[^\]]{1,6}\]\s*)+", body):     # 只有内置表情
        return "sticker", body, None
    return "text", body, None


# ---------- 适配器 ----------
# 每种来源一个 parse_xxx(…, meta) → rows。rows 的每一项是 (ts, who, body, type, dur)：
#   ts   ISO 字符串或 None
#   who  记录里的名字；文件自带我方/对方标记时用 "__me__" / "__her__"
#   body 原文
#   type 已经确定的类型；None = 交给 classify 按内容标记判
#   dur  秒数或 None
# meta 记录识别结果（format / version / encoding / columns / notes），进 messages.json 的 source_detail 和 --peek。
# meta["tzinfo"] 是 --tz（None = 本机时区），Unix 时间和 UTC 时间按它换算。

def clean_who(w):
    """WeFlow 的 txt 把名字包在单引号里；顺手把各种引号都剥掉"""
    return w.strip().strip("'\"“”‘’").strip()


def parse_txt(text, meta):
    rows = []
    lines = text.splitlines()
    quoted = False
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        matched = False
        for pat in LINE_PATTERNS:
            m = pat.match(line)
            if m and m.group("body").strip():
                rows.append((norm_ts(m.group(1)), clean_who(m.group("who")), m.group("body"), None, None))
                matched = True
                break
        if matched:
            i += 1
            continue
        m = HEADER_PATTERN.match(line)
        if m:
            if m.group("who").strip().startswith("'"):
                quoted = True
            body = []
            j = i + 1
            while j < len(lines) and not HEADER_PATTERN.match(lines[j].strip()) and not any(p.match(lines[j].strip()) for p in LINE_PATTERNS):
                if lines[j].strip():
                    body.append(lines[j].strip())
                j += 1
            rows.append((norm_ts(m.group(1)), clean_who(m.group("who")), "\n".join(body), None, None))
            i = j
            continue
        # 既不是头也不是消息行：挂到上一条
        if rows:
            ts, who, body, typ, dur = rows[-1]
            rows[-1] = (ts, who, (body + "\n" + line).strip(), typ, dur)
        i += 1
    meta["format"] = "weflow-txt" if quoted else "txt"
    return rows


def parse_csv(text, meta):
    rows = []
    r = csv.DictReader(io.StringIO(text, newline=""))
    fields = list(r.fieldnames or [])
    cols = {c.strip().lower(): c for c in fields}
    meta["columns"] = fields
    tz = meta.get("tzinfo")

    def col(*names):
        for n in names:
            if n.lower() in cols:
                return cols[n.lower()]
        return None

    c_time = col("StrTime", "CreateTime", "time", "timestamp", "ts")
    c_content = col("StrContent", "content", "msg", "text", "message")
    c_sender = col("IsSender", "is_sender", "sender", "from", "Sender")
    c_type = col("Type", "type", "msg_type", "type_name")
    c_sub = col("SubType", "sub_type")
    c_nick = col("NickName", "Remark", "nickname", "name")
    if "type_name" in cols and "is_sender" in cols and "createtime" in cols:
        meta["format"] = "weclone-csv"
    elif "issender" in cols and "strcontent" in cols:
        meta["format"] = "memotrace-csv"
    else:
        meta["format"] = "csv"
    for row in r:
        t = (row.get(c_time) or "").strip() if c_time else ""
        if t.isdigit():
            t = epoch_to_local(t, tz) or t      # Unix 秒或毫秒；认不出来留原样，norm_ts 会给 None
        who = (row.get(c_sender) or "") if c_sender else ""
        if who in ("1", "0", "True", "False", "true", "false"):
            who = "__me__" if who in ("1", "True", "true") else ((row.get(c_nick) if c_nick else "__her__") or "__her__")
        body = (row.get(c_content) or "") if c_content else ""
        raw_t = str(row.get(c_type, "")).strip() if c_type else ""
        typ = WX_TYPE.get(raw_t) or (raw_t.lower() if raw_t.lower() in ("text", "image", "sticker", "video", "voice", "location", "file") else None)
        if typ == "link" and c_sub and str(row.get(c_sub, "")).strip() in ("2000", "2001"):
            typ = "transfer"
        if typ == "system":
            if "撤回" in body:
                typ = "recall"
            else:
                continue
        rows.append((norm_ts(t, tz) if t else None, who, body, typ, None))
    return rows


def pick(d, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def parse_json(data, meta):
    """返回 ("native", 原样的 messages.json) 或 ("rows", rows)。"""
    if isinstance(data, dict) and "messages" in data and data["messages"] and isinstance(data["messages"][0], dict) \
            and data["messages"][0].get("sender") in ("her", "me"):
        meta["format"] = "native"
        return "native", data
    if isinstance(data, dict) and isinstance(data.get("weflow"), dict):
        meta["format"] = "weflow-json"
        meta["version"] = str(data["weflow"].get("version") or "").strip() or None
        sess = data.get("session") or {}
        if isinstance(sess, dict) and sess.get("displayName"):
            meta["her_name"] = str(sess["displayName"])
    else:
        meta["format"] = "json"
    tz = meta.get("tzinfo")
    items = data["messages"] if isinstance(data, dict) and "messages" in data else data
    if isinstance(items, dict):
        items = items.get("data") or items.get("list") or []
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        t = pick(it, "ts", "time", "timestamp", "createTime", "create_time", "CreateTime", "StrTime", "datetime", "date", "formattedTime")
        if isinstance(t, (int, float)) or (isinstance(t, str) and t.isdigit()):
            t = epoch_to_local(t, tz)
        who = pick(it, "sender", "from", "talker", "senderDisplayName", "senderUsername", "nickname", "name", "who", "role", "speaker")
        is_sender = pick(it, "is_sender", "isSender", "IsSender", "isSend", "is_me", "self")
        if is_sender is not None:
            who = "__me__" if str(is_sender) in ("1", "True", "true") else (who or "__her__")
        body = pick(it, "content", "text", "msg", "message", "StrContent", "body") or ""
        typ = pick(it, "type", "msg_type", "kind")
        lt = pick(it, "localType", "local_type")
        if lt is not None and str(lt).isdigit():
            # WeFlow：微信原生类型码。49（应用消息：链接/转账/文件/引用…）和 50（通话）看内容标记更准，交给 classify
            if str(lt) == "10000":
                if "撤回" in str(body):
                    typ = "recall"
                else:
                    continue                      # 系统消息不进记录
            elif str(lt) in ("49", "50"):
                typ = None
            else:
                typ = WX_TYPE.get(str(lt))
        elif isinstance(typ, int) or (isinstance(typ, str) and typ.isdigit()):
            typ = WX_TYPE.get(str(typ))
        elif isinstance(typ, str) and typ and not typ.isascii():
            typ = None                            # 中文类型名（"文本消息"）交给 classify 按内容判
        if not str(body).strip() and it.get("linkTitle"):
            body = "[链接] " + str(it["linkTitle"])
        dur = pick(it, "dur", "duration", "seconds", "voiceDuration")
        rows.append((norm_ts(str(t), tz) if t else None, str(who), str(body), typ, dur))
    return "rows", rows


# ---------- 截图转录稿 ----------
# AI 照截图逐张抄成下面这样，脚本负责去重叠、换算时间（格式说明在 references/export-guide.md）：
#   === 截图 1 ===
#   -- 2026-05-12 21:03 --        截图中间那行灰色的时间，原样抄
#   她：吃饭了吗
#   我：吃了
#   她：[语音 23秒]
#   -- 昨天 下午 3:05 --          相对时间按 --shot-date 换算
BLOCK_RE = re.compile(r"^(?:[=＝]{3,}.*|-{3,}\s*|【?截图\s*\d*】?|#+\s*截图.*)$")
SEP_RE = re.compile(r"^[-—]{2}\s*(?P<t>.*?\d.*?)\s*[-—]{2}$")
SPEAKER_RE = re.compile(r"^(?P<who>[^\s：:\[\]（）()]{1,10})(?:[（(][^）)]{0,10}[）)])?\s*[：:]\s*(?P<body>.+)$")   # "她（妈妈）："也认
HER_LABELS = {"她", "他", "对方", "左", "妈", "妈妈", "老妈", "母亲", "爸", "爸爸", "老爸", "父亲", "外婆", "外公", "奶奶", "爷爷", "姥姥", "姥爷"}
ME_LABELS = {"我", "自己", "右"}
_PERIOD = r"(?P<pd>凌晨|早上|早晨|上午|中午|下午|傍晚|晚上)?\s*"
_HM = r"(?P<h>\d{1,2})[:：](?P<mi>\d{2})(?::\d{2})?"
SEP_FORMS = [
    ("ymd", re.compile(r"^(?P<y>\d{4})\s*[-/年.]\s*(?P<m>\d{1,2})\s*[-/月.]\s*(?P<d>\d{1,2})\s*日?\s*" + _PERIOD + _HM + r"$")),
    ("md", re.compile(r"^(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日\s*" + _PERIOD + _HM + r"$")),
    ("rel", re.compile(r"^(?P<rel>昨天|前天)\s*" + _PERIOD + _HM + r"$")),
    ("wd", re.compile(r"^(?:星期|周|礼拜)(?P<wd>[一二三四五六日天])\s*" + _PERIOD + _HM + r"$")),
    ("hm", re.compile(r"^(?:今天)?\s*" + _PERIOD + _HM + r"$")),
]
WEEKDAY_CN = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


def looks_like_transcript(text):
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("//")]
    if not lines:
        return False
    first_is_mark = BLOCK_RE.match(lines[0]) or SEP_RE.match(lines[0])     # "-- 2026-05-12 21:03 --" 也长得像"名字 时间 内容"
    if not first_is_mark and (any(p.match(lines[0]) for p in LINE_PATTERNS) or HEADER_PATTERN.match(lines[0])):
        return False
    speakers = sum(1 for l in lines if SPEAKER_RE.match(l))
    marks = sum(1 for l in lines if BLOCK_RE.match(l) or SEP_RE.match(l))
    return speakers >= 2 and (marks >= 1 or speakers >= 0.6 * len(lines))


def sep_time(text, state):
    """转录稿里的一行时间 → datetime 或 None。state: {"date": 上一个已知日期, "shot": 截图那天, "relative": 换算不了的个数}。"""
    t = text.strip()
    for kind, pat in SEP_FORMS:
        m = pat.match(t)
        if not m:
            continue
        h, mi, pd = int(m.group("h")), int(m.group("mi")), m.group("pd")
        if pd in ("下午", "傍晚", "晚上") and h < 12:
            h += 12
        elif pd == "中午" and h < 11:
            h += 12
        elif pd in ("凌晨", "早上", "早晨", "上午") and h == 12:
            h = 0
        shot, d = state.get("shot"), None
        if kind == "ymd":
            try:
                d = date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
            except ValueError:
                return None
        elif kind == "md":
            # 微信对今年的消息只显示"5月12日"：年份跟截图那天（或别处写全了的年份）走，跨年的往前推一年
            year = shot.year if shot else (state["date"].year if state.get("date") else state.get("year"))
            if year is None:
                state["relative"] += 1
                return None
            try:
                d = date(year, int(m.group("m")), int(m.group("d")))
            except ValueError:
                return None
            if shot and d > shot:
                d = d.replace(year=d.year - 1)
        elif kind == "rel":
            if not shot:
                state["relative"] += 1
                return None
            d = shot - timedelta(days=1 if m.group("rel") == "昨天" else 2)
        elif kind == "wd":
            if not shot:
                state["relative"] += 1
                return None
            want = WEEKDAY_CN[m.group("wd")]
            d = next(shot - timedelta(days=k) for k in range(2, 9) if (shot - timedelta(days=k)).weekday() == want)
        else:
            d = shot or state.get("date")
            if d is None:
                state["relative"] += 1
                return None
        try:
            dt = datetime(d.year, d.month, d.day, h, mi)
        except ValueError:
            return None
        state["date"] = d
        return dt
    return None


def resolve_speaker(label, hints):
    if label in ME_LABELS or (hints.get("me") and label == hints["me"]):
        return "__me__"
    if label in HER_LABELS or label in (hints.get("her"), hints.get("call")):
        return "__her__"
    return label


def overlap_len(older, newer):
    """older 的结尾和 newer 的开头有几条一样（按发送者和内容，不看时间）。"""
    for L in range(min(len(older), len(newer)), 0, -1):
        if [(r[1], r[2]) for r in older[-L:]] == [(r[1], r[2]) for r in newer[:L]]:
            return L
    return 0


def parse_transcript(text, meta, hints=None):
    """截图转录稿 → rows。按截图分段，段内一行一条；相邻两段首尾重复的消息去掉；截图倒着给的顺过来。"""
    hints = hints or {}
    ym = re.search(r"(\d{4})\s*[-/年.]\s*\d{1,2}\s*[-/月.]\s*\d{1,2}", text)
    state = {"date": None, "shot": hints.get("shot_date"), "relative": 0, "year": int(ym.group(1)) if ym else None}
    blocks, cur = [], []
    pending_ts = None
    # "注意：明天降温"这种续行里带冒号的，别当成新的说话人：只出现一次、又认不出是谁的标签，算上一条的续行
    labels = Counter(m.group("who") for m in (SPEAKER_RE.match(l.strip()) for l in text.splitlines()) if m)
    known = {w for w in labels if resolve_speaker(w, hints) in ("__her__", "__me__")}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("```") or line.startswith("~~~"):
            continue                      # 聊天 AI 爱把稿子包在代码块里
        sp = SPEAKER_RE.match(line)
        if sp and known and sp.group("who") not in known and labels[sp.group("who")] == 1 and cur:
            cur[-1][2] += "\n" + line
            continue
        if BLOCK_RE.match(line):
            if cur:
                blocks.append(cur)
            cur, pending_ts = [], None
            continue
        sm = SEP_RE.match(line)
        if sm:
            dt = sep_time(sm.group("t"), state)
            pending_ts = dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None
            continue
        m = SPEAKER_RE.match(line)
        if m:
            cur.append([pending_ts, resolve_speaker(m.group("who"), hints), m.group("body").strip(), None, None])
            pending_ts = None             # 一个时间只给它下面的第一条，后面的没有时间戳（不编时间）
        elif cur:
            cur[-1][2] += "\n" + line     # 一条消息换了行
    if cur:
        blocks.append(cur)
    # 截图从最近往上翻着截的，段的顺序可能是新到旧：先看每段第一个时间，多数在变早就倒过来；
    # 时间不够判断时看重叠的方向——上一段的开头 = 下一段的结尾，说明是倒着给的
    firsts = [next((r[0] for r in b if r[0]), None) for b in blocks]
    known = [f for f in firsts if f]
    if len(known) >= 2:
        reversed_ = sum(1 for a, b in zip(known, known[1:]) if b < a) > (len(known) - 1) / 2
    else:
        fwd = sum(1 for a, b in zip(blocks, blocks[1:]) if overlap_len(a, b))
        bwd = sum(1 for a, b in zip(blocks, blocks[1:]) if overlap_len(b, a))
        reversed_ = bwd > fwd
    if reversed_:
        blocks.reverse()
    rows, dropped = [], 0
    for b in blocks:
        if rows:
            # 上一张截图的结尾和这一张的开头重叠：找最长的重叠，去掉这一张开头的那几条
            overlap = overlap_len(rows, b)
            for k in range(overlap):
                if not rows[len(rows) - overlap + k][0] and b[k][0]:
                    rows[len(rows) - overlap + k][0] = b[k][0]     # 重复的那条只有一边带了时间：留下时间
            dropped += overlap
            b = b[overlap:]
        rows.extend(b)
    meta["format"] = "transcript"
    meta["source"] = "screenshots"
    notes = meta.setdefault("notes", [])
    if len(blocks) > 1:
        notes.append(f"{len(blocks)} 段截图" + ("（给的顺序是从新到旧，已经倒过来）" if reversed_ else ""))
    if dropped:
        notes.append(f"去掉了相邻截图重叠的 {dropped} 条")
    if state["relative"]:
        notes.append(f"{state['relative']} 个时间是“昨天 / 星期二 / 只写了几点”这种相对说法，换算不了，下面那条不带时间——加 --shot-date 截图那天")
    return [tuple(r) for r in rows]


def looks_like_csv(text):
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    if first.count(",") < 2:
        return False
    return not (HEADER_PATTERN.match(first) or any(p.match(first) for p in LINE_PATTERNS))


def load_any(path, hints=None, tzinfo=None):
    """读文件并识别格式 → (kind, payload, meta)。kind 是 "native"（payload 是 messages.json 的 dict）或 "rows"。
    先看内容再看扩展名：.txt 里装着 JSON 也认。hints 是 --her / --me / --call / shot_date，转录稿认人用。"""
    text, enc = read_text(path)
    meta = {"format": None, "version": None, "encoding": enc, "columns": None, "tzinfo": tzinfo, "notes": []}
    ext = os.path.splitext(path)[1].lower()
    head = text.lstrip()[:1]
    if ext == ".json" or head in ("{", "["):
        try:
            data = json.loads(text)
        except ValueError as e:
            if ext == ".json":
                raise ParseError(f"✗ 不是合法的 JSON：{e}")
            data = None
        if data is not None:
            kind, payload = parse_json(data, meta)
            return kind, payload, meta
    if ext == ".csv" or looks_like_csv(text):
        return "rows", parse_csv(text, meta), meta
    if looks_like_transcript(text):
        return "rows", parse_transcript(text, meta, hints), meta
    return "rows", parse_txt(text, meta), meta


def format_label(meta):
    return FORMAT_CN.get(meta["format"], meta["format"] or "?") + (f" {meta['version']}" if meta.get("version") else "")


def source_detail(meta):
    return (meta["format"] or "unknown") + (f" {meta['version']}" if meta.get("version") else "") + f" · {meta['encoding']}"


# ---------- 主流程 ----------

def clip(msgs, since=None, until=None, last_days=None):
    """按日期切一段。返回 (保留的消息, 丢掉的条数, 实际起点, 实际终点)。
    没有时间戳的消息在切片时会被丢掉——留着也没法判断它在不在区间里。"""
    if last_days:
        dates = [m["ts"][:10] for m in msgs if m["ts"]]
        if dates:
            start = date.fromisoformat(max(dates)) - timedelta(days=last_days - 1)
            since = max(since, start.isoformat()) if since else start.isoformat()
    if not since and not until:
        return msgs, 0, None, None
    keep = [m for m in msgs if m["ts"] and (not since or m["ts"][:10] >= since) and (not until or m["ts"][:10] <= until)]
    return keep, len(msgs) - len(keep), since, until


def build(rows, her, me, pronoun, detail=None, source="export"):
    """rows → messages.json 的 dict。her / me 是记录里的名字（或 __her__ / __me__），其余发送者丢掉。"""
    msgs = []
    for ts, who, body, typ, dur in rows:
        if who == "__me__" or (me and who == me):
            side = "me"
        elif who == "__her__" or (her and who == her):
            side = "her"
        else:
            continue
        if typ in (None, "text"):
            typ2, content, dur2 = classify(body)
            typ = typ2
            dur = dur if dur is not None else dur2
        else:
            content = body if typ in ("text", "link", "recall") else ("转账" if typ == "transfer" else "")
        msgs.append({"ts": ts, "sender": side, "type": typ, "content": content, "dur": dur})
    return {"schema": SCHEMA_VERSION, "me": me or "我", "her": her or "妈妈", "her_pronoun": pronoun or "她",
            "source": source, "source_detail": detail or "unknown", "messages": msgs}


def convert(path, her=None, me=None, call=None, pronoun=None, since=None, until=None, last_days=None, tz=None, shot_date=None):
    """导出文件 → (messages.json 的 dict, 给人看的几行摘要)。出错抛 ParseError（人话）。mama.py 和 main() 共用。
    tz 是 "+08:00" 这样的字符串；shot_date 是 "YYYY-MM-DD"。"""
    if pronoun and pronoun not in ("她", "他"):
        raise ParseError(f"--pronoun 只能是 她 或 他，现在是 {pronoun!r}")
    try:
        tzinfo = parse_tz(tz)
    except ValueError as e:
        raise ParseError(f"--tz：{e}")
    try:
        shot = date.fromisoformat(shot_date) if shot_date else None
    except ValueError:
        raise ParseError(f"--shot-date 要写成 2026-08-30 这样的日期，现在是 {shot_date!r}")
    hints = {"her": her, "me": me, "call": call, "shot_date": shot}
    kind, payload, meta = load_any(path, hints, tzinfo)
    detail = source_detail(meta)
    tzs = tz_label(tzinfo)
    report = []
    if kind == "native":
        if call:
            payload["her"] = call
        if pronoun:
            payload["her_pronoun"] = pronoun
        payload.setdefault("schema", SCHEMA_VERSION)
        payload.setdefault("source_detail", detail)
        payload["messages"], dropped, s0, s1 = clip(payload["messages"], since, until, last_days)
        if not payload["messages"]:
            raise ParseError(f"这段时间（{s0 or '最早'} → {s1 or '最后'}）里没有消息，换个范围试试。" if dropped else "文件里没有消息。")
        report.append(f"已经是 messages.json 格式（{len(payload['messages'])} 条）"
                      + (f"，按 {s0 or '最早'} → {s1 or '最后'} 切掉了 {dropped} 条" if dropped else ""))
        return payload, report

    rows = payload
    senders = Counter(r[1] for r in rows)
    has_flag = "__me__" in senders or "__her__" in senders
    if not has_flag and not her:
        names = "\n".join(f"  {who}  {n} 条" for who, n in senders.most_common(6))
        raise ParseError(f"识别为：{format_label(meta)}，编码 {meta['encoding']}。记录里出现的名字（按条数）：\n{names}\n\n"
                         "请用 --her 指定对方的名字，例如：--her 妈妈 ；如果你的名字不是“我”，再加 --me 你的名字")
    if not has_flag and her not in senders:
        # 名字写错时别悄悄把所有消息都算成"我"
        raise ParseError(f"记录里没有叫“{her}”的发送者。出现的名字（按条数）：" + "、".join(f"{w}({n})" for w, n in senders.most_common(6))
                         + "\n--her 要和记录里显示的一模一样（含备注、空格）；用 --peek 看它读到了什么。")
    src = meta.get("source") or "export"
    if has_flag:
        # 文件自带我方标记；对方可能有名字也可能是 __her__，统一归到 __her__
        flagged = [(ts, ("__me__" if who == "__me__" else "__her__"), body, typ, dur) for ts, who, body, typ, dur in rows]
        data = build(flagged, "__her__", "__me__", pronoun, detail, src)
        data["her"] = her or "妈妈"
        data["me"] = me or "我"
    else:
        me2 = me or next((w for w, _ in senders.most_common() if w != her), None)   # 除了她之外条数最多的当作我
        data = build(rows, her, me2, pronoun, detail, src)
    if call:
        data["her"] = call        # 记录里叫“李秀兰”，报告里叫“妈妈”
    data["tz"] = tzs
    data["messages"], dropped, s0, s1 = clip(data["messages"], since, until, last_days)
    n = len(data["messages"])
    if dropped and n == 0:
        raise ParseError(f"这段时间（{s0 or '最早'} → {s1 or '最后'}）里没有消息，换个范围试试。")
    if n == 0:
        raise ParseError(f"识别为：{format_label(meta)}，编码 {meta['encoding']}，但没解析出任何消息。"
                         "检查 --her 的名字是不是和记录里一模一样（包括空格和备注）；用 --peek 看它读到了什么。")
    c = Counter(m["sender"] for m in data["messages"])
    t = Counter(m["type"] for m in data["messages"])
    report.append(f"解析完成：{n} 条（{format_label(meta)}，{meta['encoding']}，时区 {tzs}）"
                  + (f"，按 {s0 or '最早'} → {s1 or '最后'} 切掉了 {dropped} 条" if dropped else ""))
    for note in meta.get("notes") or []:
        report.append("  " + note)
    if meta.get("her_name") and not (her or call):
        report.append(f"  记录里对方显示为“{meta['her_name']}”，报告里默认称呼“{data['her']}”，想改用 --call")
    report.append(f"  {data['her']} {c['her']} 条 / {data['me']} {c['me']} 条")
    report.append("  类型：" + " · ".join(f"{k} {v}" for k, v in t.most_common()))
    report.append("  无时间戳：" + str(sum(1 for m in data['messages'] if not m['ts'])))
    return data, report


def peek(path, hints=None, tzinfo=None):
    """把文件读一遍，打印识别结果和前 10 条。不写任何文件。"""
    kind, payload, meta = load_any(path, hints, tzinfo)
    print(f"文件：{path}\n编码：{meta['encoding']}")
    if kind == "native":
        ms = payload["messages"]
        print(f"识别为：{format_label(meta)}（{len(ms)} 条，{payload.get('her')} / {payload.get('me')}）")
        rows = [(m.get("ts"), m.get("sender"), m.get("type"), m.get("content", "")) for m in ms[:10]]
        names = Counter(m.get("sender") for m in ms)
    else:
        print(f"识别为：{format_label(meta)}（{len(payload)} 条）")
        if meta.get("columns"):
            print(f"列名：{meta['columns']}")
        for note in meta.get("notes") or []:
            print(note)
        rows = []
        for ts, who, body, typ, dur in payload[:10]:
            if typ in (None, "text"):
                typ, content, dur2 = classify(body)
                dur = dur if dur is not None else dur2
            else:
                content = body
            rows.append((ts, who, typ + (f" {dur}秒" if dur else ""), content or body))
        names = Counter(r[1] for r in payload)
    print("\n前 10 条：")
    for ts, who, typ, content in rows:
        c = (content or "").replace("\n", " ")[:36]
        print(f"  {str(ts or '(无时间戳)'):20s} {str(who):12s} {str(typ):12s} {c}")
    print("\n发送者（按条数）：" + "、".join(f"{k}({v})" for k, v in names.most_common(6)))
    print("名字对不上就调 --her / --me；时间是 (无时间戳) 说明时间格式没认出来；"
          "类型全是 text 说明 [语音][图片] 这类标记和脚本预期的不一样——把上面几行贴给 AI，让它照 messages.json 的格式转。")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="导出文件（json / csv / txt / 截图转录稿）")
    ap.add_argument("--her", default=None, help="对方在记录里的名字/备注")
    ap.add_argument("--me", default=None, help="你在记录里的名字（CSV/JSON 有 IsSender 时不用填）")
    ap.add_argument("--pronoun", default=None, help="她 / 他，默认 她")
    ap.add_argument("--call", default=None, help="报告里怎么称呼对方（妈妈 / 老爸 / 外婆），默认同 --her")
    ap.add_argument("--out", default="messages.json")
    ap.add_argument("--since", default=None, help="只要这天及以后的（YYYY-MM-DD）")
    ap.add_argument("--until", default=None, help="只要这天及以前的（YYYY-MM-DD）")
    ap.add_argument("--last-days", type=int, default=None, help="只要最后一条消息往前 N 天（跨好几年的全量导出用这个）")
    ap.add_argument("--tz", default=None, help="Unix / UTC 时间换算到哪个时区，如 +08:00（默认本机时区）")
    ap.add_argument("--shot-date", default=None, help="截图转录稿：截图是哪天截的（YYYY-MM-DD），换算“昨天 / 星期二”")
    ap.add_argument("--peek", action="store_true", help="不写文件，只看识别结果和前 10 条")
    a = ap.parse_args()
    for f in ("since", "until"):
        v = getattr(a, f)
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                print(f"--{f} 要写成 2026-01-01 这样的日期，现在是 {v!r}")
                sys.exit(1)
    try:
        if a.peek:
            try:
                shot = date.fromisoformat(a.shot_date) if a.shot_date else None
            except ValueError:
                raise ParseError(f"--shot-date 要写成 2026-08-30 这样的日期，现在是 {a.shot_date!r}")
            peek(a.path, {"her": a.her, "me": a.me, "call": a.call, "shot_date": shot}, parse_tz(a.tz))
            return
        data, report = convert(a.path, her=a.her, me=a.me, call=a.call, pronoun=a.pronoun, since=a.since, until=a.until,
                               last_days=a.last_days, tz=a.tz, shot_date=a.shot_date)
    except (ParseError, ValueError) as e:
        print(str(e))
        sys.exit(1)
    dump_json(data, a.out)
    print(report[0] + f" → {a.out}")
    for line in report[1:]:
        print(line)


if __name__ == "__main__":
    main()
