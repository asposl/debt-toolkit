# -*- coding: utf-8 -*-
"""
replace_toolkit.py —— docx 批量内容替换工具箱（合并版）

合并来源：
  short <- 短替换.py   词对/正则批量替换（python-docx 引擎，快）
  long  <- 长替换.py   Excel 规则表区间替换并插入素材 docx（Word COM 引擎，保格式）

用法：
  python replace_toolkit.py short    # 按「短替换」工作表词对/正则做替换
  python replace_toolkit.py long     # 按替换规则表.xlsx 做区间替换+插入素材

所有日志统一输出到脚本同级的 logs/ 子文件夹。

模块结构（由原单文件按原始脚本边界拆分，long 为整块平移）:
    toolkit/config.py         公共配置（测试经 rt.config.X 覆盖）
    toolkit/common.py         日志工具 + normalize_cell
    toolkit/short_replace.py  【原 短替换.py】
    toolkit/long_replace.py   【原 长替换.py】Word COM 引擎整体保留
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import argparse

from toolkit import config  # noqa: F401  测试通过 rt.config.X 覆盖沙箱配置
from toolkit.common import normalize_cell, setup_logger  # noqa: F401
from toolkit.long_replace import cmd_long
from toolkit.short_replace import cmd_short


def main():
    parser = argparse.ArgumentParser(
        description="docx 批量内容替换工具箱（合并版），日志统一输出到 logs/ 子文件夹。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python replace_toolkit.py short   # 词对/正则替换（python-docx）\n"
            "  python replace_toolkit.py long    # 规则表区间替换+插入素材（Word COM）\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "short", help="词对/正则批量替换正文、表格、页眉页脚（原 短替换.py）"
    )
    subparsers.add_parser(
        "long",
        help="按替换规则表定位起止关键字并插入素材 docx（原 长替换.py）",
    )

    args = parser.parse_args()
    task_logger = setup_logger(args.command)

    if args.command == "short":
        code = cmd_short(task_logger)
    elif args.command == "long":
        code = cmd_long(task_logger)
    else:
        code = 1
    sys.exit(code if isinstance(code, int) else 0)


if __name__ == "__main__":
    main()
