# -*- coding: utf-8 -*-
"""离线实验：对空投票字框尝试更多识别变体，看能否救活。

变体清单（在现有 4 路基础上新增）：
  - 原图/掩码黑白 等比放大 2x（RapidOCR 对大图更稳）
  - CLAHE 对比度增强
  - 自适应阈值二值化（黑字白底）
  - K-means 聚类数 3/5 的掩码黑白
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))

import cv2
import numpy as np

from modules.scraper import actions_captcha as ac

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')


def try_recognize(crop):
    """枚举变体并逐个识别，打印全部结果。"""
    variants = {}

    def add(name, img):
        if img is not None and img.size:
            variants[name] = img

    # 现有 4 路
    add('原图', crop)
    mask4 = ac._kmeans_char_mask(crop, clusters=4)
    if mask4 is not None:
        add('掩码4黑白', ac._mask_to_bw(mask4))
    mask3 = ac._kmeans_char_mask(crop, clusters=3)
    if mask3 is not None:
        add('掩码3黑白', ac._mask_to_bw(mask3))
    mask5 = ac._kmeans_char_mask(crop, clusters=5)
    if mask5 is not None:
        add('掩码5黑白', ac._mask_to_bw(mask5))
        ang5 = ac._mask_deskew_angle(mask5)
        if abs(ang5) > 3:
            add('掩码5纠偏', ac._mask_to_bw(ac._rotate_img(mask5, ang5, 0)))
            add('原图纠偏5', ac._rotate_img(crop, ang5, (255, 255, 255)))
    if mask4 is not None:
        ang4 = ac._mask_deskew_angle(mask4)
        if abs(ang4) > 3:
            add('掩码4纠偏', ac._mask_to_bw(ac._rotate_img(mask4, ang4, 0)))
            add('原图纠偏4', ac._rotate_img(crop, ang4, (255, 255, 255)))

    # 放大 2x
    big = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    add('原图2x', big)
    if mask4 is not None:
        bw = ac._mask_to_bw(mask4)
        if bw is not None:
            add('掩码4黑白2x', cv2.resize(bw, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))
    if mask3 is not None:
        bw3 = ac._mask_to_bw(mask3)
        if bw3 is not None:
            add('掩码3黑白2x', cv2.resize(bw3, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))

    # CLAHE 对比度增强
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    add('CLAHE原图', cv2.cvtColor(lab, cv2.COLOR_LAB2BGR))

    # 自适应阈值黑字白底
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    ad = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 31, 10)
    ad = 255 - ad
    add('自适应阈值', ad)
    add('自适应阈值2x', cv2.resize(ad, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))

    for name, img in variants.items():
        text, score = ac._rec_text(img)
        mark = '  <<<' if score >= 0.25 else ''
        print(f'    {name:12s} -> "{text}" ({score:.3f}){mark}')


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    for i in range(6):
        path = os.path.join(OUT, f'diag_box{i}.png')
        if not os.path.exists(path):
            continue
        crop = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
        print(f'\n=== diag_box{i}.png ({crop.shape[1]}x{crop.shape[0]}) ===')
        try_recognize(crop)


if __name__ == '__main__':
    main()
