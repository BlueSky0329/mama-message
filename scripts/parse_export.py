#!/usr/bin/env python3
"""
把各种导出格式统一成 messages.json（SKILL.md「工作表」格式）。

支持：
  .txt   微信/QQ 导出的文本（两行式、单行式、带方括号时间等常见写法）
  .csv   留痕 / WeChatMsg 导出的 CSV（IsSender / StrContent / StrTime / Type 列）
  .json  留痕、她不一样(she-love-me)、或任意 [{time, sender, content}] 形式的 JSON

用法:
  python scripts/parse_export.py 导出文件 --her 妈妈 [--call 妈妈] [--me 我] [--pronoun 她] [--out messages.json]

--her  填对方在记录里显示的名字（或备注）。不填会先列出记录里出现的名字让你选。
--call 报告里怎么称呼对方；记录里是真名时用它，默认同 --her。
只用标准库。
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime

# Windows 默认控制台是 GBK，打不出 emoji；统一把输出切到 UTF-8（其他平台无影响）
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

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
    (re.compile(r"\[语音\]"), "voice"),
    (re.compile(r"\[图片\]|\[照片\]"), "image"),
    (re.compile(r"\[视频\]"), "video"),
    (re.compile(r"\[动画表情\]|\[表情\]|\[表情包\]|\[贴图\]"), "sticker"),
    (re.compile(r"\[转账\]|\[红包\]|\[微信红包\]|\[微信转账\]"), "transfer"),
    (re.compile(r"\[链接\]|\[分享\]|\[文章\]|\[公众号\]|\[小程序\]"), "link"),
    (re.compile(r"撤回了一条消息"), "recall"),
    (re.compile(r"\[位置\]"), "location"),
    (re.compile(r"\[文件\]"), "file"),
]
CALL_DUR = re.compile(r"(?:通话时长|时长)\s*(?:(\d+):)?(\d+):(\d+)")


def norm_ts(s):
    """各种写法的时间 → ISO；认不出来返回 None（stats.py 会当无时间戳处理，不会崩）"""
    try:
        s = s.replace("/", "-").replace("T", " ").strip()
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
            content = body if typ in ("link", "transfer", "recall") else ""
            if typ == "link":
                content = re.sub(r"\[[^\]]*\]", "", body).strip() or body
            return typ, content, dur
    if re.fullmatch(r"(\[[^\]]{1,6}\]\s*)+", body):     # 只有内置表情
        return "sticker", body, None
    return "text", body, None


# ---------- txt ----------

def parse_txt(path):
    rows = []
    lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
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
                rows.append((norm_ts(m.group(1)), m.group("who").strip(), m.group("body")))
                matched = True
                break
        if matched:
            i += 1
            continue
        m = HEADER_PATTERN.match(line)
        if m:
            body = []
            j = i + 1
            while j < len(lines) and not HEADER_PATTERN.match(lines[j].strip()) and not any(p.match(lines[j].strip()) for p in LINE_PATTERNS):
                if lines[j].strip():
                    body.append(lines[j].strip())
                j += 1
            rows.append((norm_ts(m.group(1)), m.group("who").strip(), "\n".join(body)))
            i = j
            continue
        # 既不是头也不是消息行：挂到上一条
        if rows:
            ts, who, body = rows[-1]
            rows[-1] = (ts, who, (body + "\n" + line).strip())
        i += 1
    return rows


# ---------- csv（留痕 / WeChatMsg） ----------

CSV_TYPE = {"1": "text", "3": "image", "34": "voice", "43": "video", "47": "sticker", "49": "link", "50": "call_voice",
            "10000": "system", "48": "location"}


def parse_csv(path):
    rows = []
    with open(path, encoding="utf-8-sig", errors="ignore", newline="") as f:
        r = csv.DictReader(f)
        cols = {c.lower(): c for c in r.fieldnames or []}
        def col(*names):
            for n in names:
                if n.lower() in cols:
                    return cols[n.lower()]
            return None
        c_time = col("StrTime", "CreateTime", "time", "timestamp", "ts")
        c_content = col("StrContent", "content", "msg", "text", "message")
        c_sender = col("IsSender", "is_sender", "sender", "from", "Sender")
        c_type = col("Type", "type", "msg_type")
        c_sub = col("SubType", "sub_type")
        c_nick = col("NickName", "Remark", "nickname", "name")
        for row in r:
            t = row.get(c_time, "") if c_time else ""
            if t.isdigit():
                t = datetime.fromtimestamp(int(t)).strftime("%Y-%m-%d %H:%M:%S")
            who = row.get(c_sender, "") if c_sender else ""
            if who in ("1", "0", "True", "False", "true", "false"):
                who = "__me__" if who in ("1", "True", "true") else (row.get(c_nick) if c_nick else "__her__") or "__her__"
            body = row.get(c_content, "") if c_content else ""
            typ = CSV_TYPE.get(str(row.get(c_type, "")).strip(), None) if c_type else None
            if typ == "link" and c_sub and str(row.get(c_sub, "")).strip() in ("2000", "2001"):
                typ = "transfer"
            if typ == "system":
                if "撤回" in body:
                    typ = "recall"
                else:
                    continue
            rows.append((norm_ts(t) if t else None, who, body, typ))
    return rows


# ---------- json ----------

def pick(d, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def parse_json(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict) and "messages" in data and data["messages"] and isinstance(data["messages"][0], dict) \
            and data["messages"][0].get("sender") in ("her", "me"):
        return "native", data
    items = data["messages"] if isinstance(data, dict) and "messages" in data else data
    if isinstance(items, dict):
        items = items.get("data") or items.get("list") or []
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        t = pick(it, "ts", "time", "timestamp", "create_time", "CreateTime", "StrTime", "datetime", "date")
        if isinstance(t, (int, float)) or (isinstance(t, str) and t.isdigit()):
            t = datetime.fromtimestamp(int(t) if int(t) < 1e11 else int(t) / 1000).strftime("%Y-%m-%d %H:%M:%S")
        who = pick(it, "sender", "from", "talker", "nickname", "name", "who", "role", "speaker")
        is_sender = pick(it, "is_sender", "isSender", "IsSender", "is_me", "self")
        if is_sender is not None:
            who = "__me__" if str(is_sender) in ("1", "True", "true") else (who or "__her__")
        body = pick(it, "content", "text", "msg", "message", "StrContent", "body") or ""
        typ = pick(it, "type", "msg_type", "kind")
        if isinstance(typ, int) or (isinstance(typ, str) and typ.isdigit()):
            typ = CSV_TYPE.get(str(typ))
        dur = pick(it, "dur", "duration", "seconds")
        rows.append((norm_ts(str(t)) if t else None, str(who), str(body), typ, dur))
    return "generic", rows


# ---------- 主流程 ----------

def build(rows, her, me, pronoun):
    msgs = []
    senders = Counter(r[1] for r in rows)
    for r in rows:
        ts, who, body = r[0], r[1], r[2]
        typ = r[3] if len(r) > 3 else None
        dur = r[4] if len(r) > 4 else None
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
            content = body if typ in ("text", "link", "transfer", "recall") else ""
        msgs.append({"ts": ts, "sender": side, "type": typ, "content": content, "dur": dur})
    return {"me": me or "我", "her": her or "妈妈", "her_pronoun": pronoun, "source": "export", "messages": msgs}, senders


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--her", default=None, help="对方在记录里的名字/备注")
    ap.add_argument("--me", default=None, help="你在记录里的名字（CSV/JSON 有 IsSender 时不用填）")
    ap.add_argument("--pronoun", default="她")
    ap.add_argument("--call", default=None, help="报告里怎么称呼对方（妈妈 / 老爸 / 外婆），默认同 --her")
    ap.add_argument("--out", default="messages.json")
    a = ap.parse_args()

    p = a.path.lower()
    if p.endswith(".json"):
        kind, payload = parse_json(a.path)
        if kind == "native":
            if a.call:
                payload["her"] = a.call
            json.dump(payload, open(a.out, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
            print(f"已经是 messages.json 格式，原样写到 {a.out}（{len(payload['messages'])} 条）")
            return
        rows = payload
    elif p.endswith(".csv"):
        rows = parse_csv(a.path)
    else:
        rows = parse_txt(a.path)

    senders = Counter(r[1] for r in rows)
    has_flag = "__me__" in senders or "__her__" in senders
    if not has_flag and not a.her:
        print("记录里出现的名字（按条数）：")
        for who, n in senders.most_common(6):
            print(f"  {who}  {n} 条")
        print("\n请用 --her 指定对方的名字，例如：--her 妈妈 ；如果你的名字不是“我”，再加 --me 你的名字")
        sys.exit(1)
    me = a.me
    if not has_flag and not me:
        # 除了 her 之外条数最多的当作我
        me = next((w for w, _ in senders.most_common() if w != a.her), None)
    her = a.her or "__her__"
    if has_flag:
        # CSV/JSON 已标记我方；对方可能有名字也可能是 __her__
        data, _ = build([(r[0], ("__me__" if r[1] == "__me__" else "__her__"), *r[2:]) for r in rows], "__her__", "__me__", a.pronoun)
        data["her"] = a.her or "妈妈"; data["me"] = a.me or "我"
    else:
        data, _ = build(rows, her, me, a.pronoun)
    if a.call:
        data["her"] = a.call        # 记录里叫“李秀兰”，报告里叫“妈妈”
    n = len(data["messages"])
    if n == 0:
        print("没解析出任何消息。检查 --her 的名字是不是和记录里一模一样（包括空格和备注）。")
        sys.exit(1)
    json.dump(data, open(a.out, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    c = Counter(m["sender"] for m in data["messages"])
    t = Counter(m["type"] for m in data["messages"])
    print(f"解析完成：{n} 条 → {a.out}")
    print(f"  {data['her']} {c['her']} 条 / {data['me']} {c['me']} 条")
    print("  类型：" + " · ".join(f"{k} {v}" for k, v in t.most_common()))
    print("  无时间戳：" + str(sum(1 for m in data['messages'] if not m['ts'])))


if __name__ == "__main__":
    main()
