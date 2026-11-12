# -*- coding: utf-8 -*-
"""持续采样执行信息公开网「点查询 → 出结果」全过程，确定可靠的结果判定信号。

为什么需要它：4/5 号站「验证码过了却反复点查询」的根因，是结果判定选择器
从未在「真实通过后的页面」上验证过。此前两轮 E2E 都没跑通，代码里的选择器
一直是猜的。本脚本用人工过验证码的方式拿到真凭实据。

已确认的两点事实（2026-09-01 首次探测）：
  * p.bg-default.mybg 在【表单页就已存在】——4 号站文字「综合查询被执行人」，
    5 号站「失信被执行人(自然人)公布」且多一个 bg_title 类。
    所以「该元素存在」不能当信号，只有【文字变成「查询结果」】才是。
  * 5 号站打开页面就自带一张默认名单表格，不存在「表格从无到有」的变化，
    判定必须靠内容变化（行数 / 首行姓名 / 无数据提示）。

用法（仓库根目录、非沙箱、需真实浏览器与外网）：
  python 验证码/probe_result_dom.py          # 依次跑 4、5 号站
  python 验证码/probe_result_dom.py 4 300    # 只跑 4 号站，人工等待上限 300 秒
流程：自动填表点查询 → 弹窗出现后请在浏览器里【手动完成验证码】 →
      脚本持续采样并在状态变化时打印时间线，自动落盘 DOM 证据。

注意：DrissionPage 4.1.1.4 的 run_js 不支持传 list 参数，候选选择器必须内联进 JS。
"""
import hashlib
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))

from modules.scraper.browser import bring_to_front, get_clean_page

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')
os.makedirs(OUT, exist_ok=True)

SITES = {
    '4': ('4、综合查询', 'https://zxgk.court.gov.cn/zhzxgk/'),
    '5': ('5、失信名单', 'https://zxgk.court.gov.cn/shixin/'),
}

SUBJECT = {'name': '张三', 'id_card': ''}

CANDIDATES = [
    'p.bg-default.mybg',
    '.bg-default.mybg',
    '.ResultList',
    '#ResultList',
    '.resultList',
    '.result-list',
    '.search-result',
    '.list-box',
    '.table-list',
    'a.View',
    'table',
]

# 候选选择器内联进 JS（run_js 不支持 list 参数）
PROBE_JS = r"""
return (function () {
    var sels = %s;
    var hits = [];
    for (var i = 0; i < sels.length; i++) {
        var el = null;
        try { el = document.querySelector(sels[i]); } catch (e) {}
        if (el && (el.offsetParent !== null || el.clientHeight > 0)) {
            hits.push(sels[i]);
        }
    }
    // 标题文字：表单页是「综合查询被执行人」/「失信被执行人(自然人)公布」，
    // 出结果后据观察变为「查询结果」。这是区分表单页与结果页的关键。
    var heads = document.querySelectorAll('p.bg-default.mybg');
    var ptxt = [];
    for (var h = 0; h < heads.length; h++) {
        ptxt.push(((heads[h].innerText) || '').trim());
    }
    var ov = document.querySelector('.tianai-captcha-ui-overlay');
    var popup = !!(ov && (ov.offsetParent !== null || ov.clientHeight > 0));
    var body = document.body ? document.body.innerText : '';
    var noData = ['没有符合条件的数据', '没有查询到', '无符合条件',
                  '未查询到', '暂无数据', '没有找到', '无相关数据'];
    var noHit = '';
    for (var n = 0; n < noData.length; n++) {
        if (body.indexOf(noData[n]) >= 0) { noHit = noData[n]; break; }
    }
    return JSON.stringify({
        hits: hits,
        ptxt: ptxt,
        popup: popup,
        rows: document.querySelectorAll('a.View').length,
        bodyLen: body.length,
        noHit: noHit,
        first: body.slice(0, 60)
    });
})()
""" % json.dumps(CANDIDATES)

ALL_CLASSES_JS = r"""
return (function () {
    var seen = {};
    var all = document.querySelectorAll('body *');
    for (var i = 0; i < all.length; i++) {
        var c = all[i].className;
        if (typeof c === 'string' && c) {
            var parts = c.split(/\s+/);
            for (var j = 0; j < parts.length; j++) { seen[parts[j]] = 1; }
        }
    }
    return Object.keys(seen).sort().join('\n');
})()
"""


def probe(tab):
    try:
        raw = tab.run_js(PROBE_JS)
        return json.loads(raw) if raw else {}
    except Exception as exc:
        print(f'    [probe 异常] {exc!r}')
        return {}


def sig(d):
    """状态指纹：用于只在变化时打印，避免刷屏。"""
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def dump_evidence(tab, tag, note=''):
    """落盘：全部 class 名 + 叶子节点 + 正文片段，作为照实修选择器的依据。"""
    path = os.path.join(OUT, f'{tag}_{time.strftime("%H%M%S")}.txt')
    try:
        classes = tab.run_js(ALL_CLASSES_JS)
    except Exception as exc:
        classes = f'<js-error {exc!r}>'
    try:
        nodes = tab.run_js(
            "return Array.prototype.slice.call(document.querySelectorAll('body *'))"
            ".filter(function(e){return e.children.length===0 && e.offsetParent!==null;})"
            ".slice(0,200).map(function(e){return e.tagName+'.'+e.className+' | '"
            "+ (e.innerText||'').trim().slice(0,40);}).join('\\n');"
        )
    except Exception as exc:
        nodes = f'<js-error {exc!r}>'
    try:
        text = tab.run_js("return (document.body?document.body.innerText:'').slice(0,3000);")
    except Exception as exc:
        text = f'<js-error {exc!r}>'
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(f'tag: {tag}\nnote: {note}\nurl: {tab.url}\n\n'
                 f'--- all classes ---\n{classes}\n'
                 f'\n--- leaf nodes ---\n{nodes}\n'
                 f'\n--- body text ---\n{text}\n')
    return path


def run_site(page, key, wait_sec):
    site_name, url = SITES[key]
    print(f'\n{"="*66}\n{site_name}  {url}\n{"="*66}')
    tab = page.new_tab(url)
    bring_to_front(tab)
    time.sleep(5)

    print('\n[A] 表单页基线（点查询之前）')
    base = probe(tab)
    print(f'    标题文字 p.bg-default.mybg = {base.get("ptxt")}')
    print(f'    命中候选 = {base.get("hits")}')
    print(f'    a.View 行数 = {base.get("rows")}   正文长度 = {base.get("bodyLen")}')
    dump_evidence(tab, f'base_{key}', 'form page before query')

    base_hits = set(base.get('hits') or [])
    base_ptxt = base.get('ptxt') or []
    base_rows = base.get('rows', 0)
    print(f'    → 表单页即存在的候选 {sorted(base_hits)} 不能单独当结果信号')

    print('\n[B] 填表并点击查询 → 弹窗出现后请手动完成验证码')
    try:
        tab.wait.ele_displayed('#pName', timeout=15)
        tab.ele('#pName', timeout=8).input(SUBJECT['name'], clear=True)
        tab.ele('#pCardNum', timeout=8).input(SUBJECT['id_card'], clear=True)
        tab.ele('css:button.btn-zxgk', timeout=8).click(by_js=True)
    except Exception as exc:
        print(f'    [填表失败] {exc!r}')
        return
    try:
        tab.run_js("document.title = arguments[0];",
                   '【需人工】请手动完成验证码')
    except Exception:
        pass

    print(f'\n[C] 持续采样（弹窗消失/结果出现均记录，最长 {wait_sec}s）')
    print('    —— 请现在去浏览器完成验证码 ——')
    t0 = time.time()
    last = sig(base)
    dumped = False
    result_seen = None
    while time.time() - t0 < wait_sec:
        cur = probe(tab)
        if not cur:
            time.sleep(0.5)
            continue
        if sig(cur) != last:
            el = time.time() - t0
            print(f'    +{el:6.1f}s  弹窗={cur.get("popup")}  '
                  f'标题={cur.get("ptxt")}  行数={cur.get("rows")}  '
                  f'正文长={cur.get("bodyLen")}  无数据提示={cur.get("noHit") or "-"}')
            new_hits = sorted(set(cur.get('hits') or []) - base_hits)
            if new_hits:
                print(f'              ★ 新增候选命中: {new_hits}')
            if '查询结果' in (cur.get('ptxt') or []) and '查询结果' not in base_ptxt:
                print('              ★★ 标题变为「查询结果」——这就是结果信号')
            last = sig(cur)

            # 出现实质变化且弹窗已消失 → 判定为结果态，落盘证据
            if not dumped and not cur.get('popup') and (
                new_hits or cur.get('noHit')
                or ('查询结果' in (cur.get('ptxt') or []) and '查询结果' not in base_ptxt)
                or cur.get('rows') != base_rows
            ):
                result_seen = cur
                path = dump_evidence(tab, f'result_{key}', 'after manual captcha passed')
                print(f'              [证据落盘] {path}')
                dumped = True
                break
        time.sleep(0.5)

    try:
        tab.run_js("document.title = arguments[0];", site_name)
    except Exception:
        pass

    if not dumped:
        print('\n    ⚠ 未在等待窗口内捕获到结果态（弹窗可能超时自动关闭）')
        print('      可增大等待时间重跑，例如: python 验证码/probe_result_dom.py '
              f'{key} 600')
        dump_evidence(tab, f'timeout_{key}', 'no result state captured')
    else:
        print(f'\n    结果态快照: 标题={result_seen.get("ptxt")} '
              f'行数={result_seen.get("rows")} 无数据提示={result_seen.get("noHit") or "-"}')

    try:
        tab.close()
    except Exception:
        pass


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    which = sys.argv[1] if len(sys.argv) > 1 else None
    wait_sec = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    keys = [which] if which else ['4', '5']

    print('目标：确认「出结果」的可靠判定信号（尤其是标题是否变为「查询结果」）')
    print(f'采样上限 {wait_sec}s/站；弹窗出现后请手动完成验证码\n')

    page = get_clean_page()
    try:
        for key in keys:
            try:
                run_site(page, key, wait_sec)
            except Exception as exc:
                import traceback
                print(f'[{key} 号站] 异常: {exc!r}')
                traceback.print_exc()
    finally:
        try:
            page.quit()
        except Exception:
            pass
    print(f'\n完成。证据目录: {OUT}')


if __name__ == '__main__':
    main()
