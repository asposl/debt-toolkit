"""批量截图任务编排：后台并发三阶段池 + 前台流程 + 独立工作流。"""
import json
import os
import time

from .browser import bring_to_front, close_other_tabs, get_clean_page
from .capture import screenshot_pyautogui
from .actions_captcha import set_captcha_site_count
from .foreground_runner import run_foreground_site
from .output_layout import manifest_enabled, new_run_dir, subject_dir, write_manifest
from .subject_utils import normalize_subject
from .url_builder import action_argument, format_target_url


def run_batch_screenshot_task(companies, log_queue, base_output, selected_sites, CONFIG,
                              extra_delay=0, run_dir=None):
    companies = list(companies)
    run_dir = run_dir or new_run_dir(base_output)
    os.makedirs(run_dir, exist_ok=True)
    log_queue.put(f"[输出] 本轮目录: {run_dir}\n")

    selected_config = {k: v for k, v in CONFIG.items() if k in selected_sites}
    batch_workflow_config = {
        k: v for k, v in selected_config.items() if v.get("batch_workflow")
    }
    active_config = {
        k: v for k, v in selected_config.items() if not v.get("batch_workflow")
    }
    page = None
    set_captcha_site_count(len(selected_sites))

    try:
        if active_config:
            page = get_clean_page()
            # 若接管了上一次运行未退干净的浏览器，先清理残留标签页，只保留主标签页
            close_other_tabs(page, keep_tab_id=page.latest_tab.tab_id)

        for index, raw_subject in enumerate(companies if page is not None else []):
            subject = normalize_subject(raw_subject)
            display_name = subject["display_name"]
            log_queue.put(f"\n[任务] 开始处理: {display_name}\n")

            company_folder = subject_dir(run_dir, index)
            os.makedirs(company_folder, exist_ok=True)

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
                        except Exception:
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
                            # 关闭原搜索页，避免残留
                            try:
                                old_tab = page.get_tab(original_id)
                                if old_tab:
                                    old_tab.close()
                            except Exception:
                                pass
                            # 若一次弹出多个新窗口，多余的也一并关闭
                            for extra_id in new_tabs[:-1]:
                                try:
                                    extra_tab = page.get_tab(extra_id)
                                    if extra_tab:
                                        extra_tab.close()
                                except Exception:
                                    pass
                        elif track_data["check_count"] >= 10 or (time.time() - track_data["start_time"]) > 2.5:
                            # 轮询了10次（约2秒）都没新窗口，放弃等待，把原窗口送去截图
                            tab_tracking_pool.pop(original_id)
                            result_pool[original_id] = {
                                "filename": track_data["filename"],
                                "save_name": track_data["save_name"],
                                "start_time": time.time(),
                            }
                    except Exception:
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
                        except Exception:
                            is_complete = False 
                        
                        # 结果页渲染最多等 10 秒（减少无谓的卡顿等待）
                        if is_complete or elapsed > 10:
                            result_pool.pop(t_id)

                            try:
                                # CDP 切标签页 + 激活浏览器窗口，确保物理截屏拍到的是本页
                                bring_to_front(tab)
                                time.sleep(0.15) # 降低缓冲时间

                                post_action_func = tab_config[filename].get('post_action')
                                if post_action_func:
                                    try:
                                        post_action_func(
                                            tab,
                                            action_argument(tab_config[filename], subject),
                                        )
                                    except Exception:
                                        pass

                                time.sleep(0.3 + extra_delay)
                                screenshot_pyautogui(company_folder, save_name)
                            finally:
                                # 无论截图是否成功，标签页都必须关闭，防止残留
                                try:
                                    tab.close()
                                except Exception:
                                    pass
                    except Exception as e:
                        log_queue.put(f"  -> [警告] {filename} 阶段三异常: {repr(e)}\n")
                        result_pool.pop(t_id, None)
                time.sleep(0.2)
                
            try:
                page.get_tab(main_tab_id).run_cdp('Page.bringToFront')
            except Exception:
                pass

            for filename, config in foreground_config.items():
                run_foreground_site(page, subject, company_folder, filename, config, log_queue, extra_delay)

            try:
                page.get_tab(main_tab_id).run_cdp('Page.bringToFront')
            except Exception:
                pass

            for filename, config in workflow_config.items():
                save_name = config.get("save_as", filename)
                try:
                    log_queue.put(f"  -> [独立模式] {filename} 开始执行。\n")
                    config["workflow"](page, subject, company_folder, save_name, log_queue)
                    log_queue.put(f"  -> [独立模式] {filename} 完成。\n")
                except Exception as workflow_err:
                    log_queue.put(f"  -> [警告] {filename} 独立模式失败: {repr(workflow_err)}\n")

            # 每家公司处理完毕后兜底清理：除主标签页外全部关闭，防止异常路径下残留累积
            close_other_tabs(page, keep_tab_id=main_tab_id)

        if page is not None:
            try:
                page.quit()
            except Exception as close_err:
                log_queue.put(f"  -> [提示] 浏览器关闭时出现异常: {repr(close_err)}\n")
            page = None

        for filename, config in batch_workflow_config.items():
            save_name = config.get("save_as", filename)
            try:
                log_queue.put(f"\n[整批模式] {filename} 开始执行。\n")
                config["batch_workflow"](
                    list(companies),
                    run_dir,
                    save_name,
                    log_queue,
                )
                log_queue.put(f"[整批模式] {filename} 执行完成。\n")
            except Exception as workflow_err:
                log_queue.put(
                    f"  -> [警告] {filename} 整批模式失败: {repr(workflow_err)}\n"
                )

    except Exception as e:
        log_queue.put(f">>>> [错误] 处理全局失败: {repr(e)}\n")
    finally:
        if page is not None:
            # 先尽量关闭所有标签页，再退出浏览器；即使 quit 失败也不留残留
            close_other_tabs(page, keep_tab_id=None)
            try:
                page.quit()
            except Exception as close_err:
                log_queue.put(f"  -> [提示] 浏览器关闭时出现异常: {repr(close_err)}\n")
        set_captcha_site_count(0)
        if manifest_enabled():
            saved = write_manifest(run_dir, companies)
            if saved:
                log_queue.put("[输出] 已写出主体清单 manifest.json（含映射，注意保密）\n")
        log_queue.put("DONE")
