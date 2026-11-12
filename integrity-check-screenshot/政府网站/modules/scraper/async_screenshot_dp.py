import time
import os
import json
import re
import pyautogui
from urllib.parse import quote
from DrissionPage import ChromiumPage, ChromiumOptions

# 引入 dp 版配置
from modules.scraper.async_func_dp import WEB_CONFIG

ID_PATTERN = re.compile(
    r"(?<![0-9A-Za-z])(?:\d{17}[\dXx]|\d{15}|[0-9A-Za-z]{18})(?![0-9A-Za-z])"
)


def safe_path_name(value):
    value = str(value or "").strip()
    value = re.sub(r'[<>:"/\\|?*\r\n\t]+', "_", value)
    value = value.strip(" .")
    return value or "未命名"


def normalize_subject(subject):
    if isinstance(subject, dict):
        name = str(subject.get("name") or "").strip()
        id_card = str(subject.get("id_card") or "").strip().upper()
        raw = str(subject.get("raw") or f"{name} {id_card}").strip()
    else:
        raw = str(subject or "").strip()
        match = ID_PATTERN.search(raw)
        id_card = match.group(0).upper() if match else ""
        if match:
            name = f"{raw[:match.start()]} {raw[match.end():]}"
            name = re.sub(r"[\s,，;；:：|/\\]+", " ", name).strip()
        else:
            name = raw

    display_name = name or id_card or raw or "未命名"
    return {
        "name": name,
        "id_card": id_card,
        "raw": raw,
        "display_name": display_name,
        "folder_name": display_name,
    }


def subject_text(subject, mode="name"):
    name = subject.get("name", "")
    id_card = subject.get("id_card", "")
    raw = subject.get("raw", "")

    if mode in ("name_id", "keyword"):
        return f"{name} {id_card}".strip() or raw
    if mode in ("id", "id_card"):
        return id_card
    if mode == "raw":
        return raw
    return name or raw or id_card


def format_target_url(config, subject):
    query_mode = config.get("query_mode", "name")
    values = {
        "company": quote(subject_text(subject, query_mode), safe=""),
        "name": quote(subject_text(subject, "name"), safe=""),
        "id_card": quote(subject_text(subject, "id_card"), safe=""),
        "keyword": quote(subject_text(subject, "name_id"), safe=""),
        "raw": quote(subject_text(subject, "raw"), safe=""),
    }
    return config["url"].format(**values)


def action_argument(config, subject):
    if config.get("action_arg") == "item":
        return subject
    return subject_text(subject, config.get("action_query_mode", config.get("query_mode", "name")))


def screenshot_pyautogui(company_folder, filename):
    save_path = os.path.join(company_folder, f"{safe_path_name(filename)}.png")
    # 纯物理屏幕截图（带任务栏）
    pyautogui.screenshot(save_path)  


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


def wait_tab_ready(tab, timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            state = tab.run_js("return document.readyState;")
            if state in ("interactive", "complete"):
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def get_clean_page():
    """初始化 DrissionPage 浏览器对象"""
    co = ChromiumOptions()
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


def run_foreground_site(page, subject, company_folder, filename, config, log_queue):
    """验证码、滑块、必须前台渲染的网站用串行前台流程处理。"""
    save_name = config.get("save_as", filename)
    target_url = format_target_url(config, subject)
    tab = None
    screenshot_tab = None

    try:
        log_queue.put(f"  -> [前台模式] {filename} 开始执行。\n")
        tab = page.new_tab(target_url)
        bring_to_front(tab)
        wait_tab_ready(tab, timeout=config.get("load_timeout", 30))

        action_func = config.get("action")
        old_tabs = list(page.tab_ids)
        if action_func:
            action_func(tab, action_argument(config, subject))

        screenshot_tab = tab
        for _ in range(25):
            current_tabs = page.tab_ids
            new_tabs = [t for t in current_tabs if t not in old_tabs]
            if new_tabs:
                screenshot_tab = page.get_tab(new_tabs[-1])
                break
            time.sleep(0.2)

        bring_to_front(screenshot_tab)
        wait_tab_ready(screenshot_tab, timeout=config.get("result_timeout", 10))

        post_action_func = config.get("post_action")
        if post_action_func:
            try:
                post_action_func(screenshot_tab, action_argument(config, subject))
            except Exception as post_err:
                log_queue.put(f"  -> [提示] {filename} 截图前动作失败: {repr(post_err)}\n")

        time.sleep(config.get("screenshot_delay", 0.5))
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

def run_batch_screenshot_task(companies, log_queue, base_output, selected_sites, CONFIG):
    page = get_clean_page()
    try:
        for raw_subject in companies:
            subject = normalize_subject(raw_subject)
            display_name = subject["display_name"]
            log_queue.put(f"\n[任务] 开始处理: {display_name}\n")

            company_folder = os.path.join(base_output, safe_path_name(subject["folder_name"]))
            os.makedirs(company_folder, exist_ok=True)

            active_config = {k: v for k, v in CONFIG.items() if k in selected_sites}
            tab_config = {
                k: v for k, v in active_config.items()
                if not v.get("workflow") and not v.get("foreground")
            }
            foreground_config = {
                k: v for k, v in active_config.items()
                if not v.get("workflow") and v.get("foreground")
            }
            workflow_config = {k: v for k, v in active_config.items() if v.get("workflow")}
            main_tab_id = page.latest_tab.tab_id

            initial_pool = {}
            result_pool = {}

            # ==========================================
            # 阶段一：纯后台瞬间并发发包
            # ==========================================
            for filename, config in tab_config.items():
                target_url = format_target_url(config, subject)
                tab = page.new_tab('about:blank')
                initial_pool[tab.tab_id] = {
                    "filename": filename,
                    "save_name": config.get("save_as", filename),
                    "start_time": time.time(),
                }
                tab.run_js(f"setTimeout(() => {{ window.location.href = {json.dumps(target_url)}; }}, 10);")

            # 用于异步追踪新窗口开辟的辅助字典 { 目标tab_id: {old_tabs, filename, check_count} }
            tab_tracking_pool = {}

            # ==========================================
            # 阶段二：并发交互（杜绝原地死等）
            # ==========================================
            while initial_pool or tab_tracking_pool:
                current_time = time.time()
                
                # 2.1 处理正常加载和交互的 initial_pool
                for t_id in list(initial_pool.keys()): 
                    pool_data = initial_pool[t_id]
                    filename = pool_data["filename"]
                    save_name = pool_data["save_name"]
                    elapsed = current_time - pool_data["start_time"]
                    
                    try:
                        tab = page.get_tab(t_id)
                        if not tab:
                            initial_pool.pop(t_id, None)
                            continue
                            
                        try:
                            is_complete = tab.run_js("return document.readyState;") == "complete"
                        except:
                            is_complete = False # 上下文丢失时先视作未完，交由下面超时或重试处理
                        
                        if is_complete or elapsed > 20: # 稍微缩短超时到 20 秒
                            initial_pool.pop(t_id)
                            action_func = tab_config[filename].get('action')
                            
                            if action_func:
                                old_tabs = page.tab_ids
                                try:
                                    action_func(tab, action_argument(tab_config[filename], subject))
                                    # 交互成功后，不在此处死等新窗口！而是扔进追踪池，让大循环下一次再来看
                                    tab_tracking_pool[t_id] = {
                                        "filename": filename, 
                                        "save_name": save_name,
                                        "old_tabs": old_tabs, 
                                        "check_count": 0,
                                        "start_time": time.time()
                                    }
                                except Exception as action_err:
                                    # 如果交互直接崩了（如ContextLost），直接送去第三阶段截图兜底
                                    log_queue.put(f"  -> [提示] {filename} 交互失败(转兜底截图): {repr(action_err)}\n")
                                    result_pool[t_id] = {"filename": filename, "save_name": save_name, "start_time": time.time()}
                            else:
                                # 无交互，直接进截图池
                                result_pool[t_id] = {"filename": filename, "save_name": save_name, "start_time": time.time()}
                                
                    except Exception as e:
                        log_queue.put(f"  -> [警告] {filename} 阶段二异常: {repr(e)}，强制流转。\n")
                        initial_pool.pop(t_id, None)
                        result_pool[t_id] = {"filename": filename, "save_name": save_name, "start_time": time.time()}

                # 2.2 【提速核心】异步检查新窗口，不阻塞其他网站
                for original_id in list(tab_tracking_pool.keys()):
                    track_data = tab_tracking_pool[original_id]
                    track_data["check_count"] += 1
                    
                    try:
                        current_tabs = page.tab_ids
                        new_tabs = [t for t in current_tabs if t not in track_data["old_tabs"]]
                        
                        if new_tabs:
                            # 发现了新窗口，追踪结束，把新窗口送入截图池
                            tab_tracking_pool.pop(original_id)
                            result_pool[new_tabs[-1]] = {
                                "filename": track_data["filename"],
                                "save_name": track_data["save_name"],
                                "start_time": time.time(),
                            }
                        elif track_data["check_count"] >= 10 or (time.time() - track_data["start_time"]) > 2.5:
                            # 轮询了10次（约2秒）都没新窗口，放弃等待，把原窗口送去截图
                            tab_tracking_pool.pop(original_id)
                            result_pool[original_id] = {
                                "filename": track_data["filename"],
                                "save_name": track_data["save_name"],
                                "start_time": time.time(),
                            }
                    except:
                        # 浏览器偶尔不稳定报错，允许容错，下一次大循环再试
                        if track_data["check_count"] >= 10:
                            tab_tracking_pool.pop(original_id)
                            result_pool[original_id] = {
                                "filename": track_data["filename"],
                                "save_name": track_data["save_name"],
                                "start_time": time.time(),
                            }

                time.sleep(0.2) # 缩短大循环步长，提高整体吞吐量

            # ==========================================
            # 阶段三：强制显示并截图
            # ==========================================
            while result_pool:
                for t_id in list(result_pool.keys()):
                    pool_data = result_pool[t_id]
                    filename = pool_data["filename"]
                    save_name = pool_data["save_name"]
                    elapsed = time.time() - pool_data["start_time"]
                    
                    try:
                        tab = page.get_tab(t_id)
                        if not tab:
                            result_pool.pop(t_id, None)
                            continue

                        try:
                            is_complete = tab.run_js("return document.readyState;") == "complete"
                        except:
                            is_complete = False 
                        
                        # 结果页渲染最多等 10 秒（减少无谓的卡顿等待）
                        if is_complete or elapsed > 10:
                            result_pool.pop(t_id)
                            
                            tab.run_cdp('Page.bringToFront')
                            time.sleep(0.15) # 降低缓冲时间
                            
                            post_action_func = tab_config[filename].get('post_action')
                            if post_action_func:
                                try: post_action_func(tab, action_argument(tab_config[filename], subject))
                                except: pass
                                
                            time.sleep(0.3) 
                            screenshot_pyautogui(company_folder, save_name)
                            
                            try: tab.close()
                            except: pass 
                    except Exception as e:
                        log_queue.put(f"  -> [警告] {filename} 阶段三异常: {repr(e)}\n")
                        result_pool.pop(t_id, None)
                time.sleep(0.2)
                
            try: page.get_tab(main_tab_id).run_cdp('Page.bringToFront')
            except: pass

            for filename, config in foreground_config.items():
                run_foreground_site(page, subject, company_folder, filename, config, log_queue)

            try: page.get_tab(main_tab_id).run_cdp('Page.bringToFront')
            except: pass

            for filename, config in workflow_config.items():
                save_name = config.get("save_as", filename)
                try:
                    log_queue.put(f"  -> [独立模式] {filename} 开始执行。\n")
                    config["workflow"](page, subject, company_folder, save_name, log_queue)
                    log_queue.put(f"  -> [独立模式] {filename} 完成。\n")
                except Exception as workflow_err:
                    log_queue.put(f"  -> [警告] {filename} 独立模式失败: {repr(workflow_err)}\n")

    except Exception as e:
        log_queue.put(f">>>> [错误] 处理全局失败: {repr(e)}\n")
    finally:
        page.quit()
        log_queue.put("DONE")
