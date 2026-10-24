<div align="center">

# 妈妈的消息 · mama-message

**你觉得你和你妈关系挺好的？** 把你们的聊天记录给它算一遍。

一份报告、两张卡片、一句可以直接发给她的话。<br>
分析爸爸、外婆也行，称呼和节日会跟着换。

[![License: MIT](https://img.shields.io/badge/License-MIT-07C160.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B%20%C2%B7%20%E6%A0%87%E5%87%86%E5%BA%93-3776AB?logo=python&logoColor=white)](./scripts)
[![No network](https://img.shields.io/badge/%E8%84%9A%E6%9C%AC%E6%97%A0%E7%BD%91%E7%BB%9C%E8%AF%B7%E6%B1%82-%E6%96%AD%E7%BD%91%E8%83%BD%E8%B7%91-lightgrey)](#先说隐私)
[![Tests](https://img.shields.io/badge/tests-122%20passing-brightgreen)](./tests)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-SKILL.md-1B1B1B)](./SKILL.md)

<img src="docs/img/card-send.png" width="300" alt="发给她的卡：妈，我用了个软件，它说我欠你一个电话。今晚 8 点打给你。">&nbsp;&nbsp;
<img src="docs/img/card-bill.png" width="300" alt="亲情账单卡：她发给你 192 条 / 你回她 102 条 / 结余：欠 30 条回复、1 个电话">

<sub>模拟数据，没有任何真实的人。左边那张就是拿来发给她的。</sub>

</div>

```
💛 牵挂指数    57 ██████░░░░  她发起了 67% 的对话，有 28 条是早上 8 点前发的
🧊 嗯哦好指数  35 ████░░░░░░  你 93 条回复里有 52 条不超过三个字，最长一次 3 天没回
🕰️ 不计较指数  94 █████████░  你没回的 30 次里，有 27 次是她自己先开口了下一次

她：三餐监督型 🍚 ——"吃饭了吗""今天吃的什么""别老吃外卖"，她问吃饭 19 次，11 次不在饭点
你：嗯哦好选手 🧊 ——"嗯"8 次、"好"7 次、"好的"5 次，没有一条超过两个字
综合评级：欠一个电话 📞
```

---

## 它是怎么工作的

```
聊天记录 ──(WeFlow 导出 / 截图转录稿)──▶ messages.json ──stats.py──▶ stats.json（全部数字）
                                                         └─brief.py──▶ brief.md（写作素材：原话 + 数字）
                                             AI 照 brief.md 按写作规矩写 ──▶ narrative.json ──lint──▶ 过
stats.json + narrative.json ──render.py──▶ 报告 + 两张卡片（HTML，--png 直接出图）
```

分工很清楚：**数字和原话归脚本，文字归 AI**。谁先开口、回复中位数、你发过几个"嗯"、她最常问什么、母亲节那天谁先说话——这些全部由本地 Python 脚本算出来，公式写在 [`references/metrics.md`](./references/metrics.md)，报告里每个数字都能追溯到 `stats.json` 的一个字段。脚本还会把 AI 写作要用的原话挑出来放进 `brief.md`：她唯一一次说起自己腰不好、你当时回了什么、之后有没有再问；她说过不止一次的话和几点说的；她平时怎么打字。AI 负责把这些写成人话：三个指数各配一句、她的类型和你的类型、她的黑话翻译表，最后给你一句带具体时间的话，复制就能发。

写作有规矩（[`references/writing-rules.md`](./references/writing-rules.md)）：引用她的原话要带日期或次数，有一整页的禁用词黑名单，记录里没有的事一个字都编不得。记录里有争吵、有控制、或者她已经不在了，报告会换一种口吻：不只是文字收着写，评级章、"今晚三件事"、发给她的卡这些版块会直接不出（五种口吻，写在一张表里，渲染和检查都照它来）。

写完还要过一道机器检查（[`scripts/lint_narrative.py`](./scripts/lint_narrative.py)）：引号里的话必须是记录里一字不差出现过的，文字里的数字必须能在 `stats.json` 里找到，禁用词、金额一个不能有，分析爸爸时冒出"她"也会被拦下。AI 编出来的东西过不了这一关。

## 先说隐私

- 记录在**你自己的电脑上**导出（WeFlow 这类工具本地运行），本项目的脚本不碰微信数据库、不要密码。
- 脚本全部是 Python 标准库，没有任何网络请求，断网能跑。产物都在当前目录，随时删。
- 报告引用原话最多一句，转账记次数、不记金额（连 `messages.json` 里都不落金额）。
- `python scripts/redact.py 文件 --map "李秀兰=妈妈"` 一键打掉手机号、身份证、卡号、金额、邮箱。
- 写文字那一步要经过一个 AI——你把提示词粘给谁，记录就发给了谁。这一步工具管不了，自己掂量。
- 卡片出图（`--png`）调的是你电脑上已经装好的 Chrome / Edge，卡片页面里没有任何外部资源。

## 怎么用

先拿到记录。电脑上开着 Alpha（本机微信的只读服务）的话什么都不用导，Agent 直接读：`mama.py run --wechat 妈`。否则微信 4.0+ 装个 WeFlow（本地运行，一次导全半年，格式选 JSON）；微信 3.x 用留痕 / PyWxDump；实在没有电脑再截图，让 AI 照截图抄成"她：/ 我："的转录稿，相邻截图重叠的消息和"昨天 21:30"这种时间脚本会处理。分平台的步骤在[导出指南](./references/export-guide.md)。然后三条路挑一条：

### 1 · 什么都不装

[`prompts/普通用户版.md`](./prompts/普通用户版.md) 里有四段写好的提示词（报告版、练习版、帮你回版、截图转录版）。整段复制进豆包 / Kimi / DeepSeek / Claude / ChatGPT，把记录发过去，等报告。适合在手机上就想跑一遍的人。

### 2 · Claude Code / Codex / Cursor（Agent Skill）

```bash
git clone https://github.com/BlueSky0329/mama-message ~/.claude/skills/mama-message
```

把导出文件拖进对话，说一句"分析我和我妈的聊天"，或者 `/mama-message`。AI 会自己跑两条命令：

```bash
python scripts/mama.py run 私聊_妈妈.json --call 妈妈 --last-days 180   # 解析 → 校验 → 算数 → 写作素材包，产物在 mama-out/
python scripts/mama.py finish --png                                     # 文字过规矩 → 报告和两张卡（HTML + PNG）
```

电脑上开着 Alpha 的话连导出都省了：说"看看我和我妈的聊天"，它先列出微信里名字带"妈"的私聊让你确认，然后直接读——

```bash
python scripts/mama.py run --wechat 妈 --call 妈妈 --last-days 365    # 只连本机 127.0.0.1，只读私聊，读不了发消息的接口
```

中间它读 `mama-out/brief.md` 写文字——聊天正文由脚本在你电脑上读和算，AI 看到的只有素材包。你问"这个怎么算的"，它会用 `mama.py explain 没回` 把背后那几条消息列给你看。

其他支持 Agent Skill 的工具把整个文件夹放进对应的 skills 目录即可，SKILL.md 格式通用。

### 3 · 浏览器里跑

打开 **https://bluesky0329.github.io/mama-message/** （`web/index.html`，用 [Pyodide](https://pyodide.org) 在浏览器里跑同一套脚本，记录不离开浏览器；想离线用就在仓库根目录 `python -m http.server 8000`，打开 http://localhost:8000/web/）：拖进导出文件或粘贴截图转录稿 → 检查 → 算数 → 复制提示词（带写作素材包）给任意 AI 写文字 → 粘回来 → 报告和卡片。首次打开下载约 10 MB 的运行时（jsDelivr 的几个节点和 unpkg 自动选通的、失败顺延），下载过一次后由 Service Worker 缓存，断网也能用。全量导出可以只取最近 N 天；报告口吻可以选。

---

## 报告里有什么

<div align="center">
<img src="docs/img/report-top.png" width="720" alt="报告首屏：三个指数、六个数字、成分表">
<br><sub><a href="docs/img/report.png">完整报告截图</a> · 或直接打开 <a href="examples/reports/mama-message-report.html">examples/reports/mama-message-report.html</a></sub>
</div>

| 模块 | 一句话 |
|---|---|
| 💛🧊🕰️ 三个指数 | 牵挂 / 嗯哦好 / 不计较，每个配一句扎心话，公式公开 |
| 六个数字 | 谁先开口 · 你回她通常要多久 · 她最长的一条你回了几个字 · 你的"嗯好知道了" · 她最常问的三件事 · 她最常在几点找你 |
| 成分表 | 她的消息按吃饭 / 天气 / 回家 / 转发 / 语音 / 表情包配比，像食品配料表 |
| 鉴定结果 | 她是 10 型之一（三餐监督 / 天气预报 / 养生转发 / 查岗 / 钱够不够 / 语音轰炸 / 催婚 / 等你先开口 / 沉默守望 / 新闻联播），你是 6 型之一（嗯哦好选手 / 已读不回 / 秒回三个字 / 深夜忏悔 / 周末选手 / 报喜不报忧），盖一个章：模范子女 → 欠一次回家 |
| 黑话翻译表 | "吃了吗" → "在吗，我想你了"；"你忙吧" → "我等你"。从她真说过的话里挑 |
| 节日记分牌 | 你生日她 00:02 发的；母亲节你发了一个表情包 |
| 她发了，你没回 | 最多 5 条，带日期原文，右下角一个空气泡 |
| 她转给你的 | 她转了 7 篇，6 篇养生；3 月转给你《久坐伤腰》，8 月说腰不好的是她自己 |
| 该打电话了 | 🔴 她提自己腰不好你回了四个字 · 🔴 她开始用"打扰你了"收尾 · 🟡 她主动少了 40% · 🟡 你 47 天没主动开口 |
| 两个时区 | 她 7 点，你 23 点，24 小时热力条一眼看出错开；每周消息量她 vs 你 |
| 她其实想说的是 | 120–220 字，每句能指到一条原话，不抒情不说教 |
| 今晚就做的三件事 | 第一件 30 秒能做完 |
| 帮你回 + 三句开场白 | 用你自己的口气写好，复制就能发；打电话不知道第一句说什么的看这里 |
| 亲情账单 | 收款单样式：她发给你 192 条 / 你回 102 条 / 结余：欠 30 条回复、1 个电话 |
| 发给她的一条 | "妈，我用了个软件……它说我欠你一个电话。今晚 8 点打给你。" 整个产品做到最后，就是为了这一条能发出去 |

### 还能这么玩

| 说一句 | 得到 |
|---|---|
| "练习模式" / "扮演我妈陪我练" | AI 照她平时打字的样子（几个字一条、用不用标点、你回"嗯"之后她通常接什么）跟你聊 10 回合，你回"嗯"当场被标出，最后脚本打分 |
| "和朋友比比" | 对照组 + 一张对照卡：你回朋友 3 分钟，回你妈 1 小时 30 分，差了 30 倍 |
| "妈和爸都分析一下" | 偏心报告：你回谁更快、晾谁更久、谁更主动找你 |
| "帮我回她" | 回复话术和三句开场白，跳过整份报告 |
| "做张卡片" | 亲情账单卡 + 发给她的卡，竖版 PNG，直接能发 |
| "这个怎么算的" / "那条怎么算没回" | 把这个数字背后的那几条消息原样列出来 |

---

## 数据来源

导出文件比截图好得多：半年记录一次拿全，时间戳完整；截图一屏几条，三四十张也覆盖不了多少，还得让 AI 逐张转录。

| 来源 | 怎么给 | 备注 |
|---|---|---|
| **本机微信直接读**（Alpha） | `mama.py run --wechat 妈` | 不用导出；只连本机、只读私聊，语音秒数和通话时长都有 |
| **WeFlow** 导出的 JSON / CSV / TXT | `parse_export.py` | 微信 **4.0+**，本地运行，Windows / macOS / Linux，没有 Alpha 时首选 |
| 留痕 MemoTrace / WeChatMsg / PyWxDump | CSV 或 JSON | 微信 **3.x** 走这条 |
| 微信 / QQ 文本导出 txt | `parse_export.py` | 两行式、单行式、带方括号时间都认 |
| 她不一样（she-love-me）的 messages.json | 直接喂 | 已经为她导出过的，换个人再跑一遍 |
| 微信 / QQ / 短信截图 | AI 抄成"她：/ 我："转录稿 | 没有电脑时的兜底；重叠去重、"昨天 / 星期二"换算由脚本做 |

编码（UTF-8 / GBK / UTF-16）和格式都自动识别。哪个微信版本用哪个工具、怎么导出一个人的记录、格式认不出来怎么办：[`references/export-guide.md`](./references/export-guide.md)。

`examples/` 里是 `make_sample.py` 生成的**模拟数据**（没有任何真实的人）跑出来的完整产物，想先看看长什么样就打开 `examples/reports/`；AI 写文字前读的素材包长这样：[`examples/sample-brief.md`](./examples/sample-brief.md)。

---

## 项目结构

```
mama-message/
├── SKILL.md                    # Skill 入口：流程、模式、隐私、自检
├── CLAUDE.md · CHANGELOG.md    # 给 AI 的约束 · 版本记录
├── references/
│   ├── lexicon.json            # 全部词表（改词表不改代码）
│   ├── metrics.md              # 每个数字怎么算
│   ├── types.md                # 10 + 6 个类型、五档评级
│   ├── dictionary.md           # 黑话翻译表词典和生成规则
│   ├── writing-rules.md        # 文字规矩、禁用词黑名单、什么时候要收着
│   ├── report-template.md      # 报告模板、narrative.json 字段
│   ├── practice.md             # 练习模式
│   └── export-guide.md         # 聊天记录怎么拿出来（分平台）、截图转录格式
├── scripts/                    # 全部标准库；唯一的连接是 wechat_live 连本机 127.0.0.1
│   ├── mama.py                 # 一条命令：run / finish / explain / compare / practice / status
│   ├── wechat_live.py          # 不导出，直接读本机微信（Alpha 的只读接口）
│   ├── _common.py              # 共用：契约版本、口吻表、类型枚举、时间和时区、编码嗅探
│   ├── parse_export.py         # 各种导出和截图转录稿 → messages.json（--peek 自查 · --last-days 切片 · --tz）
│   ├── validate.py             # 检查 messages.json：格式、时间顺序、重复、金额
│   ├── stats.py                # messages.json → stats.json + 终端摘要
│   ├── brief.py                # stats + messages → brief.md（写作素材包）
│   ├── lint_narrative.py       # 检查 narrative.json：规矩、口吻、原话核对、数字核对
│   ├── render.py               # stats + narrative → 报告和两张卡（按口吻去掉版块）
│   ├── snap.py                 # 卡片 HTML → PNG（本机 Chrome / Edge 无头模式）
│   ├── compare.py              # 对照组 / 偏心报告 + 对照卡
│   └── redact.py               # 一键打码
├── assets/                     # 四个 HTML 模板（报告、账单卡、发给她的卡、对照卡）
├── prompts/普通用户版.md        # 复制粘贴版
├── web/                        # 浏览器版（index.html + sw.js，Pyodide 跑同一套脚本）
├── examples/                   # 模拟数据和产物
├── tests/                      # python -m unittest discover -s tests；fixtures/ 是各种导出格式的样本
├── evals/                      # Skill 触发测试集（该触发 / 不该触发的说法）
├── tools/                      # refresh.py 一键验证 · pack.py 打包 .skill · snapshot.py HTML → PNG
├── docs/                       # HANDOFF.md 交接文档 · img/ README 截图
└── .github/workflows/          # CI（3 个系统 × Python 3.8 / 3.12）· 打 tag 自动出 Release
```

### 开发

```bash
python tools/refresh.py                              # 一条命令：重生成示例 → 算数 → 校验 → 渲染 → lint → 素材包 → 对照卡 → 测试 → 打包同步
python -m unittest discover -s tests                 # 122 个测试，含 golden 测试和文档口径同步测试
python tools/snapshot.py                             # 可选：pip install playwright，用本机 Chrome 出 docs/img（单张卡用 scripts/snap.py 就行）
```

词表只改 [`references/lexicon.json`](./references/lexicon.json)；公式和阈值只改 `scripts/stats.py` 顶部，再同步 `references/metrics.md`、`types.md`、`prompts/普通用户版.md`；口吻只改 `scripts/_common.py` 的 `MODES`，再同步 SKILL.md 和 writing-rules.md 里的那张表。`tests/test_docs_sync.py` 会逐项比对。细则在 [`CLAUDE.md`](./CLAUDE.md)，交接文档在 [`docs/HANDOFF.md`](./docs/HANDOFF.md)。

---

## 几句丑话

报告里管短回复叫"短回复"，管没回叫"没回"，禁止往"敷衍""不孝"上引——看见数字之后得出什么结论，是你自己的事。评级那个章（模范子女 → 欠一次回家）是给你转发用的，别当真。

记录里有争吵、有控制、或者她已经不在了，工具会收着写。如果它没收住，是它的错，跟你没关系。

## 写在最后

你大概是在一个很普通的晚上刷到这个的。可能刚加完班，可能在等外卖。

她今天大概也发了一条。"吃了吗"或者"降温了"。你看到了，想着等会儿回。

这个工具做的事很简单：把"等会儿"数出来。数出来大概是四个小时，或者三天，或者一个"嗯"。

数字不会让你更爱她，你本来就爱她。它把一件你早就知道、但一直没量过的事摆到你眼前。

然后它给你一句话，你可以发出去。把责任推给软件是故意的——"它说我欠你一个电话"比"我想你了"容易说出口。

她会笑。她可能会说"什么软件啊，乱七八糟的"。

然后她会等你的电话。她一直在等。

下一个节日还有几天，报告开头写着。

<div align="center"><sub><a href="./LICENSE">MIT License</a></sub></div>
