import os
import re
import openpyxl
from openpyxl.styles import Font

# ==================== 1. 自然排序核心算法 ====================

_CHINESE_NUM_MAP = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
    '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
}

_CHINESE_NUM_SORTED = sorted(_CHINESE_NUM_MAP.keys(), key=len, reverse=True)

def _replace_chinese_ordinals(s):
    def _replacer(m):
        cn_num = m.group(1)
        if cn_num in _CHINESE_NUM_MAP:
            return f"{_CHINESE_NUM_MAP[cn_num]:05d}"
        return m.group(0)

    pattern = r'第(' + '|'.join(_CHINESE_NUM_SORTED) + r')'
    return re.sub(pattern, _replacer, s)

def natural_sort_key(s):
    s_converted = _replace_chinese_ordinals(str(s))
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s_converted)]


# ==================== 2. 文件名解析逻辑 ====================

def parse_name_components(raw_name):
    """
    解析文件名/文件夹名：
    1. code_part: 开头的编号
    2. clean_name: 去除扩展名 + 去除开头编号后的纯名称
    """
    base_name, _ = os.path.splitext(raw_name)

    code_part = ""
    num_code_match = re.match(r'^([\d]+(?:-[\d]+)*)', base_name)
    cn_code_match = re.match(r'^(第[' + ''.join(_CHINESE_NUM_MAP.keys()) + r']+(?:部分|[章节编部]))', base_name)

    if num_code_match:
        code_part = num_code_match.group(1)
    elif cn_code_match:
        code_part = cn_code_match.group(1)
    elif '$' in base_name:
        code_part = base_name.split('$', 1)[0].strip()

    clean_name = base_name
    if code_part:
        clean_name = re.sub(r'^' + re.escape(code_part) + r'[\$\s\-_]*', '', base_name).strip()
    
    if not clean_name:
        clean_name = base_name

    return code_part, clean_name

def remove_empty_folders(records):
    """
    删除所有没有任何文件后代的文件夹。
    只要文件夹本身或任意子文件夹中存在文件，该文件夹就会保留；
    最末级没有文件的空文件夹不会展示在 Excel 中。
    """
    # 所有包含文件或文件后代的目录
    dirs_with_files = set()

    for item in records:
        if not item["is_folder"]:
            path = item["dir_path"]

            while True:
                dirs_with_files.add(path)

                parent = os.path.dirname(path)

                if parent == path:
                    break

                path = parent

    new_records = []

    for item in records:
        if not item["is_folder"]:
            new_records.append(item)
        elif item["full_path"] in dirs_with_files:
            new_records.append(item)

    return new_records
# ==================== 3. 目录树遍历、精准去重与 Excel 导出 ====================

def collect_directory_structure(root_path):
    records = []
    
    def _traverse(current_dir, level=1):
        try:
            entries = os.listdir(current_dir)
        except PermissionError:
            return
            
        entries_sorted = sorted(entries, key=natural_sort_key)

        folders = [e for e in entries_sorted if os.path.isdir(os.path.join(current_dir, e))]
        files = [e for e in entries_sorted if os.path.isfile(os.path.join(current_dir, e))]

        # 处理文件夹
        for folder in folders:
            folder_path = os.path.join(current_dir, folder)
            code, name = parse_name_components(folder)
            
            records.append({
                "code": code,
                "name": name,
                "dir_path": current_dir,
                "full_path": folder_path,
                "is_folder": True,
                "level": level
            })
            _traverse(folder_path, level + 1)

        # 处理文件
        for file in files:
            if file.startswith('~$') or file.startswith('.'):
                continue
            
            code, name = parse_name_components(file)
            records.append({
                "code": code,
                "name": name,
                "dir_path": current_dir,
                "full_path": os.path.join(current_dir, file),
                "is_folder": False,
                "level": level
            })

    _traverse(root_path, level=1)
    return records


def deduplicate_records(records):
    """
    只在“同一个文件夹路径下”对相同编号的文件进行去重：
    不同“部分”/文件夹中的重复编号会被完整保留。
    """
    best_item_map = {}

    for item in records:
        code = item['code']
        # 唯一组合键：所属文件夹路径 + 文件编号
        unique_key = (item['dir_path'], code) if code else None

        if not unique_key:
            continue

        if unique_key not in best_item_map:
            best_item_map[unique_key] = item
        else:
            # 同一目录下若存在同编号副本，取名称更长者
            if len(item['name']) > len(best_item_map[unique_key]['name']):
                best_item_map[unique_key] = item

    # 按照树状遍历原始顺序输出
    deduped_list = []
    visited_keys = set()

    for item in records:
        code = item['code']
        unique_key = (item['dir_path'], code) if code else None

        if not unique_key:
            deduped_list.append(item)
        elif unique_key not in visited_keys:
            deduped_list.append(best_item_map[unique_key])
            visited_keys.add(unique_key)

    return deduped_list


def export_directory_to_excel(root_dir_path, output_excel_path):
    raw_records = collect_directory_structure(root_dir_path)

    raw_records = remove_empty_folders(raw_records)
    final_records = deduplicate_records(raw_records)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "文件目录"

    # ==================== 字体定义 ====================
    # 小四 = 12pt
    header_font = Font(name="宋体", size=12, bold=True)
    folder_font = Font(name="宋体", size=12, bold=True)
    file_font = Font(name="宋体", size=12, bold=False)

    headers = ["层级", "类型", "编号", "目录/文件名称"]
    ws.append(headers)

    # 表头
    for cell in ws[1]:
        cell.font = header_font

    # 写入数据
    for item in final_records:
        ws.append([
            item["level"],
            "文件夹" if item["is_folder"] else "文件",
            item["code"],
            item["name"]
        ])

        row = ws.max_row

        if item["is_folder"]:
            font = folder_font
        else:
            font = file_font

        # 四列都设置字体
        for c in range(1, 5):
            ws.cell(row=row, column=c).font = font

    # ==================== 自动列宽（可选）====================
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter

        for cell in col:
            try:
                length = len(str(cell.value))
                if length > max_length:
                    max_length = length
            except:
                pass

        # 中文大约占1.8个英文字符
        ws.column_dimensions[col_letter].width = min(max_length * 1.8 + 2, 80)

    wb.save(output_excel_path)
    print(f"处理完成！最终目录已成功保存至: {os.path.abspath(output_excel_path)}")


def export_excel_to_word_directory(excel_path, output_word_path):
    """
    根据 export_directory_to_excel 生成的 Excel 目录，生成 Word 版缩进目录。
    文件夹加粗，文件不加粗；不按层级缩进。
    """
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.shared import Cm, Pt
    except ImportError as exc:
        raise ImportError("请先安装 python-docx：pip install python-docx") from exc

    def set_font(run, font_name="宋体", size=12, bold=False):
        run.font.name = font_name
        run.font.size = Pt(size)
        run.font.bold = bold
        run._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)

    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb.active

    header = [cell.value for cell in ws[1]]
    required_headers = ["层级", "类型", "编号", "目录/文件名称"]
    missing_headers = [h for h in required_headers if h not in header]
    if missing_headers:
        raise ValueError(f"Excel 缺少必要列：{', '.join(missing_headers)}")

    col_index = {name: header.index(name) for name in required_headers}

    doc = Document()
    normal_style = doc.styles["Normal"]
    normal_style.font.name = "宋体"
    normal_style.font.size = Pt(12)
    normal_style._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.add_run("目录")
    set_font(title_run, size=16, bold=True)

    for row in ws.iter_rows(min_row=2, values_only=True):
        level = row[col_index["层级"]]
        item_type = row[col_index["类型"]]
        code = row[col_index["编号"]]
        name = row[col_index["目录/文件名称"]]

        if name is None:
            continue

        try:
            level = int(level)
        except (TypeError, ValueError):
            level = 1

        text_parts = []
        if code:
            text_parts.append(str(code))
        text_parts.append(str(name))

        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(0)
        paragraph.paragraph_format.space_after = Pt(3)

        run = paragraph.add_run(" ".join(text_parts))
        set_font(run, size=12, bold=(item_type == "文件夹"))

    doc.save(output_word_path)
    print(f"Word 目录已成功保存至: {os.path.abspath(output_word_path)}")


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description="把多级文件夹结构导出为 Excel 目录，再转成 Word 目录。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            '  python 输出文件目录.py "D:/底稿/某项目/第三部分"\n'
            "  python 输出文件目录.py ./示例底稿目录 --excel 目录.xlsx --word 目录.docx\n"
        ),
    )
    parser.add_argument("target", nargs="?", default="示例底稿目录", help="要扫描的根目录。")
    parser.add_argument("--excel", default="目录.xlsx", help="输出 Excel 文件名（默认 目录.xlsx）。")
    parser.add_argument("--word", default="目录.docx", help="输出 Word 文件名（默认 目录.docx）。")
    parser.add_argument("--demo", action="store_true",
                        help="脱敏模式：产物名固定为 目录.xlsx/目录.docx，不带项目标识。")
    return parser.parse_args()


if __name__ == "__main__":
    _args = parse_args()
    TARGET_DIR = _args.target
    OUTPUT_EXCEL = _args.excel
    OUTPUT_WORD = _args.word

    if os.path.exists(TARGET_DIR):
        export_directory_to_excel(TARGET_DIR, OUTPUT_EXCEL)
        export_excel_to_word_directory(OUTPUT_EXCEL, OUTPUT_WORD)
    else:
        print(f"请检查 TARGET_DIR 路径是否正确：{TARGET_DIR}")
