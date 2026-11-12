# -*- coding: utf-8 -*-
"""离线验证：提示图字形模板匹配 vs OCR 识字，用于点选验证码分配。

输入：test_output/diag_tip.png（提示图，4 个目标字横排）+ diag_bg.png（背景大字图）。
思路：提示图的 4 个字与背景字同字体同色系，把提示图切成 4 格，
     与背景字框（ddddocr det + 纠偏 + 缩放到统一尺寸）做相似度匹配，
     一对一最优分配（匈牙利/穷举），不依赖 OCR 认字。
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))

import cv2
import numpy as np

from modules.scraper import actions_captcha as ac

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')


def split_tip(tip_bgr, n=4):
    """把提示图横切成 n 格。先按列投影找字符块，失败则等宽切分。"""
    gray = cv2.cvtColor(tip_bgr, cv2.COLOR_BGR2GRAY)
    # 提示图一般白底黑字或浅底深字；二值化取较暗像素
    _, binv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    col_proj = binv.sum(axis=0) / 255
    # 找连续非零段
    segments = []
    in_seg = False
    for x, v in enumerate(col_proj):
        if v > 0 and not in_seg:
            start = x
            in_seg = True
        elif v == 0 and in_seg:
            segments.append((start, x))
            in_seg = False
    if in_seg:
        segments.append((start, len(col_proj)))
    # 过滤过窄的段（噪声）
    segments = [(s, e) for s, e in segments if e - s > tip_bgr.shape[1] * 0.04]
    if len(segments) == n:
        return [tip_bgr[:, s:e] for s, e in segments], segments
    # 兜底：等宽切分
    w = tip_bgr.shape[1] // n
    return [tip_bgr[:, i * w:(i + 1) * w] for i in range(n)], None


def norm_char(img_bgr, size=64, deskew=True):
    """归一化字符图：掩码→bounding box 裁剪→纠偏→缩放到统一尺寸。"""
    mask = _char_mask(img_bgr)
    if mask is None:
        return None
    ys, xs = np.where(mask > 0)
    if len(xs) < 10:
        return None
    crop = img_bgr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    crop_mask = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    angle = 0.0
    if deskew:
        angle = ac._mask_deskew_angle(crop_mask)
    if abs(angle) > 3:
        crop = ac._rotate_img(crop, angle, (255, 255, 255))
    return cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)


def _char_mask(img_bgr):
    """字符前景掩码：K-means 高饱和簇，失败时退化为暗像素。"""
    mask = ac._kmeans_char_mask(img_bgr)
    if mask is not None and (mask > 0).sum() > img_bgr.shape[0] * img_bgr.shape[1] * 0.02:
        return mask
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return m


def sim_gray(a, b):
    """灰度归一化互相关。"""
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
    ga -= ga.mean()
    gb -= gb.mean()
    denom = np.sqrt((ga * ga).sum() * (gb * gb).sum())
    if denom < 1e-6:
        return -1.0
    return float((ga * gb).sum() / denom)


def sim_mask(a, b):
    """掩码形状 IoU 相似度。"""
    ma = _char_mask(a)
    mb = _char_mask(b)
    if ma is None or mb is None:
        return -1.0
    ma = cv2.resize(ma, (64, 64)) > 127
    mb = cv2.resize(mb, (64, 64)) > 127
    inter = (ma & mb).sum()
    union = (ma | mb).sum()
    return float(inter / union) if union else -1.0


def sim_color(a, b):
    """HSV 色调直方图相关性。"""
    ha = cv2.calcHist([cv2.cvtColor(a, cv2.COLOR_BGR2HSV)], [0], None, [32], [0, 180])
    hb = cv2.calcHist([cv2.cvtColor(b, cv2.COLOR_BGR2HSV)], [0], None, [32], [0, 180])
    return float(cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    tip = cv2.imdecode(np.fromfile(os.path.join(OUT, 'diag_tip.png'), np.uint8), cv2.IMREAD_COLOR)
    bg = cv2.imdecode(np.fromfile(os.path.join(OUT, 'diag_bg.png'), np.uint8), cv2.IMREAD_COLOR)
    if tip is None or bg is None:
        print('缺 diag_tip.png / diag_bg.png')
        return

    # OCR 提示字（作为人类可读参照）
    targets = ac._read_tip_chars(tip)
    print(f'OCR 提示字: {targets}')

    cells, segs = split_tip(tip)
    print(f'提示图切分: {len(cells)} 格  分段={segs}')

    # 背景字框
    _, buf = cv2.imencode('.png', bg)
    boxes = ac._get_dddd_det().detection(buf.tobytes())
    print(f'背景字框: {len(boxes)} 个')

    bg_norms = []
    for i, (x1, y1, x2, y2) in enumerate(boxes):
        crop = bg[max(0, y1 - 4):y2 + 4, max(0, x1 - 4):x2 + 4]
        n = norm_char(crop)
        bg_norms.append(n)
        print(f'  框{i} ({x1},{y1},{x2},{y2}) 归一化{"成功" if n is not None else "失败"}')

    tip_norms = [norm_char(c) for c in cells]

    # 相似度矩阵（多指标）
    print('\n相似度矩阵（行=提示格 i，列=背景框 j）：')
    for metric_name, fn in (('灰度NCC', sim_gray), ('形状IoU', sim_mask), ('色调直方图', sim_color)):
        mat = np.zeros((len(tip_norms), len(bg_norms)))
        for i, tn in enumerate(tip_norms):
            for j, bn in enumerate(bg_norms):
                mat[i, j] = fn(tn, bn) if (tn is not None and bn is not None) else -1.0
        print(f'\n[{metric_name}]')
        for i in range(mat.shape[0]):
            print('  ' + ' '.join(f'{mat[i, j]:6.3f}' for j in range(mat.shape[1])))

    # 综合得分 = 0.5*灰度NCC + 0.3*形状IoU + 0.2*色调
    from itertools import permutations
    n, k = len(bg_norms), len(tip_norms)
    combined = np.zeros((k, n))
    for i, tn in enumerate(tip_norms):
        for j, bn in enumerate(bg_norms):
            if tn is None or bn is None:
                continue
            combined[i, j] = 0.5 * sim_gray(tn, bn) + 0.3 * max(sim_mask(tn, bn), 0) + 0.2 * max(sim_color(tn, bn), 0)
    print('\n[综合得分]')
    for i in range(k):
        print('  ' + ' '.join(f'{combined[i, j]:6.3f}' for j in range(n)))

    best, best_total = None, -1e9
    for idxs in permutations(range(n), k):
        total = sum(combined[i, j] for i, j in enumerate(idxs))
        if total > best_total:
            best_total, best = total, idxs
    print(f'\n一对一最优分配: {[f"提示{i}->框{j}" for i, j in enumerate(best)]}  总分={best_total:.3f}')
    print(f'对应点击中心: {[f"({(boxes[j][0]+boxes[j][2])/2:.0f},{(boxes[j][1]+boxes[j][3])/2:.0f})" for j in best]}')
    print(f'（提示字顺序: {targets}）')


if __name__ == '__main__':
    main()
