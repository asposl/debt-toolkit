# -*- coding: utf-8 -*-
"""角度扫描诊断：暴力找出每个字框的"最优摆正角度"，用于确定纠偏符号约定。

对掩码黑白图在 [-90°, +90°] 上逐度旋转并 OCR，记录最高分对应的角度。
把它与 _mask_deskew_angle 的估计值对比，即可判定该用 +tilt 还是 -tilt，
以及 minAreaRect 对单个方块汉字的角度估计到底有多可靠。

用法（仓库根目录）：
    python 验证码/diag_angle_sweep.py [样本目录] [步长]
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
    step = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    from modules.scraper import actions_captcha as ac

    with open(os.path.join(sample_dir, 'diag_bg.png'), 'rb') as f:
        bg_bgr = ac._decode_captcha_img(f.read())

    import cv2
    _, buf = cv2.imencode('.png', bg_bgr)
    boxes = ac._get_dddd_det().detection(buf.tobytes())

    for i, (x1, y1, x2, y2) in enumerate(boxes):
        crop = bg_bgr[max(0, y1 - 4):y2 + 4, max(0, x1 - 4):x2 + 4]
        mask = ac._kmeans_char_mask(crop)
        tilt = ac._mask_deskew_angle(mask) if mask is not None else 0.0

        results = []
        a = -90
        while a <= 90:
            img = ac._mask_to_bw(ac._rotate_img(mask, a, 0))
            text, score = ac._rec_text(img)
            chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
            if chars and score > 0.2:
                results.append((a, chars[0], score))
            a += step

        results.sort(key=lambda r: -r[2])
        top = results[:5]
        print(f'框{i}: minAreaRect估计 tilt={tilt:6.1f}  '
              f'(-tilt={-tilt:6.1f})  最优前5:')
        for a, ch, sc in top:
            print(f'        角度{a:5d}°  {ch}  {sc:.3f}')
        if not top:
            print('        （全角度均未识别）')

    return 0


if __name__ == '__main__':
    sys.exit(main())
