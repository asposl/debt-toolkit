# -*- coding: utf-8 -*-
"""
file_toolkit.py —— 债承文件整理工具箱（统一版，路径全部参数化）

三个来源整合：
  A. 有息负债建档流水线（自 organize_toolkit.py 迁入）
     dedup_folders / convert_images / match_excel / merge_pdfs
  B. 财务底稿整理（自 会计科目底稿整理.py 迁入，保持预览/--apply 安全设计）
     pdf_merge / flat_rename / order_rename
  C. 通用重编号（自有息负债-担保重命名.ipynb 抽象收编）
     renumber_files

所有涉及改名的命令默认均为【预览模式】，只打印计划不做改动；
加 --apply（或对应执行开关）后才真正执行。
所有日志统一输出到脚本同级的 logs/ 子文件夹。

相对原代码的修正：
  1. 铺平编号由普通字典序改为自然排序（修复 "10 xxx" 排在 "2 xxx" 前的问题）
  2. 重编号默认预览、报告被跳过的未匹配文件（原来直接落盘且静默跳过）
  3. 四个编号场景统一走同一编号内核，排序策略可配置且行为一致
  4. 原地重命名统一采用两阶段临时名方案，避免中间状态命名冲突

模块结构（由原单文件按原始脚本边界拆分，函数体逐行保真）:
    toolkit/logutil.py       日志工具
    toolkit/numbering.py     编号内核
    toolkit/imaging.py       图片转 PDF
    toolkit/dedup.py         组A dedup_folders
    toolkit/ledger_match.py  组A match_excel
    toolkit/ledger_merge.py  组A merge_pdfs
    toolkit/working_paper.py 组B【会计科目底稿整理.py 整体】pdf_merge/flat_rename/order_rename
    toolkit/renumber.py      组C renumber_files
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import argparse
from pathlib import Path

from toolkit.dedup import cmd_dedup_folders
from toolkit.imaging import cmd_convert_images
from toolkit.ledger_match import cmd_match_excel
from toolkit.ledger_merge import cmd_merge_pdfs
from toolkit.logutil import setup_logger
from toolkit.renumber import run_renumber
from toolkit.working_paper import (
    cmd_pdf_merge,
    parse_folder_spec,
    run_flat_rename,
    run_order_rename,
)


# =====================================================================
# 命令行入口
# =====================================================================
def main():
    parser = argparse.ArgumentParser(
        description="债承文件整理工具箱（统一版）：路径全部参数化，日志输出到 logs/。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python file_toolkit.py dedup_folders --source E:\\src --output D:\\out\n"
            "  python file_toolkit.py convert_images --target D:\\out\n"
            "  python file_toolkit.py match_excel --excel ht.xlsx --output-dir .\n"
            '  python file_toolkit.py merge_pdfs --excel 匹配结果.xlsx --folders D:\\out --output D:\\合并\n'
            '  python file_toolkit.py pdf_merge --top "D:\\...\\2-3-6-2$xxx" --prefix 2-3-6-2-\n'
            '  python file_toolkit.py flat_rename --parent "D:\\..." --folders "2-3-5-7 固定资产科目核查:flat,2-3-5-8 无形资产科目核查"\n'
            "  python file_toolkit.py order_rename --locations D:\\a\\土地使用权证 D:\\a\\开发成本 --prefix 2-3-5-6-\n"
            "  python file_toolkit.py renumber_files --folder 示例对外担保\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ---- 组A ----
    p_dedup = subparsers.add_parser(
        "dedup_folders", help="按内容指纹对编号子文件夹去重并复制到输出目录")
    p_dedup.add_argument("--source", required=True, help="去重扫描的源目录")
    p_dedup.add_argument("--output", required=True, help="唯一文件夹输出目录")
    p_dedup.add_argument("--layout", choices=["single", "nested"], default="single",
                         help="single=数字文件夹在源目录一层；nested=母/子两层结构")
    p_dedup.add_argument("--no-image-convert", action="store_true",
                         help="复制后不先转图片再比对指纹")

    p_conv = subparsers.add_parser(
        "convert_images", help="递归将 jpg/jpeg/png/jfif 转为 PDF 并删除原图")
    p_conv.add_argument("--target", required=True, help="要处理的目录（递归）")

    p_match = subparsers.add_parser(
        "match_excel", help="台账 Sheet1/Sheet2 字段匹配：给 Sheet1 加 num 列并导出未匹配 CSV")
    p_match.add_argument("--excel", required=True, help="台账 xlsx 路径")
    p_match.add_argument("--sheet1", default="Sheet1")
    p_match.add_argument("--sheet2", default="Sheet2")
    p_match.add_argument("--cols",
                         default=",".join(["贷款机构", "借款单位", "余额", "借款日", "到期日", "利率"]),
                         help="逗号分隔的匹配列，默认 贷款机构/借款单位/余额/借款日/到期日/利率")
    p_match.add_argument("--output-dir", required=True, help="交付物输出目录")

    p_merge = subparsers.add_parser(
        "merge_pdfs", help="按 num 编号定位文件夹并按特征优先级合并 PDF")
    p_merge.add_argument("--excel", required=True, help="匹配结果 xlsx（含 num 列）")
    p_merge.add_argument("--sheet", default="sheet1")
    p_merge.add_argument("--folders", required=True, help="编号文件夹根目录")
    p_merge.add_argument("--output", required=True, help="合并 PDF 输出目录")
    p_merge.add_argument("--features", default=None,
                         help="可选：特征优先级 JSON 数组文件；缺省用内置顺序")

    # ---- 组B ----
    p_pm = subparsers.add_parser(
        "pdf_merge", help="[底稿] 子文件夹合并→铺平→连贯编号（默认预览）")
    p_pm.add_argument("--top", required=True, help="待处理的顶级文件夹")
    p_pm.add_argument("--prefix", required=True, help="编号前缀，如 2-3-6-2-")
    p_pm.add_argument("--merge", action="store_true", help="执行合并阶段")
    p_pm.add_argument("--flatten", action="store_true", help="执行铺平+重命名阶段")
    p_pm.add_argument("--all", action="store_true", help="合并+铺平一步完成")

    p_flat = subparsers.add_parser(
        "flat_rename", help="[底稿] 多个文件夹各自平铺/原地重命名（默认预览）")
    p_flat.add_argument("--parent", required=True, help="各目标文件夹所在的父目录")
    p_flat.add_argument("--folders", required=True,
                        help='逗号分隔，格式 "目录名[:flat]"，如 '
                             '"2-3-5-7 固定资产科目核查:flat,2-3-5-8 无形资产科目核查"；'
                             "编号前缀自动取目录名第一个空格前的部分")
    p_flat.add_argument("--apply", action="store_true", help="实际执行（默认仅预览）")

    p_order = subparsers.add_parser(
        "order_rename", help="[底稿] 多个固定位置的 PDF 按给定顺序全局连贯编号（默认预览）")
    p_order.add_argument("--locations", nargs="+", required=True,
                         help="按编号顺序列出各位置目录")
    p_order.add_argument("--prefix", required=True, help="编号前缀，如 2-3-5-6-")
    p_order.add_argument("--apply", action="store_true", help="实际执行（默认仅预览）")

    # ---- 组C ----
    p_ren = subparsers.add_parser(
        "renumber_files", help='已有"N 名称.pdf"的文件夹按原编号顺序重新连贯编号（默认预览）')
    p_ren.add_argument("--folder", required=True, help="目标文件夹")
    p_ren.add_argument("--pattern",
                       default=r"^(\d+)\s+(.*)$",
                       help=r"匹配模式，需含两个捕获组（旧编号, 其余名称）；默认 ^(\d+)\s+(.*)$")
    p_ren.add_argument("--start", type=int, default=1, help="起始编号（默认 1）")
    p_ren.add_argument("--apply", action="store_true", help="实际执行（默认仅预览）")

    args = parser.parse_args()
    task_logger = setup_logger(args.command)

    dispatch = {
        "dedup_folders": lambda: cmd_dedup_folders(args, task_logger),
        "convert_images": lambda: cmd_convert_images(args, task_logger),
        "match_excel": lambda: cmd_match_excel(args, task_logger),
        "merge_pdfs": lambda: cmd_merge_pdfs(args, task_logger),
        "pdf_merge": lambda: cmd_pdf_merge(args, task_logger),
        "flat_rename": lambda: run_flat_rename(
            Path(args.parent), parse_folder_spec(args.folders), args.apply, task_logger),
        "order_rename": lambda: run_order_rename(
            args.locations, args.prefix, args.apply, task_logger),
        "renumber_files": lambda: run_renumber(
            Path(args.folder), args.pattern, args.start, args.apply, task_logger),
    }
    sys.exit(dispatch[args.command]())


if __name__ == "__main__":
    main()
