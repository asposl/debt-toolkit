# -*- coding: utf-8 -*-
"""验证方案 v3：裁掉边框 → 列投影切分提示图字符 → 模板匹配分配。

已知结构（analyze_tip.py 实测）：提示图 286x76，四周有一圈装饰边框
（大连通块 x=5..283 y=2..70），字符在内部。边框是灰色的、字符是彩色的，
用 K-means 高饱和掩码做列投影，在边框内部区域切出 4 个字符格。
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))

import cv2
import numpy as np

from modules.scraper import actions_captcha as ac

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')


def det_boxes(img_bgr):
    _, buf = cv2.imencode('.png', img_bgr)
    return ac._get_dddd_det().detection(buf.tobytes())


def split_tip_cells(tip_bgr, n=4):
    """裁掉装饰边框后按彩色掩码列投影切分字符。

    返回 [cell_bgr, ...]（n 格）或 None。
    """
    mask = ac._kmeans_char_mask(tip_bgr)
    if mask is None:
        return None
    # 只保留边框内部区域（边框本身低饱和，被掩码排除；再保险起见去掉外圈 10px）
    inner = np.zeros_like(mask)
    h, w = mask.shape
    m = 10
    inner[m:h - m, m:w - m] = mask[m:h - m, m:w - m]
    col = (inner > 0).sum(axis=0)
    # 平滑投影，避免字符内部断裂
    kernel = 15
    smooth = np.convolve(col, np.ones(kernel), mode='same')
    # 自适应阈值：1/4 峰值以上视为字符列
    thr = smooth.max() * 0.25
    on = smooth > thr
    segs = []
    in_seg = False
    for x, v in enumerate(on):
        if v and not in_seg:
            s = x; in_seg = True
        elif not v and in_seg:
            segs.append((s, x)); in_seg = False
    if in_seg:
        segs.append((s, len(on)))
    # 合并过近段（间距 < 6px）
    merged = []
    for s, e in segs:
        if merged and s - merged[-1][1] < 6:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    # 保留宽度足够的段
    merged = [(s, e) for s, e in merged if e - s >= 20]
    if len(merged) != n:
        return None
    cells = []
    for s, e in merged:
        # 每格再按行投影裁到字形实际范围
        cell_mask = inner[:, s:e]
        rows = np.where((cell_mask > 0).any(axis=1))[0]
        if len(rows) == 0:
            return None
        y1, y2 = rows[0], rows[-1] + 1
        cells.append(tip_bgr[y1:y2, s:e])
    return cells


def norm_char(img_bgr, size=64):
    """K-means 掩码 bounding box 裁剪 → 纠偏 → 缩放。"""
    mask = ac._kmeans_char_mask(img_bgr)
    if mask is None:
        return None
    ys, xs = np.where(mask > 0)
    if len(xs) < 10:
        return None
    x1, x2, y1, y2 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    crop = img_bgr[y1:y2, x1:x2]
    crop_mask = mask[y1:y2, x1:x2]
    angle = ac._mask_deskew_angle(crop_mask)
    if abs(angle) > 3:
        crop = ac._rotate_img(crop, angle, (255, 255, 255))
    return cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)


def sim(a, b):
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
    ga -= ga.mean(); gb -= gb.mean()
    denom = np.sqrt((ga * ga).sum() * (gb * gb).sum())
    ncc = float((ga * gb).sum() / denom) if denom > 1e-6 else -1.0
    ha = cv2.calcHist([cv2.cvtColor(a, cv2.COLOR_BGR2HSV)], [0], None, [32], [0, 180])
    hb = cv2.calcHist([cv2.cvtColor(b, cv2.COLOR_BGR2HSV)], [0], None, [32], [0, 180])
    color = float(cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))
    return 0.6 * ncc + 0.4 * color


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    tip = cv2.imdecode(np.fromfile(os.path.join(OUT, 'diag_tip.png'), np.uint8), cv2.IMREAD_COLOR)
    bg = cv2.imdecode(np.fromfile(os.path.join(OUT, 'diag_bg.png'), np.uint8), cv2.IMREAD_COLOR)

    targets = ac._read_tip_chars(tip)
    print(f'OCR 提示字: {targets}')

    cells = split_tip_cells(tip)
    if cells is None:
        print('!! 切分失败')
        return
    print(f'切分出 {len(cells)} 格，宽度: {[c.shape[1] for c in cells]}')
    for i, c in enumerate(cells):
        cv2.imwrite(os.path.join(OUT, f'tmpl_tip_cell{i}.png'), c)

    tip_norms = [norm_char(c) for c in cells]
    print(f'归一化: {"全部成功" if all(t is not None for t in tip_norms) else "有失败"}')

    bg_boxes = det_boxes(bg)
    bg_norms = [norm_box(bg, b) for b in bg_boxes]

    mat = np.zeros((len(tip_norms), len(bg_norms)))
    for i, tn in enumerate(tip_norms):
        for j, bn in enumerate(bg_norms):
            mat[i, j] = sim(tn, bn) if (tn is not None and bn is not None) else -1.0
    print('\n模板相似度矩阵（行=提示字，列=背景框）：')
    for i in range(mat.shape[0]):
        print(f'  {targets[i]}: ' + ' '.join(f'{mat[i, j]:6.3f}' for j in range(mat.shape[1])))

    from itertools import permutations
    n, k = len(bg_norms), len(tip_norms)
    best, best_total = None, -1e9
    for idxs in permutations(range(n), k):
        total = sum(mat[i, j] for i, j in enumerate(idxs))
        if total > best_total:
            best_total, best = total, idxs
    print(f'\n模板匹配最优分配: {[f"{targets[i]}->框{j}" for i, j in enumerate(best)]}')
    print(f'点击中心(自然像素): {[f"({(bg_boxes[j][0]+bg_boxes[j][2])/2:.0f},{(bg_boxes[j][1]+bg_boxes[j][3])/2:.0f})" for j in best]}')

    # OCR 投票对照
    box_votes = []
    for x1, y1, x2, y2 in bg_boxes:
        crop = bg[max(0, y1 - 4):y2 + 4, max(0, x1 - 4):x2 + 4]
        box_votes.append(ac._rec_char_variants(crop)[0])
    print('\nOCR 投票（对照）:')
    for j, v in enumerate(box_votes):
        hit = [targets[i] for i in range(k) if targets[i] in v]
        print(f'  框{j}: {v}  目标命中={hit}')


def norm_box(img_bgr, box, pad=4):
    x1, y1, x2, y2 = box
    h, w = img_bgr.shape[:2]
    crop = img_bgr[max(0, y1 - pad):min(h, y2 + pad), max(0, x1 - pad):min(w, x2 + pad)]
    if crop.size == 0:
        return None
    mask = ac._kmeans_char_mask(crop)
    if mask is not None:
        angle = ac._mask_deskew_angle(mask)
        if abs(angle) > 3:
            crop = ac._rotate_img(crop, angle, (255, 255, 255))
    return cv2.resize(crop, (64, 64), interpolation=cv2.INTER_AREA)


if __name__ == '__main__':
    main()
