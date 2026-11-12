# -*- coding: utf-8 -*-
"""提取弹窗样本 HTML 中的元素 id / class / 图片元素，核对选择器。"""
import os
import re
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

for name in ('popup_02.html', 'popup_01.html'):
    path = os.path.join(OUT, name)
    if not os.path.exists(path):
        print(f'{name}: 不存在')
        continue
    html = open(path, encoding='utf-8').read()
    print(f'===== {name} =====')
    ids = sorted(set(re.findall(r'id="([^"]+)"', html)))
    cls = sorted(set(re.findall(r'class="([^"]+)"', html)))
    print('IDS:')
    for i in ids:
        print('  ', i)
    print('CLASSES:')
    for c in cls:
        print('  ', c)
    print('img 标签数:', len(re.findall(r'<img', html)),
          ' canvas 标签数:', len(re.findall(r'<canvas', html)))
    # 背景图相关元素的完整标签
    for m in re.finditer(r'<(?:img|canvas)[^>]*(?:bg|tip)[^>]*>', html, re.I):
        print('  元素:', m.group(0)[:200])
