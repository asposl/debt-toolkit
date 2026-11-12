"""前台串行截图流程（验证码 / 滑块 / 必须前台渲染的网站）。"""
import os
import time

from .actions_captcha import add_captcha_log_sink, suggest_captcha_debug_dir
from .browser import bring_to_front, tab_url, wait_tab_ready
from .capture import screenshot_pyautogui
from .url_builder import action_argument, format_target_url


def _wire_captcha_diagnostics(company_folder, log_queue):
    """把点选验证码的诊断信息接到 GUI 与磁盘，返回解除注册的函数。

    两件事：
      1) 验证码模块内部的 _log 只 print，默认进不了 GUI 日志区。这里注册
         log_queue.put 作为接收器，界面上才能实时看到"提示字读成什么、哪个框
         没认出来"。必须在 action 结束后反注册——log_queue 是每个站点临时接入
         的，不摘掉会在后续站点继续往里灌。
      2) 把落盘目录建议到输出根目录旁的「验证码调试」，即用户最可能去找的
         地方；不覆盖用户/环境变量的显式设置。
    """
    unsubscribe = add_captcha_log_sink(log_queue.put)
    try:
        out_root = os.path.dirname(os.path.abspath(company_folder))
        suggest_captcha_debug_dir(os.path.join(out_root, '验证码调试'))
    except Exception:
        pass
    return unsubscribe


def _wait_action_ready(tab, config):
    """等待动作所需的首个元素；没有专用选择器时回退到页面 readyState。"""
    timeout = config.get("load_timeout", 30)
    selector = config.get("action_ready_selector")
    if selector:
        try:
            return bool(tab.ele(selector, timeout=timeout))
        except Exception:
            return False
    return wait_tab_ready(tab, timeout=timeout)


def run_foreground_site(page, subject, company_folder, filename, config, log_queue, extra_delay=0):
    """验证码、滑块、必须前台渲染的网站用串行前台流程处理。"""
    save_name = config.get("save_as", filename)
    target_url = format_target_url(config, subject)
    tab = None
    screenshot_tab = None

    try:
        log_queue.put(f"  -> [前台模式] {filename} 开始执行。\n")
        tab = page.new_tab(target_url)
        bring_to_front(tab)
        if not _wait_action_ready(tab, config):
            raise RuntimeError(
                f"目标页面在 {config.get('load_timeout', 30)} 秒内未完成初始加载"
            )

        action_func = config.get("action")
        old_tabs = list(page.tab_ids)
        initial_url = tab_url(tab)
        if action_func:
            unwire = _wire_captcha_diagnostics(company_folder, log_queue)
            try:
                action_func(tab, action_argument(config, subject))
            finally:
                unwire()

        screenshot_tab = tab
        popup_deadline = time.time() + config.get("popup_timeout", 15)
        if config.get("popup_timeout", 15) > 0:
            while time.time() < popup_deadline:
                current_tabs = page.tab_ids
                new_tabs = [t for t in current_tabs if t not in old_tabs]
                if new_tabs:
                    screenshot_tab = page.get_tab(new_tabs[-1])
                    break
                if tab_url(tab) not in ("", "about:blank", initial_url):
                    break
                time.sleep(0.2)

        if config.get("require_result_navigation"):
            result_url = tab_url(screenshot_tab)
            if screenshot_tab is tab and result_url in ("", "about:blank", initial_url):
                raise RuntimeError(
                    f"搜索提交后未检测到结果页（等待 {config.get('popup_timeout', 15)} 秒）"
                )
            result_url_deadline = time.time() + config.get("result_timeout", 20)
            while result_url in ("", "about:blank") and time.time() < result_url_deadline:
                time.sleep(0.2)
                result_url = tab_url(screenshot_tab)
            if result_url in ("", "about:blank"):
                raise RuntimeError("新标签页未跳转到有效的结果地址")

        bring_to_front(screenshot_tab)
        if not wait_tab_ready(
            screenshot_tab,
            timeout=config.get("result_timeout", 20),
            require_complete=config.get("result_require_complete", True),
        ):
            raise RuntimeError("结果页在限定时间内未加载完成")

        result_selector = config.get("result_selector")
        if result_selector and not screenshot_tab.ele(
            result_selector,
            timeout=config.get("result_timeout", 20),
        ):
            raise RuntimeError(f"结果页缺少预期元素: {result_selector}")

        post_action_func = config.get("post_action")
        if post_action_func:
            try:
                post_action_func(screenshot_tab, action_argument(config, subject))
            except Exception as post_err:
                log_queue.put(f"  -> [提示] {filename} 截图前动作失败: {repr(post_err)}\n")

        time.sleep(config.get("screenshot_delay", 0.5) + extra_delay)
        screenshot_pyautogui(company_folder, save_name)
        log_queue.put(f"  -> [前台模式] {filename} 完成。\n")
    except Exception as err:
        log_queue.put(f"  -> [警告] {filename} 前台模式失败: {repr(err)}\n")
    finally:
        try:
            if screenshot_tab and getattr(screenshot_tab, "tab_id", None) != getattr(tab, "tab_id", None):
                screenshot_tab.close()
        except Exception:
            pass
        try:
            if tab:
                tab.close()
        except Exception:
            pass
