# -*- coding: utf-8 -*-
"""【原 宋体Arial.py】format —— 批量刷新 docx 格式（黑体标题+宋体正文+Arial西文）。

本文件为原始脚本的整块平移：python-docx 格式化规则（9 类段落 + 页眉页脚 + 表格）
保持完整，不做内部拆分。python-docx 仅在本模块导入。
"""

import os
import re
import time

from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from . import config

SECTION_TITLE_PATTERN = re.compile(r"^第(?:[零〇一二两三四五六七八九十百千万]+|\d+)节")
UNIT_LINE_PATTERN = re.compile(r"^[（(]?\s*单位\s*[：:]")


def get_effective_alignment(p):
    """获取段落自身或样式继承的对齐方式。"""
    if p.alignment is not None:
        return p.alignment
    try:
        return p.style.paragraph_format.alignment
    except AttributeError:
        return None


def find_caption_title_paragraphs(paragraphs, lookahead=2):
    """
    识别表格/图片标题：标题通常居中，后面 1-2 个非空段落内有右对齐的“单位：...”。
    “单位”上一行可能是两端对齐正文，因此不能直接把单位行的上一段当标题。
    """
    non_empty = [(idx, p) for idx, p in enumerate(paragraphs) if p.text.strip()]
    caption_title_indexes = set()

    for pos, (idx, p) in enumerate(non_empty):
        if get_effective_alignment(p) != WD_ALIGN_PARAGRAPH.CENTER:
            continue

        for _, next_p in non_empty[pos + 1 : pos + 1 + lookahead]:
            next_text = next_p.text.strip()
            if (
                UNIT_LINE_PATTERN.match(next_text)
                and get_effective_alignment(next_p) == WD_ALIGN_PARAGRAPH.RIGHT
            ):
                caption_title_indexes.add(idx)
                break

    return caption_title_indexes


def set_paragraph_format(
    p,
    font_name="宋体",
    font_size=None,
    bold=False,
    alignment=None,
    space_before=None,
    space_after=None,
    line_spacing=None,
    first_line_indent=None,
    clear_tabs=True,
):
    """通用段落与字体格式设置函数（完美支持中西文双字体）。"""
    if alignment is not None:
        p.alignment = alignment

    if space_before is not None:
        p.paragraph_format.space_before = Pt(space_before)
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    if line_spacing is not None:
        p.paragraph_format.line_spacing = line_spacing
    if first_line_indent is not None:
        p.paragraph_format.first_line_indent = Pt(first_line_indent)

    if clear_tabs:
        while len(p.paragraph_format.tab_stops) > 0:
            del p.paragraph_format.tab_stops[0]

    if not p.runs:
        p.add_run()

    for run in p.runs:
        run.font.name = font_name

        if font_size is not None:
            run.font.size = Pt(font_size)

        # bold=None 时保留原有加粗状态，表格内容需要使用此模式。
        if bold is not None:
            run.bold = bold

        # 中文及中文标点使用 EastAsia 字体，英文和数字使用 Arial。
        rPr = run._r.get_or_add_rPr()
        rFonts = rPr.get_or_add_rFonts()
        rFonts.set(qn("w:ascii"), "Arial")
        rFonts.set(qn("w:hAnsi"), "Arial")
        rFonts.set(qn("w:eastAsia"), font_name)
        rFonts.set(qn("w:hint"), "eastAsia")


def format_word_document(file_path):
    """智能识别段落类型，并根据规则应用对应的格式。"""
    doc = Document(file_path)

    size_map = {
        "小二": 18,
        "三号": 16,
        "小四": 12,
        "五号": 10.5,
        "小五": 9,
    }

    is_first_text = True
    caption_title_indexes = find_caption_title_paragraphs(doc.paragraphs)

    # 正文段落处理
    for paragraph_index, p in enumerate(doc.paragraphs):
        text = p.text.strip()
        if not text:
            continue

        # 1. 章节标题
        if (
            is_first_text
            or p.style.name.startswith(("Heading 1", "标题 1"))
            or SECTION_TITLE_PATTERN.match(text)
        ):
            set_paragraph_format(
                p,
                font_name="黑体",
                font_size=size_map["小二"],
                bold=False,
                alignment=None,
                line_spacing=1.5,
                space_before=0,
                space_after=0,
                first_line_indent=0,
            )
            is_first_text = False
            continue

        is_first_text = False

        # 2. “一、” 标题
        if p.style.name.startswith(("Heading 2", "标题 2")) or text.startswith(
            ("一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、")
        ):
            set_paragraph_format(
                p,
                font_name="黑体",
                font_size=size_map["三号"],
                bold=False,
                alignment=None,
                line_spacing=1.5,
                first_line_indent=24,
                space_before=0,
                space_after=0,
            )
            continue

        # 3. “（一）” 标题
        if p.style.name.startswith(("Heading 3", "标题 3")) or text.startswith(
            ("（一）", "（二）", "（三）", "（四）", "（五）", "（六）", "（七）", "（八）", "（九）", "（十）")
        ):
            set_paragraph_format(
                p,
                font_name="宋体",
                font_size=size_map["小四"],
                bold=True,
                alignment=None,
                line_spacing=1.5,
                first_line_indent=24,
                space_before=0,
                space_after=0,
            )
            continue

        # 4. “1、” 标题
        if p.style.name.startswith(("Heading 4", "标题 4")) or (
            text and text.split("、")[0].isdigit()
        ):
            set_paragraph_format(
                p,
                font_name="宋体",
                font_size=size_map["小四"],
                bold=True,
                alignment=None,
                line_spacing=1.5,
                first_line_indent=24,
                space_before=0,
                space_after=0,
            )
            continue

        # 5. “（1）” 标题
        if text.startswith(
            ("（1）", "（2）", "（3）", "（4）", "（5）", "（6）", "（7）", "（8）", "（9）", "（10）")
        ):
            set_paragraph_format(
                p,
                font_name="宋体",
                font_size=size_map["小四"],
                bold=False,
                alignment=None,
                line_spacing=1.5,
                first_line_indent=24,
                space_before=0,
                space_after=0,
            )
            continue

        # 6. “1)” 标题
        if text.split(")")[0].isdigit() or text.split("）")[0].isdigit():
            set_paragraph_format(
                p,
                font_name="宋体",
                font_size=size_map["小四"],
                bold=False,
                alignment=None,
                line_spacing=1.5,
                first_line_indent=24,
                space_before=0,
                space_after=0,
            )
            continue

        # 7. “①” 标题
        if text.startswith(("①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩")):
            set_paragraph_format(
                p,
                font_name="宋体",
                font_size=size_map["小四"],
                bold=False,
                alignment=None,
                line_spacing=1.5,
                first_line_indent=24,
                space_before=0,
                space_after=0,
            )
            continue

        # 8. 表格/图片标题：保留与正文区分用的加粗
        if paragraph_index in caption_title_indexes:
            set_paragraph_format(
                p,
                font_name="宋体",
                font_size=size_map["小四"],
                bold=True,
                alignment=None,
                line_spacing=1.5,
                first_line_indent=0,
                space_before=0,
                space_after=0,
            )
            continue

        # 9. 默认正文
        indent_val = 24
        if get_effective_alignment(p) in (
            WD_ALIGN_PARAGRAPH.CENTER,
            WD_ALIGN_PARAGRAPH.RIGHT,
        ):
            indent_val = 0

        set_paragraph_format(
            p,
            font_name="宋体",
            font_size=size_map["小四"],
            bold=False,
            alignment=None,
            line_spacing=1.5,
            first_line_indent=indent_val,
            space_before=0,
            space_after=0,
        )

    # 页眉页脚处理
    for section in doc.sections:
        for hp in section.header.paragraphs:
            set_paragraph_format(
                hp,
                font_name="宋体",
                font_size=size_map["五号"],
                bold=False,
                alignment=WD_ALIGN_PARAGRAPH.RIGHT,
                line_spacing=1.5,
                space_before=0,
                space_after=0,
            )
        for fp in section.footer.paragraphs:
            set_paragraph_format(
                fp,
                font_name="宋体",
                font_size=size_map["小四"],
                bold=False,
                alignment=None,
                line_spacing=1.5,
                space_before=0,
                space_after=0,
            )

    # 表格文字处理（不改字号与加粗，只刷字体）
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for tp in cell.paragraphs:
                    set_paragraph_format(
                        tp,
                        font_name="宋体",
                        font_size=None,
                        bold=None,
                        alignment=None,
                        space_before=None,
                        space_after=None,
                        line_spacing=None,
                        first_line_indent=None,
                        clear_tabs=False,
                    )

    doc.save(file_path)


def cmd_format(logger):
    input_folder = config.FORMAT_INPUT_FOLDER
    update_days = config.FORMAT_UPDATE_DAYS

    if not os.path.exists(input_folder):
        logger.error(f"文件夹 {input_folder} 不存在！")
        return 1

    current_time = time.time()
    time_threshold = update_days * 24 * 60 * 60

    processed_count = 0
    error_count = 0
    for folder_path, _, file_names in os.walk(input_folder):
        for file_name in file_names:
            if not file_name.lower().endswith(".docx") or file_name.startswith("~$"):
                continue

            file_path = os.path.join(folder_path, file_name)
            file_mtime = os.path.getmtime(file_path)

            if (current_time - file_mtime) <= time_threshold:
                try:
                    format_word_document(file_path)
                    relative_path = os.path.relpath(file_path, input_folder)
                    logger.info(f"成功格式化 [本地覆盖]: {relative_path}")
                    processed_count += 1
                except Exception as e:
                    relative_path = os.path.relpath(file_path, input_folder)
                    logger.error(f"文件 {relative_path} 格式化失败: {e}")
                    error_count += 1

    logger.info(f"处理完毕！共原地修改了 {processed_count} 个最近 {update_days} 天内更新的文件。")
    return 1 if error_count else 0
