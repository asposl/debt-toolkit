# -*- coding: utf-8 -*-
"""验证：K-means 高饱和掩码抠提示图字符（绕过灰色边框）。"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))

import cv2
import numpy as np

from modules.scraper import actions_captcha as ac

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')

tip = cv2.imdecode(np.fromfile(os.path.join(OUT, 'diag_tip.png'), np.uint8), cv2.IMREAD_COLOR)
mask = ac._kmeans_char_mask(tip)
print(f'掩码前景占比: {(mask > 0).mean():.3f}')

n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
print(f'连通块: {n_labels - 1}')
comps = []
for i in range(1, n_labels):
    x, y, w, h, area = stats[i]
    if area > 60:
        print(f'  块{i}: x={x} y={y} w={w} h={h} area={area}')
        comps.append((x, y, w, h, area))

# 按 x 排序看是否恰好 4 个字符块
comps.sort()
print(f'\n有效块数: {len(comps)}  x 中心: {[c[0] + c[2] / 2 for c in comps]}')

# 保存掩码可视化
cv2.imwrite(os.path.join(OUT, 'diag_tip_kmeans_mask.png'), mask)
print('掩码图 -> diag_tip_kmeans_mask.png')
