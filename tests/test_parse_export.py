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
LOCAL = datetime(2026, 5, 12, 21, 3, 14)
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
