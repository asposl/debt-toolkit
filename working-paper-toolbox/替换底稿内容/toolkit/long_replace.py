# -*- coding: utf-8 -*-
"""【原 长替换.py】long —— Excel 规则表区间替换并插入素材 docx（Word COM 引擎，保格式）。

引擎说明：Word COM 慢但完整保留格式；素材插入带页面设置隔离与分节合并。
注意：本文件为原始脚本的整块平移——Word COM 引擎逻辑（Range 定位、PageSetup
快照、节隔离与合并、Copy-Paste 插入）保持完整，不做内部拆分。
pywin32 仅在本模块导入，short 链路不依赖它。

配置读取约定：一律 config.X 属性访问（晚绑定），测试可通过补丁覆盖沙箱路径。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pythoncom
from openpyxl import load_workbook
from win32com.client import DispatchEx

from . import config
from .common import normalize_cell

# Word COM 常量
WD_ALERTS_NONE = 0
WD_DO_NOT_SAVE_CHANGES = 0
WD_FIND_STOP = 0
WD_FORMAT_ORIGINAL_FORMATTING = 16
WD_FORMAT_XML_DOCUMENT = 12
WD_SECTION_NEW_PAGE = 2
WD_SECTION_CONTINUOUS = 3
WD_WITHIN_TABLE = 12

# Word Find 的 Text 长度通常不能超过 255。长关键字会走连续分段定位。
MAX_WORD_FIND_TEXT_LENGTH = 240


@dataclass(frozen=True)
class ReplaceRule:
    row_no: int
    start_text: str
    end_text: str
    insert_path: Path

    @property
    def label(self) -> str:
        return f"第 {self.row_no} 行：{self.start_text} -> {self.end_text}"


def resolve_insert_path(raw_path: str) -> Path:
    path = Path(raw_path.strip().strip('"').strip("'"))
    if not path.is_absolute():
        path = config.INSERT_DOCX_DIR / path

    if path.suffix:
        return path

    docx_path = path.with_suffix(".docx")
    return docx_path if docx_path.exists() else path


def load_rules(excel_path: Path, sheet_name: str | None = None, logger=None) -> list[ReplaceRule]:
    if not excel_path.exists():
        raise FileNotFoundError(f"未找到规则表：{excel_path}")

    sheet_name = sheet_name or config.LONG_RULES_SHEET
    workbook = load_workbook(excel_path, data_only=True, read_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(
                f"规则表中不存在工作表「{sheet_name}」，"
                f"现有工作表：{', '.join(workbook.sheetnames)}。"
                "请使用名为 长替换 的工作表（第 1 列=起始关键字，"
                "第 2 列=结束关键字，第 3 列=素材文件名）。"
            )
        worksheet = workbook[sheet_name]
        rules: list[ReplaceRule] = []

        for row_no, row in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
            start_text = normalize_cell(row[0] if len(row) > 0 else None)
            end_text = normalize_cell(row[1] if len(row) > 1 else None)
            insert_file = normalize_cell(row[2] if len(row) > 2 else None)

            if not start_text and not end_text and not insert_file:
                continue
            if not start_text or not end_text or not insert_file:
                message = f"[规则跳过] 第 {row_no} 行缺少起始关键字、结束关键字或素材文件名。"
                if logger is not None:
                    logger.warning(message)
                else:
                    print(message)
                continue

            rules.append(
                ReplaceRule(
                    row_no=row_no,
                    start_text=start_text,
                    end_text=end_text,
                    insert_path=resolve_insert_path(insert_file),
                )
            )
    finally:
        workbook.close()

    return rules


def iter_docx_files(root_dir: Path) -> Iterable[Path]:
    for path in sorted(root_dir.rglob("*.docx")):
        if path.name.startswith("~$"):
            continue
        yield path


def get_output_path(target_path: Path) -> Path:
    if config.OVERWRITE_ORIGINAL:
        return target_path

    relative_path = target_path.relative_to(config.TARGET_DOCX_DIR)
    return config.OUTPUT_DIR / relative_path


def compact_text(text: str) -> str:
    return text.replace("\r", "\n").strip()


def range_is_whole_paragraph(text_range) -> bool:
    """判断命中内容是否独占完整段落，表格单元格内不扩展范围。"""
    if text_range.Paragraphs.Count != 1 or text_range.Information(WD_WITHIN_TABLE):
        return False

    paragraph_range = text_range.Paragraphs(1).Range
    paragraph_text = paragraph_range.Text.rstrip("\r\x07")
    return compact_text(paragraph_text) == compact_text(text_range.Text)


def build_replace_range(
    doc,
    start_range,
    end_range,
    replace_boundary_text: bool = True,
):
    """根据配置构造替换范围，并妥善处理独占段落的特征文本。"""
    if not replace_boundary_text:
        if start_range.Start == end_range.Start and start_range.End == end_range.End:
            insertion_position = start_range.End
            if range_is_whole_paragraph(start_range):
                insertion_position = start_range.Paragraphs(1).Range.End
            return doc.Range(Start=insertion_position, End=insertion_position)

        start_position = start_range.End
        end_position = end_range.Start
        if range_is_whole_paragraph(start_range):
            start_position = start_range.Paragraphs(1).Range.End
        if range_is_whole_paragraph(end_range):
            end_position = end_range.Paragraphs(1).Range.Start

        if start_position > end_position:
            start_position = end_position
        return doc.Range(Start=start_position, End=end_position)

    start_position = start_range.Start
    end_position = end_range.End

    if range_is_whole_paragraph(start_range):
        start_position = start_range.Paragraphs(1).Range.Start
    if range_is_whole_paragraph(end_range):
        end_position = end_range.Paragraphs(1).Range.End

    return doc.Range(Start=start_position, End=end_position)


PAGE_SETUP_PROPERTIES = (
    "Orientation",
    "PageWidth",
    "PageHeight",
    "TopMargin",
    "BottomMargin",
    "LeftMargin",
    "RightMargin",
    "Gutter",
    "HeaderDistance",
    "FooterDistance",
    "DifferentFirstPageHeaderFooter",
    "OddAndEvenPagesHeaderFooter",
    "MirrorMargins",
    "GutterPos",
    "VerticalAlignment",
    "SuppressEndnotes",
    "TwoPagesOnOne",
    "BookFoldPrinting",
    "BookFoldRevPrinting",
    "BookFoldPrintingSheets",
)


def snapshot_page_setup(section) -> dict[str, object]:
    """保存目标节设置，供素材前置边界使用。"""
    page_setup = section.PageSetup
    snapshot: dict[str, object] = {}

    for property_name in PAGE_SETUP_PROPERTIES:
        try:
            snapshot[property_name] = getattr(page_setup, property_name)
        except Exception:
            continue

    try:
        text_columns = page_setup.TextColumns
        snapshot["TextColumns"] = {
            "Count": text_columns.Count,
            "EvenlySpaced": text_columns.EvenlySpaced,
            "LineBetween": text_columns.LineBetween,
            "Spacing": text_columns.Spacing,
            "Widths": [
                (text_columns(index).Width, text_columns(index).SpaceAfter)
                for index in range(1, text_columns.Count + 1)
            ],
        }
    except Exception:
        pass

    return snapshot


def apply_page_setup_snapshot(page_setup, snapshot: dict[str, object]) -> None:
    """把页面尺寸、方向、页边距和分栏复制到一个临时边界节。"""
    for property_name in PAGE_SETUP_PROPERTIES:
        if property_name not in snapshot:
            continue
        try:
            setattr(page_setup, property_name, snapshot[property_name])
        except Exception:
            continue

    columns_snapshot = snapshot.get("TextColumns")
    if not isinstance(columns_snapshot, dict):
        return

    try:
        text_columns = page_setup.TextColumns
        text_columns.SetCount(columns_snapshot["Count"])
        text_columns.EvenlySpaced = columns_snapshot["EvenlySpaced"]
        text_columns.LineBetween = columns_snapshot["LineBetween"]
        text_columns.Spacing = columns_snapshot["Spacing"]

        if not columns_snapshot["EvenlySpaced"]:
            for index, (width, space_after) in enumerate(columns_snapshot["Widths"], start=1):
                text_columns(index).Width = width
                text_columns(index).SpaceAfter = space_after
    except Exception:
        pass


def section_at_insertion_start(target_range):
    doc = target_range.Document
    if target_range.Start > doc.Content.Start:
        probe = doc.Range(Start=target_range.Start - 1, End=target_range.Start)
    else:
        probe_end = min(doc.Content.End, target_range.Start + 1)
        probe = doc.Range(Start=target_range.Start, End=probe_end)
    return probe.Sections(1)


def make_isolated_source_range(source_doc, target_page_setup: dict[str, object]):
    """给素材首尾加边界节，避免素材的节属性污染目标前后内容。"""
    source_start = source_doc.Range(
        Start=source_doc.Content.Start,
        End=source_doc.Content.Start,
    )
    source_doc.Sections.Add(Range=source_start, Start=WD_SECTION_CONTINUOUS)
    apply_page_setup_snapshot(source_doc.Sections(1).PageSetup, target_page_setup)

    source_end = source_doc.Range(
        Start=source_doc.Content.End - 1,
        End=source_doc.Content.End - 1,
    )
    source_doc.Sections.Add(Range=source_end, Start=WD_SECTION_CONTINUOUS)

    first_boundary = source_doc.Sections(1).Range
    last_source_section = source_doc.Sections(source_doc.Sections.Count - 1).Range
    return source_doc.Range(
        Start=first_boundary.End - 1,
        End=last_source_section.End,
    )


def make_source_range(source_doc, target_page_setup: dict[str, object]):
    if source_doc.Sections.Count > 1:
        return make_isolated_source_range(source_doc, target_page_setup)

    source_range = source_doc.Content.Duplicate
    last_paragraph = source_doc.Paragraphs.Last.Range
    has_empty_trailing_paragraph = (
        last_paragraph.Start == source_doc.Content.End - 1
        and last_paragraph.Text == "\r"
    )
    if has_empty_trailing_paragraph:
        source_range.End -= 1
    return source_range


def split_word_find_text(text: str) -> list[str]:
    """切分并转义 Word Find 文本，确保每段都低于 Find 长度限制。"""
    normalized_text = text.replace("\r\n", "\r").replace("\n", "\r")
    chunks: list[str] = []
    current_tokens: list[str] = []
    current_length = 0

    for character in normalized_text:
        if character == "\r":
            token = "^p"
        elif character == "\v":
            token = "^l"
        elif character == "^":
            token = "^^"
        else:
            token = character

        if current_tokens and current_length + len(token) > MAX_WORD_FIND_TEXT_LENGTH:
            chunks.append("".join(current_tokens))
            current_tokens = []
            current_length = 0

        current_tokens.append(token)
        current_length += len(token)

    if current_tokens:
        chunks.append("".join(current_tokens))

    return chunks


def execute_word_find(doc, find_text: str, start_position: int):
    content_end = doc.Content.End
    if start_position >= content_end:
        return None

    search_range = doc.Range(Start=start_position, End=content_end)
    finder = search_range.Find
    finder.ClearFormatting()
    finder.Replacement.ClearFormatting()
    finder.Text = find_text
    finder.Forward = True
    finder.Wrap = WD_FIND_STOP
    finder.Format = False
    finder.MatchCase = False
    finder.MatchWholeWord = False
    finder.MatchWildcards = False
    finder.MatchSoundsLike = False
    finder.MatchAllWordForms = False

    if not finder.Execute():
        return None
    return search_range.Duplicate


def find_text_range(doc, text: str, start_position: int):
    """用 Word 原生坐标分段定位文本，避免 Python 字符下标导致 Range 越界。"""
    content_end = doc.Content.End
    if start_position >= content_end:
        return None

    chunks = split_word_find_text(text)
    if not chunks:
        return None

    candidate_from = start_position
    while candidate_from < content_end:
        first_range = execute_word_find(doc, chunks[0], candidate_from)
        if first_range is None:
            return None

        matched_end = first_range.End
        all_chunks_are_adjacent = True
        for chunk in chunks[1:]:
            next_range = execute_word_find(doc, chunk, matched_end)
            if next_range is None or next_range.Start != matched_end:
                all_chunks_are_adjacent = False
                break
            matched_end = next_range.End

        if all_chunks_are_adjacent:
            return doc.Range(Start=first_range.Start, End=matched_end)

        candidate_from = min(content_end, first_range.Start + 1)

    return None


def normalize_inserted_section_breaks(doc, inserted_start: int, inserted_end: int) -> int:
    """合并同方向节，仅保留横纵方向切换所必需的分页节。"""
    deleted_breaks = 0
    for index in range(doc.Sections.Count, 1, -1):
        previous_section = doc.Sections(index - 1)
        current_section = doc.Sections(index)
        boundary_position = current_section.Range.Start
        if boundary_position <= inserted_start or boundary_position > inserted_end:
            continue

        orientation_changed = (
            previous_section.PageSetup.Orientation
            != current_section.PageSetup.Orientation
        )
        if orientation_changed:
            current_section.PageSetup.SectionStart = WD_SECTION_NEW_PAGE
            continue

        break_range = doc.Range(
            Start=max(doc.Content.Start, boundary_position - 1),
            End=boundary_position,
        )
        if break_range.Text == "\x0c":
            break_range.Delete()
            deleted_breaks += 1
        else:
            current_section.PageSetup.SectionStart = WD_SECTION_CONTINUOUS

    return deleted_breaks


def insert_docx_keep_source_format(word, target_range, insert_path: Path) -> int:
    """保留素材格式，隔离页面设置，并合并不必要的同方向分页。"""
    target_page_setup = snapshot_page_setup(section_at_insertion_start(target_range))
    target_doc = target_range.Document
    inserted_start = target_range.Start
    replaced_length = target_range.End - target_range.Start
    content_end_before = target_doc.Content.End
    source_doc = word.Documents.Open(
        str(insert_path),
        ConfirmConversions=False,
        ReadOnly=True,
        AddToRecentFiles=False,
        Visible=False,
        OpenAndRepair=False,
        NoEncodingDialog=True,
    )

    try:
        source_range = make_source_range(source_doc, target_page_setup)
        paste_range = target_range.Duplicate
        try:
            source_range.Copy()
            paste_range.PasteAndFormat(WD_FORMAT_ORIGINAL_FORMATTING)
            inserted_length = target_doc.Content.End - content_end_before + replaced_length
            inserted_end = min(
                target_doc.Content.End,
                max(inserted_start, inserted_start + inserted_length),
            )
            deleted_breaks = normalize_inserted_section_breaks(
                target_doc,
                inserted_start,
                inserted_end,
            )
            inserted_end = max(inserted_start, inserted_end - deleted_breaks)
        except Exception as exc:
            raise RuntimeError(f"无法按源格式插入素材：{insert_path}") from exc

        return min(target_doc.Content.End, max(inserted_start + 1, inserted_end))
    finally:
        source_doc.Close(SaveChanges=WD_DO_NOT_SAVE_CHANGES)


def apply_rule_to_doc(word, doc, rule: ReplaceRule) -> int:
    replace_count = 0
    search_from = doc.Content.Start

    while True:
        start_range = find_text_range(doc, rule.start_text, search_from)
        if start_range is None:
            break

        if rule.start_text == rule.end_text:
            end_range = start_range
        else:
            end_range = find_text_range(doc, rule.end_text, start_range.End)
            if end_range is None:
                search_from = start_range.End
                continue

        replace_range = build_replace_range(
            doc,
            start_range,
            end_range,
            replace_boundary_text=config.REPLACE_BOUNDARY_TEXT,
        )
        search_from = insert_docx_keep_source_format(word, replace_range, rule.insert_path)
        replace_count += 1

    return replace_count


def open_word():
    word = DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = WD_ALERTS_NONE
    word.ScreenUpdating = False
    return word


def process_one_doc(word, target_path: Path, rules: list[ReplaceRule]) -> tuple[bool, list[str]]:
    doc = word.Documents.Open(
        str(target_path),
        ConfirmConversions=False,
        ReadOnly=not config.OVERWRITE_ORIGINAL,
        AddToRecentFiles=False,
        Visible=False,
        OpenAndRepair=False,
        NoEncodingDialog=True,
    )

    applied: list[str] = []
    output_path = get_output_path(target_path)

    try:
        for rule in rules:
            if not rule.insert_path.exists():
                continue

            count = apply_rule_to_doc(word, doc, rule)
            if count:
                applied.append(f"{rule.label}，替换 {count} 处，插入 {rule.insert_path.name}")

        if applied:
            if config.OVERWRITE_ORIGINAL:
                doc.Save()
            else:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                doc.SaveAs2(str(output_path), FileFormat=WD_FORMAT_XML_DOCUMENT)

        return bool(applied), applied
    finally:
        doc.Close(SaveChanges=WD_DO_NOT_SAVE_CHANGES)


def validate_required_paths() -> list[str]:
    messages: list[str] = []
    if not config.RULES_XLSX.exists():
        messages.append(f"[错误] 规则表不存在：{config.RULES_XLSX}")
    if not config.TARGET_DOCX_DIR.exists():
        messages.append(f"[错误] 被替换文件夹不存在：{config.TARGET_DOCX_DIR}")
    if not config.INSERT_DOCX_DIR.exists():
        messages.append(f"[错误] 插入素材文件夹不存在：{config.INSERT_DOCX_DIR}")
    return messages


def cmd_long(logger) -> int:
    logger.info("=== Word COM 规则替换批处理 ===")
    logger.info(f"规则表：{config.RULES_XLSX} [工作表: {config.LONG_RULES_SHEET}]")
    logger.info(f"被替换文件夹：{config.TARGET_DOCX_DIR}")
    logger.info(f"插入素材文件夹：{config.INSERT_DOCX_DIR}")
    logger.info(f"输出模式：{'原地覆盖' if config.OVERWRITE_ORIGINAL else f'保存到 {config.OUTPUT_DIR}'}")
    logger.info(f"起止特征：{'一并替换' if config.REPLACE_BOUNDARY_TEXT else '保留'}")

    validation_messages = validate_required_paths()
    if validation_messages:
        for message in validation_messages:
            logger.error(message)
        logger.error("已停止。")
        return 1

    try:
        rules = load_rules(config.RULES_XLSX, logger=logger)
    except ValueError as e:
        logger.error(str(e))
        return 1

    missing_rules = [rule for rule in rules if not rule.insert_path.exists()]
    active_rules = [rule for rule in rules if rule.insert_path.exists()]

    logger.info(f"有效规则数：{len(active_rules)}")
    if missing_rules:
        logger.warning("=== 素材缺失，以下规则会跳过 ===")
        for rule in missing_rules:
            logger.warning(f"[素材缺失] {rule.label}，未找到：{rule.insert_path}")

    if not active_rules:
        logger.error("没有可执行规则。")
        return 1

    target_files = list(iter_docx_files(config.TARGET_DOCX_DIR))
    if not target_files:
        logger.error("被替换文件夹中没有找到 .docx 文件。")
        return 1

    pythoncom.CoInitialize()
    word = None
    scanned_count = 0
    changed_count = 0
    error_count = 0

    try:
        word = open_word()

        for target_path in target_files:
            scanned_count += 1
            relative_path = target_path.relative_to(config.TARGET_DOCX_DIR)
            logger.info(f"[处理中] {relative_path}")

            try:
                changed, applied = process_one_doc(word, target_path, active_rules)
                if changed:
                    changed_count += 1
                    logger.info(f"[已更新] {relative_path}")
                    for item in applied:
                        logger.info(f"  - {item}")
                else:
                    logger.info(f"[未变动] {relative_path}")
            except Exception as exc:
                error_count += 1
                logger.error(f"[异常] {relative_path}：{exc}")
    finally:
        if word is not None:
            word.Quit()
        pythoncom.CoUninitialize()

    logger.info("=== 统计摘要 ===")
    logger.info(f"共扫描文件：{scanned_count} 个")
    logger.info(f"成功更新文件：{changed_count} 个")

    if not config.OVERWRITE_ORIGINAL:
        logger.info(f"输出文件夹：{config.OUTPUT_DIR}")
    return 1 if error_count else 0
