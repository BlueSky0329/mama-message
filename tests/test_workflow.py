# -*- coding: utf-8 -*-
"""
v0.6 加的那一层：写作素材（stats 的 self / meal / voice / sensitivity）、brief.py、口吻（MODES）怎么落到报告上、
对照卡、mama.py 一条命令（run / finish / explain / compare / practice / status）、卡片出 PNG。只用标准库。
"""
import copy
import os
import re
import shutil
import tempfile
import unittest
from datetime import date

from helpers import EXAMPLES, SAMPLE, SAMPLE_NARR, SAMPLE_STATS, base, load, msg, read, run, save

import _common     # noqa: E402
import brief       # noqa: E402
import render      # noqa: E402
import snap        # noqa: E402
import stats       # noqa: E402

FRIEND = os.path.join(EXAMPLES, "sample-friend-messages.json")
TODAY = date(2026, 8, 30)


class WritingMaterial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load(SAMPLE)
        cls.S = stats.compute(cls.data, today=TODAY, her_birthday="10-20", my_birthday="06-03")

    def test_self_mentions_on_sample(self):
        sf = self.S["self"]
        self.assertEqual(sf["count"], 1)
        it = sf["items"][0]
        self.assertEqual(it["content"], "最近腰不太好 医生说要少干活")
        self.assertEqual(it["reply"]["content"], "注意休息")
        self.assertEqual((it["i_mentioned_again"], it["she_mentioned_again"]), (0, 0))
        self.assertEqual(self.data["messages"][it["i"]]["content"], it["content"])     # i 指回 messages.json

    def test_self_mention_rules(self):
        ms = [msg("2026-05-01T08:00:00", "her", "你爸住院了 明天手术"),          # 家里的事：“你爸”不算在说你
              msg("2026-05-01T09:00:00", "me", "严重吗"),
              msg("2026-05-02T08:00:00", "her", "腰还疼不疼"),                  # X不X：在问你
              msg("2026-05-03T08:00:00", "her", "你多穿点 别感冒"),             # 在叮嘱你
              msg("2026-05-04T08:00:00", "her", "我今天一个人去公园转了转"),    # “一个人”
              msg("2026-05-05T08:00:00", "her", "我知道了")]                    # 太短，不算
        S = stats.compute(base(ms), today=TODAY)
        self.assertEqual([x["content"] for x in S["self"]["items"]], ["你爸住院了 明天手术", "我今天一个人去公园转了转"])
        self.assertEqual(S["self"]["items"][0]["reply"]["content"], "严重吗")
        self.assertIsNone(S["self"]["items"][1]["reply"])

    def test_meal_timing(self):
        m = self.S["meal"]
        self.assertEqual(m["asks"], 19)
        self.assertEqual(m["at_meal"] + m["off_meal"], 19)
        self.assertEqual(m["off_meal"], 11)
        ms = [msg("2026-05-01T12:10:00", "her", "吃饭了吗"), msg("2026-05-01T22:50:00", "her", "今天吃的什么")]
        S = stats.compute(base(ms), today=TODAY)
        self.assertEqual((S["meal"]["at_meal"], S["meal"]["off_meal"]), (1, 1))

    def test_shrink_context_and_unanswered_diagnostics(self):
        ph, u = self.S["phrases"], self.S["unanswered"]
        self.assertEqual((ph["self_shrink"], ph["self_shrink_after_my_short"]), (8, 6))
        self.assertLessEqual(u["was_her_reply"], u["count"])
        self.assertLessEqual(u["ended_with_closer"], u["count"])
        # 我说“妈我到了”，她回“好 到了就好”，第二天她又开口：算没回，但口径诊断要认出这是她在回我
        ms = [msg("2026-05-01T20:00:00", "me", "妈 我到了"), msg("2026-05-01T20:01:00", "her", "好 到了就好"),
              msg("2026-05-02T08:00:00", "her", "吃饭了吗")]
        S = stats.compute(base(ms), today=TODAY)
        self.assertEqual(S["unanswered"]["was_her_reply"], 1)

    def test_voice_profile(self):
        v = self.S["voice"]["her"]
        self.assertGreater(v["text_n"], 0)
        self.assertTrue(0 <= v["punct_ratio"] <= 1 and 0 <= v["space_ratio"] <= 1)
        self.assertGreaterEqual(v["burst"], 1)
        self.assertTrue(v["openers"] and v["after_my_short"])
        self.assertEqual(self.S["voice"]["me"]["longest"]["chars"], max(len(m["content"].strip()) for m in self.data["messages"]
                                                                        if m["sender"] == "me" and m["type"] == "text"))

    def test_sensitivity(self):
        self.assertIsNone(self.S["sensitivity"]["suggest"])
        ms = [msg(f"2026-05-{d:02d}T08:00:00", "her", w) for d, w in ((1, "滚 别管我"), (2, "白养你了"), (3, "没良心的东西"))]
        S = stats.compute(base(ms * 8), today=TODAY)
        self.assertEqual(S["sensitivity"]["suggest"], "neutral")
        S = stats.compute(base([msg("2025-01-01T08:00:00", "her", "吃饭了吗")] * 25), today=TODAY)
        self.assertTrue(any("memorial" in r for r in S["sensitivity"]["reasons"]))    # 最后一条是一年多以前：先问情况

    def test_tz_and_source_in_stats(self):
        d = copy.deepcopy(self.data)
        d["tz"], d["source_detail"] = "+08:00", "weflow-json 1.0.3 · utf-8"
        S = stats.compute(d, today=TODAY)
        self.assertEqual((S["basics"]["tz"], S["source_detail"]), ("+08:00", "weflow-json 1.0.3 · utf-8"))


class Brief(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.S = load(SAMPLE), load(SAMPLE_STATS)
        cls.text = brief.make_brief(cls.S, cls.data)

    def test_sections(self):
        for h in ("## 1. 数字", "## 2. 她说起自己的事", "## 3. 她发了，你没回", "## 4. 她最常问的", "## 5. 她说过不止一次的话",
                  "## 6. 你的回复", "## 7. 节日那天", "## 8. 她转给你的", "## 9. 她的说话方式", "## 10. 要不要收着", "## 11. narrative.json"):
            self.assertIn(h, self.text)

    def test_quotes_in_brief_are_real(self):
        """brief 里引号里的原话，必须是记录里真有的——AI 会照着抄，lint 会照着查"""
        corpus = [re.sub(r"\s", "", m["content"]) for m in self.data["messages"]]
        body = self.text[:self.text.index("## 11.")]            # 第 11 节是 narrative.json 的骨架，不是原话
        quotes = set(re.findall(r"“([^”\n]{1,80})”", body))
        self.assertGreater(len(quotes), 30)
        for q in quotes:
            nq = re.sub(r"\s", "", q)
            self.assertTrue(any(nq in c for c in corpus), q)

    def test_reply_targets_are_text(self):
        for line in self.text.splitlines():
            if "replies[].to 写" in line:
                self.assertNotIn("“[", line)                 # 不让 AI 去回一个表情

    def test_bounded_size_on_big_record(self):
        """记录再长，brief 也就几千字"""
        big = base([msg(f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}T{h:02d}:00:00", "her" if h % 2 else "me",
                        ["吃饭了吗", "嗯", "降温了 多穿点", "好", "最近腰不太好", "知道了"][(d + h) % 6])
                    for d in range(300) for h in range(7, 22)])
        S = stats.compute(big, today=date(2026, 12, 31))
        text = brief.make_brief(S, big)
        self.assertLess(len(text), 9000)

    def test_rejects_old_stats(self):
        S = copy.deepcopy(self.S)
        S.pop("self")
        with self.assertRaises(ValueError):
            brief.make_brief(S, self.data)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "brief.md")
            r = run("brief.py", SAMPLE_STATS, SAMPLE, "--out", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(read(out), self.text)


class Modes(unittest.TestCase):
    def test_strip_blocks(self):
        t = "a<!--#x-->X<!--#y-->Y<!--/y--><!--/x-->b<!--#y-->Y2<!--/y-->"
        self.assertEqual(render.strip_blocks(t, set()), "aXYbY2")
        self.assertEqual(render.strip_blocks(t, {"y"}), "aXb")
        self.assertEqual(render.strip_blocks(t, {"x"}), "abY2")

    def test_every_mode_renders_and_hides(self):
        S, N0 = load(SAMPLE_STATS), load(SAMPLE_NARR)
        markers = {"rating": "综合评级", "countdown": 'class="countdown"', "unanswered": "发了，你没回", "signals": "该打电话了",
                   "gap": "天没有主动找", "tonight": "今晚就做的三件事", "replies": "<h2>帮你回</h2>", "openers": "三句打电话的开场白",
                   "bill": "<h2>亲情账单</h2>", "send": "可以直接发给"}
        for mode, spec in _common.MODES.items():
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                N = dict(N0, mode=mode)
                res = render.render_all(S, N, d)
                html = read(res["files"]["report"])
                self.assertNotIn("<!--", html)
                self.assertNotIn("{{", html)
                for block, marker in markers.items():
                    (self.assertNotIn if block in spec["hide"] else self.assertIn)(marker, html, block)
                for card in ("card-bill", "card-send"):
                    self.assertEqual(card in res["files"], card not in spec["hide"], card)

    def test_gentle_lists_fewer_unanswered_and_drops_stale_cards(self):
        S, N = load(SAMPLE_STATS), load(SAMPLE_NARR)
        with tempfile.TemporaryDirectory() as d:
            render.render_all(S, N, d)
            self.assertEqual(read(os.path.join(d, "mama-message-report.html")).count('class="bubble"'), 5)
            render.render_all(S, dict(N, mode="gentle"), d)
            self.assertEqual(read(os.path.join(d, "mama-message-report.html")).count('class="bubble"'), 2)
            open(os.path.join(d, "mama-message-card-send.png"), "wb").close()
            res = render.render_all(S, dict(N, mode="memorial"), d)
            self.assertFalse(os.path.exists(os.path.join(d, "mama-message-card-send.html")))   # 上次的卡删掉，免得发出去
            self.assertFalse(os.path.exists(os.path.join(d, "mama-message-card-send.png")))
            self.assertEqual(res["skipped"], ["card-bill", "card-send"])

    def test_footnote_carries_warnings(self):
        S = stats.compute(base([msg(None, "her", "吃饭了吗"), msg(None, "me", "嗯")] * 12), today=TODAY)
        S["basics"]["tz"] = "+08:00"
        with tempfile.TemporaryDirectory() as d:
            html = read(render.render_all(S, {}, d)["files"]["report"])
        self.assertIn("没有时间戳", html)
        self.assertIn("UTC+08:00", html)

    def test_bad_mode_cli(self):
        with tempfile.TemporaryDirectory() as d:
            N = load(SAMPLE_NARR)
            N["mode"] = "sad"
            np_ = os.path.join(d, "n.json")
            save(np_, N)
            r = run("render.py", SAMPLE_STATS, np_, "--out", d)
            self.assertEqual(r.returncode, 1)
            self.assertIn("mode", r.stdout)


class CompareCard(unittest.TestCase):
    def test_messages_in_card_out(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "sub", "compare.json")
            r = run("compare.py", SAMPLE, FRIEND, "--labels", "你妈", "朋友", "--today", "2026-08-30", "--out", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            c = load(out)
            self.assertIn("差了", c["verdict"])
            html = read(os.path.join(d, "sub", "mama-message-card-compare.html"))
            self.assertNotIn("{{", html)
            self.assertLess(html.index("你回朋友"), html.index("你回你妈"))     # 先摆朋友：视频开头那一帧
            self.assertIn("差了", html)


class MamaCli(unittest.TestCase):
    def test_run_finish_explain_status(self):
        with tempfile.TemporaryDirectory() as d:
            w = os.path.join(d, "out")
            r = run("mama.py", "run", SAMPLE, "--call", "妈妈", "--today", "2026-08-30", "--her-birthday", "10-20",
                    "--my-birthday", "06-03", "--dir", w)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for f in ("messages.json", "stats.json", "brief.md", "run.json"):
                self.assertTrue(os.path.exists(os.path.join(w, f)), f)
            S = load(os.path.join(w, "stats.json"))
            golden = load(SAMPLE_STATS)
            self.assertEqual(S["index"], golden["index"])
            self.assertIn("finish", r.stdout)
            r = run("mama.py", "finish", "--dir", w)
            self.assertEqual(r.returncode, 1)                                   # 还没写 narrative
            self.assertIn("narrative.json", r.stdout)
            shutil.copyfile(SAMPLE_NARR, os.path.join(w, "narrative.json"))
            r = run("mama.py", "finish", "--dir", w)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.exists(os.path.join(w, "reports", "mama-message-card-send.html")))
            for what in ("短回复", "没回", "开口", "回复", "自己", "收尾", "没事", "追问", "信号", "节日"):
                r = run("mama.py", "explain", what, "--dir", w)
                self.assertEqual(r.returncode, 0, what + r.stdout + r.stderr)
            r = run("mama.py", "explain", "主题", "吃饭", "--dir", w, "--all")
            self.assertEqual(r.stdout.count("她：“"), 19)
            r = run("mama.py", "explain", "收尾", "--dir", w)
            self.assertIn("打扰你了 你忙吧", r.stdout)
            r = run("mama.py", "status", "--dir", w)
            self.assertIn("都好了", r.stdout)
            N = load(SAMPLE_NARR)
            N["she_means"] += "她真的很温暖！"
            save(os.path.join(w, "narrative.json"), N)
            r = run("mama.py", "finish", "--dir", w)
            self.assertEqual(r.returncode, 1)                                   # lint 有 ✗ 就不出

    def test_new_record_moves_old_narrative_aside(self):
        """同一个 mama-out 换了一份记录：上一次的 narrative.json 不能配这次的数字，改名留着；重跑同一份不动它"""
        with tempfile.TemporaryDirectory() as d:
            w = os.path.join(d, "out")
            self.assertEqual(run("mama.py", "run", SAMPLE, "--today", "2026-08-30", "--dir", w).returncode, 0)
            shutil.copyfile(SAMPLE_NARR, os.path.join(w, "narrative.json"))
            self.assertEqual(run("mama.py", "run", os.path.join(w, "messages.json"), "--today", "2026-08-30", "--dir", w).returncode, 0)
            self.assertTrue(os.path.exists(os.path.join(w, "narrative.json")))
            r = run("mama.py", "run", FRIEND, "--today", "2026-08-30", "--dir", w)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertFalse(os.path.exists(os.path.join(w, "narrative.json")))
            self.assertTrue(os.path.exists(os.path.join(w, "narrative.old.json")))

    def test_run_reports_parse_errors(self):
        with tempfile.TemporaryDirectory() as d:
            from helpers import FIXTURES
            r = run("mama.py", "run", os.path.join(FIXTURES, "twoline.txt"), "--dir", os.path.join(d, "o"))
            self.assertEqual(r.returncode, 1)
            self.assertIn("--her", r.stdout)

    def test_compare_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            for name, src in (("妈", SAMPLE), ("朋友", FRIEND)):
                r = run("mama.py", "run", src, "--today", "2026-08-30", "--dir", os.path.join(d, name))
                self.assertEqual(r.returncode, 0, r.stdout)
            r = run("mama.py", "compare", os.path.join(d, "妈"), os.path.join(d, "朋友"), "--labels", "你妈", "朋友",
                    "--out", os.path.join(d, "cmp"))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.exists(os.path.join(d, "cmp", "mama-message-card-compare.html")))

    def test_practice_score(self):
        import mama
        sc = mama.score_practice(["嗯", "注意休息", "吃了 公司楼下吃的", "周六中午我回去", "你腰好点没"], load(SAMPLE_STATS), load(SAMPLE))
        self.assertEqual(sc["n"], 5)
        self.assertEqual(sc["short"], 1)
        self.assertEqual(sc["asked"], 1)
        self.assertGreaterEqual(sc["specific"], 2)
        self.assertEqual([x["reply"] for x in sc["same_as_record"]], ["注意休息", "吃了 公司楼下吃的"])   # 一个字的“嗯”撞上不算
        self.assertEqual(mama.practice_replies("妈：吃了吗\n我：吃了\n妈：吃的啥\n我：面条"), ["吃了", "面条"])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("嗯\n注意休息\n")
            r = run("mama.py", "practice", p, "--dir", d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("短回复 1 条", r.stdout)


@unittest.skipUnless(snap.find_browser(), "本机没有 Chrome / Edge / Chromium，跳过出图")
class Png(unittest.TestCase):
    def test_card_png(self):
        with tempfile.TemporaryDirectory() as d:
            res = render.render_all(load(SAMPLE_STATS), load(SAMPLE_NARR), d, png=True)
            if res["png_error"] and os.environ.get("CI"):
                self.skipTest("CI 上的浏览器跑不起来：" + res["png_error"])     # 本机跑不起来照样算失败
            self.assertIsNone(res["png_error"], res["png_error"])
            w, h = snap.png_size(res["png"]["card-send"])
            self.assertEqual(w, 780)                     # 390 × 2 倍
            self.assertGreater(h, 1000)
            self.assertFalse(os.path.exists(os.path.join(d, ".snap-tmp")))


if __name__ == "__main__":
    unittest.main()
