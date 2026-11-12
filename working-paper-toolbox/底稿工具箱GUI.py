# -*- coding: utf-8 -*-
"""底稿工具箱GUI.py —— 债承底稿处理工具箱（图形界面）

整合 5 个功能模块：
  ① 签章页工具        签章页工具/pdf_toolkit.py     format/header/export/filter/insert
  ② 替换底稿内容      替换底稿内容/replace_toolkit.py  short/long
  ③ 比较文件夹内容    比较文件夹内容/folder_toolbox.py compare/merge/extract
  ④ 底稿PDF材料整理   底稿pdf材料/file_toolkit.py   组A/B/C 共 8 个子命令
  ⑤ 多级文件夹生成目录 多级文件夹生成目录/输出文件目录.py Excel+Word 目录

运行方式：
    python 底稿工具箱GUI.py

实现说明：
  - 各任务在独立子进程中运行（配置型模块经 gui_runner.py 中转覆写 config），
    GUI 主进程通过后台线程读取子进程输出，界面不卡顿；
  - 所有输入框的值自动记忆到 .zcode/gui_settings.json，下次启动恢复；
  - 不改动任何原有模块代码。
"""

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# 打包(exe)模式下：BASE_DIR = exe 所在目录（放设置/日志），
# RES_DIR = PyInstaller 解包资源目录（放 gui_runner.py 等数据文件）。
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = BASE_DIR
RUNNER = os.path.join(RES_DIR, "gui_runner.py")
SETTINGS_PATH = os.path.join(BASE_DIR, ".zcode", "gui_settings.json")

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _res(*parts):
    """定位随包分发的资源文件（打包后位于 _MEIPASS，源码运行时位于脚本目录）。"""
    return os.path.join(RES_DIR, *parts)


def _default(*parts):
    return os.path.normpath(os.path.join(BASE_DIR, *parts))


# =====================================================================
# 主应用
# =====================================================================
class ToolBoxApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("债承底稿处理工具箱")
        # 窗口尺寸随屏幕分辨率自适应（高分屏/150% 缩放笔记本不截断）
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = min(1240, max(1000, int(sw * 0.82)))
        h = max(640, int(sh * 0.86))
        self.root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        self.root.minsize(860, 560)

        self.vars = {}            # key -> tk 变量
        self.run_buttons = []     # 所有会触发任务的按钮
        self._busy = False
        self._proc = None
        self._queue = queue.Queue()

        self._build_ui()
        self._load_settings()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(80, self._poll_queue)

    # ------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------
    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Big.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=6)
        style.configure("Run.TButton", padding=4)
        style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))

        # ---- 主体：上（功能页签）/ 下（运行日志）可拖动分隔 ----
        paned = ttk.PanedWindow(self.root, orient="vertical")
        paned.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        page = ttk.Frame(paned)
        paned.add(page, weight=3)
        notebook = ttk.Notebook(page)
        notebook.pack(fill="both", expand=True)
        self._tab_sign(notebook)
        self._tab_replace(notebook)
        self._tab_folder(notebook)
        self._tab_extract(notebook)
        self._tab_filetoolkit(notebook)
        self._tab_dirgen(notebook)

        # ---- 日志区 ----
        log_frame = ttk.LabelFrame(paned, text="运行日志")
        paned.add(log_frame, weight=2)
        self.log_text = tk.Text(log_frame, wrap="none", height=12, state="disabled",
                                font=("Consolas", 9))
        ysb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        xsb = ttk.Scrollbar(log_frame, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text.tag_configure("info", foreground="#333333")
        self.log_text.tag_configure("ok", foreground="#106b21")
        self.log_text.tag_configure("err", foreground="#c0392b")
        self.log_text.tag_configure("head", foreground="#1a5276",
                                    font=("Consolas", 9, "bold"))

        btn_bar = ttk.Frame(self.root)
        btn_bar.pack(fill="x", padx=8, pady=(0, 2))
        ttk.Button(btn_bar, text="清空日志", command=self._clear_log).pack(side="left")
        ttk.Button(btn_bar, text="打开底稿处理工具目录",
                   command=lambda: os.startfile(BASE_DIR)).pack(side="left", padx=6)

        self.status_var = tk.StringVar(value="就绪")
        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w",
                           relief="sunken", padding=(6, 3))
        status.pack(fill="x", side="bottom")

    # ---------- 小部件辅助 ----------
    def _var(self, key, default="", kind="str"):
        if key not in self.vars:
            if kind == "bool":
                self.vars[key] = tk.BooleanVar(value=default)
            elif kind == "int":
                self.vars[key] = tk.StringVar(value=str(default))
            else:
                self.vars[key] = tk.StringVar(value=default)
        return self.vars[key]

    def _row_path(self, parent, row, label, key, default="", must_exist=False,
                  is_file=False):
        """路径选择行：标签 + 输入框 + 浏览按钮。返回下一行号。"""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=4, pady=3)
        entry = ttk.Entry(parent, textvariable=self._var(key, default), width=72)
        entry.grid(row=row, column=1, sticky="we", padx=4, pady=3)

        def browse():
            path = self.vars[key].get().strip()
            if is_file:
                initdir = os.path.dirname(path) if path else BASE_DIR
                chosen = filedialog.askopenfilename(initialdir=initdir or BASE_DIR,
                                                    parent=self.root)
            else:
                chosen = filedialog.askdirectory(initialdir=path or BASE_DIR,
                                                 parent=self.root)
            if chosen:
                self.vars[key].set(os.path.normpath(chosen))

        btn = ttk.Button(parent, text="浏览…", width=8, command=browse)
        btn.grid(row=row, column=2, padx=(0, 4), pady=3)
        parent.columnconfigure(1, weight=1)
        return row + 1

    def _run_btn(self, parent, text, command, **geom):
        btn = ttk.Button(parent, text=text, command=command, style="Run.TButton")
        if "row" in geom:  # grid 布局参数
            btn.grid(**geom)
        else:
            btn.pack(**geom)
        self.run_buttons.append(btn)
        return btn

    # ============================================================
    # Tab 1：签章页工具
    # ============================================================
    def _new_tab(self, nb, title):
        """带纵向滚动条的页签容器。

        高 DPI 缩放或窗口较矮时内容超出可视区可滚动查看，不再截断；
        鼠标悬停页签时滚轮即滚动内容。
        返回真正放置控件的内部 frame。
        """
        outer = ttk.Frame(nb)
        nb.add(outer, text=title)
        canvas = tk.Canvas(outer, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas, padding=10)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda _e: canvas.itemconfigure(win, width=canvas.winfo_width()))

        def _on_wheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        return inner

    def _tab_sign(self, nb):
        tab = self._new_tab(nb, " 签章页工具 ")
        self._row_path(tab, 0, "项目根目录", "sign.root",
                       _default("比较文件夹内容", "new"))
        ttk.Label(tab, text="项目标识").grid(row=1, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(tab, textvariable=self._var("sign.tag", "示例"), width=24)\
            .grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(tab, text="公司关键字").grid(row=2, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(tab, textvariable=self._var(
            "sign.keyword", "示例市示范区城市资产经营有限公司"), width=72)\
            .grid(row=2, column=1, sticky="we", padx=4)

        opt = ttk.Frame(tab)
        opt.grid(row=3, column=0, columnspan=3, sticky="we", pady=6)
        ttk.Checkbutton(opt, text="页眉只检查不修改 (dry-run)",
                        variable=self._var("sign.dry_run", False, "bool"))\
            .pack(side="left", padx=(0, 14))
        for label, key, dft in (("format 仅处理最近N天", "sign.update_days", 100),
                                ("export PDF复用天数(0关闭)", "sign.pdf_reuse_days", 1)):
            box = ttk.Frame(opt)
            box.pack(side="left", padx=(0, 14))
            ttk.Label(box, text=label).pack(side="left")
            ttk.Spinbox(box, from_=0, to=9999, width=6,
                        textvariable=self._var(key, dft, "int")).pack(side="left", padx=4)

        btns = ttk.LabelFrame(tab, text="执行（标准流程 ①→⑥）", padding=8)
        btns.grid(row=4, column=0, columnspan=3, sticky="we")
        steps = [
            ("① 刷新docx格式", ("format",)),
            ("② 页眉修复", ("header",)),
            ("③ 导出PDF拆签章页", ("export",)),
            ("④ 过滤索引清单", ("filter",)),
            ("⑤ 追加签章页", ("insert_append",)),
            ("⑥ 替换签字页", ("insert_replace",)),
        ]
        for i, (text, (cmd,)) in enumerate(steps):
            self._run_btn(btns, text,
                          lambda c=cmd: self._run_sign(c),
                          row=i // 3, column=i % 3, padx=5, pady=4, sticky="we")
        ttk.Label(btns, foreground="#666",
                  text="注意：③ 不要重复跑——拆过末页的 PDF 复用会把 has_company 清单冲空；"
                       "需重导请先把该 PDF 删掉或把复用天数设为 0。")\
            .grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        # ---- ④-⑥ 手动路径 ----
        adv = ttk.LabelFrame(tab, text="④-⑥ 手动路径（留空则沿用上方项目根目录与默认文件名）",
                             padding=8)
        adv.grid(row=5, column=0, columnspan=3, sticky="we", pady=(10, 0))
        r = self._row_path(adv, 0, "项目根目录（⑤追加/⑥替换）", "sign.steps_root", "")
        r = self._row_path(adv, r, "JSON 清单（④ 过滤输入）", "sign.filter_json",
                           "", is_file=True)
        r = self._row_path(adv, r, "JSON 清单（⑤ 追加用）", "sign.append_json",
                           "", is_file=True)
        r = self._row_path(adv, r, "签章页.pdf（⑤ 追加用）", "sign.append_pdf",
                           "", is_file=True)
        r = self._row_path(adv, r, "无索引清单.log（⑥ 替换用）", "sign.replace_list",
                           "", is_file=True)
        r = self._row_path(adv, r, "签字合并.pdf（⑥ 替换用）", "sign.replace_pdf",
                           "", is_file=True)
        ttk.Label(adv, foreground="#666",
                  text="说明：「项目根目录」仅对 ⑤/⑥ 生效（④ 过滤只读取 JSON 清单，不扫描目录），"
                       "留空时 ⑤/⑥ 沿用上方标准流程的项目根目录。"
                       "⑤ 与 ⑥ 用的是两组不同文件——签章页.pdf 由 ③ 导出生成"
                       "（配 has_company JSON 清单），签字合并.pdf 为已签字页合并稿"
                       "（配无索引 log 清单）。清单/PDF 留空时自动取上述根目录下的"
                       " logs\\has_company_latest.json、logs\\no_company_无索引_latest.log"
                       " 及根目录下的签章页.pdf / 签字合并.pdf；④ 的 JSON 留空自动找"
                       " logs\\no_company_latest.json。")\
            .grid(row=r, column=0, columnspan=3, sticky="w")

        # ---- 初始化底稿文件 ----
        init = ttk.LabelFrame(tab, text="初始化底稿文件（字体/行距刷新 + 末尾处理 + 汇总签章页）",
                              padding=8)
        init.grid(row=6, column=0, columnspan=3, sticky="we", pady=(10, 0))
        r = self._row_path(init, 0, "待处理 Word 文件夹", "init.root", "")
        ttk.Label(init, text="发行人").grid(row=r, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(init, textvariable=self._var("init.issuer",
                                               "示例市示范区城市资产经营有限公司"), width=72)\
            .grid(row=r, column=1, columnspan=2, sticky="we", padx=4)
        r += 1
        for label, key, dft in (("项目组", "init.team", "示例项目组"),
                                ("落款日期", "init.date", "2026年6月   日"),
                                ("汇总签章页文件名", "init.sign_name", "全部签章页.docx")):
            ttk.Label(init, text=label).grid(row=r, column=0, sticky="e", padx=4, pady=3)
            ttk.Entry(init, textvariable=self._var(key, dft), width=40)\
                .grid(row=r, column=1, sticky="w", padx=4)
            r += 1
        self._run_btn(init, "初始化底稿文件（原地修改！）",
                      lambda: self._run_init(), row=r, column=1, sticky="w", pady=4)
        ttk.Label(init, foreground="#666",
                  text="说明：统一字体与 1.5 倍行距、删除文末图片；末尾含「项目组」的文件"
                       "改写为项目组+日期落款，否则追加独立签章页并汇总到汇总签章页文档。")\
            .grid(row=r + 1, column=0, columnspan=3, sticky="w", pady=(2, 0))

    # ============================================================
    # Tab 2：替换底稿内容
    # ============================================================
    def _tab_replace(self, nb):
        tab = self._new_tab(nb, " 替换底稿内容 ")
        row = self._row_path(tab, 0, "替换规则表.xlsx", "rep.rules",
                             _default("替换规则表.xlsx"), is_file=True)
        row = self._row_path(tab, row, "docx 根目录", "rep.source",
                             _default("比较文件夹内容", "new"))

        gen_f = ttk.LabelFrame(tab, text="生成替换表模板（三张表：填写说明/短替换/长替换）", padding=8)
        gen_f.grid(row=row, column=0, columnspan=3, sticky="we", pady=4)
        r = self._row_path(gen_f, 0, "规则表输出路径", "rep.rules_out",
                           _default("替换规则表.xlsx"), is_file=False)
        self._run_btn(gen_f, "生成替换表模板", lambda: self._run_make_rules(),
                      row=r, column=1, sticky="w", pady=4)
        ttk.Label(gen_f, foreground="#666",
                  text="说明：已存在同名文件时不会覆盖，请先改名或删除；"
                       "生成后按「填写说明」表填好，再回到上方运行短/长替换。")\
            .grid(row=r + 1, column=0, columnspan=3, sticky="w")

        short_f = ttk.LabelFrame(tab, text="short —— 词对/正则替换（python-docx，快）", padding=8)
        short_f.grid(row=row + 1, column=0, columnspan=3, sticky="we", pady=4)
        r = self._row_path(short_f, 0, "输出目录（空=原地替换）", "rep.final", "")
        self._run_btn(short_f, "运行短替换", lambda: self._run_replace("short"),
                      row=r, column=1, sticky="w", pady=4)

        long_f = ttk.LabelFrame(tab, text="long —— 区间替换+插入素材（Word COM，保格式）", padding=8)
        long_f.grid(row=row + 2, column=0, columnspan=3, sticky="we", pady=4)
        r = self._row_path(long_f, 0, "素材 docx 文件夹", "rep.insert_dir",
                           _default("替换底稿内容", "素材"))
        box = ttk.Frame(long_f)
        box.grid(row=r, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Checkbutton(box, text="覆盖原文件（不勾选则另存到下方输出目录）",
                        variable=self._var("rep.overwrite", True, "bool"))\
            .pack(side="left")
        r += 1
        r = self._row_path(long_f, r, "另存输出目录", "rep.output_dir",
                           _default("替换底稿内容", "替换结果"))
        self._run_btn(long_f, "运行长替换（需本机 Word）",
                      lambda: self._run_replace("long"),
                      row=r, column=1, sticky="w", pady=4)

    # ============================================================
    # Tab 3：比较文件夹内容
    # ============================================================
    def _tab_folder(self, nb):
        tab = self._new_tab(nb, " 比较文件夹内容 ")
        mod = os.path.join(BASE_DIR, "比较文件夹内容")
        row = self._row_path(tab, 0, "old 文件夹", "cmp.old", os.path.join(mod, "old"))
        row = self._row_path(tab, row, "new 文件夹", "cmp.new", os.path.join(mod, "new"))
        btns = ttk.Frame(tab)
        btns.grid(row=row, column=0, columnspan=3, sticky="w", pady=6)
        self._run_btn(btns, "比较差异（SHA-256）",
                      lambda: self._run_cli("比较文件夹内容", "folder_toolbox.py",
                                            ["compare", self.vars["cmp.old"].get(),
                                             self.vars["cmp.new"].get()]), padx=5)
        self._run_btn(btns, "合并（new 覆盖 old，不备份！）",
                      lambda: self._confirm_then(
                          "将用 new 中的同名 docx 直接覆盖 old（不备份），确定继续？",
                          lambda: self._run_cli("比较文件夹内容", "folder_toolbox.py",
                                                ["merge", self.vars["cmp.old"].get(),
                                                 self.vars["cmp.new"].get()])), padx=5)
        ttk.Label(tab, foreground="#666",
                  text="说明：提取打印文件 / 提取非Word文件 / 文件信息统计已移至「文件提取与统计」页签。")\
            .grid(row=row + 1, column=0, columnspan=3, sticky="w", pady=6)

    # ============================================================
    # Tab 3.5：文件提取与统计
    # ============================================================
    def _tab_extract(self, nb):
        tab = self._new_tab(nb, " 文件提取与统计 ")
        mod = os.path.join(BASE_DIR, "比较文件夹内容")

        # ---- 提取打印文件 ----
        ext = ttk.LabelFrame(tab, text="提取打印文件（平铺 doc/docx 到一个文件夹）", padding=8)
        ext.grid(row=0, column=0, columnspan=3, sticky="we", pady=(0, 8))
        r = self._row_path(ext, 0, "源目录", "ext.src", self.vars["cmp.new"].get())
        r = self._row_path(ext, r, "输出目录", "ext.out", os.path.join(mod, "打印文件"))
        opts = ttk.Frame(ext)
        opts.grid(row=r, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Checkbutton(opts, text="加序号前缀 (001_)",
                        variable=self._var("ext.prefix", True, "bool")).pack(side="left")
        ttk.Checkbutton(opts, text="执行前清空输出目录中的 Word 文件",
                        variable=self._var("ext.clear", False, "bool")).pack(side="left", padx=12)
        self._run_btn(ext, "提取打印文件",
                      lambda: self._run_extract(), row=r + 1, column=0,
                      sticky="w", pady=(6, 0))

        # ---- 提取非 Word 文件 ----
        extnw = ttk.LabelFrame(
            tab, text="提取非Word文件（平铺早于截止时间的非 doc/docx 文件并编号）", padding=8)
        extnw.grid(row=1, column=0, columnspan=3, sticky="we", pady=8)
        r = self._row_path(extnw, 0, "源目录", "extnw.src", self.vars["cmp.new"].get())
        r = self._row_path(extnw, r, "输出目录", "extnw.out",
                           os.path.join(mod, "非Word文件"))
        for label, key, dft in (("截止时间(早于此时刻)", "extnw.before", ""),
                                ("跳过的文件夹名(逗号分隔,支持通配符)", "extnw.skip", "")):
            ttk.Label(extnw, text=label).grid(row=r, column=0, sticky="e", padx=4, pady=3)
            ttk.Entry(extnw, textvariable=self._var(key, dft), width=40)\
                .grid(row=r, column=1, sticky="w", padx=4)
            r += 1
        opts = ttk.Frame(extnw)
        opts.grid(row=r, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Checkbutton(opts, text="加序号前缀 (001_)",
                        variable=self._var("extnw.prefix", True, "bool")).pack(side="left")
        ttk.Checkbutton(opts, text="执行前清空输出目录中的非 Word 文件",
                        variable=self._var("extnw.clear", False, "bool")).pack(side="left", padx=12)
        ttk.Checkbutton(opts, text="模拟运行（只把将复制的清单写入log，不移动文件）",
                        variable=self._var("extnw.dry_run", False, "bool")).pack(side="left", padx=12)
        self._run_btn(extnw, "提取非Word文件",
                      lambda: self._run_extract_nonword(), row=r + 1, column=0,
                      sticky="w", pady=(6, 0))
        ttk.Label(extnw, foreground="#666",
                  text="说明：截止时间留空则使用脚本内 CUTOFF_TIME 常量；"
                       "时间格式如 2026-08-01 或 2026-08-01 12:30。"
                       "勾选「模拟运行」时不创建/清空输出目录、不复制文件，"
                       "只把将要复制的文件清单写入 logs/ 日志。")\
            .grid(row=r + 2, column=0, columnspan=3, sticky="w", pady=(2, 0))

        # ---- 文件信息统计 ----
        stf = ttk.LabelFrame(
            tab, text="文件信息统计（递归统计 Word / PDF / 其他格式文件数量）", padding=8)
        stf.grid(row=2, column=0, columnspan=3, sticky="we", pady=8)
        r = self._row_path(stf, 0, "统计目标文件夹", "st.src", self.vars["cmp.new"].get())
        self._run_btn(stf, "开始统计", lambda: self._run_stats(),
                      row=r, column=1, sticky="w", pady=(6, 0))
        ttk.Label(stf, foreground="#666",
                  text="说明：递归扫描目标文件夹全部子目录；.doc/.docx 计入 Word，"
                       ".pdf 单独统计，其余按扩展名列出明细（最多显示 20 种）。")\
            .grid(row=r + 1, column=0, columnspan=3, sticky="w", pady=(2, 0))

    # ============================================================
    # Tab 4：底稿 PDF 材料整理（file_toolkit）
    # ============================================================
    FILE_CMDS = {
        "dedup_folders 编号子文件夹去重": {
            "sub": "dedup_folders",
            "fields": [
                {"key": "source", "label": "源目录", "type": "path"},
                {"key": "output", "label": "输出目录", "type": "path"},
                {"key": "--layout", "label": "目录结构", "type": "combo",
                 "options": ["single", "nested"], "default": "single"},
                {"key": "--no-image-convert", "label": "复制后不先转图片比对", "type": "flag"},
            ],
        },
        "convert_images 图片转PDF": {
            "sub": "convert_images",
            "fields": [{"key": "--target", "label": "目标目录", "type": "path"}],
        },
        "match_excel 台账匹配": {
            "sub": "match_excel",
            "fields": [
                {"key": "--excel", "label": "台账 xlsx", "type": "file"},
                {"key": "--sheet1", "label": "Sheet1 名", "type": "text", "default": "Sheet1"},
                {"key": "--sheet2", "label": "Sheet2 名", "type": "text", "default": "Sheet2"},
                {"key": "--cols", "label": "匹配列(逗号分隔)", "type": "text",
                 "default": "贷款机构,借款单位,余额,借款日,到期日,利率"},
                {"key": "--output-dir", "label": "交付物输出目录", "type": "path"},
            ],
        },
        "merge_pdfs 特征优先级合并": {
            "sub": "merge_pdfs",
            "fields": [
                {"key": "--excel", "label": "匹配结果 xlsx(含num列)", "type": "file"},
                {"key": "--sheet", "label": "工作表名", "type": "text", "default": "sheet1"},
                {"key": "--folders", "label": "编号文件夹根目录", "type": "path"},
                {"key": "--output", "label": "合并PDF输出目录", "type": "path"},
                {"key": "--features", "label": "特征优先级JSON(可选)", "type": "file"},
            ],
        },
        "pdf_merge 子文件夹合并铺平编号": {
            "sub": "pdf_merge",
            "fields": [
                {"key": "--top", "label": "顶级文件夹", "type": "path"},
                {"key": "--prefix", "label": "编号前缀 如 2-3-6-2-", "type": "text"},
                {"key": "__stage", "label": "执行阶段", "type": "combo",
                 "options": ["预览", "仅合并(--merge)", "仅铺平(--flatten)", "一步完成(--all)"],
                 "default": "预览"},
            ],
        },
        "flat_rename 多文件夹平铺重命名": {
            "sub": "flat_rename",
            "fields": [
                {"key": "--parent", "label": "父目录", "type": "path"},
                {"key": "--folders", "label": '目录名[:flat],…', "type": "wide",
                 "placeholder": '示例：2-3-5-7 固定资产科目核查:flat,2-3-5-8 无形资产科目核查'},
                {"key": "--apply", "label": "实际执行（不勾=仅预览）", "type": "flag"},
            ],
        },
        "order_rename 固定位置顺序编号": {
            "sub": "order_rename",
            "fields": [
                {"key": "--locations", "label": "位置目录（每行一个，按编号顺序）", "type": "lines"},
                {"key": "--prefix", "label": "编号前缀 如 2-3-5-6-", "type": "text"},
                {"key": "--apply", "label": "实际执行（不勾=仅预览）", "type": "flag"},
            ],
        },
        "renumber_files 重连贯编号": {
            "sub": "renumber_files",
            "fields": [
                {"key": "--folder", "label": "目标文件夹", "type": "path"},
                {"key": "--start", "label": "起始编号", "type": "int", "default": 1},
                {"key": "--apply", "label": "实际执行（不勾=仅预览）", "type": "flag"},
            ],
        },
    }

    def _tab_filetoolkit(self, nb):
        tab = self._new_tab(nb, " 底稿PDF材料整理 ")
        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Label(top, text="选择功能：").pack(side="left")
        self.ft_combo = ttk.Combobox(top, values=list(self.FILE_CMDS.keys()),
                                     state="readonly", width=34)
        self.ft_combo.current(0)
        self.ft_combo.pack(side="left", padx=6)
        self.ft_combo.bind("<<ComboboxSelected>>",
                           lambda _e: self._rebuild_ft_fields())

        self.ft_frame = ttk.LabelFrame(tab, text="参数", padding=8)
        self.ft_frame.pack(fill="both", expand=False, pady=8)
        self._rebuild_ft_fields()

        bar = ttk.Frame(tab)
        bar.pack(fill="x")
        self._run_btn(bar, "执 行", self._run_filetoolkit, side="left", padx=4)
        ttk.Label(bar, foreground="#666",
                  text="改名类命令默认仅预览，确认无误后勾选「实际执行」再跑一次。")\
            .pack(side="left", padx=8)

    def _rebuild_ft_fields(self):
        for child in self.ft_frame.winfo_children():
            child.destroy()
        spec = self.FILE_CMDS[self.ft_combo.get()]
        self.ft_widgets = {}
        rowi = 0
        for f in spec["fields"]:
            key, typ, label = f["key"], f["type"], f["label"]
            if typ in ("path", "file"):
                self._row_path(self.ft_frame, rowi, label, "ft." + key, "", is_file=(typ == "file"))
                rowi += 1
            elif typ == "text":
                ttk.Label(self.ft_frame, text=label).grid(row=rowi, column=0, sticky="e", padx=4)
                var = self._var("ft." + key, f.get("default", ""))
                ttk.Entry(self.ft_frame, textvariable=var, width=70)\
                    .grid(row=rowi, column=1, columnspan=2, sticky="we", padx=4)
                rowi += 1
            elif typ == "wide":
                ttk.Label(self.ft_frame, text=label).grid(row=rowi, column=0, sticky="ne", padx=4)
                txt = tk.Text(self.ft_frame, height=3, wrap="word", font=("Consolas", 9))
                if f.get("placeholder"):
                    txt.insert("1.0", f["placeholder"])
                txt.grid(row=rowi, column=1, columnspan=2, sticky="we", padx=4)
                self.ft_widgets[key] = txt
                rowi += 1
            elif typ == "lines":
                ttk.Label(self.ft_frame, text=label).grid(row=rowi, column=0, sticky="ne", padx=4)
                txt = tk.Text(self.ft_frame, height=4, wrap="none", font=("Consolas", 9))
                txt.grid(row=rowi, column=1, columnspan=2, sticky="we", padx=4)
                self.ft_widgets[key] = txt
                rowi += 1
            elif typ == "combo":
                ttk.Label(self.ft_frame, text=label).grid(row=rowi, column=0, sticky="e", padx=4)
                var = self._var("ft." + key, f.get("default") or f["options"][0])
                ttk.Combobox(self.ft_frame, textvariable=var, values=f["options"],
                             state="readonly", width=30)\
                    .grid(row=rowi, column=1, sticky="w", padx=4)
                rowi += 1
            elif typ == "flag":
                var = self._var("ft." + key, False, "bool")
                ttk.Checkbutton(self.ft_frame, text=label, variable=var)\
                    .grid(row=rowi, column=1, sticky="w", padx=4)
                rowi += 1
            elif typ == "int":
                ttk.Label(self.ft_frame, text=label).grid(row=rowi, column=0, sticky="e", padx=4)
                var = self._var("ft." + key, str(f.get("default", "")))
                ttk.Spinbox(self.ft_frame, from_=0, to=99999, textvariable=var, width=8)\
                    .grid(row=rowi, column=1, sticky="w", padx=4)
                rowi += 1
        self.ft_frame.columnconfigure(1, weight=1)

    def _collect_ft_args(self):
        spec = self.FILE_CMDS[self.ft_combo.get()]
        args = [spec["sub"]]
        for f in spec["fields"]:
            key, typ = f["key"], f["type"]
            if typ == "path":
                val = self.vars["ft." + key].get().strip()
                if not val:
                    raise ValueError(f"请填写「{f['label']}」")
                args += ["--" + key if not key.startswith("--") else key, val]
            elif typ in ("text", "int"):
                val = self.vars["ft." + key].get().strip()
                if val:
                    args += [key, val]
            elif typ == "file":
                val = self.vars["ft." + key].get().strip()
                if val:
                    args += [key, val]
                elif f["label"].endswith("(可选)") or "(可选)" in f["label"]:
                    continue
                else:
                    raise ValueError(f"请填写「{f['label']}」")
            elif typ == "flag":
                if self.vars["ft." + key].get():
                    args.append(key)
            elif typ == "combo":
                val = self.vars["ft." + key].get()
                if key == "--layout":
                    args += ["--layout", val]
                elif key == "__stage":
                    if "merge" in val:
                        args.append("--merge")
                    if "flatten" in val:
                        args.append("--flatten")
                    if "all" in val:
                        args.append("--all")
            elif typ == "wide":
                widget = self.ft_widgets[key]
                val = widget.get("1.0", "end").strip()
                if not val:
                    raise ValueError(f"请填写「{f['label']}」")
                args += [key, " ".join(val.split())]
            elif typ == "lines":
                widget = self.ft_widgets[key]
                lines = [ln.strip() for ln in widget.get("1.0", "end").splitlines()
                         if ln.strip()]
                if not lines:
                    raise ValueError(f"请填写「{f['label']}」")
                args += [key] + lines
        return args

    # ============================================================
    # Tab 5：多级文件夹生成目录
    # ============================================================
    def _tab_dirgen(self, nb):
        tab = self._new_tab(nb, " 目录生成 ")

        def auto_fill(*_a):
            target = self.vars["dg.target"].get().strip()
            if target and os.path.isdir(target):
                name = os.path.basename(target.rstrip("\\/"))
                parent = os.path.dirname(target)
                self.vars["dg.excel"].set(os.path.join(parent, f"【{name}】目录.xlsx"))
                self.vars["dg.word"].set(os.path.join(parent, f"【{name}】目录.docx"))

        row = self._row_path(tab, 0, "目标文件夹", "dg.target", "")
        self.vars["dg.target"].trace_add("write", auto_fill)
        row = self._row_path(tab, row, "Excel 目录输出", "dg.excel", "")
        row = self._row_path(tab, row, "Word 目录输出", "dg.word", "")

        btns = ttk.Frame(tab)
        btns.grid(row=row, column=0, columnspan=3, sticky="w", pady=10)
        self._run_btn(btns, "生成 Excel 目录", lambda: self._run_dirgen(excel_only=True),
                      side="left", padx=5)
        self._run_btn(btns, "生成 Excel + Word 目录",
                      lambda: self._run_dirgen(excel_only=False), side="left", padx=5)
        ttk.Label(tab, foreground="#666",
                  text="说明：扫描目标文件夹的多级结构生成层级目录表（自动去空文件夹、同编号去重、"
                       "中文序号自然排序）；Word 版由 Excel 转出。").grid(
            row=row + 1, column=0, columnspan=3, sticky="w", pady=6)

    # ============================================================
    # 任务启动
    # ============================================================
    def _check_paths(self, pairs):
        for label, path, must_dir in pairs:
            if not path:
                messagebox.showwarning("缺少路径", f"请填写「{label}」。", parent=self.root)
                return False
            if must_dir and not os.path.isdir(path):
                messagebox.showwarning("路径无效", f"「{label}」不存在：\n{path}",
                                       parent=self.root)
                return False
        return True

    def _launch_runner(self, label, task, params):
        spec_json = json.dumps({"task": task, "params": params}, ensure_ascii=False)
        if getattr(sys, "frozen", False):
            # exe 模式：派生自身，进入 --gui-runner 内部模式执行中转器
            argv = [sys.executable, "--gui-runner", spec_json]
        else:
            argv = [sys.executable, RUNNER, spec_json]
        self._launch(label, argv, cwd=BASE_DIR)

    def _launch_cli(self, label, module_dir, script, args):
        if getattr(sys, "frozen", False):
            # exe 模式：脚本已作为数据文件打进包里，由自身 --run-script 模式执行。
            # 此时 exe 同级并没有模块目录，工作目录必须用打包资源目录，
            # 否则 Popen 会因目录不存在直接抛错。
            cwd = os.path.join(RES_DIR, module_dir)
            argv = [sys.executable, "--run-script", _res(module_dir, script)] \
                + list(args)
        else:
            cwd = os.path.join(BASE_DIR, module_dir)
            argv = [sys.executable, script] + list(args)
        if not os.path.isdir(cwd):  # 兜底：退回根目录，别让子进程起不来
            cwd = BASE_DIR
        self._launch(label, argv, cwd=cwd)

    def _launch(self, label, argv, cwd=None):
        if self._busy:
            messagebox.showinfo("正在运行", "已有任务在运行，请等待完成后再发起新任务。",
                                parent=self.root)
            return
        self._save_settings()
        self._busy = True
        self._set_buttons_state("disabled")
        self.status_var.set(f"运行中：{label}")
        self._log(f"\n=== {label} ===", "head")
        self._log("$ " + " ".join(argv[1:])[:400])
        threading.Thread(target=self._worker, args=(argv, cwd, label), daemon=True)\
            .start()

    def _worker(self, argv, cwd, label):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            self._proc = subprocess.Popen(
                argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", env=env,
                creationflags=CREATE_NO_WINDOW)
            for line in self._proc.stdout:
                self._queue.put(line.rstrip("\n"))
            rc = self._proc.wait()
        except Exception as exc:  # noqa: BLE001
            self._queue.put(f"[异常] {exc}")
            rc = -1
        finally:
            self._queue.put((label, rc))  # 结束哨兵

    def _poll_queue(self):
        try:
            while True:
                item = self._queue.get_nowait()
                if isinstance(item, tuple):
                    label, rc = item
                    self._finish(label, rc)
                else:
                    self._log(item)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    def _finish(self, label, rc):
        self._proc = None
        if rc == 0:
            self._log(f"--- 完成：{label}（退出码 0）---", "ok")
        else:
            self._log(f"--- 结束：{label}（退出码 {rc}，详见上方日志与 logs\\ 目录）---",
                      "err")
        self._busy = False
        self._set_buttons_state("normal")
        self.status_var.set("就绪" if rc == 0 else f"上一步失败（退出码 {rc}）")

    def _set_buttons_state(self, state):
        for btn in self.run_buttons:
            try:
                btn.configure(state=state)
            except tk.TclError:
                pass

    # ---------- 各任务参数收集 ----------
    SIGN_STEP_NAMES = {
        "format": "① 刷新docx格式", "header": "② 页眉修复",
        "export": "③ 导出PDF拆签章页", "filter": "④ 过滤索引清单",
        "insert_append": "⑤ 追加签章页", "insert_replace": "⑥ 替换签字页",
    }

    def _run_sign(self, cmd):
        params = {
            "cmd": cmd,
            "root": self.vars["sign.root"].get().strip(),
            "tag": self.vars["sign.tag"].get().strip() or None,
            "keyword": self.vars["sign.keyword"].get().strip() or None,
            "dry_run": bool(self.vars["sign.dry_run"].get()),
            "update_days": self._to_int("sign.update_days", 100),
            "pdf_reuse_days": self._to_int("sign.pdf_reuse_days", 1),
            # ④-⑥ 手动路径（留空沿用默认）
            "steps_root": self.vars["sign.steps_root"].get().strip() or None,
            "filter_json": self.vars["sign.filter_json"].get().strip() or None,
            "append_json": self.vars["sign.append_json"].get().strip() or None,
            "append_pdf": self.vars["sign.append_pdf"].get().strip() or None,
            "replace_list": self.vars["sign.replace_list"].get().strip() or None,
            "replace_pdf": self.vars["sign.replace_pdf"].get().strip() or None,
        }
        checks = [("项目根目录", params["root"], True)]
        if cmd == "filter" and params["filter_json"]:
            checks.append(("JSON 清单（④）", params["filter_json"], False))
        if cmd == "insert_append" and params["append_json"]:
            checks.append(("JSON 清单（⑤）", params["append_json"], False))
        if cmd == "insert_append" and params["append_pdf"]:
            checks.append(("签章页.pdf", params["append_pdf"], False))
        if cmd == "insert_replace" and params["replace_list"]:
            checks.append(("无索引清单.log（⑥）", params["replace_list"], False))
        if cmd == "insert_replace" and params["replace_pdf"]:
            checks.append(("签字合并.pdf", params["replace_pdf"], False))
        if cmd in ("filter", "insert_append", "insert_replace") and params["steps_root"]:
            checks.append(("④-⑥ 项目根目录", params["steps_root"], True))
        if not self._check_paths(checks):
            return
        for label, path in (("JSON 清单（④）", params["filter_json"]),
                            ("JSON 清单（⑤）", params["append_json"]),
                            ("签章页.pdf", params["append_pdf"]),
                            ("无索引清单.log（⑥）", params["replace_list"]),
                            ("签字合并.pdf", params["replace_pdf"])):
            if path and not os.path.isfile(path):
                messagebox.showwarning("文件不存在", f"「{label}」不存在：\n{path}",
                                       parent=self.root)
                return
        if cmd == "export":
            ok = messagebox.askyesno(
                "确认导出", "export 会把项目根目录下的 docx 全量导出 PDF，并拆末页合并签章页。\n"
                "不要重复对已拆过末页的 PDF 运行！继续？", parent=self.root)
            if not ok:
                return
        if cmd == "insert_replace":
            list_desc = (f"自定义清单：{params['replace_list']}" if params["replace_list"]
                         else "默认清单：logs\\no_company_无索引_latest.log（可在「④-⑥ 手动路径」指定）")
            ok = messagebox.askyesno(
                "确认替换",
                "replace 模式会用「签字合并.pdf」替换无索引清单中各文件的目标页。\n\n"
                f"· {list_desc}\n"
                "· 默认替换末页（清单行为「路径|末页」，旧版清单无标记也按末页处理）；\n"
                "· 签字页不在末页的例外文件：先在清单中把该行改成具体页码\n"
                "  （如 xxx.pdf|12），再运行本步。\n\n"
                "要求清单条数与 PDF 页数严格相等，确定继续？",
                parent=self.root)
            if not ok:
                return
        self._launch_runner(self.SIGN_STEP_NAMES[cmd], "sign", params)

    def _run_init(self):
        root = self.vars["init.root"].get().strip()
        if not self._check_paths([("待处理 Word 文件夹", root, True)]):
            return
        ok = messagebox.askyesno(
            "确认初始化",
            "初始化会原地修改文件夹内所有 docx：统一字体/行距、删除文末图片、\n"
            "改写或追加签章页。该操作不可撤销，建议先备份。\n\n确定继续？",
            parent=self.root)
        if not ok:
            return
        params = {
            "root": root,
            "issuer": self.vars["init.issuer"].get().strip() or None,
            "project_team": self.vars["init.team"].get().strip() or None,
            "date": self.vars["init.date"].get().strip() or None,
            "sign_name": self.vars["init.sign_name"].get().strip() or None,
        }
        self._launch_runner("初始化底稿文件", "init", params)

    def _run_replace(self, cmd):
        params = {
            "cmd": cmd,
            "rules_xlsx": self.vars["rep.rules"].get().strip(),
            "source": self.vars["rep.source"].get().strip(),
            "final": self.vars["rep.final"].get().strip() or None,
            "insert_dir": self.vars["rep.insert_dir"].get().strip() or None,
            "overwrite": bool(self.vars["rep.overwrite"].get()),
            "output_dir": self.vars["rep.output_dir"].get().strip() or None,
        }
        checks = [("替换规则表.xlsx", params["rules_xlsx"], False),
                  ("docx 根目录", params["source"], True)]
        if not self._check_paths(checks):
            return
        if not os.path.isfile(params["rules_xlsx"]):
            messagebox.showwarning("文件不存在",
                                   f"规则表不存在：\n{params['rules_xlsx']}",
                                   parent=self.root)
            return
        name = "短替换" if cmd == "short" else "长替换（Word COM）"
        self._launch_runner(name, "replace", params)

    def _run_make_rules(self):
        """生成「替换规则表.xlsx」模板（复用 make_rules_template.py，不覆盖已有文件）。"""
        out = self.vars["rep.rules_out"].get().strip()
        if not out:
            messagebox.showwarning("缺少路径", "请填写「规则表输出路径」。",
                                   parent=self.root)
            return
        if os.path.exists(out):
            messagebox.showwarning("文件已存在",
                                   f"目标文件已存在，为防误覆盖请先改名或删除：\n{out}",
                                   parent=self.root)
            return
        self._save_settings()
        self._launch_cli("生成替换表模板", "替换底稿内容",
                         "make_rules_template.py", [out])

    def _run_stats(self):
        """递归统计目标文件夹内 Word / PDF / 其他格式文件数量（GUI 内后台线程）。"""
        target = self.vars["st.src"].get().strip()
        if not self._check_paths([("统计目标文件夹", target, True)]):
            return
        self._save_settings()
        self._busy = True
        self._set_buttons_state("disabled")
        self.status_var.set("运行中：文件信息统计")
        self._log("\n=== 文件信息统计 ===", "head")
        self._log(f"$ 扫描目录：{target}")

        def work():
            rc = 0
            try:
                word = pdf = total = 0
                other_ext = {}
                for _dirpath, _dirnames, filenames in os.walk(target):
                    for name in filenames:
                        total += 1
                        ext = os.path.splitext(name)[1].lower()
                        if ext in (".doc", ".docx"):
                            word += 1
                        elif ext == ".pdf":
                            pdf += 1
                        else:
                            key = ext if ext else "（无扩展名）"
                            other_ext[key] = other_ext.get(key, 0) + 1
                other = total - word - pdf
                q = self._queue
                q.put(f"扫描完成：共 {total} 个文件")
                q.put(f"Word 文件（.doc/.docx）：{word} 个")
                q.put(f"PDF 文件（.pdf）：{pdf} 个")
                q.put(f"其他格式文件合计：{other} 个")
                if other_ext:
                    q.put("其他格式明细（按数量降序，最多 20 种）：")
                    for ext, cnt in sorted(other_ext.items(),
                                           key=lambda kv: (-kv[1], kv[0]))[:20]:
                        q.put(f"    {ext}: {cnt} 个")
                    if len(other_ext) > 20:
                        q.put(f"    …另有 {len(other_ext) - 20} 种扩展名未列出")
            except Exception as exc:  # noqa: BLE001
                self._queue.put(f"[异常] {exc}")
                rc = 1
            finally:
                self._queue.put(("文件信息统计", rc))  # 结束哨兵

        threading.Thread(target=work, daemon=True).start()

    def _run_extract(self):
        src = self.vars["ext.src"].get().strip()
        out = self.vars["ext.out"].get().strip()
        if not self._check_paths([("提取源目录", src, True)]):
            return
        args = ["extract"]
        if src:
            args.append(src)
        if out:
            args.append(out)
        if not self.vars["ext.prefix"].get():
            args.append("--no-prefix")
        if self.vars["ext.clear"].get():
            args.append("--clear-output")
        self._launch_cli("提取打印文件", "比较文件夹内容", "folder_toolbox.py", args)

    def _run_extract_nonword(self):
        src = self.vars["extnw.src"].get().strip()
        out = self.vars["extnw.out"].get().strip()
        if not self._check_paths([("提取源目录", src, True)]):
            return
        args = []
        if src:
            args.append(src)
        if out:
            args.append(out)
        before = self.vars["extnw.before"].get().strip()
        if before:
            args += ["--before", before]
        skip = self.vars["extnw.skip"].get().strip()
        if skip:
            args += ["--skip", ",".join(skip.split())]
        if not self.vars["extnw.prefix"].get():
            args.append("--no-prefix")
        if self.vars["extnw.clear"].get():
            args.append("--clear-output")
        if self.vars["extnw.dry_run"].get():
            args.append("--dry-run")
        self._launch_cli("提取非Word文件", "比较文件夹内容", "提取非Word文件.py", args)

    def _run_filetoolkit(self):
        try:
            args = self._collect_ft_args()
        except ValueError as exc:
            messagebox.showwarning("参数不完整", str(exc), parent=self.root)
            return
        self._launch_cli(f"file_toolkit {args[0]}", "底稿pdf材料", "file_toolkit.py", args)

    def _run_dirgen(self, excel_only):
        target = self.vars["dg.target"].get().strip()
        excel = self.vars["dg.excel"].get().strip()
        word = "" if excel_only else self.vars["dg.word"].get().strip()
        if not self._check_paths([("目标文件夹", target, True)]):
            return
        if not excel:
            messagebox.showwarning("缺少路径", "请填写「Excel 目录输出」路径。",
                                   parent=self.root)
            return
        self._launch_runner("生成目录", "dirgen",
                            {"target": target, "excel": excel, "word": word or None})

    # ---------- 工具 ----------
    def _confirm_then(self, message, func):
        if messagebox.askyesno("确认操作", message, parent=self.root):
            func()

    def _to_int(self, key, default):
        try:
            return int(float(self.vars[key].get()))
        except (ValueError, KeyError):
            return default

    def _log(self, line, tag="info"):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ---------- 设置持久化 ----------
    def _load_settings(self):
        if not os.path.isfile(SETTINGS_PATH):
            return
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        for key, value in data.items():
            var = self.vars.get(key)
            if var is not None:
                try:
                    var.set(value)
                except tk.TclError:
                    pass

    def _save_settings(self):
        data = {}
        for key, var in self.vars.items():
            try:
                data[key] = var.get()
            except tk.TclError:
                pass
        try:
            os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
            with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def _on_close(self):
        if self._busy:
            if not messagebox.askyesno("退出",
                                       "仍有任务在运行，退出将尝试终止它。确定退出？",
                                       parent=self.root):
                return
            if self._proc is not None:
                try:
                    self._proc.terminate()
                except OSError:
                    pass
        self._save_settings()
        self.root.destroy()


def _run_frozen_dispatch():
    """打包(exe)模式下的子进程入口。返回进程退出码。

    注意：windowed (console=False) 打包下，未捕获异常会触发 PyInstaller 的
    模态错误对话框，导致子进程永远不退出、GUI 端表现为"任务卡死"。
    因此这里必须兜底捕获所有异常，把堆栈打到 stdout/stderr 后返回非零码。
    """
    try:
        # 打包后脚本位于 _MEIPASS 临时目录，日志写那里会随进程退出被删除。
        # 统一重定向到 exe 同级的 logs/ 下（各模块自带子目录，见 toolkit/config.py）。
        os.environ.setdefault("IBDW_LOG_ROOT", os.path.join(BASE_DIR, "logs"))
        return _run_frozen_dispatch_inner()
    except SystemExit as exc:  # 下游脚本可能直接 sys.exit
        return exc.code if isinstance(exc.code, int) else 0
    except BaseException:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        return 1


def _run_frozen_dispatch_inner():
    if "--gui-runner" in sys.argv:
        # 内部模式1：充当 gui_runner 中转器
        import importlib.util

        spec_json = sys.argv[sys.argv.index("--gui-runner") + 1]
        spec = importlib.util.spec_from_file_location("gui_runner", RUNNER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.argv = [RUNNER, spec_json]
        return mod.main() or 0
    if "--run-script" in sys.argv:
        # 内部模式2：在进程内执行打包进来的 CLI 脚本（folder_toolbox / file_toolkit）
        import runpy

        i = sys.argv.index("--run-script")
        script = os.path.abspath(sys.argv[i + 1])
        args = sys.argv[i + 2:]
        sys.argv = [script] + list(args)
        sys.path.insert(0, os.path.dirname(script))
        try:
            runpy.run_path(script, run_name="__main__")
            return 0
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else 0
    return 2


def _enable_windows_dpi_awareness():
    """声明 Per-Monitor DPI Aware（Windows 高缩放如 150% 笔记本）。

    必须在创建 Tk 窗口之前调用：否则系统对整个窗口位图拉伸，
    文字发虚、布局按错误像素计算导致控件溢出/显示不全。
    """
    if os.name != "nt":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_DPI_AWARE
    except Exception:
        try:  # 老版本 Windows 回退
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    if getattr(sys, "frozen", False) and (
            "--gui-runner" in sys.argv or "--run-script" in sys.argv):
        sys.exit(_run_frozen_dispatch())
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    ToolBoxApp(root)
    root.mainloop()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main()
