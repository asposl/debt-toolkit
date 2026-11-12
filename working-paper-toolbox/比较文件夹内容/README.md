# folder_toolbox 使用说明

docx 文件夹工具箱：比较、合并、提取打印，三合一 CLI 工具（纯标准库，无第三方依赖）。
所有日志统一输出到脚本同级的 `logs\` 子文件夹。

## 一、环境要求

- Windows 10/11 + Python 3.13（无需安装任何第三方包）

## 二、子命令总览

| 子命令 | 来源 | 功能 |
|---|---|---|
| `compare` | compare.py | 递归比较两个母文件夹中的 docx，按相对路径 + SHA-256 找出差异 |
| `merge` | merge_file.py | 按文件名匹配，用 new 中的最新版覆盖 old（不备份） |
| `extract` | 提取打印文件.py | 把多级文件夹中的 doc/docx 平铺复制到一个文件夹，方便批量打印 |

用法：

```powershell
python folder_toolbox.py compare [old_folder] [new_folder] [--json]
python folder_toolbox.py merge   [old_folder] [new_folder]
python folder_toolbox.py extract [source_folder] [output_folder] [--no-prefix] [--clear-output]
```

## 三、默认参数

不传路径时使用 `toolbox/common.py` 顶部的常量（在 VSCode 中改这里后可直接 F5 运行）：

| 常量 | 用途 |
|---|---|
| `DEFAULT_OLD_FOLDER` / `DEFAULT_NEW_FOLDER` | compare / merge 的旧、新文件夹（默认本目录 `old/`、`new/`） |
| `DEFAULT_SOURCE_FOLDER` / `DEFAULT_OUTPUT_FOLDER` | extract 的源与平铺输出（默认 `new/` → 本目录 `打印文件/`） |
| `EXTENSIONS` / `ADD_ORDER_PREFIX` / `CLEAR_OUTPUT` | extract 行为开关（命令行 `--no-prefix` / `--clear-output` 可覆盖） |

## 四、各命令要点

### compare
- 按"相对路径相同但 SHA-256 不同 / 仅一侧存在"输出三份差异清单
- 额外报告「同名但相对路径不同」（以及同一侧同一文件名出现多次），不替代上面三份路径级清单
- `--json` 以 JSON 输出结果，便于其他程序继续处理
- 比较键是相对路径，不是文件名；同名不同路径不会被当成「内容变化」

### merge
- 六类结果分别统计：被修改 / 新增 / 内容相同 / old 独有缺失新版 / 重名冲突跳过 / 复制失败
- 复制失败（如文件被占用）只记录不中断整体流程

### extract
- 按资源管理器习惯排序：每层先处理文件再进入子文件夹；支持中文序号（第九章 < 第十章）
- 默认加 `001_` 序号前缀；重名自动改名为 `xxx__2.docx`
- 自动跳过 Office 临时锁定文件（`~$` 开头）；`--clear-output` 只清 Word 文件、不动其他类型
- `--test` 生成测试用例并自检（等价于直接运行 `test_提取打印文件.py`）

## 五、日志位置

```
logs\
└── {功能}_{项目名}_{YYYYMMDD_HHMM}.log    # compare 结果报告 / merge 替换明细 / extract 复制清单
```

## 六、测试

```powershell
python test_提取打印文件.py        # 覆盖 extract 全链路（含真实 old 目录抽检）
python test_folder_toolbox.py      # 覆盖 compare / merge / 默认 old+new 只读冒烟（extract 输出写临时目录）
```

## 模块结构（由原单文件按原始脚本边界拆分）

`folder_toolbox.py` 现为薄壳入口（argparse 分发），实现位于 `toolbox/` 包；
入口同时兼容导出全部原有符号，旧导入方式不受影响：

| 模块 | 原始脚本 | 说明 |
|---|---|---|
| toolbox/common.py | 公共配置区 + 共享工具函数 | 常量、SHA-256、路径/日志工具 |
| toolbox/compare.py | compare.py | 哈希比较两个文件夹 |
| toolbox/merge_file.py | merge_file.py | new 中同名 docx 覆盖 old |
| toolbox/extract.py | 提取打印文件.py | 平铺提取 Word 用于批量打印 |

命令行用法与拆分前完全一致。
