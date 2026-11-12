# -*- coding: utf-8 -*-
"""qtui.pages —— 功能页定义（两级导航：顶部主功能 + 左侧子功能）。

build_areas(win) 返回全部主功能区：
    [(主功能标题, [(子功能标题, 页面控件), ...]), ...]

对应关系（Tk 版页签 → 现在）：
    签章页工具 → 主功能「签章页」：标准流程 / 清单与路径 / 初始化底稿
    替换底稿内容 → 主功能「底稿替换」：生成规则表 / 执行替换
    比较文件夹内容 + 文件提取与统计 → 主功能「文件整理」：比较与合并 /
        提取打印文件 / 提取非Word文件 / 信息统计
    底稿PDF材料整理 → 主功能「PDF材料」：8 个子命令各一页
    多级文件夹生成目录 → 主功能「目录生成」
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QCheckBox, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
                               QWidget)

from .core import BASE_DIR
from .widgets import add_note, add_path_row, add_text_row


def _default(*parts):
    return os.path.normpath(os.path.join(BASE_DIR, *parts))


def _warn(parent, title, text):
    QMessageBox.warning(parent, title, text)


class PageBase(QWidget):
    """子功能页基类：滚动容器 + 网格布局。

    取值辅助基于全窗口查找（objectName 全局唯一），因此一个页面可以
    读取另一页面里的共享字段（如签章页的项目根目录）。
    """

    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 8, 4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        body.setObjectName("PageBody")
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.grid = QGridLayout(body)
        self.grid.setContentsMargins(4, 4, 16, 16)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(8)
        self.grid.setColumnStretch(1, 1)
        self.row = 0
        self.grid.setRowStretch(500, 1)  # 内容顶对齐：多余空间留给底部

    # ---- 布局辅助 ----
    def path_row(self, label, key, default="", is_file=False):
        self.row = add_path_row(self.grid, self.row, label, key, default,
                                is_file=is_file, page=self)

    def text_row(self, label, key, default="", width=0):
        self.row = add_text_row(self.grid, self.row, label, key, default,
                                width=width)

    def note(self, text):
        self.row = add_note(self.grid, self.row, text)

    def group(self, title) -> tuple[QWidget, QGridLayout]:
        box = QGroupBox(title)
        inner = QGridLayout(box)
        inner.setContentsMargins(14, 22, 14, 12)
        inner.setHorizontalSpacing(10)
        inner.setVerticalSpacing(8)
        inner.setColumnStretch(1, 1)
        self.grid.addWidget(box, self.row, 0, 1, 3)
        self.row += 1
        return box, inner

    def primary_button(self, parent_grid, text, handler, row=None, col=1) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("Primary")
        btn.clicked.connect(handler)
        parent_grid.addWidget(btn, row if row is not None else self.row - 1, col)
        self.win.register_button(btn)
        return btn

    # ---- 取值辅助（全窗口查找）----
    def val(self, key) -> str:
        w = self.win.findChild(QLineEdit, key)
        return w.text().strip() if w else ""

    def checked(self, key) -> bool:
        w = self.win.findChild(QCheckBox, key)
        return bool(w.isChecked()) if w else False

    def spin_val(self, key, default=0) -> int:
        w = self.win.findChild(QSpinBox, key)
        return int(w.value()) if w else default


# ============================================================
# 主功能一：签章页
# ============================================================
SIGN_STEP_NAMES = {
    "format": "① 刷新docx格式", "header": "② 页眉修复",
    "export": "③ 导出PDF拆签章页", "filter": "④ 过滤索引清单",
    "insert_append": "⑤ 追加签章页", "insert_replace": "⑥ 替换签字页",
}


class _SignMixin:
    def _check_paths(self, pairs) -> bool:
        for label, path, must_dir in pairs:
            if not path:
                _warn(self.win, "缺少路径", f"请填写「{label}」。")
                return False
            if must_dir and not os.path.isdir(path):
                _warn(self.win, "路径无效", f"「{label}」不存在：\n{path}")
                return False
        return True

    def _run_sign(self, cmd):
        p = {
            "cmd": cmd,
            "root": self.val("sign.root"),
            "tag": self.val("sign.tag") or None,
            "keyword": self.val("sign.keyword") or None,
            "dry_run": self.checked("sign.dry_run"),
            "update_days": self.spin_val("sign.update_days", 100),
            "pdf_reuse_days": self.spin_val("sign.pdf_reuse_days", 1),
            "steps_root": self.val("sign.steps_root") or None,
            "filter_json": self.val("sign.filter_json") or None,
            "append_json": self.val("sign.append_json") or None,
            "append_pdf": self.val("sign.append_pdf") or None,
            "replace_list": self.val("sign.replace_list") or None,
            "replace_pdf": self.val("sign.replace_pdf") or None,
        }
        checks = [("项目根目录", p["root"], True)]
        if cmd == "filter" and p["filter_json"]:
            checks.append(("JSON 清单（④）", p["filter_json"], False))
        if cmd == "insert_append" and p["append_json"]:
            checks.append(("JSON 清单（⑤）", p["append_json"], False))
        if cmd == "insert_append" and p["append_pdf"]:
            checks.append(("签章页.pdf", p["append_pdf"], False))
        if cmd == "insert_replace" and p["replace_list"]:
            checks.append(("无索引清单.log（⑥）", p["replace_list"], False))
        if cmd == "insert_replace" and p["replace_pdf"]:
            checks.append(("签字合并.pdf", p["replace_pdf"], False))
        if cmd in ("filter", "insert_append", "insert_replace") and p["steps_root"]:
            checks.append(("④-⑥ 项目根目录", p["steps_root"], True))
        if not self._check_paths(checks):
            return
        for label, path in (("JSON 清单（④）", p["filter_json"]),
                            ("JSON 清单（⑤）", p["append_json"]),
                            ("签章页.pdf", p["append_pdf"]),
                            ("无索引清单.log（⑥）", p["replace_list"]),
                            ("签字合并.pdf", p["replace_pdf"])):
            if path and not os.path.isfile(path):
                _warn(self.win, "文件不存在", f"「{label}」不存在：\n{path}")
                return
        if cmd == "export":
            ret = QMessageBox.question(
                self.win, "确认导出",
                "export 会把项目根目录下的 docx 全量导出 PDF，并拆末页合并签章页。\n"
                "不要重复对已拆过末页的 PDF 运行！继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        if cmd == "insert_replace":
            list_desc = (f"自定义清单:{p['replace_list']}" if p["replace_list"]
                         else "默认清单:logs\\no_company_无索引_latest.log"
                              "（可在「清单与路径」页指定）")
            ret = QMessageBox.question(
                self.win, "确认替换",
                "replace 模式会用「签字合并.pdf」替换无索引清单中各文件的目标页。\n\n"
                f"· {list_desc}\n"
                "· 默认替换末页（清单行为「路径|末页」，旧版清单无标记也按末页处理）；\n"
                "· 签字页不在末页的例外文件：先在清单中把该行改成具体页码\n"
                "  （如 xxx.pdf|12），再运行本步。\n\n"
                "要求清单条数与 PDF 页数严格相等，确定继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.win.launch_runner(SIGN_STEP_NAMES[cmd], "sign", p)


class SignFlowPage(_SignMixin, PageBase):
    """子页：标准流程 ①→⑥。"""

    def __init__(self, win):
        super().__init__(win)
        _, g = self.group("项目设置")
        r = add_path_row(g, 0, "项目根目录", "sign.root",
                         _default("比较文件夹内容", "new"))
        r = add_text_row(g, r, "项目标识", "sign.tag", "示例", width=120)
        r = add_text_row(g, r, "公司关键字", "sign.keyword",
                         "示例市示范区城市资产经营有限公司")

        opts = QWidget()
        ol = QHBoxLayout(opts)
        ol.setContentsMargins(0, 0, 0, 0)
        dry = QCheckBox("页眉只检查不修改 (dry-run)")
        dry.setObjectName("sign.dry_run")
        ol.addWidget(dry)
        for label, key, dft in (("format 仅处理最近N天", "sign.update_days", 100),
                                ("export PDF复用天数(0关闭)", "sign.pdf_reuse_days", 1)):
            ol.addWidget(QLabel(label))
            spin = QSpinBox()
            spin.setRange(0, 9999)
            spin.setValue(dft)
            spin.setObjectName(key)
            ol.addWidget(spin)
        g.addWidget(opts, r, 0, 1, 3)

        _, g = self.group("执行（标准流程 ①→⑥）")
        steps = [("① 刷新docx格式", "format"), ("② 页眉修复", "header"),
                 ("③ 导出PDF拆签章页", "export"), ("④ 过滤索引清单", "filter"),
                 ("⑤ 追加签章页", "insert_append"), ("⑥ 替换签字页", "insert_replace")]
        for i, (text, cmd) in enumerate(steps):
            btn = QPushButton(text)
            btn.setObjectName("Step")
            btn.clicked.connect(lambda _=False, c=cmd: self._run_sign(c))
            g.addWidget(btn, i // 3, i % 3)
            self.win.register_button(btn)
        for c in range(3):
            g.setColumnStretch(c, 1)
        tip = QLabel("注意：③ 不要重复跑——拆过末页的 PDF 复用会把 has_company 清单冲空；"
                     "需重导请先把该 PDF 删掉或把复用天数设为 0。\n"
                     "④-⑥ 的清单/PDF 手动路径与 ⑤/⑥ 专用根目录在左侧「清单与路径」页设置，"
                     "留空走本页项目根目录。")
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        g.addWidget(tip, 2, 0, 1, 3)


class SignPathsPage(_SignMixin, PageBase):
    """子页：④-⑥ 清单与手动路径。"""

    def __init__(self, win):
        super().__init__(win)
        _, g = self.group("④-⑥ 手动路径（留空则沿用默认文件名）")
        r = add_path_row(g, 0, "项目根目录（⑤追加/⑥替换）", "sign.steps_root")
        r = add_path_row(g, r, "JSON 清单（④ 过滤输入）", "sign.filter_json", is_file=True)
        r = add_path_row(g, r, "JSON 清单（⑤ 追加用）", "sign.append_json", is_file=True)
        r = add_path_row(g, r, "签章页.pdf（⑤ 追加用）", "sign.append_pdf", is_file=True)
        r = add_path_row(g, r, "无索引清单.log（⑥ 替换用）", "sign.replace_list", is_file=True)
        r = add_path_row(g, r, "签字合并.pdf（⑥ 替换用）", "sign.replace_pdf", is_file=True)
        r = add_note(g, r,
                     "说明：「项目根目录」仅对 ⑤/⑥ 生效（④ 过滤只读取 JSON 清单，"
                     "不扫描目录），留空时 ⑤/⑥ 使用「标准流程」页的项目根目录。"
                     "⑤ 与 ⑥ 用的是两组不同文件——签章页.pdf 由 ③ 导出生成"
                     "（配 has_company JSON 清单），签字合并.pdf 为已签字页合并稿"
                     "（配无索引 log 清单）。清单/PDF 留空时自动取上述根目录下的"
                     " logs\\has_company_latest.json、logs\\no_company_无索引_latest.log"
                     " 及根目录下的签章页.pdf / 签字合并.pdf。")

        _, g = self.group("直接执行")
        btns = [("④ 过滤索引清单", "filter"), ("⑤ 追加签章页", "insert_append"),
                ("⑥ 替换签字页", "insert_replace")]
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        for text, cmd in btns:
            b = QPushButton(text)
            b.setObjectName("Primary")
            b.clicked.connect(lambda _=False, c=cmd: self._run_sign(c))
            wl.addWidget(b)
            self.win.register_button(b)
        g.addWidget(wrap, r, 0, 1, 3)


class SignInitPage(PageBase):
    """子页：初始化底稿文件。"""

    def __init__(self, win):
        super().__init__(win)
        _, g = self.group("初始化底稿文件（字体/行距刷新 + 末尾处理 + 汇总签章页）")
        r = add_path_row(g, 0, "待处理 Word 文件夹", "init.root")
        r = add_text_row(g, r, "发行人", "init.issuer",
                         "示例市示范区城市资产经营有限公司")
        r = add_text_row(g, r, "项目组", "init.team", "示例项目组")
        r = add_text_row(g, r, "落款日期", "init.date", "2026年6月   日")
        r = add_text_row(g, r, "汇总签章页文件名", "init.sign_name", "全部签章页.docx")
        btn = QPushButton("初始化底稿文件（原地修改！）")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._run_init)
        g.addWidget(btn, r, 1)
        self.win.register_button(btn)
        tip = QLabel("说明：统一字体与 1.5 倍行距、删除文末图片；末尾含「项目组」的文件"
                     "改写为项目组+日期落款，否则追加独立签章页并汇总到汇总签章页文档。")
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        g.addWidget(tip, r + 1, 0, 1, 3)

    def _run_init(self):
        root = self.val("init.root")
        if not root:
            _warn(self.win, "缺少路径", "请填写「待处理 Word 文件夹」。")
            return
        if not os.path.isdir(root):
            _warn(self.win, "路径无效", f"「待处理 Word 文件夹」不存在：\n{root}")
            return
        ret = QMessageBox.question(
            self.win, "确认初始化",
            "初始化会原地修改文件夹内所有 docx：统一字体/行距、删除文末图片、\n"
            "改写或追加签章页。该操作不可撤销，建议先备份。\n\n确定继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        params = {
            "root": root,
            "issuer": self.val("init.issuer") or None,
            "project_team": self.val("init.team") or None,
            "date": self.val("init.date") or None,
            "sign_name": self.val("init.sign_name") or None,
        }
        self.win.launch_runner("初始化底稿文件", "init", params)


# ============================================================
# 主功能二：底稿替换
# ============================================================
class RulesGenPage(PageBase):
    """子页：生成替换规则表模板。"""

    def __init__(self, win):
        super().__init__(win)
        _, g = self.group("生成替换表模板（三张表：填写说明/短替换/长替换）")
        r = add_text_row(g, 0, "规则表输出路径", "rep.rules_out",
                         _default("替换规则表.xlsx"))
        btn = QPushButton("生成替换表模板")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._run_make_rules)
        g.addWidget(btn, r, 1)
        self.win.register_button(btn)
        add_note(g, r + 1,
                 "说明：已存在同名文件时不会覆盖，请先改名或删除；"
                 "生成后按「填写说明」表填好，再到「执行替换」页运行短/长替换。")

    def _run_make_rules(self):
        out = self.val("rep.rules_out")
        if not out:
            _warn(self.win, "缺少路径", "请填写「规则表输出路径」。")
            return
        if os.path.exists(out):
            _warn(self.win, "文件已存在",
                  f"目标文件已存在，为防误覆盖请先改名或删除：\n{out}")
            return
        self.win.save_settings()
        self.win.launch_cli("生成替换表模板", "替换底稿内容",
                            "make_rules_template.py", [out])


class ReplaceRunPage(PageBase):
    """子页：执行替换（short + long）。"""

    def __init__(self, win):
        super().__init__(win)
        _, g = self.group("公共设置")
        r = add_path_row(g, 0, "替换规则表.xlsx", "rep.rules",
                         _default("替换规则表.xlsx"), is_file=True)
        add_path_row(g, r, "docx 根目录", "rep.source",
                     _default("比较文件夹内容", "new"))

        _, g = self.group("short —— 词对/正则替换（python-docx，快）")
        r = add_path_row(g, 0, "输出目录（空=原地替换）", "rep.final")
        btn = QPushButton("运行短替换")
        btn.setObjectName("Primary")
        btn.clicked.connect(lambda: self._run_replace("short"))
        g.addWidget(btn, r, 1)
        self.win.register_button(btn)

        _, g = self.group("long —— 区间替换+插入素材（Word COM，保格式）")
        r = add_path_row(g, 0, "素材 docx 文件夹", "rep.insert_dir",
                         _default("替换底稿内容", "素材"))
        ow = QCheckBox("覆盖原文件（不勾选则另存到下方输出目录）")
        ow.setObjectName("rep.overwrite")
        ow.setChecked(True)
        g.addWidget(ow, r, 1)
        r += 1
        r = add_path_row(g, r, "另存输出目录", "rep.output_dir",
                         _default("替换底稿内容", "替换结果"))
        btn = QPushButton("运行长替换（需本机 Word）")
        btn.setObjectName("Primary")
        btn.clicked.connect(lambda: self._run_replace("long"))
        g.addWidget(btn, r, 1)
        self.win.register_button(btn)

    def _run_replace(self, cmd):
        params = {
            "cmd": cmd,
            "rules_xlsx": self.val("rep.rules"),
            "source": self.val("rep.source"),
            "final": self.val("rep.final") or None,
            "insert_dir": self.val("rep.insert_dir") or None,
            "overwrite": self.checked("rep.overwrite"),
            "output_dir": self.val("rep.output_dir") or None,
        }
        if not params["rules_xlsx"]:
            _warn(self.win, "缺少路径", "请填写「替换规则表.xlsx」。")
            return
        if not os.path.isdir(params["source"]):
            _warn(self.win, "路径无效", f"「docx 根目录」不存在：\n{params['source']}")
            return
        if not os.path.isfile(params["rules_xlsx"]):
            _warn(self.win, "文件不存在", f"规则表不存在：\n{params['rules_xlsx']}")
            return
        name = "短替换" if cmd == "short" else "长替换（Word COM）"
        self.win.launch_runner(name, "replace", params)


# ============================================================
# 主功能三：文件整理
# ============================================================
class FolderComparePage(PageBase):
    """子页：比较差异 / 合并覆盖。"""

    def __init__(self, win):
        super().__init__(win)
        mod = os.path.join(BASE_DIR, "比较文件夹内容")
        _, g = self.group("比较与合并")
        r = add_path_row(g, 0, "old 文件夹", "cmp.old", os.path.join(mod, "old"))
        r = add_path_row(g, r, "new 文件夹", "cmp.new", os.path.join(mod, "new"))
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        b1 = QPushButton("比较差异（SHA-256）")
        b1.setObjectName("Primary")
        b1.clicked.connect(self._run_compare)
        b2 = QPushButton("合并（new 覆盖 old，不备份！）")
        b2.clicked.connect(self._run_merge)
        self.win.register_button(b1)
        self.win.register_button(b2)
        wl.addWidget(b1)
        wl.addWidget(b2)
        g.addWidget(wrap, r, 0, 1, 3)
        self.note("说明：提取打印文件 / 提取非Word文件 / 信息统计见左侧其他子功能。")

    def _run_compare(self):
        self.win.launch_cli("比较文件夹内容", "比较文件夹内容", "folder_toolbox.py",
                            ["compare", self.val("cmp.old"), self.val("cmp.new")])

    def _run_merge(self):
        old, new = self.val("cmp.old"), self.val("cmp.new")
        ret = QMessageBox.question(
            self.win, "确认操作",
            "将用 new 中的同名 docx 直接覆盖 old（不备份），确定继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self.win.launch_cli("比较文件夹内容", "比较文件夹内容", "folder_toolbox.py",
                            ["merge", old, new])


class ExtractPrintPage(PageBase):
    """子页：提取打印文件。"""

    def __init__(self, win):
        super().__init__(win)
        mod = os.path.join(BASE_DIR, "比较文件夹内容")
        _, g = self.group("提取打印文件（平铺 doc/docx 到一个文件夹）")
        r = add_path_row(g, 0, "源目录", "ext.src",
                         _default("比较文件夹内容", "new"))
        r = add_path_row(g, r, "输出目录", "ext.out", os.path.join(mod, "打印文件"))
        opts = QWidget()
        ol = QHBoxLayout(opts)
        ol.setContentsMargins(0, 0, 0, 0)
        for label, key, dft in (("加序号前缀 (001_)", "ext.prefix", True),
                                ("执行前清空输出目录中的 Word 文件", "ext.clear", False)):
            cb = QCheckBox(label)
            cb.setObjectName(key)
            cb.setChecked(dft)
            ol.addWidget(cb)
        g.addWidget(opts, r, 0, 1, 3)
        r += 1
        btn = QPushButton("提取打印文件")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._run_extract)
        g.addWidget(btn, r, 0)
        self.win.register_button(btn)

    def _run_extract(self):
        src, out = self.val("ext.src"), self.val("ext.out")
        if not src:
            _warn(self.win, "缺少路径", "请填写「源目录」。")
            return
        args = ["extract"]
        if src:
            args.append(src)
        if out:
            args.append(out)
        if not self.checked("ext.prefix"):
            args.append("--no-prefix")
        if self.checked("ext.clear"):
            args.append("--clear-output")
        self.win.launch_cli("提取打印文件", "比较文件夹内容",
                            "folder_toolbox.py", args)


class ExtractNonWordPage(PageBase):
    """子页：提取非 Word 文件。"""

    def __init__(self, win):
        super().__init__(win)
        mod = os.path.join(BASE_DIR, "比较文件夹内容")
        _, g = self.group("提取非Word文件（平铺早于截止时间的非 doc/docx 文件并编号）")
        r = add_path_row(g, 0, "源目录", "extnw.src",
                         _default("比较文件夹内容", "new"))
        r = add_path_row(g, r, "输出目录", "extnw.out",
                         os.path.join(mod, "非Word文件"))
        r = add_text_row(g, r, "截止时间(早于此时刻)", "extnw.before", "", width=200)
        r = add_text_row(g, r, "跳过的文件夹名(逗号分隔,支持通配符)", "extnw.skip",
                         "", width=260)
        opts = QWidget()
        ol = QHBoxLayout(opts)
        ol.setContentsMargins(0, 0, 0, 0)
        for label, key, dft in (("加序号前缀 (001_)", "extnw.prefix", True),
                                ("执行前清空输出目录中的非 Word 文件", "extnw.clear", False),
                                ("模拟运行（只把将复制的清单写入log，不移动文件）",
                                 "extnw.dry_run", False)):
            cb = QCheckBox(label)
            cb.setObjectName(key)
            cb.setChecked(dft)
            ol.addWidget(cb)
        g.addWidget(opts, r, 0, 1, 3)
        r += 1
        btn = QPushButton("提取非Word文件")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._run_extract_nonword)
        g.addWidget(btn, r, 0)
        self.win.register_button(btn)
        add_note(g, r + 1,
                 "说明：截止时间留空则使用脚本内 CUTOFF_TIME 常量；"
                 "时间格式如 2026-08-01 或 2026-08-01 12:30。"
                 "勾选「模拟运行」时不创建/清空输出目录、不复制文件，"
                 "只把将要复制的文件清单写入 logs/ 日志，供确认后再实际执行。")

    def _run_extract_nonword(self):
        src, out = self.val("extnw.src"), self.val("extnw.out")
        if not src:
            _warn(self.win, "缺少路径", "请填写「源目录」。")
            return
        args = [src]
        if out:
            args.append(out)
        before = self.val("extnw.before")
        if before:
            args += ["--before", before]
        skip = self.val("extnw.skip")
        if skip:
            args += ["--skip", ",".join(skip.split())]
        if not self.checked("extnw.prefix"):
            args.append("--no-prefix")
        if self.checked("extnw.clear"):
            args.append("--clear-output")
        if self.checked("extnw.dry_run"):
            args.append("--dry-run")
        self.win.launch_cli("提取非Word文件", "比较文件夹内容",
                            "提取非Word文件.py", args)


class StatsPage(PageBase):
    """子页：文件信息统计。"""

    def __init__(self, win):
        super().__init__(win)
        _, g = self.group("文件信息统计（递归统计 Word / PDF / 其他格式文件数量）")
        r = add_path_row(g, 0, "统计目标文件夹", "st.src",
                         _default("比较文件夹内容", "new"))
        btn = QPushButton("开始统计")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._run_stats)
        g.addWidget(btn, r, 1)
        self.win.register_button(btn)
        add_note(g, r + 1,
                 "说明：递归扫描目标文件夹全部子目录；.doc/.docx 计入 Word，"
                 ".pdf 单独统计，其余按扩展名列出明细（最多显示 20 种）。结果输出到下方日志区。")

    def _run_stats(self):
        target = self.val("st.src")
        if not target:
            _warn(self.win, "缺少路径", "请填写「统计目标文件夹」。")
            return
        if not os.path.isdir(target):
            _warn(self.win, "路径无效", f"「统计目标文件夹」不存在：\n{target}")
            return
        self.win.save_settings()
        self.win.run_stats(target)


# ============================================================
# 主功能四：PDF 材料（8 个子命令）
# ============================================================
FILE_CMDS = {
    "dedup_folders 编号子文件夹去重": {
        "sub": "dedup_folders", "short": "去重",
        "fields": [
            {"key": "source", "label": "源目录", "type": "path"},
            {"key": "output", "label": "输出目录", "type": "path"},
            {"key": "--layout", "label": "目录结构", "type": "combo",
             "options": ["single", "nested"], "default": "single"},
            {"key": "--no-image-convert", "label": "复制后不先转图片比对", "type": "flag"},
        ],
    },
    "convert_images 图片转PDF": {
        "sub": "convert_images", "short": "图片转PDF",
        "fields": [{"key": "--target", "label": "目标目录", "type": "path"}],
    },
    "match_excel 台账匹配": {
        "sub": "match_excel", "short": "台账匹配",
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
        "sub": "merge_pdfs", "short": "特征合并",
        "fields": [
            {"key": "--excel", "label": "匹配结果 xlsx(含num列)", "type": "file"},
            {"key": "--sheet", "label": "工作表名", "type": "text", "default": "sheet1"},
            {"key": "--folders", "label": "编号文件夹根目录", "type": "path"},
            {"key": "--output", "label": "合并PDF输出目录", "type": "path"},
            {"key": "--features", "label": "特征优先级JSON(可选)", "type": "file"},
        ],
    },
    "pdf_merge 子文件夹合并铺平编号": {
        "sub": "pdf_merge", "short": "合并铺平",
        "fields": [
            {"key": "--top", "label": "顶级文件夹", "type": "path"},
            {"key": "--prefix", "label": "编号前缀 如 2-3-6-2-", "type": "text"},
            {"key": "__stage", "label": "执行阶段", "type": "stage"},
        ],
    },
    "flat_rename 多文件夹平铺重命名": {
        "sub": "flat_rename", "short": "平铺重命名",
        "fields": [
            {"key": "--parent", "label": "父目录", "type": "path"},
            {"key": "--folders", "label": "目录名[:flat],…", "type": "wide",
             "placeholder": "示例：2-3-5-7 固定资产科目核查:flat,"
                            "2-3-5-8 无形资产科目核查"},
            {"key": "--apply", "label": "实际执行（不勾=仅预览）", "type": "flag"},
        ],
    },
    "order_rename 固定位置顺序编号": {
        "sub": "order_rename", "short": "顺序编号",
        "fields": [
            {"key": "--locations", "label": "位置目录（每行一个，按编号顺序）",
             "type": "lines"},
            {"key": "--prefix", "label": "编号前缀 如 2-3-5-6-", "type": "text"},
            {"key": "--apply", "label": "实际执行（不勾=仅预览）", "type": "flag"},
        ],
    },
    "renumber_files 重连贯编号": {
        "sub": "renumber_files", "short": "重连贯编号",
        "fields": [
            {"key": "--folder", "label": "目标文件夹", "type": "path"},
            {"key": "--start", "label": "起始编号", "type": "int", "default": 1},
            {"key": "--apply", "label": "实际执行（不勾=仅预览）", "type": "flag"},
        ],
    },
}


class PdfCommandPage(PageBase):
    """子页：单个 file_toolkit 子命令的动态参数表。"""

    def __init__(self, win, cmd_title):
        super().__init__(win)
        self.cmd_title = cmd_title
        spec = FILE_CMDS[cmd_title]
        _, g = self.group(f"{spec['sub']} —— {cmd_title.split(' ', 1)[-1]}")
        r = 0
        for f in spec["fields"]:
            key, typ, label = f["key"], f["type"], f["label"]
            obj_key = "ft." + key
            if typ in ("path", "file"):
                r = add_path_row(g, r, label, obj_key, "",
                                 is_file=(typ == "file"), page=self)
            elif typ == "text":
                r = add_text_row(g, r, label, obj_key, str(f.get("default", "")))
            elif typ == "int":
                g.addWidget(QLabel(label), r, 0)
                spin = QSpinBox()
                spin.setRange(0, 99999)
                spin.setValue(int(f.get("default", 1)))
                spin.setObjectName(obj_key)
                g.addWidget(spin, r, 1)
                r += 1
            elif typ == "stage":
                g.addWidget(QLabel(label), r, 0)
                wrap = QWidget()
                wl = QHBoxLayout(wrap)
                wl.setContentsMargins(0, 0, 0, 0)
                for text, flag in (("预览", ""), ("仅合并", "--merge"),
                                   ("仅铺平", "--flatten"), ("一步完成", "--all")):
                    rb = QCheckBox(text)
                    rb.setObjectName(obj_key + ":" + flag)
                    wl.addWidget(rb)
                g.addWidget(wrap, r, 1)
                r += 1
            elif typ == "flag":
                cb = QCheckBox(label)
                cb.setObjectName(obj_key)
                g.addWidget(cb, r, 1)
                r += 1
            elif typ in ("wide", "lines"):
                g.addWidget(QLabel(label), r, 0)
                txt = QPlainTextEdit()
                txt.setObjectName(obj_key)
                txt.setFixedHeight(72 if typ == "wide" else 96)
                if typ == "wide" and f.get("placeholder"):
                    txt.setPlaceholderText(str(f["placeholder"]))
                g.addWidget(txt, r, 1, 1, 2)
                r += 1
        btn = QPushButton("执 行")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._run)
        g.addWidget(btn, r, 1)
        self.win.register_button(btn)
        tip = QLabel("改名类命令默认仅预览，确认无误后勾选「实际执行」再跑一次。")
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        g.addWidget(tip, r + 1, 0, 1, 3)

    def _ft_line(self, key) -> str:
        w = self.win.findChild(QLineEdit, "ft." + key)
        return w.text().strip() if w else ""

    def _collect_args(self) -> list[str]:
        spec = FILE_CMDS[self.cmd_title]
        args = [spec["sub"]]
        for f in spec["fields"]:
            key, typ, label = f["key"], f["type"], f["label"]
            if typ == "path":
                v = self._ft_line(key)
                if not v:
                    raise ValueError(f"请填写「{label}」")
                args += [key, v] if key.startswith("--") else ["--" + key, v]
            elif typ == "text":
                v = self._ft_line(key)
                if v:
                    args += [key, v]
            elif typ == "int":
                from PySide6.QtWidgets import QSpinBox as _S
                w = self.win.findChild(_S, "ft." + key)
                v = str(w.value()) if w else ""
                if v:
                    args += [key, v]
            elif typ == "file":
                v = self._ft_line(key)
                if v:
                    args += [key, v]
                elif "(可选)" in label:
                    continue
                else:
                    raise ValueError(f"请填写「{label}」")
            elif typ == "stage":
                chosen = ""
                for flag in ("--all", "--flatten", "--merge"):
                    if self.checked("ft." + key + ":" + flag):
                        chosen = flag
                        break
                if chosen:
                    args.append(chosen)
            elif typ == "flag":
                if self.checked("ft." + key):
                    args.append(key)
            elif typ in ("wide", "lines"):
                from PySide6.QtWidgets import QPlainTextEdit as _T
                txt = self.win.findChild(_T, "ft." + key)
                if typ == "wide":
                    v = " ".join(txt.toPlainText().split()) if txt else ""
                    if not v:
                        raise ValueError(f"请填写「{label}」")
                    args += [key, v]
                else:
                    lines = ([ln.strip() for ln in txt.toPlainText().splitlines()
                              if ln.strip()] if txt else [])
                    if not lines:
                        raise ValueError(f"请填写「{label}」")
                    args += [key] + lines
        return args

    def _run(self):
        try:
            args = self._collect_args()
        except ValueError as exc:
            _warn(self.win, "参数不完整", str(exc))
            return
        self.win.launch_cli(f"file_toolkit {args[0]}", "底稿pdf材料",
                            "file_toolkit.py", args)


# ============================================================
# 主功能五：目录生成
# ============================================================
class DirgenPage(PageBase):
    """子页：Excel / Word 层级目录生成。"""

    def __init__(self, win):
        super().__init__(win)
        _, g = self.group("目录生成")
        r = add_path_row(g, 0, "目标文件夹", "dg.target")
        r = add_path_row(g, r, "Excel 目录输出", "dg.excel")
        r = add_path_row(g, r, "Word 目录输出", "dg.word")
        target_edit = self.findChild(QLineEdit, "dg.target")
        excel_edit = self.findChild(QLineEdit, "dg.excel")
        word_edit = self.findChild(QLineEdit, "dg.word")

        def auto_fill(*_a):
            t = target_edit.text().strip()
            if t and os.path.isdir(t):
                name = os.path.basename(t.rstrip("\\/"))
                parent = os.path.dirname(t)
                excel_edit.setText(os.path.join(parent, f"【{name}】目录.xlsx"))
                word_edit.setText(os.path.join(parent, f"【{name}】目录.docx"))

        target_edit.textChanged.connect(auto_fill)

        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        b1 = QPushButton("生成 Excel 目录")
        b1.setObjectName("Primary")
        b1.clicked.connect(lambda: self._run(excel_only=True))
        b2 = QPushButton("生成 Excel + Word 目录")
        b2.setObjectName("Primary")
        b2.clicked.connect(lambda: self._run(excel_only=False))
        self.win.register_button(b1)
        self.win.register_button(b2)
        wl.addWidget(b1)
        wl.addWidget(b2)
        g.addWidget(wrap, r, 0, 1, 3)
        self.note("说明：扫描目标文件夹的多级结构生成层级目录表（自动去空文件夹、"
                  "同编号去重、中文序号自然排序）；Word 版由 Excel 转出。"
                  "目标文件夹填写后自动带出输出路径，可手动修改。")

    def _run(self, excel_only):
        target = self.val("dg.target")
        excel = self.val("dg.excel")
        word = "" if excel_only else self.val("dg.word")
        if not target:
            _warn(self.win, "缺少路径", "请填写「目标文件夹」。")
            return
        if not os.path.isdir(target):
            _warn(self.win, "路径无效", f"「目标文件夹」不存在：\n{target}")
            return
        if not excel:
            _warn(self.win, "缺少路径", "请填写「Excel 目录输出」路径。")
            return
        self.win.launch_runner("生成目录", "dirgen",
                               {"target": target, "excel": excel,
                                "word": word or None})


# ============================================================
# 主功能区注册表
# ============================================================
def build_areas(win):
    """返回 [(主功能标题, 图标字符, [(子功能标题, 页面), ...]), ...]。"""
    pdf_subs = [(spec["short"], PdfCommandPage(win, title))
                for title, spec in FILE_CMDS.items()]
    return [
        ("签章页", "✍", [
            ("标准流程", SignFlowPage(win)),
            ("清单与路径", SignPathsPage(win)),
            ("初始化底稿", SignInitPage(win)),
        ]),
        ("底稿替换", "⇄", [
            ("生成规则表", RulesGenPage(win)),
            ("执行替换", ReplaceRunPage(win)),
        ]),
        ("文件整理", "🗂", [
            ("比较与合并", FolderComparePage(win)),
            ("提取打印文件", ExtractPrintPage(win)),
            ("提取非Word文件", ExtractNonWordPage(win)),
            ("信息统计", StatsPage(win)),
        ]),
        ("PDF材料", "📄", pdf_subs),
        ("目录生成", "📑", [
            ("Excel / Word 目录", DirgenPage(win)),
        ]),
    ]
