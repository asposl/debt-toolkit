"""DrissionPage 浏览器生命周期与标签页管理。"""
import os
import sys
import time

from DrissionPage import ChromiumPage, ChromiumOptions


def bring_to_front(tab):
    try:
        tab.run_cdp('Page.bringToFront')
    except Exception:
        pass
    try:
        tab.set.activate()
    except Exception:
        pass
    time.sleep(0.5)


def wait_tab_ready(tab, timeout=30, require_complete=False):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            state = tab.run_js("return document.readyState;")
            ready_states = ("complete",) if require_complete else ("interactive", "complete")
            if state in ready_states:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def tab_url(tab):
    try:
        return str(tab.url or "")
    except Exception:
        return ""


def close_other_tabs(page, keep_tab_id=None):
    """关闭除指定标签页外的所有标签页，防止残留标签页跨公司/跨运行累积。"""
    try:
        for t_id in list(page.tab_ids):
            if keep_tab_id is not None and t_id == keep_tab_id:
                continue
            try:
                tab = page.get_tab(t_id)
                if tab:
                    tab.close()
            except Exception:
                pass
    except Exception:
        pass


def get_clean_page():
    """初始化 DrissionPage 浏览器对象"""
    co = ChromiumOptions()
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled_chromium = os.path.join(
            sys._MEIPASS,
            "ms-playwright",
            "chromium-1223",
            "chrome-win64",
            "chrome.exe",
        )
        if os.path.isfile(bundled_chromium):
            co.set_browser_path(bundled_chromium)

    latest_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    co.set_user_agent(latest_ua)

    # 2. 规避自动化特征（DrissionPage 默认已处理大部分，这里做加强）
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--start-maximized')
    # 确保使用 ChromiumPage
    page = ChromiumPage(co)
    stealth_js = """
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });
    """
    # 让每个新开的标签页都提前执行这段 JS
    page.run_cdp("Page.addScriptToEvaluateOnNewDocument", source=stealth_js)
    return page
