
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def natural_sort_key(s):
    """
    自然排序算法：确保文件名中的数字（如 2, 10）能按数值大小正确排序。
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def get_leading_number(name):
    """
    提取文件名或文件夹名开头的数字序号
    """
    match = re.match(r'^(\d+)', name)
    if match:
        return int(match.group(1))
    return None


def set_paragraph_formatting(paragraph, text="", is_bold=False, font_size=12, first_line_indent=None):
    """
    设置文字格式为 宋体 + Arial，支持自定义字号、首行缩进，1.5倍行距，段前段后为0
    """
    paragraph.paragraph_format.line_spacing = 1.5
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)

    # ✨ 原逻辑保留：设置首行缩进（单位为 Pt）
    if first_line_indent is not None:
        paragraph.paragraph_format.first_line_indent = first_line_indent

    if text:
        run = paragraph.add_run(text)
        run.bold = is_bold
        run.font.size = Pt(font_size)

        # 设置西文字体为 Arial
        run.font.name = 'Arial'

        # 强制设置中文字体为 宋体
        rPr = run._element.get_or_add_rPr()
        rFonts = OxmlElement('w:rFonts')
        rFonts.set(qn('w:ascii'), 'Arial')
        rFonts.set(qn('w:hAnsi'), 'Arial')
        rFonts.set(qn('w:eastAsia'), '宋体')
        rPr.append(rFonts)


def add_text_paragraph(doc, text, is_bold=False, alignment=None, font_size=12, first_line_indent=None):
    """
    添加单行文本段落，支持自定义对齐、字号和首行缩进
    """
    p = doc.add_paragraph()
    if alignment:
        p.alignment = alignment
    set_paragraph_formatting(p, text, is_bold, font_size, first_line_indent)
    return p


def add_text_block(doc, text_block):
    """
    添加多行文本块（保持每行独立的段落格式）
    """
    for line in text_block.split('\n'):
        add_text_paragraph(doc, line)


def add_image_paragraph(doc, image_path):
    """
    添加图片，并设置居中对齐、1.5倍行距、段前段后为0
    """
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)

    run = p.add_run()
    # 限制图片最大宽度为 5.5 英寸（约14厘米），防止图片过大超出 Word 页边距
    run.add_picture(image_path, width=Inches(5.5))
    return p


def generate_word_document(root_dir, output_docx, folder_name, mother="母公司名称", team="项目组名称", date="日期"):
    """
    针对单个文件夹生成对应的 Word 文档
    """
    doc = Document()

    # ----------------------------------------------------
    # 第一页说明页内容（保持你原有逻辑）
    # ----------------------------------------------------
    title_text = f"项目组关于发行人子公司（{folder_name}）诚信信息的核查说明"
    add_text_paragraph(doc, title_text, is_bold=True, alignment=WD_ALIGN_PARAGRAPH.CENTER, font_size=16)

    # 插入一个空行隔开标题与正文
    add_text_paragraph(doc, "")

    # 小四号字(12pt) 缩进 2 个字符 = 24pt
    indent_2_chars = Pt(24)

    # 2. 正文段落：小四（12pt），两端对齐，首行缩进 24pt
    p1 = f"对于{folder_name}（发行人“{mother}”的子公司），项目组经过查询中国证监会证券期货市场失信信息公开查询平台、中国裁判文书网、全国企业信用信息公示系统、国家税务总局的重大税收违法案件信息公布栏、最高人民法院失信被执行人信息查询平台、信用中国等相关查询网站（相关查询截图见下述附件），结果显示该公司诚信状况良好，不存在被列入全国法院失信被执行人名单、证券期货市场失信记录、涉及重大诉讼仲裁、重大税收违法行为、生产或环保等领域方面严重违法失信行为；未发现报告期内涉嫌违法违规被有权机关调查、被采取强制措施；未发现存在债务违约等负面情形。"
    add_text_paragraph(doc, p1, is_bold=False, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, font_size=12, first_line_indent=indent_2_chars)

    p2 = "项目组已在中国裁判文书网中查询与该公司相关的法律文书，相关涉诉案件未对该公司及发行人的经营状况未产生重大不利影响，也未对本次债券发行造成实质性的影响。截至本文件出具日，该公司不存在对其及发行人构成重大不利影响的未决诉讼、仲裁及行政处罚的情况。"
    add_text_paragraph(doc, p2, is_bold=False, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, font_size=12, first_line_indent=indent_2_chars)

    p3 = "经项目组查询媒体对该公司的相关报道，未发现相关负面报道、媒体质疑事项（查询截图同见下述附件）。"
    add_text_paragraph(doc, p3, is_bold=False, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, font_size=12, first_line_indent=indent_2_chars)

    p4 = "特此说明。"
    add_text_paragraph(doc, p4, is_bold=False, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, font_size=12, first_line_indent=indent_2_chars)

    # 插入空行隔开正文与落款
    add_text_paragraph(doc, "")
    add_text_paragraph(doc, "")

    # 3. 落款：小四（12pt），靠右对齐（这里只修复为真正使用 GUI 输入值）
    add_text_paragraph(doc, team, is_bold=False, alignment=WD_ALIGN_PARAGRAPH.RIGHT, font_size=12)
    add_text_paragraph(doc, date, is_bold=False, alignment=WD_ALIGN_PARAGRAPH.RIGHT, font_size=12)

    # 4. 第一页结束，插入分页符
    doc.add_page_break()

    # ----------------------------------------------------
    # 扫描第一级目录，并按照数字序号精确映射
    # ----------------------------------------------------
    all_items = os.listdir(root_dir)
    items_by_num = {}

    for name in all_items:
        num = get_leading_number(name)
        if num is not None:
            items_by_num[num] = name

    # ----------------------------------------------------
    # 针对 1-8 号特殊序号的处理逻辑（保持原样）
    # ----------------------------------------------------

    # 序号 1
    text_1 = "附件：查询结果截图\n1、信用中国\n另见完整文件"
    add_text_block(doc, text_1)

    # 序号 2
    if 2 in items_by_num:
        name_2 = items_by_num[2]
        path_2 = os.path.join(root_dir, name_2)
        if os.path.isfile(path_2):
            name_no_ext, _ = os.path.splitext(name_2)
            add_text_paragraph(doc, name_no_ext)
            add_image_paragraph(doc, path_2)
    else:
        add_text_paragraph(doc, "2、发行人所属地方政府网站")

    # 序号 3
    if 3 in items_by_num:
        name_3 = items_by_num[3]
        path_3 = os.path.join(root_dir, name_3)
        if os.path.isfile(path_3):
            # 如果是单张图片文件，提取不带后缀的文件名作为标题
            name_no_ext, _ = os.path.splitext(name_3)
            add_text_paragraph(doc, name_no_ext)
            add_image_paragraph(doc, path_3)
    else:
        # 如果不存在图片/文件夹，则走原本的默认文本兜底
        text_3 = "3、中国证监会证券期货市场失信记录查询平台\n "
        add_text_block(doc, text_3)

    # 序号 4
    if 4 in items_by_num:
        name_4 = items_by_num[4]
        path_4 = os.path.join(root_dir, name_4)
        if os.path.isfile(path_4):
            name_no_ext, _ = os.path.splitext(name_4)
            add_text_paragraph(doc, name_no_ext)
            add_image_paragraph(doc, path_4)
    else:
        add_text_paragraph(doc, "4、中国执行信息公开网—综合查询\n ")

    # 序号 5
    if 5 in items_by_num:
        name_5 = items_by_num[5]
        path_5 = os.path.join(root_dir, name_5)
        if os.path.isfile(path_5):
            name_no_ext, _ = os.path.splitext(name_5)
            add_text_paragraph(doc, name_no_ext)
            add_image_paragraph(doc, path_5)
    else:
        add_text_paragraph(doc, "5、全国法院失信被执行人名单信息公布与查询\n ")

    # 序号 6 (保持原样)
    text_6 = "6、国家企业信用信息公示系统\n另见完整文件"
    add_text_block(doc, text_6)

    # 序号 7
    if 7 in items_by_num:
        name_7 = items_by_num[7]
        path_7 = os.path.join(root_dir, name_7)
        if os.path.isdir(path_7):
            add_text_paragraph(doc, name_7)
            sub_images = sorted(os.listdir(path_7), key=natural_sort_key)
            for img in sub_images:
                img_path = os.path.join(path_7, img)
                if os.path.isfile(img_path) and img.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    add_image_paragraph(doc, img_path)
    else:
        add_text_paragraph(doc, "7、中国裁判文书网")

    # 序号 8
    if 8 in items_by_num:
        name_8 = items_by_num[8]
        path_8 = os.path.join(root_dir, name_8)
        if os.path.isfile(path_8):
            name_no_ext, _ = os.path.splitext(name_8)
            add_text_paragraph(doc, name_no_ext)
            add_image_paragraph(doc, path_8)
    else:
        text_8 = "8、国家税务总局江苏省税务局\n "
        add_text_block(doc, text_8)

    # ----------------------------------------------------
    # 后续序号（>= 9）：按数字严格升序读取并输出（含21号兜底）
    # ----------------------------------------------------
    nums_set = set([num for num in items_by_num.keys() if num >= 9])
    nums_set.add(21)

    remaining_nums = sorted(list(nums_set))

    for num in remaining_nums:
        if num == 21 and 21 not in items_by_num:
            add_text_paragraph(doc, "21、中国统计信息网\n ")
            continue

        name = items_by_num[num]
        path = os.path.join(root_dir, name)

        if os.path.isdir(path):
            add_text_paragraph(doc, name)
            sub_images = sorted(os.listdir(path), key=natural_sort_key)
            for img in sub_images:
                img_path = os.path.join(path, img)
                if os.path.isfile(img_path) and img.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    add_image_paragraph(doc, img_path)
        else:
            name_no_ext, _ = os.path.splitext(name)
            add_text_paragraph(doc, name_no_ext)
            if name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                add_image_paragraph(doc, path)

    # 保存文档
    doc.save(output_docx)
    print(f"【生成成功】-> {os.path.basename(output_docx)}")


def batch_process_companies(parent_dir, output_dir, mother_company_name, project_team_name, report_date):
    """
    批量处理函数：遍历父目录下的所有公司文件夹
    """
    if not os.path.exists(parent_dir):
        print(f"错误：找不到指定的父文件夹路径：{parent_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)

    print("开始进行批量处理...")
    print("-" * 50)

    success_count = 0
    for folder_name in os.listdir(parent_dir):
        folder_path = os.path.join(parent_dir, folder_name)

        if os.path.isdir(folder_path):
            docx_name = f"项目组关于发行人子公司（{folder_name}）诚信信息的核查说明.docx"
            output_docx_path = os.path.join(output_dir, docx_name)

            try:
                generate_word_document(
                    folder_path,
                    output_docx_path,
                    folder_name,
                    mother=mother_company_name,
                    team=project_team_name,
                    date=report_date
                )
                success_count += 1
            except Exception as e:
                print(f"❌ 处理文件夹【{folder_name}】时发生错误: {e}")

    print("-" * 50)
    print(f"批量处理完毕！成功生成 {success_count} 个 Word 文档。文件保存在: {os.path.abspath(output_dir)}")


# =========================
# GUI 部分
# =========================

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("诚信信息核查说明生成工具")
        self.root.geometry("760x320")
        self.root.resizable(False, False)

        self.parent_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.mother_var = tk.StringVar()
        self.team_var = tk.StringVar()
        self.date_var = tk.StringVar()

        self.build_ui()

    def build_ui(self):
        pad_y = 10

        # 输入目录
        tk.Label(self.root, text="输入目录（子公司总文件夹）:", anchor="w", width=22).grid(row=0, column=0, padx=10, pady=pad_y, sticky="w")
        tk.Entry(self.root, textvariable=self.parent_dir_var, width=60).grid(row=0, column=1, padx=5, pady=pad_y)
        tk.Button(self.root, text="选择...", command=self.select_parent_dir, width=10).grid(row=0, column=2, padx=10, pady=pad_y)

        # 输出目录
        tk.Label(self.root, text="输出目录:", anchor="w", width=22).grid(row=1, column=0, padx=10, pady=pad_y, sticky="w")
        tk.Entry(self.root, textvariable=self.output_dir_var, width=60).grid(row=1, column=1, padx=5, pady=pad_y)
        tk.Button(self.root, text="选择...", command=self.select_output_dir, width=10).grid(row=1, column=2, padx=10, pady=pad_y)

        # 母公司名称
        tk.Label(self.root, text="母公司名称:", anchor="w", width=22).grid(row=2, column=0, padx=10, pady=pad_y, sticky="w")
        tk.Entry(self.root, textvariable=self.mother_var, width=60).grid(row=2, column=1, padx=5, pady=pad_y)

        # 项目组名称
        tk.Label(self.root, text="项目组名称:", anchor="w", width=22).grid(row=3, column=0, padx=10, pady=pad_y, sticky="w")
        tk.Entry(self.root, textvariable=self.team_var, width=60).grid(row=3, column=1, padx=5, pady=pad_y)

        # 日期
        tk.Label(self.root, text="日期:", anchor="w", width=22).grid(row=4, column=0, padx=10, pady=pad_y, sticky="w")
        tk.Entry(self.root, textvariable=self.date_var, width=60).grid(row=4, column=1, padx=5, pady=pad_y)

        # 开始按钮
        tk.Button(self.root, text="开始生成", command=self.run, width=20, height=2).grid(row=5, column=1, pady=25)

    def select_parent_dir(self):
        path = filedialog.askdirectory(title="请选择输入目录")
        if path:
            self.parent_dir_var.set(path)

    def select_output_dir(self):
        path = filedialog.askdirectory(title="请选择输出目录")
        if path:
            self.output_dir_var.set(path)

    def run(self):
        parent_dir = self.parent_dir_var.get().strip()
        output_dir = self.output_dir_var.get().strip()
        mother_company_name = self.mother_var.get().strip()
        project_team_name = self.team_var.get().strip()
        report_date = self.date_var.get().strip()

        if not parent_dir:
            messagebox.showwarning("提示", "请选择输入目录。")
            return
        if not output_dir:
            messagebox.showwarning("提示", "请选择输出目录。")
            return
        if not mother_company_name:
            messagebox.showwarning("提示", "请输入母公司名称。")
            return
        if not project_team_name:
            messagebox.showwarning("提示", "请输入项目组名称。")
            return
        if not report_date:
            messagebox.showwarning("提示", "请输入日期。")
            return

        try:
            batch_process_companies(
                parent_dir=parent_dir,
                output_dir=output_dir,
                mother_company_name=mother_company_name,
                project_team_name=project_team_name,
                report_date=report_date
            )
            messagebox.showinfo("完成", "Word 文档批量生成完成。")
        except Exception as e:
            messagebox.showerror("错误", f"运行失败：{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
