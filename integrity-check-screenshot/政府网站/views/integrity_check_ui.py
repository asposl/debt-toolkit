import os
import queue
import re
import threading
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox


from modules.scraper.async_func_dp import default, WEB_CONFIG,default_2
  # 导入你新建的 default 字典
from modules.scraper.async_screenshot_dp import run_batch_screenshot_task 

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
        "key": f"{name}|{id_card}",
    }


def format_subject_label(subject):
    if subject.get("id_card"):
        return f"{subject.get('name') or '(未识别名称)'}  {subject['id_card']}"
    return subject.get("name") or subject.get("raw") or "(空)"


class IntegrityCheckFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)
        
        # --- 数据初始化 ---
        self.log_queue = queue.Queue()
        self.base_output_path = ctk.StringVar(value=os.getcwd())
        self.checkboxes = {}
        self.companies_data = [] 

        # --- 整体布局：顶层固定，中下层可调节 ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1) # 让 PanedWindow 占满剩余高度
        self.active_config = WEB_CONFIG
        self.setup_ui()
        
        # 【重要】初始化即启动监听循环，确保任务状态同步
        self.listen_to_queue()

    def setup_ui(self):
        # 1. 顶部：路径选择 (固定高度)
        self.path_section = ctk.CTkFrame(self, fg_color="transparent")
        self.path_section.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        
        self.path_entry = ctk.CTkEntry(self.path_section, textvariable=self.base_output_path, state="disabled")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.path_btn = ctk.CTkButton(self.path_section, text="选择目录", width=100, command=self.select_folder)
        self.path_btn.pack(side="right")

        # 2. 中部：输入、添加、方案选择、开始按钮 (固定高度)
        # 这里是“➕ 添加”按钮所在的位置，确保它使用 pack 布局且不被遮挡
        self.input_section = ctk.CTkFrame(self, fg_color="transparent")
        self.input_section.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        
        self.add_comp_entry = ctk.CTkEntry(self.input_section, placeholder_text="输入名称/姓名 身份证号（身份证可为空）...")
        self.add_comp_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.add_comp_entry.bind("<Return>", self.add_company)
        
        # 找回这个按钮
        self.add_comp_btn = ctk.CTkButton(self.input_section, text="➕ 添加", width=70, command=self.add_company)
        self.add_comp_btn.pack(side="left", padx=5)
        
        # 快捷方案下拉菜单
        self.preset_menu = ctk.CTkOptionMenu(
            self.input_section, 
            values=["自定义手动选择", "默认配置方案", "债券模板"], # <--- 这里加上新选项
            command=self.apply_preset,
            width=130
        )
        self.preset_menu.pack(side="left", padx=5)
        
        self.run_btn = ctk.CTkButton(self.input_section, text="▶ 开始核查", fg_color="#2FA572", hover_color="#106A43", command=self.start_task)
        self.run_btn.pack(side="right", padx=(5, 0))

        # 3. 下部：可调高度窗格 (PanedWindow)
        # 动态获取背景色，防止 "unknown color name r" 报错
        current_bg = self._apply_appearance_mode(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
        self.paned_window = tk.PanedWindow(self, orient='vertical', bg=current_bg, sashwidth=4, bd=0)
        self.paned_window.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="nsew")

        # --- 窗格 A: 公司列表容器 ---
        self.container_a = ctk.CTkFrame(self.paned_window, fg_color="transparent")
        self.paned_window.add(self.container_a, height=150) # 设置初始高度
        self.comp_list_frame = ctk.CTkScrollableFrame(self.container_a, label_text="待核查公司列表")
        self.comp_list_frame.pack(fill="both", expand=True)

        # --- 窗格 B: 网页选择容器 ---
        self.container_b = ctk.CTkFrame(self.paned_window, fg_color="transparent")
        self.paned_window.add(self.container_b, height=200)
        self.web_select_toolbar = ctk.CTkFrame(self.container_b, fg_color="transparent")
        self.web_select_toolbar.pack(fill="x", padx=4, pady=(0, 6))
        self.select_all_btn = ctk.CTkButton(
            self.web_select_toolbar,
            text="全选",
            width=70,
            command=lambda: self.set_all_checkboxes(True),
        )
        self.select_all_btn.pack(side="left", padx=(0, 6))
        self.clear_all_btn = ctk.CTkButton(
            self.web_select_toolbar,
            text="全不选",
            width=70,
            command=lambda: self.set_all_checkboxes(False),
        )
        self.clear_all_btn.pack(side="left")
        self.web_select_frame = ctk.CTkScrollableFrame(self.container_b, label_text="选择核查范围")
        self.web_select_frame.pack(fill="both", expand=True)
        self.render_checkboxes() # 渲染复选框

        # --- 窗格 C: 日志输出容器 ---
        self.container_c = ctk.CTkFrame(self.paned_window, fg_color="transparent")
        self.paned_window.add(self.container_c, height=200)
        self.log_textbox = ctk.CTkTextbox(self.container_c, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_textbox.pack(fill="both", expand=True)
        self.log_textbox.configure(state="disabled")

    def render_checkboxes(self, target_config=WEB_CONFIG):
        """动态渲染网页选择列表（接受不同的字典作为数据源）"""
        # 1. 销毁旧的 UI 控件
        for widget in self.web_select_frame.winfo_children():
            widget.destroy()
            
        # 2. 清空后台记录的复选框字典，防止旧数据残留
        self.checkboxes.clear() 
        
        # 3. 根据传入的字典，重新生成全新的复选框
        for i, site_name in enumerate(target_config.keys()):
            cb = ctk.CTkCheckBox(self.web_select_frame, text=site_name)
            cb.select() # 生成时默认全选
            cb.grid(row=i, column=0, padx=10, pady=5, sticky="w")
            self.checkboxes[site_name] = cb

    def set_all_checkboxes(self, checked):
        """一键全选或全不选当前方案下的网页。"""
        for cb in self.checkboxes.values():
            if checked:
                cb.select()
            else:
                cb.deselect()

    def apply_preset(self, choice):
        """应用快捷方案逻辑"""
        if choice == "默认配置方案":
            self.active_config = default  # 【新增】同步切换后台字典
            self.render_checkboxes(default)
            self.write_log(">>> 已切换至 [默认配置方案]，核查网页列表已更新。\n")
        elif choice == "债券模板":
            self.active_config = default_2  # 【新增】同步切换后台字典
            self.render_checkboxes(default_2)
            self.write_log(">>> 已切换至 债券模板，核查网页列表已更新。\n")
        else:
            self.active_config = WEB_CONFIG # 【新增】同步切换后台字典
            self.render_checkboxes(WEB_CONFIG)
            self.write_log(">>> 已切换至 [自定义手动选择]，核查网页列表已恢复。\n")

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
        for comp in self.companies_data:
            row = ctk.CTkFrame(self.comp_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=format_subject_label(comp)).pack(side="left", padx=5)
            ctk.CTkButton(row, text="✖", width=28, height=24, fg_color="#D9534F", 
                          command=lambda k=comp.get("key"): self.remove_company(k)).pack(side="right", padx=5)

    def remove_company(self, comp_key):
        original_len = len(self.companies_data)
        self.companies_data = [item for item in self.companies_data if item.get("key") != comp_key]
        if len(self.companies_data) != original_len:
            self.refresh_company_list()

    def start_task(self):
        selected_sites = [name for name, cb in self.checkboxes.items() if cb.get() == 1]
        if not self.companies_data or not selected_sites:
            self.write_log(">>> [错误] 请确保已添加核查对象并至少勾选一个网页\n")
            return

        self.run_btn.configure(state="disabled", text="正在运行...")
        
        # 【重点修改】在 args 的最后，把 self.active_config 也传给爬虫线程
        thread = threading.Thread(
            target=run_batch_screenshot_task, 
            args=(list(self.companies_data), self.log_queue, self.base_output_path.get(), selected_sites, self.active_config),
            daemon=True
        )
        thread.start()

    def listen_to_queue(self):
        """保持常驻的监听逻辑，防止重复调用导致主循环卡死"""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if msg == "DONE":
                    # 收到任务完成信号，恢复按钮
                    self.run_btn.configure(state="normal", text="▶ 开始核查")
                    self.write_log(">>> [系统] 任务全部完成，已可开始新任务。\n")
                elif isinstance(msg, tuple) and msg[0] == "CONFIRM":
                    payload = msg[1]
                    result = messagebox.askokcancel(
                        payload.get("title", "请确认"),
                        payload.get("message", "确认后继续执行。"),
                    )
                    payload["result"] = result
                    payload["event"].set()
                else:
                    self.write_log(msg)
        except queue.Empty:
            pass
        # 每100毫秒递归调用，确保 listen 永远活着
        self.after(100, self.listen_to_queue)

    def write_log(self, text):
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", text)
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder: self.base_output_path.set(folder)
