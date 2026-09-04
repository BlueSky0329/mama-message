# 妈妈的消息 · 开发交接文档

> 给 Claude Code 的。读完这份再动代码。仓库里是可运行的 v0.5，你的工作是把它做到可首发。
> 首次写于 2026-08-31（v0.3），2026-09-04 按 v0.5 更新。首发目标：中秋（2026-09-25）前两周内发第一个视频，仓库同步公开。
> 本文件在仓库里的位置是 `docs/HANDOFF.md`；上一级目录的 `HANDOFF.md` 是 `tools/pack.py --sync-to` 同步出来的副本，不要直接改它。

---

## 0. 一分钟版

- **产品**：把用户和妈妈（或爸爸/外婆）的聊天截图算成一份报告 + 两张卡 + 一句可以直接发给她的话。Agent Skill 形态，另有普通用户复制粘贴版提示词和浏览器版。
- **已完成**：SKILL.md、7 份 references + 词表、7 个脚本（全标准库、不联网）、3 个 HTML 模板、普通用户版提示词、README、模拟数据端到端跑通、测试、CI、浏览器版。
- **未完成**：真实数据校准、导出格式在真实样本上验证、Skill 触发测试、普通用户版实测。见第 6 节 P0。
- **v0.4（2026-08-31）补**：测试、validate.py、农历表、Windows 兼容、短回复口径修正、导出指南、浏览器版 MVP、CLAUDE.md、CHANGELOG。见 2.4 节。
- **v0.5（2026-09-04）补**：stats 拆分、词表外置、契约版本号、输入层适配器 + fixtures + 编码嗅探、narrative lint、文档口径同步测试、refresh.py、CI / Release、网页版 CDN 竞速 + 离线缓存。见 2.5 节。
- **不能碰的原则**：不联网、不解密数据库、不写金额、不评判用户、称呼跟人走、文字部分不抒情不说教。见第 5 节。

---

## 1. 产品定位（做决定时回来看这里）

### 1.1 为什么需要 AI

用户自认为最了解和父母的关系，所以这个产品**不解决"拿不准"**（那是恋爱分析类 skill 的需求）。它解决三件事：

1. **你以为你了解，但你从来没数过。** 没人故意敷衍妈妈，但 38 个"嗯"加起来是另一回事。AI 做的是计数，不是分析——把一件一直感觉到但从没量过的事变成数字。
2. **愧疚没有台阶。** 想打电话的人比打了的多得多，卡在"突然打过去说什么"。报告给一个借口："妈，我用了个软件，它说我欠你一个电话。"把主动示好的尴尬转嫁给软件。所以**最后一屏是发给她的，不是给用户看的**。
3. **晒愧疚 = 晒良心。** "我欠我妈 59 条回复"发出去，大家看到的是在乎。它是设计出来让人发的。

推论：
- 情绪 → 动作。情绪是愧疚，动作是打电话，中间每个模块都在缩短这段距离。
- 它是年度报告式的一次性传播品，不是日用工具。绑节日（中秋、春节、母亲节、生日），倒计时进报告。
- 不做心理学框架（依恋类型、Gottman）。妈妈不需要。
- 不做"复刻妈妈本人陪聊"。风险高（尤其对失去母亲的人）。练习模式是用她的说话方式训练**用户自己**，边界写在 `references/practice.md`。
- "关心还是控制"那群人有真正的分析需求，留作第二期分支产品《爸妈聊天体检》，不进主线。

### 1.2 参照系

| 项目 | 形态 | 数据 | 传播点 |
|---|---|---|---|
| 她不一样 (she-love-me) | 恋爱分析报告 | 解密微信数据库 | 指数进度条、成分表、类型鉴定、7 类危险信号、军师、祖师爷寄语、暗色 HTML |
| ex-skill（前任）| 复刻前任陪聊，5.8k star | 导出记录 + 口述 | 对话 demo、/let-go、写在最后的散文 |
| her-skill | 同上 | 同上 | 反 AI 短语黑名单、纠正机制 |

我们借的：指数 + 一句扎心话、成分表、类型标签、预警信号、可转发的卡、反 AI 黑名单、纠正机制、写在最后。
我们不借的：解密数据库（只吃截图和用户自己导出的文件，这是普通用户能用的前提，也是隐私卖点）、心理学框架、复刻本人。
社区第一反应是隐私（她不一样发布帖下第一条评论），所以 README 第一屏是隐私。

### 1.3 目标用户

首发面向**普通用户，想用不想学**。不会装 Claude Code。所以：
- `prompts/普通用户版.md` 是首发的分发主体（评论区回关键词领）
- Skill 版给开发者，也给作者立"做 skill 的人"的人设
- 网页版 v0.4 起有 MVP，v0.5 补了国内下载源和离线缓存（`web/index.html`，见 T15）

---

## 2. 当前状态

### 2.1 已完成（v0.5）

```
mama-message/
├── SKILL.md                    入口。触发描述、七步流程（第六步含 lint）、附加入口、收着的情况、自检
├── README.md                   隐私第一屏 → 模拟输出钩子 → 用法 → 模块表 → 数据来源 → 写在最后
├── CLAUDE.md · CHANGELOG.md · LICENSE (MIT) · .gitignore · .gitattributes
├── references/
│   ├── lexicon.json            全部词表：主题关键词、关心类主题、收尾语、追问语、"没事"、健康词、新闻词、我的负面词、停用字、exclude
│   ├── metrics.md              每个数字的定义（与 stats.py 一一对应；时区、契约版本、lint 也在这里）
│   ├── types.md                10 个她的类型 + 6 个你的类型 + 五档评级 + 类型句写法
│   ├── dictionary.md           黑话翻译表 20 条基础词典 + 个性化生成规则
│   ├── writing-rules.md        先问三个问题、各段文字规矩、反 AI 黑名单（lint 从这里读）、什么时候要收着
│   ├── report-template.md      对话 Markdown 报告模板 + narrative.json 字段 + 命令
│   ├── practice.md             练习模式：准备、对话规则、打分、边界
│   └── export-guide.md         分平台的导出 / 截图指南、编码、时区、认不出来怎么办
├── scripts/                    全部只用 Python 标准库，无网络
│   ├── _common.py              共用：SCHEMA_VERSION、TYPES / TYPE_CN、parse_ts / fmt_delta、epoch_to_local、read_text（编码嗅探）、load_lexicon
│   ├── parse_export.py         适配器：WeFlow JSON/TXT/weclone CSV、留痕 CSV、txt、通用 JSON、messages.json 直通 → messages.json
│   ├── validate.py             messages.json 校验：字段、枚举、时间、顺序、重复、金额、dur、sender 标反、schema
│   ├── stats.py                Ctx + sec_xxx 各算一块 → stats.json + 终端摘要；FORMULA / *_RULES 在顶部
│   ├── lint_narrative.py       narrative.json 规矩检查：字段、字数、感叹号、黑名单、评判词、原话核对、数字核对
│   ├── render.py               stats.json + narrative.json → 报告 + 两张卡（内联 SVG 图表）；拒绝旧 schema
│   ├── compare.py              两份 stats.json → 对照组 / 偏心报告
│   └── redact.py               打码：手机号、身份证、卡号、金额、邮箱、指定名字（输入编码自动识别）
├── assets/                     report.html · card-bill.html · card-send.html
├── prompts/普通用户版.md        三段提示词：报告版 / 练习版 / 帮你回版
├── web/                        index.html（Pyodide 跑 scripts/ 原文件；多个下载源竞速、失败顺延）· sw.js（缓存运行时）
├── examples/                   make_sample.py（seed=7）· sample-messages/stats/narrative.json · reports/ 三个 HTML
├── tests/                      test_pipeline · test_parse_export · test_lint · test_docs_sync · helpers · fixtures/（10 种样本）
├── tools/                      refresh.py（一键验证）· pack.py（打包 + 同步副本）· snapshot.py（HTML → PNG）
├── docs/                       HANDOFF.md（本文件）· img/（README 截图）
└── .github/workflows/          ci.yml（3 系统 × py3.8/3.12）· release.yml（打 tag 出 Release）
```

### 2.2 已验证

- 模拟数据端到端：`make_sample.py → stats.py → lint_narrative.py → render.py`，三个 HTML 无未填占位符；v0.5 重构后 stats.json 与 v0.4 逐字段一致（只多 `schema` / `lexicon`），HTML 逐字节一致。
- `parse_export.py`：`tests/fixtures/` 十种样本（WeFlow 三种、留痕 CSV、两行式、单行式、GBK、UTF-16、毫秒时间戳、.txt 里装 JSON）逐个核对条数 / 发送者 / 类型 / 时间；`--peek` 每个都能跑。
- `stats.py` 边界：空记录、全无时间戳、只有一方说话、未知 sender、时间倒序、爸爸模式、农历表外年份、02-29 生日、非法生日、自定义词表，都不崩且有对应 warning / 错误提示。
- `lint_narrative.py`：示例 narrative 零错误零提醒；黑名单、感叹号、评判词、编造的引号、翻译表引她没说过的话、找不到的数字，都能抓到。
- `compare.py`、`redact.py`（含 GBK 输入）冒烟通过。
- 性能：3 万条消息 `compute()` 0.6 秒，不需要优化。
- `.skill` 打包通过 skill-creator 的校验（v0.3）；v0.5 包内多了 `_common.py`、`lint_narrative.py`、`lexicon.json`、`tests/fixtures/`。

### 2.3 已知问题（诚实版）

| # | 问题 | 位置 | 严重度 |
|---|---|---|---|
| 1 | 留痕 / WeChatMsg 的 CSV 列名是按公开 schema 猜的，**没在真实导出上验证**。v0.5 有了 fixtures 骨架和编码嗅探，真实样本来了放进 `tests/fixtures/` 加一行期望值就行 | parse_export.py · tests/fixtures/memotrace.csv | 高 |
| 2 | 主题关键词和信号词是拍脑袋写的，没用真实数据校准。v0.5 把词表挪到 `lexicon.json` 并加了 `exclude` 机制（已挡"冷静/热闹/药店"几个明显的），校准只改 JSON 不改代码 | references/lexicon.json | 高 |
| 3 | 她自己身体的红灯信号用"含健康词 且 无'你' 且 无问句标记"判断，会漏也会误报 | stats.py `sec_signals` | 中 |
| 4 | 口头禅用 2–4 字 n-gram，粗糙；真实数据上可能出垃圾片段 | stats.py `sec_catchphrases` | 中 |
| 5 | "她最长的一条"的回复判定：中间她再发 > 2 条就视为没回，阈值随意 | stats.py `sec_longest` | 低 |
| 6 | ~~农历节日查表只到 2027~~ v0.4 扩到 2022–2030，表外年份进 `warnings`，有测试 | stats.py `LUNAR` | 已修 |
| 7 | HTML 用了 CSS grid，wkhtmltoimage（旧 WebKit）下网格塌成单列；服务端出图用 Chrome（tools/snapshot.py） | assets/*.html | 低 |
| 8 | ~~没有任何单元测试~~ v0.4 加了 28 个；v0.5 拆成四个文件、加 fixtures 和文档同步测试，数量见 README 徽章（refresh.py 自动改） | tests/ | 已修 |
| 9 | 普通用户版报告提示词约 2000 字，没在豆包 / Kimi / DeepSeek 上实测过；它让模型手算中位数，是三份口径实现里最不可靠的一份 | prompts/ | 高 |
| 10 | 练习模式纯 prompt，没有脚本统计回合 | references/practice.md | 低 |
| 11 | Skill 的 description 没做触发测试（正例/反例） | SKILL.md | 中 |
| 12 | ~~README 没有截图~~ v0.4 加了截图和徽章 | README.md | 已修 |
| 13 | 时段按运行脚本那台机器的时区算；留学生分析国内记录会整体偏一个时差。已写进 metrics.md，未实现 `tz` 字段 | stats.py `sec_hours` | 中 |
| 14 | ~~GBK / UTF-16 导出解析出 0 条；CSV 毫秒时间戳崩；02-29 生日崩；旧 stats.json KeyError；--help 没说明~~ v0.5 全修 | — | 已修 |
| 15 | ~~HANDOFF 不在仓库里，CLAUDE.md 的指引对 clone 者失效~~ v0.5 进 `docs/`，上级目录的是同步副本 | — | 已修 |

### 2.4 v0.4 增量（2026-08-31）

详见 `CHANGELOG.md`。要点：短回复只算"回复"（紧跟她的消息、24 小时内）；"早上 8 点前"拆成 `her_early_count` / `her_late_count`；`validate.py`、`tools/pack.py`、`parse_export.py --call / --since / --until / --last-days / --peek`；`stats.json` 加 `warnings`；Windows UTF-8；`CLAUDE.md`、`CHANGELOG.md`、`export-guide.md`；浏览器版 MVP；WeFlow 三种导出。

### 2.5 v0.5 增量（2026-09-04，Claude Code）

详见 `CHANGELOG.md`。结构性的几条：

- **一处定义**：词表 → `references/lexicon.json`（`stats.py --lexicon` 可换）；公式和阈值 → `stats.py` 顶部 `FORMULA` / `*_RULES`；`tests/test_docs_sync.py` 比对 `metrics.md` / `types.md` / `普通用户版` 里复述的数字。发现并清掉了短回复词表三处不一致（22 / 18 / 16 个词），那个集合本来就被"≤ 3 字"规则完全覆盖，定义改成诚实的。
- **契约版本**：三份 JSON 加 `schema`（`_common.SCHEMA_VERSION = 1`）；`render.py` 拒绝旧 stats.json；`validate.py` 拒绝更新版本的 messages.json；`messages.json` 多了 `source_detail`（来源格式、版本、编码）。
- **stats 拆分**：`Ctx`（整理输入，不改写原数据）+ `sec_xxx(ctx, S)`，每段可单独调用和测试；golden 测试逐字段守恒。
- **输入层**：适配器按内容识别格式；`read_text()` 嗅探 UTF-8 / GB18030 / UTF-16；`epoch_to_local()` 秒和毫秒；`--her` 写错报名字清单；`tests/fixtures/` 十种样本。
- **narrative lint**：`scripts/lint_narrative.py`，"出报告前自检"变成脚本，核心是**引号里的原话必须在记录里真有**、**数字必须能在 stats.json 里找到**。SKILL 第六步、网页第三步都接了。
- **流程**：`tools/refresh.py` 一条命令；CI 三系统 × py3.8/3.12 并检查示例没漂移；打 tag 自动出 Release（以后发布副本从 Release 拿）；HANDOFF 进仓库。
- **网页版**：Pyodide 多个下载源竞速 + 失败顺延 + 进度提示；`sw.js` 缓存运行时，断网可用；"只取最近 N 天 / 起止日期"；粘回 narrative 先 lint。
- 示例基线数字**不变**（第 7 节）。

---

## 3. 数据流与接口契约

```
截图 ──(AI 转录)──┐
导出文件 ──parse_export.py──┤──▶ messages.json ──validate.py──▶ stats.py ──▶ stats.json ──┐
粘贴文本 ──(AI 转录)──┘                                                                    ├──render.py──▶ reports/*.html
                        AI 按 writing-rules 写 ──▶ narrative.json ──lint_narrative.py──▶ 过 ┘
两份 stats.json ──compare.py──▶ compare.json + 终端表
```

三份契约共用一个版本号 `schema`（`scripts/_common.py` 的 `SCHEMA_VERSION`，现在是 1）。字段改到不兼容时 +1，并让 `render.py` / `validate.py` 的提示写清怎么办。

### 3.1 messages.json（唯一的输入契约，改它要全链路同步）

```json
{"schema": 1, "me": "我", "her": "妈妈", "her_pronoun": "她", "source": "screenshots|export|manual",
 "source_detail": "weflow-json 1.0.3 · utf-8",
 "messages": [
   {"ts": "2026-05-12T21:03:14", "sender": "her", "type": "text", "content": "吃饭了吗", "dur": null}
 ]}
```
- `schema` 可缺（AI 手工转录的可能没写）；比当前版本新会被 validate 拒绝。`source_detail` 是 parse_export 写的来源 / 版本 / 编码，进报告的数据说明。
- `ts` ISO 8601 或 `null`（截图无时间戳时）。`null` 参与计数，不参与时间计算。**不许编时间。** 时间按导出电脑的本地时区（metrics.md「时区」）。
- `sender` ∈ `her` | `me`
- `type` ∈ `_common.TYPES`：text · voice · image · video · sticker · transfer · link · call_voice · call_video · recall · location · file · other
- `dur` 秒，语音和通话用
- `content`：文字原文；link 放标题；transfer 只写"转账"**不写金额**；sticker 放内置表情如 `[玫瑰]`；其他类型空串
- 列表顺序 = 时间顺序（无时间戳的按截图位置插入）

### 3.2 stats.json（关键字段，完整见 `references/metrics.md`）

`schema` `lexicon`（词表版本）`her_name` `pronoun` `warnings` `basics` `opens` `reply.me/her` `longest` `short` `topics` `care_ratio` `hours` `unanswered` `phrases` `extras` `composition` `emoji` `catchphrases` `forwards` `weekly` `trend` `festivals` `countdown` `signals` `index.care/short/forgive` `mother_type` `child_type` `rating` `bill` `today`

三个指数的公式在 `metrics.md`，权重在 `stats.py` 的 `FORMULA`。**改公式或阈值必须同步四处**：`stats.py` 常量、`references/metrics.md`、`references/types.md`、`prompts/普通用户版.md`，`tests/test_docs_sync.py` 会红。改词表只改 `references/lexicon.json`（`version` +1），跑 `tools/refresh.py` 看基线变化。

### 3.3 narrative.json（AI 写，lint 查，render.py 读）

必填：`she_means` `send_text` `dictionary[]` `tonight[]` `replies[]` `call_openers[]` `type_lines.mother/child`
选填（缺省自动拼）：`schema` `title` `index_lines` `forward_insight` `bill_balance` `send_cta` `child_call` `cta` `footnote`
缺必填字段 render.py 不报错，HTML 里显示〔待写：字段名〕并在终端列出。`lint_narrative.py` 的 ✗ 要改到没有再 render：引号里的原话必须在 messages.json 里真出现过（"没说过“…”"和"你说“…”"除外），数字要能在 stats.json 里找到（找不到是 ⚠）。

### 3.4 CLI

```bash
python scripts/parse_export.py 文件 --her 记录里的名字 [--call 妈妈] [--me 我] [--pronoun 她] [--since/--until/--last-days] [--out messages.json] [--peek]
python scripts/validate.py messages.json [--strict]
python scripts/stats.py messages.json [--out stats.json] [--today YYYY-MM-DD] [--her-birthday MM-DD] [--my-birthday MM-DD] [--lexicon 词表.json] [--quiet]
python scripts/lint_narrative.py narrative.json [--stats stats.json] [--messages messages.json] [--strict]
python scripts/render.py stats.json [narrative.json] [--out reports/]
python scripts/compare.py a-stats.json b-stats.json --labels 你妈 朋友 --mode friend|papa [--out compare.json]
python scripts/redact.py 文件 [--map 真名=称呼]... [--names 名字...]
python tools/refresh.py [--no-sync] [--snapshot]        # 改完之后的一条命令
python tools/pack.py [--sync-to 目录]                    # 打 .skill + 同步发布副本
```

所有脚本 `--help` 带模块说明；失败时输出人话并 exit 1。

---

## 4. 报告模块清单与优先级

| 模块 | 数据来源 | 首发 | 视频 |
|---|---|---|---|
| 三个指数 + 一句扎心话 | stats.index + AI | 必有 | 开头 |
| 六个数字 | stats | 必有 | |
| 成分表 + 表情 + 口头禅 | stats.composition/emoji/catchphrases | 必有 | |
| 鉴定结果（她的类型 / 你的类型 / 评级章） | stats.mother_type/child_type/rating + AI 一句 | 必有 | 中段 |
| 黑话翻译表 | AI 按 dictionary.md | 必有 | 结尾候选 |
| 节日记分牌 + 倒计时 | stats.festivals/countdown | 必有 | 结尾 |
| 她发了你没回（空气泡） | stats.unanswered | 必有 | |
| 她转给你的 | stats.forwards + AI | 彩蛋 | |
| 该打电话了（红黄灯） | stats.signals | 必有 | |
| 两个时区热力条 + 每周量 | render.py SVG | 彩蛋 | |
| 她其实想说的是 | AI | 必有 | |
| 今晚三件事 / 帮你回 / 三句开场白 | AI | 必有 | |
| 亲情账单卡 | card-bill.html | 必有 | 结尾 |
| **发给她的卡** | card-send.html | **必有，产品出口** | 结尾 |
| 练习模式 | practice.md | 必有 | **中段实录** |
| 对照组（回朋友 vs 回妈） | compare.py | 必有 | **开头那一行** |
| 偏心报告（妈 vs 爸） | compare.py --mode papa | 彩蛋 | |

视频三段：开头「你回朋友 3 分钟，回你妈 4 小时」→ 中间练习模式实录（打"嗯"被抓）→ 结尾发给她的卡 + 中秋倒计时。标题用"欠一个电话"。

---

## 5. 不能破的约束

1. **隐私**：脚本无网络请求；不解密数据库；不写金额；产物只在当前目录；`.gitignore` 排除 messages/stats/narrative/reports。任何新脚本沿用。网页版只从 CDN 取 Pyodide 运行时，记录不出浏览器；`sw.js` 只缓存运行时和站内文件。
2. **依赖**：脚本只用标准库。要加第三方库必须是可选的（try/except 降级），并写进 README。Python 3.8 是下限，CI 会跑。
3. **称呼跟人走**：`her_pronoun` 决定她/他；母亲节/父亲节按人选；类型名里的"妈妈"是文案不是逻辑。测试里必须有爸爸用例。
4. **不评判**：报告里叫"短回复"不叫"敷衍"，"没回"不叫"不孝"；评级是章不是判决。这条也约束变量名之外的所有面向用户的字符串。`lint_narrative.py` 查评判词。
5. **文字规矩**：`writing-rules.md` 的黑名单和"什么时候要收着"对所有 AI 生成文字生效，包括普通用户版提示词。黑名单只在 writing-rules.md 一处，lint 从那里读。
6. **数字可追溯**：报告里每个数字在 stats.json 里有对应字段，定义在 metrics.md。不允许 AI 心算数字。引号里的原话必须在记录里真有。lint 查这两条。
7. **中文优先**：所有面向用户的文本中文。代码注释中文。变量名英文。
8. **一处定义**：词表只在 `references/lexicon.json`；公式和阈值只在 `stats.py` 顶部；`metrics.md` / `types.md` / `普通用户版.md` 是复述，`tests/test_docs_sync.py` 守着。
9. **契约有版本**：改 messages.json / stats.json / narrative.json 的字段到不兼容，`SCHEMA_VERSION` +1，并更新 SKILL.md 第三步的示例、report-template.md、本文件第 3 节。
10. **新脚本要进网页**：新加的 `scripts/*.py` 或 `references/*` 文件，要加进 `web/index.html` 的 `APP_FILES`，否则页面里取不到。

---

## 6. 剩余工作

### P0 · 首发前必须

**T1 真实数据校准**（需要作者提供打码后的真实截图或导出；作者机器微信 4.1.13，可直接用 WeFlow 导）
- 用 ≥ 2 份真实记录跑 `stats.py`，人工核对：谁先开口、短回复、没回、最常问、类型、信号。
- 校准 `references/lexicon.json`：主题词、收尾语、健康词，误判加进 `exclude`。**只改 JSON**，`lexicon.version` +1，跑 `python tools/refresh.py` 看示例基线变了哪些，能解释就更新第 7 节。
- 校准三个指数的权重（`stats.py` 的 `FORMULA`），使真实数据落在 30–80 区间、有区分度；改了要同步 metrics.md / 普通用户版，`test_docs_sync` 会红。
- 验收：作者看报告说"这是我"。

**T2 验证导出格式**（v0.5 已有骨架：`tests/fixtures/` + `tests/test_parse_export.py` 的 `CASES` 表，编码和毫秒时间戳已处理）
- 找留痕（MemoTrace）、WeChatMsg、PyWxDump 的真实导出样本，打码、截前几十条放进 `tests/fixtures/`，在 `CASES` 加一行期望值，修 `parse_export.py` 直到过。
- 补微信 iOS/Android 官方"聊天记录迁移/导出"的常见文本形态。
- 验收：每种格式一个真实样本，解析后条数和类型分布正确。

**T3 `scripts/validate.py`** ✅ v0.4。**T3b `scripts/lint_narrative.py`** ✅ v0.5：字段、字数、感叹号、黑名单、评判词、原话核对、数字核对；SKILL 第六步和网页第三步已接。

**T4 测试** ✅ v0.4 / v0.5：四个测试文件 + fixtures，CI 三系统 × py3.8/3.12。

**T5 README 截图** ✅ v0.4（`tools/snapshot.py`）。

**T6 Skill 触发测试**
- 按 skill-creator 的方法：5 条正例（"分析我和我妈的聊天""我是不是太敷衍我爸了""[直接发家人截图]""帮我看看我妈多久找我一次""陪我练练怎么回我妈"）、5 条反例（"分析我和女朋友的聊天""帮我写给妈妈的生日祝福""微信怎么导出聊天记录""我妈是什么星座""统计一下群聊谁最活跃"）。
- 调 description 直到正例全触发、反例不触发（"女朋友"那条尤其要不触发，那是她不一样的地盘）。

**T7 普通用户版实测**（和 T22 一起做）
- 在豆包、Kimi、DeepSeek、Claude 各跑一次报告版提示词 + 10 张模拟截图。
- 记录：是否被截断、是否严格按顺序输出、指数公式是否照算、黑名单是否遵守。
- 验收：至少两个国产模型能出完整报告。

**T8 仓库收尾** ✅（README 账号、CLAUDE.md、CHANGELOG、pack、公开推送、v0.5 加 CI / Release / HANDOFF 入库）。首发时 CHANGELOG 改 v1.0，打 tag `v1.0` 自动出 Release。

### P1 · 首发后一周

**T9 `.claude/commands/`** 三个快捷命令：`mama-practice.md` `mama-reply.md` `mama-compare.md`，内容是"读 SKILL.md，进入 X 模式"。验证 Claude Code 当前版本的 commands 目录规范。

**T10 卡片版式兼容**：把 `card-bill.html` `card-send.html` 的 grid 改成 flex（老 WebKit 也能渲染），报告可以保留 grid。

**T11 `compare.py` 增强**：直接接受 messages.json（内部调 stats），并出一张对照卡 `card-compare.html`（"你回朋友 3 分钟 / 回你妈 4 小时 12 分" 两个大数字）。这是视频开头那一帧。

**T12 农历表扩到 2030** ✅ v0.4。

**T13 表情转录规范**：`references/emoji.md` 列微信常见内置表情名，SKILL.md 转录步骤引用，保证截图路径和导出路径的表情统计口径一致。

**T14 练习模式计分脚本**（可选）：`scripts/practice_score.py` 读一段对话文本，数短回复、问句、字数，输出打分模板。

**T15 浏览器版**（v0.4 MVP，v0.5 加固）
- 现状：Pyodide 跑 `scripts/` 原文件；下载源竞速（jsDelivr 主站 / Fastly / Gcore / Quantil 节点 + unpkg，探 python_stdlib.zip 本身、失败顺延；npmmirror 对 .zip 返回 451 所以不用），带进度；`sw.js` 缓存运行时，https 或 localhost 下断网可用；输入 → parse_export（含最近 N 天 / 起止）→ validate → stats → 复制提示词 → 粘回 narrative → lint → render → 三个 HTML 页内预览、可下载。数据不出浏览器。
- 部署：GitHub Pages 开仓库根目录即可（页面按相对路径取 `../scripts/` `../assets/` `../references/`）。本地 `python -m http.server`。
- **待作者决定**：要不要在页面里直接调模型 API（用户填 key，截图直接上传给视觉模型转录 + 写文字）。代价：记录会发给模型商，"不联网"的说法要改成"只发给你自己选的模型"；国内模型的浏览器端 CORS 要逐家验证。没决定前不接 API。
- 后续：对照组入口（两份记录）；截图转录辅助；卡片一键出 PNG（html2canvas，可选依赖）；手机浏览器实测 Pyodide 的内存和时间。

**T16 导出更方便** ✅ v0.4（export-guide、--call / --since / --until / --last-days / --peek、WeFlow 三种导出）。仍要真实样本（= T2）；iMessage-exporter、短信 XML 没支持。WeFlow 本地 HTTP API（127.0.0.1:5031）网页版以后可直连。

**T21 时区字段**：`messages.json` 加可选 `tz`（如 `+08:00`），`stats.py` 按它算时段；`parse_export.py` 写入运行机器的时区。没做之前报告数据说明写"时段按 X 时区"。

**T22 普通用户版三段化**：拆成"转录 → 算数 → 写作"三条消息；转录那条的输出严格等于 messages.json 的形状，用户可以把它贴进网页拿到准确数字，再回到 AI 写字。和 T7 一起做，减少让模型手算的部分。

### P2 · 之后

- **《爸妈聊天体检》**：关心 vs 控制的分支产品，独立仓库。
- **多对象**：外婆、爷爷同时分析，出"全家账单"。
- 英文 README。
- ~~T17 lint、T18 CI/Release、T19 词表外置、T20 stats 拆分~~ v0.5 已完成。

---

## 7. 验证命令（每次改完跑）

```bash
cd mama-message-repo/mama-message
python tools/refresh.py          # 重生成示例 → 算数 → 校验 → 渲染 → lint → 测试 → 打包并同步上级目录，最后打印基线变化
```

它等于：

```bash
python -m unittest discover -s tests                            # 全绿（含 golden 测试、文档口径同步测试）
python examples/make_sample.py
python scripts/stats.py examples/sample-messages.json --out examples/sample-stats.json --today 2026-08-30 --my-birthday 06-03 --her-birthday 10-20
python scripts/validate.py examples/sample-messages.json
python scripts/render.py examples/sample-stats.json examples/sample-narrative.json --out examples/reports
python scripts/lint_narrative.py examples/sample-narrative.json --stats examples/sample-stats.json --messages examples/sample-messages.json
grep -c "〔待写" examples/reports/mama-message-report.html   # 期望 0
python scripts/compare.py examples/sample-stats.json examples/sample-stats.json --labels 妈 爸 --mode papa --out compare.json
python tools/pack.py --sync-to ../..                           # 重打 .skill + 同步上级目录发布副本（含本文件）
python -m http.server 8000                                     # 然后开 http://localhost:8000/web/ 点"用模拟数据试试"
```

Windows 上 `python` 而不是 `python3`；脚本已自带 UTF-8 输出。改了算法忘了重跑示例，golden 测试会红并告诉你命令。

当前 sample 的基线数字（v0.4 起不变，v0.5 重构后逐字段一致；改词典/公式后 `refresh.py` 会列出变化，变了要能解释）：
```
她 192 条 / 你 102 条 · 181 天
谁先开口 她 86 / 你 42 · 你回她中位 1 小时 30 分 · 短回复 52 条 / 93 条回复 56%（v0.3 是 53/100，口径变了）
没回 59 / 139 段 · 之后她先开口 51 · 早上 8 点前 28 条 · 晚上 10 点后 51 条
牵挂 57 · 嗯哦好 42（v0.3 41）· 不计较 92 · 评级分 62（欠一个电话）
她 三餐监督型（副 语音轰炸型）· 你 嗯哦好选手 · 评级 欠一个电话
信号：🔴 腰不好回了4字 · 🔴 8 次打扰你了收尾 · 🟡 通话时长降 · 🟡 9 次没事
```

---

## 8. 决策记录

| 决定 | 为什么 | 不这么做的代价 |
|---|---|---|
| 只吃截图和用户自己导出的文件，不解密数据库 | 普通用户能用；隐私是社区第一反应；和她不一样差异化 | 时间戳不全，部分指标精度下降——用中位数和"有时间戳的 x 对"说明兜底 |
| 回复间隔用中位数 | 一条隔三天的回复会把平均数拉爆 | — |
| 对话开启阈值 6 小时、没回阈值 24 小时、turn 内间隔 < 6 小时 | 经验值，需 T1 校准 | — |
| 评级用嗯哦好指数 + 红灯 | 一个数字 + 几个事件，用户能复述 | — |
| 报告说"短回复"不说"敷衍" | 用户自己得出结论比被告知有效；也是不评判原则 | — |
| 发给她的卡是产品出口 | 情绪需要动作接住；把责任推给软件是故意的 | 没有这张卡，报告只是让人内疚一下然后关掉 |
| 不做心理学框架 | 妈妈不需要依恋类型；普通用户要的是"这句话戳到我了" | — |
| 不做复刻妈妈陪聊 | 失去母亲的用户风险；练习模式训练的是用户不是她 | 少一个 ex-skill 式的传播点，接受 |
| 脚本全标准库 | 普通用户环境不可控；隐私承诺"不联网"要能被审计 | 分词粗糙（口头禅 n-gram） |
| HTML 用微信灰底白卡 | 主题就是微信；和她不一样的暗色区分 | — |
| 词表外置成 JSON（v0.5） | 校准是数据工作，不该改代码；文档和网页能引用同一份 | stats.py 不再单文件自足，要和 references/ 放一起 |
| 公式阈值收进常量并用测试比对文档（v0.5） | "三处同步"靠规矩已经漂移过（短回复词表 22/18/16） | 改文档措辞时偶尔要顺手改测试的正则 |
| 三份契约加 schema（v0.5） | v0.4 加字段时旧 stats.json 会 KeyError；有版本号才能给人话提示 | — |
| narrative 先过 lint 再 render（v0.5） | "不编造"靠模型自觉不可靠；引号原话和数字都能机器核对 | 引用必须一字不差，AI 偶尔要改第二版 |
| 网页版多源竞速、失败顺延 + Service Worker（v0.5） | 目标用户在国内，jsdelivr 主站时通时不通；npmmirror 对 .zip 返回 451；README 承诺"断网也能用"要成立 | 多一个 sw.js 要维护，缓存名变了要改 |
| HANDOFF 进仓库，上级目录只放同步副本（v0.5） | 公开仓库的 CLAUDE.md 指向仓库外的文件，clone 的人找不到 | — |

---

## 9. 给 Claude Code 的工作方式

1. 先跑第 7 节的 `python tools/refresh.py`，确认全绿、基线没变。
2. 按 P0 顺序做，T1 需要作者数据，没有就先做 T2、T6、T7/T22。
3. 改词表只改 `lexicon.json`（`version` +1）；改公式或阈值改 `stats.py` 顶部常量，再同步 `metrics.md` / `types.md` / `普通用户版.md`，`test_docs_sync` 过了才算；改契约字段 `SCHEMA_VERSION` +1（第 5 节第 8、9 条）。基线变了更新第 7 节和 CHANGELOG。
4. 改任何面向用户的字符串：过一遍 `writing-rules.md` 的黑名单和"不评判"；写 narrative 一律跑 `lint_narrative.py`。
5. 新脚本：标准库、Python 3.8 语法、中文注释、`from _common import …`、`argparse(description=__doc__)`、失败时输出人话 exit 1、加进 `web/index.html` 的 `APP_FILES`。
6. 不要为了完整而加模块。首发清单在第 4 节，彩蛋以外的新想法记到 P2。
7. 每完成一个 T，在 `CHANGELOG.md` 记一行，跑一次 `refresh.py`（它会重打 .skill 并同步上级目录的发布副本，包括本文件）。上级目录的 README / SKILL / 普通用户版 / 示例 HTML / HANDOFF / .skill 都是副本，不要直接改它们。
8. 有疑问优先回第 1 节看产品定位，再回第 5 节看约束。两者都没答案的，问作者，不要猜。
