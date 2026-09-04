#!/usr/bin/env python3
"""
检查 narrative.json（AI 写的文字部分）有没有违反写作规矩。出报告前跑一遍，把"出报告前自检"变成脚本。

查什么：
  必填字段齐不齐；字数（她其实想说的是 120–220、发给她的 60–100、翻译 ≤ 18 字、帮你回 ≤ 40 字）；
  发给她的那条有没有具体时间；有没有感叹号；黑名单短语（从 references/writing-rules.md 读，一处定义）；
  "敷衍 / 不孝 / 你应该 / 冷漠 / 作为子女"这类评判词；
  给了 --messages 就核对证据：引号里的"原话"必须在记录里真出现过（不编造，机器查）；
  给了 --stats 就核对数字：文字里的数字要能在 stats.json 里找到（找不到只是提醒，可能是加总）。

用法:
  python scripts/lint_narrative.py narrative.json [--stats stats.json] [--messages messages.json] [--strict]

退出码：0 通过（可以有提醒）；1 有错误。--strict 时提醒也算失败。只读，不改文件。只用标准库。
"""
import argparse
import json
import os
import re
import sys

from _common import REFERENCES, load_json, setup_utf8

setup_utf8()

REQUIRED = ("she_means", "send_text", "dictionary", "tonight", "replies", "call_openers", "type_lines")
JUDGMENT = ("敷衍", "不孝", "你应该", "冷漠", "作为子女", "作为孩子", "作为儿女")
TIME_RE = re.compile(r"(今晚|今天|明天|明晚|后天|周[一二三四五六日天末]|礼拜[一二三四五六日天]|星期[一二三四五六日天]|"
                     r"\d+\s*[点日号]|中午|晚上|早上|下午|傍晚|睡前|下班|周末|放假|节)")
QUOTE_RE = re.compile(r"[“\"「]([^”\"」\n]{1,80})[”\"」]")
NOISE_RE = re.compile(r"[\s，。！？、；：“”\"'‘’（）()《》〈〉【】\[\]—\-–~～…·,.!?;:]+")
DATE_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2})?|\d{1,2}:\d{2}|\d{1,2}\s*月\s*\d{1,2}\s*[日号]?|"
                          r"\d{1,2}\s*[月日号]|\d{1,2}\s*点(?:\s*\d{1,2}\s*分?)?|\d{1,2}\s*分")
FALLBACK_BLACKLIST = ["作为一个 AI", "作为 AI", "希望对你有帮助", "我理解你的感受", "值得注意的是", "综上所述", "总的来说",
                      "让我们", "不妨", "无论如何", "在这个快节奏的时代", "温暖", "治愈", "破防", "泪目", "世界上最",
                      "默默付出", "无私", "岁月", "时光", "陪伴是最长情的告白", "树欲静而风不止", "子欲养而亲不待"]


def load_blacklist(path=None):
    """从 writing-rules.md 的「反 AI 短语黑名单」一节读词表，读不到就用内置副本。"""
    p = path or os.path.join(REFERENCES, "writing-rules.md")
    try:
        with open(p, encoding="utf-8") as f:
            lines = f.read().split("\n")
    except OSError:
        return list(FALLBACK_BLACKLIST)
    for i, line in enumerate(lines):
        if line.strip().startswith("## 反 AI 短语黑名单"):
            for l2 in lines[i + 1:]:
                if " / " in l2:
                    return [w.strip() for w in l2.split(" / ") if w.strip()]
    return list(FALLBACK_BLACKLIST)


def norm(s):
    return NOISE_RE.sub("", s or "")


def chars(s):
    """字数：去掉空白后的字符数。"""
    return len(re.sub(r"\s", "", s or ""))


def strings_of(obj, path=""):
    """narrative 里所有字符串及其路径，如 replies[1].draft。"""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            for x in strings_of(v, f"{path}.{k}" if path else k):
                yield x
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            for x in strings_of(v, f"{path}[{i}]"):
                yield x


def numbers_in_stats(S):
    """stats.json 里出现过的所有整数，加上比例换算成的百分数、秒数换算成的分钟和小时。"""
    acc = set()

    def walk(o):
        if isinstance(o, bool):
            return
        if isinstance(o, int):
            acc.add(o)
        elif isinstance(o, float):
            acc.update({int(o), round(o), round(o * 100), int(o * 100), round(o / 60), round(o / 3600), int(o // 60), int(o // 3600)})
        elif isinstance(o, str):
            for n in re.findall(r"\d+", o):
                acc.add(int(n))
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(S)
    return acc


def lint(N, S=None, msgs=None, blacklist=None):
    """返回 (errors, warnings)。N 是 narrative dict，S 是 stats dict，msgs 是 messages.json 的 dict。"""
    errors, warnings = [], []
    if not isinstance(N, dict):
        return ["narrative.json 顶层不是对象"], []
    blacklist = blacklist if blacklist is not None else load_blacklist()

    # 1. 必填字段
    for k in REQUIRED:
        if not N.get(k):
            errors.append(f"缺必填字段 {k}")
    tl = N.get("type_lines") or {}
    if isinstance(tl, dict):
        for k in ("mother", "child"):
            if not tl.get(k):
                errors.append(f"缺必填字段 type_lines.{k}")
    else:
        errors.append("type_lines 应该是对象 {\"mother\": …, \"child\": …}")

    # 2. 字数与条数
    sm = N.get("she_means") or ""
    if sm and not (120 <= chars(sm) <= 220):
        warnings.append(f"she_means 是 {chars(sm)} 字，规矩是 120–220")
    st = N.get("send_text") or ""
    if st and not (60 <= chars(st) <= 100):
        warnings.append(f"send_text 是 {chars(st)} 字，规矩是 60–100")
    if st and not TIME_RE.search(st):
        errors.append("send_text 里没有具体时间（今晚 8 点 / 周六中午 这样的），没有时间的承诺她不会当真")
    d = N.get("dictionary") or []
    if isinstance(d, list):
        if d and not (6 <= len(d) <= 10):
            warnings.append(f"dictionary 有 {len(d)} 条，规矩是 6–10 条（记录不够就少列，不硬凑）")
        for i, item in enumerate(d):
            if not isinstance(item, dict) or not item.get("her") or not item.get("means"):
                errors.append(f"dictionary[{i}] 要有 her 和 means 两个字段")
            elif chars(item["means"]) > 18:
                warnings.append(f"dictionary[{i}] 的翻译 {chars(item['means'])} 字，规矩是 ≤ 18 字：{item['means']}")
    else:
        errors.append("dictionary 应该是数组")
    tn = N.get("tonight") or []
    if tn and len(tn) != 3:
        warnings.append(f"tonight 有 {len(tn)} 条，规矩是三件事")
    rp = N.get("replies") or []
    if isinstance(rp, list):
        for i, item in enumerate(rp):
            if not isinstance(item, dict) or not item.get("to") or not item.get("draft"):
                errors.append(f"replies[{i}] 要有 to 和 draft 两个字段")
            elif chars(item["draft"]) > 40:
                warnings.append(f"replies[{i}] 的回复 {chars(item['draft'])} 字，规矩是 ≤ 40 字")
    co = N.get("call_openers") or []
    if co and len(co) != 3:
        warnings.append(f"call_openers 有 {len(co)} 条，规矩是三句")

    # 3. 措辞：感叹号、黑名单、评判词（引号里的原话不算）
    QUOTE_FIELDS = {"replies", "dictionary"}
    for path, text in strings_of(N):
        top = path.split(".")[0].split("[")[0]
        if top in QUOTE_FIELDS and (path.endswith(".to") or path.endswith(".her")):
            continue                      # 她的原话，照抄的
        stripped = QUOTE_RE.sub("", text)
        if "!" in stripped or "！" in stripped:
            errors.append(f"{path} 里有感叹号：{text[:40]}")
        for w in blacklist:
            if w in stripped:
                errors.append(f"{path} 里有黑名单短语“{w}”：{text[:40]}")
        for w in JUDGMENT:
            if w in stripped:
                errors.append(f"{path} 里有评判词“{w}”，报告不评判：{text[:40]}")

    # 4. 证据：引号里的话要在记录里真出现过
    if msgs and isinstance(msgs, dict) and isinstance(msgs.get("messages"), list):
        corpus_all = [norm(m.get("content") or "") for m in msgs["messages"] if isinstance(m, dict)]
        corpus_her = [norm(m.get("content") or "") for m in msgs["messages"] if isinstance(m, dict) and m.get("sender") == "her"]
        corpus_me = [norm(m.get("content") or "") for m in msgs["messages"] if isinstance(m, dict) and m.get("sender") == "me"]

        def found(q, corpus):
            nq = norm(q)
            return not nq or any(nq in c for c in corpus)

        def check_quotes(path, text, corpus, who):
            for m in QUOTE_RE.finditer(text or ""):
                before = text[max(0, m.start() - 8):m.start()]
                if any(w in before for w in ("你说", "你提到", "你答")):
                    continue              # 用户回答三个问题时说的，不在记录里
                if any(w in before for w in ("没", "不曾", "从未")):
                    continue              # "从来没问过“怎么不回”"：引的是她没说过的话，不用在记录里找
                if not found(m.group(1), corpus):
                    errors.append(f"{path} 引了“{m.group(1)}”，但记录里{who}没说过这句（不编造：引原话要一字不差，或者别加引号）")

        check_quotes("she_means", sm, corpus_all, "")
        check_quotes("type_lines.mother", tl.get("mother") if isinstance(tl, dict) else "", corpus_her, "她")
        check_quotes("type_lines.child", tl.get("child") if isinstance(tl, dict) else "", corpus_me, "你")
        check_quotes("forward_insight", N.get("forward_insight") or "", corpus_all, "")
        for k, v in (N.get("index_lines") or {}).items():
            check_quotes(f"index_lines.{k}", v, corpus_all, "")
        if isinstance(d, list):
            for i, item in enumerate(d):
                if isinstance(item, dict) and item.get("her") and not found(item["her"], corpus_her):
                    errors.append(f"dictionary[{i}] 的“{item['her']}”记录里她没说过（翻译表只翻她真说过的话）")
        if isinstance(rp, list):
            for i, item in enumerate(rp):
                if isinstance(item, dict) and item.get("to"):
                    check_quotes(f"replies[{i}].to", item["to"], corpus_her, "她")

    # 5. 数字可追溯：文字里的数字要能在 stats.json 里找到（日期时间除外）
    if S and isinstance(S, dict):
        known = numbers_in_stats(S)
        fields = [("she_means", sm), ("send_text", st), ("forward_insight", N.get("forward_insight") or ""),
                  ("bill_balance", N.get("bill_balance") or ""), ("footnote", N.get("footnote") or "")]
        fields += [(f"index_lines.{k}", v) for k, v in (N.get("index_lines") or {}).items()]
        if isinstance(tl, dict):
            fields += [(f"type_lines.{k}", v) for k, v in tl.items()]
        fields += [(f"call_openers[{i}]", v) for i, v in enumerate(co) if isinstance(v, str)]
        unknown = []
        for path, text in fields:
            cleaned = DATE_TIME_RE.sub(" ", text or "")
            for n in re.findall(r"\d+", cleaned):
                if int(n) not in known and (path, n) not in unknown:
                    unknown.append((path, n))
        if unknown:
            warnings.append("这些数字在 stats.json 里找不到，确认是加总或换算，不是心算：" + "、".join(f"{p} 的 {n}" for p, n in unknown[:8])
                            + (" …" if len(unknown) > 8 else ""))
    return errors, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("narrative", help="narrative.json")
    ap.add_argument("--stats", default=None, help="stats.json，给了就核对数字")
    ap.add_argument("--messages", default=None, help="messages.json，给了就核对引号里的原话")
    ap.add_argument("--strict", action="store_true", help="有提醒也失败")
    a = ap.parse_args()
    try:
        N = load_json(a.narrative)
    except json.JSONDecodeError as e:
        print(f"✗ 不是合法的 JSON：{e}。让 AI 只输出一个 JSON 对象，不要围栏以外的文字")
        sys.exit(1)
    S = load_json(a.stats) if a.stats else None
    M = load_json(a.messages) if a.messages else None
    errors, warnings = lint(N, S, M)
    for w in warnings:
        print(f"⚠ {w}")
    for e in errors:
        print(f"✗ {e}")
    if errors:
        print(f"\n{len(errors)} 个问题，改好再 render")
        sys.exit(1)
    if warnings and a.strict:
        sys.exit(1)
    print("\n✓ 文字部分过了规矩" + (f"（{len(warnings)} 个提醒，看一眼）" if warnings else "")
          + ("" if (S and M) else "；加 --stats 和 --messages 还能核对数字和原话"))


if __name__ == "__main__":
    main()
