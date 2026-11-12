# -*- coding: utf-8 -*-
"""
收集签字页.py —— insert --mode replace（原 插入签字页.py）的逆向操作。

正向（toolkit/insert_pages.py replace 模式）：按 no_company_无索引 清单，
用 签字合并.pdf 第 i 页替换第 i 个文件的末页。

本脚本逆向收拢：读同一份清单，按清单顺序逐个打开对应 PDF——
  · 若该 PDF 为奇数（2n+1）页，只抽取最后 1 页；
  · 否则（偶数页）抽取最后 2 页；
再把抽出的页按**原始文件名**逐个单独输出为新的 PDF，统一放进输出文件夹
（缺省为 项目根目录\收集签字页\）。不同子文件夹出现同名文件时，
后写入的自动加 "_2"、"_3" 后缀并在日志中告警。
全程只读源文件，不改动任何原 PDF。

用法：
  python 收集签字页.py                              # 全部走默认配置
  python 收集签字页.py --root "D:\\某项目根目录"      # 指定项目根目录
  python 收集签字页.py --output-dir "D:\\收集结果"    # 指定输出文件夹
  python 收集签字页.py --list 自定义清单.log          # 缺省 no_company_无索引_latest.log

清单兼容 .json 与逐行一条的 .txt/.log（自动跳过旧版文件末尾的统计信息块），
与 insert --mode replace 使用完全相同的清单读取逻辑。
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import argparse

from pypdf import PdfReader, PdfWriter

from toolkit import config
from toolkit.filter_index import _load_path_list
from toolkit.insert_pages import normalize_relative_path
from toolkit.logutil import _resolve_input, setup_logger


DEFAULT_OUTPUT_DIR_NAME = "收集签字页"


def _pages_to_take(page_count):
    """奇数页取末 1 页，偶数页取末 2 页（0 页由调用方先行排除）。"""
    return 1 if page_count % 2 == 1 else 2


def _unique_output_name(base_name, used_names):
    """输出文件名保持原始文件名；本轮已用过（不同子文件夹同名）则加 _2/_3 后缀。"""
    if base_name not in used_names:
        return base_name
    stem, ext = os.path.splitext(base_name)
    k = 2
    while f"{stem}_{k}{ext}" in used_names:
        k += 1
    return f"{stem}_{k}{ext}"


def collect_signature_pages(logger, root_dir, list_path, output_dir):
    """按清单顺序把每个 PDF 的末尾页以原始文件名单独输出。返回退出码。"""
    logger.info("开始执行签字页收集任务（insert --mode replace 的逆向操作）...")

    # ---- 配置校验 ----
    if not root_dir or not str(root_dir).strip():
        logger.error("ROOT_DIR 未填写，已退出。请用 --root 或在配置区填入顶层文件夹路径。")
        return 1
    if not os.path.isdir(root_dir):
        logger.error(f"ROOT_DIR 不存在或不是文件夹: {root_dir}")
        return 1

    resolved_list = _resolve_input(list_path)
    if not os.path.isfile(resolved_list):
        logger.error(f"路径清单不存在: {list_path}")
        return 1

    # ---- 读清单（与 insert --mode replace 完全同源）----
    try:
        target_paths = _load_path_list(resolved_list)
    except Exception as e:
        logger.error(f"读取路径清单失败: {e}")
        return 1
    if not target_paths:
        logger.error("清单为空，没有可收集的文件。")
        return 1
    logger.info(f"成功读取路径清单，共 {len(target_paths)} 条有效路径。")
    logger.info(f"设定的基础根目录为: {os.path.abspath(root_dir)}")

    # ---- 输出文件夹（缺省自动创建）----
    out_dir_abs = os.path.abspath(output_dir)
    try:
        os.makedirs(out_dir_abs, exist_ok=True)
    except Exception as e:
        logger.error(f"输出文件夹无法创建: {out_dir_abs} ({e})")
        return 1
    logger.info(f"输出文件夹: {out_dir_abs}")

    # ---- 逐条抽取末尾页并单独落盘（只读源文件）----
    used_names = set()
    success_count = 0
    failed_items = []  # (序号, 相对路径, 原因)

    for i, relative_path in enumerate(target_paths):
        target_full_path = os.path.normpath(
            os.path.join(root_dir, normalize_relative_path(relative_path))
        )
        logger.info(f"正在处理第 {i + 1}/{len(target_paths)} 条:")
        logger.info(f"  完整目标路径: {target_full_path}")

        if not os.path.isfile(target_full_path):
            logger.error("  [失败] 目标文件不存在，已跳过。")
            failed_items.append((i + 1, relative_path, "文件不存在"))
            continue

        temp_path = None
        try:
            reader = PdfReader(target_full_path)
            page_count = len(reader.pages)
            if page_count == 0:
                raise ValueError("PDF 页数为 0，无可抽取内容")

            take = _pages_to_take(page_count)
            writer = PdfWriter()
            for page in reader.pages[-take:]:
                writer.add_page(page)

            base_name = os.path.basename(target_full_path)
            out_name = _unique_output_name(base_name, used_names)
            used_names.add(out_name)
            out_path = os.path.join(out_dir_abs, out_name)

            # 临时文件原子写，中断不会留下半截输出
            temp_path = out_path + ".tmp"
            with open(temp_path, "wb") as temp_file:
                writer.write(temp_file)
            os.replace(temp_path, out_path)

            parity = "奇数" if take == 1 else "偶数"
            note = "" if out_name == base_name else "（与此前条目重名，自动改名）"
            logger.info(
                f"  [成功] 该文件共 {page_count} 页（{parity}），"
                f"已抽取末 {take} 页 -> {out_name}{note}"
            )
            if out_name != base_name:
                logger.warning(f"  [告警] 清单第 {i + 1} 条的文件名与之前条目重复：{base_name}")
            success_count += 1
        except Exception as e:
            logger.error(f"  [失败] 处理该文件时发生错误: {e}")
            failed_items.append((i + 1, relative_path, str(e)))
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    if success_count == 0:
        logger.error("没有任何一个文件收集成功，未产出任何结果。")
        self_report_failed(logger, failed_items)
        return 1

    logger.info("所有处理已完成。")
    logger.info(
        f"汇总：清单 {len(target_paths)} 条 | 成功 {success_count} 个文件 | "
        f"失败 {len(failed_items)} 条 | 输出文件夹 {out_dir_abs}"
    )
    if failed_items:
        self_report_failed(logger, failed_items)
        return 1
    return 0


def self_report_failed(logger, failed_items):
    """把跳过明细写进日志，方便对照“清单第几条”回查。"""
    for idx, rel, reason in failed_items:
        logger.warning(f"  失败明细 - 清单第 {idx} 条: {rel} ({reason})")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "收集签字页：insert --mode replace 的逆向操作。"
            "按无索引清单把各 PDF 的末尾页（奇数页取末1页/偶数页取末2页）"
            "按原始文件名逐个单独输出。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python 收集签字页.py\n"
            '  python 收集签字页.py --root "示例项目根目录"\n'
            '  python 收集签字页.py --root D:\\proj --output-dir D:\\proj\\收集结果\n'
            "  python 收集签字页.py --list no_company_无索引_latest.log\n"
        ),
    )
    parser.add_argument(
        "--root",
        default=config.REPLACE_ROOT_DIR,
        help="项目根目录（清单内是相对路径）；缺省用配置区 REPLACE_ROOT_DIR",
    )
    parser.add_argument(
        "--list",
        dest="list_path",
        default=config.REPLACE_LIST_PATH,
        help="路径清单文件；缺省 no_company_无索引_latest.log（相对路径找不到时自动尝试 logs/ 目录）",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default=None,
        help=f"输出文件夹；缺省 项目根目录\\{DEFAULT_OUTPUT_DIR_NAME}（不存在会自动创建）",
    )

    args = parser.parse_args()
    logger = setup_logger("collect")
    output_dir = args.output_dir or os.path.join(args.root, DEFAULT_OUTPUT_DIR_NAME)
    return collect_signature_pages(logger, args.root, args.list_path, output_dir)


if __name__ == "__main__":
    sys.exit(main())
