# -*- coding: utf-8 -*-
"""诊断提示图识别质量 + 各字框掩码质量。

1) 提示图：整图识别 vs 投影切分后逐字识别，对比两者结果；
2) 字框掩码：前景占比、连通域数量/面积，判断掩码提取是否成功；
3) K-means 随机性：同一图重复跑 N 次，看掩码前景占比是否稳定。

用法（仓库根目录）：
    python 验证码/diag_tip_and_mask.py [样本目录]
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    sample_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')

    from modules.scraper import actions_captcha as ac
    import cv2
    import numpy as np

    # ---------------- 提示图 ----------------
    with open(os.path.join(sample_dir, 'diag_tip.png'), 'rb') as f:
        tip = ac._decode_captcha_img(f.read())
    print(f'提示图 {tip.shape[1]}x{tip.shape[0]}')

    whole, wscore = ac._rec_text(tip)
    print(f'  整图识别: "{whole}" ({wscore:.3f})')

    gray = cv2.cvtColor(tip, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    colsum = (bw > 0).sum(axis=0)
    # 按列投影找连续有像素的区段 = 单字
    segs, in_seg, s = [], False, 0
    for x, v in enumerate(colsum):
        if v > 0 and not in_seg:
            s, in_seg = x, True
        elif v == 0 and in_seg:
            segs.append((s, x))
            in_seg = False
    if in_seg:
        segs.append((s, len(colsum)))
    segs = [g for g in segs if g[1] - g[0] >= 8]
    print(f'  列投影切出 {len(segs)} 段: {segs}')

    per_char = []
    for i, (a, b) in enumerate(segs):
        sub = tip[:, max(0, a - 2):b + 2]
        pad = cv2.copyMakeBorder(sub, 8, 8, 8, 8,
                                 cv2.BORDER_CONSTANT, value=(255, 255, 255))
        t, sc = ac._rec_text(pad)
        ch = [c for c in t if '\u4e00' <= c <= '\u9fff']
        per_char.append((i, (a, b), t, sc))
        print(f'    字{i} 列{a}-{b} 宽{b-a:3d} -> "{t}" ({sc:.3f}) '
              f'汉字={ch}')

    # ---------------- 字框掩码 ----------------
    with open(os.path.join(sample_dir, 'diag_bg.png'), 'rb') as f:
        bg = ac._decode_captcha_img(f.read())
    _, buf = cv2.imencode('.png', bg)
    boxes = ac._get_dddd_det().detection(buf.tobytes())
    print(f'\n字框 {len(boxes)} 个')

    for i, (x1, y1, x2, y2) in enumerate(boxes):
        crop = bg[max(0, y1 - 4):y2 + 4, max(0, x1 - 4):x2 + 4]
        stats = []
        for _ in range(5):  # K-means 随机性检测
            m = ac._kmeans_char_mask(crop)
            stats.append(0.0 if m is None else float((m > 0).mean()))
        m = ac._kmeans_char_mask(crop)
        info = 'None'
        if m is not None:
            n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
            areas = sorted(st[1:, cv2.CC_STAT_AREA], reverse=True)[:4] if n > 1 else []
            info = (f'前景占比={float((m > 0).mean()):.3f} '
                    f'连通域={n - 1} 最大面积={areas}')
        print(f'  框{i} {x1},{y1},{x2},{y2} 尺寸{crop.shape[1]}x{crop.shape[0]} '
              f'重复5次占比={[round(s,3) for s in stats]}')
        print(f'        {info}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
