# -*- coding: utf-8 -*-
"""分析提示图结构：尺寸、字符连通块位置、投影轮廓。"""
import os
import sys

import cv2
import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')

tip = cv2.imdecode(np.fromfile(os.path.join(OUT, 'diag_tip.png'), np.uint8), cv2.IMREAD_UNCHANGED)
print(f'提示图尺寸: {tip.shape}  dtype={tip.dtype}')

if tip.shape[2] == 4:
    print(f'alpha 通道: min={tip[:,:,3].min()} max={tip[:,:,3].max()}')
    alpha = tip[:, :, 3]
    # alpha 分段（不透明区域）
    col = (alpha > 128).sum(axis=0)
    segs = []
    in_seg = False
    for x, v in enumerate(col):
        if v > 0 and not in_seg:
            s = x; in_seg = True
        elif v == 0 and in_seg:
            segs.append((s, x)); in_seg = False
    if in_seg:
        segs.append((s, len(col)))
    print(f'alpha 不透明列分段: {segs}')

# 连通块分析（灰度）
gray = cv2.cvtColor(tip[:, :, :3], cv2.COLOR_BGR2GRAY)
print(f'灰度: min={gray.min()} max={gray.max()} mean={gray.mean():.1f}')
_, binv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
print(f'otsu 阈值后前景占比: {(binv>0).mean():.3f}')
n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binv, connectivity=8)
print(f'连通块数: {n_labels - 1}')
for i in range(1, n_labels):
    x, y, w, h, area = stats[i]
    if area > 30:
        print(f'  块{i}: x={x} y={y} w={w} h={h} area={area} 中心={centroids[i].round(1)}')

# 保存放大版中间结果便于检查
h, w = gray.shape
vis = np.repeat(np.repeat(binv[:, :, None], 4, axis=0), 4, axis=1)
cv2.imwrite(os.path.join(OUT, 'diag_tip_binary_x4.png'), vis)
print('二值化放大图 -> diag_tip_binary_x4.png')
