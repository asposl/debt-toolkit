# pdf_toolkit 使用说明

债承 PDF/docx 处理工具箱（合并版）。本脚本将原目录下的 6 个独立脚本合并为一个 CLI 工具，所有日志与清单文件统一输出到 `logs/` 子文件夹。

## 一、环境要求

- Windows 10/11 + Python 3.13
- 第三方依赖：

```powershell
pip install python-docx pypdf pywin32
```

- `export` 子命令需要本机安装 Microsoft Word（通过 COM 调用导出 PDF）

## 二、子命令总览

| 子命令 | 合并来源 | 功能 |
|---|---|---|
| `format` | 宋体Arial.py | 批量刷新 docx 格式（黑体标题 + 宋体正文 + Arial 西文） |
| `header` | 页眉检查.py | 检查并修复 docx 页眉编号 |
| `export` | 输出签章页.py | Word→PDF 全量导出、拆末页合并签章页、生成清单 |
| `filter` | check_sign.py | 过滤 no_company JSON 中含"索引"的条目，输出带默认页码的清单 |
| `insert` | 插入签章页.py + 插入签字页.py | 追加签章页 / 替换末页或指定页为签字页 |

用法：

```powershell
python pdf_toolkit.py format
python pdf_toolkit.py header
python pdf_toolkit.py export
python pdf_toolkit.py filter
python pdf_toolkit.py insert --mode append     # 按 has_company JSON 追加签章页到 PDF 末尾
python pdf_toolkit.py insert --mode replace    # 按无索引清单用签字页替换末页或指定页
```

## 三、标准工作流程

一个完整项目的典型执行顺序：

```
① format   刷新 docx 格式（黑体标题+宋体正文+Arial西文）
② header   修复页眉编号
③ export   Word→PDF 导出，按公司名拆末页并合并成 签章页.pdf，
           生成 has_company_latest.json / no_company_latest.json
④ filter   从 no_company JSON 中过滤"索引"条目，
           生成 no_company_无索引_latest.log（每行默认「路径|末页」）
⑤ insert --mode append    把 签章页.pdf 逐份追加到对应 PDF 末尾
⑥ insert --mode replace   用签字合并 PDF 替换无索引文件的末页或指定页
```

> 步骤 ③④ 的产物默认写入固定名副本（`*_latest.json` / `*_latest.log`），步骤 ⑤⑥ 默认直接引用它们——**整条链跑下来不需要中途改配置**。
>
> **签字页不在末页的例外文件**（如签字页后有附件）：复核纸质版对目录时顺便记下该文件签字页在第几页，把清单里对应行的「末页」改成具体页码（如 `xxx.pdf|12`）即可，无需再手动调整 PDF。
>
> **不要在拆页后再跑一遍 `export`。** 第二次会复用已拆过的 PDF，末页公司名已经不在，`has_company_latest.json` 会被写成空清单，下游 insert 就对不上。需要重导时先把该 PDF 删掉，或把 `EXPORT_RECENT_PDF_MAX_AGE_DAYS` 设为 0。

## 四、配置说明

所有配置集中在 `toolkit/config.py`，换项目时只需改这一处：

### 公共配置

| 配置项 | 说明 |
|---|---|
| `PROJECT_TAG` | 项目标识（如"示例"、"示例"），拼进输出文件名用于区分项目 |
| `PROJECT_ROOT` | 项目根文件夹。`format` / `header` / `export` / `insert` 的目录都从这里派生。本机无 D: 正式盘时默认指向仓库样本 `比较文件夹内容/new`；**format / header / export / insert 会原地改这个目录**，正式项目请改回配置文件里注释的 D: 路径 |

### format

| 配置项 | 说明 |
|---|---|
| `FORMAT_INPUT_FOLDER` | 要处理的 docx 根文件夹（默认等于 `PROJECT_ROOT`，递归处理所有子文件夹） |
| `FORMAT_UPDATE_DAYS` | 只处理最近 N 天内更新的文件 |

格式化规则：章节标题黑体小二、"一、"/"（一）"/"1、"/"（1）"/"1)"/"①"各级标题按层级设置字号加粗、正文宋体小四、全部行距 1.5；中文用宋体/黑体、英文数字强制 Arial；表格只刷字体不改字号和加粗；居中/右对齐段落保留原对齐且不加首行缩进。

### header

| 配置项 | 说明 |
|---|---|
| `HEADER_ROOT_DIR` | 要扫描的根文件夹（默认等于 `PROJECT_ROOT`） |
| `HEADER_DRY_RUN` | `True` 只检查不修改；`False` 检查并修改 |

规则：从文件名提取编号（如 `4-1-1`），与各节页眉中的编号比对，不一致则替换、缺失则补入或新建页眉。同时自动修复旧版工具可能造成的 XML 命名空间损坏。

### export

| 配置项 | 说明 |
|---|---|
| `EXPORT_ROOT_FOLDER` | 项目根文件夹（Word/PDF 所在位置，默认等于 `PROJECT_ROOT`） |
| `EXPORT_COMPANY_KEYWORD` | 公司全名关键字，用于识别需拆末页的文件 |
| `EXPORT_MERGED_PDF_NAME` | 合并后的签章页 PDF 文件名（输出到根文件夹） |
| `EXPORT_RECENT_PDF_MAX_AGE_DAYS` | 最近 N 天生成的 PDF 直接复用不重导出（0 关闭） |
| `EXPORT_PATH_LENGTH_LIMIT` | 超长路径 docx 自动改名阈值（防 MAX_PATH=260 报错） |

流程分四个阶段：① 缩短超长路径文件名 → ② Word 全量导出 PDF → ③ 自然排序后识别末尾 150 字是否含公司名，含则拆出末页并入签章页 → ④ 输出清单与日志。

### filter

| 配置项 | 说明 |
|---|---|
| `FILTER_JSON_PATH` | 输入 JSON 清单，默认 `no_company_latest.json`（相对路径找不到时会自动尝试 `logs/` 目录） |
| `FILTER_KEYWORD` | 需要过滤掉的关键字（默认"索引"） |

filter 输出的无索引清单每行带默认页码标记：`路径|末页`。例外文件（签字页不在末页）人工把「末页」改为具体页码即可。

### insert

| 配置项 | append 模式 | replace 模式 |
|---|---|---|
| 清单 | `APPEND_JSON_PATH`（默认 `has_company_latest.json`） | `REPLACE_LIST_PATH`（默认 `no_company_无索引_latest.log`） |
| 签字 PDF | `APPEND_SIGNATURE_PDF_PATH`（默认 `PROJECT_ROOT\签章页.pdf`） | `REPLACE_SIGNATURE_PDF_PATH`（默认 `PROJECT_ROOT\签字合并.pdf`） |
| 根目录 | `APPEND_ROOT_DIR`（默认 `PROJECT_ROOT`） | `REPLACE_ROOT_DIR`（默认 `PROJECT_ROOT`） |

- **append**：把签章 PDF 第 i 页**追加**到清单第 i 个文件末尾；清单与 PDF 页数不一致时告警并按较小值匹配。默认签章 PDF 为 `PROJECT_ROOT\签章页.pdf`（即 export 的交付物）。
- **replace**：用签字 PDF 第 i 页**替换**清单第 i 个文件的目标页（用于去掉目录等自带的签字页再放回）；数量不一致时直接拒绝执行。默认签字 PDF 为 `PROJECT_ROOT\签字合并.pdf`。
  - 清单条目格式：`路径|末页`（filter 的默认输出，替换末页）、`路径|数字`（1 起算，替换第 N 页）或旧版纯 `路径`（等同末页）。签字页不在末页的例外文件，把「末页」改成具体页码即可。
  - 页码越界：跳过该条、计入失败数且不改动文件；页码非法（非数字/≤0）：动手前整体拒绝执行。每次替换都会把被替换页的首行文本写入日志留痕。
- 两者均采用临时文件写回 + `os.replace`，写入中断不会损坏原文件。
- 清单支持 `.json` 和逐行一条的 `.txt/.log` 两种格式，按扩展名自动识别；`.log` 会自动跳过旧版文件末尾的「统计信息」块。

## 五、输出文件位置

| 文件 | 位置 |
|---|---|
| 运行日志（每个子命令每次运行一份） | 脚本同级 `logs\<任务>_<项目标识>_<YYYYMMDD_HHMM>.txt` |
| has/no_company 清单 | `logs\has_company_<标识>_<时间戳>.json` 等 + 固定名 `*_latest.json` 副本 |
| 无索引清单 | `logs\no_company_无索引_<标识>_<时间戳>.log` + 固定名 `_latest.log` 副本（**只含路径，不含统计**） |
| 全流程处理日志（export） | `logs\processing_log_<标识>_<时间戳>.txt` |
| **签章页.pdf（交付物）** | **项目根文件夹**（`PROJECT_ROOT` / `EXPORT_ROOT_FOLDER`），不在 logs 里 |

## 六、常见问题

**Q：换新项目要改哪里？**
优先改 `toolkit/config.py` 里三处：`PROJECT_TAG`、`PROJECT_ROOT`、`EXPORT_COMPANY_KEYWORD`。format / header / export / insert 会跟着 `PROJECT_ROOT` 走。示例/示例正式盘路径以注释形式留在配置文件中。

**Q：insert 提示"ROOT_DIR 不存在"？**
默认样本目录应存在；若已改成 D: 正式盘但本机没有该盘符，把 `PROJECT_ROOT` 改回实际项目顶层文件夹。format / header / export 也会读同一根路径。

**Q：insert 提示"数量不匹配，已拒绝执行"？**
replace 模式要求清单条数与签字 PDF 页数严格相等。检查 filter 清单是否最新、签字合并 PDF 是否对应同一批文件。

**Q：export 后部分 PDF 没有重新导出？**
这是 PDF 复用机制在生效（`EXPORT_RECENT_PDF_MAX_AGE_DAYS`）。若源 docx 比 PDF 新会强制重导；确需全部重导可把该值设为 0。已经拆过末页的 PDF 被复用时，会因为末页不再含公司名而改记入 `no_company`，并把 `has_company_latest.json` 冲空。

**Q：format 会改动对齐方式吗？**
不会。所有段落仅刷字体/字号/行距/缩进，原有居中、右对齐等对齐方式全部保留。

**Q：旧脚本还能用吗？**
原目录下的 6 个 .py、历史 log/json 与 `格式匹配.ipynb` 均未改动，可继续单独使用；本工具只是功能上的整合替代。

## 模块结构（由原单文件按原始脚本边界拆分）

`pdf_toolkit.py` 现为薄壳入口（argparse 分发），实现位于 `toolkit/` 包：

| 模块 | 原始脚本 | 说明 |
|---|---|---|
| toolkit/config.py | 公共配置区 | 全部配置常量；测试/脚本经 config.X 属性覆盖 |
| toolkit/logutil.py | 公共日志区 | setup_logger / _resolve_input / _log_path |
| toolkit/format_word.py | 宋体Arial.py | format：docx 格式刷新（python-docx） |
| toolkit/header_fix.py | 页眉检查.py | header：页眉编号检查修复（OOXML，整块平移） |
| toolkit/export_sign.py | 输出签章页.py | export：Word→PDF 导出+拆末页合并（COM 整块平移） |
| toolkit/filter_index.py | check_sign.py | filter + 清单读取工具（供 insert 共用） |
| toolkit/insert_pages.py | 插入签章页.py + 插入签字页.py | insert append/replace |

命令行用法与拆分前完全一致。

## 七、测试

```powershell
python test_pdf_toolkit.py            # header/format/filter/insert + ASCII PDF 拆页 + Word COM 全链路（临时目录，不动样本 new/）
```
