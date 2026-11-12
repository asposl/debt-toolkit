# debt-toolkit

处理债承工作的一些杂活。

两个独立的桌面小工具，都是 Python + GUI，面向债券承做过程中重复、机械的文件处理环节：

| 目录 | 工具 | 形态 | 主要用途 |
|---|---|---|---|
| [`working-paper-toolbox/`](working-paper-toolbox/) | **债承底稿处理工具箱** | PySide6（另含一版 Tk 旧界面） | 签章页拆分/追加/替换、底稿目录生成、Word 版式刷齐、批量替换、PDF 合并去重与编号 |
| [`integrity-check-screenshot/`](integrity-check-screenshot/) | **诚信核查自动化截图** | CustomTkinter | 按主体名批量化执行信披/司法/税务等站点查询并截图归档，支持验证码站点 |

> ⚠️ **先读 [`DISCLAIMER.md`](DISCLAIMER.md)。** 本仓库是**脱敏后的演示版本**，源码中的
> 主体名称、证件号、统一社会信用代码、项目代号与本机路径已替换为示例值，
> **直接运行会出现查不到结果、路径不存在、匹配失败等情况 —— 这是脱敏的预期后果，不是 bug。**

## 一、这个仓库是什么

- 面向**学习与流程参考**的开源版本：工具的分层、命令编排、GUI 与子进程协作方式都可以直接读。
- 不面向开箱即用：要真正跑起来，需要自己补齐主体名单、项目路径与模板文件（见下文「脱敏提示」）。
- 不包含任何真实的客户资料、底稿、印章件、征信截图或内部制度文件。

## 二、目录结构

```
debt-toolkit/
├── DISCLAIMER.md                      # 免责声明与脱敏说明（必读）
├── working-paper-toolbox/             # 底稿处理工具箱
│   ├── 底稿工具箱Qt.py                 # 主入口（PySide6，推荐）
│   ├── 底稿工具箱GUI.py                # 旧入口（Tk）
│   ├── qtui/                          # Qt 界面（设置/页面/控件/子进程运行器）
│   ├── 签章页工具/                     # 拆签字页、追加/替换签章页、页眉与格式修复
│   ├── 比较文件夹内容/                 # 目录比对合并、非 Word 文件提取
│   ├── 替换底稿内容/                   # 短替换（词对/正则）与长替换（Word COM）
│   ├── 底稿pdf材料/                    # PDF 合并/去重/编号/影像转换
│   ├── 多级文件夹生成目录/              # 目录树 → Excel → Word 目录
│   └── Qt工具箱使用手册.md
└── integrity-check-screenshot/        # 诚信核查自动化截图
    ├── GUI/                           # 主程序（main.py 入口）
    │   ├── modules/scraper/           # 站点配置、动作、截图、批量编排、输出布局
    │   └── views/                     # 界面（核查页/模板页/董监高/说明生成）
    ├── 验证码/                        # 点选/滑块验证码识别实验与基准
    ├── 独立网站截图/                   # 各站点独立脚本（天眼查/文书网/百度/统计信息网）
    ├── 税务局/                        # 江苏/贵州税务局独立脚本
    ├── 政府网站/                       # 早期独立版本（含 chromedriver）
    └── GUI/README.md                  # 详细设计说明
```

## 三、怎么跑

**环境**：Windows + Python 3.10 及以上（部分功能依赖 Windows：Word COM、物理屏幕截图）。

```bash
# 底稿处理工具箱（PySide6）
pip install PySide6 pandas pypdf python-docx openpyxl pypdfium2 pillow pywin32
python working-paper-toolbox/底稿工具箱Qt.py

# 诚信核查截图
pip install customtkinter DrissionPage ddddocr onnxruntime opencv-python playwright pyautogui python-docx
python -m playwright install chromium
python integrity-check-screenshot/GUI/main.py
```

没有 `requirements.txt`：两个工具的依赖清单与打包命令在各子目录 README 与
`.spec` 文件里，按需安装即可。

## 四、脱敏提示（重要）

为了让仓库可以公开，做了以下替换，**它们会直接影响功能**：

| 被替换的内容 | 替换为 | 副作用 |
|---|---|---|
| 真实发行人/子公司名称 | `示例市…有限公司`、`示例主体001` | 到任何网站都查不到结果，截图流程会「成功但内容为空」 |
| 18 位证件号 / 统一社会信用代码 | `110101199001011234`、`91320800MA0000001X` | 校验位不成立，提交会报错或被拒 |
| 项目代号（如 `26某某02`）、阶段名 | `示例项目` / `示例底稿目录` | 路径不存在，需自行改成自己的目录 |
| 本机绝对路径（含用户名） | 相对路径或系统临时目录 | 首次运行需重新指定路径 |
| 真实底稿 docx/pdf 样本 | 合成的最小 docx/pdf | 页眉、编号、公司关键字匹配等逻辑拿不到真实结构，需自备样本 |
| 替换规则表 `替换规则表.xlsx` | 未提供（可生成空白模板） | 替换功能需先用 `替换底稿内容/make_rules_template.py` 生成模板 |

另外：

- **日志默认脱敏**：日志文件名只有 `功能_时间戳`，正文里的项目根显示为 `<ROOT>`、用户目录显示为 `<USER>`。
- **GUI 有「脱敏模式」开关**（底稿工具箱状态栏）：勾选后子进程以 `IBDW_DEMO_MODE=1` 运行，
  发行人/项目组/落款用示例值，产物名剥掉项目标识。
- **截图输出目录为 `output/run_<时间戳>/subj_001/`**，路径里不含被查询主体名称；
  序号与主体的映射默认不落盘，需要时设 `IBDW_WRITE_MANIFEST=1`（该文件含真实名称，按机密对待）。
- 若要让工具按真实数据工作，请**在你自己的私有环境里**改回真实名单与路径，不要把真实数据提交回本仓库。

## 五、合规提醒

这些工具会访问征信、司法、税务、工商等公开网站的查询页面，部分站点带验证码。
使用前请确认：**遵守目标网站的服务条款与 robots 规则、遵守《个人信息保护法》《数据安全法》
及所在机构的内部规定**，仅在有权查询的范围内使用，不要用于批量采集他人信息。
详见 [`DISCLAIMER.md`](DISCLAIMER.md)。

## 六、许可证

[Apache License 2.0](LICENSE)。
