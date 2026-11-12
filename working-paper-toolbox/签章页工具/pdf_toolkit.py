# -*- coding: utf-8 -*-
"""
pdf_toolkit.py —— 债承 PDF/docx 处理工具箱（合并版）

合并来源：
  format  <- 宋体Arial.py     批量刷新 docx 格式（黑体标题+宋体正文+Arial西文）
  header  <- 页眉检查.py      检查并修复 docx 页眉编号
  export  <- 输出签章页.py    Word→PDF 导出、拆末页合并签章页、生成清单
  filter  <- check_sign.py    过滤 no_company JSON 中含"索引"的条目
  insert  <- 插入签章页.py + 插入签字页.py
             --mode append   按 has_company JSON 把签章页追加到 PDF 末尾
             --mode replace  按无索引清单把签字页替换为末页或指定页

用法：
  python pdf_toolkit.py format
  python pdf_toolkit.py header
  python pdf_toolkit.py export
  python pdf_toolkit.py filter
  python pdf_toolkit.py insert --mode append
  python pdf_toolkit.py insert --mode replace

所有日志与清单文件统一输出到脚本同级的 logs/ 子文件夹。

模块结构（由原单文件按原始脚本边界拆分，Word/OOXML/COM 逻辑各自整体保留）:
    toolkit/config.py        公共配置（测试经 pt.config.X 覆盖）
    toolkit/logutil.py       日志工具
    toolkit/format_word.py   【原 宋体Arial.py】
    toolkit/header_fix.py    【原 页眉检查.py】OOXML 整块平移
    toolkit/export_sign.py   【原 输出签章页.py】COM 流程整块平移
    toolkit/filter_index.py  【原 check_sign.py】+ 清单读取工具
    toolkit/insert_pages.py  【原 插入签章页.py + 插入签字页.py】
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import argparse

from toolkit import config  # noqa: F401  测试通过 pt.config.X 覆盖沙箱配置
from toolkit.export_sign import cmd_export
from toolkit.filter_index import _load_path_list, cmd_filter  # noqa: F401
from toolkit.format_word import cmd_format
from toolkit.header_fix import cmd_header
from toolkit.insert_pages import cmd_insert
from toolkit.logutil import setup_logger


# ============================================================
# 命令行入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="债承 PDF/docx 处理工具箱（合并版），日志统一输出到 logs/ 子文件夹。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python pdf_toolkit.py format\n"
            "  python pdf_toolkit.py header\n"
            "  python pdf_toolkit.py export\n"
            "  python pdf_toolkit.py filter\n"
            "  python pdf_toolkit.py insert --mode append\n"
            "  python pdf_toolkit.py insert --mode replace\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("format", help="批量刷新 docx 格式（原 宋体Arial.py）")
    subparsers.add_parser("header", help="检查并修复 docx 页眉编号（原 页眉检查.py）")
    subparsers.add_parser(
        "export",
        help="Word→PDF 导出、拆末页合并签章页、生成清单（原 输出签章页.py）",
    )
    subparsers.add_parser(
        "filter", help="过滤 no_company JSON 中含关键字的条目，输出带默认页码的清单（原 check_sign.py）"
    )

    parser_insert = subparsers.add_parser(
        "insert",
        help="插入签章页/替换签字页（原 插入签章页.py + 插入签字页.py）",
    )
    parser_insert.add_argument(
        "--mode",
        choices=["append", "replace"],
        default="append",
        help="append=按 has_company JSON 追加签章页；replace=按无索引清单替换末页或指定页",
    )

    args = parser.parse_args()

    task_logger = setup_logger(args.command)

    if args.command == "format":
        code = cmd_format(task_logger)
    elif args.command == "header":
        code = cmd_header(task_logger)
    elif args.command == "export":
        code = cmd_export(task_logger)
    elif args.command == "filter":
        code = cmd_filter(task_logger)
    elif args.command == "insert":
        code = cmd_insert(task_logger, args.mode)
    else:
        code = 1
    sys.exit(code if isinstance(code, int) else 0)


if __name__ == "__main__":
    main()
