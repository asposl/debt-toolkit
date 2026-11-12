import os
import time
from datetime import datetime
from DrissionPage import ChromiumPage
import pyautogui

def main():
    # ==================== 自定义配置区域 ====================
    # 截图保存的根目录
    base_save_dir = r"pics" 
    
    # 百度资讯/AI搜索的目标 URL
    target_sites = {
        "33、其他网站和媒体报道": "https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&rsv_dl=ns_pc&word=x"  # 请确保此页面包含你提到的 id 元素，如果不是该URL请自行替换
    }
    
    # 需要查询的数据
    user_data = [
        {"name": "示例省誉能装备（集团）有限公司", "id_card": "123456789012345678"},  # 示例增加了身份证
        {"name": "示例省誉兴矿山科技有限公司", "id_card": "876543210987654321"},
        {"name": "示例市博跃新能源开发利用有限公司", "id_card": ""},  # 身份证为空的情况也会兼容
        {"name": "示例省黑金供应链管理有限公司", "id_card": "112233445566778899"},
    ]
    # ========================================================

    # 开始自动化循环
    for site_name, url in target_sites.items():
        print(f"\n=================================")
        print(f"开始处理网站: [{site_name}] {url}")
        print(f"=================================")
        
        # 打开浏览器窗口
        page = ChromiumPage()
        page.set.window.max()
        
        for user in user_data:
            name = user.get("name", "")
            id_card = user.get("id_card", "")
            
            # 将姓名和身份证用空格隔开（如果身份证为空，则只输姓名）
            search_keyword = f"{name} {id_card}".strip()
            print(f"\n  -> 正在搜索关键词: [{search_keyword}]")
            
            # 每次重新访问初始 URL，确保搜索框是干净的
            page.get(url)
            page.wait.load_start() 
            
            # 1. 准确定位 textarea 搜索框并输入组合后的关键词
            # 使用了你提供的 id="chat-textarea"
            search_box = page.ele('#chat-textarea')
            search_box.clear()
            search_box.input(search_keyword)
            
            # 2. 点击 “百度一下” 按钮
            # 使用了你提供的 id="ci-submit-button"
            print("     点击搜索按钮...")
            page.ele('#ci-submit-button').click()
            
            # 3. 等待查询结果加载
            print("     等待搜索结果加载与渲染...")
            time.sleep(4)  # 资讯或AI搜索渲染可能较慢，给予4秒等待时间
            
            # 4. 创建保存目录
            user_dir = os.path.join(base_save_dir, name)
            os.makedirs(user_dir, exist_ok=True)
            
            # 5. 拼接文件名并全屏截图（包含Windows任务栏时间）
            screenshot_filename = os.path.join(user_dir, f"{site_name}.png")
            pyautogui.screenshot(screenshot_filename)
            print(f"     [成功] 已保存带系统时间的全屏截图: {screenshot_filename}")
        
        # 关闭当前浏览器
        print(f"\n[{site_name}] 所有人员处理完毕，正在清理浏览器环境...")
        page.quit()

    print("\n所有任务处理完毕！")

if __name__ == "__main__":
    main()