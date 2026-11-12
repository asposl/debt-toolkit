# -*- coding: utf-8 -*-
"""检查执行信息公开网表单页是否自带 .ResultList 等结果元素（结果判定误报排查）。"""
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))

from modules.scraper.browser import bring_to_front, get_clean_page

SITES = [
    ('zhzxgk-综合查询', 'https://zxgk.court.gov.cn/zhzxgk/'),
    ('shixin-失信名单', 'https://zxgk.court.gov.cn/shixin/'),
]


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    page = get_clean_page()
    try:
        for name, url in SITES:
            print(f'\n===== {name} =====')
            tab = page.new_tab(url)
            bring_to_front(tab)
            time.sleep(4)  # 等页面完全渲染
            for sel in ('css:.ResultList', 'text=没有符合条件的数据', 'css:.Result', 'css:#result'):
                try:
                    ele = tab.ele(sel, timeout=1)
                except Exception as exc:
                    print(f'{sel:40s} 查询异常: {exc!r}')
                    continue
                if ele:
                    try:
                        shown = ele.states.is_displayed
                        text = (ele.text or '').strip().replace('\n', ' ')[:50]
                    except Exception:
                        shown, text = '?', '?'
                    print(f'{sel:40s} 存在  displayed={shown}  text="{text}"')
                else:
                    print(f'{sel:40s} 不存在')
            tab.close()
    finally:
        try:
            page.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
