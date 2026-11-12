# 文件路径: main.py
# 作者: 见 LICENSE

import ctypes
import os
import sys
import traceback

# 高分屏必需：声明 Per-Monitor DPI Awareness。
# 否则 Windows 对窗口做位图缩放：内容模糊、边缘拖拽热区失效（窗口不可拉伸）。
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)   # Win 8.1+
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()     # Win7 兜底
    except Exception:
        pass

# PyInstaller 打包后，让 playwright 去打包目录内找 chromium 浏览器。
# 注意必须强制覆盖：若系统环境残留 PLAYWRIGHT_BROWSERS_PATH=0，
# playwright 会转而去 driver/package/.local-browsers 下找浏览器而启动失败。
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _bundled_browsers = os.path.join(sys._MEIPASS, "ms-playwright")
    if os.path.isdir(_bundled_browsers):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _bundled_browsers

import customtkinter as ctk

from views import theme
from views.integrity_check_ui import IntegrityCheckFrame
from views.word_generator_ui import WordGeneratorFrame
from views.djg_ui import DjgFrame
from views.template_ui import TemplateFrame
from views.help_ui import HelpFrame

CURRENT_VERSION = "v2.0.1"
AUTHOR = "IBDW Contributors"


def verify_bundle():
    """Exercise dependencies that are otherwise imported only by workflows."""
    import cv2
    import numpy as np
    import pyautogui
    import pyscreeze
    from PIL import ImageGrab
    from playwright.sync_api import sync_playwright

    if pyautogui.screenshot is not pyscreeze.screenshot:
        raise RuntimeError("PyAutoGUI screenshot dependency is not available")
    if not callable(ImageGrab.grab):
        raise RuntimeError("Pillow ImageGrab is not available")

    image = np.zeros((8, 8, 3), dtype=np.uint8)
    if cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).shape != (8, 8):
        raise RuntimeError("OpenCV bundle self-check failed")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content("<title>IBDW bundle check</title>")
            if page.title() != "IBDW bundle check":
                raise RuntimeError("Playwright bundle self-check failed")
        finally:
            browser.close()


class IBDWApp(ctk.CTk):
    """侧边栏导航 + 主内容区 + 底部状态栏的应用骨架。"""

    PAGES = (("📷", "诚信核查截图"), ("📄", "核查说明生成"),
             ("👔", "董监高核查"), ("📋", "核查模板"), ("📖", "使用说明"))

    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")  # 默认深色，侧边栏可切换
        self.title(f"诚信核查自动化截图 {CURRENT_VERSION}")
        self.geometry("1080x800")
        self.configure(fg_color=theme.BG)

        # 布局：row0 = [侧边栏 | 页面容器]（占满），row1 = 状态栏
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # 状态栏必须先于页面构建：页面初始化时会通过回调推送计数
        self._build_sidebar()
        self._build_statusbar()
        self._build_pages()
        self.select_page(0)

    # ============================ 侧边栏 ============================
    def _build_sidebar(self):
        side = ctk.CTkFrame(self, width=192, corner_radius=0, fg_color=theme.SIDEBAR_BG)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)

        # 品牌区
        header = ctk.CTkFrame(side, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(20, 6))
        ctk.CTkLabel(header, text="诚信核查自动化截图", font=theme.f(15, bold=True),
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(header, text="IBDW · 投行执行自动化", font=theme.f(11),
                     text_color=theme.MUTED, anchor="w").pack(fill="x")
        ver_chip = ctk.CTkLabel(
            header, text=CURRENT_VERSION, font=theme.f(10),
            fg_color=theme.CARD_INNER, corner_radius=6,
            text_color=theme.MUTED,
        )
        ver_chip.pack(anchor="w", pady=(6, 0), ipadx=6, ipady=1)

        divider = ctk.CTkFrame(side, height=1, fg_color=theme.CARD_BORDER)
        divider.pack(fill="x", padx=16, pady=(14, 12))

        # 导航项（选中态为品牌色胶囊）
        self._nav_buttons = []
        for idx, (icon, label) in enumerate(self.PAGES):
            btn = ctk.CTkButton(
                side, text=f"{icon}  {label}", anchor="w",
                height=40, corner_radius=9, font=theme.f(13),
                fg_color="transparent", hover_color=theme.SUBTLE_HOVER,
                command=lambda i=idx: self.select_page(i),
            )
            btn.pack(fill="x", padx=10, pady=3)
            self._nav_buttons.append(btn)

        # 底部：外观模式开关 + 版本脚注
        footer = ctk.CTkFrame(side, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=16, pady=16)
        self.dark_mode_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            footer, text="深色主题", variable=self.dark_mode_var,
            onvalue=True, offvalue=False, font=theme.f(12),
            progress_color=theme.ACCENT,
            command=self._apply_appearance_choice,
        ).pack(anchor="w")
        ctk.CTkLabel(footer, text=f"{CURRENT_VERSION} · {AUTHOR}", font=theme.f(10),
                     text_color=theme.MUTED, anchor="w").pack(
            anchor="w", pady=(10, 0))

    def _apply_appearance_choice(self):
        mode = "dark" if self.dark_mode_var.get() else "light"
        ctk.set_appearance_mode(mode)
        # 原生 tk 控件不会自动跟随主题，延迟同步分隔条底色
        self.after(60, lambda: self.integrity_frame.sync_paned_bg())

    # ============================ 页面容器 ============================
    def _build_pages(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=1, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.integrity_frame = IntegrityCheckFrame(
            container, status_cb=self.set_status, counts_cb=self.set_counts,
        )
        self.word_frame = WordGeneratorFrame(container, status_cb=self.set_status)
        self.djg_frame = DjgFrame(
            container, status_cb=self.set_status, go_preset_cb=self.go_djg_preset,
        )
        self.template_frame = TemplateFrame(
            container, status_cb=self.set_status,
            load_cb=self.load_template_companies,
        )
        self.help_frame = HelpFrame(container)
        self._frames = (self.integrity_frame, self.word_frame,
                        self.djg_frame, self.template_frame, self.help_frame)
        for frame in self._frames:
            frame.grid(row=0, column=0, sticky="nsew")

    def load_template_companies(self, subjects):
        """模板页载入回调：替换核查名单并跳转截图页。"""
        self.integrity_frame.companies_data = list(subjects)
        self.integrity_frame.refresh_company_list()
        self.select_page(0)

    def go_djg_preset(self):
        """董监高页一键：切换主界面预设并跳转截图页。"""
        self.integrity_frame.apply_preset("董监高模板")
        self.integrity_frame.preset_menu.set("董监高模板")
        self.select_page(0)

    def show_help(self):
        """侧边栏「使用说明」：重显快速上手指引并跳回核查页。"""
        self.integrity_frame.show_help()
        self.select_page(0)

    def select_page(self, index):
        frame = self._frames[index]
        frame.tkraise()
        for i, btn in enumerate(self._nav_buttons):
            selected = i == index
            btn.configure(
                fg_color=theme.ACCENT if selected else "transparent",
                hover_color=theme.ACCENT_HOVER if selected else theme.SUBTLE_HOVER,
                text_color="#ffffff" if selected else ("gray15", "#e6e6ec"),
            )
        # 切页时刷新状态栏右侧计数：核查页显示实时计数，生成页留空
        if index == 0:
            self.integrity_frame.push_counts()
        else:
            self.set_counts("")

    # ============================ 状态栏 ============================
    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=32, corner_radius=0, fg_color=theme.SIDEBAR_BG)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")

        self.status_dot = ctk.CTkLabel(bar, text="●", font=theme.f(12, bold=True),
                                       text_color=theme.STATUS_COLOR["idle"])
        self.status_dot.pack(side="left", padx=(16, 6))
        self.status_text = ctk.CTkLabel(bar, text="就绪", font=theme.f(12))
        self.status_text.pack(side="left")

        self.counts_label = ctk.CTkLabel(bar, text="", font=theme.f(12),
                                         text_color=theme.MUTED)
        self.counts_label.pack(side="right", padx=16)

    def set_status(self, text, kind="idle"):
        """供各页面推送运行状态；kind: idle / run。"""
        if not hasattr(self, "status_text"):
            return
        self.status_text.configure(text=text)
        self.status_dot.configure(text_color=theme.STATUS_COLOR.get(kind, "#94a3b8"))

    def set_counts(self, text):
        if not hasattr(self, "counts_label"):
            return
        self.counts_label.configure(text=text)


if __name__ == "__main__":
    if "--verify-bundle" in sys.argv:
        try:
            verify_bundle()
        except Exception:
            log_path = os.path.join(
                os.path.dirname(sys.executable), "bundle_verify_error.log"
            )
            with open(log_path, "w", encoding="utf-8") as log_file:
                traceback.print_exc(file=log_file)
            raise
    else:
        try:
            app = IBDWApp()
            app.mainloop()
        except Exception:
            # 冻结环境下 windowed 模式看不到 traceback，落盘便于排查
            crash_dir = (os.path.dirname(sys.executable)
                         if getattr(sys, "frozen", False)
                         else os.path.dirname(os.path.abspath(__file__)))
            with open(os.path.join(crash_dir, "gui_crash.log"),
                      "w", encoding="utf-8") as log_file:
                traceback.print_exc(file=log_file)
            raise
