# -*- coding: utf-8 -*-
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_LINE_SPACING

# ==================== 配置路径 ====================
INPUT_FOLDER = "示例底稿目录/第十章$上市审核规则适用指引——审核重点关注事项核查底稿"       # 你的待处理 Word 文件夹路径
OUTPUT_FOLDER = INPUT_FOLDER    # 处理后的文档输出路径
SEPARATE_FOLDER = INPUT_FOLDER # 独立额外输出的签章页文档路径
issuer = "示例市示范区城市资产经营有限公司"
project_team = "示例项目组 "
date = "2026年6月   日"
sign_name = "全部签章页.docx"

# ==================== 脱敏模式 ====================
# IBDW_DEMO_MODE=1（或 --demo）时，发行人/项目组/落款日期一律用示例值，
# 避免把真实主体写进生成的 Word。
DEMO_MODE = str(os.environ.get("IBDW_DEMO_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}
DEMO_ISSUER = "示例市示范区城市资产经营有限公司"
DEMO_TEAM = "示例项目组"
DEMO_DATE = "2026年6月   日"



# 创建输出文件夹
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(SEPARATE_FOLDER, exist_ok=True)


def set_run_font(run, chinese_font="宋体", western_font="Arial", size_pt=12):
    """
    设置字体：
    中文：宋体
    英文：Arial
    默认字号：小四（12pt）
    """
    # 英文字体
    run.font.name = western_font
    run.font.size = Pt(size_pt)

    rPr = run._r.get_or_add_rPr()

    # 如果已有 rFonts，则复用；否则新建
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)

    rFonts.set(qn("w:ascii"), western_font)
    rFonts.set(qn("w:hAnsi"), western_font)
    rFonts.set(qn("w:eastAsia"), chinese_font)
    rFonts.set(qn("w:hint"), "eastAsia")

def force_run_font(run, chinese_font="宋体", western_font="Arial"):
    """
    仅修改字体，不修改字号
    """
    run.font.name = western_font

    rPr = run._r.get_or_add_rPr()

    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)

    rFonts.set(qn("w:ascii"), western_font)
    rFonts.set(qn("w:hAnsi"), western_font)
    rFonts.set(qn("w:eastAsia"), chinese_font)
    rFonts.set(qn("w:hint"), "eastAsia")

def force_document_font(doc):
    """
    全文统一字体，不修改字号
    """

    # 普通段落
    for p in doc.paragraphs:
        for run in p.runs:
            force_run_font(run)

    # 表格
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for run in p.runs:
                        force_run_font(run)

    # 页眉
    for section in doc.sections:
        for p in section.header.paragraphs:
            for run in p.runs:
                force_run_font(run)

        for p in section.footer.paragraphs:
            for run in p.runs:
                force_run_font(run)

def force_header_font(doc):
    """
    页眉统一设置：
    中文：宋体
    英文：Arial
    字号：5号（10.5pt）
    """
    for section in doc.sections:

        # 页眉
        for p in section.header.paragraphs:
            for run in p.runs:
                run.font.name = "Arial"
                run.font.size = Pt(10.5)

                rPr = run._r.get_or_add_rPr()

                rFonts = rPr.find(qn("w:rFonts"))
                if rFonts is None:
                    rFonts = OxmlElement("w:rFonts")
                    rPr.append(rFonts)

                rFonts.set(qn("w:ascii"), "Arial")
                rFonts.set(qn("w:hAnsi"), "Arial")
                rFonts.set(qn("w:eastAsia"), "宋体")
                rFonts.set(qn("w:hint"), "eastAsia")

def set_paragraph_format(doc):
    """
    设置表格外所有段落：
    - 1.5 倍行距
    - 段前 0
    - 段后 0
    """
    for p in doc.paragraphs:
        fmt = p.paragraph_format
        fmt.line_spacing = 1.5
        fmt.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        fmt.space_before = Pt(0)
        fmt.space_after = Pt(0)

def format_paragraph(paragraph):
    fmt = paragraph.paragraph_format
    fmt.line_spacing = 1.5
    fmt.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)

def remove_last_picture(doc):
    """
    删除文档最后一张图片（正文）
    """

    drawings = []

    for p in doc.paragraphs:
        for run in p.runs:
            drawing = run._element.find(qn("w:drawing"))
            if drawing is not None:
                drawings.append(run)

    if drawings:
        last_run = drawings[-1]
        last_run._element.getparent().remove(last_run._element)

def parse_filename(filename):
    """
    解析文件名，提取编号和标题
    例如: "1-2-1 控股股东或者实际控制人为自然人的..."
    返回: ("1-2-1", "控股股东或者实际控制人为自然人的...")
    """
    name_without_ext = os.path.splitext(filename)[0]
    # 使用空格拆分第一组字符（通常是编号）
    parts = name_without_ext.split(maxsplit=1)
    
    if len(parts) == 2 and any(char.isdigit() or char == '-' for char in parts[0]):
        return parts[0], parts[1]
    else:
        return "", name_without_ext


def process_docx(file_path, filename, all_sign_doc, output_path):
    doc = Document(file_path)
    force_document_font(doc)      # 字体
    force_header_font(doc)        # 页眉
    set_paragraph_format(doc)     # 行距
    remove_last_picture(doc)
    # 1. 获取文档最后50个字符
    full_text = "".join([p.text for p in doc.paragraphs])
    last_50_chars = full_text[-50:]
    
    numbering, title = parse_filename(filename)

   # ------------------ 情况 A: 存在“项目组”字样 ------------------
    if "项目组" in last_50_chars:
        print(f"[处理] {filename} -> 匹配到【项目组】，正在替换末尾文字...")
        
        # 倒序查找最后一个包含“项目组”的段落
        target_idx = -1
        for i in range(len(doc.paragraphs) - 1, -1, -1):
            if "项目组" in doc.paragraphs[i].text:
                target_idx = i
                break
                
        if target_idx != -1:
            # 替换当前行（保留原有格式：只改写第一个 run 的文字，清空后续 run）
            p1 = doc.paragraphs[target_idx]
            if p1.runs:
                p1.runs[0].text = project_team
                for r in p1.runs[1:]:
                    r.text = ""
            else:
                p1.text = project_team
            
            format_paragraph(p1)
            p1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            # ✅ 修改：遍历段落中的 runs 来设置字体
            for run in p1.runs:
                set_run_font(run)
            
            # 替换下一行（日期行）
            if target_idx + 1 < len(doc.paragraphs):
                p2 = doc.paragraphs[target_idx + 1]
                if p2.runs:
                    p2.runs[0].text = date
                    for r in p2.runs[1:]:
                        r.text = ""
                else:
                    p2.text = date
                    
                format_paragraph(p2)
                p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                # ✅ 修改：遍历段落中的 runs 来设置字体
                for run in p2.runs:
                    set_run_font(run)

            # ===== 删除日期行之后的所有段落 =====
            for i in range(len(doc.paragraphs) - 1, target_idx + 1, -1):
                p = doc.paragraphs[i]
                p._element.getparent().remove(p._element)

        # 保存修改后的原文件
        doc.save(output_path)

    # ------------------ 情况 B: 不存在“项目组”字样 ------------------
    else:
        print(f"[处理] {filename} -> 未匹配到【项目组】，正在生成独立签章页...")
        
        # --- 动作1：在原文档末尾追加独立成页的签章页(1) ---
        # 使用添加新节(Section)来实现完全独立的页眉控制
        new_section = doc.add_section()
        new_section.header.is_linked_to_previous = False # 断开页眉链接
        
        # 设置原文档最后一页的页眉
        if numbering:
            hp = new_section.header.paragraphs[0]
            hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            hrun = hp.add_run(numbering)
            set_run_font(hrun, size_pt=10.5) # 五号字 = 10.5pt

        # 写入签章页文字
        p1 = doc.add_paragraph()
        format_paragraph(p1)
        r1 = p1.add_run(f"（本页无正文，为《{title}》之签章页）")
        set_run_font(r1) # 小四，这里设为12pt

        for _ in range(8):
            px = doc.add_paragraph()
            format_paragraph(px)

        p2 = doc.add_paragraph()
        format_paragraph(p2)
        p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r2 = p2.add_run(issuer)
        set_run_font(r2)
        
        p3 = doc.add_paragraph()
        format_paragraph(p3)
        p3.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r3 = p3.add_run(date)
        set_run_font(r3)
        
        doc.save(output_path)

        # --- 动作2：单独输出一个纯签章页的独立 Word 文档 ---
        # 如果不是第一页，则先分页
        if len(all_sign_doc.paragraphs) > 0:
            section = all_sign_doc.add_section(WD_SECTION.NEW_PAGE)
        section = all_sign_doc.sections[-1]

        header = section.header
        header.is_linked_to_previous = False

        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        if numbering:
            run = hp.add_run(numbering)
            set_run_font(run, size_pt=10.5)

        p1 = all_sign_doc.add_paragraph()
        format_paragraph(p1)
        r1 = p1.add_run(
            f"（本页无正文，为《{title}》之签章页）"
        )
        set_run_font(r1)

        for _ in range(8):
            px = all_sign_doc.add_paragraph()
            format_paragraph(px)

        p2 = all_sign_doc.add_paragraph()
        format_paragraph(p2)
        p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r2 = p2.add_run(issuer)
        set_run_font(r2)
       
        p3 = all_sign_doc.add_paragraph()
        format_paragraph(p3)
        p3.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r3 = p3.add_run(date)
        set_run_font(r3)


def main():
    global issuer, project_team, date
    if DEMO_MODE:
        issuer, project_team, date = DEMO_ISSUER, DEMO_TEAM, DEMO_DATE
        print(">>> 脱敏模式：发行人/项目组/落款日期使用示例值")

    if not os.path.exists(INPUT_FOLDER):
        print(f"找不到输入的文件夹：{INPUT_FOLDER}，请先创建并放入Word文件。")
        return
    
    all_sign_doc = Document()
    docx_files = []

    for root, dirs, files in os.walk(INPUT_FOLDER):
        for f in files:
            if f.endswith('.docx') and not f.startswith('~$'):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, INPUT_FOLDER)
                docx_files.append((full_path, rel_path))  
                
    print(f"开始批量处理，共发现 {len(docx_files)} 个有效的 Docx 文件...")
    
    if len(all_sign_doc.paragraphs) == 1 and not all_sign_doc.paragraphs[0].text:
        p = all_sign_doc.paragraphs[0]._element
        p.getparent().remove(p)
    
    for file_path, rel_path in docx_files:
        filename = os.path.basename(file_path)
        out_path = os.path.join(OUTPUT_FOLDER, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            process_docx(file_path, filename, all_sign_doc, out_path)
        except Exception as e:
            print(f"处理文件 {filename} 时发生错误: {e}")

    all_sign_doc.save(
        os.path.join(SEPARATE_FOLDER, sign_name)
    )
    print("\n所有文件批处理完成！")


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description="初始化底稿文件：字体/行距刷新 + 末尾处理 + 汇总签章页。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            '  python 初始化底稿文件.py --folder "D:/底稿/某项目/第三部分" --issuer "示例公司" --team "示例项目组"\n'
            "  python 初始化底稿文件.py --folder ./示例底稿目录 --demo\n"
        ),
    )
    parser.add_argument("--folder", default=None, help="待处理 Word 文件夹；默认取模块内 INPUT_FOLDER。")
    parser.add_argument("--issuer", default=None, help="落款发行人名称；默认取模块内 issuer。")
    parser.add_argument("--team", default=None, help="落款项目组名称；默认取模块内 project_team。")
    parser.add_argument("--date", default=None, help="落款日期文本；默认取模块内 date。")
    parser.add_argument("--sign-name", default=None, help="汇总签章页文件名；默认取模块内 sign_name。")
    parser.add_argument("--demo", action="store_true",
                        help="脱敏模式：发行人/项目组/落款日期强制用示例值（等价于 IBDW_DEMO_MODE=1）。")
    return parser.parse_args()


if __name__ == "__main__":
    _args = parse_args()
    if _args.demo:
        DEMO_MODE = True
    if _args.folder:
        INPUT_FOLDER = OUTPUT_FOLDER = SEPARATE_FOLDER = _args.folder
    if _args.issuer:
        issuer = _args.issuer
    if _args.team:
        project_team = _args.team
    if _args.date:
        date = _args.date
    if _args.sign_name:
        sign_name = _args.sign_name
    main()