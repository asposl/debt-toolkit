import os
import time
from playwright.sync_api import Playwright, sync_playwright
import pyautogui

# 你的公司列表
company_list = [
    # "示例市宏信国有资产投资管理有限公司",
    # "示例市兴农农村经济发展有限公司",
    # "示例市民惠住房投资开发有限公司",
    # "示例市示范区经济适用房开发有限公司",
        "示例市示范区城市资产经营有限公司",
    "示例市示范区城投置业有限公司",
    "示例市第二市政工程有限公司",
    "示例市示范区水利建筑工程有限公司",
    "示例市兴源水务有限公司",
    "示例市古城文化旅游资源开发有限公司",




                 ]

def run(playwright: Playwright) -> None:
    # 1. 启动浏览器并实现真正全屏
    browser = playwright.chromium.launch(
        headless=False, 
        args=["--start-maximized"]
    )
    context = browser.new_context(no_viewport=True)
    page = context.new_page()
    
    print("正在打开天眼查首页...")
    try:
        page.goto(
            "https://www.tianyancha.com/company/22822", 
            wait_until="commit",  
            timeout=60000         
        )
    except Exception as e:
        print(f"打开首页略有延迟，但我们可以继续：{e}")
    
    print("\n" + "="*50)
    print("【提示】请在弹出的浏览器中完成登录。")
    print("登录成功并确保页面加载完成后，回到这里（终端）按下【回车键】继续运行爬虫...")
    print("="*50 + "\n")
    
    input() # 阻塞在这里，等待你敲回车
    print("收到指令，开始执行批量搜索及截图...")

    # 【修改点 1】定义基础输出路径
    base_dir = r"截图输出"

    # 2. 遍历公司列表进行搜索
    for company in company_list:
        try:
            print(f"正在处理: {company}")
            
            # 【修改点 2】为当前公司创建专属文件夹：pics\公司名
            company_dir = os.path.join(base_dir, company)
            if not os.path.exists(company_dir):
                os.makedirs(company_dir)
            
            # 定位搜索框并输入
            search_box = page.get_by_role("textbox", name="请输入公司名称、老板姓名、品牌名称等")
            search_box.click()
            search_box.fill(company)
            
            # 点击搜索
            page.get_by_role("button", name="天眼一下").click()
            
            # 等待搜索结果的 DOM 结构加载
            page.wait_for_load_state("domcontentloaded")
            
            # 直接寻找包含“公司名字”的第一个 a 标签链接
            company_link = page.locator(f"a:has-text('{company}')").first
            company_link.wait_for(state="visible", timeout=5000)
            
            # 点击链接并捕获弹出的新页面
            with page.expect_popup() as page1_info:
                company_link.click()
            page1 = page1_info.value
            
            # 确保新页面（详情页）加载，并给 4 秒让数据和图表渲染出来
            page1.wait_for_load_state("domcontentloaded")
            time.sleep(4) 
            
            # 将新标签页推到 Windows 最前端，准备用 pyautogui 截图
            page1.bring_to_front()
            time.sleep(0.5) 
            
            # 【修改点 3】组合最终的截图路径：pics\公司名\天眼查.png
            screenshot_path = os.path.join(company_dir, "天眼查.png")
            
            # 包含 Windows 任务栏和时间的全屏截图
            screenshot = pyautogui.screenshot()
            screenshot.save(screenshot_path)
            print(f"【成功】截图已保存至: {screenshot_path}")
            
            # 关闭详情页，回到搜索主页
            page1.close()
            time.sleep(1)
            
        except Exception as e:
            print(f"【失败】处理 {company} 时发生错误: {e}")
            # 如果中间出错，尝试回退到天眼查首页，避免影响下一次循环
            try:
                page.goto("https://www.tianyancha.com/company/22822", wait_until="commit")
            except:
                pass
            continue

    # 关闭浏览器
    context.close()
    browser.close()

with sync_playwright() as playwright:
    run(playwright)