"""Playwright 独立批量工作流（登录一次 + 逐对象处理）。"""
from datetime import datetime
import os
import time

from .gui_confirm import _request_gui_confirm
from .output_layout import subject_dir
from .page_helpers import _safe_filename, _screenshot, _subject_name


def batch_workflow_tianyancha(subjects, run_dir, filename, log_queue):
    """按原独立脚本的语义：登录一次，再批量搜索并截取公司详情页。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("天眼查模式需要先安装 playwright") from exc

    home_url = "https://www.tianyancha.com/company/22822"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        context = browser.new_context(no_viewport=True)
        tab = context.new_page()

        try:
            try:
                tab.goto(home_url, wait_until="commit", timeout=60000)
            except Exception as exc:
                log_queue.put(f"     天眼查首页加载较慢，将继续等待人工登录: {exc}\n")

            log_queue.put("     天眼查已打开，请完成登录后回到 GUI 确认。\n")
            confirmed = _request_gui_confirm(
                log_queue,
                "天眼查登录确认",
                "请在浏览器中完成天眼查登录，并确认页面已加载。\n\n"
                "准备好后点击“确定”，程序会连续处理全部核查对象；点击“取消”将跳过天眼查。",
            )
            if not confirmed:
                log_queue.put("     已取消天眼查批量任务。\n")
                return

            for index, subject in enumerate(subjects):
                company = _subject_name(subject)
                if not company:
                    log_queue.put("  -> [提示] 天眼查跳过空名称。\n")
                    continue

                company_folder = subject_dir(run_dir, index)
                os.makedirs(company_folder, exist_ok=True)
                detail_tab = None

                try:
                    log_queue.put(f"  -> [天眼查] 正在处理: {company}\n")
                    search_box = tab.get_by_role(
                        "textbox",
                        name="请输入公司名称、老板姓名、品牌名称等",
                    )
                    search_box.click()
                    search_box.fill(company)
                    tab.get_by_role("button", name="天眼一下").click()
                    tab.wait_for_load_state("domcontentloaded")

                    company_link = tab.locator(f"a:has-text('{company}')").first
                    company_link.wait_for(state="visible", timeout=5000)
                    with tab.expect_popup() as popup_info:
                        company_link.click()
                    detail_tab = popup_info.value
                    detail_tab.wait_for_load_state("domcontentloaded")
                    time.sleep(4)
                    detail_tab.bring_to_front()
                    time.sleep(0.5)

                    _screenshot(company_folder, filename)
                    log_queue.put(f"  -> [天眼查] {company} 截图完成。\n")
                except Exception as exc:
                    log_queue.put(f"  -> [警告] 天眼查处理 {company} 失败: {repr(exc)}\n")
                    try:
                        tab.goto(home_url, wait_until="commit", timeout=60000)
                    except Exception:
                        pass
                finally:
                    if detail_tab:
                        try:
                            detail_tab.close()
                        except Exception:
                            pass
                    try:
                        tab.bring_to_front()
                    except Exception:
                        pass
                    time.sleep(1)
        finally:
            context.close()
            browser.close()


def batch_workflow_wenshu(subjects, run_dir, filename, log_queue):
    """按原独立脚本的语义：登录一次，再逐家公司检索和翻页长截图。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("法律文书网模式需要先安装 playwright") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            no_viewport=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        tab = context.new_page()

        try:
            tab.goto("https://wenshu.court.gov.cn/")
            log_queue.put("     法律文书网已打开，请完成登录并进入检索页后回到 GUI 确认。\n")
            confirmed = _request_gui_confirm(
                log_queue,
                "法律文书网登录确认",
                "请在浏览器中完成法律文书网登录，并进入检索页面。\n\n"
                "准备好后点击“确定”，程序会连续处理全部核查对象；点击“取消”将跳过法律文书网。",
            )
            if not confirmed:
                log_queue.put("     已取消法律文书网批量任务。\n")
                return

            for index, subject in enumerate(subjects):
                company = _subject_name(subject)
                if not company:
                    log_queue.put("  -> [提示] 法律文书网跳过空名称。\n")
                    continue

                target_dir = os.path.join(
                    subject_dir(run_dir, index),
                    _safe_filename(filename),
                )
                os.makedirs(target_dir, exist_ok=True)

                try:
                    log_queue.put(f"  -> [法律文书网] 正在处理: {company}\n")
                    clear_btn = tab.locator("#clear-Btn")
                    if clear_btn.is_visible():
                        clear_btn.click()
                        tab.wait_for_timeout(1000)

                    search_input = tab.locator(".searchKey")
                    search_input.click()
                    search_input.fill("")
                    search_input.fill(company)
                    tab.locator(".search-rightBtn").click()
                    tab.wait_for_timeout(4000)

                    current_page = 1
                    while True:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        file_path = os.path.join(
                            target_dir,
                            f"{timestamp}_page_{current_page}.png",
                        )
                        tab.screenshot(path=file_path, full_page=True)

                        next_page_value = current_page + 1
                        next_btn = tab.locator(
                            f".pageButton[value='{next_page_value}']"
                        ).first
                        if not next_btn.is_visible():
                            break

                        next_btn.click()
                        tab.wait_for_timeout(3000)
                        current_page = next_page_value

                    log_queue.put(
                        f"  -> [法律文书网] {company} 共保存 {current_page} 页。\n"
                    )
                except Exception as exc:
                    log_queue.put(
                        f"  -> [警告] 法律文书网处理 {company} 失败: {repr(exc)}\n"
                    )
        finally:
            context.close()
            browser.close()
