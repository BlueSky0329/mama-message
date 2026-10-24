# -*- coding: utf-8 -*-
"""测试共用的小工具：路径、子进程、读写。只用标准库。"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
EXAMPLES = os.path.join(ROOT, "examples")
REFERENCES = os.path.join(ROOT, "references")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

SAMPLE = os.path.join(EXAMPLES, "sample-messages.json")
SAMPLE_STATS = os.path.join(EXAMPLES, "sample-stats.json")
SAMPLE_NARR = os.path.join(EXAMPLES, "sample-narrative.json")
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, obj):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, text, encoding="utf-8", newline="\n"):
    with open(p, "w", encoding=encoding, newline=newline) as f:
        f.write(text)


def run(script, *args, cwd=ROOT, env=None):
    """跑 scripts/ 下的脚本，返回 CompletedProcess（stdout/stderr 都是 UTF-8 文本）。env 是在 ENV 上额外加的变量。"""
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          cwd=cwd, env=dict(ENV, **(env or {})), capture_output=True, text=True, encoding="utf-8", errors="replace")


def msg(ts, sender, content="", type_="text", dur=None):
    return {"ts": ts, "sender": sender, "type": type_, "content": content, "dur": dur}


def base(messages, her="妈妈", pronoun="她"):
    return {"me": "我", "her": her, "her_pronoun": pronoun, "source": "test", "messages": messages}
