import os
import time
from datetime import datetime
from DrissionPage import ChromiumPage
import ddddocr
import pyautogui

def main():
    # ==================== 自定义配置区域 ====================
    # 支持绝对路径和相对路径
    base_save_dir = r"截图输出"
    # ========================================================

    # 初始化 ddddocr (关闭广告输出)
    ocr = ddddocr.DdddOcr(show_ad=False)
    
    # 准备测试数据
    target_sites = {
        "8、国家税务总局江苏省税务局": "https://jiangsu.chinatax.gov.cn/module/jslib/bulletin3/lpindex.html"
    }
    
    user_data = [
        # {"name": "示例市新城投资开发集团有限公司", "id_card": ""},
    #     {"name": "示例市示范区城市资产经营有限公司", "id_card": "91320800MA0000001X"},
    #     {"name": "示例市示范区城投置业有限公司", "id_card": "91320800MA0000002X"},
    #     {"name": "示例市第二市政工程有限公司", "id_card": "91320800MA0000001X"},
    #     {"name": "示例市示范区水利建筑工程有限公司", "id_card": "91320800MA0000001X"},
    #     {"name": "示例市兴源水务有限公司", "id_card": "91320800MA0000001X"},
    #     {"name": "示例市古城文化旅游资源开发有限公司", "id_card": "91320800MA0000001X"},
        {"name": "示例市兴农农村经济发展有限公司", "id_card": ""},
        {"name": "示例市民惠住房投资开发有限公司", "id_card": ""},
        {"name": "示例市示范区经济适用房开发有限公司", "id_card": ""},
        {"name": "示例市宏信国有资产投资管理有限公司", "id_card": ""},


    ]

    # 开始自动化循环
    for site_name, url in target_sites.items():
        print(f"\n=================================")
        print(f"开始处理网站: [{site_name}] {url}")
        print(f"=================================")
        
        # 打开浏览器窗口
        page = ChromiumPage()
        page.set.window.max()
        
        for user in user_data:
            name = user.get("name")
            id_card = user.get("id_card")
            print(f"\n  -> 正在处理用户: {name}")
            
            # 进入用户页面时只在最开始访问一次 URL
            page.get(url)
            page.wait.load_start() 
            
            # 提前定位好长期存在的表单元素，减少重复检索时间
            input_name = page.ele('#name')
            input_nsrsbh = page.ele('#nsrsbh')
            input_rand = page.ele('#rand')
            captcha_ele = page.ele('#randImage')
            search_btn = page.ele('@onclick=refreshIf()')
            
            max_retries = 5
            success = False
            
            for retry in range(max_retries):
                print(f"    [第 {retry + 1} / {max_retries} 次尝试]")
                
                # 1. 填写企业/个人姓名
                input_name.clear()
                input_name.input(name)
                
                # 2. 填写纳税人识别号
                if id_card:
                    input_nsrsbh.clear()
                    input_nsrsbh.input(id_card)
                
                # 如果不是第一次尝试，说明上一次失败了，点击验证码图片刷新
                if retry > 0:
                    captcha_ele.click()
                    # 智能等待验证码图片加载更新，抛弃固定的 time.sleep
                    page.wait(0.5) 
                    
                # 3. 验证码处理
                img_bytes = captcha_ele.get_screenshot(as_bytes=True)
                code_text = ocr.classification(img_bytes)
                print(f"     识别到验证码: {code_text}")
                
                # 填写验证码
                input_rand.clear()
                input_rand.input(code_text)
                
                # 4. 点击查询
                search_btn.click()
                
                # 5. 动态等待：不再死等3秒，而是等待“结果表格”或“错误提示”任意一个出现即可
                # 这一步是提速的核心
                is_loaded = page.wait.eles_loaded(['text=验证码错误，请重新输入', '.table_main', '#searchResult'], timeout=4)
                
                if not is_loaded:
                    # 如果超时了什么都没等到，稳妥起见稍微补一个小等待
                    time.sleep(1)
                
                # 6. 校验结果
                error_ele = page.ele('text=验证码错误，请重新输入', timeout=0.1)
                
                if error_ele:
                    print("     ❌ 验证码错误，直接在当前页重试...")
                    # 仅在验证码输入框内回车或清空，不刷新整个网页
                    continue
                else:
                    print("     ✅ 验证码正确，开始保存结果。")
                    success = True
                    
                    # 确保 Pyautogui 截图前页面渲染完毕
                    time.sleep(0.5) 
                    
                    # 7. 自定义文件保存逻辑
                    user_dir = os.path.join(base_save_dir, name)
                    os.makedirs(user_dir, exist_ok=True)
                    
                    screenshot_filename = os.path.join(user_dir, f"{site_name}.png")
                    pyautogui.screenshot(screenshot_filename)
                    print(f"     已保存截图: {screenshot_filename}")
                    break
                    
            if not success:
                print(f"    ⚠️ 警告: 用户 [{name}] 连续 {max_retries} 次验证码识别失败。")
        
        print(f"\n[{site_name}] 处理完毕，正在清理浏览器环境...")
        page.quit()

    print("\n所有任务处理完毕！")

if __name__ == "__main__":
    main()