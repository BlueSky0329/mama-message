# -*- coding: utf-8 -*-
"""narrative.json 的规矩检查：示例要过，常见违规要抓到。"""
import copy
import os
import tempfile
import unittest

from helpers import REFERENCES, SAMPLE, SAMPLE_NARR, SAMPLE_STATS, load, run, save

import lint_narrative as ln   # noqa: E402


class LintSample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.N, cls.S, cls.M = load(SAMPLE_NARR), load(SAMPLE_STATS), load(SAMPLE)

    def test_sample_passes(self):
        errors, warnings = ln.lint(self.N, self.S, self.M)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [], warnings)

    def test_blacklist_read_from_writing_rules(self):
        bl = ln.load_blacklist(os.path.join(REFERENCES, "writing-rules.md"))
        self.assertIn("子欲养而亲不待", bl)
        self.assertIn("作为 AI", bl)
        self.assertGreater(len(bl), 15)
        self.assertEqual(ln.load_blacklist(os.path.join(REFERENCES, "nope.md")), ln.FALLBACK_BLACKLIST)

    def _errs(self, **changes):
        N = copy.deepcopy(self.N)
        N.update(changes)
        return ln.lint(N, self.S, self.M)

    def test_missing_required(self):
        errors, _ = self._errs(she_means="", send_text=None)
        self.assertTrue(any("she_means" in e for e in errors))
        self.assertTrue(any("send_text" in e for e in errors))
        N = copy.deepcopy(self.N)
        N["type_lines"] = {"mother": "x"}
        errors, _ = ln.lint(N, self.S, self.M)
        self.assertTrue(any("type_lines.child" in e for e in errors))

    def test_send_text_needs_time(self):
        errors, _ = self._errs(send_text="妈，我用了个软件，它说我欠你一个电话。我会打给你的，你等我。这几天忙完就打，你别做饭了，等我电话。真的。")
        self.assertTrue(any("具体时间" in e for e in errors))
        errors, _ = self._errs(send_text="妈，我用了个软件，它把咱俩这半年的聊天记录算了一遍，说我欠你一个电话。今晚 8 点打给你，你别做饭了，等我电话。")
        self.assertFalse(any("具体时间" in e for e in errors))

    def test_exclamation_blacklist_judgment(self):
        errors, _ = self._errs(she_means=self.N["she_means"] + " 她真的很温暖！你不该这么敷衍她。")
        self.assertTrue(any("感叹号" in e for e in errors))
        self.assertTrue(any("温暖" in e for e in errors))
        self.assertTrue(any("敷衍" in e for e in errors))

    def test_quoted_original_text_is_not_flagged(self):
        """引号里她的原话带感叹号不算；replies[].to 和 dictionary[].her 是照抄的，不查黑名单"""
        errors, _ = self._errs(she_means=self.N["she_means"] + " 她说“发烧了？多少度 喝水了吗 去医院了没”。")
        self.assertFalse(any("感叹号" in e for e in errors))

    def test_evidence_check(self):
        errors, _ = self._errs(she_means=self.N["she_means"] + " 她还说过“你怎么老不回家”。")
        self.assertTrue(any("你怎么老不回家" in e for e in errors))
        # 引的是她没说过的话（否定句）、或用户回答的话，不查
        errors, _ = self._errs(she_means=self.N["she_means"] + " 她从来没说过“我想你”。你说“上次回去是过年”。")
        self.assertFalse(any("我想你" in e or "过年" in e for e in errors))
        # 空格和标点不影响匹配
        errors, _ = self._errs(she_means=self.N["she_means"] + " 8 月她说“打扰你了，你忙吧”。")
        self.assertFalse(any("打扰你了" in e for e in errors))

    def test_dictionary_must_quote_her(self):
        N = copy.deepcopy(self.N)
        N["dictionary"] = N["dictionary"][:5] + [{"her": "你什么时候带对象回来", "means": "我等不及了"}]
        errors, warnings = ln.lint(N, self.S, self.M)
        self.assertTrue(any("dictionary[5]" in e for e in errors))
        N["dictionary"][5] = {"her": "周末回来吗", "means": "这句翻译写得太长了超过十八个字肯定会被提醒的"}
        errors, warnings = ln.lint(N, self.S, self.M)
        self.assertFalse(any("dictionary[5]" in e for e in errors))
        self.assertTrue(any("18 字" in w for w in warnings))

    def test_length_and_count_warnings(self):
        _, warnings = self._errs(she_means="太短了。", tonight=["只有一件"], call_openers=["一句"])
        blob = "\n".join(warnings)
        self.assertIn("she_means", blob)
        self.assertIn("tonight", blob)
        self.assertIn("call_openers", blob)

    def test_numbers_must_trace_to_stats(self):
        _, warnings = self._errs(she_means=self.N["she_means"].replace("19 次吃饭", "1234 次吃饭"))
        self.assertTrue(any("1234" in w for w in warnings))
        _, warnings = self._errs(she_means=self.N["she_means"] + " 8 月 14 日早上 7 点 15 分。")   # 日期时间不算
        self.assertFalse(any("找不到" in w for w in warnings))

    def test_without_stats_and_messages(self):
        errors, warnings = ln.lint(self.N)
        self.assertEqual(errors, [])


class LintCli(unittest.TestCase):
    def test_exit_codes(self):
        r = run("lint_narrative.py", SAMPLE_NARR, "--stats", SAMPLE_STATS, "--messages", SAMPLE)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("✓", r.stdout)
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("{oops")
            r = run("lint_narrative.py", bad)
            self.assertEqual(r.returncode, 1)
            self.assertIn("JSON", r.stdout)
            N = load(SAMPLE_NARR)
            N["she_means"] = "太短。"
            short = os.path.join(d, "short.json")
            save(short, N)
            self.assertEqual(run("lint_narrative.py", short).returncode, 0)                 # 只是提醒
            self.assertEqual(run("lint_narrative.py", short, "--strict").returncode, 1)     # 严格模式提醒也算失败
            N["send_text"] = "没有时间的承诺"
            save(short, N)
            self.assertEqual(run("lint_narrative.py", short).returncode, 1)


if __name__ == "__main__":
    unittest.main()
