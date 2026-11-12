import os
import time
from DrissionPage import ChromiumPage
import pyautogui

def main():
    # ==================== 自定义配置区域 ====================
    # 支持绝对路径和相对路径
    base_save_dir = r"pics" 
    # 固定保存的文件名
    save_file_name = "21、中国统计信息网"
    # ========================================================
    
    # 准备测试数据（请在这里替换为实际的“高级搜索”页面的 URL）
    target_sites = {
        save_file_name: "http://www.tjcn.org/search/"  # <--- 请在此处替换为真实URL
    }
    
    # 你打算直接用列表储存的名称数据
    search_names = [
    "示例市宏信国有资产投资管理有限公司",
    "示例市兴农农村经济发展有限公司",
    "示例市民惠住房投资开发有限公司",
    "示例市示范区经济适用房开发有限公司",
    # "示例市示范区城市资产经营有限公司",
    # "示例省誉能装备（集团）有限公司",
    # "示例省誉兴矿山科技有限公司",
    # "示例市博跃新能源开发利用有限公司",
    # "示例省黑金供应链管理有限公司",
    # "示例市古城自来水有限责任公司",
    # "示例市楼下河水电开发有限公司",
    # "示例省誉晟机械再制造有限公司",
    # "示例市乌都河水电开发有限责任公司",
    # "示例省盘兴能投商贸有限公司",
    # "示例省盘兴能源开发投资股份有限公司",
    # "示例市示范区城市资产经营有限公司",
    # "示例市示范区城投置业有限公司",
    # "示例市第二市政工程有限公司",
    # "示例市示范区水利建筑工程有限公司",
    # "示例市兴源水务有限公司",
    # "示例市古城文化旅游资源开发有限公司",
    ]

    # 开始自动化循环
    for site_name, url in target_sites.items():
        print(f"\n=================================")
        print(f"开始处理网站: [{site_name}] {url}")
        print(f"=================================")
        
        # 打开浏览器窗口
        page = ChromiumPage()
        page.set.window.max()
        
        # 访问页面并等待基础加载完成
        page.get(url)
        page.wait.load_start() 
        
        for name in search_names:
            print(f"\n  -> 正在处理名称: {name}")
            
            # 每次查完一个人重新刷新初始 URL，确保输入框干净
            page.get(url)
            page.wait.load_start() 
            
            # 1. 定位到 id="keyboard2" 的输入框并输入名称
            search_input = page.ele('#keyboard2')
            search_input.clear()
            search_input.input(name)
            
            # 如果输入完需要模拟敲回车进行搜索，可以取消下面这行的注释：
            # search_input.input('\n') 
            
            print("     等待页面稳定或搜索结果加载...")
            time.sleep(3)  # 留出充足的渲染/加载时间以供截图
            
            # ==========================================
            # 2. 结果截图与文件保存逻辑
            # ==========================================
            # 建立以【名称/企业名】命名的文件夹
            user_dir = os.path.join(base_save_dir, name)
            os.makedirs(user_dir, exist_ok=True)
            
            # 拼接最终的文件名：自定义根路径 / 名称 / 21、中国统计信息网.png
            screenshot_filename = os.path.join(user_dir, f"{site_name}.png")
            
            # 调用 pyautogui 全屏截图（带系统任务栏时间）
            pyautogui.screenshot(screenshot_filename)
            print(f"     已成功保存截图: {screenshot_filename}")
        
        # 当前网站的所有人跑完后，关闭当前浏览器
        print(f"[{site_name}] 处理完毕，正在清理浏览器环境...")
        page.quit()

    print("\n所有任务处理完毕！")

if __name__ == "__main__":
    main()