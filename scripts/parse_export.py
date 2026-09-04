#!/usr/bin/env python3
"""
把各种导出格式统一成 messages.json（SKILL.md「工作表」格式）。

认得的来源（按内容识别，扩展名不对也行）：
  WeFlow 详细 JSON / TXT / weclone CSV        微信 4.0+，字段从社区 fork 源码核对
  留痕 MemoTrace / WeChatMsg 的 CSV / JSON      IsSender / StrContent / StrTime / Type 列（按公开 schema 写的，还没在真实导出上验证）
  微信 / QQ 导出的 txt                          两行式、单行式、带方括号时间等常见写法
  她不一样(she-love-me) / 本项目的 messages.json  直通（可以只切时间段、改称呼）
  任意 [{time, sender, content}] 形式的 JSON
文件编码自动识别：UTF-8 / GB18030 / UTF-16。

用法:
  python scripts/parse_export.py 导出文件 --her 妈妈 [--call 妈妈] [--me 我] [--pronoun 她] [--out messages.json]
  python scripts/parse_export.py 导出文件 --her 妈妈 --last-days 180     # 只要最近半年
  python scripts/parse_export.py 导出文件 --her 妈妈 --since 2026-01-01 --until 2026-06-30
  python scripts/parse_export.py 导出文件 --peek                        # 认不出格式时先看它读到了什么

--her  填对方在记录里显示的名字（或备注）。不填会先列出记录里出现的名字让你选。
--call 报告里怎么称呼对方；记录里是真名时用它，默认同 --her。
--peek 不写文件，只打印识别到的格式、编码、前 10 条的解析结果（时间、发送者、类型、内容）和发送者名单。
       文件格式怪、条数不对、名字对不上时先跑这个，一眼能看出是哪一步歪了。
--since / --until / --last-days
       只取一段时间。WeFlow、留痕这类工具导出的是全量记录，可能有几万条、跨好几年，
       报告会被稀释成"三年平均"；一般取最近 6–12 个月。--last-days 是相对**最后一条消息**
       算的（不是今天），所以老档案也能用。
时间戳按导出电脑的本地时区解释（Unix 秒 / 毫秒、UTC ISO 都会转成本地时间）；人在国外分析国内的记录，时段会偏，见 metrics.md「时区」。
只用标准库。
"""
import argparse
import csv
import io
import json
import os
import sys
from collections import Counter
from datetime import datetime, date, timedelta

from _common import SCHEMA_VERSION, dump_json, epoch_to_local, read_text, setup_utf8

setup_utf8()

import re  # noqa: E402

TS_RE = r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?)"
LINE_PATTERNS = [
    re.compile(r"^\[?" + TS_RE + r"\]?\s+(?P<who>[^:：\n]{1,30}?)(?:\(\d+\)|<[^>]+>)?\s*[:：]\s*(?P<body>.*)$"),  # 时间 名字: 内容
    re.compile(r"^(?P<who>[^:：\n]{1,30}?)\s+" + TS_RE + r"\s*[:：]?\s*(?P<body>.*)$"),                      # 名字 时间 内容
]
HEADER_PATTERN = re.compile(r"^\[?" + TS_RE + r"\]?\s+(?P<who>[^\n]{1,30}?)(?:\(\d+\)|<[^>]+>)?\s*$")   # 时间 名字（下一行是内容）

TYPE_MARKERS = [
    (re.compile(r"\[语音\]\s*(\d+)\s*[\"”秒s]?"), "voice"),
    (re.compile(r"\[语音(?:通话|聊天)\]"), "call_voice"),
    (re.compile(r"\[视频通话\]|\[视频聊天\]"), "call_video"),
    (re.compile(r"\[语音消息[^\]]*\]"), "voice"),
    (re.compile(r"\[语音\]"), "voice"),
    (re.compile(r"\[图片\]|\[照片\]"), "image"),
    (re.compile(r"\[视频\]"), "video"),
    (re.compile(r"\[动画表情\]|\[表情\]|\[表情包\]|\[贴图\]"), "sticker"),
    (re.compile(r"\[转账[^\]]*\]|\[红包[^\]]*\]|\[微信红包\]|\[微信转账\]"), "transfer"),
    (re.compile(r"\[链接\]|\[分享\]|\[文章\]|\[公众号\]|\[小程序\]"), "link"),
    (re.compile(r"撤回了一条消息"), "recall"),
    (re.compile(r"\[位置\]"), "location"),
    (re.compile(r"\[文件\]"), "file"),
]
CALL_DUR = re.compile(r"(?:通话时长|时长)\s*(?:(\d+):)?(\d+):(\d+)")

# 微信原生类型码（留痕 CSV 的 Type 列、WeFlow JSON 的 localType）
WX_TYPE = {"1": "text", "3": "image", "34": "voice", "43": "video", "47": "sticker", "49": "link", "50": "call_voice",
           "10000": "system", "48": "location"}

FORMAT_CN = {"native": "本项目的 messages.json", "weflow-json": "WeFlow 详细 JSON", "weflow-txt": "WeFlow TXT",
             "weclone-csv": "WeFlow weclone CSV", "memotrace-csv": "留痕 / WeChatMsg CSV", "csv": "通用 CSV",
             "json": "通用 JSON", "txt": "文本"}


def norm_ts(s):
    """各种写法的时间 → ISO；认不出来返回 None（stats.py 会当无时间戳处理，不会崩）"""
    try:
        s = s.strip()
        if s.endswith("Z") or re.search(r"[+-]\d{2}:\d{2}$", s):
            # WeFlow weclone CSV 的 CreateTime 是 UTC ISO-8601，转回本地时间
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%dT%H:%M:%S")
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
# meta 记录识别结果（format / version / encoding / columns），进 messages.json 的 source_detail 和 --peek。

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
            t = epoch_to_local(t) or t          # Unix 秒或毫秒；认不出来留原样，norm_ts 会给 None
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
        rows.append((norm_ts(t) if t else None, who, body, typ, None))
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
    items = data["messages"] if isinstance(data, dict) and "messages" in data else data
    if isinstance(items, dict):
        items = items.get("data") or items.get("list") or []
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        t = pick(it, "ts", "time", "timestamp", "createTime", "create_time", "CreateTime", "StrTime", "datetime", "date", "formattedTime")
        if isinstance(t, (int, float)) or (isinstance(t, str) and t.isdigit()):
            t = epoch_to_local(t)
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
        rows.append((norm_ts(str(t)) if t else None, str(who), str(body), typ, dur))
    return "rows", rows


def looks_like_csv(text):
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    if first.count(",") < 2:
        return False
    return not (HEADER_PATTERN.match(first) or any(p.match(first) for p in LINE_PATTERNS))


def load_any(path):
    """读文件并识别格式 → (kind, payload, meta)。kind 是 "native"（payload 是 messages.json 的 dict）或 "rows"。
    先看内容再看扩展名：.txt 里装着 JSON 也认。"""
    text, enc = read_text(path)
    meta = {"format": None, "version": None, "encoding": enc, "columns": None}
    ext = os.path.splitext(path)[1].lower()
    head = text.lstrip()[:1]
    if ext == ".json" or head in ("{", "["):
        try:
            data = json.loads(text)
        except ValueError as e:
            if ext == ".json":
                print(f"✗ 不是合法的 JSON：{e}")
                sys.exit(1)
            data = None
        if data is not None:
            kind, payload = parse_json(data, meta)
            return kind, payload, meta
    if ext == ".csv" or looks_like_csv(text):
        return "rows", parse_csv(text, meta), meta
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


def build(rows, her, me, pronoun, detail=None):
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
            "source": "export", "source_detail": detail or "unknown", "messages": msgs}


def peek(path):
    """把文件读一遍，打印识别结果和前 10 条。不写任何文件。"""
    kind, payload, meta = load_any(path)
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
    ap.add_argument("path", help="导出文件（json / csv / txt）")
    ap.add_argument("--her", default=None, help="对方在记录里的名字/备注")
    ap.add_argument("--me", default=None, help="你在记录里的名字（CSV/JSON 有 IsSender 时不用填）")
    ap.add_argument("--pronoun", default=None, help="她 / 他，默认 她")
    ap.add_argument("--call", default=None, help="报告里怎么称呼对方（妈妈 / 老爸 / 外婆），默认同 --her")
    ap.add_argument("--out", default="messages.json")
    ap.add_argument("--since", default=None, help="只要这天及以后的（YYYY-MM-DD）")
    ap.add_argument("--until", default=None, help="只要这天及以前的（YYYY-MM-DD）")
    ap.add_argument("--last-days", type=int, default=None, help="只要最后一条消息往前 N 天（跨好几年的全量导出用这个）")
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
    if a.pronoun and a.pronoun not in ("她", "他"):
        print(f"--pronoun 只能是 她 或 他，现在是 {a.pronoun!r}")
        sys.exit(1)

    if a.peek:
        peek(a.path)
        return
    kind, payload, meta = load_any(a.path)
    detail = source_detail(meta)
    if kind == "native":
        if a.call:
            payload["her"] = a.call
        if a.pronoun:
            payload["her_pronoun"] = a.pronoun
        payload.setdefault("schema", SCHEMA_VERSION)
        payload.setdefault("source_detail", detail)
        payload["messages"], dropped, s0, s1 = clip(payload["messages"], a.since, a.until, a.last_days)
        if not payload["messages"]:
            print(f"这段时间（{s0 or '最早'} → {s1 or '最后'}）里没有消息，换个范围试试。" if dropped else "文件里没有消息。")
            sys.exit(1)
        dump_json(payload, a.out)
        print(f"已经是 messages.json 格式，写到 {a.out}（{len(payload['messages'])} 条）"
              + (f"，按 {s0 or '最早'} → {s1 or '最后'} 切掉了 {dropped} 条" if dropped else ""))
        return

    rows = payload
    senders = Counter(r[1] for r in rows)
    has_flag = "__me__" in senders or "__her__" in senders
    if not has_flag and not a.her:
        print(f"识别为：{format_label(meta)}，编码 {meta['encoding']}。记录里出现的名字（按条数）：")
        for who, n in senders.most_common(6):
            print(f"  {who}  {n} 条")
        print("\n请用 --her 指定对方的名字，例如：--her 妈妈 ；如果你的名字不是“我”，再加 --me 你的名字")
        sys.exit(1)
    if not has_flag and a.her not in senders:
        # 名字写错时别悄悄把所有消息都算成"我"
        print(f"记录里没有叫“{a.her}”的发送者。出现的名字（按条数）：" + "、".join(f"{w}({n})" for w, n in senders.most_common(6)))
        print("--her 要和记录里显示的一模一样（含备注、空格）；用 --peek 看它读到了什么。")
        sys.exit(1)
    if has_flag:
        # 文件自带我方标记；对方可能有名字也可能是 __her__，统一归到 __her__
        flagged = [(ts, ("__me__" if who == "__me__" else "__her__"), body, typ, dur) for ts, who, body, typ, dur in rows]
        data = build(flagged, "__her__", "__me__", a.pronoun, detail)
        data["her"] = a.her or "妈妈"
        data["me"] = a.me or "我"
    else:
        me = a.me or next((w for w, _ in senders.most_common() if w != a.her), None)   # 除了她之外条数最多的当作我
        data = build(rows, a.her, me, a.pronoun, detail)
    if a.call:
        data["her"] = a.call        # 记录里叫“李秀兰”，报告里叫“妈妈”
    data["messages"], dropped, s0, s1 = clip(data["messages"], a.since, a.until, a.last_days)
    n = len(data["messages"])
    if dropped and n == 0:
        print(f"这段时间（{s0 or '最早'} → {s1 or '最后'}）里没有消息，换个范围试试。")
        sys.exit(1)
    if n == 0:
        print(f"识别为：{format_label(meta)}，编码 {meta['encoding']}，但没解析出任何消息。"
              "检查 --her 的名字是不是和记录里一模一样（包括空格和备注）；用 --peek 看它读到了什么。")
        sys.exit(1)
    dump_json(data, a.out)
    c = Counter(m["sender"] for m in data["messages"])
    t = Counter(m["type"] for m in data["messages"])
    print(f"解析完成：{n} 条 → {a.out}（{format_label(meta)}，{meta['encoding']}）"
          + (f"，按 {s0 or '最早'} → {s1 or '最后'} 切掉了 {dropped} 条" if dropped else ""))
    if meta.get("her_name") and not (a.her or a.call):
        print(f"  记录里对方显示为“{meta['her_name']}”，报告里默认称呼“{data['her']}”，想改用 --call")
    print(f"  {data['her']} {c['her']} 条 / {data['me']} {c['me']} 条")
    print("  类型：" + " · ".join(f"{k} {v}" for k, v in t.most_common()))
    print("  无时间戳：" + str(sum(1 for m in data['messages'] if not m['ts'])))


if __name__ == "__main__":
    main()
