# CLAUDE.md · 妈妈的消息

给在这个仓库里干活的 AI 的最短说明。产品定位、决策记录、任务清单在上一级目录的 `HANDOFF.md`，先读它。

## 这是什么

把用户和妈妈（或爸爸/外婆）的聊天记录算成一份报告 + 两张卡 + 一句可以直接发给她的话。Agent Skill（`SKILL.md`）+ 普通用户复制粘贴版（`prompts/`）+ 浏览器版（`web/`）。数字由 `scripts/` 算，文字由 AI 按 `references/writing-rules.md` 写，`render.py` 合成。

## 不能破的约束

1. 脚本只用标准库，无网络请求；不解密数据库；转账不写金额；产物只在当前目录。
2. 称呼跟人走：`her_pronoun` 决定她/他，母亲节/父亲节按人选。测试里必须保留爸爸用例。
3. 不评判：面向用户的字符串里叫"短回复"不叫"敷衍"，"没回"不叫"不孝"。黑名单在 `references/writing-rules.md`。
4. 数字可追溯：报告里每个数字在 `stats.json` 有字段，定义在 `references/metrics.md`。
5. **一处定义，三处同步**：改指标 → `scripts/stats.py` + `references/metrics.md` + `prompts/普通用户版.md`；改类型 → `stats.py` + `references/types.md` + `普通用户版.md`。
6. 中文优先：面向用户的文本和代码注释中文，变量名英文。

## 每次改完跑

```bash
python -m unittest discover -s tests            # 全绿才算完
python examples/make_sample.py                  # 改了算法/词典要重跑下面三步
python scripts/stats.py examples/sample-messages.json --out examples/sample-stats.json --today 2026-08-30 --her-birthday 10-20 --my-birthday 06-03
python scripts/render.py examples/sample-stats.json examples/sample-narrative.json --out examples/reports
python tools/pack.py --sync-to ../..            # 重打 .skill 并同步上级目录的发布副本
```

`tests/test_pipeline.py::test_examples_in_sync` 是 golden 测试：`examples/sample-stats.json` 必须等于当前 `stats.py` 的输出。改了算法后要重跑示例，并核对 `examples/sample-narrative.json`、`README.md` 开头示例块、`HANDOFF.md` 第 7 节基线里的数字。

## 目录

- `scripts/` parse_export · validate · stats · render · compare · redact（CLI，`--help` 能看懂）
- `references/` 指标、类型、词典、写作规矩、报告模板、练习模式、导出指南
- `assets/` 三个 HTML 模板；`web/` 浏览器版（Pyodide 跑同一套脚本）
- `examples/` 模拟数据（`make_sample.py` seed=7，没有真实的人）
- `tools/pack.py` 打包 `.skill` + 同步发布副本

## 平台注意

- Windows：脚本已把 stdout 切到 UTF-8，写文件用 `newline="\n"`；新脚本沿用。
- 浏览器版通过 `runpy` 跑 `scripts/*.py`，所以脚本必须保持 `if __name__ == "__main__": main()` 结构，不能在 import 时做副作用。
