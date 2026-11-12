# 文件路径: views/djg_ui.py
# 董监高核查独立页：
#   卡片A 一键切换主界面至「董监高诚信核查」预设
#   卡片B 截图整理（每人一夹 → 每站一夹 的转置，移植自 高管查询结果整理.ipynb）
#   卡片C 汇总文档（《项目组关于董监高人员诚信信息的核查说明》，首页空白留手工撰写）
# 纯逻辑函数位于模块顶部（reorganize_screenshots / build_summary_docx），可脱离 GUI 测试。

import threading
import queue
from pathlib import Path

import customtkinter as ctk

from views import theme
from views.theme import ToolTip
from views.word_generator_ui import add_image_paragraph, add_text_paragraph, natural_sort_key

IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
DEFAULT_DOCX_NAME = "项目组关于董监高人员诚信信息的核查说明"


# ============================ 纯逻辑：截图转置 ============================

def reorganize_screenshots(source_dir, output_dir, move=False):
    """把 <高管名>/<站点截图> 层级转置为 <站点>/<高管名.ext>。

    - 一级图片：`王五/3、证监会….png` → `<输出>/3、证监会…/王五.png`
    - 二级文件夹：`张三/7、法律文书网/*.png` → `<输出>/7、法律文书网/原文件名`
      （二级文件名通常自带时间戳，直接平移；若重命名后同名冲突则跳过并记 warning）
    - 默认 copy 不动源文件；move=True 时改为移动。
    返回统计 dict：persons / level1 / level2 / skipped / warnings。
    """
    src = Path(source_dir)
    out = Path(output_dir)
    if not src.is_dir():
        raise ValueError(f"输入目录不存在或不是文件夹：{source_dir}")
    out.mkdir(parents=True, exist_ok=True)

    transfer = (lambda s, d: Path(s).replace(d)) if move else _copy2_safe
    stats = {"persons": 0, "level1": 0, "level2": 0, "skipped": 0, "warnings": []}

    for exec_folder in sorted(src.iterdir(), key=lambda p: natural_sort_key(p.name)):
        if not exec_folder.is_dir():
            continue
        exec_name = exec_folder.name
        stats["persons"] += 1

        for item in exec_folder.iterdir():
            if item.is_file() and item.suffix.lower() in IMG_EXTS:
                target_dir = out / item.stem
                target_dir.mkdir(parents=True, exist_ok=True)
                dest = target_dir / f"{exec_name}{item.suffix.lower()}"
                if dest.exists():
                    stats["skipped"] += 1
                    stats["warnings"].append(f"同名跳过：{dest.name} 已存在于 {target_dir.name}/")
                    continue
                transfer(item, dest)
                stats["level1"] += 1
            elif item.is_dir():
                for sub_item in item.iterdir():
                    if sub_item.is_file() and sub_item.suffix.lower() in IMG_EXTS:
                        target_dir = out / item.name
                        target_dir.mkdir(parents=True, exist_ok=True)
                        dest = target_dir / sub_item.name
                        if dest.exists():
                            stats["skipped"] += 1
                            stats["warnings"].append(
                                f"同名跳过：{item.name}/{sub_item.name}")
                            continue
                        transfer(sub_item, dest)
                        stats["level2"] += 1
    return stats


def _copy2_safe(src_path, dst_path):
    import shutil
    shutil.copy2(str(src_path), str(dst_path))


# ============================ 纯逻辑：汇总 docx ============================

def build_summary_docx(source_dir, output_docx, include_site_titles=True):
    """生成单一汇总 docx：首页空白（供手工添加说明文字），之后按站点顺序插入全部截图。

    - 站点夹按名称自然排序（default_3 命名天然形成 1-4 序）；
    - 开启标题行时每个站点组前插入文本段（站点文件夹名，宋体小四左对齐）；
    - 组内图片按自然排序插入（居中、宽 5.5 英寸）；
    - 空站点夹计入 warnings 不中断。
    返回统计 dict：sites / images / empty_sites / warnings。
    """
    from docx import Document

    src = Path(source_dir)
    if not src.is_dir():
        raise ValueError(f"来源目录不存在或不是文件夹：{source_dir}")

    doc = Document()
    add_text_paragraph(doc, "")          # 首页保持空白，方便用户自行添加说明文字
    doc.add_page_break()

    site_dirs = sorted((d for d in src.iterdir() if d.is_dir()),
                       key=lambda p: natural_sort_key(p.name))
    if not site_dirs:
        raise ValueError("来源目录下没有任何站点子文件夹，请先执行「截图整理」。")

    stats = {"sites": 0, "images": 0, "empty_sites": [], "warnings": []}
    for site_dir in site_dirs:
        images = sorted((f for f in site_dir.iterdir()
                         if f.is_file() and f.suffix.lower() in IMG_EXTS),
                        key=lambda p: natural_sort_key(p.name))
        stats["sites"] += 1
        if include_site_titles:
            add_text_paragraph(doc, site_dir.name)
        if not images:
            stats["empty_sites"].append(site_dir.name)
            stats["warnings"].append(f"站点夹为空：{site_dir.name}")
            continue
        for img in images:
            add_image_paragraph(doc, str(img))
            stats["images"] += 1

    output_docx = str(output_docx)
    if not output_docx.lower().endswith(".docx"):
        output_docx += ".docx"
    doc.save(output_docx)
    stats["output"] = output_docx
    return stats


# ============================ 页面 UI ============================

class DjgFrame(ctk.CTkFrame):
    def __init__(self, master, status_cb=None, go_preset_cb=None, **kwargs):
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)
        self.status_cb = status_cb      # 主窗口状态栏 (text, kind)
        self.go_preset_cb = go_preset_cb  # 切换主界面预设并跳转截图页
        self.log_queue = queue.Queue()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_ui()
        self.listen_to_queue()

    # ---------------------------- 界面 ----------------------------
    def setup_ui(self):
        # 整页可滚动：小窗口 / 高 DPI 缩放下内容超高时仍可完整操作
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")

        # 卡片A：准备截图
        card_a, body_a, _ = theme.make_card(scroll, title="第一步 · 准备截图")
        card_a.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            body_a,
            text="使用「董监高诚信核查」方案对每位人员完成四站截图"
                 "（证监会平台 / 失信名单 / 法律文书网 / 百度媒体）。\n"
                 "对象请输入自然人：姓名 身份证号。",
            font=theme.f(12), text_color=theme.MUTED, justify="left", anchor="w",
        ).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(
            body_a, text="切换至董监高模板并前往截图 ▶", height=34,
            font=theme.f(13, bold=True),
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self._go_preset,
        ).pack(fill="x")

        # 卡片B：截图整理（转置）
        card_b, body_b, _ = theme.make_card(scroll, title="第二步 · 截图整理（每人一夹 → 每站一夹）")
        card_b.pack(fill="x", pady=(0, 12))
        body_b.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(body_b, text="输入目录:", font=theme.f(13)).grid(
            row=0, column=0, padx=(0, 10), pady=6, sticky="w")
        self.src_entry = ctk.CTkEntry(body_b, height=32, font=theme.f(12),
                                      placeholder_text="选择包含各高管文件夹的目录…")
        self.src_entry.grid(row=0, column=1, padx=5, pady=6, sticky="ew")
        ctk.CTkButton(body_b, text="选择...", width=80, height=30, font=theme.f(12),
                      command=self.select_src).grid(row=0, column=2, padx=(10, 0), pady=6)

        ctk.CTkLabel(body_b, text="输出目录:", font=theme.f(13)).grid(
            row=1, column=0, padx=(0, 10), pady=6, sticky="w")
        self.dst_entry = ctk.CTkEntry(body_b, height=32, font=theme.f(12),
                                      placeholder_text="整理结果将按站点分夹输出（复制模式，不改动源文件）")
        self.dst_entry.grid(row=1, column=1, padx=5, pady=6, sticky="ew")
        ctk.CTkButton(body_b, text="选择...", width=80, height=30, font=theme.f(12),
                      command=self.select_dst).grid(row=1, column=2, padx=(10, 0), pady=6)

        self.move_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(body_b, text="移动而非复制（慎选）", variable=self.move_var,
                      onvalue=True, offvalue=False, font=theme.f(12),
                      progress_color=theme.ACCENT).grid(
            row=2, column=1, sticky="w", pady=(2, 4))

        self.reorg_btn = ctk.CTkButton(
            body_b, text="开始整理", width=120, height=32, font=theme.f(12, bold=True),
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self.start_reorganize,
        )
        self.reorg_btn.grid(row=2, column=2, padx=(10, 0), pady=4, sticky="e")

        # 卡片C：汇总文档
        card_c, body_c, _ = theme.make_card(scroll, title="第三步 · 生成汇总文档")
        card_c.pack(fill="x", pady=(0, 12))
        body_c.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(body_c, text="来源目录:", font=theme.f(13)).grid(
            row=0, column=0, padx=(0, 10), pady=6, sticky="w")
        self.doc_src_entry = ctk.CTkEntry(body_c, height=32, font=theme.f(12),
                                          placeholder_text="默认使用第二步的输出目录")
        self.doc_src_entry.grid(row=0, column=1, padx=5, pady=6, sticky="ew")
        ctk.CTkButton(body_c, text="选择...", width=80, height=30, font=theme.f(12),
                      command=self.select_doc_src).grid(row=0, column=2, padx=(10, 0), pady=6)

        ctk.CTkLabel(body_c, text="保存位置:", font=theme.f(13)).grid(
            row=1, column=0, padx=(0, 10), pady=6, sticky="w")
        self.doc_out_entry = ctk.CTkEntry(body_c, height=32, font=theme.f(12),
                                          placeholder_text=f"输出文件路径，默认文件名《{DEFAULT_DOCX_NAME}.docx》")
        self.doc_out_entry.grid(row=1, column=1, padx=5, pady=6, sticky="ew")
        ctk.CTkButton(body_c, text="选择...", width=80, height=30, font=theme.f(12),
                      command=self.select_doc_out).grid(row=1, column=2, padx=(10, 0), pady=6)

        row_opt = ctk.CTkFrame(body_c, fg_color="transparent")
        row_opt.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.titles_var = ctk.BooleanVar(value=True)   # 站点标题行默认开启，可关
        titles_switch = ctk.CTkSwitch(row_opt, text="插入站点标题行", variable=self.titles_var,
                                      onvalue=True, offvalue=False, font=theme.f(12),
                                      progress_color=theme.ACCENT)
        titles_switch.pack(side="left")
        ToolTip(titles_switch,
                "开启时每个站点组前插入文本行（如「1、中国证监会证券期货市场失信记录查询平台」）；\n"
                "关闭则为纯图片流。首页始终空白，供您手工添加说明文字。")

        self.doc_btn = ctk.CTkButton(
            row_opt, text="生成汇总文档 ▶", width=140, height=32,
            font=theme.f(12, bold=True),
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self.start_build_docx,
        )
        self.doc_btn.pack(side="right")

        # 日志卡片
        log_card, log_body, log_head = theme.make_card(scroll, title="运行日志")
        log_card.pack(fill="x")
        clear_btn = ctk.CTkButton(
            log_head, text="清空", width=56, height=22,
            font=theme.f(11), fg_color=theme.SUBTLE_BTN, hover_color=theme.SUBTLE_HOVER,
            text_color=("gray25", "#cfcfd8"), command=self.clear_log,
        )
        clear_btn.pack(side="right")
        self.log_textbox = ctk.CTkTextbox(log_body, height=130,
                                          font=theme.f(12, mono=True), wrap="word")
        self.log_textbox.pack(fill="both", expand=True)
        theme.setup_log_tags(self.log_textbox)
        self.log_textbox.configure(state="disabled")

    # ---------------------------- 选择器 ----------------------------
    def select_src(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="选择各高管文件夹所在目录")
        if folder:
            self.src_entry.delete(0, "end")
            self.src_entry.insert(0, folder)

    def select_dst(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="选择整理输出目录")
        if folder:
            self.dst_entry.delete(0, "end")
            self.dst_entry.insert(0, folder)

    def select_doc_src(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="选择站点夹所在的来源目录")
        if folder:
            self.doc_src_entry.delete(0, "end")
            self.doc_src_entry.insert(0, folder)

    def select_doc_out(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="选择汇总文档保存位置", defaultextension=".docx",
            initialfile=f"{DEFAULT_DOCX_NAME}.docx",
            filetypes=[("Word 文档", "*.docx")],
        )
        if path:
            self.doc_out_entry.delete(0, "end")
            self.doc_out_entry.insert(0, path)

    # ---------------------------- 动作 ----------------------------
    def _go_preset(self):
        if self.go_preset_cb:
            self.go_preset_cb()

    def start_reorganize(self):
        src = self.src_entry.get().strip()
        dst = self.dst_entry.get().strip()
        if not src:
            self.write_log(">>> [错误] 请选择输入目录。\n")
            return
        if not dst:
            self.write_log(">>> [错误] 请选择输出目录。\n")
            return
        move = bool(self.move_var.get())
        self._run_async(f"正在整理截图{'（移动模式）' if move else ''}…",
                        self._do_reorganize, src, dst, move)

    def _do_reorganize(self, src, dst, move):
        try:
            stats = reorganize_screenshots(src, dst, move=move)
        except Exception as exc:
            self.log_queue.put(f">>> [错误] 整理失败：{exc}\n")
            return
        verb = "移动" if move else "复制"
        self.log_queue.put(
            f"整理完成：{stats['persons']} 人 | 一级图片{verb} {stats['level1']} 张 | "
            f"二级归档 {stats['level2']} 张 | 跳过 {stats['skipped']}\n"
        )
        for w in stats["warnings"][:20]:
            self.log_queue.put(f">>> [提示] {w}\n")
        if len(stats["warnings"]) > 20:
            self.log_queue.put(f">>> [提示] 其余 {len(stats['warnings']) - 20} 条警告省略\n")
        if not self.doc_src_entry.get().strip():
            self.doc_src_entry.insert(0, dst)
        self.log_queue.put(">>> [成功] 整理完成，可直接进行第三步生成汇总文档。\n")

    def start_build_docx(self):
        src = self.doc_src_entry.get().strip() or self.dst_entry.get().strip()
        out = self.doc_out_entry.get().strip()
        if not src:
            self.write_log(">>> [错误] 请先执行第二步整理，或手动选择来源目录。\n")
            return
        if not out:
            self.write_log(">>> [错误] 请选择汇总文档保存位置。\n")
            return
        self._run_async("正在生成汇总文档…",
                        self._do_build_docx, src, out, bool(self.titles_var.get()))

    def _do_build_docx(self, src, out, with_titles):
        try:
            stats = build_summary_docx(src, out, include_site_titles=with_titles)
        except Exception as exc:
            self.log_queue.put(f">>> [错误] 生成失败：{exc}\n")
            return
        self.log_queue.put(
            f">>> [成功] 生成成功 -> {stats['output']}\n"
            f"共 {stats['sites']} 个站点 / {stats['images']} 张截图"
        )
        if stats["empty_sites"]:
            self.log_queue.put(
                f">>> [提示] 以下站点夹为空，未插图：" + "、".join(stats["empty_sites"]) + "\n")

    # ---------------------------- 异步骨架 ----------------------------
    def _run_async(self, running_text, fn, *args):
        self.reorg_btn.configure(state="disabled")
        self.doc_btn.configure(state="disabled")
        if self.status_cb:
            self.status_cb(running_text, "run")
        thread = threading.Thread(target=self._worker, args=(fn, args), daemon=True)
        thread.start()

    def _worker(self, fn, args):
        try:
            fn(*args)
        finally:
            self.log_queue.put("DONE")

    def listen_to_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if msg == "DONE":
                    self.reorg_btn.configure(state="normal")
                    self.doc_btn.configure(state="normal")
                    if self.status_cb:
                        self.status_cb("就绪", "idle")
                else:
                    self.write_log(msg)
        except queue.Empty:
            pass
        self.after(100, self.listen_to_queue)

    # ---------------------------- 日志 ----------------------------
    def write_log(self, text):
        theme.append_log(self.log_textbox, text)

    def clear_log(self):
        theme.clear_logbox(self.log_textbox)
