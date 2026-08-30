# CHANGELOG

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
