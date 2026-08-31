# -*- coding: utf-8 -*-
"""
全链路和边界测试。只用标准库。

  python -m unittest discover -s tests          # 在仓库根目录跑
  python -m unittest discover -s tests -v
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
EXAMPLES = os.path.join(ROOT, "examples")
sys.path.insert(0, SCRIPTS)

import stats        # noqa: E402
import validate     # noqa: E402
import redact       # noqa: E402

SAMPLE = os.path.join(EXAMPLES, "sample-messages.json")
SAMPLE_STATS = os.path.join(EXAMPLES, "sample-stats.json")
SAMPLE_NARR = os.path.join(EXAMPLES, "sample-narrative.json")
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


def load(p):
    return json.load(open(p, encoding="utf-8"))


def run(script, *args, cwd=ROOT):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          cwd=cwd, env=ENV, capture_output=True, text=True, encoding="utf-8")


def msg(ts, sender, content="", type_="text", dur=None):
    return {"ts": ts, "sender": sender, "type": type_, "content": content, "dur": dur}


def base(messages):
    return {"me": "我", "her": "妈妈", "her_pronoun": "她", "source": "test", "messages": messages}


class StatsOnSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = stats.compute(load(SAMPLE), today=date(2026, 8, 30), her_birthday="10-20", my_birthday="06-03")

    def test_scores_in_range(self):
        for k in ("care", "short", "forgive"):
            s = self.S["index"][k]["score"]
            self.assertTrue(s is None or 0 <= s <= 100, k)
        self.assertIn(self.S["rating"]["label"], {"模范子女", "还行", "欠一个电话", "欠一顿饭", "欠一次回家"})

    def test_counts_consistent(self):
        b = self.S["basics"]
        self.assertEqual(b["total"], b["her"] + b["me"])
        self.assertEqual(b["total"], b["with_ts"] + b["without_ts"])
        self.assertLessEqual(self.S["short"]["count"], self.S["short"]["replies"])
        self.assertLessEqual(self.S["short"]["replies"], b["me_text"])
        self.assertLessEqual(self.S["unanswered"]["count"], self.S["unanswered"]["turns"])
        self.assertLessEqual(self.S["unanswered"]["reopened_by_her"], self.S["unanswered"]["count"])
        self.assertEqual(self.S["bill"]["her_sent"], b["her"])
        self.assertAlmostEqual(sum(c["pct"] for c in self.S["composition"]), 100, delta=1.5)
        self.assertEqual(sum(self.S["hours"]["her"]), b["her"])

    def test_no_private_keys_leaked(self):
        data = load(SAMPLE)
        stats.compute(data, today=date(2026, 8, 30))
        for m in data["messages"]:
            for k in ("_i", "_dt", "_chars"):
                self.assertNotIn(k, m)

    def test_no_transfer_amount_in_output(self):
        blob = json.dumps(self.S, ensure_ascii=False)
        self.assertNotIn("1000 元", blob)

    def test_examples_in_sync(self):
        """examples/sample-stats.json 必须是当前 stats.py 对 sample-messages.json 的输出（改了算法记得重跑）"""
        golden = load(SAMPLE_STATS)
        today = date.fromisoformat(golden["today"])
        S = stats.compute(load(SAMPLE), today=today, her_birthday="10-20", my_birthday="06-03")
        S["today"] = golden["today"]
        self.assertEqual(json.loads(json.dumps(S, ensure_ascii=False)), golden,
                         "跑 python scripts/stats.py examples/sample-messages.json --out examples/sample-stats.json --today %s --her-birthday 10-20 --my-birthday 06-03" % golden["today"])


class StatsEdgeCases(unittest.TestCase):
    def test_empty(self):
        S = stats.compute(base([]), today=date(2026, 8, 30))
        self.assertEqual(S["basics"]["total"], 0)
        self.assertTrue(any("不到 20 条" in w for w in S["warnings"]))
        self.assertEqual(S["rating"]["label"], "模范子女")

    def test_all_without_timestamp(self):
        ms = [msg(None, "her", "吃饭了吗"), msg(None, "me", "吃了")] * 15
        S = stats.compute(base(ms), today=date(2026, 8, 30))
        self.assertIsNone(S["basics"]["first"])
        self.assertEqual(S["opens"]["her"], 0)
        self.assertTrue(any("没有时间戳" in w for w in S["warnings"]))
        self.assertEqual(S["short"]["count"], 15)          # 无时间戳的照样计数

    def test_only_her(self):
        ms = [msg(f"2026-05-{d:02d}T08:00:00", "her", "吃饭了吗") for d in range(1, 26)]
        S = stats.compute(base(ms), today=date(2026, 8, 30))
        self.assertIsNone(S["short"]["ratio"])
        self.assertEqual(S["unanswered"]["count"], 25)
        self.assertEqual(S["unanswered"]["reopened_by_her"], 24)   # 最后一段后面没有消息，不算她重开
        self.assertEqual(S["index"]["forgive"]["score"], 98)       # 0.6×24/25 + 0.4×1

    def test_unknown_sender_ignored(self):
        ms = [msg("2026-05-01T08:00:00", "her", "吃饭了吗"), msg("2026-05-01T08:05:00", "dad", "吃了没"),
              msg("2026-05-01T08:10:00", "me", "吃了")]
        S = stats.compute(base(ms), today=date(2026, 8, 30))
        self.assertEqual(S["basics"]["total"], 2)
        self.assertTrue(any("sender" in w for w in S["warnings"]))

    def test_backwards_time_warning(self):
        ms = [msg("2026-05-02T08:00:00", "her", "吃饭了吗"), msg("2026-05-01T08:05:00", "me", "吃了")] * 10
        S = stats.compute(base(ms), today=date(2026, 8, 30))
        self.assertTrue(any("倒序" in w for w in S["warnings"]))

    def test_my_opener_is_not_a_reply(self):
        """“在吗”是我主动找她，不是短回复；“嗯”才是"""
        ms = [msg("2026-05-01T20:00:00", "me", "在吗"), msg("2026-05-01T20:01:00", "her", "在的 怎么了"),
              msg("2026-05-01T20:02:00", "me", "没事"), msg("2026-05-03T08:00:00", "her", "吃饭了吗"),
              msg("2026-05-03T08:30:00", "me", "嗯")]
        S = stats.compute(base(ms), today=date(2026, 8, 30))
        self.assertEqual(S["short"]["replies"], 2)
        self.assertEqual(S["short"]["count"], 2)
        self.assertNotIn("在吗", dict(S["short"]["top"]))

    def test_late_reply_still_counts(self):
        """她早上发、你晚上回，隔 12 小时的“嗯”是回复；隔 3 天的不是"""
        ms = [msg("2026-05-01T07:00:00", "her", "吃饭了吗"), msg("2026-05-01T19:00:00", "me", "嗯"),
              msg("2026-05-01T19:01:00", "me", "在忙"),
              msg("2026-05-03T07:00:00", "her", "吃饭了吗"), msg("2026-05-06T20:00:00", "me", "好")]
        S = stats.compute(base(ms), today=date(2026, 8, 30))
        self.assertEqual(S["short"]["replies"], 2)      # “嗯”“在忙”；隔 3 天的“好”不算
        self.assertEqual(S["short"]["count"], 2)

    def test_short_reply_exclusions(self):
        ms = [msg("2026-05-01T08:00:00", "her", "吃饭了吗"), msg("2026-05-01T08:01:00", "me", "谢谢妈"),
              msg("2026-05-02T08:00:00", "her", "吃饭了吗"), msg("2026-05-02T08:01:00", "me", "[OK]"),
              msg("2026-05-03T08:00:00", "her", "吃饭了吗"), msg("2026-05-03T08:01:00", "me", "好的")]
        S = stats.compute(base(ms), today=date(2026, 8, 30))
        self.assertEqual(S["short"]["count"], 1)

    def test_early_late_split(self):
        ms = [msg("2026-05-01T07:00:00", "her", "早"), msg("2026-05-01T23:30:00", "her", "睡了吗"),
              msg("2026-05-02T01:00:00", "her", "在吗"), msg("2026-05-02T12:00:00", "her", "吃了吗")]
        S = stats.compute(base(ms), today=date(2026, 8, 30))
        self.assertEqual(S["hours"]["her_early_count"], 1)
        self.assertEqual(S["hours"]["her_late_count"], 2)

    def test_lunar_table_gap_warns(self):
        ms = [msg("2035-05-01T08:00:00", "her", "吃饭了吗")]
        S = stats.compute(base(ms), today=date(2035, 5, 2))
        self.assertTrue(any("农历" in w for w in S["warnings"]))

    def test_father_pronoun_switches_festival(self):
        data = base([msg("2026-06-21T09:00:00", "her", "爸爸节日快乐")] + [msg("2026-05-10T09:00:00", "me", "妈妈节日快乐")])
        data["messages"].sort(key=lambda m: m["ts"])
        data["her"], data["her_pronoun"] = "爸爸", "他"
        S = stats.compute(data, today=date(2026, 8, 30))
        names = {f["name"] for f in S["festivals"]}
        self.assertIn("父亲节", names)
        self.assertNotIn("母亲节", names)
        self.assertNotIn("母亲节", {c["name"] for c in S["countdown"]})


class RenderAndCompare(unittest.TestCase):
    def test_render_sample_complete(self):
        with tempfile.TemporaryDirectory() as d:
            r = run("render.py", SAMPLE_STATS, SAMPLE_NARR, "--out", d)
            self.assertEqual(r.returncode, 0, r.stderr)
            for name in ("report", "card-bill", "card-send"):
                p = os.path.join(d, f"mama-message-{name}.html")
                self.assertTrue(os.path.exists(p), p)
                html = open(p, encoding="utf-8").read()
                self.assertNotIn("{{", html, f"{name} 有没替换的占位符")
                self.assertNotIn("待写", html, f"{name} 还有待写")
            self.assertNotIn("还缺", r.stdout)

    def test_render_without_narrative(self):
        with tempfile.TemporaryDirectory() as d:
            r = run("render.py", SAMPLE_STATS, "--out", d)
            self.assertEqual(r.returncode, 0, r.stderr)
            html = open(os.path.join(d, "mama-message-report.html"), encoding="utf-8").read()
            self.assertIn("待写", html)
            self.assertIn("还缺", r.stdout)

    def test_render_edge_stats(self):
        """空记录 / 无时间戳的 stats 也要能出 HTML"""
        for data in (base([]), base([msg(None, "her", "吃饭了吗"), msg(None, "me", "嗯")] * 12)):
            S = stats.compute(data, today=date(2026, 8, 30))
            with tempfile.TemporaryDirectory() as d:
                sp = os.path.join(d, "s.json")
                json.dump(S, open(sp, "w", encoding="utf-8"), ensure_ascii=False)
                r = run("render.py", sp, "--out", d)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_compare(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "compare.json")
            r = run("compare.py", SAMPLE_STATS, SAMPLE_STATS, "--labels", "妈", "爸", "--mode", "papa", "--out", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            c = load(out)
            self.assertEqual(len(c["rows"]), 7)
            self.assertIn("差不多", c["verdict"])

    def test_stats_cli_prints_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "stats.py"), SAMPLE, "--out", os.path.join(d, "s.json"),
                                "--today", "2026-08-30"], cwd=ROOT, capture_output=True)   # 故意不设 PYTHONIOENCODING
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
            self.assertIn("牵挂指数".encode("utf-8"), r.stdout)


class Validate(unittest.TestCase):
    def test_sample_passes(self):
        errors, warnings, s = validate.check(load(SAMPLE))
        self.assertEqual(errors, [])
        self.assertEqual(s["total"], 294)

    def test_catches_common_mistakes(self):
        data = base([
            msg("2026-05-02T08:00:00", "mom", "吃饭了吗"),
            msg("昨天晚上", "me", "吃了"),
            msg("2026-05-01T08:00:00", "her", "吃饭了吗"),
            msg("2026-05-01T08:00:00", "her", "吃饭了吗"),
            msg("2026-05-01T09:00:00", "her", "转账 500 元", "transfer"),
            msg("2026-05-01T09:30:00", "her", "", "voice"),
        ])
        errors, warnings, s = validate.check(data)
        blob = "\n".join(errors)
        self.assertIn("sender", blob)
        self.assertIn("时间戳格式", blob)
        self.assertIn("倒序", blob)
        wb = "\n".join(warnings)
        self.assertIn("相同", wb)
        self.assertIn("金额", wb)
        self.assertIn("dur", wb)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            json.dump(base([msg("x", "me", "嗯")]), open(bad, "w", encoding="utf-8"), ensure_ascii=False)
            self.assertEqual(run("validate.py", bad).returncode, 1)
            self.assertEqual(run("validate.py", SAMPLE).returncode, 0)


class ParseExport(unittest.TestCase):
    def _parse(self, text, *extra):
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "chat.txt"), os.path.join(d, "m.json")
            open(src, "w", encoding="utf-8").write(text)
            r = run("parse_export.py", src, "--her", "妈妈", "--out", out, *extra)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            return load(out)

    def test_two_line_format(self):
        data = self._parse("2026-05-12 21:03:14 妈妈\n吃饭了吗\n\n2026-05-12 21:30:00 我\n吃了\n\n2026-05-13 07:10:00 妈妈\n[语音] 23秒\n")
        ms = data["messages"]
        self.assertEqual([m["sender"] for m in ms], ["her", "me", "her"])
        self.assertEqual(ms[0]["ts"], "2026-05-12T21:03:14")
        self.assertEqual(ms[2]["type"], "voice")
        self.assertEqual(ms[2]["dur"], 23)

    def test_one_line_format(self):
        data = self._parse("2026/5/12 21:03 妈妈: 吃饭了吗\n2026/5/12 21:30 我: [图片]\n2026/5/12 21:31 我: [转账] 转账 200 元\n")
        ms = data["messages"]
        self.assertEqual(ms[0]["ts"], "2026-05-12T21:03:00")
        self.assertEqual(ms[1]["type"], "image")
        self.assertEqual(ms[2]["type"], "transfer")

    def test_native_json_passthrough(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "m.json")
            r = run("parse_export.py", SAMPLE, "--out", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(len(load(out)["messages"]), 294)

    def test_clip_by_date(self):
        from parse_export import clip
        ms = [{"ts": f"2026-05-{d:02d}T08:00:00"} for d in range(1, 11)] + [{"ts": None}]
        keep, dropped, s0, s1 = clip(ms, since="2026-05-08")
        self.assertEqual(len(keep), 3)            # 08、09、10；没时间戳的切片时丢掉
        self.assertEqual(dropped, 8)
        keep, _, _, _ = clip(ms, since="2026-05-03", until="2026-05-05")
        self.assertEqual(len(keep), 3)
        keep, _, s0, _ = clip(ms, last_days=3)    # 相对最后一条（05-10），不是今天
        self.assertEqual([m["ts"][:10] for m in keep], ["2026-05-08", "2026-05-09", "2026-05-10"])
        self.assertEqual(s0, "2026-05-08")
        keep, dropped, _, _ = clip(ms)            # 不给条件就原样返回，无时间戳的也留着
        self.assertEqual((len(keep), dropped), (11, 0))

    def test_clip_cli(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "m.json")
            r = run("parse_export.py", SAMPLE, "--out", out, "--last-days", "30")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(len(load(out)["messages"]), 44)
            self.assertEqual(run("parse_export.py", SAMPLE, "--out", out, "--since", "2030-01-01").returncode, 1)
            self.assertEqual(run("parse_export.py", SAMPLE, "--out", out, "--since", "abc").returncode, 1)

    def test_bad_timestamp_does_not_crash(self):
        from parse_export import norm_ts
        self.assertIsNone(norm_ts("2026-13-45 99:99"))
        self.assertIsNone(norm_ts("昨天"))
        self.assertEqual(norm_ts("2026/5/1 8:05"), "2026-05-01T08:05:00")


class WeFlowFormats(unittest.TestCase):
    """WeFlow（863108316/WeFlow）三种导出。字段口径来自它的 exportService.ts。"""

    def _cli(self, path, *args):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "m.json")
            r = run("parse_export.py", path, "--call", "妈妈", "--out", out, *args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            return load(out), open(out, encoding="utf-8").read()

    def test_weflow_detailed_json(self):
        from datetime import datetime as dt
        t0 = int(dt(2026, 5, 12, 21, 3, 14).timestamp())
        def wf(off, is_send, lt, content, **extra):
            d = {"localId": 1, "createTime": t0 + off, "formattedTime": "", "type": "文本消息",
                 "localType": lt, "content": content, "isSend": is_send,
                 "senderUsername": "wxid_x", "senderDisplayName": "我" if is_send else "妈妈"}
            d.update(extra)
            return d
        payload = {"weflow": {"version": "1.0.3", "generator": "WeFlow"},
                   "session": {"displayName": "妈妈", "type": "私聊"},
                   "messages": [
                       wf(0, 0, 1, "吃饭了吗"),
                       wf(60, 1, 1, "吃了"),
                       wf(120, 0, 34, "[语音消息]"),
                       wf(180, 0, 47, None),
                       wf(240, 0, 49, "[链接] 久坐伤腰 三个动作缓解\nhttps://x"),
                       wf(300, 0, 49, "[转账] (妈妈转账给我) ￥1000.00"),
                       wf(360, 0, 50, "[语音通话] 通话时长 03:25"),
                       wf(420, 0, 10000, "对方撤回了一条消息"),
                       wf(480, 0, 10000, "你已添加了妈妈"),          # 系统消息，应被跳过
                       wf(540, 0, 49, None, linkTitle="这几种菜千万不能一起吃"),
                   ]}
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "私聊_妈妈.json")
            json.dump(payload, open(src, "w", encoding="utf-8"), ensure_ascii=False)
            data, raw = self._cli(src)
        ms = data["messages"]
        self.assertEqual(data["her"], "妈妈")
        self.assertEqual(len(ms), 9)                                  # 系统消息被跳过
        self.assertEqual(ms[0]["ts"], "2026-05-12T21:03:14")          # Unix 秒 → 本地时间
        self.assertEqual([m["sender"] for m in ms[:2]], ["her", "me"])  # isSend
        self.assertEqual([m["type"] for m in ms],
                         ["text", "text", "voice", "sticker", "link", "transfer", "call_voice", "recall", "link"])
        self.assertEqual(ms[5]["content"], "转账")                     # 金额不落地
        self.assertNotIn("￥", raw)
        self.assertNotIn("1000.00", raw)
        self.assertEqual(ms[6]["dur"], 205)                           # 通话时长 03:25
        self.assertIn("这几种菜", ms[8]["content"])                    # content 空时用 linkTitle

    def test_weflow_txt(self):
        text = ("2026-05-12 21:03:14 '妈妈'\n吃饭了吗\n\n"
                "2026-05-12 21:30:00 '我'\n吃了\n\n"
                "2026-05-13 08:00:00 '妈妈'\n[语音通话] 通话时长 02:00\n\n")
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "chat.txt")
            open(src, "w", encoding="utf-8").write(text)
            data, _ = self._cli(src, "--her", "妈妈", "--me", "我")
        ms = data["messages"]
        self.assertEqual([m["sender"] for m in ms], ["her", "me", "her"])   # 引号已剥
        self.assertEqual(ms[2]["type"], "call_voice")
        self.assertEqual(ms[2]["dur"], 120)

    def test_weclone_csv_utc_to_local(self):
        from datetime import datetime as dt, timezone
        rows = ('\ufeffid,MsgSvrID,type_name,is_sender,talker,msg,src,CreateTime\r\n'
                '1,1,text,0,妈妈,吃饭了吗,,2026-05-12T13:03:14.000Z\r\n'
                '2,2,voice,1,我,[语音消息],media/voices/a.wav,2026-05-12T13:30:00.000Z\r\n'
                '3,3,text,0,妈妈,"[转账] (妈妈转账给我) ￥50.00",,2026-05-13T01:00:00.000Z\r\n')
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "私聊_妈妈.csv")
            open(src, "w", encoding="utf-8", newline="").write(rows)
            data, raw = self._cli(src)
        ms = data["messages"]
        expect = dt.fromisoformat("2026-05-12T13:03:14+00:00").astimezone().strftime("%Y-%m-%dT%H:%M:%S")
        self.assertEqual(ms[0]["ts"], expect)                          # UTC → 本地
        self.assertEqual([m["sender"] for m in ms], ["her", "me", "her"])
        self.assertEqual([m["type"] for m in ms], ["text", "voice", "transfer"])
        self.assertEqual(ms[2]["content"], "转账")
        self.assertNotIn("50.00", raw)

    def test_redact_yuan_amount(self):
        out = redact.redact("[转账] (妈妈转账给我) ￥1,000.50 和 ¥88", {}, [])
        self.assertNotIn("1,000", out)
        self.assertNotIn("88", out)


class Redact(unittest.TestCase):
    def test_patterns(self):
        out = redact.redact("张小明 手机 13812345678 身份证 11010119900101123X 转了 500 元 卡号 6222021234567890123 邮箱 a@b.com",
                            {"张小明": "我"}, ["王阿姨"])
        self.assertNotIn("13812345678", out)
        self.assertNotIn("11010119900101123X", out)
        self.assertNotIn("6222021234567890123", out)
        self.assertNotIn("500", out)
        self.assertNotIn("a@b.com", out)
        self.assertIn("我", out)
        self.assertNotIn("张小明", out)


if __name__ == "__main__":
    unittest.main()
