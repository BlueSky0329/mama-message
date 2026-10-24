# CHANGELOG

## v0.6 · 2026-10-24

让写文字的 AI 写得准、让"收着"的规矩真的生效、让 Agent 少走错步。示例基线只因"没回"口径变了一次：没回 59 → 30 段，嗯哦好 42 → 35，不计较 92 → 94，评级分 62 → 55，评级和类型鉴定不变。

加：
- `scripts/wechat_live.py` 和 `mama.py run --wechat 妈`：**不用导出，直接读本机微信**。连本机 Alpha 的只读 MCP 接口（`127.0.0.1:5031/mcp`），按名字找私聊、按页读完、转成 messages.json。只连本机、不走代理、工具白名单里只有读会话和读消息、只读私聊；转账去金额，没接通的通话不算；语音秒数和通话时长都有。正文由脚本本地读和算，写文字的 AI 只看 brief.md
- `.github/workflows/pages.yml`：main 有推送就把网页版发到 GitHub Pages（T24）
- `test_docs_sync.ShowcaseNumbers`：README 首屏、示例 narrative、HANDOFF 基线里的数字和示例数据比对；README 不再写"中秋在九月底"这种会过时的话
- `scripts/brief.py`：写作素材包。把关键数字和对应的原话整理成 brief.md——她说起自己的事和你当时的回复、没回清单带上下文、她最常问的原话、她说过不止一次的话和几点说的、节日那天、她转给你的、她和你的说话方式、要不要收着、narrative.json 骨架。篇幅有上限，记录再长也读得完。网页版提示词从"整份 stats.json"换成"素材包 + 精简 stats"，AI 终于看得到原话
- `stats.py` 写作素材字段（不进指数）：`self`（她说起自己的事 + 你的回复 + 之后有没有再提）、`meal`（问吃饭几次在饭点）、`voice`（说话方式）、`sensitivity`（冲突字眼 / 催婚占比 / 最后一条多久以前 → 建议口吻）、`phrases.self_shrink_after_my_short / _her`、`unanswered.natural_end`、`basics.tz`、`source_detail`、各处消息下标 `i`；`compute_with_ctx()`
- 截图转录稿：AI 照截图抄成"她：/ 我："+ `-- 时间 --` + `=== 截图 N ===`，`parse_export.py` 去相邻截图的重叠、把倒序给的截图顺过来、按 `--shot-date` 换算"昨天 / 星期二 / 下午 3:05 / 只写几点"，换算不了的留空不编；容忍代码块包裹、"她（妈妈）："、续行带冒号。粘贴的"妈妈：… / 我：…"也认（以前 0 条）
- 口吻表 `_common.MODES`（normal / gentle / neutral / memorial / third）：`render.py` 按 narrative.json 的 `mode` 去掉版块和卡片（模板里 `<!--#版块-->` 标记），换口吻时删掉上次留下的卡；`lint_narrative.py` 按它算必填字段
- `scripts/mama.py`：run（解析 → 校验 → 算数 → 素材包）/ finish（lint → 报告和卡）/ explain（列出某个数字背后的消息）/ compare / practice（练习打分，T14）/ status，产物都在 `mama-out/`
- `scripts/snap.py` 和 `--png`：用本机 Chrome / Edge 无头模式把卡片截成 2 倍清晰度的 PNG，先量高度再截；没装浏览器就只出 HTML
- `assets/card-compare.html` 对照卡（T11）；`compare.py` 接受 messages.json / 输出目录；示例数据加了一份朋友的聊天
- `parse_export.py --tz`（T21）：Unix / UTC 时间换算到指定时区，messages.json 记 `tz`，报告数据说明自动写时区
- lint：口吻和必填、金额（错误）、发给她的那条道歉（提醒）、称呼串了（分析爸爸时冒出"她 / 母亲节"，提醒）
- `evals/triggers.json`：Skill 触发测试集 12 正 12 反（T6 备料）；SKILL.md description 加"不用于"
- 普通用户版 ④ 截图转录版（T22 第一步）
- 测试 77 → 115：`test_workflow.py`（素材、brief、口吻、对照卡、mama.py、出图）、转录稿、时区、lint 新规则、口吻表和新阈值的文档同步

改：
- lint 的数字核对不再拿时段分布、每周条数、类型打分、指数分项、消息下标作证——以前几乎任何小数字都能"找到"
- `render.py` 自动把 stats.json 的 warnings 和时区补进数据说明；核心拆成 `render_all()`
- `parse_export.py` 核心拆成 `convert()`（出错抛 `ParseError`），CLI 和 mama.py 共用
- SKILL.md 重写：一条命令、五步、追问和纠正、口吻表；writing-rules.md 加「素材从哪来」和口吻表；export-guide.md 加截图转录格式
- lexicon.json v2：加 `self_words`、`question`、`conflict`

修：
- 示例 narrative 里三处和模拟数据对不上的话："只有 3 次是在饭点"（实际 8 次在饭点、11 次不在）、"这 8 次里有 6 次前一条是她问的问题"（前一条是你的短回复）、"3 月 13 日咳嗽之后她转的三篇和这个有关"（记录里没有）；"早点睡 别熬夜"她是中午和晚上九点多发的，按 dictionary.md 第 4 条改译；发给她的那条去掉"还有 59 条我压根没回"（没回的口径是段，不是条）
- writing-rules.md、types.md 的例子同步改成和示例数据一致
- 账单卡上"嗯 / 好 / 知道了"的引号方向

定了（T23）："没回"不再算她在回你、又没问你什么的段——那是对话自然说完了（`unanswered.natural_end`）。算没回的只剩她先开口没人接的、和她回你时问了你你没接的。依据是作者真实记录：5 年 6307 段里旧口径 491 段没回，438 段是这种。

## v0.5 · 2026-09-04

架构整理，示例基线数字不变（同一份模拟数据，stats.json 逐字段一致，只多了 `schema` / `lexicon` 两个键）。

改：
- `stats.py` 拆成 `Ctx` + 一组 `sec_xxx(ctx, S)`，每个指标能单独算、单独测；不再改写传入的 messages；主题分类每条只算一次
- 词表外置到 `references/lexicon.json`（主题、收尾语、追问语、健康词、停用字……），加 `exclude` 机制挡"冷静"命中"冷"这类误判；`stats.py --lexicon` 可换词表；公式和阈值收进 `FORMULA` / `*_RULES`
- 短回复的定义写诚实了：就是"≤ 3 字"，原来代码里那个词集合每个词都不超过三个字，等于没起作用；三份文档各列一套词表（22 / 18 / 16 个）的漂移一并清掉
- 三份契约加 `schema` 版本号（`_common.SCHEMA_VERSION`）；`render.py` 拒绝旧版 stats.json 并提示重跑；`validate.py` 拒绝更新版本的 messages.json
- `parse_export.py` 改成适配器：按内容识别格式（.txt 里装 JSON 也认），`source_detail` 记录来源和版本（WeFlow 头里的版本号不再丢）、编码；`--her` 写错时报名字清单而不是把所有消息都算成"我"；`--pronoun` 对 messages.json 直通也生效
- 公共模块 `scripts/_common.py`：UTF-8 输出、JSON 读写、时间解析与格式化、类型枚举（原来在四个文件里各写一份）、编码嗅探、词表加载
- 所有脚本 `--help` 带模块说明
- 发布副本改由 `tools/pack.py --sync-to` 一并同步 `docs/HANDOFF.md`；交接文档进仓库

修：
- GB18030 / UTF-16 编码的导出文件被 `errors="ignore"` 吞掉后解析出 0 条、还误导去改 `--her`；现在自动识别编码（`redact.py` 同样）
- CSV 里的毫秒时间戳直接崩（JSON 路径早就处理了，CSV 没有）
- `--her-birthday 02-29` 或 `13-45` 崩：现在非闰年跳过、非法日期给人话错误
- `render.py` 读缺 `her_early_count` 的旧 stats.json KeyError
- 测试里的 ResourceWarning（文件没关）

加：
- `scripts/lint_narrative.py`：narrative.json 的规矩检查——必填字段、字数、感叹号、黑名单（从 writing-rules.md 读，一处定义）、评判词，**核对引号里的原话是不是记录里真有的、数字能不能在 stats.json 里找到**。SKILL 第六步、网页第三步都接了
- `tests/test_docs_sync.py`：metrics.md / types.md / 普通用户版 里复述的公式、阈值、词表和代码比对，"三处同步"从规矩变成测试
- `tests/fixtures/`：WeFlow JSON / TXT / weclone CSV、留痕 CSV、两行式、单行式、GBK、UTF-16、毫秒时间戳、扩展名骗人的样本，`tests/test_parse_export.py` 逐个核对
- `tools/refresh.py`：一条命令跑完"改完之后要做的事"，打印示例基线变化，自动改 README 里的测试数量
- `.github/workflows/ci.yml`（ubuntu / windows / macos × Python 3.8 / 3.12，并检查示例产物没漂移）、`release.yml`（打 tag 自动出 Release 附件：.skill、三个 HTML、README、SKILL、普通用户版、HANDOFF）
- 浏览器版：Pyodide 下载源竞速（jsDelivr 主站 / Fastly / Gcore / Quantil 节点 + unpkg，探的是 python_stdlib.zip 本身，失败顺延下一个；npmmirror 对 .zip 返回 451 所以不用），带进度提示；`web/sw.js` 缓存运行时，"断网也能用"成立；第一步加"只取最近 N 天 / 起止日期"；第三步粘回 narrative 后先 lint；文件名不再直接进 innerHTML
- `metrics.md` 加「时区」一节：时段按运行脚本那台机器的时区，海外用户会偏

## v0.4 · 2026-08-31

修：
- Windows 默认 GBK 控制台下 `stats.py` 打印摘要崩溃；所有脚本统一 UTF-8 输出，写文件统一 LF
- 短回复把用户自己先开口的那条（"在吗""妈我到了"）也算成"回复"；现在"回复"= 紧跟在她消息后、24 小时内发的（`short.replies`），分母同步改。注意不是用 6 小时的开启对话规则判——那会把隔 12 小时的晚回"嗯"漏掉
- "早上 8 点前"实际统计的是 0–8 点；拆成 `hours.her_early_count`（4–8 点）和 `hours.her_late_count`（22 点后）
- `parse_export.norm_ts` 对认不出或不存在的时间（"2026-13-45"）返回 `None` 而不是崩/放过
- 示例生成器把"转账 1000 元"写进了 content，违反不记金额的规矩
- 示例 narrative 有两处数字和 stats 对不上（26 vs 52 条、100 对 vs 87 对）
- `prompts/普通用户版.md` 文件名乱码、README clone 地址占位、残留空目录

加：
- `scripts/validate.py`：转录完先查 sender / 时间格式 / 时间倒序 / 相邻重复 / 转账金额 / 语音缺秒数 / sender 疑似标反，打印条数和时间范围
- `stats.json` 的 `warnings`：无时间戳过半、时间倒序、未知 sender、年份不在农历表——要照抄进报告的数据说明
- 农历节日表扩到 2022–2030，表外年份进 warnings
- `parse_export.py --call`：记录里的真名（`--her`）和报告里的称呼分开
- `parse_export.py --since / --until / --last-days`：全量导出（WeFlow / 留痕，动辄几万条跨几年）切最近一段再分析，`--last-days` 相对最后一条消息算，老档案也能用
- `parse_export.py --peek`：不写文件，打印前 10 条的解析结果和识别到的名字，格式认不出来时自己诊断
- **认 WeFlow 的三种导出**（字段从社区 fork 源码逐行核对）：详细 JSON（`createTime` 秒 / `isSend` / `localType`，49/50 型按内容标记再分类，系统消息跳过，`linkTitle` 兜底）；TXT（`时间 '名字'` 两行式，剥引号）；weclone CSV（`type_name` 列，**UTC 时间转回本地**，否则时段统计偏 8 小时）
- 转账 content 一律只写"转账"——WeFlow 的转账文案带金额（`￥10.00`），原来会原样进 messages.json；`redact.py` 补 ￥/¥ 金额模式；`[语音消息]``[转账收款]` 标记
- `tests/test_pipeline.py`：29 个测试，含 golden 测试、边界（空记录、全无时间戳、单方说话、爸爸模式）、全链路
- `references/export-guide.md`：分平台的聊天记录导出 / 截图指南
- `web/index.html`：浏览器版，Pyodide 跑同一套脚本，数据不离开浏览器；文字部分靠"复制提示词 → 粘回 narrative.json"
- `tools/snapshot.py`：用本机 Chrome（playwright，可选依赖）把三个 HTML 出成 `docs/img/*.png`，README 首屏用的就是它
- README 重排：徽章、真截图、三种用法、开发段
- `tools/pack.py`、`CLAUDE.md`、`.gitattributes`（全 LF）、本文件
- 仓库公开：https://github.com/BlueSky0329/mama-message

示例基线变化（同一份模拟数据）：短回复 53/100 → 52/93，嗯哦好 41 → 42，评级不变。

## v0.3 · 2026-08-30

SKILL.md、6 份 references、5 个脚本、3 个 HTML 模板、普通用户版提示词、README、模拟数据端到端跑通。
