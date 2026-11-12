"""简单搜索交互动作：输入关键词 + 点击，一步完成。"""
import time

from .page_helpers import _subject_id, _subject_name


'''深交所-监管措施 (包含纪律处分逻辑也一样)'''
def action_shenjiaosuo_jgcs(page, company):
    time.sleep(1) 
    inp = page.ele('#ZQ_JGCS_tab1_txtGjz')
    inp.input(company, clear=True)
    time.sleep(0.5) 
    try:
        page.ele('css:button.btn-query-primary').click(by_js=True)
    except Exception:
        inp.input('\n')
'''深交所-监管措施 (包含纪律处分逻辑也一样)'''
def action_shenjiaosuo_jlcf(page, company):

    time.sleep(1) 
    inp = page.ele('#ZQ_JLCF_tab1_txtGjz')
    inp.input(company, clear=True)
    time.sleep(0.5) 
    try:
        page.ele('css:button.btn-query-primary').click(by_js=True)
    except Exception:
        inp.input('\n')


'''自然资源部-一般/高级检索（已改为结果页直连，此函数仅作备用）'''
def action_ziranziyuanbu(page, company):
    # 注意：官网头部搜索框默认 display:none（鼠标悬停放大镜才显示），
    # 直接 input() 会把 Ctrl+A 等按键打到页面 body 上，导致整页被选中、搜索失效。
    # 必须先用 JS 把容器显示出来再交互。
    page.run_js("var s=document.querySelector('.search_input'); if(s){s.style.display='block';}")
    time.sleep(0.3)
    search_input = page.ele('#searchText')
    search_input.clear()
    search_input.input(company)
    time.sleep(0.5)
    search_input.run_js(f'this.value = "{company}";')
    search_button = page.ele('xpath://a[contains(@onclick, "onSearch")]')
    search_button.click(by_js=True)


'''盐行业信用管理'''
def action_yanhangyexinyong(page, company):
    page.ele('#indexKeyWord').input(company, clear=True)
def action_caizhengbu(page, company):
    # 填写输入框
    page.ele('@id=andsen').input(company, clear=True)
    
    # 优化后的点击逻辑：
    # 使用 css 模糊匹配包含 checkInput 的 a 标签，或者直接定位内部的 img 元素
    search_btn = page.ele('css:a[onclick*="checkInput"]')
    
    # 执行点击
    search_btn.click(by_js=True)


def action_haiguanzongshu(page, company):
    page.ele('#keyWords').input(company, clear=True)
    page.ele('xpath://div[contains(@class, "view") and contains(@onclick, "query")]').click(by_js=True)


def action_shangwuxinyong(page, company):
    page.ele('@name=e_input-31').input(company, clear=True)


'''应急管理：阶段一（点火）'''
def action_yingjiguanli(page, company):
    page.ele('#iptSword').input(company, clear=True)
    page.ele('#query_btn').click(by_js=True)


def action_jiaotongbu(page, company):
    """交通运输部搜索交互"""
    page.ele('#qt').input(company, clear=True)
    page.ele('#button').click(by_js=True)


'''应急管理：阶段三（截图前收尾）'''
def post_action_yingjiguanli(page, company):
    page.ele('#sw').input(company, clear=True)


"""中国盐业协会：仅在搜索框输入文本，不执行点击"""
def post_action_zhongguoyanye(page, company):
    page.ele('@name=q').input(company, clear=True)


'''证监会-一般检索'''
def action_zhengjianhui_normal(page, company):
    input_box = page.ele('#searchWord')
    input_box.input(company, clear=True)
    input_box.input('\n') # 模拟回车提交


def action_zhengjianhui_govern(page, company):
    page.ele('#content').input(company, clear=True)
    page.ele('.search-icon').click(by_js=True)


def action_chaozai(page, company):
    page.ele('#select_publicityType').select('行政处罚')


def action_baidu_news_independent(page, keyword):
    """复用独立脚本的百度资讯/AI搜索框模式：输入 名称 + 证件号。"""
    search_box = page.ele('#chat-textarea', timeout=8)
    search_box.clear()
    search_box.input(keyword)
    page.ele('#ci-submit-button', timeout=5).click(by_js=True)
    time.sleep(4)


def action_tongji_info(page, company):
    """中国统计信息网独立脚本模式。"""
    search_input = page.ele('#keyboard2', timeout=8)
    search_input.clear()
    search_input.input(company)
    time.sleep(3)


def action_guizhou_tax(page, subject):
    """贵州税务局独立脚本模式：名称必填，证件号可空。"""
    name = _subject_name(subject)
    id_card = _subject_id(subject)

    page.ele('#nsrmc', timeout=8).input(name, clear=True)
    if id_card:
        page.ele('#nsrsbh', timeout=3).input(id_card, clear=True)
    page.ele('#search_cx', timeout=5).click(by_js=True)
    time.sleep(3)
