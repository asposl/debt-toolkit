# -*- coding: utf-8 -*-
"""验证 ddddocr det 在提示图上的字框检测 + 改进版模板匹配。"""
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


def norm_box(img_bgr, box, pad=4):
    """按字框裁剪 → K-means 掩码纠偏 → 全彩缩放到统一尺寸。"""
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


def sim(a, b):
    """灰度 NCC ×0.6 + 色调直方图 ×0.4。"""
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

    tip_boxes = det_boxes(tip)
    tip_boxes = sorted(tip_boxes, key=lambda b: b[0])
    print(f'提示图 det 字框: {tip_boxes}')
    if len(tip_boxes) != len(targets):
        print(f'!! 提示图字框数 {len(tip_boxes)} 与目标字数 {len(targets)} 不一致')
        return
    tip_norms = [norm_box(tip, b) for b in tip_boxes]

    bg_boxes = det_boxes(bg)
    print(f'背景 det 字框: {bg_boxes}')
    bg_norms = [norm_box(bg, b) for b in bg_boxes]

    mat = np.zeros((len(tip_norms), len(bg_norms)))
    for i, tn in enumerate(tip_norms):
        for j, bn in enumerate(bg_norms):
            mat[i, j] = sim(tn, bn) if (tn is not None and bn is not None) else -1.0
    print('\n模板相似度矩阵（行=提示字顺序，列=背景框）：')
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

    # 与 OCR 投票交叉验证
    box_votes = []
    for x1, y1, x2, y2 in bg_boxes:
        crop = bg[max(0, y1 - 4):y2 + 4, max(0, x1 - 4):x2 + 4]
        votes, _ = ac._rec_char_variants(crop)
        box_votes.append(votes)
    print('\nOCR 投票（对照）:')
    for j, v in enumerate(box_votes):
        hit = [targets[i] for i in range(k) if targets[i] in v]
        print(f'  框{j}: {v}  目标命中={hit}')


if __name__ == '__main__':
    main()
