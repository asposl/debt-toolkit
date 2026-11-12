# -*- coding: utf-8 -*-
"""验证刷新是否切换验证码类型：触发查询后连续刷新 N 次观察类型序列。"""
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))

from modules.scraper import actions_captcha as ac
from modules.scraper.browser import bring_to_front, get_clean_page


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    page = get_clean_page()
    try:
        tab = page.new_tab('https://zxgk.court.gov.cn/zhzxgk/')
        bring_to_front(tab)
        tab.wait.ele_displayed('#pName', timeout=10)
        tab.ele('#pName', timeout=8).input('张三', clear=True)
        tab.ele('#pCardNum', timeout=8).input('110101199003077512', clear=True)
        tab.ele('css:button.btn-zxgk', timeout=8).click(by_js=True)
        print('已点击查询', flush=True)

        popup = ac._tianai_popup(tab, timeout=10)
        if not popup:
            print('未弹出验证码')
            return
        ac._tianai_content_ready(popup, timeout=12)
        modes = [ac._tianai_mode(popup)]
        for i in range(7):
            if not ac._tianai_still_showing(tab):
                print('弹窗消失，停止')
                break
            cur = tab.ele('css:.tianai-captcha-ui-overlay', timeout=1)
            if not cur:
                break
            ok = ac._tianai_refresh(tab, cur)
            if not ok:
                print(f'刷新失败（第{i+1}次）')
                break
            cur = tab.ele('css:.tianai-captcha-ui-overlay', timeout=2)
            if cur:
                ac._tianai_content_ready(cur, timeout=12)
                modes.append(ac._tianai_mode(cur))
            print(f'第{i+1}次刷新完成，累计类型序列: {modes}', flush=True)
        print(f'\n最终类型序列: {modes}')
        print(f'类型切换次数: {sum(1 for a, b in zip(modes, modes[1:]) if a != b)} / {len(modes)-1} 次刷新')
    finally:
        try:
            page.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
