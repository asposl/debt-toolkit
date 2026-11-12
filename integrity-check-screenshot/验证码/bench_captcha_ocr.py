# -*- coding: utf-8 -*-
"""点选验证码 OCR 管线离线基准（无需浏览器）。

用 diag_tianai.py / e2e 落盘的真实样本（diag_bg.png + diag_tip.png）跑完整
识别管线，输出逐框投票、置信度、分配结果，用于量化改动前后效果。

用法（仓库根目录）：
    python 验证码/bench_captcha_ocr.py                 # 默认 test_output/
    python 验证码/bench_captcha_ocr.py <样本目录>
"""
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    sample_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')
    bg_path = os.path.join(sample_dir, 'diag_bg.png')
    tip_path = os.path.join(sample_dir, 'diag_tip.png')
    for p in (bg_path, tip_path):
        if not os.path.exists(p):
            print(f'样本缺失: {p}')
            return 1

    t0 = time.time()
    from modules.scraper import actions_captcha as ac
    print(f'模块导入 {time.time() - t0:.1f}s')

    with open(bg_path, 'rb') as f:
        bg_bgr = ac._decode_captcha_img(f.read())
    with open(tip_path, 'rb') as f:
        tip_bgr = ac._decode_captcha_img(f.read())
    print(f'背景图 {bg_bgr.shape[1]}x{bg_bgr.shape[0]}  提示图 {tip_bgr.shape[1]}x{tip_bgr.shape[0]}')

    # --- 1. 提示字识别 ---
    t = time.time()
    targets = ac._read_tip_chars(tip_bgr)
    print(f'\n[提示字] {targets}  ({time.time() - t:.1f}s)')

    # --- 2. 字框检测 ---
    import cv2
    t = time.time()
    _, buf = cv2.imencode('.png', bg_bgr)
    boxes = ac._get_dddd_det().detection(buf.tobytes())
    print(f'[字框] ddddocr det 检出 {len(boxes)} 个  ({time.time() - t:.1f}s)')

    # --- 3. 逐框识别投票 ---
    candidates = set(targets) if targets else None
    box_votes = []
    print('\n[逐框投票]')
    for i, (x1, y1, x2, y2) in enumerate(boxes):
        crop = bg_bgr[max(0, y1 - 4):y2 + 4, max(0, x1 - 4):x2 + 4]
        t = time.time()
        try:  # 兼容改动前后两种签名
            votes, _dump = ac._rec_char_variants(crop, candidates)
        except (TypeError, ValueError):
            votes, _dump = ac._rec_char_variants(crop)
        dt = time.time() - t
        mask = ac._kmeans_char_mask(crop)
        angle = ac._mask_deskew_angle(mask) if mask is not None else 0.0
        hit = sorted([c for c in votes if c in (candidates or set())],
                     key=lambda c: -votes[c])
        print(f'  框{i}: {x1},{y1},{x2},{y2} 角度={angle:5.1f}° '
              f'耗时={dt:.2f}s 命中提示字={hit} 全票={votes}')
        box_votes.append((((x1 + x2) / 2, (y1 + y2) / 2), votes))

    # --- 4. 一对一分配 ---
    found = ac._assign_click_boxes(targets, box_votes)
    print(f'\n[分配] targets={targets} -> {"成功" if found else "失败"}')
    if found:
        for ch, pt in zip(targets, found):
            print(f'    {ch} -> ({pt[0]:.0f}, {pt[1]:.0f})')

    # --- 4b. 生产路径端到端复验（走 _detect_char_positions，含候选字集约束）---
    t = time.time()
    found2, det_boxes2, box_votes2, _ = ac._detect_char_positions(bg_bgr, targets)
    print(f'\n[生产路径] _detect_char_positions -> '
          f'{"成功" if found2 else "失败"}  ({time.time() - t:.1f}s)')
    if found2:
        for ch, pt in zip(targets, found2):
            print(f'    {ch} -> ({pt[0]:.0f}, {pt[1]:.0f})')

    # --- 5. 汇总指标 ---
    hit_boxes = sum(1 for _, v in box_votes
                    if any(c in (candidates or set()) for c in v))
    best_scores = [max(v.values()) for _, v in box_votes if v]
    print(f'\n[指标] 字框数={len(boxes)} 命中提示字的框={hit_boxes} '
          f'平均最高分={sum(best_scores) / len(best_scores) if best_scores else 0:.3f} '
          f'分配={"OK" if found else "FAIL"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
