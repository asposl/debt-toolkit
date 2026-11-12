# 文件路径: views/integrity_check_ui.py
# 诚信核查截图界面（线程调度、日志队列、弹窗处理）
# 视觉层使用 views/theme.py 的设计 Token：卡片化布局、多列站点网格、进度条、彩色日志。

import json
import os
import queue
import re
import threading
import time
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog

from modules.scraper.async_func_dp import default, WEB_CONFIG, default_2, default_3
from modules.scraper.async_screenshot_dp import run_batch_screenshot_task
from modules.scraper.output_layout import new_run_dir
import run_state
import templates_store as store
from views import theme
from views.theme import ConfirmDialog, InputDialog, ToolTip

CHECKBOX_COLS = 3  # 站点复选框列数（32 个站点约 11 行收齐）

ID_PATTERN = re.compile(
    r"(?<![0-9A-Za-z])(?:\d{17}[\dXx]|\d{15}|[0-9A-Za-z]{18})(?![0-9A-Za-z])"
)


def parse_search_subject(raw_text):
    """从单个输入框中拆出名称和身份证/证件号，证件号可以为空。"""
    raw_text = raw_text.strip()
    match = ID_PATTERN.search(raw_text)
    id_card = match.group(0).upper() if match else ""

    name = raw_text
    if match:
        name = f"{raw_text[:match.start()]} {raw_text[match.end():]}"
    name = re.sub(r"[\s,，;；:：|/\\]+", " ", name).strip()

    return {
        "name": name,
        "id_card": id_card,
        "raw": raw_text,
        # 匿名键：状态文件/核验结果只认这个摘要，不落真实名称
        "key": run_state.company_key({"name": name, "id_card": id_card}),
    }


def format_subject_label(subject):
    if subject.get("id_card"):
        return f"{subject.get('name') or '(未识别名称)'}  {subject['id_card']}"
    return subject.get("name") or subject.get("raw") or "(空)"


class IntegrityCheckFrame(ctk.CTkFrame):
    def __init__(self, master, status_cb=None, counts_cb=None, **kwargs):
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)
        self.status_cb = status_cb      # 向主窗口状态栏推送运行状态 (text, kind)
        self.counts_cb = counts_cb      # 向主窗口状态栏推送计数文本

        # --- 数据初始化 ---
        self.log_queue = queue.Queue()
        # 输出目录默认落在「启动目录/output」，统一收口、避免污染源码树。
        # 该目录已被 .gitignore 忽略（output/ 及 GUI/*/），不入库、含个人数据可随时删。
        # batch_runner 在首跑时会用 makedirs(..., exist_ok=True) 自动创建。
        self.base_output_path = ctk.StringVar(value=os.path.join(os.getcwd(), "output"))
        self.checkboxes = {}
        self.companies_data = []
        self.custom_config = self._load_custom_sites()

        # 重跑核验：本轮任务快照 与 状态文件缓存（按输出目录惰性加载）
        self._pending_task = None
        self._pending_config = None
        self._pending_base = None
        self._state_cache = None
        self._state_cache_base = None

        # --- 整体布局：顶部两张卡片固定，下方 PanedWindow 占满剩余高度 ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.active_config = default_2  # 默认使用债券模板
        self.setup_ui()
        self._refresh_custom_menu()
        self.refresh_company_list()   # 初始渲染空态占位提示
        self.push_counts()

        # 【重要】初始化即启动监听循环，确保任务状态同步
        self.listen_to_queue()

    # ============================ 界面搭建 ============================
    def setup_ui(self):
        # 1. 卡片一：输出目录（固定高度）
        path_card, path_body, _ = theme.make_card(self, title="输出目录")
        path_card.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        self.path_entry = ctk.CTkEntry(
            path_body, textvariable=self.base_output_path,
            state="disabled", height=32, font=theme.f(13),
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.path_btn = ctk.CTkButton(
            path_body, text="选择目录", width=104, height=32,
            font=theme.f(13), command=self.select_folder,
        )
        self.path_btn.pack(side="right")

        # 2. 卡片二：核查输入（固定高度；进度条仅在任务运行期间显示）
        input_card, input_body, _ = theme.make_card(self, title="核查输入")
        input_card.grid(row=1, column=0, padx=16, pady=8, sticky="ew")
        input_body.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(input_body, mode="indeterminate", height=6)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.progress.grid_remove()   # 空闲时隐藏，开始核查时再显示

        row = ctk.CTkFrame(input_body, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")

        self.add_comp_entry = ctk.CTkEntry(
            row, placeholder_text="输入待核查对象",
            height=32, font=theme.f(13),
        )
        self.add_comp_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.add_comp_entry.bind("<Return>", self.add_company)
        ToolTip(self.add_comp_entry,
                "每行一个对象：名称 [证件号]，回车或点「添加」\n"
                "例：XX子公司（张三） 91320000MA1K35678X")

        self.add_comp_btn = ctk.CTkButton(
            row, text="➕ 添加", width=84, height=32, font=theme.f(13),
            command=self.add_company,
        )
        self.add_comp_btn.pack(side="left", padx=4)

        self.run_btn = ctk.CTkButton(
            row, text="▶ 开始核查", width=124, height=36,
            font=theme.f(13, bold=True),
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self.start_task,
        )
        self.run_btn.pack(side="right", padx=(8, 0))

        # 3. 可拖拽调高窗格（PanedWindow）：对象列表 / 核查范围 / 运行日志 三张卡片
        # 动态获取背景色，防止 "unknown color name r" 报错
        paned_bg = self._apply_appearance_mode(theme.BG)
        self.paned_window = tk.PanedWindow(
            self, orient="vertical", bg=paned_bg,
            sashwidth=6, bd=0, sashrelief="flat", showhandle=False,
        )
        self.paned_window.grid(row=2, column=0, padx=16, pady=(8, 16), sticky="nsew")

        # --- 窗格 A: 待核查对象 ---
        card_a, body_a, head_a = theme.make_card(self.paned_window, title="待核查对象")
        self.save_tpl_btn = ctk.CTkButton(
            head_a, text="💾 存为模板", width=96, height=22,
            font=theme.f(11), fg_color=theme.SUBTLE_BTN, hover_color=theme.SUBTLE_HOVER,
            text_color=("gray25", "#cfcfd8"), command=self.save_as_template,
        )
        self.save_tpl_btn.pack(side="right")
        ToolTip(self.save_tpl_btn, "把当前名单保存为模板（弹窗命名），可在「核查模板」页管理")
        self.obj_count_label = ctk.CTkLabel(
            head_a, text="", font=theme.f(11), text_color=theme.MUTED,
        )
        self.obj_count_label.pack(side="right", padx=(0, 10))
        self.paned_window.add(card_a, height=170, minsize=110, sticky="nsew")
        self.comp_list_frame = ctk.CTkScrollableFrame(body_a, fg_color="transparent")
        self.comp_list_frame.pack(fill="both", expand=True)

        # --- 窗格 B: 核查范围（全选工具条 + 自定义网站栏 + 多列复选框） ---
        card_b, body_b, head_b = theme.make_card(self.paned_window, title="核查范围")
        self.site_count_label = ctk.CTkLabel(
            head_b, text="", font=theme.f(11), text_color=theme.MUTED,
        )
        self.site_count_label.pack(side="right")
        self.paned_window.add(card_b, height=240, minsize=140, sticky="nsew")

        self.web_select_toolbar = ctk.CTkFrame(body_b, fg_color="transparent")
        self.web_select_toolbar.pack(fill="x", pady=(0, 6))
        self.select_all_btn = ctk.CTkButton(
            self.web_select_toolbar, text="全选", width=72, height=28,
            font=theme.f(12), fg_color=theme.SUBTLE_BTN, hover_color=theme.SUBTLE_HOVER,
            text_color=("gray20", "#e6e6ec"),
            command=lambda: self.set_all_checkboxes(True),
        )
        self.select_all_btn.pack(side="left", padx=(0, 6))
        self.clear_all_btn = ctk.CTkButton(
            self.web_select_toolbar, text="全不选", width=72, height=28,
            font=theme.f(12), fg_color=theme.SUBTLE_BTN, hover_color=theme.SUBTLE_HOVER,
            text_color=("gray20", "#e6e6ec"),
            command=lambda: self.set_all_checkboxes(False),
        )
        self.clear_all_btn.pack(side="left")
        self.select_failed_btn = ctk.CTkButton(
            self.web_select_toolbar, text="⚠ 仅选上次失败", width=116, height=28,
            font=theme.f(12), fg_color=theme.SUBTLE_BTN, hover_color=theme.SUBTLE_HOVER,
            text_color=("gray20", "#e6e6ec"),
            command=self.select_failed_sites,
        )
        self.select_failed_btn.pack(side="left", padx=(14, 6))
        ToolTip(self.select_failed_btn,
                "读取输出目录中的核验记录，仅勾选上次失败的网站；\n"
                "配合现有名单直接开始核查即可补跑缺图")
        self.clear_state_btn = ctk.CTkButton(
            self.web_select_toolbar, text="清除记录", width=84, height=28,
            font=theme.f(12), fg_color=theme.SUBTLE_BTN, hover_color=theme.SUBTLE_HOVER,
            text_color=("gray25", "#cfcfd8"),
            command=self.clear_run_history,
        )
        self.clear_state_btn.pack(side="right")
        ToolTip(self.clear_state_btn, "删除当前输出目录下的核验状态文件 _ibdw_state.json")

        # 方案选择与延时（与网站选择同区，从核查输入卡迁移而来）
        self.delay_entry = ctk.CTkEntry(
            self.web_select_toolbar, placeholder_text="延时(秒)",
            width=78, height=28, font=theme.f(12),
        )
        self.delay_entry.pack(side="right", padx=(6, 0))
        ToolTip(self.delay_entry, "每张截图前额外等待的秒数，可留空按默认节奏执行")
        self.preset_menu = ctk.CTkOptionMenu(
            self.web_select_toolbar,
            values=["债券模板", "董监高模板"],
            command=self.apply_preset,
            width=140, height=28, font=theme.f(12), dynamic_resizing=False,
        )
        self.preset_menu.pack(side="right")
        self.preset_menu.set("债券模板")  # 与初始 active_config 保持一致
        ToolTip(self.preset_menu,
                "切换内置站点方案（自定义网站始终附加在当前方案之上）\n"
                "董监高模板：证监会/失信名单/法律文书网/百度媒体 四站，对象为自然人")

        # 自定义网站管理栏：URL + 显示名 + 添加/删除
        self.custom_bar = ctk.CTkFrame(body_b, fg_color="transparent")
        self.custom_bar.pack(fill="x", pady=(0, 8))
        self.custom_url_entry = ctk.CTkEntry(
            self.custom_bar, height=30, font=theme.f(12),
            placeholder_text="自定义搜索URL（支持 www/站名开头或含{company}）…",
        )
        self.custom_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ToolTip(self.custom_url_entry, "支持 www 开头或包含 {company} 占位符的搜索链接，"
                                       "纯链接会自动在末尾拼接核查名称")
        self.custom_name_entry = ctk.CTkEntry(
            self.custom_bar, placeholder_text="显示名(可空)",
            width=120, height=30, font=theme.f(12),
        )
        self.custom_name_entry.pack(side="left", padx=(0, 5))
        self.custom_add_btn = ctk.CTkButton(
            self.custom_bar, text="➕ 添加自定义", width=104, height=30,
            font=theme.f(12), command=self.add_custom_site,
        )
        self.custom_add_btn.pack(side="left", padx=(0, 5))
        self.custom_manage_menu = ctk.CTkOptionMenu(
            self.custom_bar, values=["(无自定义网站)"], width=140, height=30,
            font=theme.f(12), dynamic_resizing=False,
            command=lambda _: None,
        )
        self.custom_manage_menu.pack(side="left", padx=(0, 5))
        ToolTip(self.custom_manage_menu,
                "列出已保存的自定义网站，选中后可删除；\n仅作用于自定义网站，内置站点不受影响")
        self.custom_del_btn = ctk.CTkButton(
            self.custom_bar, text="🗑 删除选中", width=96, height=30,
            font=theme.f(12), fg_color=theme.DANGER, hover_color="#a33b37",
            command=self.delete_custom_site,
        )
        self.custom_del_btn.pack(side="left")
        ToolTip(self.custom_del_btn,
                "仅删除选中的自定义网站（会先弹确认框）；\n内置站点不受影响，同名覆盖的自定义项删除后自动恢复内置原版")

        self.web_select_frame = ctk.CTkScrollableFrame(body_b, fg_color="transparent")
        self.web_select_frame.pack(fill="both", expand=True)
        self.render_checkboxes(self.active_config)  # 按当前方案渲染复选框（默认债券模板）

        # --- 窗格 C: 运行日志 ---
        card_c, body_c, head_c = theme.make_card(self.paned_window, title="运行日志")
        clear_btn = ctk.CTkButton(
            head_c, text="清空", width=56, height=22,
            font=theme.f(11), fg_color=theme.SUBTLE_BTN, hover_color=theme.SUBTLE_HOVER,
            text_color=("gray25", "#cfcfd8"), command=self.clear_log,
        )
        clear_btn.pack(side="right")
        self.paned_window.add(card_c, height=200, minsize=110, sticky="nsew")
        self.log_textbox = ctk.CTkTextbox(
            body_c, font=theme.f(12, mono=True), wrap="word",
        )
        self.log_textbox.pack(fill="both", expand=True)
        theme.setup_log_tags(self.log_textbox)
        self.log_textbox.configure(state="disabled")

    def sync_paned_bg(self):
        """外观模式切换后同步 PanedWindow 分隔条颜色（原生 tk 控件不会自动跟随）。"""
        try:
            self.paned_window.configure(bg=self._apply_appearance_mode(theme.BG))
        except Exception:
            pass

    # ============================ 站点渲染 ============================
    def render_checkboxes(self, target_config=WEB_CONFIG):
        """动态渲染网页选择列表（多列网格；接受不同的字典作为数据源）。"""
        # 1. 销毁旧的 UI 控件
        for widget in self.web_select_frame.winfo_children():
            widget.destroy()

        # 2. 清空后台记录的复选框字典，防止旧数据残留
        self.checkboxes.clear()

        for col in range(CHECKBOX_COLS):
            self.web_select_frame.grid_columnconfigure(col, weight=1)

        # 3. 合并自定义网站后，重新生成全新的复选框
        merged = {**target_config, **self.custom_config}
        for i, site_name in enumerate(merged.keys()):
            cb = ctk.CTkCheckBox(
                self.web_select_frame, text=site_name,
                font=theme.f(12), checkbox_width=18, checkbox_height=18,
                corner_radius=5, fg_color=theme.ACCENT,
                hover_color=theme.ACCENT_HOVER,
                command=self.push_counts,
            )
            cb.grid(row=i // CHECKBOX_COLS, column=i % CHECKBOX_COLS,
                    padx=(4, 14), pady=3, sticky="w")
            cb.select()  # 生成时默认全选
            self.checkboxes[site_name] = cb
        self.push_counts()

    def set_all_checkboxes(self, checked):
        """一键全选或全不选当前方案下的网页。"""
        for cb in self.checkboxes.values():
            if checked:
                cb.select()
            else:
                cb.deselect()
        self.push_counts()  # select()/deselect() 不触发 command，手动刷新计数

    def apply_preset(self, choice):
        """应用快捷方案逻辑（仅两套内置方案；自定义网站始终附加在当前方案之上）。"""
        if choice == "董监高模板":
            self.active_config = default_3
            self.render_checkboxes(default_3)
            self.write_log(">>> 已切换至 [董监高模板]，核查网页列表已更新（对象为自然人：姓名 证件号）。\n")
        elif choice == "债券模板":
            self.active_config = default_2
            self.render_checkboxes(default_2)
            self.write_log(">>> 已切换至 [债券模板]，核查网页列表已更新。\n")
        # 其余 choice 静默忽略（防御历史残留值）

    # ============================ 计数联动 ============================
    def push_counts(self):
        """刷新卡片角标与主窗口状态栏的对象/站点计数。"""
        sel = sum(1 for cb in self.checkboxes.values() if cb.get() == 1)
        total = len(self.checkboxes)
        n_obj = len(self.companies_data)
        if hasattr(self, "site_count_label"):
            self.site_count_label.configure(text=f"已选 {sel}/{total}")
        if hasattr(self, "obj_count_label"):
            self.obj_count_label.configure(text=f"{n_obj} 个对象")
        if self.counts_cb:
            self.counts_cb(f"对象 {n_obj} · 站点 {sel}/{total}")

    # ============================ 重跑核验 ============================
    def save_as_template(self):
        """把当前名单保存为模板（弹窗命名；重名自动加序号）。"""
        if not self.companies_data:
            self.write_log(">>> [提示] 名单为空，请先添加待核查对象再保存模板。\n")
            return
        dlg = InputDialog(self.winfo_toplevel(), "保存为模板",
                          "请输入模板名称：", placeholder="例如：苏垦农发2026")
        self.wait_window(dlg)
        name = dlg.result
        if not name:
            return
        self._save_template_named(name)

    def _save_template_named(self, name):
        """按给定名称保存当前名单为模板（供对话框与测试复用）。"""
        templates = store.load_templates()
        names = {t.get("name") for t in templates}
        base, i = name, 2
        while name in names:
            name = f"{base} {i}"
            i += 1
        renamed = name != base
        entries = [{"raw": c.get("raw", ""), "name": c.get("name", ""),
                    "id_card": c.get("id_card", ""), "code": c.get("code", "")}
                   for c in self.companies_data]
        templates.append({"name": name, "updated_at": store.now_stamp(),
                          "companies": entries})
        try:
            store.save_templates(templates)
        except Exception as exc:
            self.write_log(f">>> [错误] 模板保存失败：{repr(exc)}\n")
            return
        if renamed:
            self.write_log(f">>> [提示] 名称与现有模板重复，已自动命名为「{name}」。\n")
        self.write_log(f">>> [成功] 已保存模板「{name}」：{len(entries)} 个对象"
                       f"（可在「核查模板」页管理或载入）。\n")

    def _current_state(self):
        """按输出目录惰性缓存状态文件内容。"""
        base = self.base_output_path.get()
        if self._state_cache_base != base or self._state_cache is None:
            self._state_cache_base = base
            self._state_cache = run_state.load_state(base)
        return self._state_cache

    def _finalize_run_verification(self):
        """DONE 后：核验本轮产出 → 合并历史 → 原子落盘 → 刷新行徽章。"""
        task = self._pending_task
        self._pending_task = None
        if not task:
            return
        try:
            verdict = run_state.verify_run(task, self._pending_config)
            state = run_state.load_state(self._pending_base)
            counts = verdict["counts"]
            summary = {
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_pairs": sum(counts.values()),
                "ok": counts["ok"], "fail": counts["fail"], "unknown": counts["unknown"],
            }
            run_state.merge_results(state, verdict["results"], summary)
            saved = run_state.save_state(self._pending_base, state)
            self._state_cache_base = self._pending_base
            self._state_cache = state
            self.refresh_company_list()
            note = "状态已保存" if saved else "状态保存失败"
            self.write_log(
                f">>> [系统] 本轮核验：成功{counts['ok']} 失败{counts['fail']} "
                f"未判定{counts['unknown']}（{note}，可点「⚠ 仅选上次失败」补跑缺图）\n"
            )
        except Exception as exc:
            self.write_log(f">>> [提示] 本轮核验失败，不影响截图结果：{repr(exc)}\n")

    def select_failed_sites(self):
        """按历史记录勾选现存公司范围内失败过的站点（其余取消）。"""
        state = self._current_state()
        keys = [c.get("key") for c in self.companies_data]
        failed = run_state.failed_sites_for(state.get("results"), keys)
        if not failed:
            self.write_log(">>> [提示] 当前名单没有失败记录（先跑一轮，或确认输出目录正确）。\n")
            return
        known = set(self.checkboxes)
        targets = failed & known
        skipped = len(failed) - len(targets)
        for name, cb in self.checkboxes.items():
            if name in targets:
                cb.select()
            else:
                cb.deselect()
        self.push_counts()
        msg = f">>> 已按失败记录勾选 {len(targets)} 个站点，其余已取消勾选。"
        if skipped:
            msg += f"（另有 {skipped} 个失败站点不在当前方案中，已跳过）"
        self.write_log(msg + "\n")

    def clear_run_history(self):
        base = self.base_output_path.get()
        if run_state.clear_state(base):
            self._state_cache = run_state.empty_state()
            self.refresh_company_list()
            self.write_log(f">>> [系统] 已清除核验记录（{run_state.state_path(base)}）。\n")
        else:
            self.write_log(">>> [错误] 清除核验记录失败。\n")

    @staticmethod
    def _result_badge(per_site):
        """由单公司各站点状态计算行徽章文案/颜色/失败明细。"""
        ok_n = sum(1 for st in per_site.values() if st == run_state.STATUS_OK)
        fail_names = [s for s, st in per_site.items() if st == run_state.STATUS_FAIL]
        un_n = sum(1 for st in per_site.values() if st == run_state.STATUS_UNKNOWN)
        parts = []
        if ok_n:
            parts.append(f"✅{ok_n}")
        if fail_names:
            parts.append(f"❌{len(fail_names)}")
        if un_n:
            parts.append(f"❔{un_n}")
        color = "#ef4444" if fail_names else ("#94a3b8" if un_n == len(per_site) else "#22c55e")
        return "·".join(parts), color, fail_names

    # ============================ 自定义网站管理 ============================
    def _custom_sites_path(self):
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "custom_sites.json",
        )

    def _load_custom_sites(self):
        path = self._custom_sites_path()
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as fobj:
                    data = json.load(fobj)
                if isinstance(data, list):
                    result = {}
                    for item in data:
                        if isinstance(item, dict) and item.get("name") and item.get("url"):
                            result[str(item["name"])] = {
                                "url": str(item["url"]),
                                "action": None,
                                "post_action": None,
                                "query_mode": item.get("query_mode", "name"),
                            }
                    return result
        except Exception as exc:
            # 注意：此方法在 setup_ui 之前调用，日志框尚不存在，不能用 write_log
            print(f"[提示] 加载自定义网站失败: {repr(exc)}")
        return {}

    def _save_custom_sites(self):
        path = self._custom_sites_path()
        try:
            payload = [
                {"name": name, "url": v.get("url"), "query_mode": v.get("query_mode", "name")}
                for name, v in self.custom_config.items()
            ]
            with open(path, "w", encoding="utf-8") as fobj:
                json.dump(payload, fobj, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.write_log(f">>> [提示] 保存自定义网站失败: {repr(exc)}\n")

    def _site_name_taken(self, name):
        if name in self.custom_config:
            return True
        for cfg in (WEB_CONFIG, default, default_2, default_3):
            if name in cfg:
                return True
        return False

    def _default_custom_name(self, url):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url if "://" in url else "https://" + url)
            domain = parsed.netloc or url
        except Exception:
            domain = url
        base = f"自定义: {domain}"
        name, idx = base, 1
        while self._site_name_taken(name):
            idx += 1
            name = f"{base} ({idx})"
        return name

    def _refresh_custom_menu(self):
        names = list(self.custom_config.keys())
        if names:
            self.custom_manage_menu.configure(values=names)
            self.custom_manage_menu.set(names[0])
        else:
            self.custom_manage_menu.configure(values=["(无自定义网站)"])
            self.custom_manage_menu.set("(无自定义网站)")

    def add_custom_site(self):
        raw_url = self.custom_url_entry.get().strip()
        if not raw_url:
            self.write_log(">>> [错误] 请输入自定义搜索 URL。\n")
            return
        if any(ch.isspace() for ch in raw_url):
            self.write_log(">>> [错误] URL 不能包含空格。\n")
            return
        name = self.custom_name_entry.get().strip()
        is_replace = False
        if not name:
            name = self._default_custom_name(raw_url)
        elif self._site_name_taken(name):
            # 与已存在网站同名 → 直接替换（自定义配置覆盖同名内置网站，
            # 典型场景：替换「2、发行人所属地方政府网站」为当期项目对应的政府网站）
            is_replace = True
        self.custom_config[name] = {
            "url": raw_url,
            "action": None,
            "post_action": None,
            "query_mode": "name",
        }
        self._save_custom_sites()
        self.render_checkboxes(self.active_config)
        self._refresh_custom_menu()
        self.custom_url_entry.delete(0, "end")
        self.custom_name_entry.delete(0, "end")
        if is_replace:
            self.write_log(f">>> 已替换网站 [{name}]，新URL：{raw_url}（删除该自定义项可恢复原配置）\n")
        else:
            self.write_log(f">>> 已添加自定义网站 [{name}]：{raw_url}\n")

    def delete_custom_site(self):
        selected = self.custom_manage_menu.get()
        if not selected or selected == "(无自定义网站)" or selected not in self.custom_config:
            self.write_log(">>> [提示] 没有可删除的自定义网站。\n")
            return
        url = str(self.custom_config[selected].get("url") or "")
        dlg = ConfirmDialog(self.winfo_toplevel(), "删除自定义网站",
                            f"确定删除自定义网站「{selected}」？\nURL：{url}")
        self.wait_window(dlg)
        if not dlg.result:
            return
        self.custom_config.pop(selected)
        self._save_custom_sites()
        self.render_checkboxes(self.active_config)
        self._refresh_custom_menu()
        self.write_log(
            f">>> 已删除自定义网站 [{selected}]（URL：{url}）。\n"
            f">>> [提示] 如需恢复，请用相同 URL 重新添加；同名覆盖的内置站点已自动恢复原版。\n")

    # ============================ 核查对象列表 ============================
    def add_company(self, event=None):
        raw_value = self.add_comp_entry.get().strip()
        subject = parse_search_subject(raw_value)
        existing_keys = {item.get("key") for item in self.companies_data}
        if raw_value and subject["key"] not in existing_keys:
            self.companies_data.append(subject)
            self.refresh_company_list()
        self.add_comp_entry.delete(0, "end")

    def refresh_company_list(self):
        for widget in self.comp_list_frame.winfo_children():
            widget.destroy()

        if not self.companies_data:
            ctk.CTkLabel(
                self.comp_list_frame,
                text="尚无核查对象 — 在上方输入后回车或点击「➕ 添加」",
                font=theme.f(12), text_color=theme.MUTED,
            ).pack(pady=18)
            self.push_counts()
            return

        normal_bg = theme.CARD_INNER
        hover_bg = ("gray90", "#32323f")
        state = self._current_state()
        for idx, comp in enumerate(self.companies_data, start=1):
            row = ctk.CTkFrame(self.comp_list_frame, corner_radius=8, fg_color=normal_bg)
            row.pack(fill="x", pady=3, padx=2)

            badge = ctk.CTkLabel(
                row, text=str(idx), width=26, height=26, corner_radius=13,
                fg_color=theme.ACCENT, text_color="#ffffff", font=theme.f(11, bold=True),
            )
            badge.pack(side="left", padx=(8, 7), pady=4)

            name_lbl = ctk.CTkLabel(
                row, text=comp.get("name") or "(未识别名称)",
                font=theme.f(13, bold=True), anchor="w",
            )
            name_lbl.pack(side="left", padx=(0, 10))

            widgets_to_hover = [row, badge, name_lbl]
            if comp.get("id_card"):
                id_lbl = ctk.CTkLabel(
                    row, text=comp["id_card"], font=theme.f(11),
                    text_color=theme.MUTED,
                )
                id_lbl.pack(side="left")
                widgets_to_hover.append(id_lbl)

            del_btn = ctk.CTkButton(
                row, text="✕", width=28, height=26, corner_radius=13,
                fg_color="transparent", hover_color=("gray85", "#3a3a48"),
                text_color=theme.MUTED, border_width=0, font=theme.f(12, bold=True),
                command=lambda k=comp.get("key"): self.remove_company(k),
            )
            del_btn.pack(side="right", padx=8)

            # 上次核验结果徽章（有历史记录时才显示）
            per_site = (state.get("results") or {}).get(comp.get("key")) or {}
            if per_site:
                badge_text, badge_color, fail_names = self._result_badge(per_site)
                res_badge = ctk.CTkLabel(
                    row, text=badge_text, font=theme.f(11), text_color=badge_color,
                )
                res_badge.pack(side="right", padx=(0, 4))
                tip = ("上次失败：\n" + "\n".join(fail_names)) if fail_names else "上次核验全部成功"
                ToolTip(res_badge, tip)

            for wdg in widgets_to_hover:
                wdg.bind("<Enter>", lambda _e, r=row: r.configure(fg_color=hover_bg),
                         add="+")
                wdg.bind("<Leave>", lambda _e, r=row: r.configure(fg_color=normal_bg),
                         add="+")
        self.push_counts()

    def remove_company(self, comp_key):
        original_len = len(self.companies_data)
        self.companies_data = [item for item in self.companies_data if item.get("key") != comp_key]
        if len(self.companies_data) != original_len:
            self.refresh_company_list()

    # ============================ 任务调度 ============================
    def start_task(self):
        selected_sites = [name for name, cb in self.checkboxes.items() if cb.get() == 1]
        if not self.companies_data or not selected_sites:
            self.write_log(">>> [错误] 请确保已添加核查对象并至少勾选一个网页\n")
            return

        # 手动延时参数：可留空（按原逻辑运行），填写则每张截图前额外等待指定秒数
        delay_raw = self.delay_entry.get().strip()
        extra_delay = 0.0
        if delay_raw:
            try:
                extra_delay = max(0.0, float(delay_raw))
            except ValueError:
                self.write_log(">>> [错误] 延时参数必须是数字（单位：秒），也可以留空。\n")
                return

        self.run_btn.configure(state="disabled", text="正在核查…")
        self.progress.grid()      # 运行期间显示进度条
        self.progress.start()
        if self.status_cb:
            self.status_cb("正在核查…", "run")

        # 合并自定义网站后传给爬虫线程
        merged_config = {**self.active_config, **self.custom_config}
        # 每轮独立目录：run_<时间戳>/subj_NNN，路径里不出现主体名称
        base_output = self.base_output_path.get()
        run_dir = new_run_dir(base_output)
        # 快照本轮核验范围（公司×站点）与起始时间，DONE 后用于文件核验
        self._pending_base = base_output
        self._pending_config = merged_config
        self._pending_task = run_state.build_task(
            list(self.companies_data), selected_sites, run_dir)
        thread = threading.Thread(
            target=run_batch_screenshot_task,
            args=(list(self.companies_data), self.log_queue, base_output,
                  selected_sites, merged_config, extra_delay, run_dir),
            daemon=True,
        )
        thread.start()

    def listen_to_queue(self):
        """保持常驻的监听逻辑，防止重复调用导致主循环卡死"""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if msg == "DONE":
                    # 收到任务完成信号，恢复按钮、隐藏进度条
                    self.run_btn.configure(state="normal", text="▶ 开始核查")
                    self.progress.stop()
                    self.progress.set(0)
                    self.progress.grid_remove()
                    if self.status_cb:
                        self.status_cb("就绪", "idle")
                    # 核验本轮产出并持久化（失败不影响截图结果）
                    self._finalize_run_verification()
                    self.write_log(">>> [系统] 任务全部完成，已可开始新任务。\n")
                elif isinstance(msg, tuple) and msg[0] == "CONFIRM":
                    payload = msg[1]
                    dialog = ConfirmDialog(
                        self.winfo_toplevel(),
                        payload.get("title", "请确认"),
                        payload.get("message", "确认后继续执行。"),
                    )
                    self.wait_window(dialog)
                    payload["result"] = bool(dialog.result)
                    payload["event"].set()
                else:
                    self.write_log(msg)
        except queue.Empty:
            pass
        # 每100毫秒递归调用，确保 listen 永远活着
        self.after(100, self.listen_to_queue)

    # ============================ 日志 ============================
    def write_log(self, text):
        theme.append_log(self.log_textbox, text)

    def clear_log(self):
        theme.clear_logbox(self.log_textbox)

    # ============================ 目录选择 ============================
    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.base_output_path.set(folder)
