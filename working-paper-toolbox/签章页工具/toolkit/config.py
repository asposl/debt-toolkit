# -*- coding: utf-8 -*-
"""公共配置（原 pdf_toolkit.py「公共配置」区）。

换项目时优先改这三处：PROJECT_TAG、PROJECT_ROOT、EXPORT_COMPANY_KEYWORD。
format / header / export / insert 都从 PROJECT_ROOT 派生，整条链不用再改分项路径。

所有路径常量统一通过本模块属性访问（config.X），保证晚绑定；
LOG_DIR / SCRIPT_DIR 锚定到包的上一级目录（即入口脚本所在目录）。
"""

import os

# ==================== 公共配置 ====================
# 日志目录先锚定，PROJECT_ROOT 再相对它解析。
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

PROJECT_TAG = "示例"

# ---- 日志脱敏（默认开启）----
# 开启后日志文件名不带 PROJECT_TAG，正文里的项目根替换为 <ROOT>、本机用户名替换为 <USER>。
LOG_REDACT = True

# ---- 脱敏模式 ----
# IBDW_DEMO_MODE=1（GUI「脱敏模式」勾选时由运行器注入，或命令行 --demo）：
# 产物里的发行人/项目组/落款一律用示例值，主体名不写进文件名。
DEMO_MODE = str(os.environ.get("IBDW_DEMO_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}
# 默认回落到仓库内样本目录（比较文件夹内容/new），换真实项目时再改 PROJECT_ROOT。
# 警告：format / header / export / insert 会原地改 PROJECT_ROOT 下的文件。
# 换项目时改这三处：PROJECT_TAG、PROJECT_ROOT、EXPORT_COMPANY_KEYWORD。
# PROJECT_ROOT = "D:/底稿/<项目名>"
_SAMPLE_PROJECT = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "比较文件夹内容", "new")
)
PROJECT_ROOT = _SAMPLE_PROJECT

# ---- format（docx 格式化，原 宋体Arial.py）----
FORMAT_INPUT_FOLDER = PROJECT_ROOT
FORMAT_UPDATE_DAYS = 100          # 只处理最近 N 天内更新的 docx

# ---- header（页眉检查修复，原 页眉检查.py）----
HEADER_ROOT_DIR = PROJECT_ROOT
HEADER_DRY_RUN = False            # True: 只检查不修改；False: 检查并修改

# ---- export（Word 转 PDF 拆页，原 输出签章页.py）----
EXPORT_ROOT_FOLDER = PROJECT_ROOT
EXPORT_COMPANY_KEYWORD = "示例市示范区城市资产经营有限公司"
EXPORT_MERGED_PDF_NAME = "签章页.pdf"        # 合并后的签章页 PDF 名（输出到根文件夹）

# 切换项目时，把上面的 PROJECT_TAG / PROJECT_ROOT / EXPORT_COMPANY_KEYWORD 改成新项目对应值：
# PROJECT_TAG = "项目A"
# PROJECT_ROOT = "D:/底稿/项目A"
# EXPORT_COMPANY_KEYWORD = "示例市宏信国有资产投资管理有限公司"
#
# format / header / export / insert 的目录均从 PROJECT_ROOT 派生（导入时赋值）。
# 只改 PROJECT_ROOT 后需重新运行脚本；测试覆盖时请同时改 FORMAT_INPUT_FOLDER 等分项。

# 最近生成的 PDF 复用天数（0 或负数关闭复用；docx 更新时仍强制重导出）
EXPORT_RECENT_PDF_MAX_AGE_DAYS = 1
# Windows MAX_PATH=260，超此长度的 docx 将被就地改名缩短
EXPORT_PATH_LENGTH_LIMIT = 250

# ---- filter（过滤索引，原 check_sign.py）----
FILTER_JSON_PATH = "no_company_latest.json"   # export 的固定名副本（相对路径找不到时会尝试 logs/）
FILTER_KEYWORD = "索引"                 # 需要过滤掉的关键字

# ---- insert append（追加签章页，原 插入签章页.py）----
APPEND_JSON_PATH = "has_company_latest.json"   # export 生成的最新清单（logs/ 目录下的固定名副本）
APPEND_SIGNATURE_PDF_PATH = os.path.join(PROJECT_ROOT, EXPORT_MERGED_PDF_NAME)
APPEND_ROOT_DIR = PROJECT_ROOT

# ---- insert replace（替换签字页）----
# 清单条目支持「路径|页码」：filter 默认输出「路径|末页」，
# 签字页不在末页的例外文件由人工把「末页」改成具体页码（如 xxx.pdf|12）
REPLACE_LIST_PATH = "no_company_无索引_latest.log"   # filter 生成的最新清单（固定名副本）
REPLACE_SIGNATURE_PDF_PATH = os.path.join(PROJECT_ROOT, "签字合并.pdf")
REPLACE_ROOT_DIR = PROJECT_ROOT
# ================================================
