# file_toolkit 使用说明

债承文件整理工具箱（统一版）。将三个来源整合为一个 CLI：`organize_toolkit.py`（有息负债流水线）、`会计科目底稿整理.py`（财务底稿整理）、`有息负债-担保重命名.ipynb`（顺序重编号）。

**所有路径均通过命令行参数传入，不再硬编码。** 所有涉及改名的命令默认【预览模式】，加 `--apply` / 对应执行开关才真正落盘。日志统一输出到脚本同级的 `logs\` 子文件夹。

## 一、环境要求

- Windows 10/11 + Python 3.13
- 第三方依赖：

```powershell
pip install pillow pandas openpyxl pypdf
```

## 二、子命令总览

### 组A：有息负债建档流水线

| 子命令 | 功能 |
|---|---|
| `dedup_folders` | 按内容指纹对编号子文件夹去重并复制到输出目录 |
| `convert_images` | 递归把 jpg/jpeg/png/jfif 转为 PDF 并删除原图 |
| `match_excel` | 台账 Sheet1/Sheet2 字段匹配：给 Sheet1 加 num 列、导出未匹配 CSV |
| `merge_pdfs` | 按 num 编号定位文件夹，按特征优先级排序合并 PDF |

### 组B：财务底稿整理

| 子命令 | 功能 |
|---|---|
| `pdf_merge` | 子文件夹合并 → 铺平 → 连贯编号（两阶段，可分步核对） |
| `flat_rename` | 多个文件夹各自平铺/原地重命名 |
| `order_rename` | 多个固定位置的 PDF 按给定顺序全局连贯编号 |

### 组C：通用重编号

| 子命令 | 功能 |
|---|---|
| `renumber_files` | 已有"N 名称.pdf"的文件夹按原编号顺序重新连贯编号 |

## 三、用法示例

```powershell
# ---- 组A ----
python file_toolkit.py dedup_folders --source E:\src --output D:\out `
    [--layout single|nested] [--no-image-convert]
python file_toolkit.py convert_images --target D:\out
python file_toolkit.py match_excel --excel ht.xlsx --output-dir . `
    [--cols "贷款机构,借款单位,余额,借款日,到期日,利率"]
python file_toolkit.py merge_pdfs --excel 匹配结果_已添加num.xlsx `
    --folders D:\out --output D:\合并 [--features 特征表.json]

# ---- 组B（默认预览，--apply 执行）----
python file_toolkit.py pdf_merge --top "D:\...\2-3-6-2$权属证明" --prefix 2-3-6-2-
python file_toolkit.py pdf_merge --top ... --prefix ... --merge     # 阶段一：合并
python file_toolkit.py pdf_merge --top ... --prefix ... --flatten   # 阶段二：铺平编号
python file_toolkit.py pdf_merge --top ... --prefix ... --all       # 一步完成
python file_toolkit.py flat_rename --parent "D:\底稿目录" `
    --folders "2-3-5-7 固定资产科目核查:flat,2-3-5-8 无形资产科目核查" --apply
python file_toolkit.py order_rename --locations D:\a\土地使用权证 D:\a\开发成本 `
    --prefix 2-3-5-6- --apply

# ---- 组C（默认预览，--apply 执行）----
python file_toolkit.py renumber_files --folder 示例对外担保 [--start 1] [--apply]
```

## 四、各命令要点

### dedup_folders
- 编号识别兼容纯数字、`99-100` 范围、带中文后缀（`114（查不到此笔放款）`）
- 指纹 = 文件相对路径 + MD5 全量比对；重复只保留编号最小的副本；源目录不动
- `--layout nested` 处理"母/子"两层结构；默认复制后先转图片再判重（`--no-image-convert` 关闭）

### match_excel
- `--cols` 可自定义匹配字段；Sheet2 的"序号"列作为 num 来源
- 校验缺失列并给出明确报错
- 匹配前会去掉整数值浮点的 `.0`，真正的空值保持 NA；空值行不会互配（含 pandas 3 把 NA 键当相等的情况）

### merge_pdfs
- num 支持单数字与 `3-6` 范围；文件夹名只认**开头**的编号（`5 …` / `99-100 …`）。`2-3-5-7 固定资产` 这种多段索引不会被拆成 2-3
- 文件夹内有任一文件匹配不到特征 → 整体放弃合并（防漏件）
- 一份都没合并成功时退出码为 1
- `--features` 可传入 JSON 数组自定义特征优先级，缺省为内置的 合同→担保→决议→借据 顺序

### pdf_merge（原 merge）
- 建议分步：先 `--merge` 出合并件人工核对，再 `--flatten` 铺平编号（会删除子文件夹内原始 PDF，不可恢复）
- 子文件夹内再套一层也能合并（按真实路径读取，不只看子文件夹根目录）
- `--flatten` 发现某个子文件夹还没有合并件时会拒绝执行，避免误删原始 PDF

### flat_rename（原 r5789）
- `--folders` 格式 `"目录名[:flat],..."`；`:flat` 表示递归收集并把文件移到顶级
- 编号前缀自动取目录名第一个空格前的部分，产出 `前缀-N 名称.pdf`

### order_rename（原 r56）
- `--locations` 的给出顺序即编号顺序，跨位置全局连贯；每个位置内部按自然排序（2 在 10 前）；原地重命名

### renumber_files（新收编）
- 把 `3 xxx.pdf`、`1 yyy.pdf`、`10 zzz.pdf` 按原编号顺序重排为 1/2/3…
- 两阶段临时名改名，杜绝中间态命名冲突；未匹配编号模式的文件会被跳过并在日志中明确警告
- `--pattern` 可自定义匹配模式（需两个捕获组：旧编号、其余名称），`--start` 指定起始号

## 五、相对原代码的修正

1. **自然排序修复**：铺平编号原来用字典序，`10 xxx` 会排在 `2 xxx` 前；现全部走统一编号内核的自然排序（含子目录收集）
2. **重编号安全化**：ipynb 版本无预览直接落盘且静默跳过不匹配文件；现默认预览 + 显式警告跳过清单 + 冲突检查
3. **统一编号内核**：四个编号场景共用 collect→sort→assign 一条链，原地改名统一两阶段临时名方案；flatten 也走两阶段，失败会尽量回滚到原名
4. **清理死代码**：删除 r56 中完全相同的 if/else 分支等残留

## 六、常见问题

**Q：命令跑完没改任何文件？**
组B/组C 的命令默认预览模式，确认计划无误后加 `--apply`（pdf_merge 加对应阶段开关）。

**Q：flat_rename 报"目标已存在"？**
顶级目录已有同名目标文件。先清理或换前缀；工具不做覆盖。

**Q：renumber_files 提示跳过了文件？**
被跳过的 PDF 不符合 `^\d+\s+(.*)$`（没有"N "前缀）。如需纳入，先手工补编号或调整 `--pattern`。

**Q：日志在哪？**
脚本同级 `logs\<子命令>_<YYYYMMDD_HHMM>.txt`，控制台与文件内容一致。

## 模块结构（由原单文件按原始脚本边界拆分）

`file_toolkit.py` 现为薄壳入口（argparse 分发），实现位于 `toolkit/` 包：

| 模块 | 来源 | 说明 |
|---|---|---|
| toolkit/logutil.py | 公共日志区 | setup_logger |
| toolkit/numbering.py | 编号内核 | 收集/排序/编号/两阶段重命名/核验（组B、C 共用） |
| toolkit/imaging.py | convert.ipynb 图片核心 | 图片转 PDF |
| toolkit/dedup.py | organize_toolkit·dedup_folders | 组A 去重复制 |
| toolkit/ledger_match.py | organize_toolkit·match_excel | 组A 台账匹配 |
| toolkit/ledger_merge.py | organize_toolkit·merge_pdfs | 组A 特征优先级合并 |
| toolkit/working_paper.py | 会计科目底稿整理.py 整体 | 组B pdf_merge / flat_rename / order_rename |
| toolkit/renumber.py | 有息负债-担保重命名.ipynb 单元1 | 组C renumber_files |

命令行用法与拆分前完全一致。

## 七、测试

```powershell
python test_file_toolkit.py           # 组B/组C 冒烟：renumber / pdf_merge / flat_rename / order_rename / match_excel
python test_file_toolkit_group_a.py   # 组A + 编号内核：dedup / convert_images / merge_pdfs / numbering
```
