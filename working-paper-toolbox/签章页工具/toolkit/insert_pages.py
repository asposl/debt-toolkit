# -*- coding: utf-8 -*-
"""【原 插入签章页.py + 插入签字页.py】insert —— append 追加签章页 / replace 替换签字页。

统一骨架：读清单 -> 读签章/签字 PDF -> 校验 -> 逐个临时文件安全写回。
清单读取工具（_load_path_list）来自 filter_index 模块；pypdf 仅在本模块导入。

replace 清单条目支持「路径|页码」格式（见 filter_index.parse_page_entry）：
无页码或「末页」替换末页；数字替换第 N 页（1 起算，用于签字页后有附件、
签字页不在末页的文件）。
"""

import os

from pypdf import PdfReader, PdfWriter

from . import config
from .filter_index import _load_path_list, parse_page_entry
from .logutil import _resolve_input


def normalize_relative_path(relative_path):
    """把日志里混用的 / 与 \\ 统一为 os.sep。"""
    return relative_path.replace("/", os.sep).replace("\\", os.sep)


def insert_signature_pages(logger, mode):
    """
    统一骨架：读清单 -> 读签章/签字 PDF -> 校验 -> 逐个临时文件安全写回。
    append：在目标 PDF 末尾追加对应签章页；
    replace：用签字页替换目标 PDF 的末页或清单指定页。
    """
    if mode == "append":
        list_path = config.APPEND_JSON_PATH
        signature_pdf_path = config.APPEND_SIGNATURE_PDF_PATH
        root_dir = config.APPEND_ROOT_DIR
        action = "签章页追加"
    else:
        list_path = config.REPLACE_LIST_PATH
        signature_pdf_path = config.REPLACE_SIGNATURE_PDF_PATH
        root_dir = config.REPLACE_ROOT_DIR
        action = "签字页替换"

    logger.info(f"开始执行 PDF {action}任务（mode={mode}）...")

    # 配置校验
    if not root_dir or not root_dir.strip():
        logger.error("ROOT_DIR 未填写，已退出。请在配置区填入顶层文件夹路径。")
        return 1
    if not signature_pdf_path or not signature_pdf_path.strip():
        logger.error("签章/签字 PDF 路径未填写，已退出。")
        return 1
    if not os.path.isdir(root_dir):
        logger.error(f"ROOT_DIR 不存在或不是文件夹: {root_dir}")
        return 1
    if not os.path.isfile(signature_pdf_path):
        logger.error(f"签章/签字 PDF 不存在: {signature_pdf_path}")
        return 1

    resolved_list = _resolve_input(list_path)
    if not os.path.isfile(resolved_list):
        logger.error(f"路径清单不存在: {list_path}")
        return 1

    logger.info(f"设定的基础根目录为: {os.path.abspath(root_dir)}")

    try:
        target_paths = _load_path_list(resolved_list)
        logger.info(f"成功读取路径清单，共 {len(target_paths)} 条有效路径。")
    except Exception as e:
        logger.error(f"读取路径清单失败: {e}")
        return 1

    # replace 模式解析「路径|页码」条目；任何格式错误都在动手前整体拒绝执行
    if mode == "replace":
        parsed_targets = []
        format_errors = []
        for entry in target_paths:
            try:
                parsed_targets.append(parse_page_entry(entry))
            except ValueError as e:
                format_errors.append(f"  - {entry}（{e}）")
        if format_errors:
            logger.error("清单中存在非法条目，已拒绝执行（未改动任何文件）：")
            for msg in format_errors:
                logger.error(msg)
            return 1
    else:
        parsed_targets = [(path, None) for path in target_paths]

    try:
        sig_reader = PdfReader(signature_pdf_path)
        sig_pages_count = len(sig_reader.pages)
        logger.info(f"成功读取签章/签字 PDF，共 {sig_pages_count} 页。")
    except Exception as e:
        logger.error(f"读取签章/签字 PDF 失败: {e}")
        return 1

    # 数量校验：replace 模式要求严格一一对应；append 模式按较小值匹配并告警
    if mode == "replace":
        if len(target_paths) != sig_pages_count:
            logger.error(
                f"数量不匹配，已拒绝执行：清单 {len(target_paths)} 条，"
                f"签字 PDF {sig_pages_count} 页。"
            )
            return 1
        match_count = len(target_paths)
    else:
        if len(target_paths) != sig_pages_count:
            logger.warning(
                f"数量不匹配！JSON 中的目标文件有 {len(target_paths)} 个，"
                f"但签章页 PDF 只有 {sig_pages_count} 页。将按较小的值进行匹配。"
            )
        match_count = min(len(target_paths), sig_pages_count)

    failed_count = 0
    for i in range(match_count):
        relative_path, page_override = parsed_targets[i]
        if mode == "append":
            target_full_path = os.path.abspath(os.path.join(root_dir, relative_path))
        else:
            relative_path = normalize_relative_path(relative_path)
            target_full_path = os.path.normpath(os.path.join(root_dir, relative_path))

        logger.info(f"正在处理第 {i + 1}/{match_count} 组:")
        logger.info(f"  完整目标路径: {target_full_path}")

        if not os.path.exists(target_full_path):
            logger.error("  [失败] 目标文件不存在，请检查根目录或清单路径是否正确。跳过此操作。")
            failed_count += 1
            continue

        temp_path = target_full_path + ".tmp"
        try:
            target_reader = PdfReader(target_full_path)
            n = len(target_reader.pages)
            writer = PdfWriter()

            if mode == "append":
                for page in target_reader.pages:
                    writer.add_page(page)
                writer.add_page(sig_reader.pages[i])
                success_msg = f"  [成功] 签章页第 {i + 1} 页已成功插入至该文件末尾（共 {n + 1} 页）。"
            else:
                # 确定被替换页：无页码 -> 末页；数字 -> 第 N 页（1 起算）
                if page_override is None:
                    drop_index = n - 1
                    pos_desc = f"末页（第 {n} 页）"
                else:
                    if page_override > n:
                        logger.error(
                            f"  [失败] 指定页码 {page_override} 超出该文件总页数 {n}。"
                            "跳过此操作，未改动文件。"
                        )
                        failed_count += 1
                        continue
                    drop_index = page_override - 1
                    pos_desc = f"第 {page_override} 页"

                # 留痕：记录被替换页的首行文本，便于事后核对没删错页
                replaced_text = (target_reader.pages[drop_index].extract_text() or "").strip()
                first_line = replaced_text.splitlines()[0] if replaced_text else "（空白页或无文本）"
                logger.info(f"  将替换{pos_desc}，该页首行文本：{first_line[:40]}")

                # 用签字页原位替换目标页，保持页序不变
                pages = list(target_reader.pages)
                pages[drop_index] = sig_reader.pages[i]
                for page in pages:
                    writer.add_page(page)
                success_msg = f"  [成功] 已用签字第 {i + 1} 页替换{pos_desc}（共 {n} 页）。"

            # 临时文件替换法，防止写入中断损坏原文件
            with open(temp_path, "wb") as temp_file:
                writer.write(temp_file)

            os.replace(temp_path, target_full_path)
            logger.info(success_msg)

        except Exception as e:
            logger.error(f"  [失败] 处理该文件时发生错误: {e}")
            failed_count += 1
            if os.path.exists(temp_path):
                os.remove(temp_path)

    logger.info("所有处理已完成。请查看日志文件了解详情。")
    return 1 if failed_count else 0


def cmd_insert(logger, mode):
    return insert_signature_pages(logger, mode)
