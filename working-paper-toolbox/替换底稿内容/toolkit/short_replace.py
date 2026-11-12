# -*- coding: utf-8 -*-
"""【原 短替换.py】short —— 词表外置的词对/正则替换（python-docx 引擎，快）。

引擎说明：python-docx 纯 Python 解析，速度快，但会把整段文本写进第一个 run
（跨 run 的格式细节不保留）。需要完整保格式的场景请用 long。
"""

import os
import re

from docx import Document
from openpyxl import load_workbook

from . import config
from .common import normalize_cell


def load_short_rules(excel_path, sheet_name: str, logger=None) -> dict[str, str]:
    """
    从规则表工作簿的指定工作表读取词对，返回 {查找词: 替换词}（保持行序）。
    查找词以 "regex:" 开头表示正则；替换词留空表示删除。
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"未找到规则表：{excel_path}")

    workbook = load_workbook(excel_path, data_only=True, read_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(
                f"规则表中不存在工作表「{sheet_name}」，"
                f"现有工作表：{', '.join(workbook.sheetnames)}。"
                f"请在该工作簿中新建此工作表（第 1 列=查找词，第 2 列=替换词）。"
            )
        worksheet = workbook[sheet_name]

        rules: dict[str, str] = {}
        for row_no, row in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
            old_text = normalize_cell(row[0] if len(row) > 0 else None)
            new_text = normalize_cell(row[1] if len(row) > 1 else None)

            if not old_text:
                continue  # 整行为空

            if old_text.lower() == "regex:":
                message = f"[规则跳过] 第 {row_no} 行查找词为空的正则前缀。"
                if logger is not None:
                    logger.warning(message)
                else:
                    print(message)
                continue

            rules[old_text] = new_text  # 替换词留空 = 删除查找词
        return rules
    finally:
        workbook.close()


def replace_text_robust(paragraph, replacements):
    """
    支持跨 run 的安全替换，同时支持多词匹配，并尽量保留格式
    """
    full_text = "".join(run.text for run in paragraph.runs)
    is_modified = False

    for old, new in replacements.items():
        if old.startswith("regex:"):
            pattern = old.removeprefix("regex:")
            new_text, count = re.subn(pattern, lambda m: new, full_text)
            if count:
                full_text = new_text
                is_modified = True
        elif old in full_text:
            full_text = full_text.replace(old, new)
            is_modified = True

    if is_modified:
        if paragraph.runs:
            paragraph.runs[0].text = full_text
            for run in paragraph.runs[1:]:
                run.text = ""

    return is_modified


def process_single_docx(file_path, save_path, replacements):
    """处理单个Word文档，全方位替换正文、表格、页眉页脚"""
    doc = Document(file_path)
    is_modified = False

    # 1. 替换正文段落
    for p in doc.paragraphs:
        if replace_text_robust(p, replacements):
            is_modified = True

    # 2. 替换表格中的文字
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    if replace_text_robust(p, replacements):
                        is_modified = True

    # 3. 替换页眉和页脚中的文字
    for section in doc.sections:
        if section.header:
            for p in section.header.paragraphs:
                if replace_text_robust(p, replacements):
                    is_modified = True
        if section.footer:
            for p in section.footer.paragraphs:
                if replace_text_robust(p, replacements):
                    is_modified = True

    # 只有真正发生修改时，才写入磁盘，否则放过它
    if is_modified:
        doc.save(save_path)

    return is_modified


def cmd_short(logger):
    if not os.path.exists(config.SOURCE_FOLDER):
        logger.error(f"找不到源文件夹：{config.SOURCE_FOLDER}")
        return 1

    try:
        replacements = load_short_rules(
            config.SHORT_RULES_XLSX, config.SHORT_RULES_SHEET, logger=logger
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        return 1

    if not replacements:
        logger.error(
            f"工作表「{config.SHORT_RULES_SHEET}」中没有有效规则"
            f"（第 1 列=查找词，第 2 列=替换词，从第 2 行开始填写）。"
        )
        return 1

    logger.info("启动通用文本批量替换（仅保存修改文件）...")
    logger.info(f"词表：{config.SHORT_RULES_XLSX} [工作表: {config.SHORT_RULES_SHEET}]")
    logger.info(f"有效替换规则：{len(replacements)} 条")
    for old, new in replacements.items():
        logger.info(f"  【{old}】 ---> 【{new if new else '（删除）'}】")
    logger.info("-" * 50)

    total_files = 0
    modified_files = 0
    error_files = 0

    for root, dirs, files in os.walk(config.SOURCE_FOLDER):
        for filename in files:
            if filename.lower().endswith(".docx") and not filename.startswith("~$"):
                total_files += 1

                current_file_path = os.path.join(root, filename)
                relative_path = os.path.relpath(root, config.SOURCE_FOLDER)
                target_sub_dir = os.path.join(config.FINAL_FOLDER, relative_path)

                # 创建对应的多级子文件夹
                os.makedirs(target_sub_dir, exist_ok=True)
                final_save_path = os.path.join(target_sub_dir, filename)

                try:
                    changed = process_single_docx(
                        current_file_path, final_save_path, replacements
                    )
                    display_name = os.path.join(relative_path, filename)
                    if changed:
                        logger.info(f"[已修改并保存] -> {display_name}")
                        modified_files += 1
                    else:
                        logger.info(f"[跳过(未匹配)] -> {display_name}")
                except Exception as e:
                    logger.error(f"无法处理文件 {filename}, 错误: {e}")
                    error_files += 1

    logger.info("任务全部完成！")
    logger.info(f"扫描文件总数: {total_files} 个")
    logger.info(f"实际修改并写入的文件数: {modified_files} 个")
    logger.info(f"保持原样跳过的文件数: {total_files - modified_files - error_files} 个")
    if error_files:
        logger.error(f"处理失败的文件数: {error_files} 个")
        return 1
    return 0
