# 文件路径: views/word_generator_ui.py
# 功能来源: 输出.py —— 批量生成《诚信信息的核查说明》Word 文档
# P4 扩展：可选「编号映射」——命中的公司文件名加 `{编号} ` 前缀，
#          全部输出仍写入统一输出目录；无编号公司保持旧行为。

import os
import queue
import re
import threading
import customtkinter as ctk
from tkinter import filedialog

from views import theme
import templates_store as store
from modules.scraper.subject_utils import safe_path_name
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


# =========================
# Word 生成核心逻辑（源自 输出.py）
# =========================

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

    # 设置首行缩进（单位为 Pt）
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


def generate_word_document(root_dir, output_docx, folder_name, mother="母公司名称", team="项目组名称", date="日期", log=print):
    """
    针对单个文件夹生成对应的 Word 文档
    """
    doc = Document()

    # ----------------------------------------------------
    # 第一页说明页内容
    # ----------------------------------------------------
    title_text = f"项目组关于发行人子公司（{folder_name}）诚信信息的核查说明"
    add_text_paragraph(doc, title_text, is_bold=True, alignment=WD_ALIGN_PARAGRAPH.CENTER, font_size=16)

    # 插入一个空行隔开标题与正文
    add_text_paragraph(doc, "")

    # 小四号字(12pt) 缩进 2 个字符 = 24pt
    indent_2_chars = Pt(24)

    # 正文段落：小四（12pt），两端对齐，首行缩进 24pt
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

    # 落款：小四（12pt），靠右对齐
    add_text_paragraph(doc, team, is_bold=False, alignment=WD_ALIGN_PARAGRAPH.RIGHT, font_size=12)
    add_text_paragraph(doc, date, is_bold=False, alignment=WD_ALIGN_PARAGRAPH.RIGHT, font_size=12)

    # 第一页结束，插入分页符
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
    # 针对 1-8 号特殊序号的处理逻辑
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
            name_no_ext, _ = os.path.splitext(name_3)
            add_text_paragraph(doc, name_no_ext)
            add_image_paragraph(doc, path_3)
    else:
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

    # 序号 6
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
    log(f"【生成成功】-> {os.path.basename(output_docx)}")


def _demo_mode_enabled():
    """IBDW_DEMO_MODE=1 时导出脱敏版说明文件：主体名一律显示为 示例主体NNN。"""
    import os
    return str(os.environ.get("IBDW_DEMO_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}


def batch_process_companies(parent_dir, output_dir, mother_company_name, project_team_name, report_date, log=print, code_map=None):
    """
    批量处理函数：遍历父目录下的所有公司文件夹。
    code_map: {公司名: 编号}（可选）——命中者文件名为 `{编号} 原名.docx`，
              未命中/未传保持旧行为原名；输出一律写入 output_dir。
    """
    if not os.path.exists(parent_dir):
        log(f"错误：找不到指定的父文件夹路径：{parent_dir}")
        return 0

    os.makedirs(output_dir, exist_ok=True)
    lookup = {safe_path_name(name): str(code).strip()
              for name, code in (code_map or {}).items() if str(code).strip()}

    log("开始进行批量处理...")
    log("-" * 50)

    success_count = 0
    coded_count = 0
    demo = _demo_mode_enabled()
    folders = [n for n in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, n))]
    demo_names = {name: f"示例主体{index:03d}" for index, name in enumerate(folders, start=1)}
    if demo:
        log(">>> 脱敏模式：文件名与正文中的主体名替换为 示例主体NNN")
    for folder_name in os.listdir(parent_dir):
        folder_path = os.path.join(parent_dir, folder_name)

        if os.path.isdir(folder_path):
            display_name = demo_names.get(folder_name, folder_name) if demo else folder_name
            base_docx_name = f"项目组关于发行人子公司（{display_name}）诚信信息的核查说明.docx"
            code = lookup.get(folder_name) or lookup.get(safe_path_name(folder_name)) or ""
            docx_name = f"{code} {base_docx_name}" if code else base_docx_name
            if code:
                coded_count += 1
                log(f"编号 {code} → {folder_name}")
            output_docx_path = os.path.join(output_dir, docx_name)

            try:
                generate_word_document(
                    folder_path,
                    output_docx_path,
                    display_name,
                    mother=mother_company_name,
                    team=project_team_name,
                    date=report_date,
                    log=log
                )
                success_count += 1
            except Exception as e:
                log(f"❌ 处理文件夹【{folder_name}】时发生错误: {e}")

    log("-" * 50)
    if coded_count:
        log(f"其中 {coded_count} 个文档已应用编号前缀。")
    log(f"批量处理完毕！成功生成 {success_count} 个 Word 文档。文件保存在: {output_dir}")
    return success_count


def parse_code_map(text):
    """「编号映射」多行文本 → {公司名: 编号}；无编号/无名称的行忽略。"""
    code_map = {}
    for entry in store.parse_roster(text):
        if entry["code"] and entry["name"]:
            code_map[entry["name"]] = entry["code"]
    return code_map


def best_template_for(parent_dir):
    """扫描模板库，返回与 parent_dir 子文件夹命中数最多的 (模板, 命中数)。"""
    try:
        subdirs = {d for d in os.listdir(parent_dir)
                   if os.path.isdir(os.path.join(parent_dir, d))}
    except OSError:
        return None, 0
    best, best_hits = None, 0
    for t in store.load_templates():
        hits = sum(1 for c in (t.get("companies") or [])
                   if safe_path_name(c.get("name")) in subdirs)
        if hits > best_hits:
            best, best_hits = t, hits
    return best, best_hits


# =========================
# GUI 部分（customtkinter，风格与 IntegrityCheckFrame 保持一致）
# =========================

class WordGeneratorFrame(ctk.CTkFrame):
    def __init__(self, master, status_cb=None, **kwargs):
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)
        self.status_cb = status_cb  # 向主窗口状态栏推送运行状态 (text, kind)

        # --- 数据初始化 ---
        self.log_queue = queue.Queue()
        self.parent_dir_var = ctk.StringVar()
        self.output_dir_var = ctk.StringVar()
        self.mother_var = ctk.StringVar()
        self.team_var = ctk.StringVar()
        self.date_var = ctk.StringVar()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # 日志区域占满剩余高度

        self.setup_ui()
        self.listen_to_queue()

    def setup_ui(self):
        # 1. 上部：生成参数卡片（固定高度；底部内嵌不确定模式进度条）
        form_card, form_body, _ = theme.make_card(self, title="生成参数")
        form_card.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        form_body.grid_columnconfigure(1, weight=1)

        self.progress = ctk.CTkProgressBar(form_body, mode="indeterminate", height=6)
        self.progress.set(0)
        self.progress.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.progress.grid_remove()   # 空闲时隐藏，开始生成时再显示

        pad_y = 7
        lbl_font = theme.f(13)
        entry_font = theme.f(13)
        btn_font = theme.f(12)

        # 输入目录
        ctk.CTkLabel(form_body, text="输入目录（子公司总文件夹）:", font=lbl_font).grid(row=0, column=0, padx=(0, 10), pady=pad_y, sticky="w")
        ctk.CTkEntry(form_body, textvariable=self.parent_dir_var, height=32, font=entry_font).grid(row=0, column=1, padx=5, pady=pad_y, sticky="ew")
        ctk.CTkButton(form_body, text="选择...", width=80, height=30, font=btn_font, command=self.select_parent_dir).grid(row=0, column=2, padx=(10, 0), pady=pad_y)

        # 输出目录
        ctk.CTkLabel(form_body, text="输出目录:", font=lbl_font).grid(row=1, column=0, padx=(0, 10), pady=pad_y, sticky="w")
        ctk.CTkEntry(form_body, textvariable=self.output_dir_var, height=32, font=entry_font).grid(row=1, column=1, padx=5, pady=pad_y, sticky="ew")
        ctk.CTkButton(form_body, text="选择...", width=80, height=30, font=btn_font, command=self.select_output_dir).grid(row=1, column=2, padx=(10, 0), pady=pad_y)

        # 母公司名称
        ctk.CTkLabel(form_body, text="母公司名称:", font=lbl_font).grid(row=2, column=0, padx=(0, 10), pady=pad_y, sticky="w")
        ctk.CTkEntry(form_body, textvariable=self.mother_var, height=32, font=entry_font).grid(row=2, column=1, padx=5, pady=pad_y, sticky="ew")

        # 项目组名称
        ctk.CTkLabel(form_body, text="项目组名称:", font=lbl_font).grid(row=3, column=0, padx=(0, 10), pady=pad_y, sticky="w")
        ctk.CTkEntry(form_body, textvariable=self.team_var, height=32, font=entry_font).grid(row=3, column=1, padx=5, pady=pad_y, sticky="ew")

        # 日期
        ctk.CTkLabel(form_body, text="日期:", font=lbl_font).grid(row=4, column=0, padx=(0, 10), pady=pad_y, sticky="w")
        ctk.CTkEntry(form_body, textvariable=self.date_var, height=32, font=entry_font,
                     placeholder_text="如：2026年8月11日").grid(row=4, column=1, padx=5, pady=pad_y, sticky="ew")

        # 编号映射（可选）：命中的公司 docx 文件名加 `{编号} ` 前缀，输出目录不变
        ctk.CTkLabel(form_body, text="编号映射\n(可选):", font=theme.f(12),
                     text_color=theme.MUTED, justify="left").grid(
            row=5, column=0, padx=(0, 10), pady=(8, pad_y), sticky="nw")
        self.code_map_box = ctk.CTkTextbox(form_body, height=76,
                                           font=theme.f(12, mono=True), wrap="none")
        self.code_map_box.grid(row=5, column=1, padx=5, pady=(8, pad_y), sticky="ew")
        ctk.CTkButton(form_body, text="从模板导入", width=90, height=30, font=btn_font,
                      command=self.import_code_map_from_template).grid(
            row=5, column=2, padx=(10, 0), pady=(8, pad_y), sticky="ne")

        # 开始按钮
        self.run_btn = ctk.CTkButton(
            form_body,
            text="▶ 开始生成",
            fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
            height=38,
            font=theme.f(14, bold=True),
            command=self.start_generate,
        )
        self.run_btn.grid(row=6, column=0, columnspan=3, pady=(14, 2))

        # 2. 下部：运行日志卡片（占满剩余高度）
        log_card, log_body, log_head = theme.make_card(self, title="运行日志")
        log_card.grid(row=1, column=0, padx=16, pady=(8, 16), sticky="nsew")
        clear_btn = ctk.CTkButton(
            log_head, text="清空", width=56, height=22,
            font=theme.f(11), fg_color=theme.SUBTLE_BTN, hover_color=theme.SUBTLE_HOVER,
            text_color=("gray25", "#cfcfd8"), command=self.clear_log,
        )
        clear_btn.pack(side="right")
        log_body.grid_columnconfigure(0, weight=1)
        log_body.grid_rowconfigure(0, weight=1)

        self.log_textbox = ctk.CTkTextbox(log_body, font=theme.f(12, mono=True), wrap="word")
        self.log_textbox.grid(row=0, column=0, sticky="nsew")
        theme.setup_log_tags(self.log_textbox)
        self.log_textbox.configure(state="disabled")

    def select_parent_dir(self):
        folder = filedialog.askdirectory(title="请选择输入目录")
        if folder:
            self.parent_dir_var.set(folder)

    def select_output_dir(self):
        folder = filedialog.askdirectory(title="请选择输出目录")
        if folder:
            self.output_dir_var.set(folder)

    def import_code_map_from_template(self):
        """从模板库自动匹配与输入目录子文件夹命中最多的模板，预填编号映射。"""
        parent = self.parent_dir_var.get().strip()
        if not parent or not os.path.isdir(parent):
            self.write_log(">>> [错误] 请先选择有效的输入目录，再导入模板映射。\n")
            return
        best, hits = best_template_for(parent)
        if not best:
            self.write_log(">>> [提示] 模板库为空，或没有任何模板的公司与输入目录子文件夹匹配。\n")
            return
        lines = []
        for c in (best.get("companies") or []):
            raw = str(c.get("raw") or "").strip()
            if not raw:
                continue
            code = str(c.get("code") or "").strip()
            lines.append(f"{code} {raw}".strip())
        self.code_map_box.delete("1.0", "end")
        self.code_map_box.insert("1.0", "\n".join(lines))
        total = len(best.get("companies") or [])
        self.write_log(f">>> [成功] 已导入模板「{best.get('name')}」"
                       f"（{total} 行，其中 {hits} 家公司与当前输入目录匹配）。\n")

    def start_generate(self):
        parent_dir = self.parent_dir_var.get().strip()
        output_dir = self.output_dir_var.get().strip()
        mother_company_name = self.mother_var.get().strip()
        project_team_name = self.team_var.get().strip()
        report_date = self.date_var.get().strip()

        if not parent_dir:
            self.write_log(">>> [错误] 请选择输入目录。\n")
            return
        if not output_dir:
            self.write_log(">>> [错误] 请选择输出目录。\n")
            return
        if not mother_company_name:
            self.write_log(">>> [错误] 请输入母公司名称。\n")
            return
        if not project_team_name:
            self.write_log(">>> [错误] 请输入项目组名称。\n")
            return
        if not report_date:
            self.write_log(">>> [错误] 请输入日期。\n")
            return

        self.run_btn.configure(state="disabled", text="正在生成...")
        self.progress.grid()
        self.progress.start()
        if self.status_cb:
            self.status_cb("正在生成…", "run")

        code_map = parse_code_map(self.code_map_box.get("1.0", "end"))
        if code_map:
            self.write_log(f">>> [提示] 已载入编号映射 {len(code_map)} 条，"
                           f"命中的公司文件名将加「{''}编号 」前缀。\n")

        thread = threading.Thread(
            target=self._run_batch_task,
            args=(parent_dir, output_dir, mother_company_name, project_team_name,
                  report_date, code_map),
            daemon=True,
        )
        thread.start()

    def _run_batch_task(self, parent_dir, output_dir, mother, team, date, code_map=None):
        """后台线程执行批量生成，日志通过队列回传主线程。"""
        try:
            batch_process_companies(
                parent_dir=parent_dir,
                output_dir=output_dir,
                mother_company_name=mother,
                project_team_name=team,
                report_date=date,
                log=lambda msg: self.log_queue.put(str(msg) + "\n"),
                code_map=code_map,
            )
        except Exception as e:
            self.log_queue.put(f">>> [错误] 运行失败：{e}\n")
        finally:
            self.log_queue.put("DONE")

    def listen_to_queue(self):
        """保持常驻的日志监听循环。"""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if msg == "DONE":
                    self.run_btn.configure(state="normal", text="▶ 开始生成")
                    self.progress.stop()
                    self.progress.set(0)
                    self.progress.grid_remove()
                    if self.status_cb:
                        self.status_cb("就绪", "idle")
                    self.write_log(">>> [系统] 任务全部完成，已可开始新任务。\n")
                else:
                    self.write_log(msg)
        except queue.Empty:
            pass
        self.after(100, self.listen_to_queue)

    def write_log(self, text):
        theme.append_log(self.log_textbox, text)

    def clear_log(self):
        theme.clear_logbox(self.log_textbox)
