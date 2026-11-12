# replace_toolkit 使用说明

docx 批量内容替换工具箱（合并版）。将原目录下的 `短替换.py` 和 `长替换.py` 合并为一个 CLI 工具，**两种替换的规则都外置在 `替换规则表.xlsx` 中**，所有日志统一输出到 `logs/` 子文件夹。

## 一、环境要求

- Windows 10/11 + Python 3.13
- 第三方依赖：

```powershell
pip install python-docx openpyxl pywin32
```

- `long` 子命令需要本机安装 Microsoft Word（通过 COM 调用）

## 二、子命令总览

| 子命令 | 来源 | 引擎 | 功能 |
|---|---|---|---|
| `short` | 短替换.py | python-docx（快） | 按「短替换」工作表的词对/正则，替换正文、表格、页眉页脚 |
| `long` | 长替换.py | Word COM（保格式） | 按规则表定位"起始关键字…结束关键字"区间，删除后插入素材 docx 原格式内容 |

用法：

```powershell
python replace_toolkit.py short
python replace_toolkit.py long
```

## 三、规则表格式（替换规则表.xlsx）

规则表位于工具包根目录（`底稿处理工具\替换规则表.xlsx`），含三个工作表：
**「填写说明」（程序不读取）、「短替换」（short 读）、「长替换」（long 读）**。
可用 `python make_rules_template.py` 重新生成模板（已存在时不覆盖）。

### 工作表「短替换」（short 用）

| A 列：查找词 | B 列：替换词 |
|---|---|
| 本募集说明书签署日 | 本文件出具日 |
| regex:2026年6月[\s\u00A0\u3000]*日 | 2026年6月30日 |
| 要删掉的词 | （留空 = 删除该词） |

- 第 1 行为表头，规则从第 2 行开始填写
- 查找词以 `regex:` 开头表示正则表达式（如匹配任意空白间隔的日期）
- 替换词留空表示删除查找词

> 若工作簿中还没有「短替换」工作表，请新建一个；脚本会给出明确报错提示。

### 工作表「长替换」（long 用）

> 注：旧版本此表名为 `Sheet1`，现已改为「长替换」；模板由 `make_rules_template.py` 生成。

| A 列：起始关键字 | B 列：结束关键字 | C 列：替换素材文件名 |
|---|---|---|
| 【起始标记】 | 【结束标记】 | 新内容素材.docx |

- C 列可写文件名（相对 `INSERT_DOCX_DIR`）或绝对路径，省略 `.docx` 后缀会自动补全
- 素材缺失的规则会被跳过并记录在日志中

## 四、配置说明

所有配置集中在 `toolkit/config.py`（业务代码以 `config.X` 属性读取，测试可覆盖）：

### short

| 配置项 | 说明 |
|---|---|
| `SHORT_RULES_XLSX` | 规则表工作簿路径（默认为上级文件夹的 替换规则表.xlsx） |
| `SHORT_RULES_SHEET` | 词对所在工作表名（默认「短替换」） |
| `SOURCE_FOLDER` | 被替换 docx 的源根目录（递归处理子文件夹，跳过 ~$ 临时文件）。本机无 D: 时默认指向仓库样本 `比较文件夹内容/new`；**short 在 SOURCE==FINAL 时原地改文件**，正式项目请改路径 |
| `FINAL_FOLDER` | 输出根目录（与源相同即原地替换） |

特性：跨 run 安全替换（合并段落后写入第一个 run）；只保存真正发生修改的文件。

### long

| 配置项 | 说明 |
|---|---|
| `RULES_XLSX` | 规则表工作簿路径 |
| `LONG_RULES_SHEET` | long 读取的工作表名（默认「长替换」，不依赖 Excel 当前活动表） |
| `TARGET_DOCX_DIR` | 被替换 docx 所在根文件夹（递归处理）。默认同样回落到仓库样本，`OVERWRITE_ORIGINAL=True` 时会改原文件 |
| `INSERT_DOCX_DIR` | 插入素材 docx 所在文件夹（默认本目录 `素材/`） |
| `OVERWRITE_ORIGINAL` | True=原地覆盖；False=另存到 `OUTPUT_DIR`（不改原文件） |
| `OUTPUT_DIR` | 另存模式的输出目录（默认脚本同级 `替换结果`） |
| `REPLACE_BOUNDARY_TEXT` | True=起止标记一并替换；False=保留标记只换中间内容 |

特性：Word Find 分段定位支持超长关键字（突破 255 字符限制）；插入时给素材加边界节隔离页面设置（横纵向/页边距/分栏不污染前后文）；自动合并不必要的同方向分节符。

## 五、日志位置

```
logs\          # 脚本同级
├── short_YYYYMMDD_HHMM.txt   # 每次运行的规则清单 + 逐文件处理结果 + 统计
└── long_YYYYMMDD_HHMM.txt    # 有效规则数、素材缺失清单、逐文件更新明细、统计摘要
```

## 六、常见问题

**Q：short 报"规则表中不存在工作表「短替换」"？**
打开 替换规则表.xlsx 新建名为「短替换」的工作表，第 1 列填查找词、第 2 列填替换词即可。

**Q：short 替换后整段格式变成第一个 run 的格式？**
这是 python-docx 跨 run 替换的固有行为（原脚本如此）：段落内命中词对时，整段文本会合并进第一个文字块。对格式敏感的长文档请改用 `long`（Word COM 保格式）。

**Q：long 报"没有可执行规则"？**
检查名为「长替换」的工作表是否从第 2 行开始有完整的三列数据，以及 C 列素材文件是否存在于 `INSERT_DOCX_DIR`。工作表名不对时脚本会报错，不会误读「短替换」。

**Q：long 运行很慢？**
正常。每个文件都要启动 Word 定位与粘贴，且逐份打开素材。建议先用小批量测试。

**Q：旧脚本还能用吗？**
原目录下的 短替换.py、长替换.py、替换规则表.xlsx、处理日志.txt 均未改动，可继续单独使用。

## 模块结构（由原单文件按原始脚本边界拆分）

`replace_toolkit.py` 现为薄壳入口（argparse 分发），实现位于 `toolkit/` 包：

| 模块 | 原始脚本 | 说明 |
|---|---|---|
| toolkit/config.py | 公共配置区 | 全部配置常量；测试经 config.X 属性覆盖（晚绑定） |
| toolkit/common.py | 公共日志区 | setup_logger + normalize_cell |
| toolkit/short_replace.py | 短替换.py | short：词对/正则替换（python-docx） |
| toolkit/long_replace.py | 长替换.py | long：区间替换+插入素材（Word COM 引擎整块平移） |

命令行用法与拆分前完全一致。

## 七、测试

```powershell
python test_replace_toolkit.py        # short 词表替换 + 横版节隔离 + Find 超 255 切分 + 规则表模板（long COM 不启动 Word）
```
