# 文件路径: views/theme.py
# 统一视觉设计 Token 与通用 UI 组件（卡片 / Tooltip / 确认弹窗 / 彩色日志）。
# 所有颜色使用 (浅色, 深色) 元组，CustomTkinter 会随外观模式自动切换。

import tkinter as tk
import customtkinter as ctk

# ============================ 设计 Token ============================

FONT_FAMILY = "Microsoft YaHei UI"
MONO_FAMILY = "Consolas"

BG          = ("gray94", "#17171e")   # 应用窗口底色
SIDEBAR_BG  = ("gray93", "#12121a")   # 侧边栏底色
CARD        = ("gray98", "#1f1f29")   # 卡片底色
CARD_INNER  = ("gray95", "#272733")   # 卡片内嵌元素（列表行等）
CARD_BORDER = ("gray82", "#2d2d39")   # 卡片描边
MUTED       = ("gray42", "gray62")    # 次要文字
ACCENT      = ("#178a56", "#2fa572")  # 品牌强调色（主按钮 / 选中态）
ACCENT_HOVER = ("#106b42", "#23855c")
DANGER      = ("#b03a34", "#d9534f")
SUBTLE_BTN   = ("gray86", "#2c2c37")  # 次级按钮底色
SUBTLE_HOVER = ("gray80", "#38384a")

STATUS_COLOR = {"idle": "#94a3b8", "run": "#22c55e"}

LOG_TAGS = {
    "err":  "#ef4444",
    "ok":   "#22c55e",
    "warn": "#eab308",
    "sys":  "#7aa2f7",
}


def f(size=13, bold=False, mono=False):
    """构造 CTkFont。注意：必须在应用窗口创建之后调用。"""
    return ctk.CTkFont(
        family=MONO_FAMILY if mono else FONT_FAMILY,
        size=size,
        weight="bold" if bold else "normal",
    )


def make_card(master, title=None):
    """创建圆角卡片，返回 (card, body, head)。

    - 有标题时 head 为标题栏容器，可向其右侧打包附加控件；
    - 内容一律放进 body（body 已带内边距）。
    """
    card = ctk.CTkFrame(
        master, corner_radius=10, fg_color=CARD,
        border_width=1, border_color=CARD_BORDER,
    )
    head = None
    top_pad = 10
    if title:
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(
            head, text=title, font=f(12, bold=True),
            text_color=MUTED, anchor="w",
        ).pack(side="left")
        top_pad = 0
    body = ctk.CTkFrame(card, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=12, pady=(top_pad, 12))
    return card, body, head


# ============================ 彩色日志 ============================

def setup_log_tags(textbox):
    """为 CTkTextbox 底层 Text 注册日志着色 tag（创建后调用一次）。"""
    inner = getattr(textbox, "_textbox", textbox)  # CTkTextbox 内部的原生 tk.Text
    for tag, color in LOG_TAGS.items():
        inner.tag_configure(tag, foreground=color)


def classify_log(text):
    """按关键词判定日志级别 tag，无匹配返回 None。"""
    if ("[错误]" in text) or ("❌" in text):
        return "err"
    if ("[成功]" in text) or ("成功生成" in text) or ("✅" in text):
        return "ok"
    if "[系统]" in text:
        return "sys"
    if "[提示]" in text:
        return "warn"
    return None


def append_log(textbox, text):
    """向禁用态 CTkTextbox 追加一条日志并按级别着色（仅主线程调用）。"""
    textbox.configure(state="normal")
    tag = classify_log(text)
    if tag:
        textbox.insert("end", text, tag)
    else:
        textbox.insert("end", text)
    textbox.see("end")
    textbox.configure(state="disabled")


def clear_logbox(textbox):
    textbox.configure(state="normal")
    textbox.delete("1.0", "end")
    textbox.configure(state="disabled")


# ============================ Tooltip ============================

class ToolTip:
    """轻量提示气泡：悬停延时弹出，离开即消失，颜色跟随外观模式。"""

    def __init__(self, widget, text, delay=450):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    @staticmethod
    def _colors():
        dark = str(ctk.get_appearance_mode()).lower() == "dark"
        return ("#2e2e38", "#f2f2f2") if dark else ("#fffbd6", "#3a3a30")

    def _show(self):
        if self._tip is not None or not self.text:
            return
        bg, fg = self._colors()
        x = self.widget.winfo_rootx() + max(8, self.widget.winfo_width() // 6)
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tk.Label(
            tw, text=self.text, justify="left", bg=bg, fg=fg,
            padx=9, pady=5, bd=0, font=(FONT_FAMILY, 10),
        ).pack()
        tw.wm_geometry(f"+{x}+{y}")
        tw.lift()

    def _hide(self, _=None):
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


# ======================== 模态对话框 ========================

class _ModalBase(ctk.CTkToplevel):
    """模态对话框公共基类：居中定位 / 安全 grab / 结果回传。"""

    def _place_over_master(self):
        self.update_idletasks()
        mw = self.master.winfo_toplevel()
        x = mw.winfo_x() + max(0, (mw.winfo_width() - self.winfo_width()) // 2)
        y = mw.winfo_y() + max(0, (mw.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")
        self.lift()
        self.focus_force()

    def _grab_safely(self):
        try:
            self.grab_set()
        except Exception:
            pass

    def _finish(self, value):
        self.result = value
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


class ConfirmDialog(_ModalBase):
    """CustomTkinter 风格模态确认弹窗（替代 messagebox.askokcancel）。

    用法：
        dlg = ConfirmDialog(master, title, message)
        master.wait_window(dlg)
        ok = bool(dlg.result)
    """

    def __init__(self, master, title="请确认", message=""):
        super().__init__(master)
        self.result = None
        self.title(title)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.configure(fg_color=CARD)

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=26, pady=(22, 20))

        ctk.CTkLabel(wrap, text=title, font=f(15, bold=True),
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(wrap, text=message, font=f(13), justify="left",
                     wraplength=380, anchor="w").pack(fill="x", pady=(10, 20))

        btn_row = ctk.CTkFrame(wrap, fg_color="transparent")
        btn_row.pack(fill="x")
        cancel_btn = ctk.CTkButton(
            btn_row, text="取消", width=96, height=32, font=f(13),
            fg_color=SUBTLE_BTN, hover_color=SUBTLE_HOVER,
            text_color=("gray15", "#e8e8ee"),
            command=lambda: self._finish(False),
        )
        cancel_btn.pack(side="right", padx=(10, 0))
        ok_btn = ctk.CTkButton(
            btn_row, text="确定", width=96, height=32, font=f(13, bold=True),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=lambda: self._finish(True),
        )
        ok_btn.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", lambda: self._finish(False))
        self.bind("<Escape>", lambda _e: self._finish(False))
        self.bind("<Return>", lambda _e: self._finish(True))

        self.after(10, self._place_over_master)
        self.after(150, self._grab_safely)
        self.after(250, ok_btn.focus_set)


class InputDialog(_ModalBase):
    """单行文本输入模态对话框。

    用法：
        dlg = InputDialog(master, title, label, initial="", placeholder="")
        master.wait_window(dlg)
        value = dlg.result   # None=取消，str=输入内容
    """

    def __init__(self, master, title="输入", label="", initial="", placeholder=""):
        super().__init__(master)
        self.result = None
        self.title(title)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.configure(fg_color=CARD)

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=26, pady=(22, 20))

        if label:
            ctk.CTkLabel(wrap, text=label, font=f(13), justify="left",
                         wraplength=360, anchor="w").pack(fill="x")
        self.entry = ctk.CTkEntry(wrap, height=34, font=f(13),
                                  placeholder_text=placeholder)
        self.entry.pack(fill="x", pady=(12, 18))
        if initial:
            self.entry.insert(0, initial)
            self.entry.select_range(0, "end")

        btn_row = ctk.CTkFrame(wrap, fg_color="transparent")
        btn_row.pack(fill="x")
        cancel_btn = ctk.CTkButton(
            btn_row, text="取消", width=96, height=32, font=f(13),
            fg_color=SUBTLE_BTN, hover_color=SUBTLE_HOVER,
            text_color=("gray15", "#e8e8ee"),
            command=lambda: self._finish(None),
        )
        cancel_btn.pack(side="right", padx=(10, 0))
        ok_btn = ctk.CTkButton(
            btn_row, text="确定", width=96, height=32, font=f(13, bold=True),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._confirm,
        )
        ok_btn.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", lambda: self._finish(None))
        self.bind("<Escape>", lambda _e: self._finish(None))
        self.bind("<Return>", lambda _e: self._confirm())

        self.after(10, self._place_over_master)
        self.after(150, self._grab_safely)
        self.after(250, self.entry.focus_set)

    def _confirm(self):
        self._finish(self.entry.get().strip())
