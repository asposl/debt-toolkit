# -*- coding: utf-8 -*-
"""结果判定逻辑离线单测：不启浏览器，直接喂真实采样到的状态验证差分判定。

用例数据来自 2026-09-01 用 probe_result_dom.py 人工过验证码后的真实采样：
  4 号站表单页 {rows:0, heads:['综合查询被执行人','']}
  4 号站结果页 {rows:10, heads:['综合查询被执行人','查询结果']}
  5 号站表单页自带默认名单（rows 已有值）

覆盖重点：
  * 4 号站「0 行 → N 行」能检出
  * 5 号站「默认名单 → 过滤后名单」行数变化能检出
  * 5 号站行数恰好相同但内容不同，靠 names 检出（不漏也不误报）
  * 无数据提示文字能检出
  * 弹窗超时自动关闭（页面仍在表单页、状态与基线一致）【不能】误判为通过
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'GUI'))

from modules.scraper import actions_captcha as ac

FAILED = []


def check(case, base, cur, expect_hit, note):
    """用 mock 的当前状态跑一次判定，比对是否符合预期。"""
    ac._court_state = lambda page: cur
    signal = ac._court_result_appeared(page=None, base=base)
    hit = bool(signal)
    ok = hit == expect_hit
    tag = 'PASS' if ok else 'FAIL'
    if not ok:
        FAILED.append(case)
    print(f'  [{tag}] {case}')
    print(f'         期望{"检出" if expect_hit else "不检出"} → 实际: '
          f'{signal or "(未检出)"}')
    if note:
        print(f'         {note}')


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print('结果判定差分逻辑离线验证\n')

    # 4 号站（综合查询）：真实采样值
    base4 = {'rows': 0, 'names': [], 'heads': ['综合查询被执行人', ''], 'noHit': ''}
    res4 = {'rows': 10, 'names': ['查看'] * 5,
            'heads': ['综合查询被执行人', '查询结果'], 'noHit': ''}

    print('4 号站（综合查询）')
    check('出结果：0 行 → 10 行，标题变「查询结果」',
          base4, res4, True, '双重信号，任一命中即可')
    check('弹窗超时关闭，页面仍在表单页（状态=基线）',
          base4, base4, False, '关键：不能误判为通过，否则会截图到空表单')

    # 无数据分支
    print('\n无数据分支')
    check('查询无结果：出现「没有符合条件的数据」',
          base4,
          {'rows': 0, 'names': [], 'heads': ['综合查询被执行人', '查询结果'],
           'noHit': '没有符合条件的数据'},
          True, '无数据时同样算查询完成，必须放行')

    # 5 号站（失信名单）：自带默认名单
    base5 = {'rows': 5, 'names': ['王巧玲', '郭菲菲', '陈峰', '金根宝', '胡怀荣'],
             'heads': ['失信被执行人(自然人)公布'], 'noHit': ''}
    print('\n5 号站（失信名单，基线自带默认名单）')
    check('查询后行数变化（22 → 3）',
          base5,
          {'rows': 3, 'names': ['张三', '张三', '张三'],
           'heads': ['失信被执行人(自然人)公布'], 'noHit': ''},
          True, '行数差分')
    check('查询后行数相同但内容不同',
          base5,
          {'rows': 5, 'names': ['张三', '张三', '张三', '张三', '张三'],
           'heads': ['失信被执行人(自然人)公布'], 'noHit': ''},
          True, '靠 names 差分兜底，避免 rows 恰好相等时漏检')
    check('状态与基线完全一致（仍在默认名单）',
          base5, base5, False, '未发生查询，不能误判')

    # 表单页基线本身就带 noHit 的极端情况
    print('\n边界：基线自带无数据提示')
    check('基线已有 noHit，查询后仍是同一个 noHit',
          {'rows': 0, 'names': [], 'heads': [''], 'noHit': '暂无数据'},
          {'rows': 0, 'names': [], 'heads': [''], 'noHit': '暂无数据'},
          False, '同一提示不能算新结果')

    print()
    if FAILED:
        print(f'✗ {len(FAILED)} 个用例未通过: {FAILED}')
        return 1
    print('✓ 全部用例通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
