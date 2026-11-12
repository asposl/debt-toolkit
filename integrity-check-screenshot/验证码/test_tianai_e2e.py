# -*- coding: utf-8 -*-
"""天爱验证码端到端测试：4 号站（综合查询）/ 5 号站（失信名单）。

用法（在仓库根目录、非沙箱环境执行）：
  python 验证码/test_tianai_e2e.py sample            # 快速收集弹窗 DOM 样本（不求解）
  python 验证码/test_tianai_e2e.py full              # 完整端到端（默认主体：张三/空证件号）
  python 验证码/test_tianai_e2e.py full 李四 320...  # 指定姓名与证件号

sample 模式：填表单 → 点查询 → 弹窗出现即 dump HTML → 点刷新换图 → 再 dump，
循环收集多张样本用于离线确认滑块把手等 DOM 结构。
full 模式：跑完整 action_court_captcha（人工兜底默认 120s，够人手动完成验证码；
无人值守时用第 4 个参数调小），结束后校验结果并物理截图。
"""
import os
import sys
import time
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))

from modules.scraper import actions_captcha as ac
from modules.scraper.browser import bring_to_front, close_other_tabs, get_clean_page
from modules.scraper.capture import screenshot_pyautogui

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')
os.makedirs(OUT, exist_ok=True)

SITES = [
    ('4、中国执行信息公开网—综合查询', 'https://zxgk.court.gov.cn/zhzxgk/'),
    ('5、全国法院失信被执行人名单', 'https://zxgk.court.gov.cn/shixin/'),
]

_dump_seq = 0
_orig_popup = ac._tianai_popup


def _popup_with_dump(page, timeout=8):
    global _dump_seq
    popup = _orig_popup(page, timeout)
    if popup:
        ac._tianai_content_ready(popup)
        _dump_seq += 1
        try:
            html = popup.html
            path = os.path.join(OUT, f'popup_{_dump_seq:02d}.html')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f'[dump] popup_{_dump_seq:02d}.html  mode={ac._tianai_mode(popup)}')
        except Exception as exc:
            print(f'[dump] 失败: {exc!r}')
    return popup


ac._tianai_popup = _popup_with_dump


def _fill_and_query(tab, name, id_card):
    tab.wait.ele_displayed('#pName', timeout=10)
    tab.ele('#pName', timeout=8).input(name, clear=True)
    tab.ele('#pCardNum', timeout=8).input(id_card, clear=True)
    tab.ele('css:button.btn-zxgk', timeout=8).click(by_js=True)


def sample(page, subject, rounds=4):
    """每站触发一次查询 dump 首张图，再连点刷新收集换图样本。"""
    for site_name, url in SITES:
        print(f'\n===== sample: {site_name} =====')
        tab = page.new_tab(url)
        bring_to_front(tab)
        try:
            _fill_and_query(tab, subject['name'], subject.get('id_card', ''))
            popup = ac._tianai_popup(tab, timeout=10)
            if not popup:
                print('-> 未弹出验证码（可能直接出结果或被风控），跳过')
                continue
            for _ in range(rounds):
                if not ac._popup_visible(popup):
                    print('-> 弹窗已消失，停止采样')
                    break
                ac._tianai_refresh(page, popup)
                time.sleep(0.5)
        except Exception as exc:
            print(f'-> sample 异常: {exc!r}')
        finally:
            try:
                tab.close()
            except Exception:
                pass


def full(page, subject, out_dir):
    for site_name, url in SITES:
        print(f'\n===== full: {site_name} =====')
        tab = page.new_tab(url)
        bring_to_front(tab)
        try:
            ac.action_court_captcha(tab, subject)
            print('-> action 正常返回（判定通过）')
        except Exception as exc:
            print(f'-> action 抛异常: {exc!r}')
            traceback.print_exc()
        # 结果页渲染需要时间，等待后再校验。
        # 注意：不能再用 .ResultList——真实 class 是 Resultlist（小写 l），且该容器
        # 在表单页就已存在（隐藏）。改用实测有效的「结果行数 or 无数据提示」口径。
        state = None
        for _ in range(12):
            state = ac._court_state(tab)
            if state and (state.get('rows') or state.get('noHit')):
                break
            time.sleep(1)
        print(f'-> 结果状态: {state}')
        bring_to_front(tab)
        time.sleep(0.5)
        try:
            screenshot_pyautogui(out_dir, site_name)
            print(f'-> 截图完成: {site_name}.png')
        except Exception as exc:
            print(f'-> 截图失败: {exc!r}')
        try:
            tab.close()
        except Exception:
            pass


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    mode = sys.argv[1] if len(sys.argv) > 1 else 'full'
    subject = {'name': sys.argv[2] if len(sys.argv) > 2 else '张三',
               'id_card': sys.argv[3] if len(sys.argv) > 3 else ''}
    print(f'模式: {mode}  主体: {subject["name"]} / {subject["id_card"] or "(空)"}')

    if mode == 'full':
        # 人工兜底时长：默认 120 秒，够人手动完成一次验证码；
        # 无人值守跑批时用第 4 个参数调小。
        manual = int(sys.argv[4]) if len(sys.argv) > 4 else 120
        _orig_fb = ac._manual_fallback
        ac._manual_fallback = lambda page, base, timeout=90: _orig_fb(page, base, timeout=manual)

    page = get_clean_page()
    try:
        if mode == 'sample':
            sample(page, subject)
        else:
            out_dir = os.path.join(OUT, f'run_{time.strftime("%H%M%S")}')
            os.makedirs(out_dir, exist_ok=True)
            full(page, subject, out_dir)
    finally:
        try:
            close_other_tabs(page)
            page.quit()
        except Exception:
            pass
    print('\n完成。样本与截图在: ' + OUT)


if __name__ == '__main__':
    main()
