# -*- coding: utf-8 -*-
"""
wechat_live.py：直接读本机微信（Alpha 的只读 MCP 接口）。测试里起一个假的 Alpha（127.0.0.1 随机端口），
走真的 HTTP / SSE / 分页；不碰真实的微信。只用标准库。
"""
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from helpers import load, run

import parse_export   # noqa: E402
import wechat_live    # noqa: E402

TOKEN = "test-token"
MOM = "wxid_mom"
SESSIONS = [
    {"id": MOM, "display_name": "妈", "kind": 1, "last_activity_unix_ms": 1792840197000},
    {"id": "wxid_aunt", "display_name": "舅妈", "kind": 1, "last_activity_unix_ms": 1776320034000},
    {"id": "123@chatroom", "display_name": "相亲相爱一家人（妈也在）", "kind": 2, "last_activity_unix_ms": 1792840197000},
]
T0 = 1777600800000   # 2026-05-01 10:00 +08:00


def item(k, from_me, text, type_=None, minutes=0):
    it = {"id": str(k), "server_id": str(k), "sent_at_unix_ms": str(T0 + minutes * 60000), "text": text,
          "sender": "我" if from_me else "妈", "sender_id": "me" if from_me else MOM}
    if from_me:
        it["from_me"] = True
    if type_:
        it["type"] = type_
    return it


MESSAGES = [
    item(1, False, "吃饭了吗", minutes=0),
    item(2, True, "吃了", minutes=1),
    item(3, False, "[语音 23秒]", "语音", 2),
    item(4, False, "[转账] ￥200.00 妈妈转账给你 收款200.00元。", "转账", 3),
    item(5, False, "[通话] Duration: 03:25", "通话", 60),
    item(6, False, "[通话] Call canceled by caller", "通话", 120),
    item(7, False, "[视频号] 久坐伤腰 三个动作缓解", "视频号", 180),
    item(8, False, "[表情]", "表情", 181),
    item(9, False, "You recalled a message", "系统消息", 182),
    item(10, True, "好的", "引用", 183),
    item(11, False, "[Smile]", None, 184),
]


class FakeAlpha(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, format, *args):  # noqa: A002  安静点
        pass

    def do_POST(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            self.send_response(401)
            self.end_headers()
            return
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        name, args = req["params"].get("name"), req["params"].get("arguments", {})
        FakeAlpha.calls.append(name)
        if name == "wechat.chat.resolve_session":
            data = {"status": "ok", "items": [s for s in SESSIONS if args["query"] in s["display_name"]]}
        elif name == "wechat.chat.get_messages":
            start = int(args.get("cursor") or 0)
            page = [m for m in MESSAGES if int(m["sent_at_unix_ms"]) > int(args.get("after_unix_ms", "-1"))][start:start + 4]
            more = start + 4 < len(MESSAGES)
            data = {"status": "ok", "items": page, "hasMore": more, "nextCursor": str(start + 4) if more else None}
        else:
            data = {"status": "error", "code": "UNKNOWN_TOOL"}
        body = {"jsonrpc": "2.0", "id": req["id"], "result": {"structuredContent": data}}
        # 一半回 SSE（data: 行），一半回纯 JSON，两种都要认
        raw = json.dumps(body, ensure_ascii=False)
        out = ("event: message\ndata: " + raw + "\n\n") if len(FakeAlpha.calls) % 2 else raw
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if len(FakeAlpha.calls) % 2 else "application/json")
        self.end_headers()
        self.wfile.write(out.encode("utf-8"))


class WechatLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeAlpha)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/mcp"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def client(self):
        return wechat_live.Alpha(self.url, TOKEN)

    def test_types_and_privacy(self):
        data, report = wechat_live.fetch("妈", client=self.client(), call="妈妈", tz="+08:00")
        ms = data["messages"]
        self.assertEqual([m["type"] for m in ms],
                         ["text", "text", "voice", "transfer", "call_voice", "link", "sticker", "text", "sticker"])
        self.assertEqual(ms[2]["dur"], 23)
        self.assertEqual(ms[4]["dur"], 205)
        self.assertEqual(ms[3]["content"], "转账")                       # 金额不落地
        self.assertNotIn("200", json.dumps(data, ensure_ascii=False))
        self.assertEqual(ms[5]["content"], "久坐伤腰 三个动作缓解")
        self.assertEqual([m["sender"] for m in ms[:2]], ["her", "me"])
        self.assertEqual(ms[0]["ts"], "2026-05-01T10:00:00")
        self.assertEqual((data["her"], data["tz"], data["source"]), ("妈妈", "+08:00", "wechat-live"))
        self.assertIn("没接通的通话 1", report[1])
        self.assertIn("系统消息 1", report[1])

    def test_pick_session(self):
        # “妈”和“舅妈”都带“妈”：一字不差的那个胜出；群聊不进候选
        cands = wechat_live.find(self.client(), "妈")
        self.assertEqual([c["id"] for c in cands], [MOM, "wxid_aunt"])
        self.assertEqual(wechat_live.pick(cands, "妈")["id"], MOM)
        self.assertIsNone(wechat_live.pick(cands, "舅"))               # 两个候选、没有一字不差的 → 让人选
        self.assertEqual(wechat_live.fetch("舅妈", client=self.client())[0]["her"], "舅妈")
        SESSIONS.append({"id": "wxid_mom2", "display_name": "妈", "kind": 1, "last_activity_unix_ms": 1})
        try:
            with self.assertRaises(parse_export.ParseError) as e:
                wechat_live.fetch("妈", client=self.client())
            self.assertIn("--id", str(e.exception))
        finally:
            SESSIONS.pop()
        with self.assertRaises(parse_export.ParseError):
            wechat_live.fetch("外婆", client=self.client())

    def test_read_only_and_local_only(self):
        with self.assertRaises(PermissionError):
            self.client().call("wechat.chat.send_text", username=MOM, text="hi")
        with self.assertRaises(PermissionError):
            self.client().call("alpha.exports.start", conversation_id=MOM, format="json", destination_path="x")
        with self.assertRaises(parse_export.ParseError):
            wechat_live.Alpha("http://192.168.1.5:5031/mcp", TOKEN)
        with self.assertRaises(parse_export.ParseError) as e:
            wechat_live.Alpha(self.url, "wrong").call("wechat.chat.resolve_session", query="妈")
        self.assertIn("令牌", str(e.exception))
        self.assertEqual(wechat_live.find_token("<abc>"), "abc")     # 从页面上复制时带了尖括号

    def test_mama_run_wechat(self):
        with tempfile.TemporaryDirectory() as d:
            w = os.path.join(d, "out")
            env = {"MAMA_ALPHA_URL": self.url, "MAMA_ALPHA_TOKEN": TOKEN}
            r = run("mama.py", "run", "--wechat", "妈", "--call", "妈妈", "--today", "2026-05-02", "--tz", "+08:00",
                    "--dir", w, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("从本机微信读了 11 条", r.stdout)
            self.assertEqual(load(os.path.join(w, "run.json"))["input"], "wechat:妈")
            self.assertTrue(os.path.exists(os.path.join(w, "brief.md")))
            r = run("mama.py", "run", "--dir", w, env=env)
            self.assertEqual(r.returncode, 1)                       # 文件和 --wechat 总得给一个
            r = run("wechat_live.py", "find", "妈", env=env)
            self.assertIn("--id wxid_mom", r.stdout)


if __name__ == "__main__":
    unittest.main()
