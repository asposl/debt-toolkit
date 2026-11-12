from urllib.parse import quote
from datetime import datetime
import os
import re
import threading
import time
import pyautogui
from DrissionPage.common import Keys
# ==========================================
# 纯粹的页面内交互动作 (DrissionPage 版)
# ==========================================
import time


def _subject_name(subject):
    if isinstance(subject, dict):
        return str(subject.get("name") or subject.get("raw") or "").strip()
    return str(subject or "").strip()


def _subject_id(subject):
    if isinstance(subject, dict):
        return str(subject.get("id_card") or "").strip()
    return ""


def _subject_keyword(subject):
    name = _subject_name(subject)
    id_card = _subject_id(subject)
    return f"{name} {id_card}".strip()


def _safe_filename(value):
    value = str(value or "").strip()
    value = re.sub(r'[<>:"/\\|?*\r\n\t]+', "_", value)
    value = value.strip(" .")
    return value or "未命名"


def _screenshot(company_folder, filename):
    pyautogui.screenshot(os.path.join(company_folder, f"{_safe_filename(filename)}.png"))


def _wait_ele(tab, selector, seconds=30, interval=0.5):
    end_time = time.time() + seconds
    while time.time() < end_time:
        try:
            ele = tab.ele(selector, timeout=interval)
            if ele:
                return ele
        except Exception:
            pass
        time.sleep(interval)
    return None


def _xpath_literal(value):
    value = str(value)
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    parts = value.split("'")
    return "concat(" + ', "\'", '.join(f'"{part}"' for part in parts) + ")"


def _first_ele(page, selectors, timeout=0.5):
    for selector in selectors:
        try:
            ele = page.ele(selector, timeout=timeout)
            if ele:
                return ele
        except Exception:
            pass
    return None


def _save_page_screenshot(tab, file_path):
    folder = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    os.makedirs(folder, exist_ok=True)

    try:
        tab.get_screenshot(path=folder, name=filename, full_page=True)
        return
    except Exception:
        pass

    try:
        tab.get_screenshot(file_path, full_page=True)
        return
    except Exception:
        pass

    tab.run_cdp('Page.bringToFront')
    time.sleep(0.5)
    pyautogui.screenshot(file_path)


def _get_base64_img_bytes(img_element):
    if not img_element:
        return None
    try:
        src = img_element.attr("src")
        if src and "base64," in src:
            import base64

            return base64.b64decode(src.split("base64,", 1)[1])
    except Exception:
        pass
    return None


def _find_slider_distance_cv2(slider_bytes, bg_bytes):
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("证监会滑块验证码模式需要先安装 opencv-python 和 numpy") from exc

    slider = cv2.imdecode(np.frombuffer(slider_bytes, np.uint8), cv2.IMREAD_COLOR)
    bg = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)

    slider_edge = cv2.Canny(cv2.cvtColor(slider, cv2.COLOR_BGR2GRAY), 100, 200)
    bg_edge = cv2.Canny(cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY), 100, 200)
    _, _, _, max_loc = cv2.minMaxLoc(
        cv2.matchTemplate(bg_edge, slider_edge, cv2.TM_CCOEFF_NORMED)
    )
    return max_loc[0], bg.shape[1]


def _request_gui_confirm(log_queue, title, message):
    payload = {
        "title": title,
        "message": message,
        "event": threading.Event(),
        "result": False,
    }
    log_queue.put(("CONFIRM", payload))
    payload["event"].wait()
    return payload["result"]

'''深交所-监管措施 (包含纪律处分逻辑也一样)'''
def action_shenjiaosuo_jgcs(page, company):
    time.sleep(1) 
    inp = page.ele('#ZQ_JGCS_tab1_txtGjz')
    inp.input(company, clear=True)
    time.sleep(0.5) 
    try:
        page.ele('css:button.btn-query-primary').click(by_js=True)
    except:
        inp.input('\n')
'''深交所-监管措施 (包含纪律处分逻辑也一样)'''
def action_shenjiaosuo_jlcf(page, company):

    time.sleep(1) 
    inp = page.ele('#ZQ_JLCF_tab1_txtGjz')
    inp.input(company, clear=True)
    time.sleep(0.5) 
    try:
        page.ele('css:button.btn-query-primary').click(by_js=True)
    except:
        inp.input('\n')

'''自然资源部-一般/高级检索'''
def action_ziranziyuanbu(page, company):
    search_input = page.ele('#searchText')
    search_input.clear()
    search_input.input(company) 
    time.sleep(0.5)
    search_input.run_js(f'this.value = "{company}";')
    search_button = page.ele('xpath://a[contains(@onclick, "onSearch")]')
    search_button.click(by_js=True)

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
'''证监会-一般检索'''
def action_zhengjianhui_normal(page, company):
    input_box = page.ele('#searchWord')
    input_box.input(company, clear=True)
    input_box.input('\n') # 模拟回车提交
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
def action_zhengjianhui_govern(page, company):
    page.ele('#content').input(company, clear=True)
    page.ele('.search-icon').click(by_js=True)

def action_chaozai(page, company):
    page.ele('#select_publicityType').select('行政处罚')


def action_court_captcha(page, subject):
    """最高院执行公开网字符验证码查询，来自验证码文件夹脚本。"""
    try:
        import ddddocr
    except ImportError as exc:
        raise RuntimeError("最高院验证码模式需要先安装 ddddocr") from exc

    name = _subject_name(subject)
    id_card = _subject_id(subject)
    ocr = ddddocr.DdddOcr(show_ad=False)

    for retry in range(5):
        try:
            page.wait.ele_displayed('#pName', timeout=5)
        except Exception:
            pass

        name_ele = page.ele('#pName', timeout=8)
        card_ele = page.ele('#pCardNum', timeout=8)
        captcha_ele = page.ele('#captchaImg', timeout=8)
        code_ele = page.ele('#yzm', timeout=8)

        name_ele.input(name, clear=True)
        card_ele.input(id_card, clear=True)

        captcha_ele.click()
        time.sleep(0.6)

        img_bytes = captcha_ele.get_screenshot(as_bytes=True)
        code_text = ocr.classification(img_bytes)
        code_ele.input(code_text, clear=True)
        page.ele('text=查询', timeout=5).click(by_js=True)

        is_error = False
        for _ in range(10):
            error_element = page.ele('.important', timeout=0.2)
            if error_element and ("验证码错误" in error_element.text or "验证码已过期" in error_element.text):
                is_error = True
                break

            if (
                page.ele('css:.ResultList', timeout=0.1)
                or page.ele('text=没有符合条件的数据', timeout=0.1)
                or page.ele('text=查询结果', timeout=0.1)
            ):
                break

        if not is_error:
            time.sleep(0.5)
            return

    raise RuntimeError("最高院字符验证码连续识别失败")


def action_csrc_shixin_slider(page, subject):
    """中国证监会证券期货市场失信记录查询平台滑块验证码。"""
    name = _subject_name(subject)
    id_card = _subject_id(subject)

    page.ele('css:input[placeholder*="必须填写姓名"]', timeout=10).input(name, clear=True)
    page.ele('css:input[placeholder*="需要填写完整"]', timeout=10).input(id_card, clear=True)
    page.ele("css:.searchBtn", timeout=8).click(by_js=True)
    time.sleep(2)

    for retry_count in range(5):
        try:
            bg = (
                page.ele("css:.verify-img-panel img", timeout=2)
                or page.ele("css:.popup-bg", timeout=2)
            )
            slider = (
                page.ele("css:.verify-sub-block img", timeout=2)
                or page.ele("css:.popup-slide", timeout=2)
            )
            drag = (
                page.ele("css:.verify-move-block", timeout=2)
                or page.ele("css:.slider-btn", timeout=2)
            )

            if not (bg and slider and drag) or bg.rect.size[0] == 0:
                break

            bg_bytes = _get_base64_img_bytes(bg)
            slider_bytes = _get_base64_img_bytes(slider)
            if not (bg_bytes and slider_bytes):
                time.sleep(1)
                continue

            x, original_width = _find_slider_distance_cv2(slider_bytes, bg_bytes)
            bg_width = bg.rect.size[0]
            if bg_width == 0:
                break

            distance = x * (bg_width / original_width)
            page.actions.move_to(drag).hold()
            page.actions.move(offset_x=distance, offset_y=0, duration=1.2)
            page.actions.release()
            time.sleep(3)
        except Exception as exc:
            if "没有位置及大小" in str(exc) or "ElementLostError" in str(exc):
                break
            time.sleep(1)
    else:
        raise RuntimeError("证监会滑块验证码连续识别失败")

    time.sleep(2)


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


def action_jiangsu_tax(page, subject):
    """江苏税务局独立脚本模式，保留验证码 OCR 重试。"""
    try:
        import ddddocr
    except ImportError as exc:
        raise RuntimeError("江苏税务局模式需要先安装 ddddocr") from exc

    name = _subject_name(subject)
    id_card = _subject_id(subject)
    ocr = ddddocr.DdddOcr(show_ad=False)

    input_name = page.ele('#name', timeout=10)
    input_nsrsbh = page.ele('#nsrsbh', timeout=10)
    input_rand = page.ele('#rand', timeout=10)
    captcha_ele = page.ele('#randImage', timeout=10)
    search_btn = page.ele('@onclick=refreshIf()', timeout=10)

    for retry in range(5):
        input_name.input(name, clear=True)
        input_nsrsbh.input(id_card, clear=True)

        if retry > 0:
            captcha_ele.click()
            time.sleep(0.5)

        img_bytes = captcha_ele.get_screenshot(as_bytes=True)
        code_text = ocr.classification(img_bytes)
        input_rand.input(code_text, clear=True)
        search_btn.click(by_js=True)

        try:
            page.wait.eles_loaded(['text=验证码错误，请重新输入', '.table_main', '#searchResult'], timeout=4)
        except Exception:
            time.sleep(1)

        error_ele = page.ele('text=验证码错误，请重新输入', timeout=0.2)
        if not error_ele:
            time.sleep(0.5)
            return

    raise RuntimeError("江苏税务局验证码连续识别失败")


def workflow_tianyancha(page, subject, company_folder, filename, log_queue):
    """天眼查独立脚本模式，保留人工登录窗口，但不再阻塞命令行 input。"""
    company = _subject_name(subject)
    tab = page.new_tab("https://www.tianyancha.com/company/22822")
    search_tab = tab
    tab.run_cdp('Page.bringToFront')

    log_queue.put("     请在浏览器中完成天眼查登录；出现搜索框后会自动继续（最多等待180秒）。\n")
    search_box = _wait_ele(
        tab,
        'xpath://input[contains(@placeholder, "请输入公司名称") or contains(@placeholder, "老板姓名")]',
        seconds=180,
        interval=1,
    )
    if not search_box:
        raise RuntimeError("未等到天眼查搜索框")

    search_box.click()
    search_box.input(company, clear=True)
    search_button = tab.ele('xpath://*[contains(text(), "天眼一下")]', timeout=8)
    search_button.click(by_js=True)
    time.sleep(3)

    old_tabs = page.tab_ids
    company_literal = _xpath_literal(company)
    company_link = tab.ele(f'xpath://a[contains(text(), {company_literal})]', timeout=8)
    if company_link:
        company_link.click(by_js=True)
        new_tab_id = None
        for _ in range(30):
            current_tabs = page.tab_ids
            new_tabs = [t for t in current_tabs if t not in old_tabs]
            if new_tabs:
                new_tab_id = new_tabs[-1]
                break
            time.sleep(0.2)
        if new_tab_id:
            tab = page.get_tab(new_tab_id)

    tab.run_cdp('Page.bringToFront')
    time.sleep(4)
    _screenshot(company_folder, filename)
    try:
        tab.close()
    except Exception:
        pass
    if getattr(search_tab, "tab_id", None) != getattr(tab, "tab_id", None):
        try:
            search_tab.close()
        except Exception:
            pass


def workflow_wenshu(page, subject, company_folder, filename, log_queue):
    """裁判文书网独立脚本模式，保留人工登录，并可在结果页直接接管截图。"""
    company = _subject_name(subject)
    tab = page.new_tab("https://wenshu.court.gov.cn/")
    tab.run_cdp('Page.bringToFront')

    search_selectors = [
        '.searchKey',
        'css:input.searchKey',
        'css:textarea.searchKey',
        'xpath://input[contains(@class, "searchKey")]',
        'xpath://textarea[contains(@class, "searchKey")]',
        'xpath://input[contains(@placeholder, "请输入")]',
    ]
    result_selectors = [
        '.pageButton',
        'css:.caseName',
        'css:.LM_list',
        'css:.result-list',
        'text=篇文书',
        'text=裁判文书',
        'text=没有符合条件',
    ]

    log_queue.put(
        "     文书网已打开。请在浏览器中完成登录，并停留在检索页或已查询结果页；"
        "然后回到 GUI 点击确认开始接管。\n"
    )
    confirmed = _request_gui_confirm(
        log_queue,
        "裁判文书网确认",
        "请在浏览器中完成裁判文书网登录，并停留在检索页或已经查询出的结果页。\n\n"
        "准备好后点击“确定”，程序将开始自动搜索/截图；点击“取消”将跳过文书网。",
    )
    if not confirmed:
        raise RuntimeError("用户取消文书网接管")

    state = None
    search_input = None
    end_time = time.time() + 20
    while time.time() < end_time:
        search_input = _first_ele(tab, search_selectors, timeout=0.3)
        if search_input:
            state = "search"
            break
        if _first_ele(tab, result_selectors, timeout=0.2):
            state = "result"
            break
        time.sleep(1)

    if state == "search":
        try:
            clear_btn = tab.ele('#clear-Btn', timeout=1)
            if clear_btn:
                clear_btn.click(by_js=True)
                time.sleep(1)
        except Exception:
            pass

        search_input.click()
        search_input.input(company, clear=True)
        search_btn = _first_ele(
            tab,
            ['.search-rightBtn', 'css:.search-rightBtn', 'xpath://*[contains(@class, "search-rightBtn")]'],
            timeout=8,
        )
        if search_btn:
            search_btn.click(by_js=True)
        else:
            search_input.input('\n')
        time.sleep(4)
    elif state == "result":
        log_queue.put("     已检测到文书网结果页，跳过自动输入，直接开始截图。\n")
    else:
        raise RuntimeError("未检测到文书网检索页或结果页")

    target_dir = os.path.join(company_folder, _safe_filename(filename))
    os.makedirs(target_dir, exist_ok=True)

    current_page = 1
    while current_page <= 50:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(target_dir, f"{timestamp}_page_{current_page}.png")
        _save_page_screenshot(tab, file_path)

        next_page_value = current_page + 1
        next_btn = _first_ele(
            tab,
            [
                f"css:.pageButton[value='{next_page_value}']",
                f"xpath://*[@value='{next_page_value}' and contains(@class, 'pageButton')]",
                f"xpath://*[normalize-space(text())='{next_page_value}' and contains(@class, 'pageButton')]",
            ],
            timeout=1,
        )
        if not next_btn:
            break

        next_btn.click(by_js=True)
        time.sleep(3)
        current_page = next_page_value

    try:
        tab.close()
    except Exception:
        pass



# 对于一步到位的网站，action 填 None 即可

WEB_CONFIG = {
    # === 国家部委及总局 ===
        '3、中国证监会证券期货市场失信记录查询平台（验证码）': {
            'url': 'https://neris.csrc.gov.cn/shixinchaxun/neris.csrc.gov.cn',
            'action': action_csrc_shixin_slider,
            'action_arg': 'item',
            'post_action': None,
            'save_as': '3、中国证监会证券期货市场失信记录查询平台',
            'foreground': True,
        },
        '4、中国执行信息公开网—综合查询（验证码）': {
            'url': 'https://zxgk.court.gov.cn/zhzxgk/',
            'action': action_court_captcha,
            'action_arg': 'item',
            'post_action': None,
            'save_as': '4、中国执行信息公开网—综合查询',
            'foreground': True,
        },
        '5、全国法院失信被执行人名单信息公布与查询（验证码）': {
            'url': 'https://zxgk.court.gov.cn/shixin/',
            'action': action_court_captcha,
            'action_arg': 'item',
            'post_action': None,
            'save_as': '5、全国法院失信被执行人名单信息公布与查询',
            'foreground': True,
        },
        '7、法律文书网（独立模式）': {
            'url': 'https://wenshu.court.gov.cn/',
            'workflow': workflow_wenshu,
            'save_as': '7、法律文书网',
            'query_mode': 'name',
        },
        '8、国家税务总局江苏省税务局（独立模式）': {
            'url': 'https://jiangsu.chinatax.gov.cn/module/jslib/bulletin3/lpindex.html',
            'action': action_jiangsu_tax,
            'action_arg': 'item',
            'post_action': None,
            'save_as': '8、国家税务总局江苏省税务局',
            'foreground': True,
        },
        '8、国家税务总局贵州省税务局（独立模式）': {
            'url': 'https://guizhou.chinatax.gov.cn/zdsswfsxajxxgbl/index.html',
            'action': action_guizhou_tax,
            'action_arg': 'item',
            'post_action': None,
            'save_as': '8、国家税务总局贵州省税务局',
            'foreground': True,
        },
        '21、中国统计信息网（独立模式）': {
            'url': 'http://www.tjcn.org/search/',
            'action': action_tongji_info,
            'post_action': None,
            'save_as': '21、中国统计信息网',
            'foreground': True,
        },
        '33、其他网站和媒体报道（百度独立模式）': {
            'url': 'https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&rsv_dl=ns_pc&word=x',
            'action': action_baidu_news_independent,
            'post_action': None,
            'query_mode': 'name_id',
            'save_as': '33、其他网站和媒体报道',
            'foreground': True,
        },
        '天眼查（独立模式）': {
            'url': 'https://www.tianyancha.com/company/22822',
            'workflow': workflow_tianyancha,
            'save_as': '天眼查',
            'query_mode': 'name',
        },
        '2、发行人所属地方政府网站': {'url': 'http://www.zghaq.gov.cn/search/index.html?q={company}', 'action': None, 'post_action': None},
        '发改委-一般检索': {'url': 'https://so.ndrc.gov.cn/s?siteCode=bm04000007&ssl=1&token=&qt={company}', 'action': None, 'post_action': None},
        '25、中华人民共和国财政部': {'url': 'http://www.mof.gov.cn/index.htm', 'action': action_caizhengbu, 'post_action': None},
        '33、其他网站和媒体报道': {'url': 'https://www.baidu.com/s?ie=utf-8&bsst=1&rsv_dl=news_t_sk&tn=news&cl=2&medium=0&rtt=1&wd={company}', 'action': None, 'post_action': None},

    # '财政部': {'url': 'http://www.mof.gov.cn/index.htm', 'action': action_caizhengbu, 'post_action': None},
    # '工信部-一般检索': {'url': 'https://www.miit.gov.cn/search/index.html?websiteid=110000000000000&pg=&p=&tpl=&category=&jsflIndexSeleted=&q={company}', 'action': None, 'post_action': None},
    # '工信部-高级检索': {'url': 'https://www.miit.gov.cn/search/index.html?websiteid=110000000000000&pg=&p=&tpl=&category=&jsflIndexSeleted=&q={company}', 'action': action_gongxinbu_gaoji, 'post_action': None},
    # '能源局': {'url': 'https://www.nea.gov.cn/search.htm?kw={company}', 'action': None, 'post_action': None},
    # '国家市场监管总局': {'url': 'https://www.samr.gov.cn/api-gateway/jpaas-jsearch-web-server/search?serviceId=db6d646f22e541d7a303940a8e8623cc&websiteid=&cateid=aef29dab559a4e9db9da54ff2e1eb92b&q={company}&sortType=2', 'action': None, 'post_action': None},
    # '国家统计局': {'url': 'https://www.stats.gov.cn/search/s?qt={company}', 'action': None, 'post_action': None},
    # '药监局-一般检索': {'url': 'https://www.nmpa.gov.cn/so/s?tab=all&qt={company}', 'action': None, 'post_action': None},
    # '药监局-高级检索': {'url': 'https://www.nmpa.gov.cn/so/s?tab=all&qt={company}', 'action': action_yaojianju_gaoji, 'post_action': None},
    # '海关总署': {'url': 'http://search.customs.gov.cn/eportal/ui?pageId=7690f322e6a0410881e172afbfaaa25c', 'action': action_haiguanzongshu, 'post_action': None},
    # '农业农村部-一般检索': {'url': 'https://www.moa.gov.cn/so/s?qt={company}', 'action': None, 'post_action': None},
    # '农业农村部-高级检索': {'url': 'https://www.moa.gov.cn/so/s?qt={company}', 'action': action_nongyenongcun_gaoji, 'post_action': None},
    # '商务部': {'url': 'https://search.mofcom.gov.cn/allSearch/?siteId=0&keyWordType=title&acSuggest={company}', 'action': None, 'post_action': None},
    # '商务信用平台': {'url': 'https://www.315gov.cn/globalSearch.html?keywords={company}&appIds=all', 'action': action_shangwuxinyong, 'post_action': None},
    # '生态环境部-一般检索': {'url': 'https://www.mee.gov.cn/searchnew/?searchword={company}', 'action': None, 'post_action': None},
    # '生态环境部-高级检索': {'url': 'https://www.mee.gov.cn/searchnew/?searchword={company}', 'action': action_shengtaihuanjingbu_gaoji, 'post_action': None},
    # '应急管理': {'url': 'https://www.mem.gov.cn/', 'action': action_yingjiguanli, 'post_action': post_action_yingjiguanli},
    # '住建部-一般检索': {'url': 'https://www.mohurd.gov.cn/api-gateway/jpaas-jsearch-web-server/search?serviceId=e2f3058e2a3b4f8abc93eb76e739e3e7&websiteid=&cateid=6ca0f12c0f0642ab8b1dc17028e12ea1&q={company}', 'action': None, 'post_action': None},
    # '住建部-高级检索': {'url': 'https://www.mohurd.gov.cn/api-gateway/jpaas-jsearch-web-server/search?serviceId=e2f3058e2a3b4f8abc93eb76e739e3e7&websiteid=&cateid=6ca0f12c0f0642ab8b1dc17028e12ea1&q={company}', 'action': action_zhujianbu_gaoji, 'post_action': None},
    # '国家外汇管理局': {'url':'https://www.safe.gov.cn/safe/search/index.html?q={company}&siteid=safe&order=releasetime', 'action': None, 'post_action': None},
    # '中国人民银行-一般检索':{'url':'https://wzdig.pbc.gov.cn/search/pcRender?sr=score+desc&pageId=c177a85bd02b4114bebebd210809f691&ext=&pNo=1&q={company}', 'action': None, 'post_action': None},
    # '中国人民银行-高级检索':{'url':'https://wzdig.pbc.gov.cn/search/pcRender?pageId=ba91211b4019456db06f6678d71f5047', 'action': action_renminyinhang_gaoji, 'post_action': None},
    # '中国盐业协会':{'url':'https://www.cnsalt.cn/index/index/search.html?q={company}', 'action': None, 'post_action': post_action_zhongguoyanye},
    # '中国电力企业联合会':{'url':'https://cec.org.cn/search/index.html?search={company}', 'action': None, 'post_action': None},
    # '交通运输部': {'url': 'https://www.mot.gov.cn/', 'action': action_jiaotongbu, 'post_action': None},
    # '人力资源和社会保障部':{'url':'https://www.mohrss.gov.cn/hsearch/?searchword={company}', 'action': None, 'post_action': None },
    # '安全生产领域失信生产经营单位': {'url': 'https://www.mem.gov.cn/', 'action': action_yingjiguanli, 'post_action': post_action_yingjiguanli},
    # '自然资源部-一般检索':{'url':'https://www.mnr.gov.cn/','action': action_ziranziyuanbu, 'post_action': None},
    # '自然资源部-高级检索':{'url':'https://www.mnr.gov.cn/','action': action_ziranziyuanbu, 'post_action': None},
    # '全国建筑市场监管公共服务平台': {'url': 'https://jzsc.mohurd.gov.cn/since/index', 'action': action_jianzushichang, 'post_action': None},
    # '盐行业信用管理':{'url':'http://yan.bcpcn.com/website/xyjl.jsp?keyword={company}&searchtype=1&page=1', 'action': action_yanhangyexinyong, 'post_action': None},
    # '中国政府采购网':{'url':'https://search.ccgp.gov.cn/bxsearch?searchtype=2&page_index=1&start_time=&end_time=&timeType=2&searchparam=&searchchannel=0&dbselect=bidx&kw={company}&bidSort=0&pinMu=0&bidType=0&buyerName=&projectId=&displayZone=&zoneId=&agentName=', 'action': None, 'post_action': None},
    # '发改委-高级检索':{'url':'https://so.ndrc.gov.cn/s?qt="{company}"&siteCode=bm04000007&tab=all&keyPlace=0&sort=&days=0&fileType=&timeOption=0&adv=1', 'action': None, 'post_action': None},
    # # === 证券交易及监管核查 ===
    # '证监会-一般检索': {'url': 'http://www.csrc.gov.cn/', 'action': action_zhengjianhui_normal, 'post_action': None},
    # '证监会-高级检索': {'url': 'http://www.csrc.gov.cn/', 'action': action_zhengjianhui_gaoji, 'post_action': None},
    # '证监会-政府公开信息': {'url': 'http://www.csrc.gov.cn/csrc/c100033/zfxxgk_zdgk.shtml', 'action': action_zhengjianhui_govern, 'post_action': None},
    # '发行人行贿核查': {'url': 'https://www.baidu.com/s?wd={company}%20行贿核查&rsv_btype=t&inputT=2224&rsv_t=b47e6furN%2Buws5yK33qvVaMI50O7yxzu2SUStbjtkTStWDxuTokDQSCATjFvvjLKMIr2&rsv_pq=910a7b9f00002f8f&rsv_sug3=15&rsv_sug1=10&rsv_sug7=100&rsv_sug4=2224', 'action': None, 'post_action': None},
    # '深交所-纪律处分':{'url':'http://www.szse.cn/disclosure/bond/punish/index.html','action': action_shenjiaosuo_jlcf, 'post_action': None},
    # '深交所-监管措施':{'url':'http://www.szse.cn/disclosure/bond/measure/index.html','action': action_shenjiaosuo_jgcs, 'post_action': None},
    # '上交所-纪律处分':{'url':'https://www.sse.com.cn/home/search/index.shtml?webswd={company}', 'action': action_shangjiaosuo, 'post_action': None},
    # '上交所-监管措施':{'url':'https://www.sse.com.cn/home/search/index.shtml?webswd={company}', 'action': action_shangjiaosuo, 'post_action': None},
    # '全国资源公共交易平台':{'url':'https://www.ggzy.gov.cn/deal/dealList.html?DEAL_TIME=05&FINDTXT={company}', 'action':None ,'post_action':None},
    # # === 地方政府及其他专项 ===
    # '地方政府处罚': {'url': 'http://www.zghaq.gov.cn/search/index.html?q={company}', 'action': None, 'post_action': None},
    # '信用交通': {'url': 'http://219.143.235.38:8080/CreditTraffic/jsp/pc/integrationAll.jsp?flag=1&searchValue={company}', 'action': action_chaozai, 'post_action': None},
    
    # # === 百度舆情检索 ===
    # '百度_违约': {'url': 'https://www.baidu.com/s?wd={company}%20违约&rsv_btype=t&inputT=2224&rsv_t=b47e6furN%2Buws5yK33qvVaMI50O7yxzu2SUStbjtkTStWDxuTokDQSCATjFvvjLKMIr2&rsv_pq=910a7b9f00002f8f&rsv_sug3=15&rsv_sug1=10&rsv_sug7=100&rsv_sug4=2224', 'action': None, 'post_action': None},
    # '百度_负面': {'url': 'https://www.baidu.com/s?wd={company}%20负面&rsv_btype=t&inputT=2224&rsv_t=b47e6furN%2Buws5yK33qvVaMI50O7yxzu2SUStbjtkTStWDxuTokDQSCATjFvvjLKMIr2&rsv_pq=910a7b9f00002f8f&rsv_sug3=15&rsv_sug1=10&rsv_sug7=100&rsv_sug4=2224', 'action': None, 'post_action': None},
}
default = {
    '3.发改委-一般检索': {'url': 'https://so.ndrc.gov.cn/s?siteCode=bm04000007&ssl=1&token=&qt={company}', 'action': None, 'post_action': None},
    '4.发改委-高级检索':{'url':'https://so.ndrc.gov.cn/s?qt="{company}"&siteCode=bm04000007&tab=all&keyPlace=0&sort=&days=0&fileType=&timeOption=0&adv=1', 'action': None, 'post_action': None},
    '7.全国资源公共交易平台':{'url':'https://www.ggzy.gov.cn/deal/dealList.html?DEAL_TIME=05&FINDTXT={company}', 'action':None ,'post_action':None},
    '10.应急管理部': {'url': 'https://www.mem.gov.cn/', 'action': action_yingjiguanli, 'post_action': post_action_yingjiguanli},
    '11.生态环境部-一般检索': {'url': 'https://www.mee.gov.cn/searchnew/?searchword={company}', 'action': None, 'post_action': None},
    '12.生态环境部-高级检索': {'url': 'https://www.mee.gov.cn/searchnew/?searchword={company}', 'action': action_shengtaihuanjingbu_gaoji, 'post_action': None},
    '13.工信部-一般检索': {'url': 'https://www.miit.gov.cn/search/index.html?websiteid=110000000000000&pg=&p=&tpl=&category=&jsflIndexSeleted=&q={company}', 'action': None, 'post_action': None},
    '14.工信部-高级检索': {'url': 'https://www.miit.gov.cn/search/index.html?websiteid=110000000000000&pg=&p=&tpl=&category=&jsflIndexSeleted=&q={company}', 'action': action_gongxinbu_gaoji, 'post_action': None},
    '15.商务部': {'url': 'https://search.mofcom.gov.cn/allSearch/?siteId=0&keyWordType=title&acSuggest={company}', 'action': None, 'post_action': None},
    '16.商务信用平台': {'url': 'https://www.315gov.cn/globalSearch.html?keywords={company}&appIds=all', 'action': action_shangwuxinyong, 'post_action': None},
    '18.国家外汇管理局': {'url':'https://www.safe.gov.cn/safe/search/index.html?q={company}&siteid=safe&order=releasetime', 'action': None, 'post_action': None},
    '19.中国人民银行-一般检索':{'url':'https://wzdig.pbc.gov.cn/search/pcRender?sr=score+desc&pageId=c177a85bd02b4114bebebd210809f691&ext=&pNo=1&q={company}', 'action': None, 'post_action': None},
    '20.中国人民银行-高级检索':{'url':'https://wzdig.pbc.gov.cn/search/pcRender?pageId=ba91211b4019456db06f6678d71f5047', 'action': action_renminyinhang_gaoji, 'post_action': None},
    '22.证监会-一般检索': {'url': 'http://www.csrc.gov.cn/', 'action': action_zhengjianhui_normal, 'post_action': None},
    '23.证监会-高级检索': {'url': 'http://www.csrc.gov.cn/', 'action': action_zhengjianhui_gaoji, 'post_action': None},
    '25.中国盐业协会':{'url':'https://www.cnsalt.cn/index/index/search.html?q={company}', 'action': None, 'post_action': post_action_zhongguoyanye},
    '26.国家统计局': {'url': 'https://www.stats.gov.cn/search/s?qt={company}', 'action': None, 'post_action': None},
    '27.能源局': {'url': 'https://www.nea.gov.cn/search.htm?kw={company}', 'action': None, 'post_action': None},
    '28国家市场监管总局': {'url': 'https://www.samr.gov.cn/api-gateway/jpaas-jsearch-web-server/search?serviceId=db6d646f22e541d7a303940a8e8623cc&websiteid=&cateid=aef29dab559a4e9db9da54ff2e1eb92b&q={company}&sortType=2', 'action': None, 'post_action': None},
    '29.财政部': {'url': 'http://www.mof.gov.cn/index.htm', 'action': action_caizhengbu, 'post_action': None},
    '30.住建部-一般检索': {'url': 'https://www.mohurd.gov.cn/api-gateway/jpaas-jsearch-web-server/search?serviceId=e2f3058e2a3b4f8abc93eb76e739e3e7&websiteid=&cateid=6ca0f12c0f0642ab8b1dc17028e12ea1&q={company}', 'action': None, 'post_action': None},
    '31.住建部-高级检索': {'url': 'https://www.mohurd.gov.cn/api-gateway/jpaas-jsearch-web-server/search?serviceId=e2f3058e2a3b4f8abc93eb76e739e3e7&websiteid=&cateid=6ca0f12c0f0642ab8b1dc17028e12ea1&q={company}', 'action': action_zhujianbu_gaoji, 'post_action': None},
    '32.全国建筑市场监管公共服务平台': {'url': 'https://jzsc.mohurd.gov.cn/since/index', 'action': action_jianzushichang, 'post_action': None},
    '33.中国电力企业联合会':{'url':'https://cec.org.cn/search/index.html?search={company}', 'action': None, 'post_action': None},
    '34.农业农村部-一般检索': {'url': 'https://www.moa.gov.cn/so/s?qt={company}', 'action': None, 'post_action': None},
    '35.农业农村部-高级检索': {'url': 'https://www.moa.gov.cn/so/s?qt={company}', 'action': action_nongyenongcun_gaoji, 'post_action': None},
    '37.上交所-纪律处分':{'url':'https://www.sse.com.cn/home/search/index.shtml?webswd={company}', 'action': action_shangjiaosuo, 'post_action': None},
    '38.上交所-监管措施':{'url':'https://www.sse.com.cn/home/search/index.shtml?webswd={company}', 'action': action_shangjiaosuo, 'post_action': None},
    '39.深交所-纪律处分':{'url':'http://www.szse.cn/disclosure/bond/punish/index.html','action': action_shenjiaosuo_jlcf, 'post_action': None},
    '40.深交所-监管措施':{'url':'http://www.szse.cn/disclosure/bond/measure/index.html','action': action_shenjiaosuo_jgcs, 'post_action': None},
    '41.药监局-一般检索': {'url': 'https://www.nmpa.gov.cn/so/s?tab=all&qt={company}', 'action': None, 'post_action': None},
    '42.药监局-高级检索': {'url': 'https://www.nmpa.gov.cn/so/s?tab=all&qt={company}', 'action': action_yaojianju_gaoji, 'post_action': None},
    '43.盐行业信用管理':{'url':'http://yan.bcpcn.com/website/xyjl.jsp?keyword={company}&searchtype=1&page=1', 'action': action_yanhangyexinyong, 'post_action': None},
    '44.自然资源部-一般检索':{'url':'https://www.mnr.gov.cn/','action': action_ziranziyuanbu, 'post_action': None},
    '45.自然资源部-高级检索':{'url':'https://www.mnr.gov.cn/','action': action_ziranziyuanbu, 'post_action': None},
    '46.百度-负面': {'url': 'https://www.baidu.com/s?wd={company}%20负面&rsv_btype=t&inputT=2224&rsv_t=b47e6furN%2Buws5yK33qvVaMI50O7yxzu2SUStbjtkTStWDxuTokDQSCATjFvvjLKMIr2&rsv_pq=910a7b9f00002f8f&rsv_sug3=15&rsv_sug1=10&rsv_sug7=100&rsv_sug4=2224', 'action': None, 'post_action': None},
    '47.中国政府采购网':{'url':'https://search.ccgp.gov.cn/bxsearch?searchtype=2&page_index=1&start_time=&end_time=&timeType=2&searchparam=&searchchannel=0&dbselect=bidx&kw={company}&bidSort=0&pinMu=0&bidType=0&buyerName=&projectId=&displayZone=&zoneId=&agentName=', 'action': None, 'post_action': None},
    '48.海关总署': {'url': 'http://search.customs.gov.cn/eportal/ui?pageId=7690f322e6a0410881e172afbfaaa25c', 'action': action_haiguanzongshu, 'post_action': None},
    '50.人力资源和社会保障部':{'url':'https://www.mohrss.gov.cn/hsearch/?searchword={company}', 'action': None, 'post_action': None },
    '52.安全生产领域失信生产经营单位': {'url': 'https://www.mem.gov.cn/', 'action': action_yingjiguanli, 'post_action': post_action_yingjiguanli},
    '53.信用交通': {'url': 'http://219.143.235.38:8080/CreditTraffic/jsp/pc/integrationAll.jsp?flag=1&searchValue={company}', 'action': action_chaozai, 'post_action': None}
}
default_2 = {
    # === 国家部委及总局 ===
    # 示例地市A
    # '2、发行人所属地方政府网站': {'url': 'https://panzhou.gov.cn/so/search.shtml?tenantId=157&tenantIds=&configTenantId=&searchWord={company}&dataTypeId=101&sign=78e2f8a8-cfff-4f0f-a197-88b81435697f', 'action': None, 'post_action': None},
    # 示例地市B
    '2、发行人所属地方政府网站': {'url': 'http://www.zghaq.gov.cn/search/index.html?q={company}', 'action': None, 'post_action': None},
    '9、中国政府采购网':{'url':'https://search.ccgp.gov.cn/bxsearch?searchtype=2&page_index=1&start_time=&end_time=&timeType=2&searchparam=&searchchannel=0&dbselect=bidx&kw={company}&bidSort=0&pinMu=0&bidType=0&buyerName=&projectId=&displayZone=&zoneId=&agentName=', 'action': None, 'post_action': None},
    '10、中华人民共和国应急管理部': {'url': 'https://www.mem.gov.cn/', 'action': action_yingjiguanli, 'post_action': post_action_yingjiguanli},       
    '11、中华人民共和国生态环境部': {'url': 'https://www.mee.gov.cn/searchnew/?searchword={company}', 'action': None, 'post_action': None},
    '12、中华人民共和国工业和信息化部': {'url': 'https://www.miit.gov.cn/search/index.html?websiteid=110000000000000&pg=&p=&tpl=&category=&jsflIndexSeleted=&q={company}', 'action': None, 'post_action': None},
    '13、国家外汇管理局': {'url':'https://www.safe.gov.cn/safe/search/index.html?q={company}&siteid=safe&order=releasetime', 'action': None, 'post_action': None},
    '14、国家金融监督管理总局': {'url':'https://www.nfra.gov.cn/cn/view/pages/index/jiansuo.html?keyWords={company}', 'action': None, 'post_action': None},
    '15、中国人民银行':{'url':'https://wzdig.pbc.gov.cn/search/pcRender?sr=score+desc&pageId=c177a85bd02b4114bebebd210809f691&ext=&pNo=1&q={company}', 'action': None, 'post_action': None},
    '16、中国证监会网站': {'url': 'http://www.csrc.gov.cn/', 'action': action_zhengjianhui_normal, 'post_action': None},
    '17、国家市场监督管理总局': {'url': 'https://www.samr.gov.cn/api-gateway/jpaas-jsearch-web-server/search?serviceId=db6d646f22e541d7a303940a8e8623cc&websiteid=&cateid=aef29dab559a4e9db9da54ff2e1eb92b&q={company}&sortType=2', 'action': None, 'post_action': None},
    '18、国家药品监督管理局': {'url': 'https://www.nmpa.gov.cn/so/s?tab=all&qt={company}', 'action': None, 'post_action': None},
    '19、中国盐业协会':{'url':'https://www.cnsalt.cn/index/index/search.html?q={company}', 'action': None, 'post_action': post_action_zhongguoyanye},
    '20、国家统计局': {'url': 'https://www.stats.gov.cn/search/s?qt={company}', 'action': None, 'post_action': None},
    '22、国家能源局': {'url': 'https://www.nea.gov.cn/search.htm?kw={company}', 'action': None, 'post_action': None},
    '23、中华人民共和国商务部': {'url': 'https://search.mofcom.gov.cn/allSearch/?siteId=0&keyWordType=title&acSuggest={company}', 'action': None, 'post_action': None},
    '24、中华人民共和国国家发展和改革委员会': {'url': 'https://so.ndrc.gov.cn/s?siteCode=bm04000007&ssl=1&token=&qt={company}', 'action': None, 'post_action': None},
    '25、中华人民共和国财政部': {'url': 'http://www.mof.gov.cn/index.htm', 'action': action_caizhengbu, 'post_action': None},
    '26、中华人民共和国农业农村部': {'url': 'https://www.moa.gov.cn/so/s?qt={company}', 'action': None, 'post_action': None},
    '27、海关总署': {'url': 'http://search.customs.gov.cn/eportal/ui?pageId=7690f322e6a0410881e172afbfaaa25c', 'action': action_haiguanzongshu, 'post_action': None},
    '28、中华人民共和国住房和城乡建设部': {'url': 'https://www.mohurd.gov.cn/api-gateway/jpaas-jsearch-web-server/search?serviceId=e2f3058e2a3b4f8abc93eb76e739e3e7&websiteid=&cateid=6ca0f12c0f0642ab8b1dc17028e12ea1&q={company}', 'action': None, 'post_action': None},
    '29、全国建筑市场监管公共服务平台': {'url': 'https://jzsc.mohurd.gov.cn/since/index', 'action': action_jianzushichang, 'post_action': None},
    '30、中华人民共和国交通运输部': {'url': 'https://www.mot.gov.cn/', 'action': action_jiaotongbu, 'post_action': None},  
    '31、中华人民共和国自然资源部':{'url':'https://www.mnr.gov.cn/','action': action_ziranziyuanbu, 'post_action': None},
    '32、中华人民共和国人力资源和社会保障部':{'url':'https://www.mohrss.gov.cn/hsearch/?searchword={company}', 'action': None, 'post_action': None },
    '33、其他网站和媒体报道': {'url': 'https://www.baidu.com/s?ie=utf-8&bsst=1&rsv_dl=news_t_sk&tn=news&cl=2&medium=0&rtt=1&wd={company}', 'action': None, 'post_action': None},
}
