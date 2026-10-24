#!/usr/bin/env python3
"""
直接从本机的微信服务读聊天记录 → messages.json，不用手动导出。

现在认的服务：Alpha（WeFlow 的本地服务版）。它在本机 127.0.0.1:5031 开了一个只读的 MCP 接口，
读的是这台电脑上已登录微信的数据库。这个脚本只做三件事：按名字找会话、按页把消息读下来、转成 messages.json。
  · 只连本机（127.0.0.1 / localhost），不走代理，地址写成别的直接拒绝
  · 只调读取类工具；发消息、导出文件这类工具在代码里就调不了
  · 解密数据库是 Alpha 的事，这里不碰数据库，也不保存令牌
聊天内容由脚本在本地读、本地算，不经过写文字的 AI——AI 只读后面生成的 brief.md。

用法:
  python scripts/wechat_live.py find 妈                          # 列出名字里带"妈"的私聊
  python scripts/wechat_live.py pull 妈 --call 妈妈 --last-days 365 --out messages.json
  python scripts/wechat_live.py pull --id wxid_xxx --call 妈妈    # 同名的有好几个时用 id
  python scripts/mama.py run --wechat 妈 --call 妈妈 --last-days 365   # 一条命令跑到素材包

令牌：Alpha 里「HTTP API」页面上的那串。按顺序找 --token、环境变量 MAMA_ALPHA_TOKEN / ALPHA_TOKEN / PDB_ALPHA_TOKEN
（Windows 上环境变量刚设、终端还没重开也能读到）。地址默认 http://127.0.0.1:5031/mcp，换端口用 --endpoint 或 MAMA_ALPHA_URL。
只用标准库。
"""
import argparse
import itertools
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta

from _common import dump_json, epoch_to_local, parse_tz, setup_utf8, tz_label
from parse_export import ParseError, build, clip, norm_ts

setup_utf8()

ENDPOINT = "http://127.0.0.1:5031/mcp"
TOKEN_ENVS = ("MAMA_ALPHA_TOKEN", "ALPHA_TOKEN", "PDB_ALPHA_TOKEN")
# 白名单：只有这几个能调。wechat.chat.send_text（替你发消息）和 alpha.exports.start（往磁盘写文件）不在里面
READ_TOOLS = {"wechat.core.list_accounts", "wechat.chat.resolve_session", "wechat.chat.list_sessions",
              "wechat.chat.get_messages"}
PAGE = 200

# Alpha 的消息类型（中文）→ messages.json 的 type；None = 跳过
ALPHA_TYPE = {"引用": "text", "表情": "sticker", "动画表情": "sticker", "图片": "image", "视频": "video", "语音": "voice",
              "通话": "call_voice", "语音通话": "call_voice", "视频通话": "call_video", "转账": "transfer", "红包": "transfer",
              "链接": "link", "视频号": "link", "应用消息": "link", "小程序": "link", "公众号": "link", "聊天记录": "link",
              "位置": "location", "文件": "file", "系统消息": None, "拍一拍": None}
VOICE_DUR = re.compile(r"\[语音\s*(\d+)\s*秒\]")
CALL_DUR = re.compile(r"Duration:\s*(?:(\d+):)?(\d+):(\d+)|时长\s*(?:(\d+):)?(\d+):(\d+)")
CALL_MISSED = re.compile(r"cancel|wasn.t answered|not answered|declined|busy|已取消|未接|对方已拒绝|忙线", re.I)


class Alpha:
    """本机 Alpha 的只读客户端（JSON-RPC over HTTP，回包可能是 SSE 的 data: 行）。"""

    def __init__(self, endpoint=None, token=None, timeout=120):
        self.endpoint = endpoint or os.environ.get("MAMA_ALPHA_URL") or ENDPOINT
        host = urllib.parse.urlparse(self.endpoint).hostname or ""
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ParseError(f"只连本机的服务，{self.endpoint} 不是本机地址。聊天记录不能经过别人的服务器。")
        self.token = token or find_token()
        self.timeout = timeout
        self._ids = itertools.count(1)
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 本机服务，别让系统代理截走

    def rpc(self, method, params=None, timeout=None):
        body = json.dumps({"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or {}}).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=body, headers={
            "Authorization": "Bearer " + self.token, "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"})
        try:
            with self._opener.open(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            e.close()
            if e.code in (401, 403):
                raise ParseError("Alpha 拒绝了令牌（401）。到 Alpha 的「HTTP API」页面复制令牌，"
                                 "设成环境变量 MAMA_ALPHA_TOKEN，或者用 --token 传进来（不要带尖括号）。")
            raise ParseError(f"Alpha 返回 HTTP {e.code}：{e.reason}")
        except (urllib.error.URLError, OSError) as e:
            raise ParseError(f"连不上 {self.endpoint}（{getattr(e, 'reason', e)}）。Alpha 开着吗？「HTTP API」打开了吗？"
                             "没有 Alpha 的话，按 references/export-guide.md 用 WeFlow 导出文件，或者截图。")
        if raw.lstrip().startswith(("event:", "data:")):
            raw = next((line[5:].strip() for line in raw.splitlines() if line.startswith("data:")), "{}")
        data = json.loads(raw)
        if "error" in data:
            raise ParseError(f"Alpha {method} 出错：{data['error'].get('message', data['error'])}")
        return data.get("result", {})

    def call(self, tool, **arguments):
        if tool not in READ_TOOLS:
            raise PermissionError(f"wechat_live 只读，不调用 {tool}")
        result = self.rpc("tools/call", {"name": tool, "arguments": arguments}, timeout=600)
        data = result.get("structuredContent")
        if data is None:
            text = "".join(p.get("text", "") for p in result.get("content", []) if p.get("type") == "text")
            try:
                data = json.loads(text)
            except ValueError:
                raise ParseError(f"Alpha {tool} 的回复不是 JSON：{text[:120]}")
        if isinstance(data, dict) and data.get("status") == "error":
            raise ParseError(f"Alpha {tool} 出错：{data.get('code')} {data.get('detail', '')}".strip())
        return data


def find_token(explicit=None):
    if explicit:
        return explicit.strip().strip("<>")
    for name in TOKEN_ENVS:
        if os.environ.get(name):
            return os.environ[name].strip().strip("<>")
    if os.name == "nt":
        # 用户级环境变量刚设好时，已经开着的终端里还读不到，直接去注册表读
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                for name in TOKEN_ENVS:
                    try:
                        v = winreg.QueryValueEx(key, name)[0]
                    except OSError:
                        continue
                    if v:
                        return str(v).strip().strip("<>")
        except OSError:
            pass
    raise ParseError("缺少 Alpha 的令牌。到 Alpha 的「HTTP API」页面复制令牌，设成环境变量 MAMA_ALPHA_TOKEN，"
                     "或者用 --token 传进来。")


def find(client, query):
    """名字（备注 / 昵称里带这几个字）→ 私聊候选 [{id, name, last}]，按最后活跃时间排。群聊、公众号不要。"""
    r = client.call("wechat.chat.resolve_session", query=query)
    out = []
    for c in r.get("items") or []:
        sid = c.get("id") or ""
        if c.get("kind") != 1 or sid.startswith(("gh_", "@")) or sid.endswith("@chatroom"):
            continue
        last = epoch_to_local(c.get("last_activity_unix_ms")) if c.get("last_activity_unix_ms") else None
        out.append({"id": sid, "name": c.get("display_name") or sid, "last": last})
    out.sort(key=lambda c: c["last"] or "", reverse=True)
    return out


def pick(cands, query):
    """唯一候选、或名字和 query 一字不差的唯一一个 → 它；否则 None（让人选）。"""
    if len(cands) == 1:
        return cands[0]
    exact = [c for c in cands if c["name"] == query]
    return exact[0] if len(exact) == 1 else None


def pull(client, username, after_ms=None, before_ms=None, progress=None):
    """按时间顺序读完一个会话。after / before 是不含边界的 Unix 毫秒。"""
    items, cursor = [], None
    while True:
        args = {"username": username, "limit": PAGE, "order": "asc", "defer_media": True,
                "after_unix_ms": str(after_ms if after_ms is not None else -1)}
        if before_ms is not None:
            args["before_unix_ms"] = str(before_ms)
        if cursor:
            args["cursor"] = cursor
        page = client.call("wechat.chat.get_messages", **args)
        got = page.get("items") or []
        items += got
        if progress:
            progress(len(items))
        cursor = page.get("nextCursor")
        if not got or not cursor or page.get("hasMore") is False:
            return items


def to_rows(items, tzinfo=None):
    """Alpha 的消息 → parse_export 的 rows (ts, who, body, type, dur)，外加跳过了什么的计数。"""
    rows, skipped = [], Counter()
    for it in items:
        label = it.get("type")
        text = it.get("text") or ""
        if label is None:
            typ = None                       # 普通文字；[Smile] 这种内置表情交给 classify 判
        elif label in ALPHA_TYPE:
            typ = ALPHA_TYPE[label]
            if typ is None:
                skipped[label] += 1
                continue
        else:
            typ = "other"
        dur = None
        if typ == "voice":
            m = VOICE_DUR.search(text)
            dur = int(m.group(1)) if m else None
        elif typ == "call_voice":
            if CALL_MISSED.search(text):
                skipped["没接通的通话"] += 1
                continue
            m = CALL_DUR.search(text)
            if m:
                h, mi, se = (m.group(1), m.group(2), m.group(3)) if m.group(2) else (m.group(4), m.group(5), m.group(6))
                dur = int(h or 0) * 3600 + int(mi) * 60 + int(se)
        if typ == "link":
            text = re.sub(r"^\[[^\]]*\]\s*", "", text).strip(" —") or label
        elif typ not in (None, "text"):
            text = ""                         # 图片 / 转账 / 通话这类不留原文（转账原文里有金额）
        ts = norm_ts(epoch_to_local(it.get("sent_at_unix_ms"), tzinfo) or "") if it.get("sent_at_unix_ms") else None
        rows.append((ts, "__me__" if it.get("from_me") else "__her__", text, typ, dur))
    return rows, skipped


def fetch(query=None, username=None, call=None, me=None, pronoun=None, since=None, until=None, last_days=None, tz=None,
          endpoint=None, token=None, client=None, progress=None):
    """读本机微信的一个私聊 → (messages.json 的 dict, 给人看的几行摘要)。出错抛 ParseError（人话）。"""
    if pronoun and pronoun not in ("她", "他"):
        raise ParseError(f"--pronoun 只能是 她 或 他，现在是 {pronoun!r}")
    try:
        tzinfo = parse_tz(tz)
    except ValueError as e:
        raise ParseError(f"--tz：{e}")
    client = client or Alpha(endpoint, token)
    name = None
    if not username:
        if not query:
            raise ParseError("要么给名字（她在你微信里的备注，比如 妈），要么给 --id")
        cands = find(client, query)
        if not cands:
            raise ParseError(f"微信里没找到名字带“{query}”的私聊。换成她在你微信里的备注试试（python scripts/wechat_live.py find 关键字）。")
        hit = pick(cands, query)
        if not hit:
            lines = "\n".join(f"  {c['name']}  --id {c['id']}  最后聊天 {c['last'] or '—'}" for c in cands[:8])
            raise ParseError(f"名字带“{query}”的私聊有 {len(cands)} 个：\n{lines}\n用 --id 指定是哪一个。")
        username, name = hit["id"], hit["name"]

    # since / until 先在服务端截掉，读得少；last_days 相对最后一条算，要读完再切
    def ms(d, end=False):
        dt = datetime.combine(date.fromisoformat(d) + timedelta(days=1 if end else 0), datetime.min.time())
        return int((dt.replace(tzinfo=tzinfo) if tzinfo else dt.astimezone()).timestamp() * 1000)
    try:
        after = ms(since) - 1 if since else None
        before = ms(until, end=True) if until else None
    except ValueError:
        raise ParseError("--since / --until 要写成 2026-01-01 这样的日期")
    items = pull(client, username, after, before, progress)
    rows, skipped = to_rows(items, tzinfo)
    detail = f"alpha-live {username}"
    data = build(rows, "__her__", "__me__", pronoun, detail, "wechat-live")
    data["her"] = call or name or query or "妈妈"
    data["me"] = me or "我"
    data["tz"] = tz_label(tzinfo)
    data["messages"], dropped, s0, s1 = clip(data["messages"], since, until, last_days)
    n = len(data["messages"])
    if n == 0:
        raise ParseError("这个会话里没读到消息" + (f"（{s0 or '最早'} → {s1 or '最后'}）" if (since or until or last_days) else "") + "。")
    c = Counter(m["sender"] for m in data["messages"])
    t = Counter(m["type"] for m in data["messages"])
    report = [f"从本机微信读了 {len(items)} 条（{name or username}，时区 {data['tz']}），保留 {n} 条"
              + (f"，按 {s0 or '最早'} → {s1 or '最后'} 切掉 {dropped} 条" if dropped else "")]
    if skipped:
        report.append("  跳过：" + " · ".join(f"{k} {v}" for k, v in skipped.most_common()))
    report.append(f"  {data['her']} {c['her']} 条 / {data['me']} {c['me']} 条")
    report.append("  类型：" + " · ".join(f"{k} {v}" for k, v in t.most_common()))
    if not call and name:
        report.append(f"  报告里称呼“{data['her']}”（她在你微信里的备注），想改用 --call 妈妈")
    return data, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find", help="按名字找私聊")
    f.add_argument("query")
    p = sub.add_parser("pull", help="读一个私聊 → messages.json")
    p.add_argument("query", nargs="?", default=None, help="她在你微信里的备注 / 昵称")
    p.add_argument("--id", default=None, help="会话 id（wxid_…），同名的有好几个时用")
    p.add_argument("--call", default=None, help="报告里怎么称呼她（默认用微信备注）")
    p.add_argument("--me", default=None)
    p.add_argument("--pronoun", default=None, help="她 / 他")
    p.add_argument("--since", default=None)
    p.add_argument("--until", default=None)
    p.add_argument("--last-days", type=int, default=None)
    p.add_argument("--tz", default=None)
    p.add_argument("--out", default="messages.json")
    for x in (f, p):
        x.add_argument("--endpoint", default=None, help=f"默认 {ENDPOINT}")
        x.add_argument("--token", default=None, help="不给就读环境变量 " + " / ".join(TOKEN_ENVS))
    a = ap.parse_args()
    try:
        if a.cmd == "find":
            cands = find(Alpha(a.endpoint, a.token), a.query)
            if not cands:
                print(f"没找到名字带“{a.query}”的私聊")
            for c in cands:
                print(f"{c['name']}  --id {c['id']}  最后聊天 {c['last'] or '—'}")
            return
        data, report = fetch(a.query, a.id, call=a.call, me=a.me, pronoun=a.pronoun, since=a.since, until=a.until,
                             last_days=a.last_days, tz=a.tz, endpoint=a.endpoint, token=a.token,
                             progress=lambda k: print(f"\r  已读 {k} 条", end="", file=sys.stderr, flush=True))
        print(file=sys.stderr)
    except ParseError as e:
        print(str(e))
        sys.exit(1)
    dump_json(data, a.out)
    print(report[0] + f" → {a.out}")
    for line in report[1:]:
        print(line)


if __name__ == "__main__":
    main()
