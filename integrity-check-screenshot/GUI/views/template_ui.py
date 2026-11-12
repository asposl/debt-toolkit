# 文件路径: views/template_ui.py
# 核查模板页：创建/选择/保存常用公司（或高管）名单，每行可携带编号代码；
# 一键把名单载入主核查界面。存储于 GUI/check_templates.json。

import copy
import customtkinter as ctk

import templates_store as store
from views import theme
from views.theme import ConfirmDialog, ToolTip


class TemplateFrame(ctk.CTkFrame):
    def __init__(self, master, status_cb=None, load_cb=None, **kwargs):
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)
        self.status_cb = status_cb      # 主窗口状态栏 (text, kind)
        self.load_cb = load_cb          # 载入回调：load_cb(subjects) → 主界面切页并替换名单
        self.templates = store.load_templates()
        self.current_index = -1         # 当前编辑的模板下标，-1=未选择

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_ui()
        self.refresh_list()
        if self.templates:
            self.select_template(0)

    # ============================ 界面 ============================
    def setup_ui(self):
        # ---- 左列：模板列表 ----
        list_card, list_body, head_l = theme.make_card(self, title="我的模板")
        list_card.grid(row=0, column=0, sticky="nsw", padx=(16, 8), pady=16)
        ctk.CTkLabel(head_l, text=f"共 {len(self.templates)} 个",
                     font=theme.f(11), text_color=theme.MUTED).pack(side="right")
        list_body.configure(width=230)
        self.list_frame = ctk.CTkScrollableFrame(list_body, fg_color="transparent",
                                                 width=220)
        self.list_frame.pack(fill="both", expand=True)

        # ---- 右列：编辑区 ----
        edit_card, body_e, _ = theme.make_card(self, title="模板内容")
        edit_card.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        body_e.grid_columnconfigure(0, weight=1)
        body_e.rowconfigure(1, weight=1)

        name_row = ctk.CTkFrame(body_e, fg_color="transparent")
        name_row.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(name_row, text="模板名:", font=theme.f(13)).pack(side="left")
        self.name_entry = ctk.CTkEntry(name_row, height=32, font=theme.f(13),
                                       placeholder_text="例如：苏垦农发2025年报")
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.roster_box = ctk.CTkTextbox(body_e, font=theme.f(12, mono=True), wrap="none")
        self.roster_box.grid(row=1, column=0, sticky="nsew", pady=(10, 4))
        ToolTip(self.roster_box,
                "每行一个对象：[编号] 名称 [证件号]\n"
                "例：  1-3-1-3-1 XX子公司（张三） 91320000MEDKJ8XP\n"
                "　　　李四 110101199001011234\n"
                "编号形如 数字-数字 才会被识别；支持从 Excel 直接粘贴多行。")

        ctk.CTkLabel(body_e, text="编号将用于「核查说明生成」页的 docx 文件名前缀；"
                                 "不带编号的对象按原文件名生成。",
                     font=theme.f(11), text_color=theme.MUTED, anchor="w"
                     ).grid(row=2, column=0, sticky="w", pady=(0, 8))

        btns = ctk.CTkFrame(body_e, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        sub_btn_kw = dict(height=30, font=theme.f(12),
                          fg_color=theme.SUBTLE_BTN, hover_color=theme.SUBTLE_HOVER,
                          text_color=("gray20", "#e6e6ec"))
        ctk.CTkButton(btns, text="💾 保存修改", width=104,
                      fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                      height=30, font=theme.f(12, bold=True),
                      command=self.save_current).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="➕ 新建", width=76, command=self.new_template,
                      **sub_btn_kw).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="📄 复制", width=76, command=self.duplicate_current,
                      **sub_btn_kw).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="🗑 删除", width=76, command=self.delete_current,
                      fg_color=theme.DANGER, hover_color="#a33b37",
                      height=30, font=theme.f(12)).pack(side="left", padx=(0, 12))
        ctk.CTkButton(btns, text="↗ 载入到核查页 ▶", width=140,
                      fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                      height=32, font=theme.f(12, bold=True),
                      command=self.load_to_check).pack(side="right")

        # ---- 底部：运行日志 ----
        log_card, log_body, log_head = theme.make_card(self, title="操作日志")
        log_card.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 16))
        clear_btn = ctk.CTkButton(
            log_head, text="清空", width=56, height=22,
            font=theme.f(11), fg_color=theme.SUBTLE_BTN, hover_color=theme.SUBTLE_HOVER,
            text_color=("gray25", "#cfcfd8"), command=self.clear_log,
        )
        clear_btn.pack(side="right")
        self.log_textbox = ctk.CTkTextbox(log_body, height=110,
                                          font=theme.f(12, mono=True), wrap="word")
        self.log_textbox.pack(fill="both", expand=True)
        theme.setup_log_tags(self.log_textbox)
        self.log_textbox.configure(state="disabled")

    # ============================ 列表渲染 ============================
    def refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        for idx, t in enumerate(self.templates):
            selected = idx == self.current_index
            row = ctk.CTkFrame(
                self.list_frame, corner_radius=8,
                fg_color=theme.ACCENT if selected else "transparent",
            )
            row.pack(fill="x", pady=2)
            n = len(t.get("companies") or [])
            ctk.CTkLabel(
                row, text=t.get("name") or "(未命名)",
                font=theme.f(12, bold=selected), anchor="w",
                text_color="#ffffff" if selected else ("gray10", "#e6e6ec"),
            ).pack(fill="x", padx=10, pady=(6, 0))
            ctk.CTkLabel(
                row,
                text=f"{n} 个对象 · {t.get('updated_at') or '未保存'}",
                font=theme.f(10), anchor="w",
                text_color="#dff5ea" if selected else theme.MUTED,
            ).pack(fill="x", padx=10, pady=(0, 6))
            for w in (row, *row.winfo_children()):
                w.bind("<Button-1>", lambda _e, i=idx: self.select_template(i), add="+")

    def select_template(self, index):
        if not (0 <= index < len(self.templates)):
            return
        self.current_index = index
        t = self.templates[index]
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, t.get("name") or "")
        self.roster_box.configure(state="normal")
        self.roster_box.delete("1.0", "end")
        self.roster_box.insert("1.0", store.serialize_roster(t.get("companies")))
        self.refresh_list()

    # ============================ 编辑动作 ============================
    def _collect_editor(self):
        """读取编辑区 → (name, entries)。"""
        name = self.name_entry.get().strip()
        text = self.roster_box.get("1.0", "end")
        return name, store.parse_roster(text)

    def save_current(self):
        if not (0 <= self.current_index < len(self.templates)):
            self.write_log(">>> [提示] 请先在左侧选择（或新建）一个模板。\n")
            return
        name, entries = self._collect_editor()
        if not name:
            self.write_log(">>> [错误] 模板名不能为空。\n")
            return
        t = self.templates[self.current_index]
        t["name"] = name
        t["companies"] = entries
        t["updated_at"] = store.now_stamp()
        try:
            store.save_templates(self.templates)
        except Exception as exc:
            self.write_log(f">>> [错误] 保存失败：{repr(exc)}\n")
            return
        with_code = sum(1 for e in entries if e["code"])
        self.write_log(f">>> [成功] 已保存模板「{name}」：{len(entries)} 个对象"
                       f"（含编号 {with_code} 个）。\n")
        self.refresh_list()

    def new_template(self):
        base = "新模板"
        names = {t.get("name") for t in self.templates}
        name, i = base, 2
        while name in names:
            name = f"{base}{i}"
            i += 1
        self.templates.append({"name": name, "updated_at": "",
                               "companies": []})
        self.current_index = len(self.templates) - 1
        self.refresh_list()
        self.select_template(self.current_index)
        self.name_entry.focus_set()
        self.name_entry.select_range(0, "end")

    def duplicate_current(self):
        if not (0 <= self.current_index < len(self.templates)):
            self.write_log(">>> [提示] 请先选择要复制的模板。\n")
            return
        clone = copy.deepcopy(self.templates[self.current_index])
        clone["name"] = f"{clone.get('name') or '未命名'} 副本"
        clone["updated_at"] = ""
        self.templates.append(clone)
        try:
            store.save_templates(self.templates)
        except Exception as exc:
            self.write_log(f">>> [错误] 保存失败：{repr(exc)}\n")
            return
        self.current_index = len(self.templates) - 1
        self.refresh_list()
        self.write_log(f">>> [成功] 已复制为「{clone['name']}」。\n")

    def delete_current(self):
        if not (0 <= self.current_index < len(self.templates)):
            self.write_log(">>> [提示] 请先选择要删除的模板。\n")
            return
        name = self.templates[self.current_index].get("name")
        dlg = ConfirmDialog(self.winfo_toplevel(), "删除模板",
                            f"确定删除模板「{name}」？该操作不可撤销。")
        self.wait_window(dlg)
        if not dlg.result:
            return
        self.templates.pop(self.current_index)
        try:
            store.save_templates(self.templates)
        except Exception as exc:
            self.write_log(f">>> [错误] 保存失败：{repr(exc)}\n")
            return
        self.current_index = -1
        self.name_entry.delete(0, "end")
        self.roster_box.delete("1.0", "end")
        self.refresh_list()
        self.write_log(f">>> [系统] 已删除模板「{name}」。\n")

    # ============================ 载入到核查页 ============================
    def load_to_check(self):
        if not (0 <= self.current_index < len(self.templates)):
            self.write_log(">>> [提示] 请先选择要载入的模板。\n")
            return
        subjects = store.to_subjects(self.templates[self.current_index]["companies"])
        if not subjects:
            self.write_log(">>> [提示] 该模板名单为空。\n")
            return
        if self.load_cb:
            self.load_cb(subjects)
        self.write_log(f">>> [成功] 已载入 {len(subjects)} 个对象到核查页"
                       f"（编号信息已随行携带，供说明生成使用）。\n")

    # ============================ 日志 ============================
    def write_log(self, text):
        theme.append_log(self.log_textbox, text)

    def clear_log(self):
        theme.clear_logbox(self.log_textbox)
