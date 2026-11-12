# -*- coding: utf-8 -*-
"""临时冒烟：用 stub 页面端到端跑 _solve_tianai_word_click（验证 main.py 真实路径）。

这不是单元测试——它模拟 DrissionPage 的元素接口，把生产函数从头跑到尾，
用来确认 GUI 调用链（site_configs -> action_court_captcha -> _solve_tianai_word_click）
在本轮改动后是通的，而不是只在离线函数层面通。

覆盖两类风险：
  1. 正常路径：识别 → 点击 → 落盘 → 日志三端（控制台 / GUI 队列 / log.txt）
  2. 元素失效路径：OCR 跑了近 1 秒，期间页面局部刷新把 img 节点换掉，
     之后读 rect.size / click 都会抛 ElementLostError。要求能自愈，
     且"图被换成另一张"时必须放弃（旧坐标作废，点了就是点错）。
"""
import base64
import os
import queue
import shutil
import sys

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'GUI'))

from modules.scraper import actions_captcha as ac  # noqa: E402

SRC = os.path.join(ROOT, '验证码', 'test_output')
OUT = os.path.join(ROOT, '验证码', 'captcha_live_smoke')


def _b64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode()


def _imread(path):
    """cv2.imread 不支持中文路径，走 np.frombuffer + imdecode。"""
    import numpy as np
    with open(path, 'rb') as f:
        return cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)


class _ElementLost(Exception):
    """模拟 DrissionPage.errors.ElementLostError。"""


class _Clicker:
    def __init__(self, owner):
        self._owner = owner
        self.points = []

    def at(self, x, y, *a, **k):
        self._owner._touch('click')
        self.points.append((round(float(x), 1), round(float(y), 1)))


class _Rect:
    def __init__(self, owner):
        self._owner = owner

    @property
    def size(self):
        self._owner._touch('rect')
        return self._owner._disp


class _Img:
    """模拟验证码 img 节点。

    fail=(kind, n)：kind 为 'rect' 或 'click'，表示第 n+1 次及之后的访问
    全部抛 ElementLostError——用来模拟"OCR 期间元素被页面换掉"。
    """

    def __init__(self, b64, nat, disp, name, fail=None):
        self._src = 'data:image/png;base64,' + b64
        self._nat = nat
        self._disp = disp
        self.name = name
        self._fail = fail
        self._n = {}
        self.rect = _Rect(self)
        self.click = _Clicker(self)

    def _touch(self, kind):
        self._n[kind] = self._n.get(kind, 0) + 1
        if self._fail and self._fail[0] == kind and self._n[kind] > self._fail[1]:
            raise _ElementLost(
                f'{self.name} 第 {self._n[kind]} 次 {kind} 访问时元素已失效')

    def attr(self, n):
        return self._src if n == 'src' else None

    def run_js(self, js):
        return self._nat[0] if 'naturalWidth' in js else self._nat[1]


class _Popup:
    """bg 元素按 bgs 队列依次返回（用完重复最后一个），模拟 DOM 节点被替换。"""

    def __init__(self, tip, bgs):
        self._tip = tip
        self._bgs = list(bgs)
        self._i = 0

    def ele(self, css, timeout=0):
        if css == 'css:#tianai-captcha-tip-img':
            return self._tip
        if css != 'css:#tianai-captcha-slider-bg-img':
            return None
        img = self._bgs[min(self._i, len(self._bgs) - 1)]
        self._i += 1
        return img


class _Page:
    title = 'stub-page'

    def ele(self, css, timeout=0):
        return None


def _latest_outcome(root):
    """从最近一次落盘的 meta.json 里读 outcome（目录名也带，但 json 更直接）。"""
    import json
    best, best_mt = None, -1
    for dirpath, _, files in os.walk(root):
        if 'meta.json' not in files:
            continue
        p = os.path.join(dirpath, 'meta.json')
        mt = os.path.getmtime(p)
        if mt > best_mt:
            best, best_mt = p, mt
    if not best:
        return None
    with open(best, encoding='utf-8') as f:
        return json.load(f).get('outcome')


def _run_case(case_root, tip, bgs):
    """跑一次生产函数，返回 (solved, outcome, 全部点击点)。"""
    shutil.rmtree(case_root, ignore_errors=True)
    ac.set_captcha_debug_dir('', force=True)
    ac.suggest_captcha_debug_dir(os.path.join(case_root, '验证码调试'))
    try:
        solved = ac._solve_tianai_word_click(_Page(), _Popup(tip, bgs))
    finally:
        ac.set_captcha_debug_dir('', force=True)
    clicks = []
    for img in bgs:
        if img is not None:
            clicks.extend(img.click.points)
    return solved, _latest_outcome(case_root), clicks


def main():
    # 兼容 diag_*.png 别名，缺样本时自动复制一份（跑完不删，方便下次）
    for name, alias in (('tip.png', 'diag_tip.png'), ('bg.png', 'diag_bg.png')):
        dst = os.path.join(SRC, name)
        if not os.path.isfile(dst) and os.path.isfile(os.path.join(SRC, alias)):
            shutil.copyfile(os.path.join(SRC, alias), dst)
    for p in (os.path.join(SRC, 'tip.png'), os.path.join(SRC, 'bg.png')):
        if not os.path.isfile(p):
            print(f'缺样本: {p}')
            return 1

    tip_raw = _imread(os.path.join(SRC, 'tip.png'))
    bg_raw = _imread(os.path.join(SRC, 'bg.png'))
    print(f'样本: tip={tip_raw.shape} bg={bg_raw.shape}')

    tip_b64, bg_b64 = _b64(os.path.join(SRC, 'tip.png')), _b64(os.path.join(SRC, 'bg.png'))
    nat = (bg_raw.shape[1], bg_raw.shape[0])

    def new_bg(name, b64=None, fail=None):
        return _Img(b64 or bg_b64, nat, nat, name, fail=fail)

    tip = _Img(tip_b64, (tip_raw.shape[1], tip_raw.shape[0]),
               (tip_raw.shape[1], tip_raw.shape[0]), 'tip')

    shutil.rmtree(OUT, ignore_errors=True)
    fails = []

    # ---------- 1. 正常路径（含三端日志） ----------
    bg = new_bg('bg')
    gui_logs = []
    ac.set_captcha_debug_dir('', force=True)  # 清掉显式设置，让 suggest 生效
    unwire = ac.add_captcha_log_sink(gui_logs.append)
    ac.suggest_captcha_debug_dir(os.path.join(OUT, '01_ok', '验证码调试'))
    try:
        solved_ok = ac._solve_tianai_word_click(_Page(), _Popup(tip, [bg]))
    finally:
        unwire()
        ac.set_captcha_debug_dir('', force=True)

    print(f'\n=== 1. 正常路径: solved={solved_ok} ===')
    print(f'点击坐标（页面像素）: {bg.click.points}')

    print('\n落盘目录树:')
    for root, dirs, files in os.walk(os.path.join(OUT, '01_ok')):
        rel = os.path.relpath(root, os.path.join(OUT, '01_ok'))
        depth = 0 if rel == '.' else rel.count(os.sep) + 1
        print('  ' * depth + f'{os.path.basename(root)}/')
        for f in sorted(files):
            print('  ' * (depth + 1) + f)

    print(f'\n--- GUI 日志区会收到的 {len(gui_logs)} 条 ---')
    for line in gui_logs[:6]:
        print('  ' + line.rstrip())
    if len(gui_logs) > 6:
        print(f'  ... 其余 {len(gui_logs) - 6} 条')

    log_file = None
    for root, _, files in os.walk(OUT):
        if 'log.txt' in files:
            log_file = os.path.join(root, 'log.txt')
            break
    if log_file:
        print(f'\n--- {os.path.basename(log_file)} ---')
        for line in open(log_file, encoding='utf-8').read().rstrip().split('\n'):
            print('  ' + line)

    # ---------- 2. 元素失效路径 ----------
    print('\n=== 2. 元素失效自愈（DrissionPage ElementLostError）===')
    cases = []

    # (a) 探测到失效，重定位成功且图没换 → 应该在【新元素】上点完 4 个字
    old, fresh = new_bg('bg0', fail=('rect', 1)), new_bg('bg1')
    solved, outcome, clicks = _run_case(os.path.join(OUT, '02a_relocate'), tip,
                                        [old, fresh])
    ok_a = solved is True and outcome == 'solved' and len(clicks) == 4 \
        and len(fresh.click.points) == 4
    cases.append(('重定位成功（同一张图）', ok_a,
                  f'solved={solved} outcome={outcome} 点击={len(clicks)}个'
                  f'(新元素{len(fresh.click.points)}个)'))

    # (b) 重定位回来发现图被换了 → 必须放弃，一个字都不能点
    old, changed = new_bg('bg0', fail=('rect', 1)), new_bg('bg1', b64=tip_b64)
    solved, outcome, clicks = _run_case(os.path.join(OUT, '02b_changed'), tip,
                                        [old, changed])
    ok_b = solved is False and outcome == 'element-lost' and not clicks
    cases.append(('重定位后图已被换', ok_b,
                  f'solved={solved} outcome={outcome} 点击={len(clicks)}个'))

    # (c) 节点彻底消失 → 必须放弃
    gone = new_bg('bg0', fail=('rect', 1))
    solved, outcome, clicks = _run_case(os.path.join(OUT, '02c_gone'), tip,
                                        [gone, None])
    ok_c = solved is False and outcome == 'element-lost' and not clicks
    cases.append(('重定位失败（节点没了）', ok_c,
                  f'solved={solved} outcome={outcome} 点击={len(clicks)}个'))

    # (d) 点到第 3 个字时才失效 → 重新定位后续点，总共仍是 4 个字
    old, fresh = new_bg('bg0', fail=('click', 2)), new_bg('bg1')
    solved, outcome, clicks = _run_case(os.path.join(OUT, '02d_midclick'), tip,
                                        [old, fresh])
    ok_d = (solved is True and outcome == 'solved' and len(clicks) == 4
            and len(old.click.points) == 2 and len(fresh.click.points) == 2)
    cases.append(('点到一半失效 → 续点', ok_d,
                  f'solved={solved} outcome={outcome} 点击={len(clicks)}个'
                  f'(旧{len(old.click.points)}+新{len(fresh.click.points)})'))

    for name, ok, detail in cases:
        print(f'  [{"PASS" if ok else "FAIL"}] {name}: {detail}')
        if not ok:
            fails.append(name)

    # ---------- 3. 接线回归：foreground_runner ----------
    # 这是 GUI 真实入口（main.py → integrity_check_ui → batch_runner →
    # foreground_runner）。单独验一遍，确保"日志进 GUI 队列 + 目录跟输出走"
    # 这条接线不会因为重构断掉——断了的表现是界面上完全看不到验证码诊断。
    print('\n--- foreground_runner 接线回归 ---')
    try:
        sys.path.insert(0, os.path.join(ROOT, 'GUI'))
        from modules.scraper.foreground_runner import _wire_captcha_diagnostics
    except Exception as exc:
        print(f'  FAIL 导入 foreground_runner: {exc!r}')
        return 1
    company_folder = os.path.join(OUT, '某公司', '4_执行信息公开网')
    os.makedirs(company_folder, exist_ok=True)
    q = queue.Queue()
    ac.set_captcha_debug_dir('', force=True)
    unwire = _wire_captcha_diagnostics(company_folder, q)
    suggested = ac._captcha_debug_root()
    print(f'  建议目录（应跟输出到中文路径下）: {suggested}')
    ac._log('接线探针')
    got = q.get_nowait() if q.qsize() else None
    print(f'  GUI 队列收到: {got.strip() if got else None}')
    unwire()
    ac._log('解注册后（不该再进队列）')
    leaked = q.qsize()
    ac.set_captcha_debug_dir('', force=True)
    wire_ok = (
        suggested.replace('\\', '/').endswith('验证码调试')
        and got is not None and leaked == 0
    )
    print('  [判定]', 'PASS 接线正常' if wire_ok else f'FAIL (leaked={leaked})')

    ok = (solved_ok is True and bool(bg.click.points) and log_file is not None
          and bool(gui_logs) and wire_ok and not fails)
    print('\n[判定]', 'PASS 生产路径 + 元素失效自愈 + 三端日志 + GUI 接线都通'
          if ok else f'FAIL (失败项={fails})')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
