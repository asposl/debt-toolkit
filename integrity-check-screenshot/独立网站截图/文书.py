import os
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# ==================== 配置区域 ====================
# 1. 自定义输出根路径（可以在这里指定任意盘符和文件夹）
# 示例： "D:/文书网截图结果" 或 "C:/Users/Administrator/Desktop/Screenshots"
# 如果保持 "." 则表示保存在当前脚本所在的目录下
BASE_OUTPUT_DIR = r"pics" 

# 2. 你的公司名称/检索列表
COMPANY_LIST = [
    # "示例市宏信国有资产投资管理有限公司",
    # "示例市兴农农村经济发展有限公司",
    # "示例市民惠住房投资开发有限公司",
    # "示例市示范区经济适用房开发有限公司",
    # "示例市新城投资开发集团有限公司",
    # "示例市示范区城市资产经营有限公司",
    # "示例市示范区城投置业有限公司",
    # "示例市第二市政工程有限公司",
    # "示例市示范区水利建筑工程有限公司",
    # "示例市兴源水务有限公司",
    # "示例市古城文化旅游资源开发有限公司",
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
    # "张三 110101199001011234",
    # "李四 110101199002022345",
    # "王五 110101199003033456",
    # "赵六 110101199004044567",
    # "钱七 110101199005055678",
    # "孙八 110101199006066789",
    # "周九 110101199007077890",
    # "吴十 110101199008088901",
    # "郑一 110101199009099012",
    # "冯二 110101199010100123"
"陈三 110101199011111234",
"褚四 110101199012122345",
"卫五 110101199101013456",
"蒋六 110101199102024567",
"沈七 110101199103035678",
"韩八 110101199104046789",
"杨九 110101199105057890",
"朱十 110101199106068901",
    
]

# 3. 需要访问的网站登录/搜索页 URL
TARGET_URL = "https://wenshu.court.gov.cn/"

# 4. 元素选择器配置（根据网页实际情况修改：.表示class，#表示id）
SELECTOR_INPUT = ".searchKey"           # 输入框
SELECTOR_SEARCH_BTN = ".search-rightBtn" # 搜索按钮
SELECTOR_PAGE_BTN = ".pageButton"         # 翻页按钮的基本类名
SELECTOR_CLEAR_BTN = "#clear-Btn"       # 清空条件按钮 (ID选择器)
# ==================================================

def run_automation():
    with sync_playwright() as p:
        print("正在启动浏览器并进行防检测伪装...")
        # 启动 Chromium 浏览器，添加防自动化检测参数
        browser = p.chromium.launch(
            headless=False, 
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled", # 禁用自动化控制特征
                "--no-sandbox"
            ]
        )
        
        # 创建上下文，并注入防爬混淆脚本（防止 window.navigator.webdriver 被检测）
        context = browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # 注入基础绕过脚本
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = context.new_page()
        
        print(f"正在打开网站: {TARGET_URL}")
        page.goto(TARGET_URL)
        
        # 【关键步骤】等待用户手动登录
        print("\n" + "="*50)
        print("【提示】请在弹出的浏览器中完成登录操作。")
        print("登录成功并进入搜索页面后，请回到这里（命令行）按下【回车键(Enter)】开始自动化任务...")
        print("="*50)
        input() 
        
        # 开始遍历公司列表
        for company in COMPANY_LIST:
            print(f"\n[开始处理] 公司名称: {company}")
            
            # ✨【核心修改点】将自定义根路径与公司名、子文件夹拼接在一起
            target_dir = os.path.join(BASE_OUTPUT_DIR, company, "7、法律文书网")
            
            # 自动创建多级文件夹（如果不存在）
            os.makedirs(target_dir, exist_ok=True)
            print(f" -> 保存路径已确认为: {target_dir}")
            
            # 在键入新公司前，先点击清空条件按钮
            try:
                if page.locator(SELECTOR_CLEAR_BTN).is_visible():
                    print(" -> 正在清空历史搜索条件...")
                    page.locator(SELECTOR_CLEAR_BTN).click()
                    page.wait_for_timeout(1000)
            except Exception as e:
                print(f" -> 提示：清空按钮未找到或无法点击（可能当前无历史条件），继续执行。")
            
            # 定位输入框并输入公司名
            search_input = page.locator(SELECTOR_INPUT)
            search_input.click()
            search_input.fill("") # 先清空文本框
            search_input.fill(company)
            
            # 点击搜索按钮
            page.locator(SELECTOR_SEARCH_BTN).click()
            
            # 等待搜索结果加载（文书网较慢，建议延长至 3-5 秒）
            page.wait_for_timeout(4000)
            
            current_page = 1
            
            # 开始翻页截图循环
            while True:
                print(f" -> 正在截取第 {current_page} 页...")
                
                # 生成时间戳文件名
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_name = f"{timestamp}_page_{current_page}.png"
                
                # 将图片直接保存到刚才定义好的自定义 target_dir 目录中
                file_path = os.path.join(target_dir, file_name)
                
                # 长截图
                try:
                    page.screenshot(path=file_path, full_page=True)
                except Exception as e:
                    print(f" -> ❌ 截图失败: {e}")
                
                # 计算下一页的 value 值
                next_page_value = current_page + 1
                next_btn_selector = f"{SELECTOR_PAGE_BTN}[value='{next_page_value}']"
                
                # 加上 .first 避免与“下一页”按钮冲突
                next_btn = page.locator(next_btn_selector).first
                
                # 检查是否存在并可见
                if next_btn.is_visible():
                    print(f" -> 发现第 {next_page_value} 页按钮，正在点击跳转...")
                    next_btn.click()
                    
                    # 等待新一页的数据加载完成（建议调大防卡顿）
                    page.wait_for_timeout(3000)
                    
                    # 页码计数器自增，继续下一次循环
                    current_page = next_page_value
                else:
                    print(f" -> 未检测到 value='{next_page_value}' 的按钮。该公司的搜索截图任务结束。")
                    break
                    
        print("\n" + "="*50)
        print("🎉 所有公司的搜索及截图任务已全部完成！")
        print(f"文件已全部安全保存在: {BASE_OUTPUT_DIR}")
        print("="*50)
        
        time.sleep(3)
        browser.close()

if __name__ == "__main__":
    run_automation()