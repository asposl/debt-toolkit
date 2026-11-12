# GUI接口文档

> 供后续修改/二次开发使用。配套文件：`底稿工具箱GUI.py`（界面）、`gui_runner.py`（子进程中转器）、`README_GUI.md`（用户手册）。
> 最后更新：2026-08-23

---

## 一、总体架构

```
┌────────────────────┐  subprocess.Popen   ┌──────────────────────┐
│  底稿工具箱GUI.py   │ ──────────────────► │  gui_runner.py        │
│  (Tkinter 主进程)   │  argv[1] = JSON     │  (独立 Python 子进程)  │
│                    │ ◄────────────────── │                      │
│  后台线程读 stdout  │  stdout/stderr 流   │  覆写 config 后调用    │
│  queue + after()   │  (utf-8)            │  各模块命令函数        │
└────────────────────┘                     └──────────────────────┘
                                                    │ import
                                    ┌───────────────┼────────────────┐
                                    ▼               ▼                ▼
                              签章页工具/       替换底稿内容/      多级文件夹生成目录/
                              pdf_toolkit      replace_toolkit   输出文件目录.py
```

两类任务通道：

| 通道 | 适用模块 | 原因 |
|---|---|---|
| **经 gui_runner.py 中转** | 签章页工具、替换底稿内容、初始化底稿文件、目录生成 | 路径等配置写死在各模块 `config.py` / 脚本顶部，需在子进程内动态覆写 |
| **GUI 直调 CLI** | 比较文件夹内容（folder_toolbox.py）、底稿PDF材料整理（file_toolkit.py） | 原生支持完整命令行参数，直接 `python 脚本.py 子命令 参数…` |

**为什么必须子进程隔离**（改代码前必读）：

1. 各模块的实现包同名：签章页工具、替换底稿内容、底稿pdf材料都有 `toolkit/`，比较文件夹内容是 `toolbox/`。同进程内先后 import 会发生 `sys.modules` 冲突，只有独立子进程能彻底隔离。
2. Word COM（export / long）等重资源操作若在 GUI 进程内跑，崩溃会拖死界面。
3. 部分模块的 `config.py` 在**导入时**就把派生路径赋值完毕（如 `FORMAT_INPUT_FOLDER = PROJECT_ROOT`），覆写时机必须早于命令函数调用——中转器正是为此存在。

---

## 二、gui_runner.py 任务协议

### 2.1 调用方式

```powershell
python gui_runner.py "<JSON 字符串>"
```

JSON 结构统一为：

```json
{ "task": "<任务类型>", "params": { ... } }
```

- 退出码：`0` = 成功；非 `0` = 失败（透传下游命令函数返回值，或异常时 Python 默认 1）。
- 所有输出走 stdout/stderr，编码 utf-8（脚本顶部已 `reconfigure`）。
- 任务类型注册在模块底部的 `TASKS` 字典，新增任务在这里挂载。

### 2.2 任务类型一览

#### `sign` —— 签章页工具（pdf_toolkit）

| param | 类型 | 说明 | 覆写的 config 属性 |
|---|---|---|---|
| cmd | str | `format` / `header` / `export` / `filter` / `insert_append` / `insert_replace` | — |
| root | str | 项目根目录（必填） | `PROJECT_ROOT`、`FORMAT_INPUT_FOLDER`、`HEADER_ROOT_DIR`、`EXPORT_ROOT_FOLDER`、`APPEND_ROOT_DIR`、`REPLACE_ROOT_DIR`、`APPEND_SIGNATURE_PDF_PATH`、`REPLACE_SIGNATURE_PDF_PATH` |
| tag | str? | 项目标识 | `PROJECT_TAG` |
| keyword | str? | 公司关键字 | `EXPORT_COMPANY_KEYWORD` |
| dry_run | bool | 页眉只检查 | `HEADER_DRY_RUN` |
| update_days | int | format 只处理最近 N 天 | `FORMAT_UPDATE_DAYS` |
| pdf_reuse_days | int | PDF 复用天数 | `EXPORT_RECENT_PDF_MAX_AGE_DAYS` |

⚠️ **关键点**：`config.py` 中派生路径在导入时赋值，因此 root 必须**同时覆写全部 8 个派生属性**（见 `_run_sign`）。若 pdf_toolkit 未来新增从 `PROJECT_ROOT` 派生的配置，这里要同步补。

#### `replace` —— 替换底稿内容（replace_toolkit）

| param | 类型 | 说明 | 覆写的 config 属性 |
|---|---|---|---|
| cmd | str | `short` / `long` | — |
| rules_xlsx | str | 规则表路径 | `SHORT_RULES_XLSX`、`RULES_XLSX` |
| source | str | docx 根目录 | `SOURCE_FOLDER`、`TARGET_DOCX_DIR` |
| final | str? | short 输出目录（空=原地） | `FINAL_FOLDER` |
| insert_dir | str? | long 素材目录 | `INSERT_DOCX_DIR` |
| overwrite | bool | long 是否覆盖原文件 | `OVERWRITE_ORIGINAL` |
| output_dir | str? | long 另存目录 | `OUTPUT_DIR` |

#### `init` —— 初始化底稿文件

目标脚本 `签章页工具\初始化底稿文件.py` 是**顶层硬编码配置的独立脚本**（非 config 包），无法直接 import（顶层 `os.makedirs` 会按硬编码的【示例项目】路径建目录）。`_run_init` 的做法：

1. 读源码，**临时屏蔽 `os.makedirs`** 后 `exec` 到独立 namespace（屏蔽 import 副作用）；
2. 向 namespace 覆写全局变量：`INPUT_FOLDER` / `OUTPUT_FOLDER` / `SEPARATE_FOLDER`（= root / separate）、`issuer`、`project_team`、`date`、`sign_name`；
3. 恢复 `os.makedirs` 后调用 `namespace["main"]()`。

| param | 类型 | 说明 |
|---|---|---|
| root | str | 待处理 Word 文件夹（写入 INPUT/OUTPUT/SEPARATE 三项） |
| separate | str? | 汇总签章页独立输出目录（空=同 root） |
| issuer / project_team / date / sign_name | str? | 对应脚本同名全局变量 |

#### `dirgen` —— 目录生成

直接 import `多级文件夹生成目录\输出文件目录.py`（无副作用），调用：

- `export_directory_to_excel(target, excel)`
- `export_excel_to_word_directory(excel, word)`

| param | 类型 | 说明 |
|---|---|---|
| target | str | 目标文件夹（生成 Excel 时必填） |
| excel | str | Excel 输出路径（必填） |
| word | str? | Word 输出路径（填了则需 excel 已存在） |

### 2.3 新增任务类型的步骤

1. 在 `gui_runner.py` 写 `_run_xxx(p)` 处理函数（p 为 params 字典），内部 `sys.path.insert(0, 模块目录)` → 覆写配置 → 调用命令函数 → `return int 退出码`；
2. 注册进 `TASKS` 字典；
3. GUI 侧加启动方法（见 3.3）。

---

## 三、底稿工具箱GUI.py 内部接口

### 3.1 类与关键状态

```
ToolBoxApp
├── self.vars        {key: tk.StringVar/BooleanVar}   全部输入变量注册表
├── self.run_buttons [ttk.Button]                     所有执行按钮（任务运行时统一禁用）
├── self._busy       bool                             任务锁（同一时刻仅一个任务）
├── self._proc       subprocess.Popen                 当前子进程
├── self._queue      queue.Queue                      子进程输出队列（行字符串 / 结束哨兵元组）
└── self.log_text    tk.Text                          共享日志区
```

### 3.2 线程模型

- **子进程读取在 daemon 线程**（`_worker`）：Popen 逐行读 stdout → `queue.put`；结束时 put 哨兵元组 `(label, returncode)`。
- **Tkinter 更新只在主线程**（`_poll_queue`，`after(80)` 轮询）：取队列内容写日志；收到哨兵后调 `_finish` 复位 `_busy`、恢复按钮。
- ⚠️ 任何新建任务代码都必须走 `_launch` 入口，不要在回调里直接碰 `_proc` 或跨线程调 Tkinter。

### 3.3 任务启动方法（GUI → 子进程）

| 方法 | 用途 |
|---|---|
| `_launch_runner(label, task, params)` | 经 gui_runner.py 中转的任务 |
| `_launch_cli(label, module_dir, script, args)` | 直调某模块目录下的 CLI 脚本 |
| `_launch(label, argv, cwd=None)` | 底层入口：加任务锁 → 存设置 → 起线程 |

各页签的参数收集方法：`_run_sign(cmd)`、`_run_init()`、`_run_replace(cmd)`、`_run_extract()`、`_run_filetoolkit()`、`_run_dirgen(excel_only)`。

**新增一个执行按钮的标准流程**：

```python
def _run_mytask(self):
    params = {...}                       # 从 self.vars 收集
    if not self._check_paths([("标签", path, True)]):   # 必填校验
        return
    self._launch_runner("任务名", "tasktype", params)   # 或 _launch_cli
```

### 3.4 输入变量命名规则

`self.vars` 的 key 即设置持久化的 key，命名约定：

| 前缀 | 页签 | 示例 |
|---|---|---|
| `sign.` | 签章页六步 | `sign.root`、`sign.dry_run` |
| `init.` | 初始化底稿文件 | `init.issuer` |
| `rep.` | 替换底稿内容 | `rep.source` |
| `cmp.` / `ext.` | 比较/提取 | `cmp.old`、`ext.prefix` |
| `ft.<参数key>` | 底稿PDF材料整理动态表单 | `ft.--top`、`ft.--apply` |
| `dg.` | 目录生成 | `dg.target` |

注册方式：`self._var(key, default, kind)`（kind: `"str"`/`"bool"`/`"int"`，int 实际存 StringVar）。
持久化：`_save_settings()` / `_load_settings()` 读写 `.zcode/gui_settings.json`，遍历 `self.vars`，无需额外登记。

### 3.5 表单构建辅助

| 方法 | 用途 |
|---|---|
| `_row_path(parent, row, label, key, default, is_file=False)` | 标签+输入框+浏览按钮 一行；返回下一行号 |
| `_run_btn(parent, text, command, **geom)` | 创建执行按钮并登记进 `run_buttons`；含 `row=` 时走 grid，否则 pack |
| `_check_paths([(label, path, must_dir)])` | 必填/存在性校验，弹窗提示 |
| `_confirm_then(message, func)` | 确认框包装 |
| `_to_int(key, default)` | Spinbox 值安全转 int |

### 3.6 底稿PDF材料整理动态表单（FILE_CMDS）

`ToolBoxApp.FILE_CMDS` 是声明式配置，**加新子命令只需加一条配置**，无需写界面代码：

```python
"命令显示名": {
    "sub": "CLI子命令名",
    "fields": [
        {"key": "source",   "label": "源目录",        "type": "path"},          # 必填目录 → --source
        {"key": "--excel",  "label": "台账 xlsx",     "type": "file"},          # 文件（label 含"(可选)"则可空）
        {"key": "--cols",   "label": "匹配列",        "type": "text", "default": "..."},
        {"key": "--layout", "label": "目录结构",      "type": "combo", "options": [...], "default": "single"},
        {"key": "--apply",  "label": "实际执行",      "type": "flag"},          # 勾选则追加裸旗标
        {"key": "--start",  "label": "起始编号",      "type": "int", "default": 1},
        {"key": "folders",  "label": "...", "type": "wide"},   # 多行 Text，压成单行（逗号清单）
        {"key": "locations","label": "...", "type": "lines"},  # 多行 Text，每行一个值（nargs="+")
        {"key": "__stage",  "label": "执行阶段", "type": "combo", ...},  # 特殊key：pdf_merge 阶段→--merge/--flatten/--all
    ],
}
```

- key 不带 `--` 的 path 类型会自动补 `--` 前缀；
- `_rebuild_ft_fields()` 切换下拉时销毁重建表单，控件存 `self.ft_widgets`（仅 wide/lines 需要）；
- 参数拼装在 `_collect_ft_args()`，缺必填项抛 `ValueError` 由调用方弹窗。

---

## 四、修改指南（按场景）

### 场景 A：给现有页签加一个输入项

1. 页签构建方法里加一行 `self._row_path(...)` 或 `ttk.Entry(textvariable=self._var("前缀.新key", 默认值))`；
2. 对应 `_run_xxx` 里把 `self.vars[...].get()` 塞进 params；
3. 若经 runner 中转，在 `_run_xxx`（runner 侧）覆写对应 config 属性。
   设置记忆自动生效，无需改持久化代码。

### 场景 B：签章页工具新增子命令（如 pdf_toolkit 加了 `xxx`）

1. `gui_runner.py::_run_sign` 的 `dispatch` 字典加 `"xxx": lambda lg: cmd_xxx(lg)`；
2. GUI `_tab_sign` 的 `steps` 列表加按钮、`SIGN_STEP_NAMES` 加显示名；
3. 若需要确认框，仿照 `_run_sign` 里 export 的写法。

### 场景 C：接入一个全新的功能模块

优先判断该模块是否已有参数化 CLI：
- 有 → GUI 加页签/区块，用 `_launch_cli(模块目录, 脚本名, args)` 直调；
- 没有（配置写死） → 在 `gui_runner.py` 新增任务类型（见 2.3），注意：
  - 模块顶层有副作用（建目录/跑 main）时，仿照 `_run_init` 的 exec+屏蔽方案；
  - 模块有 `toolkit/` 包时确认与已加载包不冲突（子进程天然隔离，无需处理）。

### 场景 D：修改任务并发模型

当前为单任务锁（`_busy`）。若要并发：`_launch` 的锁检查、`run_buttons` 的禁用粒度、`_poll_queue` 的哨兵分发都需要改造，且注意 Word COM 类任务并发会互相干扰，不建议。

---

## 五、约定与坑

1. **编码**：所有子进程 env 强制 `PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`；GUI 与 runner 顶部都有 `reconfigure`。新增输出通道保持 utf-8。
2. **路径**：界面向子进程传的都是**绝对路径**字符串；JSON 用 `ensure_ascii=False` 打包进 argv（Windows CreateProcess 走 UTF-16，中文安全）。
3. **config 派生属性**：签章页 config 的派生路径是导入时赋值，覆写 root 必须逐项同步（见 2.2），漏一项就会写到旧样本目录。
4. **退出码**：runner 透传命令函数返回值；`SystemExit` 会被捕获换算。GUI 以 `rc == 0` 判定成功，非 0 只影响状态栏与日志，不弹错误框。
5. **原模块零改动原则**：GUI/runner 不得修改各模块源码；需要新配置入口时优先在 runner 侧覆写。若确实要改模块，需同步更新 2.2 的映射表。
6. **冒烟测试**：改动后至少跑一遍界面构建冒烟（实例化 ToolBoxApp → 遍历 FILE_CMDS 切换 → `_save_settings`），涉及 runner 的任务用临时目录端到端验证，**不要对仓库样本目录跑写操作**（format/insert/init 等会原地改文件）。

---

## 六、exe 打包（底稿工具箱.spec）

### 6.1 打包与分发

```powershell
python -m PyInstaller 底稿工具箱.spec --noconfirm
# 产物：dist\底稿工具箱\   ← 整个文件夹一起拷贝分发，双击 底稿工具箱.exe 运行
```

onedir 模式（不压单文件）：启动快、Word COM 稳定。依赖已全部打进包，
目标机器**无需安装 Python**。

### 6.2 冻结模式原理

exe 被派生子进程时有两种内部模式（见 `底稿工具箱GUI.py::main/_run_frozen_dispatch`）：

| 模式 | 调用形式 | 行为 |
|---|---|---|
| `--gui-runner <JSON>` | `_launch_runner` 在 frozen 时改派 exe 自身 | 从 `_MEIPASS/gui_runner.py` 动态加载中转器执行 |
| `--run-script <脚本> [args…]` | `_launch_cli` 在 frozen 时改派 exe 自身 | `runpy.run_path` 进程内执行打包进来的 CLI 脚本（folder_toolbox / file_toolkit） |

路径基准（frozen 下）：

| 常量 | 值 | 用途 |
|---|---|---|
| `BASE_DIR` | **exe 所在目录** | `.zcode/gui_settings.json`、`os.startfile` |
| `RES_DIR`（`sys._MEIPASS`） | `<exe目录>\_internal` | gui_runner.py 及各 CLI 脚本/实现包 |

⚠️ **`_launch_cli` / `launch_cli` 的工作目录必须跟着脚本走**：frozen 下模块目录只存在于
`RES_DIR`，exe 同级没有。若把 cwd 设成 `BASE_DIR\<模块目录>`，Qt 版 QProcess 会以
FailedToStart 结束且**不发 finished 信号**，界面会永久卡在「运行中」、按钮全灰；
Tk 版则是 Popen 直接抛错。现在 cwd 默认取 `RES_DIR\<模块目录>`，缺失时退回 `BASE_DIR`。
Qt 版 `Runner` 另接了 `errorOccurred` 兜底（启动失败即按退出码 1 收尾），双保险。

### 6.3 spec 关键配置（改代码后需同步）

- **datas**：`gui_runner.py`、`初始化底稿文件.py`、`输出文件目录.py`、
  `folder_toolbox.py + 提取非Word文件.py + toolbox/`、`file_toolkit.py + toolkit/`——凡是经
  子进程运行的脚本都必须作为数据文件打进 `_MEIPASS`，否则 frozen 模式找不到；
- **collect_all**：`docx / openpyxl / pypdf / pandas / PIL / win32com`——这些库
  由 CLI 脚本运行时才 import，PyInstaller 静态分析探测不到，必须显式声明；
- 新增功能若引入新第三方库且走子进程通道 → 记得加进 spec 的 collect_all 列表。

### 6.4 日志文件都写在哪

| 场景 | 位置 | 说明 |
|---|---|---|
| **打包运行（exe）** | `exe同级\logs\<模块名>\` | 全部模块集中在这里，如 `logs\比较文件夹内容\非Word_xxx.log` |
| 源码运行 | 各模块目录下的 `logs\` | 如 `比较文件夹内容\logs\`、`签章页工具\logs\` |
| 界面底部「运行日志」 | 不落盘 | 需要留存时点日志区的「保存日志」另存为 `.log` |
| 界面填写的路径等设置 | `BASE_DIR\.zcode\gui_settings.json` | exe 同级；日志内容**不会**写进去 |

常见日志文件名：

| 功能 | 文件名 |
|---|---|
| 提取打印文件 | `extract_{项目}_{时间戳}.log` |
| 提取非Word文件 | `非Word_{项目}_{时间戳}.log` |
| 比较 / 合并 | `compare_…` / `merge_…` |
| 签章页工具各步 | `format_…` / `header_…` / `export_…` / `filter_…` / `insert_…`（`.txt`） |
| 替换底稿内容 | `short_…` / `long_…`（`.txt`） |

界面日志区工具条（右下角）：**清屏**（Ctrl+L）、**运行前自动清屏**（勾选后每次新任务只留本次输出，
该开关会被记住）、**保存日志**、**打开日志目录**（直达上表中的目录）。

### 6.5 已知限制

   冻结入口（`_run_frozen_dispatch`）会先设 `IBDW_LOG_ROOT=<exe目录>\logs`，
   各模块据此把日志写到 **exe 同级 `logs\<模块名>\`**（`比较文件夹内容/toolbox/common.py`、
   `底稿pdf材料/toolkit/logutil.py` 读环境变量；签页/替换由 `gui_runner._apply_log_root` 覆写
   `config.LOG_DIR`）。新增模块请沿用同一约定。
   另：界面日志区的 `LogView` 已在 `widgets.collect_state/apply_state` 中排除，
   **不要把日志内容写进设置 json**，否则下次启动会把历史日志整段恢复回来。
2. 首次启动比源码模式慢约 1-2 秒（解包校验）；每个子任务会再派生一个自身进程。
3. 若杀毒软件拦截 exe 派生自身的进程链，把整个文件夹加入白名单即可。
