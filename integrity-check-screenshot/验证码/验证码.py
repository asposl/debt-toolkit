# -*- coding: utf-8 -*-
import os
import time
import base64
import cv2
import numpy as np
import pyautogui
import ddddocr
from DrissionPage import ChromiumPage

# ==================== 1. 自定义通用配置区域 ====================
# [配置 A] 支持绝对路径和相对路径，保存截图的根目录
BASE_SAVE_DIR = r"截图输出" 

# [配置 B] 调试开关：设置为 True 则执行查询，设置为 False 则直接跳过该网站
SITE_SWITCHES = {
    "最高法院_失信人": True,   # 对应：5、全国法院失信被执行人名单信息公布与查询
    "最高法院_综合查询": True, # 对应：4、中国执行信息公开网—综合查询
    "证监会_失信平台": True    # 对应：3、中国证监会证券期货市场失信记录查询平台
}

# [配置 C] 统一维护需要查询的企业/用户名单
USER_DATA = [
        # {"name": "示例市示范区城市资产经营有限公司", "id_card": "91320800MA0000001X"},
        # {"name": "示例市示范区城投置业有限公司", "id_card": "91320800MA0000002X"},
        # {"name": "示例市第二市政工程有限公司", "id_card": "91320800MA0000001X"},
        # {"name": "示例市示范区水利建筑工程有限公司", "id_card": "91320800MA0000001X"},
        # {"name": "示例市兴源水务有限公司", "id_card": "91320800MA0000001X"},
        # {"name": "示例市古城文化旅游资源开发有限公司", "id_card": "91320800MA0000001X"},
        # {"name": "示例市新城投资开发集团有限公司", "id_card": ""},
        {"name": "示例市兴农农村经济发展有限公司", "id_card": ""},
        {"name": "示例市民惠住房投资开发有限公司", "id_card": ""},
        {"name": "示例市示范区经济适用房开发有限公司", "id_card": ""},
        {"name": "示例市宏信国有资产投资管理有限公司", "id_card": ""},
]
# ============================================================


# ==================== 2. 滑块验证码辅助函数 ====================
def get_base64_img_bytes(img_element):
    """提取Base64图片元素的字节流"""
    if not img_element:
        return None
    try:
        src = img_element.attr("src")
        if src and "base64," in src:
            return base64.b64decode(src.split("base64,")[1])
    except Exception:
        pass
    return None

def find_slider_distance_cv2(slider_bytes, bg_bytes):
    """使用OpenCV计算滑块需要滑动的距离"""
    slider = cv2.imdecode(np.frombuffer(slider_bytes, np.uint8), cv2.IMREAD_COLOR)
    bg = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)

    s = cv2.Canny(cv2.cvtColor(slider, cv2.COLOR_BGR2GRAY), 100, 200)
    b = cv2.Canny(cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY), 100, 200)

    _, _, _, max_loc = cv2.minMaxLoc(
        cv2.matchTemplate(b, s, cv2.TM_CCOEFF_NORMED)
    )
    return max_loc[0], bg.shape[1]


# ==================== 3. 主程序逻辑 ====================
def main():
    # 检查是否至少开启了一个网站，如果全为 False，直接退出
    if not any(SITE_SWITCHES.values()):
        print("提示：SITE_SWITCHES 中的所有网站开关均为 False，程序退出。")
        return

    # 初始化常规验证码 OCR 识别器 (关闭广告输出)
    ocr = ddddocr.DdddOcr(show_ad=False)
    temp_captcha_path = "temp_captcha.png"
    max_retries = 5  # 统一最大重试次数

    # 统一浏览器启动参数
    browser = ChromiumPage()
    browser.set.load_mode.eager() # 启用 eager 动态提速模式
    browser.set.window.max()

    # ------------------------------------------------------------
    # 核心部分 A：处理 【最高法院执行公开网】 的两个子栏目
    # ------------------------------------------------------------
    court_sites_config = {
        "最高法院_失信人": {
            "site_name": "5、全国法院失信被执行人名单信息公布与查询",
            "url": "https://zxgk.court.gov.cn/shixin/"
        },
        "最高法院_综合查询": {
            "site_name": "4、中国执行信息公开网—综合查询",
            "url": "https://zxgk.court.gov.cn/zhzxgk/"
        }
    }

    for switch_key, config in court_sites_config.items():
        if not SITE_SWITCHES.get(switch_key, False):
            print(f"\n跳过网站: [{config['site_name']}] (开关已关闭)")
            continue

        site_name = config["site_name"]
        url = config["url"]

        print(f"\n==================================================")
        print(f" 开始处理最高院网站: [{site_name}]")
        print(f"==================================================")
        
        if len(browser.tab_ids) > 1:
            while len(browser.tab_ids) > 1:
                browser.get_tab(browser.tab_ids[-1]).close()
                time.sleep(0.1) # 缩减关闭标签的等待
        
        home = browser.get_tab(browser.tab_ids[0])
        
        for user in USER_DATA:
            name = user.get("name")
            id_card = user.get("id_card")
            print(f"\n -> 正在处理用户: {name}")
            
            captcha_success = False
            
            # 【优化点1】将页面初始化加载移到重试循环外，避免验证码识别错时重复加载整个网页
            home.get(url)
            
            for retry in range(1, max_retries + 1):
                print(f"    [第 {retry}/{max_retries} 次尝试验证码]")
                
                # 【优化点2】用显式等待代替硬睡眠，确保输入框已在 eager 模式下加载完
                home.wait.ele_displayed('#pName', timeout=3)
                
                # 输入数据
                home.ele('#pName').clear().input(name)
                if id_card:
                    home.ele('#pCardNum').clear().input(id_card)
                    
                captcha_ele = home.ele('#captchaImg')
                captcha_ele.click()  # 强刷验证码
                
                # 【优化点3】这里缩减为 0.5s，或利用 wait 等待图片 src 属性更新完毕（若无法探测可用短暂睡眠）
                time.sleep(0.6) 
                
                captcha_ele.save(path='.', name=temp_captcha_path)
                with open(temp_captcha_path, "rb") as f:
                    img_bytes = f.read()
                code_text = ocr.classification(img_bytes)
                print(f"     识别到字符验证码: {code_text}")
                
                home.ele('#yzm').clear().input(code_text)
                print("     点击查询按钮...")
                home.ele('text=查询').click()
                
                # 【优化点4】动态判定：最高院如果验证码错误，会立刻弹窗或在 .important 渲染文字
                # 盲等 3 秒太慢，改成每 0.2 秒探测一次结果
                is_error = False
                for _ in range(10): # 最多等 2 秒
                    error_element = home.ele('.important', timeout=0.2)
                    if error_element and ("验证码错误" in error_element.text or "验证码已过期" in error_element.text):
                        is_error = True
                        break
                    # 如果页面出现了具体的结果表格，则说明成功了，也可以提前 break
                    if home.ele('css:.ResultList', timeout=0.1) or home.ele('text=没有符合条件的数据', timeout=0.1):
                        break

                if is_error:
                    print("     [结果] 验证码错误或过期，准备重试...")
                    if os.path.exists(temp_captcha_path): os.remove(temp_captcha_path)
                    # 验证码错了，不用 get(url)，清除当前输入框直接进入下一次循环输入
                    continue 
                else:
                    print("     [结果] 验证码正确，成功进入结果页面。")
                    captcha_success = True
                    break 
            
            if not captcha_success:
                print(f"❌ 【警告】用户 [{name}] 连续 {max_retries} 次验证码失败，跳过。")
                if os.path.exists(temp_captcha_path): os.remove(temp_captcha_path)
                continue 

            # 创建独立文件夹并截全屏
            user_dir = os.path.join(BASE_SAVE_DIR, name)
            os.makedirs(user_dir, exist_ok=True)
            screenshot_filename = os.path.join(user_dir, f"{site_name}.png")
            
            # 确保页面渲染完成再截图
            time.sleep(0.5)
            pyautogui.screenshot(screenshot_filename)
            print(f"     已成功保存截图: {screenshot_filename}")
            
            if os.path.exists(temp_captcha_path):
                os.remove(temp_captcha_path)

    # ------------------------------------------------------------
# ------------------------------------------------------------
    # 核心部分 B：处理 【中国证监会证券期货市场失信记录查询平台】
    # ------------------------------------------------------------
    zjh_url = "https://neris.csrc.gov.cn/shixinchaxun/neris.csrc.gov.cn"
    zjh_site_name = "3、中国证监会证券期货市场失信记录查询平台"
    
    if SITE_SWITCHES.get("证监会_失信平台", False):
        print(f"\n==================================================")
        print(f" 开始处理证监会网站: [{zjh_site_name}]")
        print(f"==================================================")

        # 确保一开始只有一个初始空白页或干净的主页，防止混淆
        if len(browser.tab_ids) > 1:
            while len(browser.tab_ids) > 1:
                browser.get_tab(browser.tab_ids[-1]).close()
                time.sleep(0.1)

        home = browser.get_tab(browser.tab_ids[0])

        for user in USER_DATA:
            name = user["name"]
            card = user["id_card"]
            print(f"\n -> 正在处理用户: {name}")

            # 每次循环都让主页面明确跳转到初始查询页，彻底清理上一次的残留
            home.get(zjh_url)
            home.wait.ele_displayed('css:input[placeholder*="必须填写姓名"]', timeout=5)

            try:
                home.ele('css:input[placeholder*="必须填写姓名"]').clear().input(name)
                home.ele('css:input[placeholder*="需要填写完整"]').clear().input(card)

                # 记录点击查询前的所有标签页 ID 集合
                old_tabs = set(browser.tab_ids)
                home.ele("css:.searchBtn").click()
                time.sleep(1)

                # 滑块验证码处理逻辑
                retry_count = 0
                slider_passed = False
                
                while retry_count < max_retries:
                    try:
                        bg = home.ele("css:.verify-img-panel img", timeout=1.5) or home.ele("css:.popup-bg", timeout=1.5)
                        slider = home.ele("css:.verify-sub-block img", timeout=1.5) or home.ele("css:.popup-slide", timeout=1.5)
                        drag = home.ele("css:.verify-move-block", timeout=1.5) or home.ele("css:.slider-btn", timeout=1.5)

                        if not (bg and slider and drag) or bg.rect.size[0] == 0:
                            print("     未检测到滑块弹窗或验证码已通过。")
                            slider_passed = True
                            break

                        print(f"     检测到滑块验证码，开始第 {retry_count + 1} 次轨迹识别...")
                        
                        bg_bytes = get_base64_img_bytes(bg)
                        slider_bytes = get_base64_img_bytes(slider)

                        if bg_bytes and slider_bytes:
                            x, ow = find_slider_distance_cv2(slider_bytes, bg_bytes)
                            bg_size = bg.rect.size
                            if bg_size[0] == 0:
                                print("     验证码元素已失效，判定为通过。")
                                slider_passed = True
                                break
                                
                            scale = bg_size[0] / ow
                            distance = x * scale

                            home.actions.move_to(drag).hold()
                            home.actions.move(offset_x=distance, offset_y=0, duration=1.2)
                            home.actions.release()
                            time.sleep(2) # 拖拽完给系统响应时间
                        else:
                            print("     未能获取验证码图片字节流，重试...")
                            time.sleep(1)

                    except Exception as ce:
                        if "没有位置及大小" in str(ce) or "ElementLostError" in str(ce):
                            print("     验证码元素在拖拽后瞬时消失，判定为验证成功！")
                            slider_passed = True
                            break
                        else:
                            print(f"     滑块处理时遇到偶发错误: {ce}，继续尝试...")
                            time.sleep(1)

                    retry_count += 1
                
                if not slider_passed:
                    print(f"❌ 警告：已达最大重试次数 {max_retries}，滑块仍未通过，跳过此人。")
                    continue

                print("     等待新结果标签页弹出并加载...")
                result_tab = None
                
                # ✨【修改点 1】精准动态捕获新弹出的搜索结果标签页
                for _ in range(25):  # 最多等待 5 秒钟弹出新页面
                    current_tabs = set(browser.tab_ids)
                    new_tabs = current_tabs - old_tabs
                    if new_tabs:
                        result_tab = browser.get_tab(list(new_tabs)[0])
                        break
                    time.sleep(0.2)

                # 如果没有新标签页弹出，说明结果直接在原网页或者点击失效
                if not result_tab:
                    print("     未检测到新标签页弹出，将使用原页面进行检测。")
                    result_tab = home

                # ✨【修改点 2】强力等待新标签页内部的实际数据元素渲染完成再执行下一步
                # 证监会结果页通常包含 class 为 .table 的表格，或者特定的无数据提示，这里盲等 + 显式元素混合等待
                time.sleep(1.5) 
                
                # ✨【修改点 3】操作系统级别焦点切换：将新页面激活，并真正引导操作系统前端窗口聚焦
                result_tab.set.activate()
                
                # 准备截图保存路径
                folder = os.path.join(BASE_SAVE_DIR, name)
                os.makedirs(folder, exist_ok=True)
                screenshot_filename = os.path.join(folder, f"{zjh_site_name}.png")
                
                # 确保浏览器窗口完全置顶和渲染无误后，使用 pyautogui 截取全屏（含任务栏时间）
                time.sleep(0.5)
                pyautogui.screenshot(screenshot_filename)
                print(f" 成功保存【新弹出结果页】截图: {screenshot_filename}")

                # ✨【修改点 4】顺畅返回逻辑：截图完成后，如果确认打开了新标签页，将其关闭，把焦点还给主查询页
                if result_tab != home:
                    result_tab.close()
                    time.sleep(0.2)
                
                # 让主页面重新激活，为下一个用户的搜索做准备
                home.set.activate()
                time.sleep(0.3)

            except Exception as e:
                print(f"❌ 证监会模块内发生错误：{e}")
    else:
        print(f"\n跳过网站: [{zjh_site_name}] (开关已关闭)")

    print("\n==================================================")
    print(" 🎉 运行结束！")
    print("==================================================")
    browser.quit()

if __name__ == "__main__":
    main()