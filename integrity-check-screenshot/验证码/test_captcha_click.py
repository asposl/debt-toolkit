# -*- coding: utf-8 -*-
"""点选验证码识别管线离线测试单元（无需浏览器）。

目的
----
生产环境运行 action_court_captcha 期间，开启环境变量 CAPTCHA_DEBUG_DIR
会把每次点选的 tip / bg / 识别详情写到该目录的子目录里。本脚本负责把
这些"现场样本"或"人工保存的样本"离线喂给新版识别管线（ddddocr 普通模型单引擎
+ 完整字集直接识别 + probability），逐框打印识别结果与分配结论，用于复盘
"到底是没识别出、识别错了、还是点偏了"。

样本目录约定（任选其一即可）：
  验证码/captcha_live/<时间戳>_<主体>_<结果>/        ← 生产自动落盘
  验证码/test_output/                                ← diag_tianai.py 默认落盘
  任意用户指定目录，需含 tip.png + bg.png

用法（仓库根目录）：
  # 默认目录 test_output/
  python 验证码/test_captcha_click.py

  # 指定其它目录
  python 验证码/test_captcha_click.py 验证码/captcha_live/20260901_142000_张三_failed

  # 指定若干样本批量跑
  python 验证码/test_captcha_click.py 验证码/captcha_live 验证码/test_output

  # 只跑"已落盘"样本（不重新落盘）
  python 验证码/test_captcha_click.py --no-dump <目录...>

输出
----
stdout: 提示字 / det 框 / 每框投票 / 分配结果 / 命中提示字的框数 / 用时
可视化: <样本目录>/review/
  - bg_with_boxes.png   背景图上画 det 框（命中=绿，未命中=红）
  - boxes/<i>.png       逐框裁剪
  - variants/<i>/       每框的多路变体（raw / bw / bw_rotXX）
  - summary.json        本次跑的完整结构化结论
"""
import argparse
import json
import os
import sys
import time
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))


def _find_samples(roots):
    """在若干根目录里寻找"含 tip.png + bg.png"的样本子目录。

    兼容别名：diag_tip.png / diag_bg.png（diag_tianai.py 旧版落盘名）。
    找到候选后会归一化到 {tip.png, bg.png} 软链/复制，便于统一处理。
    """
    out = []
    name_pairs = [
        ('tip.png', 'bg.png'),
        ('diag_tip.png', 'diag_bg.png'),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        candidates = []
        if any(os.path.isfile(os.path.join(root, a)) and os.path.isfile(os.path.join(root, b))
               for a, b in name_pairs):
            candidates.append(root)
        try:
            for sub in sorted(os.listdir(root)):
                p = os.path.join(root, sub)
                if not os.path.isdir(p):
                    continue
                if any(os.path.isfile(os.path.join(p, a)) and os.path.isfile(os.path.join(p, b))
                       for a, b in name_pairs):
                    candidates.append(p)
        except Exception:
            pass
        out.extend(candidates)
    # 归一化：缺 tip.png 时把 diag_tip.png 复制过去
    for s in out:
        if not os.path.isfile(os.path.join(s, 'tip.png')) \
                and os.path.isfile(os.path.join(s, 'diag_tip.png')):
            try:
                import shutil
                shutil.copyfile(os.path.join(s, 'diag_tip.png'),
                                os.path.join(s, 'tip.png'))
            except Exception:
                pass
        if not os.path.isfile(os.path.join(s, 'bg.png')) \
                and os.path.isfile(os.path.join(s, 'diag_bg.png')):
            try:
                import shutil
                shutil.copyfile(os.path.join(s, 'diag_bg.png'),
                                os.path.join(s, 'bg.png'))
            except Exception:
                pass
    return out


def _read_img(path):
    import cv2
    return cv2.imdecode(
        __import__('numpy').fromfile(path, __import__('numpy').uint8),
        cv2.IMREAD_COLOR,
    )


def _write_img(path, img):
    import cv2
    ok, buf = cv2.imencode('.png', img)
    if ok:
        with open(path, 'wb') as f:
            f.write(buf.tobytes())
    return ok


def _run_one(sample_dir, dump=True):
    """在单条样本上跑识别管线，返回 dict 形式的结论。"""
    from modules.scraper import actions_captcha as ac

    t_total = time.time()
    tip_bgr = ac._decode_captcha_img(open(os.path.join(sample_dir, 'tip.png'), 'rb').read())
    bg_bgr = ac._decode_captcha_img(open(os.path.join(sample_dir, 'bg.png'), 'rb').read())
    if tip_bgr is None or bg_bgr is None:
        return {'sample': sample_dir, 'error': 'tip/bg 解码失败'}

    targets = ac._read_tip_chars(tip_bgr)

    # 直接调用生产路径（完整字集识别，目标字只作结果过滤）
    t_det = time.time()
    assignment, boxes, box_votes, box_dumps = ac._detect_char_positions(bg_bgr, targets)
    t_det = time.time() - t_det

    hit = sum(1 for _, votes in box_votes
              if any(c in (set(targets) if targets else set()) and votes.get(c, 0) > 0
                     for c in votes))
    summary = {
        'sample': sample_dir,
        'targets': targets,
        'det_box_count': len(boxes),
        'hit_box_count': hit,
        'assigned': dict(zip(targets, [(round(x, 1), round(y, 1)) for x, y in (assignment or [])]))
                      if assignment else None,
        'assign_ok': bool(assignment),
        'time_sec': round(t_det, 3),
        'box_votes': [
            {
                'box': list(boxes[i]),
                'votes': {k: round(v, 4) for k, v in votes.items()},
            }
            for i, ((_cx, _cy), votes) in enumerate(box_votes)
        ],
    }

    if dump:
        review = os.path.join(sample_dir, 'review')
        boxes_dir = os.path.join(review, 'boxes')
        variants_dir = os.path.join(review, 'variants')
        os.makedirs(boxes_dir, exist_ok=True)
        os.makedirs(variants_dir, exist_ok=True)
        vis = bg_bgr.copy()
        for bi, ((x1, y1, x2, y2), votes) in enumerate(zip(boxes, [v for _, v in box_votes])):
            cv2 = __import__('cv2')
            is_hit = any(c in (set(targets) if targets else set()) and votes.get(c, 0) > 0
                         for c in votes)
            color = (0, 200, 0) if is_hit else (0, 0, 220)
            crop = bg_bgr[max(0, y1 - 4):y2 + 4, max(0, x1 - 4):x2 + 4]
            _write_img(os.path.join(boxes_dir, f'box{bi}.png'), crop)
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
            cv2.putText(vis, f'#{bi}', (x1, max(0, y1 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        _write_img(os.path.join(review, 'bg_with_boxes.png'), vis)
        for bi, (box, variants) in enumerate(box_dumps or []):
            sub = os.path.join(variants_dir, f'box{bi}')
            os.makedirs(sub, exist_ok=True)
            for tag, img in variants:
                _write_img(os.path.join(sub, f'{tag}.png'), img)
        with open(os.path.join(review, 'summary.json'), 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    summary['total_sec'] = round(time.time() - t_total, 3)
    return summary


def _print_summary(s):
    print(f"\n=== {s.get('sample')} ===")
    if 'error' in s:
        print(f"  ERROR: {s['error']}")
        return
    print(f"  targets         : {s['targets']}")
    print(f"  det 框数        : {s['det_box_count']}    命中提示字的框: {s['hit_box_count']}")
    print(f"  分配结果        : {'OK' if s['assign_ok'] else 'FAIL'}"
          f"   {s['assigned']}")
    print(f"  det 耗时        : {s['time_sec']}s    总耗时: {s.get('total_sec')}s")
    for i, b in enumerate(s['box_votes']):
        print(f"  框{i} box={b['box']} votes={b['votes']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('roots', nargs='*', default=[
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')
    ], help='样本根目录（递归 1 层查找含 tip.png+bg.png 的子目录）')
    parser.add_argument('--no-dump', action='store_true',
                        help='不在样本目录写 review/（仅跑识别打日志）')
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    samples = _find_samples(args.roots)
    if not samples:
        print(f'未找到任何样本（tip.png + bg.png），root={args.roots}')
        return 1
    print(f'找到 {len(samples)} 个样本')

    fail = 0
    for s in samples:
        try:
            summary = _run_one(s, dump=not args.no_dump)
        except Exception:
            traceback.print_exc()
            fail += 1
            continue
        if not summary.get('assign_ok'):
            fail += 1
        _print_summary(summary)
    print(f'\n共 {len(samples)} 条，分配失败 {fail} 条')
    return 0 if fail == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
