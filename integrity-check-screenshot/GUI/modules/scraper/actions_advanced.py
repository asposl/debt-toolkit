"""多步高级检索动作：展开高级面板、填表、等待新标签页等。"""
import time

from DrissionPage.common import Keys


'''全国建筑市场监管公共服务平台 (Element-UI 框架)'''
def action_jianzushichang(page, company):
    input_xpath = "xpath://span[contains(text(), '诚信记录主体')]/ancestor::div[contains(@class, 'el-col')]//input"
    search_input = page.ele(input_xpath)
    search_input.clear()
    search_input.input(company) 
    search_input.run_js(f'this.value = "{company}";')
    search_input.run_js("this.dispatchEvent(new Event('input', { bubbles: true }));")
    search_input.run_js("this.dispatchEvent(new Event('change', { bubbles: true }));")
    time.sleep(2)
    search_input.input(Keys.ENTER)


'''上交所-纪律处分/监管措施'''
def action_shangjiaosuo(page, company):
    tab_xpath = "xpath://span[contains(@class, 'credibility') and text()='监管']"
    target_tab = page.ele(tab_xpath)
    target_tab.click(by_js=True)  
'''生态环境部-高级检索'''
def action_shengtaihuanjingbu_gaoji(page, company):
    tab_xpath = "xpath://span[contains(@class, 'p_gaoji') and text()='高级检索']"
    target_tab = page.ele(tab_xpath)
    target_tab.click(by_js=True)
    time.sleep(1) 
    search_input = page.ele('#total') 
    search_input.clear()
    search_input.input(company)
    search_input.run_js(f'this.value = "{company}";')
    time.sleep(1)
    adv_search_btn = page.ele('#advSearch')
    adv_search_btn.click(by_js=True)


'''证监会-高级检索 '''
def action_zhengjianhui_gaoji(page, company):
    input_box = page.ele('#searchWord')
    input_box.input(company, clear=True)
    
    old_tabs = page.browser.tab_ids
    input_box.input('\n') # 模拟回车提交，触发新窗口
    
    # 轮询等待新标签页产生
    new_tab_id = None
    for _ in range(25): 
        time.sleep(0.2)
        current_tabs = page.browser.tab_ids
        diff = [t for t in current_tabs if t not in old_tabs]
        if diff:
            new_tab_id = diff[-1]
            break

    if new_tab_id:
        new_page = page.browser.get_tab(new_tab_id)
        
        # 【核心防御】：等待高级搜索按钮彻底渲染出来再点击
        search_btn_1 = new_page.ele('#highSearch', timeout=5)
        if search_btn_1:
            search_btn_1.click(by_js=True)
            
            # 等待第二个按钮出来
            search_btn_2 = new_page.ele('#advanceSearch', timeout=5)
            if search_btn_2:
                search_btn_2.click(by_js=True)


'''工信部-高级检索'''
def action_gongxinbu_gaoji(page, company):
    adv_xpath = "xpath://span[@class='ui-search-btn-adv' and text()='高级检索']"
    adv_span = page.ele(adv_xpath)
    adv_span.click(by_js=True)
    time.sleep(1)
    input_pq_xpath = "xpath://input[@id='pq']"
    search_input = page.ele(input_pq_xpath)
    search_input.clear()
    search_input.input(company)
    search_input.run_js(f'this.value = "{company}";')
    time.sleep(1)
    search_btn_xpath = "xpath://input[@id='ipt_btn']"
    search_btn = page.ele(search_btn_xpath)
    search_btn.click(by_js=True)


'''中国人民银行-高级检索'''
def action_renminyinhang_gaoji(page, company):
    time.sleep(1)
    input_qAll = "xpath://input[@name='q']"
    search_input = page.ele(input_qAll)
    search_input.clear()
    search_input.input(company)
    search_input.run_js(f'this.value = "{company}";')
    time.sleep(1)
    
    # 1. 记录点击前的所有标签页 ID
    old_tabs = page.browser.tab_ids
    
    search_btn = page.ele('#button')
    search_btn.click(by_js=True)
    
    # 2. 手写轮询等待新标签页产生（最多等 5 秒，完美替代 wait.new_tab）
    new_tab_id = None
    for _ in range(25): 
        time.sleep(0.1)
        current_tabs = page.browser.tab_ids
        diff = [t for t in current_tabs if t not in old_tabs]
        if diff:
            new_tab_id = diff[-1]
            break
            
    # 3. 如果成功抓到了新标签页
    if new_tab_id:
        new_page = page.browser.get_tab(new_tab_id)
        # 【核心防御】：给 .ele() 加上 timeout=5，死死盯住这个输入框直到它渲染出来！
        new_page_search_input = new_page.ele('#q', timeout=5)
        if new_page_search_input:
            new_page_search_input.clear()
            new_page_search_input.input(company)
            new_page_search_input.run_js(f'this.value = "{company}";')


'''住建部-高级检索'''
def action_zhujianbu_gaoji(page, company):
    search_btn_1 = page.ele('#senior')
    search_btn_1.click(by_js=True)
    time.sleep(1)
    search_input = page.ele('#gq')
    search_input.clear()
    search_input.input(company)
    search_input.run_js(f'this.value = "{company}";')
    time.sleep(1)
    search_btn_xpath = "xpath://button[contains(text(), '开始检索')]"
    search_btn_2 = page.ele(search_btn_xpath)
    search_btn_2.click(by_js=True)


'''农业农村部-高级检索'''
def action_nongyenongcun_gaoji(page, company):
    search_btn_1 = page.ele('#toolbar_adv')
    search_btn_1.click(by_js=True)
    time.sleep(1)
    input_xpath_1 = "xpath://input[@placeholder='请输入包含任意关键词']"
    search_input_1 = page.ele(input_xpath_1)
    search_input_1.clear()
    search_input_1.input(company)
    time.sleep(1)
    search_btn_2_xpath = "xpath://div[contains(@class, 'search-btn') and contains(text(), '开始搜索')]"
    search_btn_2 = page.ele(search_btn_2_xpath)
    search_btn_2.click(by_js=True)
    time.sleep(1)
    input_xpath_2 = 'xpath://input[@placeholder="请输入搜索词"]'
    search_input_2 = page.ele(input_xpath_2)
    search_input_2.clear()
    search_input_2.input(company)


'''药监局-高级检索'''
def action_yaojianju_gaoji(page, company):
    search_btn_1_xpath = "xpath://a[contains(text(), '高级搜索')]"
    search_btn_1 = page.ele(search_btn_1_xpath)
    search_btn_1.click(by_js=True)
    time.sleep(1)
    search_input_1 = page.ele('#q2')
    search_input_1.clear()
    search_input_1.input(company)
    time.sleep(1)
    search_btn_2_xpath = "xpath://input[@value='开始搜索']"
    search_btn_2 = page.ele(search_btn_2_xpath)
    search_btn_2.click(by_js=True)
