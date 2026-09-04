# CHANGELOG

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
