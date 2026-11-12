# 诚信核查自动化截图 — 项目开发文档

> 面向后续维护者的爬虫程序修改指南。当前版本见 `main.py` 的 `CURRENT_VERSION`。
> 维护者：见 LICENSE ｜ 当前版本：v2.0.1

---

## 1. 项目概述

桌面 GUI 工具，用于批量核查发行人/高管在各类政府及监管网站的诚信记录并**自动截图存档**：

- **诚信核查截图**：输入多个核查对象（名称 + 可选证件号），勾选目标网站后批量访问、交互、截图，按对象分文件夹保存 PNG；支持**失败记录核验与一键补跑**（见 §10）。
- **核查说明生成**：生成 Word 版核查说明文档（`views/word_generator_ui.py`）；支持**编号映射**为 docx 文件名加层级编号前缀（见 §13）。
- **董监高核查**：四站专用方案 + 截图转置整理 + 单一汇总 docx（`views/djg_ui.py`，见 §12）。
- **核查模板**：常用名单的创建/保存/一键载入，每行可携带编号代码（`views/template_ui.py`，见 §11）。

技术栈：Python 3.13 / CustomTkinter（GUI）/ DrissionPage（浏览器控制）/ Playwright（个别独立流程）/ pyautogui（物理屏幕截图）。

运行：`python main.py`（入口），打包版支持 `--verify-bundle` 自检。

---

## 2. 目录结构

```
GUI/
├── main.py                      # 应用入口（五页侧边栏导航、底部状态栏、打包环境自检）
├── custom_sites.json            # 用户自定义网站配置（运行时生成，勿手工删改格式）
├── check_templates.json         # 核查模板存储（运行时生成：名单+可选编号代码）
├── run_state.py                 # ★ 重跑核验与状态持久化（文件级判定、原子写、_ibdw_state.json）
├── templates_store.py           # ★ 模板存储与名单行解析（[编号] 名称 证件号）
├── modules/
│   └── scraper/                 # ===== 爬虫核心包 =====
│       ├── async_screenshot_dp.py   # 兼容门面（re-export，勿在此写新代码）
│       ├── async_func_dp.py         # 兼容门面（re-export，勿在此写新代码）
│       ├── subject_utils.py     # 核查对象解析、安全文件名
│       ├── url_builder.py       # 目标 URL 与交互参数构造
│       ├── capture.py           # 物理屏幕截图（pyautogui）
│       ├── browser.py           # DrissionPage 浏览器生命周期/标签页管理/反检测
│       ├── foreground_runner.py # 前台串行流程（验证码类网站）
│       ├── batch_runner.py      # 批量任务总编排（三阶段并发池）
│       ├── page_helpers.py      # 页内通用小工具
│       ├── gui_confirm.py       # GUI 确认弹窗桥接协议
│       ├── actions_basic.py     # 简单搜索动作（输入+点击）
│       ├── actions_advanced.py  # 多步高级检索动作
│       ├── actions_captcha.py   # OCR/滑块验证码动作
│       ├── workflows.py         # Playwright 独立批量工作流（天眼查/文书网）
│       └── site_configs.py      # ★ 站点配置字典（加新网站主要改这里）
└── views/
    ├── theme.py                 # ★ 设计 Token 与通用组件（卡片/Tooltip/确认弹窗/彩色日志）
    ├── integrity_check_ui.py    # 诚信核查截图界面（线程调度、重跑核验、仅选上次失败、日志队列）
    ├── word_generator_ui.py     # 核查说明生成界面（支持编号映射回填 docx 文件名前缀）
    ├── djg_ui.py                # ★ 董监高核查页（截图转置整理、单一汇总docx：首页空白）
    ├── template_ui.py           # ★ 核查模板页（名单 CRUD、编号代码、一键载入核查页）
    └── help_ui.py               # ★ 使用说明页（分卡片静态指引，修改文案编辑 _SECTIONS）

> **运行时产物**：截图默认输出到 `启动目录/output/`（GUI 内即 `GUI/output/`），
> 目录结构为 `output/run_YYYYmmdd-HHMMSS/subj_001/<站点>.png`：
> **路径里只出现运行时间戳与主体序号，不出现被查询主体名称**（`subj_001` 与主体的
> 对应关系默认不落盘，需要时设 `IBDW_WRITE_MANIFEST=1` 才会写 `run_*/manifest.json`，
> 且该文件含真实名称，按客户机密对待）。
> **该目录已被 `.gitignore` 忽略，不入库**，可随时清空。
```

> **重要**：`async_screenshot_dp.py` 和 `async_func_dp.py` 是历史兼容门面，
> 只做 re-export。新增/修改代码请直接写到对应子模块。

---

## 3. 整体架构与数据流

```
integrity_check_ui.py                    modules/scraper/
┌─────────────────────┐   thread    ┌──────────────────────────┐
│ 输入对象+勾选站点     │ ─────────→ │ batch_runner             │
│ merged_config =     │  log_queue  │   ├─ browser.get_clean_page()
│   active_config     │             │   ├─ 对每个公司:          │
│   + custom_config   │ ←───────── │   │   后台并发池(三阶段)   │
│                     │  ("CONFIRM",│   │   → foreground_runner │
│ listen_to_queue()   │   payload)  │   │   → config["workflow"]│
│ 渲染日志/弹窗        │             │   └─ batch_workflow(整批)  │
└─────────────────────┘             └──────────┬───────────────┘
                                               │ 依赖
                     subject_utils ← url_builder ← foreground/batch
                     capture ← page_helpers
```

- UI 在子线程中调用 `run_batch_screenshot_task(companies, log_queue, base_output, selected_sites, CONFIG, extra_delay, run_dir)`；
- 进度通过 `log_queue`（字符串日志）和 `("CONFIRM", payload)`（弹窗请求）回传主线程渲染。

### 核查对象（subject）

输入框文本由 `subject_utils.normalize_subject()` 解析为：

| 字段 | 含义 |
|---|---|
| `name` | 名称（剔除证件号后的部分） |
| `id_card` | 正则识别出的 15/18 位证件号 |
| `raw` | 原始输入 |
| `display_name` | 日志显示名（仅用于日志，不参与路径） |

每个对象的截图保存到
`<base_output>/run_<时间戳>/subj_<序号>.png` 所在的 `subj_NNN/` 目录下，
文件名取 `save_as`（如 `4、中国执行信息公开网—综合查询.png`）。
序号按名单顺序从 1 开始，写入端与核验端用同一顺序，无需共享状态即可对上。

---

## 4. 四种执行模式（batch_runner）

对每个核查对象，配置字典中的站点按以下优先顺序分派：

| 模式 | 触发字段 | 执行方式 | 典型场景 |
|---|---|---|---|
| **后台并发**（默认） | 无特殊字段 | 多个标签页同时开，三阶段流水线 | 一般政府网站检索 |
| **前台串行** | `'foreground': True` | 单标签页前台逐步执行 | 有验证码/滑块/必须前台渲染 |
| **单对象独立工作流** | `'workflow': 函数` | 每个对象调用一次，签名 `(page, subject, company_folder, save_name, log_queue)` | （预留扩展） |
| **整批工作流** | `'batch_workflow': 函数` | 全部对象只跑一次，签名 `(companies, run_dir, save_name, log_queue)`；先于逐对象循环前执行 | 天眼查/文书网（需人工登录一次） |

### 三阶段后台并发池（batch_runner 核心逻辑）

1. **阶段一（点火）**：为每个后台站点开一个 `about:blank` 标签页，用 JS 延迟跳转到目标 URL —— 所有站点瞬间并发发出请求；
2. **阶段二（交互 + 新窗口追踪）**：轮询各标签页 `document.readyState`；加载完成后执行 `action` 交互；若交互弹出**新标签页**，放入追踪池异步等待（约 2.5 秒超时），不阻塞其他站点；交互失败直接流转到阶段三兜底截图；
3. **阶段三（强制显示 + 截图)**：结果页加载完成后 `Page.bringToFront` 置顶 → 执行 `post_action` → `pyautogui` 截图 → **无论成败关闭标签页**（防残留累积）。

每家公司处理完后兜底清理除主标签页外的所有标签页。

> ⚠️ **截图是物理屏幕截图（pyautogui），执行期间不能最小化浏览器或锁屏**，
> 这是架构级约束，不是 bug。

---

## 5. 站点配置字典详解（site_configs.py）

四个字典；**UI 方案菜单仅暴露两套**：`default_2`（债券模板）与 `default_3`（董监高模板）。
`default` 与 `WEB_CONFIG` 保留为数据源/兼容用途（自定义网站始终合并进当前所选方案）：

| 字典 | 条目数 | 用途 |
|---|---|---|
| `default_2` | 32 | **债券模板（UI 默认）** |
| `default` | 41 | 数据源保留（不再作为菜单项） |
| `WEB_CONFIG` | 12 | 数据源保留（不再作为菜单项） |
| `default_3` | 4 | **董监高模板**（由 default_2 的 3/5/7/33 号站复制重编号，见 §12） |

### 配置项字段一览

```python
'站点名称（同时是 UI 复选框文字）': {
    'url': 'https://.../search?q={company}',  # 必填；支持占位符
    'action': action_xxx,          # 页面交互函数；一步到位填 None
    'action_arg': 'item',          # 可选：传整个 subject 而非关键词字符串
    'post_action': post_xxx,       # 可选：截图前的收尾动作（如回填搜索框）
    'query_mode': 'name',          # 关键词取值模式，见下表
    'save_as': '输出文件名',        # 可选：默认等于站点名称 key
    'foreground': True,            # 前台串行模式
    'require_result_navigation': True,  # 仅前台模式：提交后必须检测到结果页跳转
    'popup_timeout': 15,           # 前台模式：等待新标签页秒数
    'result_timeout': 20,          # 结果页加载超时秒数
    'load_timeout': 30,            # 首次页面加载超时
    'result_selector': 'css:...',  # 前台模式：结果页必须存在的选择器
    'workflow': func,              # 单对象独立工作流
    'batch_workflow': func,        # 整批工作流
}
```

### query_mode 取值（决定搜索关键词）

| 值 | 关键词内容 |
|---|---|
| `'name'`（默认） | 仅名称 |
| `'name_id'` / `'keyword'` | `名称 证件号` |
| `'id'` / `'id_card'` | 仅证件号 |
| `'raw'` | 原始输入原文 |

### URL 占位符规则

- `{company}` `{name}` `{id_card}` `{keyword}` `{raw}` 会被 URL 编码后替换；
- **URL 不含 `{` 且没有 action/post_action 时**：视为纯前缀模式，把关键词直接拼到 URL 末尾（自定义网站走这条路）;
- URL 不含 `{` 但有 action 时：原样打开，靠页面内交互填词；
- 不以 `http(s)://` 开头会自动补 `https://`。

---

## 6. 编写动作函数（actions_*.py）

所有 action 签名统一为 `func(page, arg)`：`page` 为 DrissionPage 标签页对象；
`arg` 默认是按 `query_mode` 取出的关键词字符串，配了 `'action_arg': 'item'` 则是整个 subject 字典。

### 放哪里？

- **actions_basic.py**：一步完成——定位输入框 → 清空 → 输入 → 点查询按钮。
- **actions_advanced.py**：多步——点"高级检索"展开面板、多输入框、等待新标签页等。
- **actions_captcha.py**：验证码动作、ddddocr 普通模型点选识别、cv2 滑块轨迹计算及验证码诊断接口。

### 验证码动作接口

验证码网站必须配置 `'foreground': True`，由 `foreground_runner.run_foreground_site()`
在前台标签页调用动作。当前对外暴露的动作入口为：

| 接口 | 签名 | 用途 | 失败行为 |
|---|---|---|---|
| `action_court_captcha` | `func(page, subject, overall_timeout=180)` | 执行信息公开网天爱点选/滑块验证码 | 最多 5 次查询流程；主动刷新不计次，少批量时可人工兜底 |
| `action_csrc_shixin_slider` | `func(page, subject)` | 证监会滑块验证码 | 最多 5 次自动流程；少批量时可人工兜底 |
| `action_jiangsu_tax` | `func(page, subject)` | 江苏税务验证码 | 验证码 OCR 重试最多 5 次 |

点选验证码的识别契约如下：

- `_get_dddd_ocr()` 使用 `ddddocr.DdddOcr(beta=False, show_ad=False)`；检测器和字符识别器分别实例化。
- 提示图识别出的文字用于确定目标字及顺序；背景字框识别始终使用完整字集。提示字只过滤模型的直接结果，不通过 `set_ranges` 或候选集概率归一化强行猜字。
- 单框原始置信度低于 `DDDD_REJECT_BELOW`，或无法以 `DDDD_ASSIGN_MIN_SCORE` 完成目标字的一对一分配时，本张验证码视为不可靠并刷新，不执行点击。
- `set_captcha_debug_dir(path)` 用于显式指定诊断目录；`suggest_captcha_debug_dir(path)` 仅提供默认建议，不覆盖显式设置；`add_captcha_log_sink(fn)` / `remove_captcha_log_sink(fn)` 用于把识别日志接入 GUI 日志队列。
- 3/4/5/8 号验证码流程的自动尝试上限为 5 次；主动刷新只受整体超时时间约束，不占用尝试次数。
- 选中网站数大于 10 时跳过人工介入；网站数小于等于 10 时，每个主体、每个站点最多人工介入一次，等待 90 秒并每 0.3 秒检查结果。天爱弹窗消失后最多再等待 5 秒确认结果。
- 验证码识别依赖按需导入 `ddddocr`、`opencv-python` 和 `numpy`。修改识别实现后需执行源码编译检查，并在重新打包时重新运行 `--verify-bundle`。

### 常用套路（从现有函数复制改造最快）

```python
# 最简输入+点击 (basic)
def action_xxx(page, company):
    time.sleep(1)
    page.ele('#input_id').input(company, clear=True)
    page.ele('#btn_id').click(by_js=True)

# Vue/Element-UI 输入框需手动触发事件 (advanced, 参考 action_jianzushichang)
search_input.run_js(f'this.value = "{company}";')
search_input.run_js("this.dispatchEvent(new Event('input', { bubbles: true }));")

# 提交后弹新标签页：记录旧 tab 列表轮询差集 (advanced, 参考 action_zhengjianhui_gaoji)
old_tabs = page.browser.tab_ids
...
for _ in range(25):
    diff = [t for t in page.browser.tab_ids if t not in old_tabs]
    if diff:
        new_page = page.browser.get_tab(diff[-1]); break
```

注意事项：

- 输入框点击/输入后建议补 `run_js(f'this.value = "{company}";')` 双保险（很多站框架绑定不认模拟输入）；
- 动作内部失败会被上层捕获并降级为兜底截图（后台模式）或记警告（前台模式），不要在 action 里吞掉关键异常——抛出让日志可见；
- 验证码重试上限一般 5 次，连续失败应 `raise RuntimeError("...连续识别失败")`。

---

## 7. 常见修改任务操作指南

### 任务 A：新增一个"打开链接就能看到结果"的网站

在 `site_configs.py` 对应字典里加一条即可，无需写代码：

```python
'XX、某网站': {'url': 'https://xxx.gov.cn/search?q={company}', 'action': None, 'post_action': None},
```

### 任务 B：新增需要在页面里输入关键词再点搜索的网站

1. 在 `actions_basic.py`（或多步则 `actions_advanced.py`）照现有样式写 `action_xxx(page, company)`；
2. 在 `site_configs.py` 加条目并在文件头部的 import 列表中补上该函数；
3. 若提交后会弹出新窗口且要截新窗口 → 后台并发模式天然支持；若页面有验证码 → 加 `'foreground': True` 并参考任务 C。

### 任务 C：新增验证码网站

1. 在 `actions_captcha.py` 写动作（字符验证码参考 `action_court_captcha` 用 ddddocr；滑块参考 `action_csrc_shixin_slider` 用 cv2 算缺口距离 + `page.actions` 模拟人手拖动）；
2. 配置必须加 `'foreground': True`（验证码必须前台渲染）；
3. 依赖缺失时按惯例抛出带安装提示的 RuntimeError。

### 任务 D：新增需要人工登录的网站（整批模式）

参考 `workflows.py` 的 `batch_workflow_tianyancha` / `batch_workflow_wenshu`：

1. 写 `batch_workflow_xxx(subjects, base_output, filename, log_queue)`，用 Playwright 打浏览器；
2. 登录等待用 `_request_gui_confirm(log_queue, "标题", "提示语")` —— 它会向 UI 发 `("CONFIRM", payload)`，用户在 GUI 上点确定/取消后返回布尔值；
3. 配置条目用 `'batch_workflow': batch_workflow_xxx`，并给 `'save_as'` 和 `'query_mode'`。

### 任务 E：调整某个网站的速度/稳定性

| 症状 | 调整位置 |
|---|---|
| 后台站点结果页没加载完就截图 | `batch_runner.py` 阶段三的超时（`elapsed > 10`）与新窗口追踪超时（`check_count >= 10 or > 2.5 秒`） |
| 前台站点加载慢 | 配置里的 `load_timeout` / `result_timeout` / `popup_timeout` |
| 截图时页面还在动 | 配置无 `screenshot_delay` 字段时看 `foreground_runner.py` 的固定延时；全局额外延迟用 UI 传入的 `extra_delay` |
| 浏览器被反爬识别 | `browser.py get_clean_page()` 的 UA / stealth_js |

### 任务 F：修改对象解析或输出命名

全部在 `subject_utils.py`：证件号正则 `ID_PATTERN`、`normalize_subject`、`safe_path_name`（Windows 非法字符清洗）。注意 UI 侧 `integrity_check_ui.py` 里有一份相同的 `ID_PATTERN` 用于输入预览，两处需同步改。

---

## 8. GUI ↔ 爬虫通信协议

| 消息类型 | 方向 | 说明 |
|---|---|---|
| `"普通字符串"` | 爬虫 → UI | 追加到日志框，末尾带 `\n` |
| `("CONFIRM", {"title", "message", "event", "result"})` | 爬虫 → UI | UI 弹窗，用户选择后设置 `result` 并 `event.set()`；爬虫侧阻塞等待 |
| `"DONE"` | 爬虫 → UI | 任务结束标记（无论成败最后必发） |

新增工作流如需用户确认，一律走 `_request_gui_confirm()`，不要用 tkinter 直接跨线程调 UI。

---

## 9. 自定义网站功能（custom_sites.json）

- UI 上的"➕ 添加自定义"按钮把 `{name, url, query_mode}` 存到 `GUI/custom_sites.json`；
- 加载后自动转为标准配置条目（`action=None`），与所选方案字典 merge 后一起渲染复选框、参与任务；
- 自定义网站 URL 通常不含占位符 → 走"纯前缀拼接关键词"模式；若目标站需要页面内交互填词，请改为内置站点（任务 B）；
- 「🗑 删除选中」仅作用于自定义网站（内置站点不受影响），删除前弹确认框并显示 URL，
  删除日志同时记录 URL 便于恢复；同名覆盖内置站点的自定义项删除后自动恢复原版。

---

## 10. 重跑核验与断点补跑（run_state.py）

> 目标：一轮跑完后知道**哪个公司哪个站没出图**，下次一键只补失败项。
> 不侵入爬虫协议，靠文件系统核验实现。

### 判定规则（`verify_run()`，纯函数）

开跑前快照本轮范围（现存公司 × 勾选站点 + 运行目录 + 起跑时间戳）；收到 `DONE` 后逐对检查
`<run_dir>/subj_NNN/<save_as>.png`：

| 结果 | 条件 |
|---|---|
| `ok` | 文件存在 且 >0 字节 且 mtime ≥ 起跑时间-2s（本轮新生成） |
| `fail` | 其余情况（缺图 / 仍是上轮旧图 / 空文件） |
| `unknown` | 站点配置含 `workflow`/`batch_workflow`（天眼查、文书网等整批模式，产出命名不可预测），不参与自动判定 |

### 状态持久化

写入 `<base_output>/_ibdw_state.json`（临时文件 + `os.replace` 原子写；损坏静默降级为空状态）。
键是主体的 **SHA1 摘要**（`subject_utils.anonymize_key`，16 位），**状态文件里不含任何真实名称**：

```json
{
  "version": 2,
  "last_run": {"finished_at": "...", "total_pairs": 96, "ok": 88, "fail": 6, "unknown": 2},
  "results": {"公司名|证件号": {"1、信用中国": "ok", "7、法律文书网": "unknown"}}
}
```

合并语义：本轮结果覆盖同键，未涉及的历史条目保留 → 状态随项目目录跨重启累积。

### UI 入口

- 对象行徽章：`✅n · ❌k · ❔u`（悬停列出失败站点明细）；
- 【⚠ 仅选上次失败】：取**当前名单内**各公司 fail 站点并集勾选、其余取消——直接再点开始即全名单补跑；
- 【清除记录】：删除状态文件。

> ⚠️ 已知局限：动作失败但兜底截图成功会被判 ok（架构决定：阶段三兜底必出图），
> 需人工复核图片内容；这是设计取舍而非 bug。

---

## 11. 核查模板（templates_store.py + check_templates.json）

常用名单的持久化。每行格式：

```
[编号]<空白分隔>名称 [证件号]
1-3-1-3-1   XX子公司（张三） 91320000MA1K35678X
李四 110101199001011234
```

- 编号仅当行首 token 匹配 `^\d+(-\d+)+$` 时识别并剥离（普通数字开头的人名不受影响）；
- 名称解析复用 `subject_utils`：全角括号备注保留在名称中，18 位统一社会信用代码 /
  15 位工商注册号 / 身份证均能正确提取；TAB 分隔支持 Excel 直接粘贴；
- 存储：`GUI/check_templates.json`，条目 `{name, updated_at, companies:[{raw,name,id_card,code}]}`，
  原子写、损坏静默降级；
- 「载入到核查页」构造的 subject 与手动输入完全同构（含去重键 `name|id_card`），
  `code` 字段随行携带供 §13 使用；
- 除在本页 CRUD 外，核查页「待核查对象」卡片右上角的 **【💾 存为模板】** 可把当前
  名单直接保存（弹窗命名，Enter 确定 / Esc 取消；重名自动追加序号）。

---

## 12. 董监高核查工作流（views/djg_ui.py + default_3）

面向《项目组关于董监高人员诚信信息的核查说明》的三步专用流程：

### ① 截图

预设 `default_3` 由债券模板复制重编号而来（对象为自然人，百度站 `query_mode='name_id'`）：

| 新 key（=save_as=附件序号） | 来源 | 模式 |
|---|---|---|
| 1、中国证监会证券期货市场失信记录查询平台 | 原 3、 | 前台滑块验证码 |
| 2、全国法院失信被执行人名单信息公布与查询 | 原 5、 | 前台验证码 |
| 3、法律文书网 | 原 7、 | 整批工作流（人工登录） |
| 4、其他网站和媒体报道 | 原 33、 | 百度新闻，关键词=姓名+证件号 |

### ② 截图整理（转置，移植自 高管查询结果整理.ipynb）

`reorganize_screenshots(source, output, move=False)`：

- 一级图片：`王五/3、法律文书网.png` → `<输出>/3、法律文书网/王五.png`
- 二级文件夹：`张三/7、法律文书网/*.png` → `<输出>/…/原文件名`（自带时间戳不冲突）
- 默认 **copy 不动源文件**；同名冲突跳过并计数警告。

### ③ 汇总文档（build_summary_docx）

生成**单一** docx：《项目组关于董监高人员诚信信息的核查说明》——

- **首页完全空白**（仅一个空段落 + 分页符），说明文字由使用者手工添加；
- 之后按站点夹名称自然排序分组插图（组内按人名自然排序，居中宽 5.5 英寸）；
- 「插入站点标题行」开关默认开启（组前插入站点夹名文本段），关闭则为纯图片流；
- 空站点夹记入日志警告，不中断。

---

## 13. 编号映射回填 docx 文件名（word_generator_ui.py）

「核查说明生成」页的可选功能，用于把生成的文档挂到申报材料目录树：

- 「编号映射」框每行 `[编号] 公司名 [证件号]`，可手填或点【从模板导入】自动预填
  （匹配规则：模板公司与输入目录子文件夹命中数最多的模板）；
- 批处理时以 `safe_path_name(公司名) == 子文件夹名` 匹配：
  - 命中 → 输出文件名 `{编号} 项目组关于发行人子公司（{folder}）诚信信息的核查说明.docx`
  - 未命中 / 未填映射 → 完全旧行为原名生成（字节级兼容）；
- **所有输出一律写入统一输出目录**，绝不写入任何公司自己的文件夹；
- `generate_word_document()` 内部逻辑未改动，编号只作用于批处理的命名层。

---

## 14. 打包与依赖注意

- **打包配置**：仓库根目录 `诚信核查自动化截图.spec`（onedir），执行
  `pyinstaller 诚信核查自动化截图.spec --noconfirm`，产物在 `dist\诚信核查自动化截图\`。
  旧 `输出.spec` 属于历史独立脚本，与 GUI 无关；
- **spec 关键点**（换机器打包前必读）：
  - `collect_all` 整包收集 playwright（node 驱动）/ DrissionPage（配置）/ ddddocr（onnx 模型）；
  - 打包本机 `%LOCALAPPDATA%\ms-playwright` 的 `chromium-1223`（DrissionPage 与
    playwright 有头工作流共用，构建号须与 `browser.py` 兜底路径一致）与
    `chromium_headless_shell-1223`（无头自检用）；
  - **conda 环境必须手工收集 `Library\bin` 的 12 个 DLL**（ffi×3 / tcl86t / tk86t /
    zlib / charset / iconv / libxml2 / libxslt / libexslt / liblzma），缺失症状分别为
    `import ctypes` 失败、GUI 无法启动、lxml（DrissionPage）导入失败；
  - `excludes` 排除 torch/matplotlib/scipy/dask/IPython/sphinx/PyQt5/PySide6/pytest 等
    ——ddddocr→onnxruntime 的分析链会误拖入这些（实测运行时均不加载），
    且 PyQt5+PySide6 同时存在会直接中止构建；
- **DPI Awareness 勿删**：`main.py` 顶部通过 `SetProcessDpiAwareness` 声明（含 Win7 兜底）。
  删掉后高分屏缩放环境下窗口会退化为位图拉伸：文字模糊、边缘拖拽热区失效（窗口不可拉伸）、
  页面内容可能被裁切；
- **崩溃排查**：windowed 模式看不到 traceback，GUI 启动异常会写入 exe 同目录
  `gui_crash.log`；打包自检用 `--verify-bundle`（覆盖 cv2/numpy/playwright 无头拉起）；
- **可选依赖按需导入**：`ddddocr`（OCR 验证码）、`cv2/numpy`（滑块）、`playwright`（天眼查/文书网）。缺哪个会在触发对应站点时报错，打包时都要收进去；
- `modules/scraper/__init__.py` 必须保留（保证 PyInstaller 把拆分后的子模块当常规包分析）；
- 打包后务必跑 `--verify-bundle` 自检 + 选 1 个后台型 + 1 个验证码型网站冒烟。

---

## 15. 修改后验证清单

- [ ] `python -m compileall modules views main.py run_state.py templates_store.py` 编译通过
- [ ] `python -c "import sys; sys.path.insert(0,'.'); from modules.scraper.async_func_dp import WEB_CONFIG, default, default_2, default_3"` 导入无误
- [ ] 新站点在三种对象形态下试跑：仅名称 / 名称+身份证 / 纯数字名
- [ ] 后台模式站点：确认结果页完整后再截图（图片肉眼可读）
- [ ] 验证码站点：连续失败路径是否给出明确日志
- [ ] 异常中断（手动关浏览器）后重跑，无残留标签页累积
- [ ] 重跑闭环：跑一轮 → 手动删 1 张图 → 【仅选上次失败】→ 补跑后状态翻绿且其余站未被访问
- [ ] 模板：保存/复制/删除/载入全链路；带编号行往返解析无损；损坏 JSON 容错
- [ ] 董监高端到端：预设 4 站截图 → 转置整理 → 汇总 docx（首页空白、标题行开关生效）
- [ ] Word 混合批次：有码加前缀 / 无码原名 / 映射为空与旧行为完全一致
- [ ] git 提交，commit message 说明改动动机；**不要**提交 `output/`、运行时 JSON（`custom_sites.json` 等）与 `.workbuddy*/`（这些已在 `.gitignore` 忽略）；如在 `GUI/` 下新增源码目录，记得补 `!` 放行规则

## 16. 已知约束（勿踩坑）

1. 截图依赖物理屏幕 → 执行中不能最小化窗口/锁屏/远程断开；
2. 同一时刻只能跑一个批任务（共享一个浏览器实例与 log_queue）；
3. 站点 key 即输出文件名与 UI 文案，改名会导致输出目录名变化；default_3 是复制重编号的新条目，勿改 default_2 既有 key；
4. 门面文件（两个 `async_*_dp.py`）只许 re-export，避免再次膨胀成巨型文件；
5. `page_helpers._screenshot` 与主流程 `capture.screenshot_pyautogui` 已统一实现，不要再另写截图函数；
6. 重跑核验依赖「文件名 = save_as + .png、文件夹 = safe_path_name(名称)」这一约定，改动命名链路须同步 `run_state.expected_png_path()`；
7. 汇总 docx 首页必须保持空白（使用者手工撰写说明），不要往第一页自动加内容。

---

## 17. Git 与忽略约定（提交卫生）

提交前务必核对 `.gitignore`，确保下列内容**不入库**：

- `output/`（截图产出，按主体分目录，含个人信息）；
- `GUI/*/` 下所有运行时目录（旧的 `GUI/张三/`、`GUI/xx/` 等），源码目录已用
  `!GUI/modules/`、`!GUI/views/`、`!GUI/.vscode/` 显式放行；
- `GUI/custom_sites.json`、`GUI/check_templates.json`、`GUI/_ibdw_state.json`（运行时用户数据）；
- `.workbuddy/`、`.workbuddy-ai/`、`.zcode/`（Agent / 编辑器工作目录）；
- `验证码/test_output/`（诊断/测试落盘，体积大且可再生）；
- `build/`、`dist/`、`__pycache__/`、`*.pyc`（打包与缓存产物）。

**新增源码目录时**：若在 `GUI/` 下新增子目录（如 `GUI/新模块/`），必须在 `.gitignore` 补一条
`!GUI/新模块/` 放行规则，否则会被 `GUI/*/` 通配忽略而漏提交。

**提交规范**：

- 每笔提交 message 说明「为什么改」（动机），而非只写「改了什么」；
- 功能改动与文档改动尽量拆分提交，便于回滚；
- 切勿 `git add -A` 把 `output/`、PII 或个人状态文件带进仓库。
