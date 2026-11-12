# -*- coding: utf-8 -*-
"""OCR 引擎离线对比基准：ddddocr old(生产现状) / ddddocr beta / PaddleOCR v5 server。

用已保存的真实验证码样本（test_output/diag_tip.png + diag_bg.png）走生产同一条
点选管线（提示字识别 → 字框定位 → 逐框多路投票 → 一对一分配），只替换识别引擎，
对比：提示字是否正确、逐框识别是否正确、最终分配是否命中真值、耗时是否可接受。

真值（人工核对 diag_bg.png 确认）：
  上排左→右 砧(100,94) 昔(247,97) 算(398,94) 狸(549,95)
  下排左→右 述(99,245) 鞠(250,244)
  提示图目标字（点击顺序）：算 昔 砧 鞠

用法：python 验证码/bench_engines.py [old|beta|paddle|all]
"""
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'GUI'))

TIP_PATH = os.path.join(ROOT, '验证码', 'test_output', 'diag_tip.png')
BG_PATH = os.path.join(ROOT, '验证码', 'test_output', 'diag_bg.png')

GT_TIP = ['算', '昔', '砧', '鞠']
# (x1,y1,x2,y2, 字) —— 与 meta.json 的 det_boxes 对应
GT_BOXES = [
    (208, 59, 287, 135, '昔'),
    (362, 60, 435, 129, '算'),
    (510, 55, 589, 136, '狸'),
    (211, 204, 289, 285, '鞠'),
    (59, 53, 142, 135, '砧'),
    (64, 208, 135, 283, '述'),
]


def imread(path):
    with open(path, 'rb') as f:
        return cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)


def enc(img):
    ok, buf = cv2.imencode('.png', img)
    return buf.tobytes() if ok else b''


def _hr(title):
    print('\n' + '=' * 64)
    print(' ', title)
    print('=' * 64)


def run_ddddocr(beta):
    """走生产函数，仅替换 _DDDD_OCR 实例。"""
    import ddddocr
    from modules.scraper import actions_captcha as ac

    tag = 'ddddocr-beta' if beta else 'ddddocr-old(生产现状)'
    _hr(f'引擎: {tag}')
    t = time.time()
    ac._DDDD_OCR = ddddocr.DdddOcr(beta=beta, show_ad=False)
    init_dt = time.time() - t
    print(f'  初始化 {init_dt:.1f}s')

    tip = imread(TIP_PATH)
    bg = imread(BG_PATH)

    t = time.time()
    targets = ac._read_tip_chars(tip)
    tip_dt = time.time() - t
    tip_ok = sorted(targets) == sorted(GT_TIP)
    print(f'  提示字: {"".join(targets)}  真值 {"".join(GT_TIP)}  '
          f'{"OK" if tip_ok else "WRONG"}  ({tip_dt:.1f}s)')

    t = time.time()
    assign, boxes, box_votes, _ = ac._detect_char_positions(bg, targets)
    det_dt = time.time() - t
    print(f'  字框数: {len(boxes)}  (det 仍为 ddddocr det)  识别+分配 {det_dt:.1f}s')

    _report_boxes(assign, boxes, box_votes, targets)
    return tip_ok, assign


def run_paddle():
    """把生产管线的识别引擎换成 PaddleOCR v5 server rec（多路投票框架不变）。"""
    from modules.scraper import actions_captcha as ac

    _hr('引擎: PaddleOCR v5 server (已下载的飞桨模型)')
    t = time.time()
    from paddlex import create_predictor
    rec = create_predictor('PP-OCRv5_server_rec', device='cpu')
    det = create_predictor('PP-OCRv5_server_det', device='cpu')
    init_dt = time.time() - t
    print(f'  初始化(det+rec) {init_dt:.1f}s')

    tip = imread(TIP_PATH)
    bg = imread(BG_PATH)

    # --- 单字 rec 耗时摸底：决定投票路数 ---
    x1, y1, x2, y2, _ = GT_BOXES[1]
    crop = bg[y1 - 4:y2 + 4, x1 - 4:x2 + 4]
    t = time.time()
    r0 = list(rec.predict(crop))[0]
    one_dt = time.time() - t
    print(f'  单字 rec 首次耗时 {one_dt:.2f}s  原始输出={r0.get("rec_text")!r} '
          f'score={r0.get("rec_score"):.3f}')
    full_variants = one_dt < 0.5  # 单路太快才跑 15 路，否则只跑 3 路

    import re as _re

    def paddle_rec(img_bgr, candidates=None):
        if img_bgr is None or img_bgr.size == 0:
            return '', 0.0
        if img_bgr.ndim == 2:
            img_bgr = cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2BGR)
        try:
            res = list(rec.predict(img_bgr))[0]
        except Exception:
            return '', 0.0
        text = (res.get('rec_text') or '').strip()
        score = float(res.get('rec_score') or 0.0)
        chars = _re.findall(r'[一-鿿]', text)
        if not chars:
            return '', 0.0
        if candidates and any(c not in candidates for c in chars):
            return '', 0.0
        return ''.join(chars), score

    def paddle_norm(_img, candidates):
        return {}  # 飞桨 rec 无全字符集 softmax，归一化兜底不适用

    # 单路太慢时缩减变体路数（只留 raw/bw/rot0）
    if not full_variants:
        orig_variants = ac._rec_char_variants

        def slim_variants(crop_img, candidates=None):
            votes = {}

            def vote(img, _tag):
                if img is None or getattr(img, 'size', 0) == 0:
                    return
                text, score = ac._rec_text_dddd(img, candidates)
                chars = _re.findall(r'[一-鿿]', text)
                if len(chars) == 1 and score >= ac.DDDD_REJECT_BELOW:
                    ch = chars[0]
                    if score > votes.get(ch, 0):
                        votes[ch] = score

            vote(crop_img, 'raw')
            mask = ac._kmeans_char_mask(crop_img)
            if mask is not None:
                vote(ac._mask_to_bw(mask), 'bw')
            return votes, []

        ac._rec_char_variants = slim_variants
        print('  单路 rec 偏慢 → 投票缩减为 3 路 (raw/bw)')

    ac._rec_text_dddd = paddle_rec
    ac._rec_candidate_scores = paddle_norm

    try:
        t = time.time()
        targets = ac._read_tip_chars(tip)
        tip_dt = time.time() - t
        tip_ok = sorted(targets) == sorted(GT_TIP)
        print(f'  提示字: {"".join(targets)}  真值 {"".join(GT_TIP)}  '
              f'{"OK" if tip_ok else "WRONG"}  ({tip_dt:.1f}s)')

        # 飞桨自己的 det 也跑一次对照
        t = time.time()
        dres = list(det.predict(bg))[0]
        polys = dres.get('dt_polys') or []
        det_dt = time.time() - t
        print(f'  飞桨 server det 检出 {len(polys)} 个框 ({det_dt:.1f}s): '
              + str([[int(p[0][0]), int(p[0][1])] for p in polys]))

        t = time.time()
        assign, boxes, box_votes, _ = ac._detect_char_positions(bg, targets)
        det2_dt = time.time() - t
        print(f'  生产管线(det=ddddocr): 字框 {len(boxes)}  识别+分配 {det2_dt:.1f}s')
        _report_boxes(assign, boxes, box_votes, targets)
    finally:
        # 还原，避免污染后续引擎
        import importlib
        importlib.reload(sys.modules['modules.scraper.actions_captcha'])
    return tip_ok, assign


def _report_boxes(assign, boxes, box_votes, targets):
    gt_at = {}
    for x1, y1, x2, y2, ch in GT_BOXES:
        gt_at[ch] = ((x1 + x2) / 2, (y1 + y2) / 2)

    n_box_ok = 0
    for i, ((cx, cy), votes) in enumerate(box_votes):
        gt = next((ch for ch, (gx, gy) in gt_at.items()
                   if abs(gx - cx) < 8 and abs(gy - cy) < 8), '?')
        top = max(votes.items(), key=lambda kv: kv[1]) if votes else ('', 0.0)
        ok = bool(votes) and top[0] == gt
        n_box_ok += ok
        print(f'    框{i} ({cx:5.0f},{cy:5.0f}) 真值={gt} '
              f'识别={top[0] or "-"} {top[1]:.3f} {"OK" if ok else "WRONG"} '
              f'全票={{{", ".join(f"{k}:{v:.2f}" for k, v in votes.items())}}}')
    print(f'  逐框 top1: {n_box_ok}/{len(box_votes)}')

    if assign:
        errs = []
        for ch, (px, py) in zip(targets, assign):
            gx, gy = gt_at.get(ch, (px, py))
            d = ((px - gx) ** 2 + (py - gy) ** 2) ** 0.5
            errs.append(d)
            print(f'    分配 {ch} -> ({px:.0f},{py:.0f})  真值({gx:.0f},{gy:.0f}) '
                  f'偏差 {d:.1f}px')
        ok_all = all(d < 15 for d in errs)
        print(f'  最终分配: 命中 {"OK" if ok_all else "WRONG"} '
              f'(最大偏差 {max(errs):.1f}px)')
    else:
        print('  最终分配: FAIL（凑不出一对一匹配）')


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'

    import ddddocr as _d
    pkg = os.path.dirname(_d.__file__)
    for f in ('common_old.onnx', 'common.onnx', 'common_det.onnx'):
        p = os.path.join(pkg, f)
        if os.path.exists(p):
            print(f'{f}: {os.path.getsize(p) / 1e6:.1f} MB')

    results = {}
    if which in ('old', 'all'):
        results['old'] = run_ddddocr(beta=False)
    if which in ('beta', 'all'):
        results['beta'] = run_ddddocr(beta=True)
    if which in ('paddle', 'all'):
        results['paddle'] = run_paddle()

    _hr('汇总')
    for k, v in results.items():
        print(f'  {k}: 提示字{"OK" if v[0] else "WRONG"}, 分配 '
              f'{"OK" if v[1] else "FAIL/WRONG"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
