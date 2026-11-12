# -*- coding: utf-8 -*-
"""天爱验证码求解管线诊断：逐步打日志 + 图片落盘 + 人工辅助模式。

用法（仓库根目录执行）：
  python 验证码/diag_tianai.py                 # 默认 4 号站，主体 张三/110101199003077512
  python 验证码/diag_tianai.py 5              # 5 号站
  python 验证码/diag_tianai.py 4 李四 320...

流程：填表 → 点查询 → 等弹窗图片就位 → dump tip/bg 图片 →
跑自动求解管线（每步打日志：提示字/字框/逐字投票/分配）→
成功则点击；失败则把图片留在 test_output/ 等人工解：
  把点击坐标（显示像素，相对背景图左上角，逗号分隔，多点用空格分开）
  写入 test_output/solution.txt，脚本会按序点击并观察结果。
最后：弹窗消失后 dump 页面 HTML + 截图，检查结果元素判定。
"""
import json
import os
import sys
import time
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))

from modules.scraper import actions_captcha as ac
from modules.scraper.browser import bring_to_front, get_clean_page

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')
os.makedirs(OUT, exist_ok=True)

SITES = {
    '4': ('4、综合查询', 'https://zxgk.court.gov.cn/zhzxgk/'),
    '5': ('5、失信名单', 'https://zxgk.court.gov.cn/shixin/'),
}


def log(msg):
    print(msg, flush=True)


def imwrite_safe(path, img):
    """cv2.imwrite 对中文路径静默失败，用 imencode+文件对象绕过。"""
    import cv2

    ok, buf = cv2.imencode('.png', img)
    if ok:
        with open(path, 'wb') as f:
            f.write(buf.tobytes())
    return ok


def dump_result_dom(tab, tag):
    try:
        html = tab.html
        path = os.path.join(OUT, f'diag_result_{tag}.html')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        log(f'[dump] 结果页 HTML -> {path}')
    except Exception as exc:
        log(f'[dump] 结果页 HTML 失败: {exc!r}')


def check_result(tab):
    checks = {
        'css:.ResultList': None,
        'text=没有符合条件的数据': None,
        'text=查询结果': None,
        'css:.important': None,
    }
    for sel in checks:
        try:
            ele = tab.ele(sel, timeout=0.5)
            if ele:
                try:
                    checks[sel] = f'displayed={ele.states.is_displayed} text="{(ele.text or "")[:40]}"'
                except Exception:
                    checks[sel] = '存在(状态不可读)'
            else:
                checks[sel] = '不存在'
        except Exception as exc:
            checks[sel] = f'异常:{exc!r}'
    for sel, state in checks.items():
        log(f'  [结果检查] {sel:28s} {state}')


def run_word_click_diagnostics(popup):
    """跑点选管线并逐步打日志，返回 (targets, found_points, scale)。"""
    import cv2

    tip_img = popup.ele('css:#tianai-captcha-tip-img', timeout=3)
    bg_img = popup.ele('css:#tianai-captcha-slider-bg-img', timeout=3)
    if not (tip_img and bg_img):
        log('  [管线] 提示图/背景图元素缺失')
        return None, None, None

    tip_bgr = ac._decode_captcha_img(ac._get_base64_img_bytes(tip_img))
    bg_bgr = ac._decode_captcha_img(ac._get_base64_img_bytes(bg_img))
    imwrite_safe(os.path.join(OUT, 'diag_tip.png'), tip_bgr)
    imwrite_safe(os.path.join(OUT, 'diag_bg.png'), bg_bgr)
    log(f'  [dump] 提示图/背景图 -> {OUT}\\diag_tip.png / diag_bg.png  '
        f'bg尺寸={bg_bgr.shape[1]}x{bg_bgr.shape[0]}')

    targets = ac._read_tip_chars(tip_bgr)
    log(f'  [管线] 提示字识别: {targets}')

    nat_w = bg_img.run_js('return this.naturalWidth;') or bg_bgr.shape[1]
    nat_h = bg_img.run_js('return this.naturalHeight;') or bg_bgr.shape[0]
    disp_w, disp_h = bg_img.rect.size
    scale = (disp_w / nat_w, disp_h / nat_h)
    log(f'  [管线] natural={nat_w}x{nat_h} display={disp_w:.0f}x{disp_h:.0f} scale=({scale[0]:.3f},{scale[1]:.3f})')

    _, buf = cv2.imencode('.png', bg_bgr)
    boxes = ac._get_dddd_det().detection(buf.tobytes())
    log(f'  [管线] ddddocr det 字框 {len(boxes)} 个: {boxes}')

    box_votes = []
    for i, (x1, y1, x2, y2) in enumerate(boxes):
        crop = bg_bgr[max(0, y1 - 4):y2 + 4, max(0, x1 - 4):x2 + 4]
        votes, _dump = ac._rec_char_variants(crop)
        imwrite_safe(os.path.join(OUT, f'diag_box{i}.png'), crop)
        log(f'  [管线] 框{i} ({x1},{y1},{x2},{y2}) 中心=({(x1+x2)/2:.0f},{(y1+y2)/2:.0f}) 投票={votes} -> diag_box{i}.png')
        box_votes.append((((x1 + x2) / 2, (y1 + y2) / 2), votes))

    found = ac._assign_click_boxes(targets, box_votes)
    log(f'  [管线] 一对一分配结果: {found}')
    return targets, found, scale


def wait_manual_solution(timeout=180):
    """等待人工把点击坐标写入 solution.txt（显示像素，空格分隔多个点）。"""
    sol = os.path.join(OUT, 'solution.txt')
    if os.path.exists(sol):
        os.remove(sol)
    log(f'  [人工] 请查看 {OUT}\\diag_tip.png 与 diag_bg.png，'
        f'把点击坐标（显示像素，相对背景图左上角）写入 {sol}')
    log('  [人工] 格式: x1,y1 x2,y2 x3,y3 x4,y4 （按提示字顺序，空格分隔）')
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(sol):
            time.sleep(0.3)
            try:
                with open(sol, encoding='utf-8') as f:
                    content = f.read().strip()
                pts = []
                for tok in content.replace('，', ' ').replace(',', ' ').split():
                    try:
                        pts.append(float(tok))
                    except ValueError:
                        pass
                if len(pts) >= 4 and len(pts) % 2 == 0:
                    return [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)]
            except Exception:
                pass
        time.sleep(1)
    return None


def click_word_points(popup, points):
    bg_img = popup.ele('css:#tianai-captcha-slider-bg-img', timeout=3)
    for dx, dy in points:
        bg_img.click.at(dx, dy)
        time.sleep(0.4)
    time.sleep(0.5)
    confirm = popup.ele('css:.click-confirm-btn', timeout=2)
    if confirm and confirm.states.is_displayed:
        confirm.click()
        log('  [点击] 已点击确定')
    time.sleep(2)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    site_key = sys.argv[1] if len(sys.argv) > 1 else '4'
    name = sys.argv[2] if len(sys.argv) > 2 else '张三'
    id_card = sys.argv[3] if len(sys.argv) > 3 else '110101199003077512'
    site_name, url = SITES[site_key]
    log(f'站点: {site_name}  主体: {name} / {id_card}')

    page = get_clean_page()
    tag = site_key
    try:
        tab = page.new_tab(url)
        bring_to_front(tab)
        tab.wait.ele_displayed('#pName', timeout=10)
        tab.ele('#pName', timeout=8).input(name, clear=True)
        tab.ele('#pCardNum', timeout=8).input(id_card, clear=True)
        tab.ele('css:button.btn-zxgk', timeout=8).click(by_js=True)
        log('已点击查询')

        popup = ac._tianai_popup(tab, timeout=10)
        if not popup:
            log('未弹出验证码')
            dump_result_dom(tab, tag)
            return
        if not ac._tianai_content_ready(popup, timeout=12):
            log('警告：图片就位等待超时，继续尝试')
        mode = ac._tianai_mode(popup)
        log(f'弹窗类型: {mode}')

        if mode == 'click':
            targets, found, scale = run_word_click_diagnostics(popup)
            if found:
                log('  [自动] 分配成功，自动点击')
                click_word_points(popup, found)
            else:
                log('  [自动] 分配失败，转人工辅助')
                points = wait_manual_solution()
                if points:
                    log(f'  [人工] 收到坐标 {points}，点击')
                    click_word_points(popup, points)
                else:
                    log('  [人工] 超时未收到坐标')
        else:
            # 滑块：dump 图片 + 打缺口诊断日志，人工辅助暂不支持
            bg_img = popup.ele('css:#tianai-captcha-slider-bg-img', timeout=3)
            piece_img = popup.ele('css:#tianai-captcha-slider-move-img', timeout=3)
            handle = popup.ele('css:#tianai-captcha-slider-move-btn', timeout=3)
            log(f'  [滑块] bg={bool(bg_img)} piece={bool(piece_img)} handle={bool(handle)}')
            if bg_img and piece_img:
                bg_bgr = ac._decode_captcha_img(ac._get_base64_img_bytes(bg_img))
                piece_bgr = ac._decode_captcha_img(ac._get_base64_img_bytes(piece_img))
                imwrite_safe(os.path.join(OUT, 'diag_bg.png'), bg_bgr)
                imwrite_safe(os.path.join(OUT, 'diag_piece.png'), piece_bgr)
                log('  [dump] 背景/拼图 -> diag_bg.png / diag_piece.png')
                gap_x, piece_margin = ac._find_tianai_gap_x(
                    ac._get_base64_img_bytes(piece_img), ac._get_base64_img_bytes(bg_img))
                log(f'  [滑块] 缺口x(自然像素)={gap_x} 拼图透明左边距={piece_margin}')
                if bg_img and piece_img and handle:
                    try:
                        piece_offset = piece_img.rect.location[0] - bg_img.rect.location[0]
                        log(f'  [滑块] 拼图当前偏移={piece_offset:.0f}px 缺口(显示像素)={gap_x * scale_gap(bg_img):.0f}')
                    except Exception as exc:
                        log(f'  [滑块] 偏移计算失败: {exc!r}')
            ok = ac._solve_tianai_slider(page, popup)
            log(f'  [滑块] 自动求解返回: {ok}')

        # 观察验证结果
        for i in range(20):
            try:
                cur = tab.ele('css:.tianai-captcha-ui-overlay', timeout=0.3)
                visible = bool(cur) and ac._popup_visible(cur)
            except Exception:
                visible = False
            if not visible:
                log(f'弹窗已消失（第 {i * 0.5:.1f}s）')
                break
            time.sleep(0.5)
        else:
            log('弹窗仍在显示（验证未通过）')

        time.sleep(3)
        try:
            dump_result_dom(tab, tag)
        except Exception as exc:
            log(f'[dump] 结果页失败: {exc!r}')
        try:
            check_result(tab)
        except Exception as exc:
            log(f'[结果检查] 失败: {exc!r}')
        try:
            import pyautogui
            shot = os.path.join(OUT, f'diag_screen_{tag}.png')
            pyautogui.screenshot(shot)
            log(f'[截图] {shot}')
        except Exception as exc:
            log(f'[截图] 失败: {exc!r}')
    except Exception:
        traceback.print_exc()
    finally:
        try:
            page.quit()
        except Exception:
            pass


def scale_gap(bg_img):
    nat_w = bg_img.run_js('return this.naturalWidth;') or 1
    return bg_img.rect.size[0] / nat_w


if __name__ == '__main__':
    main()
