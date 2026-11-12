import os
import time
from datetime import datetime
from DrissionPage import ChromiumPage
import pyautogui

def main():
    # ==================== 自定义配置区域 ====================
    # 支持绝对路径和相对路径
    base_save_dir = r"pics" 
    # ========================================================
    
    # 准备测试数据（请在这里替换为实际的国家税务总局贵州省税务局查询页 URL）
    target_sites = {
        "8、国家税务总局贵州省税务局": "https://guizhou.chinatax.gov.cn/zdsswfsxajxxgbl/index.html"  # <--- 请在此处替换为真实URL
    }
    
    user_data = [
        {"name": "示例省誉能装备（集团）有限公司", "id_card": ""},
        {"name": "示例省誉兴矿山科技有限公司", "id_card": ""},
        {"name": "示例市博跃新能源开发利用有限公司", "id_card": ""},
        {"name": "示例省黑金供应链管理有限公司", "id_card": ""},
        {"name": "示例市古城自来水有限责任公司", "id_card": ""},
        {"name": "示例市楼下河水电开发有限公司", "id_card": ""},
        {"name": "示例省誉晟机械再制造有限公司", "id_card": ""},
        {"name": "示例市乌都河水电开发有限责任公司", "id_card": ""},
        {"name": "示例省盘兴能投商贸有限公司", "id_card": ""},
        {"name": "示例省盘兴能源开发投资股份有限公司", "id_card": ""},
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
        
        for user in user_data:
            name = user.get("name")
            id_card = user.get("id_card")
            print(f"\n  -> 正在处理用户: {name}")
            
            # 每次查完一个人重新刷新初始 URL，确保表单干净
            page.get(url)
            page.wait.load_start() 
            
            # 1. 填写企业/个人姓名 (id="nsrmc")
            page.ele('#nsrmc').clear()
            page.ele('#nsrmc').input(name)
            
            # 2. 填写纳税人识别号 (id="nsrsbh")（如果存在且不为空）
            if id_card:
                page.ele('#nsrsbh').clear()
                page.ele('#nsrsbh').input(id_card)
                
            # ==========================================
            # 3. 点击查询并等待结果
            # ==========================================
            print("     点击查询按钮...")
            # 精确匹配 id="search_cx" 的 span 标签
            page.ele('#search_cx').click()
            
            print("     等待查询结果加载...")
            time.sleep(3)  # 给系统响应和渲染结果留出时间
            
            # ==========================================
            # 4. 结果截图与文件保存
            # ==========================================
            # 拼接最终的文件夹路径：自定义根路径 / 姓名
            user_dir = os.path.join(base_save_dir, name)
            os.makedirs(user_dir, exist_ok=True)
            
            # 拼接最终的文件名
            screenshot_filename = os.path.join(user_dir, f"{site_name}.png")
            
            # 调用 pyautogui 全屏截图（带系统任务栏时间）
            pyautogui.screenshot(screenshot_filename)
            print(f"     已保存带系统时间的结果截图: {screenshot_filename}")
        
        # 当前网站的所有人跑完后，关闭当前浏览器
        print(f"[{site_name}] 处理完毕，正在清理浏览器环境...")
        page.quit()

    print("\n所有任务处理完毕！")

if __name__ == "__main__":
    main()