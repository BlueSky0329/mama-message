# -*- coding: utf-8 -*-
"""
"一处定义，三处同步"变成测试：metrics.md、types.md、prompts/普通用户版.md 里复述的公式、阈值、词表，
必须和 scripts/stats.py 顶部的常量、references/lexicon.json 一致。改了哪边都会在这里红。
"""
import os
import re
import unittest

from helpers import REFERENCES, ROOT, read

import _common   # noqa: E402
import stats     # noqa: E402

METRICS = read(os.path.join(REFERENCES, "metrics.md"))
TYPES = read(os.path.join(REFERENCES, "types.md"))
PROMPT = read(os.path.join(ROOT, "prompts", "普通用户版.md"))
RULES = read(os.path.join(REFERENCES, "writing-rules.md"))
SKILL = read(os.path.join(ROOT, "SKILL.md"))
TEMPLATE = read(os.path.join(REFERENCES, "report-template.md"))
LEX = _common.load_lexicon()

# MODES 的版块名 → 文档里的叫法
BLOCK_CN = {"rating": "评级", "countdown": "倒计时", "unanswered": "没回", "signals": "信号", "gap": "多久没主动找",
            "tonight": "今晚三件事", "replies": "帮你回", "openers": "开场白", "bill": "账单", "send": "发给她的一条"}


def line_with(text, marker):
    for line in text.split("\n"):
        if marker in line:
            return line
    raise AssertionError(f"找不到含“{marker}”的行")


def decimals(s):
    return [float(x) for x in re.findall(r"\d\.\d+", s)]


def pct(x):
    return f"{round(x * 100)}%"


class Formulas(unittest.TestCase):
    def test_care_weights(self):
        f = stats.FORMULA["care"]
        want = [f["her_open_ratio"], f["care_ratio"], f["offhour_ratio"], f["density"]]
        self.assertEqual(decimals(line_with(METRICS, "牵挂指数** ="))[:4], want)
        self.assertEqual(decimals(line_with(PROMPT, "牵挂指数 ="))[:4], want)
        self.assertIn(f"÷ {f['density_per_day']}", line_with(METRICS, "平均每个活跃日"))
        self.assertIn(f"/{f['density_per_day']}, 1)", line_with(PROMPT, "牵挂指数 ="))

    def test_short_weights(self):
        f = stats.FORMULA["short"]
        want = [f["short_ratio"], f["unanswered_ratio"], f["latency"]]
        self.assertEqual(decimals(line_with(METRICS, "嗯哦好指数** ="))[:3], want)
        self.assertEqual(decimals(line_with(PROMPT, "嗯哦好指数 ="))[:3], want)
        self.assertIn(f"÷ {f['latency_cap_h']}", line_with(METRICS, "回复中位小时数"))
        self.assertIn(f"/{f['latency_cap_h']}, 1)", line_with(PROMPT, "嗯哦好指数 ="))

    def test_forgive_weights(self):
        f = stats.FORMULA["forgive"]
        want = [f["reopen_ratio"], f["no_chase"]]
        self.assertEqual(decimals(line_with(METRICS, "不计较指数** ="))[:2], want)
        self.assertEqual(decimals(line_with(PROMPT, "不计较指数 ="))[:2], want)

    def test_rating_bands(self):
        bands = list(stats.RATING_BANDS)
        for i, (upper, label) in enumerate(bands):
            lo = bands[i - 1][0] if i else None
            rng = f"< {upper}" if lo is None else (f"≥ {lo}" if upper is None else f"{lo}–{upper - 1}")
            self.assertIn(f"- {rng} {label}", METRICS)                       # metrics.md：- < 25 模范子女
            self.assertRegex(TYPES, rf"\| {label}\s*\|\s*{rng}\s*\|")         # types.md 表格：| 模范子女 | < 25 |
        # 普通用户版写成一行
        line = line_with(PROMPT, "综合评级：分 =")
        self.assertIn(f"<{bands[0][0]} {bands[0][1]}", line)
        self.assertIn(f"{bands[0][0]}–{bands[1][0] - 1} {bands[1][1]}", line)
        self.assertIn(f"≥{bands[3][0]} {bands[4][1]}", line)
        for doc in (METRICS, TYPES, PROMPT):
            self.assertRegex(doc, rf"嗯哦好指数 \+ {stats.RED_WEIGHT} ?× ?红灯数")


class Thresholds(unittest.TestCase):
    def test_basic_thresholds(self):
        self.assertIn(f"间隔 ≥ {stats.OPEN_GAP_H} 小时", METRICS)
        self.assertIn(f"隔了 {stats.OPEN_GAP_H} 小时以上", PROMPT)
        self.assertIn(f"{stats.REPLY_WINDOW_H} 小时", METRICS)
        self.assertIn(f"{stats.REPLY_WINDOW_H} 小时内", PROMPT)
        self.assertIn(f"字数 ≤ {stats.SHORT_MAX_CHARS}", METRICS)
        self.assertIn(f"字数 ≤ {stats.SHORT_MAX_CHARS}", PROMPT)
        self.assertIn(f"不足 {stats.PEAK_MIN_MSGS} 条", METRICS)
        self.assertIn(f"不到 {stats.PEAK_MIN_MSGS} 条", PROMPT)
        self.assertIn(f"跨度 ≥ {stats.TREND_MIN_SPAN_DAYS} 天", METRICS)

    def test_signal_thresholds(self):
        R = stats.SIGNAL_RULES
        self.assertIn(f"≤ {R['health_reply_chars']} 个字", METRICS)
        self.assertIn(f"不超过 {R['health_reply_chars']} 个字", PROMPT)
        self.assertIn(f"≥ {R['self_shrink_min']} 次", METRICS)
        self.assertIn(f"{R['sticker_mult']} 倍以上且 ≥ {round(R['sticker_min'] * 100)}%", METRICS)
        self.assertIn(f"少 {abs(R['opens_drop_pct'])}% 以上", METRICS)
        self.assertIn(f"≥ {R['nothing_min']} 次", METRICS)
        self.assertIn(f"≥ {R['my_open_gap_days']} 天前", METRICS)
        self.assertIn(f"超过 {R['my_open_gap_days']} 天", PROMPT)

    def test_child_type_thresholds(self):
        R = stats.CHILD_RULES
        self.assertIn(f"短回复占比 ≥ {pct(R['short_ratio'])}", TYPES)
        self.assertIn(f"没回占比 ≥ {pct(R['unanswered_ratio'])}", TYPES)
        self.assertIn(f"< {round(R['fast_h'] * 60)} 分钟且短回复 ≥ {pct(R['fast_short_ratio'])}", TYPES)
        self.assertIn(f"{stats.HOUR_RULES['me_late_from']} 点后的消息 ≥ {pct(R['late_ratio'])}", TYPES)
        self.assertIn(f"≥ {pct(R['weekend_ratio'])} 在周末", TYPES)
        self.assertIn(f"问身体 ≥ {R['body_asks']} 次", TYPES)
        self.assertIn(f"短回复≥{pct(R['short_ratio'])}", PROMPT)
        self.assertIn(f"没回≥{pct(R['unanswered_ratio'])}", PROMPT)
        self.assertIn(f"{stats.HOUR_RULES['me_late_from']} 点后的消息≥{pct(R['late_ratio'])}", PROMPT)
        self.assertIn(f"问身体≥{R['body_asks']} 次", PROMPT)

    def test_mother_type_thresholds(self):
        R = stats.MOTHER_RULES
        self.assertIn(f"她开启 < {pct(R['wait_open_ratio'])} 但回你 < {R['wait_fast_s'] // 60} 分钟", TYPES)
        self.assertIn(f"> {R['secondary_min']}", TYPES)


class Modes(unittest.TestCase):
    """口吻表：SKILL.md 和 writing-rules.md 各有一张，和 _common.MODES 逐行比"""
    def _table(self, doc):
        rows = {}
        for line in doc.split("\n"):
            m = re.match(r"^\| `(\w+)`[^|]*\|([^|]*)\|([^|]*)\|$", line)
            if m:
                rows[m.group(1)] = (m.group(2).strip(), m.group(3).strip())
        return rows

    def test_mode_tables_match_code(self):
        for name, doc in (("SKILL.md", SKILL), ("writing-rules.md", RULES)):
            rows = self._table(doc)
            self.assertEqual(set(rows), set(_common.MODES), name)
            for mode, spec in _common.MODES.items():
                when, hidden = rows[mode]
                self.assertEqual(when, spec["when"], f"{name} {mode} 的“什么时候”")
                blocks = [b for b in spec["hide"] if not b.startswith("card-")]
                for b in blocks:
                    self.assertIn(BLOCK_CN[b], hidden, f"{name} {mode} 没写去掉 {b}")
                for b, cn in BLOCK_CN.items():
                    if b not in spec["hide"] and cn in hidden and not (b == "unanswered" and spec["unanswered_max"] < 5):
                        self.fail(f"{name} {mode} 写了去掉“{cn}”，代码里没去掉")
                cards_off = {"card-bill", "card-send"} <= set(spec["hide"])
                self.assertEqual(cards_off, "两张卡都不出" in hidden or "只出报告" in hidden, f"{name} {mode} 的卡片")
                if spec["unanswered_max"] not in (0, 5):
                    self.assertIn(f"只列 {spec['unanswered_max']} 条", hidden, f"{name} {mode}")

    def test_template_lists_modes_and_required(self):
        self.assertIn(" / ".join(_common.MODES), TEMPLATE)
        for mode in ("neutral", "memorial", "third"):
            dropped = [f for f in _common.NARRATIVE_REQUIRED if f not in _common.required_fields(mode)]
            line = line_with(TEMPLATE, f"`{mode}` ")
            for f in dropped:
                self.assertIn(f"`{f}`", line, f"report-template 里 {mode} 不用写的字段")


class WritingMaterial(unittest.TestCase):
    def test_material_thresholds(self):
        self.assertIn("、".join(f"{a}–{b}" for a, b in stats.MEAL_HOURS) + " 点", METRICS)
        self.assertIn(f'≥ {stats.SELF_MIN_CHARS} 字的"我……"', METRICS)
        self.assertIn(f"最近 {stats.SELF_ITEMS_MAX} 条", METRICS)
        R = stats.SENSITIVITY_RULES
        self.assertIn(f"≥ {R['conflict_min']} 条建议 `neutral`", METRICS)
        self.assertIn(f"≥ {pct(R['marriage_ratio'])}", METRICS)
        self.assertIn(f"≥ {R['stale_days']} 天", METRICS)
        for key in ("self_words", "question", "conflict"):
            self.assertIn(f"`{key}`", METRICS, key)


class Lexicon(unittest.TestCase):
    def test_topics_listed_in_order(self):
        self.assertIn(" / ".join(LEX["topics"]), METRICS)
        self.assertIn("/".join(LEX["care_topics"]), METRICS)

    def test_prompt_word_lists_are_subsets(self):
        """普通用户版是简写，列出来的词至少要在词表里"""
        m = re.search(r"她说\"([^\"]+)\"的次数", PROMPT)
        self.assertIsNotNone(m)
        for w in m.group(1).split("/"):
            self.assertIn(w, LEX["chase"], w)
        m = re.search(r"用\"([^\"]+)\"收尾", PROMPT)
        self.assertIsNotNone(m)
        for w in m.group(1).split("/"):
            self.assertIn(w, LEX["self_shrink"], w)
        for w in ("腰疼", "检查", "医院", "血压"):
            self.assertTrue(any(k in w for k in LEX["health_red"]), w)

    def test_metrics_examples_come_from_lexicon(self):
        for key, marker in (("chase", "`chase`："), ("self_shrink", "`self_shrink`："), ("health_red", "`health_red`：")):
            line = line_with(METRICS, marker)
            listed = re.search(marker + r"([^）……]+)", line).group(1)
            for w in re.split(r"\s*/\s*", listed):
                self.assertIn(w.strip(), LEX[key], w)
        self.assertIn("references/lexicon.json", METRICS)

    def test_short_reply_defined_by_length_not_word_set(self):
        """短回复的定义是 ≤ 3 字，词只是例子；三处不能再各列一套词表"""
        for doc in (METRICS, PROMPT):
            self.assertNotIn("或属于", doc)
            self.assertNotIn("属于集合", doc)


if __name__ == "__main__":
    unittest.main()
