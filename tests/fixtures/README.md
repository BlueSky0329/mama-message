# 测试用的导出样本

每种来源一份最小样本，`tests/test_parse_export.py` 逐个解析并核对条数、发送者、类型。
没有真实的人，内容都是编的。

| 文件 | 来源 | 口径来自 | 在真实导出上验证过 |
|---|---|---|---|
| weflow.json | WeFlow 详细 JSON | fork 源码 `electron/services/exportService.ts` | 否（字段逐行核对过） |
| weflow.txt | WeFlow TXT | 同上 | 否 |
| weclone.csv | WeFlow weclone CSV（UTC 时间、BOM、CRLF） | 同上 | 否 |
| memotrace.csv | 留痕 MemoTrace / WeChatMsg CSV | 公开 schema | **否**（HANDOFF T2） |
| twoline.txt / oneline.txt | 微信 / QQ 文本导出 | 常见写法 | 部分 |
| gbk.txt / utf16.txt | 同 twoline，只是编码不同 | 老工具的 ANSI / Unicode 导出 | — |
| ms.csv | 毫秒时间戳 | — | — |
| native-as-txt.txt | messages.json 存成了 .txt | — | — |

拿到真实导出后：打码（`scripts/redact.py`）、截前几十条、放进来，在测试里加一行期望值。
gbk.txt / utf16.txt 在 .gitattributes 里标成 binary，别让编辑器"帮忙"转码。
