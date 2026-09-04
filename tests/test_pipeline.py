# -*- coding: utf-8 -*-
"""
统计引擎、渲染、校验、打码的全链路和边界测试。只用标准库。

  python -m unittest discover -s tests          # 在仓库根目录跑
  python -m unittest discover -s tests -v

导出格式解析在 test_parse_export.py，文字 lint 在 test_lint.py，文档与代码口径一致在 test_docs_sync.py。
"""
import copy
import json
import os
import tempfile
import unittest
from datetime import date

from helpers import SAMPLE, SAMPLE_NARR, SAMPLE_STATS, SCRIPTS, base, load, msg, read, run, save

import _common     # noqa: E402
import redact      # noqa: E402
import stats       # noqa: E402
import validate    # noqa: E402


class StatsOnSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = stats.compute(load(SAMPLE), today=date(2026, 8, 30), her_birthday="10-20", my_birthday="06-03")

    def test_scores_in_range(self):
        for k in ("care", "short", "forgive"):
            s = self.S["index"][k]["score"]
            self.assertTrue(s is None or 0 <= s <= 100, k)
        self.assertIn(self.S["rating"]["label"], {label for _, label in stats.RATING_BANDS})

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

    def test_schema_and_lexicon_version(self):
        self.assertEqual(self.S["schema"], _common.SCHEMA_VERSION)
        self.assertEqual(self.S["lexicon"], _common.load_lexicon()["version"])

    def test_input_not_mutated(self):
        data = load(SAMPLE)
        before = json.dumps(data, ensure_ascii=False, sort_keys=True)
        stats.compute(data, today=date(2026, 8, 30))
        self.assertEqual(before, json.dumps(data, ensure_ascii=False, sort_keys=True))
        # 缺 type / content 的消息也不会被补写回去
        d2 = {"me": "我", "her": "妈妈", "messages": [{"ts": "2026-05-01T08:00:00", "sender": "her"}]}
        stats.compute(d2, today=date(2026, 8, 30))
        self.assertEqual(d2["messages"][0], {"ts": "2026-05-01T08:00:00", "sender": "her"})

    def test_no_transfer_amount_in_output(self):
        blob = json.dumps(self.S, ensure_ascii=False)
        self.assertNotIn("1000 元", blob)

    def test_examples_in_sync(self):
        """examples/sample-stats.json 必须是当前 stats.py 对 sample-messages.json 的输出（改了算法跑 python tools/refresh.py）"""
        golden = load(SAMPLE_STATS)
        today = date.fromisoformat(golden["today"])
        S = stats.compute(load(SAMPLE), today=today, her_birthday="10-20", my_birthday="06-03")
        S["today"] = golden["today"]
        self.assertEqual(json.loads(json.dumps(S, ensure_ascii=False)), golden,
                         "跑 python tools/refresh.py 重新生成示例（今天用 %s）" % golden["today"])

    def test_sections_are_callable_alone(self):
        """拆分后每一段可以单独算：给 Ctx 就行，不用跑完整个 compute"""
        ctx = stats.Ctx(load(SAMPLE), _common.load_lexicon(), today=date(2026, 8, 30))
        S = {"warnings": []}
        S["basics"] = stats.sec_basics(ctx, S)
        S["opens"] = stats.sec_opens(ctx, S)
        self.assertEqual(S["opens"]["her"] + S["opens"]["me"], len(ctx.d["her_opens"]) + len(ctx.d["my_opens"]))
        self.assertEqual(S["basics"]["total"], 294)


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

    def test_short_reply_rule(self):
        """短回复 = ≤ 3 字、不是表情、不含谢/爱/想、不以妈/爸结尾；4 字就不是"""
        lex = _common.load_lexicon()
        for text, expect in (("嗯", True), ("好的", True), ("知道了", True), ("ok", True), ("OK！", True),
                             ("好的好的", False), ("谢谢妈", False), ("想你", False), ("好妈", False), ("[OK]", False), ("", False)):
            self.assertEqual(stats.is_short({"content": text}, lex), expect, text)

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

    def test_birthday_validation(self):
        data = load(SAMPLE)
        with self.assertRaises(ValueError):
            stats.compute(data, today=date(2026, 8, 30), her_birthday="13-45")
        with self.assertRaises(ValueError):
            stats.compute(data, today=date(2026, 8, 30), her_birthday="生日")
        S = stats.compute(data, today=date(2026, 8, 30), her_birthday="02-29")   # 非闰年跳过，不崩
        self.assertNotIn("她的生日", {f["name"] for f in S["festivals"]})
        r = run("stats.py", SAMPLE, "--out", os.devnull, "--her-birthday", "13-45", "--quiet")
        self.assertEqual(r.returncode, 1)
        self.assertIn("生日", r.stdout)

    def test_lexicon_exclude_blocks_false_positive(self):
        """“冷静”不算天气；“多穿”还是天气。词表可以整份替换"""
        ms = [msg("2026-05-01T08:00:00", "her", "你冷静一下"), msg("2026-05-02T08:00:00", "her", "降温了 多穿点")]
        S = stats.compute(base(ms), today=date(2026, 8, 30))
        self.assertEqual([t for t in S["topics"] if t["topic"] == "天气"][0]["count"], 1)
        lex = copy.deepcopy(_common.load_lexicon())
        lex["exclude"] = {}
        S2 = stats.compute(base(ms), today=date(2026, 8, 30), lexicon=lex)
        self.assertEqual([t for t in S2["topics"] if t["topic"] == "天气"][0]["count"], 2)

    def test_custom_lexicon_cli(self):
        with tempfile.TemporaryDirectory() as d:
            lex = copy.deepcopy(_common.load_lexicon())
            lex["version"] = 99
            lp = os.path.join(d, "lex.json")
            save(lp, lex)
            out = os.path.join(d, "s.json")
            r = run("stats.py", SAMPLE, "--out", out, "--today", "2026-08-30", "--lexicon", lp, "--quiet")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(load(out)["lexicon"], 99)
            r = run("stats.py", SAMPLE, "--out", out, "--lexicon", os.path.join(d, "nope.json"), "--quiet")
            self.assertEqual(r.returncode, 1)
            self.assertIn("词表", r.stdout)


class RenderAndCompare(unittest.TestCase):
    def test_render_sample_complete(self):
        with tempfile.TemporaryDirectory() as d:
            r = run("render.py", SAMPLE_STATS, SAMPLE_NARR, "--out", d)
            self.assertEqual(r.returncode, 0, r.stderr)
            for name in ("report", "card-bill", "card-send"):
                p = os.path.join(d, f"mama-message-{name}.html")
                self.assertTrue(os.path.exists(p), p)
                html = read(p)
                self.assertNotIn("{{", html, f"{name} 有没替换的占位符")
                self.assertNotIn("待写", html, f"{name} 还有待写")
            self.assertNotIn("还缺", r.stdout)

    def test_render_without_narrative(self):
        with tempfile.TemporaryDirectory() as d:
            r = run("render.py", SAMPLE_STATS, "--out", d)
            self.assertEqual(r.returncode, 0, r.stderr)
            html = read(os.path.join(d, "mama-message-report.html"))
            self.assertIn("待写", html)
            self.assertIn("还缺", r.stdout)

    def test_render_missing_narrative_file_warns(self):
        with tempfile.TemporaryDirectory() as d:
            r = run("render.py", SAMPLE_STATS, os.path.join(d, "nope.json"), "--out", d)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("找不到", r.stdout)

    def test_render_rejects_old_schema(self):
        with tempfile.TemporaryDirectory() as d:
            S = load(SAMPLE_STATS)
            S.pop("schema")
            sp = os.path.join(d, "old.json")
            save(sp, S)
            r = run("render.py", sp, "--out", d)
            self.assertEqual(r.returncode, 1)
            self.assertIn("重新跑", r.stdout)

    def test_render_edge_stats(self):
        """空记录 / 无时间戳的 stats 也要能出 HTML"""
        for data in (base([]), base([msg(None, "her", "吃饭了吗"), msg(None, "me", "嗯")] * 12)):
            S = stats.compute(data, today=date(2026, 8, 30))
            with tempfile.TemporaryDirectory() as d:
                sp = os.path.join(d, "s.json")
                save(sp, S)
                r = run("render.py", sp, "--out", d)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_render_escapes_html(self):
        with tempfile.TemporaryDirectory() as d:
            N = load(SAMPLE_NARR)
            N["send_text"] = "<script>alert(1)</script> 今晚 8 点打给你"
            np_ = os.path.join(d, "n.json")
            save(np_, N)
            r = run("render.py", SAMPLE_STATS, np_, "--out", d)
            self.assertEqual(r.returncode, 0, r.stderr)
            html = read(os.path.join(d, "mama-message-card-send.html"))
            self.assertNotIn("<script>alert", html)
            self.assertIn("&lt;script&gt;", html)

    def test_compare(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "compare.json")
            r = run("compare.py", SAMPLE_STATS, SAMPLE_STATS, "--labels", "妈", "爸", "--mode", "papa", "--out", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            c = load(out)
            self.assertEqual(len(c["rows"]), 7)
            self.assertIn("差不多", c["verdict"])

    def test_stats_cli_prints_utf8(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "stats.py"), SAMPLE, "--out", os.path.join(d, "s.json"),
                                "--today", "2026-08-30"], cwd=os.path.dirname(SCRIPTS), capture_output=True)   # 故意不设 PYTHONIOENCODING
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
            self.assertIn("牵挂指数".encode("utf-8"), r.stdout)

    def test_every_cli_has_help_text(self):
        """--help 要能看懂：至少带模块说明的第一句"""
        for script, hint in (("parse_export.py", "messages.json"), ("validate.py", "stats.py"), ("stats.py", "统计引擎"),
                             ("render.py", "HTML"), ("compare.py", "对照组"), ("redact.py", "打码"), ("lint_narrative.py", "写作规矩")):
            r = run(script, "--help")
            self.assertEqual(r.returncode, 0, script)
            self.assertIn(hint, r.stdout, script)


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

    def test_future_schema_rejected(self):
        data = base([msg("2026-05-01T08:00:00", "her", "吃饭了吗")])
        data["schema"] = _common.SCHEMA_VERSION + 1
        errors, _, _ = validate.check(data)
        self.assertTrue(any("schema" in e for e in errors))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            save(bad, base([msg("x", "me", "嗯")]))
            self.assertEqual(run("validate.py", bad).returncode, 1)
            self.assertEqual(run("validate.py", SAMPLE).returncode, 0)


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

    def test_yuan_amount(self):
        out = redact.redact("[转账] (妈妈转账给我) ￥1,000.50 和 ¥88", {}, [])
        self.assertNotIn("1,000", out)
        self.assertNotIn("88", out)

    def test_cli_reads_gbk_writes_utf8(self):
        from helpers import FIXTURES
        import shutil
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "gbk.txt")
            shutil.copyfile(os.path.join(FIXTURES, "gbk.txt"), src)
            r = run("redact.py", src, "--map", "妈妈=母亲")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("gb18030", r.stdout)
            out = read(os.path.join(d, "gbk.redacted.txt"))
            self.assertIn("母亲", out)
            self.assertNotIn("妈妈", out)


class Common(unittest.TestCase):
    def test_epoch_to_local_seconds_and_ms(self):
        from datetime import datetime
        t = int(datetime(2026, 5, 12, 21, 3, 14).timestamp())
        self.assertEqual(_common.epoch_to_local(t), "2026-05-12 21:03:14")
        self.assertEqual(_common.epoch_to_local(str(t * 1000)), "2026-05-12 21:03:14")
        self.assertIsNone(_common.epoch_to_local("abc"))
        self.assertIsNone(_common.epoch_to_local(10 ** 18))

    def test_read_text_sniffs_encoding(self):
        with tempfile.TemporaryDirectory() as d:
            for enc, name in (("utf-8", "utf-8"), ("utf-8-sig", "utf-8-sig"), ("gb18030", "gb18030"), ("utf-16", "utf-16")):
                p = os.path.join(d, enc + ".txt")
                with open(p, "w", encoding=enc, newline="\n") as f:
                    f.write("妈妈：吃饭了吗\n")
                text, got = _common.read_text(p)
                self.assertEqual(got, name)
                self.assertEqual(text, "妈妈：吃饭了吗\n")

    def test_parse_mmdd(self):
        self.assertEqual(_common.parse_mmdd("10-20"), (10, 20))
        for bad in ("13-45", "1020", "x-y", ""):
            with self.assertRaises(ValueError):
                _common.parse_mmdd(bad)
        self.assertIsNone(_common.safe_date(2026, 2, 29))
        self.assertEqual(str(_common.safe_date(2028, 2, 29)), "2028-02-29")

    def test_fmt_delta(self):
        self.assertEqual(_common.fmt_delta(None), "—")
        self.assertEqual(_common.fmt_delta(180), "3 分钟")
        self.assertEqual(_common.fmt_delta(5400), "1 小时 30 分")
        self.assertEqual(_common.fmt_delta(3 * 86400), "3 天")

    def test_lexicon_has_all_keys(self):
        lex = _common.load_lexicon()
        self.assertEqual(set(lex["care_topics"]) - set(lex["topics"]), set())
        for topic in lex["exclude"]:
            self.assertTrue(topic in lex["topics"] or topic in lex, topic)


if __name__ == "__main__":
    unittest.main()
