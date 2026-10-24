# CLAUDE.md · 妈妈的消息

给在这个仓库里干活的 AI 的最短说明。产品定位、决策记录、任务清单、示例基线在 `docs/HANDOFF.md`，先读它（上一级目录的 `HANDOFF.md` 是同步出来的副本，不要直接改）。

## 这是什么

把用户和妈妈（或爸爸/外婆）的聊天记录算成一份报告 + 两张卡 + 一句可以直接发给她的话。Agent Skill（`SKILL.md`）+ 普通用户复制粘贴版（`prompts/`）+ 浏览器版（`web/`）。数字和原话由 `scripts/` 算和挑（`stats.py` → `brief.py` 出写作素材包），文字由 AI 按 `references/writing-rules.md` 写、再过 `scripts/lint_narrative.py`，`render.py` 合成。入口是 `scripts/mama.py`（run / finish / explain / compare / practice / status）。

## 不能破的约束

1. 脚本只用标准库，无网络请求；不解密数据库；转账不写金额；产物只在当前目录（`mama.py` 默认 `mama-out/`）。`snap.py` 出图调本机已装的 Chrome / Edge，关掉后台联网，临时目录用完即删。
2. 称呼跟人走：`her_pronoun` 决定她/他，母亲节/父亲节按人选。测试里必须保留爸爸用例。lint 会查称呼串没串。
3. 不评判：面向用户的字符串里叫"短回复"不叫"敷衍"，"没回"不叫"不孝"。黑名单在 `references/writing-rules.md`，`lint_narrative.py` 会查。
4. 数字可追溯：报告里每个数字在 `stats.json` 有字段，定义在 `references/metrics.md`；引号里的原话必须在记录里真出现过（lint 会核对）。brief.md 里 “” 只引记录原话，说明文字用「」。
5. **一处定义**：词表只在 `references/lexicon.json`（改词表不改代码）；公式和阈值只在 `scripts/stats.py` 顶部的 `FORMULA` / `*_RULES` / `MEAL_HOURS` 等常量；报告口吻只在 `scripts/_common.py` 的 `MODES`。`metrics.md`、`types.md`、`prompts/普通用户版.md`、SKILL.md 和 writing-rules.md 的口吻表是复述，`tests/test_docs_sync.py` 会比对——改了任何一处都要让它过。
6. 三份契约（messages.json / stats.json / narrative.json）有 `schema` 版本号（`_common.SCHEMA_VERSION`），格式不兼容时 +1，`render.py` 会拒绝旧版 stats.json。加可选字段（v0.6 的 `tz`、`mode`、stats 的 `self` / `voice` 等）不算不兼容。
7. 中文优先：面向用户的文本和代码注释中文，变量名英文。

## 每次改完跑

```bash
python tools/refresh.py            # 重生成示例 → 算数 → 校验 → 渲染 → lint → 素材包 → 对照卡 → 测试 → 打包并同步上级目录，最后打印基线变化
```

它等于下面这串，拆开跑也行：

```bash
python -m unittest discover -s tests            # 全绿才算完（有 Chrome / Edge 的机器上会多跑一个出图测试）
python examples/make_sample.py                  # 妈妈的半年 + 朋友的两个月（对照组）
python scripts/stats.py examples/sample-messages.json --out examples/sample-stats.json --today 2026-08-30 --her-birthday 10-20 --my-birthday 06-03
python scripts/render.py examples/sample-stats.json examples/sample-narrative.json --out examples/reports
python scripts/lint_narrative.py examples/sample-narrative.json --stats examples/sample-stats.json --messages examples/sample-messages.json
python scripts/brief.py examples/sample-stats.json examples/sample-messages.json --out examples/sample-brief.md
python tools/pack.py --sync-to ../..            # 重打 .skill 并同步上级目录的发布副本
```

`tests/test_pipeline.py::test_examples_in_sync` 是 golden 测试：`examples/sample-stats.json` 必须等于当前 `stats.py` 的输出。`refresh.py` 跑完会说基线数字变没变；变了要核对 `examples/sample-narrative.json`、`README.md` 开头示例块、`docs/HANDOFF.md` 第 7 节、`CHANGELOG.md`。README 里的测试数量它会自动改。CI（`.github/workflows/ci.yml`）在三个系统 × Python 3.8 / 3.12 上跑同一套，并检查提交的示例产物没有漂移。

## 目录

- `scripts/` mama（入口）· `_common`（契约版本、口吻表 MODES、类型枚举、时间和时区、编码嗅探、词表加载）· parse_export（含截图转录稿）· validate · stats · brief · lint_narrative · render · snap · compare · redact（CLI，`--help` 带说明）
- `references/` lexicon.json（词表）、指标、类型、词典、写作规矩（含口吻表）、报告模板、练习模式、导出指南（含截图转录格式）
- `assets/` 四个 HTML 模板（报告里 `<!--#版块-->…<!--/版块-->` 包起来的部分按口吻去掉）；`web/` 浏览器版（Pyodide 跑同一套脚本，`sw.js` 缓存运行时）
- `examples/` 模拟数据（`make_sample.py`，没有真实的人）、示例 brief、示例报告和卡片；`tests/fixtures/` 各种导出格式的最小样本
- `evals/` Skill 触发测试集；`tools/` refresh.py · pack.py · snapshot.py；`docs/` HANDOFF.md · img/；`.github/workflows/` CI 和 Release

## 平台注意

- Windows：脚本通过 `_common.setup_utf8()` 把 stdout 切到 UTF-8，写文件用 `newline="\n"`；新脚本沿用。
- 浏览器版通过 `runpy` 跑 `scripts/*.py`，RUNNER 已把 `/app/scripts` 加进 `sys.path`；脚本必须保持 `if __name__ == "__main__": main()` 结构，不能在 import 时做副作用。**新加的脚本或 references 文件要加进 `web/index.html` 的 `APP_FILES`**，不然页面里取不到（`mama.py` `snap.py` `compare.py` 网页用不到，没加）。
- Python 3.8 是下限（CI 会跑），别用 3.9+ 的语法和 API。
