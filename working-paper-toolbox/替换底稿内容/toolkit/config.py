# -*- coding: utf-8 -*-
"""公共配置（原 replace_toolkit.py「公共配置」区）。

所有路径常量统一通过本模块属性访问（config.X），保证晚绑定；
LOG_DIR / SCRIPT_DIR 锚定到包的上一级目录（即入口脚本所在目录），
保证日志仍生成在「脚本同级 logs/」。
"""

import os
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

# ---- short（词对/正则替换）----
# 词表外置于规则表工作簿：第 1 列=查找词，第 2 列=替换词。
# 查找词以 "regex:" 开头表示正则表达式；替换词留空表示删除查找词。
SHORT_RULES_XLSX = Path(SCRIPT_DIR).parent / "替换规则表.xlsx"
SHORT_RULES_SHEET = "短替换"          # 规则表中的工作表名

# 包含多层子文件夹的源根目录。
# D: 正式盘当前不存在，默认用仓库样本。short 在 SOURCE==FINAL 时原地替换，
# F5 会改样本 docx；正式项目请改成实际底稿根目录。
_SAMPLE_DOCX_ROOT = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "比较文件夹内容", "new")
)
SOURCE_FOLDER = _SAMPLE_DOCX_ROOT

# 处理后的最终文件输出根目录（与源相同 = 原地替换）
FINAL_FOLDER = _SAMPLE_DOCX_ROOT

# ---- long（规则表区间替换，原 长替换.py）----
# 规则表：第 1 列=起始关键字（前缀），第 2 列=结束关键字（后缀），第 3 列=插入素材 docx 文件名。
RULES_XLSX = Path(SCRIPT_DIR).parent / "替换规则表.xlsx"
LONG_RULES_SHEET = "长替换"        # long 固定读此工作表，不依赖 Excel 当前活动表

# 被替换 docx 所在文件夹。脚本会递归处理子文件夹中的 .docx。
TARGET_DOCX_DIR = Path(_SAMPLE_DOCX_ROOT)

# 需要插入的 docx 素材所在文件夹。规则表第 3 列可写文件名，也可写绝对路径。
INSERT_DOCX_DIR = Path(SCRIPT_DIR) / "素材"

# False：保存到 OUTPUT_DIR，不改原文件；True：直接覆盖原文件。
OVERWRITE_ORIGINAL = True
OUTPUT_DIR = Path(SCRIPT_DIR) / "替换结果"

# True：连同起始、结束特征一起替换；False：保留起止特征，只替换两者之间的内容。
REPLACE_BOUNDARY_TEXT = True
