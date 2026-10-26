# -*- coding: utf-8 -*-
"""
导出格式解析：tests/fixtures/ 里每种来源一份最小样本，逐个解析并核对条数、发送者、类型、时间。
拿到真实导出后，打码、截前几十条放进 fixtures/，在 CASES 里加一行期望值。
"""
import os
import tempfile
import unittest
from datetime import datetime

from helpers import FIXTURES, SAMPLE, load, read, run

import _common      # noqa: E402
from parse_export import TYPE_MARKERS, WX_TYPE, clip, norm_ts   # noqa: E402

# 时间戳按本机时区解释，期望值也按本机算，CI 在哪个时区都过
LOCAL = datetime.fromtimestamp(1778590994)   # ms.csv 第一条的毫秒时间戳，北京时间 2026-05-12 21:03:14
UTC_13_03 = datetime.fromisoformat("2026-05-12T13:03:14+00:00").astimezone().strftime("%Y-%m-%dT%H:%M:%S")

CASES = {
    "weflow.json": {"format": "weflow-json 1.0.3", "n": 9, "senders": ["her", "me"] + ["her"] * 7,
                    "types": ["text", "text", "voice", "sticker", "link", "transfer", "call_voice", "recall", "link"],
                    "ts0": datetime.fromtimestamp(load(os.path.join(FIXTURES, "weflow.json"))["messages"][0]["createTime"]).strftime("%Y-%m-%dT%H:%M:%S")},
    "weflow.txt": {"format": "weflow-txt", "n": 3, "senders": ["her", "me", "her"], "types": ["text", "text", "call_voice"],
                   "ts0": "2026-05-12T21:03:14", "args": ["--her", "妈妈", "--me", "我"]},
    "weclone.csv": {"format": "weclone-csv", "n": 3, "senders": ["her", "me", "her"], "types": ["text", "voice", "transfer"],
                    "ts0": UTC_13_03, "encoding": "utf-8-sig"},
    "memotrace.csv": {"format": "memotrace-csv", "n": 7, "senders": ["her", "me"] + ["her"] * 5,
                      "types": ["text", "text", "image", "voice", "link", "transfer", "recall"], "ts0": "2026-05-12T21:03:14"},
    "twoline.txt": {"format": "txt", "n": 3, "senders": ["her", "me", "her"], "types": ["text", "text", "voice"], "ts0": "2026-05-12T21:03:14"},
    "oneline.txt": {"format": "txt", "n": 3, "senders": ["her", "me", "me"], "types": ["text", "image", "transfer"], "ts0": "2026-05-12T21:03:00"},
    "gbk.txt": {"format": "txt", "n": 3, "senders": ["her", "me", "her"], "types": ["text", "text", "voice"], "ts0": "2026-05-12T21:03:14", "encoding": "gb18030"},
    "utf16.txt": {"format": "txt", "n": 3, "senders": ["her", "me", "her"], "types": ["text", "text", "voice"], "ts0": "2026-05-12T21:03:14", "encoding": "utf-16"},
    "ms.csv": {"format": "memotrace-csv", "n": 2, "senders": ["her", "me"], "types": ["text", "text"], "ts0": LOCAL.strftime("%Y-%m-%dT%H:%M:%S")},
    "native-as-txt.txt": {"format": "native", "n": 2, "senders": ["her", "me"], "types": ["text", "text"], "ts0": "2026-05-12T21:03:14"},
    "transcript.txt": {"format": "transcript", "n": 10, "senders": ["her", "me", "her", "her", "her", "me", "her", "her", "me", "me"],
                       "types": ["text", "text", "text", "text", "voice", "text", "text", "link", "call_video", "text"],
                       "ts0": "2026-08-14T07:15:00", "args": ["--shot-date", "2026-08-30"]},
}


class Fixtures(unittest.TestCase):
    def _cli(self, name, *extra):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "m.json")
            args = list(extra) or ["--her", "妈妈"]
            r = run("parse_export.py", os.path.join(FIXTURES, name), "--call", "妈妈", "--out", out, *args)
            self.assertEqual(r.returncode, 0, name + "\n" + r.stdout + r.stderr)
            return load(out), read(out), r.stdout

    def test_every_fixture(self):
        for name, exp in CASES.items():
            with self.subTest(fixture=name):
                data, raw, out = self._cli(name, *exp.get("args", []))
                ms = data["messages"]
                self.assertEqual(len(ms), exp["n"])
                self.assertEqual([m["sender"] for m in ms], exp["senders"])
                self.assertEqual([m["type"] for m in ms], exp["types"])
                self.assertEqual(ms[0]["ts"], exp["ts0"])
                self.assertEqual(data["her"], "妈妈")
                self.assertEqual(data["schema"], _common.SCHEMA_VERSION)
                self.assertTrue(data["source_detail"].startswith(exp["format"]), data["source_detail"])
                if "encoding" in exp:
                    self.assertIn(exp["encoding"], data["source_detail"])
                for m in ms:
                    self.assertIn(m["type"], _common.TYPES)
                    if m["type"] == "transfer":
                        self.assertEqual(m["content"], "转账")
                self.assertNotIn("￥", raw)          # 金额不落地
                self.assertNotIn("1000.00", raw)

    def test_weflow_details(self):
        data, raw, _ = self._cli("weflow.json")
        ms = data["messages"]
        self.assertEqual(ms[6]["dur"], 205)                           # 通话时长 03:25
        self.assertIn("这几种菜", ms[8]["content"])                    # content 空时用 linkTitle
        self.assertEqual(ms[4]["content"].split("\n")[0], "久坐伤腰 三个动作缓解")
        data, _, _ = self._cli("weflow.txt", "--her", "妈妈", "--me", "我")
        self.assertEqual(data["messages"][2]["dur"], 120)
        data, _, _ = self._cli("twoline.txt")
        self.assertEqual(data["messages"][2]["dur"], 23)

    def test_peek_runs_on_every_fixture(self):
        for name in CASES:
            with self.subTest(fixture=name):
                r = run("parse_export.py", os.path.join(FIXTURES, name), "--peek")
                self.assertEqual(r.returncode, 0, name + r.stdout + r.stderr)
                self.assertIn("识别为", r.stdout)
                self.assertIn("编码", r.stdout)

    def test_no_her_lists_names(self):
        with tempfile.TemporaryDirectory() as d:
            r = run("parse_export.py", os.path.join(FIXTURES, "twoline.txt"), "--out", os.path.join(d, "m.json"))
            self.assertEqual(r.returncode, 1)
            self.assertIn("妈妈", r.stdout)
            self.assertIn("--her", r.stdout)

    def test_wrong_her_says_peek(self):
        with tempfile.TemporaryDirectory() as d:
            r = run("parse_export.py", os.path.join(FIXTURES, "twoline.txt"), "--her", "老妈", "--out", os.path.join(d, "m.json"))
            self.assertEqual(r.returncode, 1)
            self.assertIn("--peek", r.stdout)

    def test_bad_json_extension(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write("{not json")
            r = run("parse_export.py", p, "--her", "妈妈", "--out", os.path.join(d, "m.json"))
            self.assertEqual(r.returncode, 1)
            self.assertIn("JSON", r.stdout)


class Transcript(unittest.TestCase):
    """截图转录稿：AI 照截图抄，脚本去重叠、排顺序、换算相对时间"""
    def _parse(self, *args):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "m.json")
            r = run("parse_export.py", os.path.join(FIXTURES, "transcript.txt"), "--call", "妈妈", "--out", out, *args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            return load(out), r.stdout

    def test_with_shot_date(self):
        data, out = self._parse("--shot-date", "2026-08-30")
        ms = data["messages"]
        self.assertEqual(data["source"], "screenshots")
        self.assertIn("倒过来", out)                       # 截图是从新到旧给的
        self.assertIn("重叠的 2 条", out)                  # 两处重叠：“打扰你了 你忙吧”、“[语音 12秒]”
        self.assertEqual([m["ts"] for m in ms if m["ts"]],
                         ["2026-08-14T07:15:00", "2026-08-14T19:02:00", "2026-08-19T20:30:00", "2026-08-25T21:10:00",
                          "2026-08-28T09:30:00",            # 星期五（截图那天是星期日）
                          "2026-08-29T15:05:00",            # 昨天 下午3:05
                          "2026-08-30T21:30:00"])           # 只写了 21:30 = 截图当天
        self.assertEqual(sum(1 for m in ms if not m["ts"]), 3)   # 一个时间只给它下面第一条，后面的不编
        self.assertEqual(ms[4]["dur"], 12)
        self.assertEqual(ms[8]["dur"], 205)
        self.assertEqual(ms[7]["content"], "久坐伤腰 三个动作缓解")

    def test_without_shot_date_still_orders_and_dedupes(self):
        """没给截图日期：相对时间换算不了（留空、提示），但顺序和去重靠重叠方向照样对"""
        data, out = self._parse()
        ms = data["messages"]
        self.assertEqual(len(ms), 10)
        self.assertIn("--shot-date", out)
        self.assertEqual(ms[0]["content"], "最近腰不太好 医生说要少干活")
        self.assertEqual(ms[3]["ts"], "2026-08-25T21:10:00")     # “8月25日”借了别处写全的年份
        self.assertIsNone(ms[5]["ts"])

    def test_plain_pasted_dialogue(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "paste.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("妈妈：吃饭了吗\n我：吃了\n妈妈：吃的什么\n我：面\n")
            out = os.path.join(d, "m.json")
            r = run("parse_export.py", src, "--out", out)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertEqual([m["sender"] for m in load(out)["messages"]], ["her", "me", "her", "me"])
            # 聊天 AI 回的稿子：前面一句客套话、包在代码块里、“她（妈妈）：”、续行里带冒号
            with open(src, "w", encoding="utf-8") as f:
                f.write("好的，下面是抄好的稿子：\n```\n=== 截图 1 ===\n-- 2026-05-12 21:03 --\n她（妈妈）：明天降温\n注意：多穿点\n我：好\n```\n")
            r = run("parse_export.py", src, "--out", out)
            self.assertEqual(r.returncode, 0, r.stdout)
            ms = load(out)["messages"]
            self.assertEqual([(m["sender"], m["content"]) for m in ms], [("her", "明天降温\n注意：多穿点"), ("me", "好")])
            self.assertEqual(ms[0]["ts"], "2026-05-12T21:03:00")

    def test_sep_time_forms(self):
        from datetime import date
        from parse_export import sep_time
        st = {"date": None, "shot": date(2026, 8, 30), "relative": 0, "year": None}
        cases = {"2026年5月12日 晚上9:03": "2026-05-12 21:03", "5月12日 下午3:05": "2026-05-12 15:05",
                 "12月30日 08:00": "2025-12-30 08:00",       # 比截图那天晚 → 是去年的
                 "昨天 凌晨1:20": "2026-08-29 01:20", "前天 12:30": "2026-08-28 12:30", "星期二 中午12:10": "2026-08-25 12:10",
                 "周日 07:00": "2026-08-23 07:00", "21:30": "2026-08-30 21:30", "上午 12:05": "2026-08-30 00:05"}
        for text, want in cases.items():
            dt = sep_time(text, dict(st))
            self.assertEqual(dt.strftime("%Y-%m-%d %H:%M") if dt else None, want, text)
        st2 = {"date": None, "shot": None, "relative": 0, "year": None}
        self.assertIsNone(sep_time("昨天 21:30", st2))
        self.assertEqual(st2["relative"], 1)


class TimeZone(unittest.TestCase):
    def test_tz_flag_makes_utc_deterministic(self):
        """weclone CSV 的 UTC 时间：给了 --tz 就按那个时区换算，在哪台机器上跑都一样"""
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "m.json")
            r = run("parse_export.py", os.path.join(FIXTURES, "weclone.csv"), "--out", out, "--tz", "+08:00")
            self.assertEqual(r.returncode, 0, r.stdout)
            data = load(out)
            self.assertEqual(data["messages"][0]["ts"], "2026-05-12T21:03:14")
            self.assertEqual(data["tz"], "+08:00")
            r = run("parse_export.py", os.path.join(FIXTURES, "weclone.csv"), "--out", out, "--tz", "UTC-5")
            self.assertEqual(load(out)["messages"][0]["ts"], "2026-05-12T08:03:14")
            r = run("parse_export.py", os.path.join(FIXTURES, "weclone.csv"), "--out", out, "--tz", "北京")
            self.assertEqual(r.returncode, 1)
            self.assertIn("+08:00", r.stdout)

    def test_parse_tz(self):
        from datetime import timedelta
        self.assertIsNone(_common.parse_tz(None))
        for s, h in (("+08:00", 8), ("+0800", 8), ("UTC+8", 8), ("-5", -5), ("+05:30", 5.5)):
            self.assertEqual(_common.parse_tz(s).utcoffset(None), timedelta(hours=h), s)
        for bad in ("8", "北京", "+25:00"):
            with self.assertRaises(ValueError):
                _common.parse_tz(bad)
        self.assertRegex(_common.tz_label(), r"^[+-]\d{2}:\d{2}$")


class NativeAndClip(unittest.TestCase):
    def test_native_passthrough(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "m.json")
            r = run("parse_export.py", SAMPLE, "--out", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = load(out)
            self.assertEqual(len(data["messages"]), 294)
            self.assertEqual(data["schema"], _common.SCHEMA_VERSION)
            self.assertEqual(data["her_pronoun"], "她")                      # 没给 --pronoun 就不动
            r = run("parse_export.py", SAMPLE, "--out", out, "--call", "老爸", "--pronoun", "他")
            self.assertEqual(r.returncode, 0, r.stderr)
            data = load(out)
            self.assertEqual((data["her"], data["her_pronoun"]), ("老爸", "他"))
            r = run("parse_export.py", SAMPLE, "--out", out, "--pronoun", "它")
            self.assertEqual(r.returncode, 1)

    def test_clip_by_date(self):
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
        self.assertIsNone(norm_ts("2026-13-45 99:99"))
        self.assertIsNone(norm_ts("昨天"))
        self.assertEqual(norm_ts("2026/5/1 8:05"), "2026-05-01T08:05:00")

    def test_type_maps_target_the_enum(self):
        """各家导出到本项目类型的映射，目标必须在 _common.TYPES 里（system 是中间态）"""
        for v in WX_TYPE.values():
            self.assertTrue(v in _common.TYPES or v == "system", v)
        for _, t in TYPE_MARKERS:
            self.assertIn(t, _common.TYPES)
        self.assertEqual(set(_common.TYPE_CN), set(_common.TYPES) - {"text"})


if __name__ == "__main__":
    unittest.main()
