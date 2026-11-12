# 验证码类动作；ddddocr / cv2 在函数内按需导入。
import json
import os
import re
import shutil
import threading
import time
import traceback

from .page_helpers import _subject_id, _subject_name


# ============================================================
# 天爱验证码（执行信息公开网 4/5 号站）：点选文字 + 滑块拼图
# ============================================================

# 旧版的双引擎策略（rapidocr + ddddocr）已经废弃，全部走 ddddocr。保留两个
# 旧名作为兼容壳：_RAPIDOCR 不再被实例化（rapidocr 也未安装），_get_rapidocr
# 抛错以便任何老路径被发现。
_RAPIDOCR = None
_DDDD_DET = None
_DDDD_OCR = None
_DDDD_OCR_FAILED = False  # ddddocr 识别路是否曾异常（用于只告警一次）

# 点选 OCR 用哪个模型：False=普通模型，True=beta 模型。
# 只影响 4/5 号站（天爱点选是 _get_dddd_ocr 的唯一使用者）；3 号站滑块走
# cv2、8 号站自己 new 一个默认 DdddOcr，都不受这个开关影响。
#
# 普通模型是生产默认值；如需临时对比 beta，只改这一处即可。
DDDD_OCR_BETA = False

# 生产路径始终让 ddddocr 在完整字集上直接识别。提示字只用于过滤模型原始
# 结果，不能把候选集重新归一化后当成真实概率，否则会把低可信结果强行配上。
DDDD_VOTE_SCORE = 0.45
DDDD_REJECT_BELOW = 0.60     # 原始 confidence 低于此值视为不可信，不计票
DDDD_ASSIGN_MIN_SCORE = 0.60
# ddddocr 的 set_ranges(int=N) 实际是 charset[:N+1]——N=2 只含前 3 个字符
# (空 + 2 个偏门字)，**不含任何汉字**。tip 整图识别的旧版 _read_tip_chars
# 在切到 ddddocr 后就是被这条暗坑打回，提示字全空。无 candidates 时必须用
# 完整 charset 列表，不能用 int。

# 点选验证码诊断落盘。三种指定方式，优先级从高到低：
#   1) set_captcha_debug_dir(path) 运行时设置（GUI 长驻进程唯一可行的入口）
#   2) 环境变量 CAPTCHA_DEBUG_DIR（进程启动前设，适合源码跑批）
#   3) 都没设 → 默认开启到 <启动目录>/验证码调试/
# 第 3 条是刻意保留的兜底：点选出错时最先需要的就是现场图片，而用户几乎不会
# 预开开关，默认关等于出问题时什么都没留下。开销可控——默认只写 5 个文件
# （见 CAPTCHA_DEBUG_VERBOSE），每次点约 200KB，且自动保留最近若干次。
CAPTCHA_DEBUG_DIR = os.environ.get("CAPTCHA_DEBUG_DIR", "").strip()
CAPTCHA_DEBUG_DEFAULT = os.environ.get("CAPTCHA_DEBUG_DEFAULT", "1").strip() != "0"

# 是否额外落每框的 15 路识别变体（raw/bw/bw_rot±90°，6 框约 96 个文件）。
# 只在调优识别算法时才需要，默认关闭，否则跑一批就几千个文件。
CAPTCHA_DEBUG_VERBOSE = os.environ.get("CAPTCHA_DEBUG_VERBOSE", "").strip() == "1"

# 每个主体目录下最多保留最近多少次点选目录，超出自动删最旧的
CAPTCHA_DEBUG_KEEP = int(os.environ.get("CAPTCHA_DEBUG_KEEP", "40") or 40)

# ------------------------------------------------------------------
# 求解额度：3 / 4 / 5 / 8 号站共用同一套口径
# ------------------------------------------------------------------
# 「重试 N 次」计的是**真正向站点提交了一次答案**的次数。没提交就换图
# （提示字读不出、字框凑不出一对一匹配、元素失效……）属于主动刷新，
# 不消耗这个额度——否则一张烂图就能吃掉一整轮的预算。
CAPTCHA_MAX_ATTEMPTS = 5

# ------------------------------------------------------------------
# 人工介入：只在「少批量查漏」时启用
# ------------------------------------------------------------------
# 批量处理（勾选站点数 > 10）时不要求人工：一是没人会一直盯着屏幕，
# 二是每个对象卡 90s × N 个对象会拖垮整批。查漏场景站点少才值得等。
MANUAL_BATCH_THRESHOLD = 10

MANUAL_TIMEOUT = 90          # 人工介入等待时长（秒）
MANUAL_POLL_INTERVAL = 0.3   # 轮询间隔（秒）
MANUAL_RESULT_WAIT = 5       # 验证码控件消失后，再给结果多少秒做最终确认
COURT_FORM_STARTUP_TIMEOUT = 15  # 4/5 号站打不开时，不进入整体 180 秒循环

# 本次任务勾选了多少个站点。由 batch_runner 在开始前注入，用来决定
# 是否允许人工介入；0 表示未知（保守地允许介入，沿用查漏的宽松口径）。
_CAPTCHA_SITE_COUNT = 0

_DEBUG_DIR_EXPLICIT = bool(CAPTCHA_DEBUG_DIR)  # 是否被显式设置过（供 force 判断）
_DEBUG_DIR_SUGGESTED = None  # 由调用方建议的值，可被反复更新


# ------------------------------------------------------------------
# 点选诊断日志：一处产生，三处消费
#   1) 控制台 print（exe 是 console=True，双击也能看到）
#   2) GUI 日志区——通过 add_captcha_log_sink(log_queue.put) 注册
#   3) 落盘 log.txt——每次点选一个目录，里面图文并茂
# 批量跑是多线程的：sink 表共享（加锁 + 引用计数），但"本轮会话"必须线程
# 隔离，否则并发点选时 A 的框日志会串进 B 的 log.txt。
# ------------------------------------------------------------------
_CAPTCHA_LOG_SINKS = {}   # {sink_fn: 引用计数}
_CAPTCHA_LOG_LOCK = threading.Lock()
_CAPTCHA_SESSION = threading.local()  # .lines: list[str]｜.dir: str | None


def add_captcha_log_sink(fn):
    """注册日志接收器（GUI 传 log_queue.put 即可）。返回反注册函数。

    【为什么用引用计数而不是 list 去重】站点流程目前是串行的，但多个站点
    传进来的往往是**同一个** sink（同一个 log_queue.put）。若只在列表里存
    一份，第一个站点结束时反注册就会把还在用的接收器摘掉，后续站点的诊断
    日志全部丢失——这种 bug 只在"最后一个站点有点选"时才暴露，极难复现。
    故按 (id 相等) 计数：注册 N 次就要反注册 N 次。
    """
    with _CAPTCHA_LOG_LOCK:
        _CAPTCHA_LOG_SINKS[fn] = _CAPTCHA_LOG_SINKS.get(fn, 0) + 1
    return lambda: remove_captcha_log_sink(fn)


def remove_captcha_log_sink(fn):
    with _CAPTCHA_LOG_LOCK:
        n = _CAPTCHA_LOG_SINKS.get(fn, 0) - 1
        if n > 0:
            _CAPTCHA_LOG_SINKS[fn] = n
        else:
            _CAPTCHA_LOG_SINKS.pop(fn, None)


def _log(msg, *args):
    try:
        line = ' '.join([str(msg)] + [str(a) for a in args])
    except Exception:
        line = str(msg)
    stamp = time.strftime('%H:%M:%S')
    try:
        print(f'[tianai {stamp}] {line}')
    except Exception:
        pass
    # 本轮会话缓冲（供落盘 log.txt）
    buf = getattr(_CAPTCHA_SESSION, 'lines', None)
    if buf is not None:
        buf.append(f'[{stamp}] {line}')
    # 推给 GUI 日志区
    with _CAPTCHA_LOG_LOCK:
        sinks = list(_CAPTCHA_LOG_SINKS.keys())
    for fn in sinks:
        try:
            fn(f'  -> [验证码] {line}\n')
        except Exception:
            pass


def _default_captcha_debug_root():
    """未显式指定时的默认落盘根目录。

    exe（sys.frozen）取 exe 所在目录，源码取工作目录——双击启动时两者都是
    用户能找到的地方，避免日志落进 System32 这类意料之外的位置。
    """
    import sys

    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
        else os.getcwd()
    return os.path.join(base, '验证码调试')


def _captcha_debug_root():
    """返回当前生效的落盘根目录（代码设置 > 环境变量 > 默认目录）。"""
    explicit = (CAPTCHA_DEBUG_DIR or os.environ.get("CAPTCHA_DEBUG_DIR", "")).strip()
    if explicit:
        return explicit
    return _default_captcha_debug_root() if CAPTCHA_DEBUG_DEFAULT else ""


def set_captcha_debug_dir(path, force=True):
    """运行时设置点选诊断落盘根目录，无需重启进程。

    force=False 时只在本模块尚未被显式设置过才生效——用于调用方"建议"一个
    目录（如输出到用户指定的输出目录旁），又不覆盖用户自己的设置。
    传空串 + force=True 可彻底关闭落盘。返回生效后的根目录。
    """
    global CAPTCHA_DEBUG_DIR, _DEBUG_DIR_EXPLICIT
    path = (path or "").strip()
    if not force and _DEBUG_DIR_EXPLICIT:
        return CAPTCHA_DEBUG_DIR
    CAPTCHA_DEBUG_DIR = path
    _DEBUG_DIR_EXPLICIT = bool(path)
    return CAPTCHA_DEBUG_DIR


def suggest_captcha_debug_dir(path):
    """由调用方"建议"一个落盘目录（如输出到用户指定的输出目录旁）。

    与 set_captcha_debug_dir(force=False) 的区别：建议值会被后续调用持续更新
    （每换一个输出目录就跟着换），但仍不覆盖用户/环境变量的显式设置。
    """
    global CAPTCHA_DEBUG_DIR, _DEBUG_DIR_SUGGESTED
    if _DEBUG_DIR_EXPLICIT:
        return CAPTCHA_DEBUG_DIR
    p = (path or "").strip()
    if p and p != _DEBUG_DIR_SUGGESTED:
        CAPTCHA_DEBUG_DIR = p
        _DEBUG_DIR_SUGGESTED = p
    return CAPTCHA_DEBUG_DIR


def _captcha_debug_enabled():
    return bool(_captcha_debug_root())


def set_captcha_site_count(n):
    """告知验证码模块本次任务勾选了多少个站点（决定要不要人工介入）。

    由 batch_runner 在开跑前调用一次。站点数 > MANUAL_BATCH_THRESHOLD 视为
    批量处理，全程不要求人工；<= 阈值视为少批量查漏，允许每个对象介入一次。
    """
    global _CAPTCHA_SITE_COUNT
    try:
        _CAPTCHA_SITE_COUNT = max(0, int(n))
    except Exception:
        _CAPTCHA_SITE_COUNT = 0
    return _CAPTCHA_SITE_COUNT


def _manual_allowed():
    """本次任务是否允许人工介入。

    站点数未知（0，即调用方没注入）时保守地允许——宁可多等一次，也不要
    在查漏场景静默丢图。真正跑批量时 batch_runner 一定会注入。
    """
    if _CAPTCHA_SITE_COUNT <= 0:
        return True
    return _CAPTCHA_SITE_COUNT <= MANUAL_BATCH_THRESHOLD


def _prune_debug_dirs(root, keep=None):
    """只保留最近 keep 次点选目录，删掉更旧的，避免长期跑批把磁盘撑满。"""
    keep = CAPTCHA_DEBUG_KEEP if keep is None else keep
    if keep <= 0:
        return
    try:
        if not os.path.isdir(root):
            return
        subs = [d for d in os.listdir(root)
                if os.path.isdir(os.path.join(root, d))]
        if len(subs) <= keep:
            return
        # 目录名以 时间戳 开头（YYYYMMDD_HHMMSS_），字典序即时间序
        for old in sorted(subs)[:len(subs) - keep]:
            shutil.rmtree(os.path.join(root, old), ignore_errors=True)
    except Exception:
        pass


def _captcha_finalize_debug_dir(dbg_dir, outcome):
    """把 pending 目录重命名为最终 outcome，让目录名本身就能筛成败。

    落盘目录在读到 tip/bg 的当下就建（outcome=pending），这样即使后面崩在
    识别里也能留下原图复盘。代价是目录名定格在 pending——不重命名的话，
    跑完一批只能挨个点开 meta.json 才知道哪次成了，失去了"按名筛"的意义。
    """
    if not dbg_dir or outcome in ('pending', 'unknown'):
        return dbg_dir
    root, name = os.path.split(dbg_dir.rstrip(os.sep))
    if not name.endswith('_pending'):
        return dbg_dir
    final = os.path.join(root, name[:-len('_pending')] + '_' + outcome)
    try:
        if os.path.abspath(final) == os.path.abspath(dbg_dir):
            return dbg_dir
        if os.path.isdir(final):
            shutil.rmtree(final, ignore_errors=True)
        os.rename(dbg_dir, final)
        return final
    except Exception as exc:
        _log(f'debug 目录重命名失败 {dbg_dir} -> {final}: {exc!r}')
        return dbg_dir


def _imwrite(path, img):
    """写图片（支持中文路径）→ bool。

    【坑】cv2.imwrite 在 Windows 上对非 ASCII 路径会**静默失败**：底层 fopen
    打不开文件，它返回 False 而不是抛异常。本项目落盘目录几乎必然含中文
    （如 验证码\\captcha_live\\...），裸调 cv2.imwrite 的表现就是"明明开了
    CAPTCHA_DEBUG_DIR，目录建了、meta.json 也有，唯独 png 一张没有"，且外层
    try/except 完全感知不到。统一走 imencode + ndarray.tofile 绕过，并显式
    校验返回值。
    """
    import cv2

    try:
        ext = os.path.splitext(path)[1] or '.png'
        ok, buf = cv2.imencode(ext, img)
        if not ok or buf is None:
            _log(f'图片编码失败: {path}')
            return False
        buf.tofile(path)  # 走 numpy，不经 cv2 的 fopen
        return True
    except Exception as exc:
        _log(f'图片写入失败 {path}: {exc!r}')
        return False


def _write_session_log(dbg_dir, subject, outcome):
    """把本轮会话日志写成人类可读的 log.txt。

    这是排查点选问题的第一入口：按时间顺序列出 取图→识字→定位→分配→点击
    每一步的中间结果，末尾附现场文件清单。对照 outcome 释义就能定位到环节，
    不用去翻 meta.json。
    """
    if not dbg_dir:
        return
    lines = list(getattr(_CAPTCHA_SESSION, 'lines', None) or [])
    try:
        header = [
            f'主体 : {subject}',
            f'结果 : {outcome}',
            f'时间 : {time.strftime("%Y-%m-%d %H:%M:%S")}',
            '',
            '结果释义：',
            '  solved       点完并提交（只代表流程走完，不代表点对）',
            '  no-elements  没找到 tip/bg 图节点 → 站点 DOM 改版',
            '  decode-failed base64 图解码失败',
            '  no-tip       提示字没读出来 → 看 tip.png，图正常则是 OCR 失效',
            '  assign-fail  字框凑不出一对一匹配 → 看 bg_with_boxes.png 红框',
            '  no-size      bg 显示尺寸为 0，无法换算点击坐标',
            '  element-lost 图节点在 OCR 后失效：重定位失败（node没了）或'
            '图已被换（image-changed）→ 旧坐标作废，必须换图重来',
            '  exception    求解过程抛异常（详情见下方栈）',
            '  pending      崩在落盘之前，只有原图没有结论',
            '',
            '本目录文件：tip.png 提示图 / bg.png 背景图 / '
            'bg_with_boxes.png 绿框=命中并点击 红框=未识别 / meta.json 完整中间结果'
            + (' / variants/ 每框 15 路识别变体' if CAPTCHA_DEBUG_VERBOSE else ''),
            '-' * 62,
        ]
        with open(os.path.join(dbg_dir, 'log.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(header + lines) + '\n')
    except Exception as exc:
        _log(f'log.txt 写入失败: {exc!r}')
    # 把落盘位置推给 GUI 日志区——用户排查时最想知道的就是"图在哪"。
    # 放在这里而不是点选开始时：只有真的产生了目录才提示，不刷屏。
    _log(f'诊断明细已落盘（图 + log.txt）→ {dbg_dir}')


def _captcha_debug_dir_for(subject, outcome):
    """生成单次点选的落盘目录：<root>/<主体简名>/<时间戳>_<outcome>/。

    按主体分子目录，跑一批几十家公司时不会挤在一个目录里翻。outcome 放在
    目录名末尾（由 _captcha_finalize_debug_dir 从 pending 改过来），扫一眼
    目录名就知道这次成了还是卡在哪一步。
    """
    root = _captcha_debug_root()
    if not root:
        return None
    safe = re.sub(r'[^\w\u4e00-\u9fff]+', '_', str(subject) or 'subj')[:32].strip('_') or 'subj'
    subj_dir = os.path.join(root, safe)
    folder = os.path.join(subj_dir, f'{time.strftime("%Y%m%d_%H%M%S")}_{outcome}')
    try:
        os.makedirs(folder, exist_ok=True)
        _prune_debug_dirs(subj_dir)
    except Exception as exc:
        _log(f'debug 目录创建失败 {folder}: {exc!r}')
        return None
    return folder


def _get_rapidocr():
    """旧接口兼容壳：自 2026-09 改为 ddddocr 单引擎，此处直接抛错以暴露老调用方。"""
    raise RuntimeError(
        "rapidocr 已废弃，请改用 ddddocr（_rec_text_dddd / _rec_char_variants）"
    )


def _get_dddd_det():
    """ddddocr 目标检测惰性单例（用于定位图中文字块）。"""
    global _DDDD_DET
    if _DDDD_DET is None:
        try:
            import ddddocr
        except ImportError as exc:
            raise RuntimeError("执行信息公开网验证码模式需要先安装 ddddocr") from exc
        _DDDD_DET = ddddocr.DdddOcr(det=True, show_ad=False)
    return _DDDD_DET


def _get_dddd_ocr():
    """ddddocr 字符识别惰性单例（点选 OCR 的唯一引擎）。

    唯一可用的识别实例。注意 det=True 时调用 classification() 会抛
    DDDDOCRError（det / ocr 互斥），故检测/识别必须各建实例。

    模型由 DDDD_OCR_BETA 决定（默认普通模型），切换后旧实例不会自动重建——
    单例只在首次调用时创建，改常量后需重启进程才生效。
    """
    global _DDDD_OCR
    if _DDDD_OCR is None:
        try:
            import ddddocr
        except ImportError as exc:
            raise RuntimeError("执行信息公开网验证码模式需要先安装 ddddocr") from exc
        _DDDD_OCR = ddddocr.DdddOcr(beta=DDDD_OCR_BETA, show_ad=False)
    return _DDDD_OCR


def _reset_ocr_ranges(ocr):
    """把 ddddocr 的字符集范围恢复成"全字符集"，且必须是 O(N) 的。

    为什么不能沿用 set_ranges(完整 charset)：ddddocr 的
    CharsetManager._update_valid_indices 对每个候选字都跑一次
    `self.charset.index(item)` —— 线性扫描 6000+ 字的列表。传 4 个候选字
    是 4×6000，微秒级；传完整字符集就成了 6000×6000 ≈ 3600 万次字符串比较，
    实测 3 秒一次。而点选流程每次 OCR 前都要重设字符集（否则被上次的限定
    污染），提示字那一步一跑就是 9 秒——页面在这期间刷新 DOM，回头读
    rect.size 时元素早被换掉（ElementLostError）。这是个隐蔽的性能 →
    稳定性连锁故障，别再改回 set_ranges(全量)。

    直接把 charset_range 清空，引擎自身就会走"valid index = 全索引"的默认
    分支（见 OCREngine.predict：charset_range 为空时调 _update_valid_indices），
    语义与传全字符集完全等价，代价是 O(N)。
    """
    try:
        cm = ocr.ocr_engine.charset_manager
        if getattr(cm, 'charset_range', None):
            cm.charset_range = []
            cm._update_valid_indices()
        # 幂等：已经是全字符集时也必须 return，否则会掉进下面兜底的
        # set_ranges(全量)，把 8211 项重新塞回去——下一轮再清空，来回震荡，
        # 表现为"一次 1.9s、一次 0.04s"交替（踩过一次，别改回去）。
        return
    except Exception:
        pass
    # 兜底：内部结构变了就退回官方接口（慢，但至少结果对）
    try:
        ocr.set_ranges(ocr.ocr_engine.charset_manager.charset)
    except Exception:
        pass


def _rec_text_dddd(img_bgr, candidates=None):
    """用 ddddocr 做字符识别 → (text, score)。

    candidates：候选字集合（来自提示图）。候选集只做识别结果的硬过滤，不能
    参与 set_ranges 或候选集内的概率归一化；否则模型认错时也会被强行改成某个
    目标字。调用方拿不到候选字时应放弃本次验证码并刷新。

    每次调用都用 _reset_ocr_ranges() 恢复完整字集，避免上一次调用的状态污染。
    """
    import cv2

    if img_bgr is None or img_bgr.size == 0:
        return "", 0.0
    if img_bgr.ndim == 2:
        img_bgr = cv2.cvtColor(img_bgr, cv2.COLOR_GRAY2BGR)
    ok, buf = cv2.imencode('.png', img_bgr)
    if not ok:
        return "", 0.0

    global _DDDD_OCR_FAILED
    try:
        ocr = _get_dddd_ocr()
        # 始终使用完整字集；提示字只在模型返回后过滤，禁止强制候选匹配。
        _reset_ocr_ranges(ocr)
        res = ocr.classification(buf.tobytes(), probability=True)
    except Exception as exc:
        if not _DDDD_OCR_FAILED:
            _DDDD_OCR_FAILED = True
            _log(f'ddddocr 字符识别异常，该路投票将失效: {exc!r}')
        return "", 0.0

    if not isinstance(res, dict):
        # 旧版 ddddocr 兼容：classification 不带 probability 时直接返回 str
        text = res or ""
    else:
        text = (res.get("text") or "").strip()
    if not text:
        return "", 0.0

    chars = re.findall(r'[一-鿿]', text)
    if not chars:
        return "", 0.0
    if candidates:
        # 模型原始结果不是目标字时整条作废，避免形近字占用目标字票位。
        if any(ch not in candidates for ch in chars):
            return "", 0.0
    if len(chars) == 1:
        score = float(res.get("confidence", DDDD_VOTE_SCORE)) if isinstance(res, dict) else DDDD_VOTE_SCORE
        if score < DDDD_REJECT_BELOW:
            return "", 0.0
        return chars[0], score
    # 多字：把 confidence 当作整条结果的可信度，扣字数加权
    score = float(res.get("confidence", DDDD_VOTE_SCORE * 0.7)) if isinstance(res, dict) else DDDD_VOTE_SCORE * 0.7
    return "".join(chars), score


def _decode_captcha_img(img_bytes):
    """解码验证码图片；PNG 带透明通道时合成到白底（否则透明区变黑导致 OCR 失败）。"""
    import cv2
    import numpy as np

    arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
    if arr is None:
        return None
    if arr.ndim == 3 and arr.shape[2] == 4:
        alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
        rgb = arr[:, :, :3].astype(np.float32)
        white = np.full_like(rgb, 255.0)
        arr = (rgb * alpha + white * (1 - alpha)).astype(np.uint8)
    return arr


def _rec_text(img_bgr, candidates=None):
    """兼容入口：自 2026-09 起所有识别走 ddddocr。

    旧实现是 rapidocr.text_recognizer(...)，外部脚本（bench/diag/test_*）
    仍可能 import 此名。直接转发到 _rec_text_dddd 即可，签名/返回值一致。
    """
    return _rec_text_dddd(img_bgr, candidates)


def _read_tip_chars(tip_bgr):
    """识别提示图中的目标字串（单行从左到右，仅保留汉字）。

    对多条预处理路线各识别一次，取【汉字数最多、其次置信度最高】的结果。
    提示图（4 大字 + 干扰线/圈）整图识别 ddddocr 实测不稳，但多路投票（OTSU
    + 2x 放大 + 灰度反转）能在主字形上稳出 4 个汉字。少数样例只能出 3 字，
    此时 _detect_char_positions 也无能为力——提示图识别是整套点选的根，
    出错就该走刷新路径。

    注意：不要改成"先切分成单字再逐字识别"。实测该提示图列方向粘连，
    投影切分只能切出 1 段；强行 4 等分会把字形切坏（第 2 字置信度掉到
    0.068、第 3 字误判成"黏"）。提示字一旦认错，后面定位全盘皆错。
    """
    import cv2

    if tip_bgr is None:
        return []

    def _n_chars(text):
        return len(re.findall(r'[一-鿿]', text))

    best_text, best_score = "", 0.0

    def _try(img):
        nonlocal best_text, best_score
        text, score = _rec_text(img)
        if (_n_chars(text), score) > (_n_chars(best_text), best_score):
            best_text, best_score = text, score

    _try(tip_bgr)
    gray = cv2.cvtColor(tip_bgr, cv2.COLOR_BGR2GRAY)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    for img in (otsu, cv2.resize(otsu, None, fx=2, fy=2,
                                 interpolation=cv2.INTER_CUBIC)):
        _try(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))

    return re.findall(r'[一-鿿]', best_text)


def _kmeans_char_mask(crop, clusters=None):
    """K-means 按颜色聚类 + 连通域筛选，取出最像"字"的像素作为掩码。

    相较旧版（固定 4 簇 + 只按饱和度挑簇），针对"实景底图 + 彩色艺术字"加固：
      1. 固定 RNG 种子：cv2.kmeans 的 PP_CENTERS 初始化带随机性，实测同一张
         字框重复跑，前景占比会在 0.146~0.305 间跳变——这会让识别结果随机，
         同一张验证码两次求解结论不同，务必固定；
      2. 簇数自适应 6~8：底图颜色种类多时，固定 4 簇会把花瓣与字并进同一簇；
      3. 剔除绿色系：叶/茎在 HSV 里同样高饱和，是最常见的误判源；
      4. 连通域打分：字 = 少量中等连通域；花瓣/叶子 = 一大片或一堆碎点。
    """
    import cv2
    import numpy as np

    h, w = crop.shape[:2]
    total = h * w
    if clusters is None:
        clusters = int(np.clip(total // 1200, 6, 8))

    cv2.setRNGSeed(0)  # 固定 kmeans 初始化，消除上条第 1 点的随机性
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(
        hsv, clusters, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )
    labels = labels.reshape((h, w))
    centers = centers.astype(np.int32)

    # 字的连通域面积区间（按裁图面积取比例，兼容不同字号）
    min_area = max(30, int(total * 0.004))
    max_area = max(min_area + 1, int(total * 0.55))

    best_k, best_score = None, None
    for k in range(clusters):
        mask_k = ((labels == k).astype(np.uint8)) * 255
        frac = float((mask_k > 0).mean())
        if not (0.03 < frac < 0.70):
            continue
        hue, sat, _ = (int(c) for c in centers[k])
        # 绿/青色系（叶、茎）：OpenCV 的 H 取值 0~179，35~85 大致是绿到青
        if 35 <= hue <= 85 and sat >= 40:
            continue
        n_comp, _, stats, _ = cv2.connectedComponentsWithStats(mask_k, 8)
        if n_comp <= 1:
            continue
        areas = stats[1:, cv2.CC_STAT_AREA]
        keep = areas[(areas >= min_area) & (areas <= max_area)]
        if not len(keep):
            continue
        cover = float(keep.sum()) / total
        # 覆盖率只作为软约束：字通常占 15%~35%，过低=碎点，过高=大片背景。
        # 注意不要让覆盖率主导——背景往往占比最大，主导了就会选中背景。
        frac_score = 1.0 - min(1.0, abs(cover - 0.25) / 0.25)
        n_score = 1.0 / (1.0 + abs(len(keep) - 2))        # 字通常 1~3 块部件
        score = (sat / 255.0) * 2.0 + frac_score * 1.2 + n_score * 0.6
        if best_score is None or score > best_score:
            best_score, best_k = score, k

    if best_k is None:
        return None

    # 选中簇再做一次连通域过滤，剔掉残留的花瓣大块与碎点
    mask = ((labels == best_k).astype(np.uint8)) * 255
    n_comp, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    out = np.zeros_like(mask)
    for i in range(1, n_comp):
        a = int(stats[i, cv2.CC_STAT_AREA])
        if min_area <= a <= max_area:
            out[lab == i] = 255
    return out if out.any() else mask


def _mask_deskew_angle(mask):
    """由掩码估计文字旋转角（归一化到 ±45°）。

    OpenCV ≥4.5 的 minAreaRect 把 angle 规范到 [0, 90)，且 w 恒为"较水平的
    那条边"，两种情形要分开还原：
      * w >= h（字横躺）→ 真实倾角 = +angle
      * w <  h（字竖立）→ 真实倾角 = angle - 90，即 -(90 - angle)

    旧代码这里写的是 angle += 90，导致所有【向上倾斜】的字被多转 90°，
    纠偏后反而更歪。实测 OpenCV 4.10：真实 -30° 会算成 +60.5°，
    真实 -20° 会算成 +70.2°——这正是艺术字验证码识别率差的首要原因
    （几乎正的字不受影响，所以旧版偶尔能蒙对）。
    """
    import cv2
    import numpy as np

    ys, xs = np.where(mask > 0)
    if len(xs) < 50:
        return 0.0
    pts = np.column_stack([xs, ys]).astype(np.float32)
    (_, _), (w, h), angle = cv2.minAreaRect(pts)
    if w < h:
        angle -= 90.0  # 旧代码为 += 90，见上方说明
    if angle > 45:
        angle -= 90
    elif angle < -45:
        angle += 90
    return float(angle)


def _rotate_img(img, angle, border):
    import cv2

    h, w = img.shape[:2]
    mat = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, mat, (w, h), borderValue=border)


def _mask_to_bw(mask, denoise=True):
    """掩码 → 黑字白底图（可选去噪/膨胀 → 裁剪到内容 → 留白边）。

    denoise 针对花丛/实景底图下掩码的两个典型毛病：
      1. 开运算清掉孤立碎点（花瓣噪点），闭运算补上笔画内的小孔洞；
      2. 轻度膨胀接续被背景"咬断"的笔画——艺术字笔画细，在复杂背景上
         常断成数段，接续后识别率明显提升。
    """
    import cv2
    import numpy as np

    if denoise:
        m = mask.copy()
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        m = cv2.dilate(m, np.ones((2, 2), np.uint8), iterations=1)
        if m.any():
            mask = m

    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None
    content = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    out = np.full_like(content, 255)
    out[content > 0] = 0
    return cv2.copyMakeBorder(out, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)


def _rec_char_variants(crop, candidates=None):
    """对单个字框做多路预处理 + ddddocr 投票，返回 {字: 最高分}。

    candidates: 候选字集合（提示字列表），只过滤模型直接识别出的结果；不会
    限定 softmax，也不会使用候选集归一化兜底。

    多路投票保留 4 类变体：
      - 原图：让 ddddocr 看到完整背景信息（色块、纹理有时反而是特征）；
      - K-means 掩码 → 黑字白底：去背景、给识别模型最舒服的"印刷体"输入；
      - 掩码 ±90° 按 15° 步长暴力扫描：单字方块汉字 minAreaRect 估的
        倾角存在 90° 象限歧义（见旧版 docstring），暴力扫描最稳；
      - 每路都走一次 _rec_text_dddd（完整字集 + probability=True）。

    比旧版省掉 1/2 推理量：旧 rapidocr + ddddocr 双引擎=每路 2 次推理，
    现在只有 ddddocr 一路，识别时间从 ~0.4s/框 → ~0.05s/框。
    """
    import cv2

    votes = {}
    cropped_for_dump = []  # 调试落盘：原图/掩码/角度变体

    def vote(img, tag):
        if img is None or getattr(img, "size", 0) == 0:
            return
        cropped_for_dump.append((tag, img))
        text, score = _rec_text_dddd(img, candidates)
        chars = re.findall(r'[一-鿿]', text)
        # 投票接受"单字高分"或"多字首位"，但多字首位 score 衰减，避免
        # ddddocr 一次返回 2 字时把第二个字当框归属目标。
        if len(chars) == 1 and score >= DDDD_REJECT_BELOW:
            ch = chars[0]
            if score > votes.get(ch, 0):
                votes[ch] = score

    # 1) 原图（保留色块信息）
    vote(crop, 'raw')

    mask = _kmeans_char_mask(crop)
    if mask is not None:
        bw = _mask_to_bw(mask)
        # 2) 掩码
        vote(bw, 'bw')

        # 3) 暴力角度扫描：±90° 按 15° 步长；只扫掩码（背景已去，多角度仍要再算）
        for ang in range(-90, 91, 15):
            vote(_mask_to_bw(_rotate_img(mask, ang, 0)), f'bw_rot{ang:+d}')

    # 没有直接识别出目标字就保持空票；上层会判定本图失败并刷新。
    return votes, cropped_for_dump


def _assign_click_boxes(targets, box_votes, min_score=DDDD_ASSIGN_MIN_SCORE):
    """按提示字顺序为每个字分配一个字框（一对一，总分最大）。

    targets: 有序目标字列表；box_votes: [((cx, cy), {字: 分数}), ...]
    返回 [(cx, cy), ...]（与 targets 同序），分配失败返回 None。
    """
    from itertools import permutations

    n = len(box_votes)
    k = len(targets)
    if n < k:
        return None
    best_assign, best_total = None, 0.0
    for idxs in permutations(range(n), k):
        total = 0.0
        ok = True
        for ch, bi in zip(targets, idxs):
            score = box_votes[bi][1].get(ch, 0.0)
            if score < min_score:
                ok = False
                break
            total += score
        if ok and total > best_total:
            best_total = total
            best_assign = idxs
    if best_assign is None:
        return None
    return [box_votes[bi][0] for bi in best_assign]


def _detect_char_positions(bg_bgr, targets):
    """ddddocr det 定位字框 → 逐框多路识别投票 → 按提示字顺序分配点击坐标。

    targets 会作为结果过滤条件传给识别环节：只有模型直接识别出提示字且达到
    置信度门槛才会计票。无法完成高置信度的一对一分配时返回 None，由上层刷新
    验证码，不用候选集概率强行猜测。

    返回 (assignment, boxes, box_votes, box_dumps)。box_dumps 始终填充
    （每框的 raw / bw / bw_rotXX 多路变体图），生产路径可选落盘，
    离线测试单元（test_captcha_click.py）则直接用其写 review/。
    """
    import cv2

    _, buf = cv2.imencode('.png', bg_bgr)
    boxes = _get_dddd_det().detection(buf.tobytes())
    candidates = set(targets) if targets else None
    box_votes = []
    box_dumps = []
    for x1, y1, x2, y2 in boxes:
        crop = bg_bgr[max(0, y1 - 4):y2 + 4, max(0, x1 - 4):x2 + 4]
        votes, dump = _rec_char_variants(crop, candidates)
        box_votes.append((((x1 + x2) / 2, (y1 + y2) / 2), votes))
        box_dumps.append(((x1, y1, x2, y2), dump))
    assignment = _assign_click_boxes(targets, box_votes)
    return assignment, boxes, box_votes, box_dumps


def _tianai_popup(page, timeout=8):
    """等待天爱验证码弹窗出现并返回容器元素。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        popup = page.ele('css:.tianai-captcha-ui-overlay', timeout=0.5)
        if popup:
            return popup
        time.sleep(0.3)
    return None


def _tianai_content_ready(popup, timeout=10):
    """等待验证码图片真正加载完成。

    弹窗先渲染加载骨架（#tianai-captcha-loading 转圈），图片异步加载、切换较慢；
    图片就位前识别类型/求解都会扑空。
    注意：DrissionPage 的 ele() 找不到时返回 falsy 的 NoneElement（不是 None），
    必须用 truthiness 判断，对 NoneElement 访问属性会抛 ElementNotFoundError。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            loading = popup.ele('css:#tianai-captcha-loading', timeout=0.3)
            if loading and loading.states.is_displayed:
                time.sleep(0.3)
                continue
            bg = popup.ele('css:#tianai-captcha-slider-bg-img', timeout=0.5)
            if bg and bg.attr('src'):
                time.sleep(0.3)  # 图片就位后再留一点渲染时间
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _tianai_still_showing(page):
    """弹窗是否仍显示：每次重新查找容器（刷新可能重建弹窗），短暂消失二次确认。"""

    def _find_visible():
        try:
            cur = page.ele('css:.tianai-captcha-ui-overlay', timeout=0.5)
            return bool(cur and cur.states.is_displayed)
        except Exception:
            return False

    if _find_visible():
        return True
    time.sleep(1)  # 可能正处于刷新重建瞬间，误判为通过会浪费整轮机会
    return _find_visible()


def _tianai_mode(popup):
    """识别当前弹窗类型：click=点选文字，slider=滑块拼图。

    实测 DOM：点选型独有 #tianai-captcha-click-track-font；
    滑块型独有把手 #tianai-captcha-slider-move-btn（提示文字为
    "向右拖动滑块填充拼图"，text= 精确匹配"拖动滑块"匹配不到，不能用）。
    """
    try:
        tip = popup.ele('css:#tianai-captcha-click-track-font', timeout=1)
        if tip and tip.states.is_displayed:
            return 'click'
    except Exception:
        pass
    try:
        if popup.ele('css:#tianai-captcha-slider-move-btn', timeout=1):
            return 'slider'
    except Exception:
        pass
    # 无法判定时默认按点选处理（该站以点选为主）
    return 'click'


def _tianai_refresh(page, popup):
    """点击刷新按钮换一张验证码。

    该站切换新图较慢：点击后轮询背景图 src 变化（最多 8 秒）再返回，
    避免上一张还没换掉就开始求解旧图。刷新可能重建弹窗容器，
    轮询时每次重新查找 overlay，不依赖旧元素引用。
    """
    try:
        btn = popup.ele('css:#tianai-captcha-slider-refresh-btn', timeout=2) \
            or popup.ele('css:.refresh-btn', timeout=2)
        if not btn:
            return False
        bg = popup.ele('css:#tianai-captcha-slider-bg-img', timeout=1)
        old_src = bg.attr('src') if bg else None
        btn.click()
        deadline = time.time() + 8
        while time.time() < deadline:
            time.sleep(0.3)
            cur = page.ele('css:.tianai-captcha-ui-overlay', timeout=0.5)
            if not cur:
                continue  # 容器重建瞬间
            img = cur.ele('css:#tianai-captcha-slider-bg-img', timeout=0.5)
            new_src = img.attr('src') if img else None
            if new_src and new_src != old_src:
                time.sleep(0.3)  # 新图就位，稍等渲染
                return True
        return True  # 点击已发出，没等到换图也放行，交给下一轮判断
    except Exception:
        return False


def _bg_img_signature(img):
    """bg 图指纹（src 的 md5），用来判断"还是不是同一张验证码图"。

    天爱验证码会在超时、刷新或被提交后替换图片节点，此时先前算好的字坐标
    全部作废——再点就是点错图，比不点更糟。所以任何"元素失效后重新定位"
    的动作都必须先过这一关，指纹不一致就放弃、交外层刷新重来。
    """
    if not img:
        return None
    raw = None
    try:
        raw = _get_base64_img_bytes(img)
    except Exception:
        raw = None
    if not raw:
        try:
            raw = (img.attr('src') or '').encode('utf-8', 'ignore')
        except Exception:
            return None
    if not raw:
        return None
    import hashlib

    return hashlib.md5(raw).hexdigest()


def _bg_img_geometry(img, bg_bgr):
    """读 (nat_w, nat_h, disp_w, disp_h)；拿不到的维度一律返回 0，不抛异常。

    元素在这里失效是"预期内的常见情况"（OCR 要跑近 1 秒，期间页面可能局部
    刷新把 img 节点换掉），所以本函数只负责采集、不判断，由调用方决定是
    重定位还是放弃。
    """
    nat_w = nat_h = 0
    try:
        nat_w = img.run_js('return this.naturalWidth;') or 0
        nat_h = img.run_js('return this.naturalHeight;') or 0
    except Exception:
        nat_w = nat_h = 0
    if not nat_w or not nat_h:
        # 退化用解码后的像素尺寸（天爱 bg 通常 1:1 显示，够用）
        nat_w, nat_h = bg_bgr.shape[1], bg_bgr.shape[0]

    disp_w = disp_h = 0
    try:
        disp_w, disp_h = img.rect.size
    except Exception:
        pass
    return nat_w, nat_h, disp_w, disp_h


def _bg_img_alive(img):
    """探测元素引用是否还有效：凡是走 nodeId 的操作都会立刻暴露失效。"""
    try:
        img.rect.size
        return True
    except Exception:
        return False


def _relocate_bg_img(popup, expect_sig):
    """元素失效后重新定位 bg 图，并确认它还是同一张验证码图。

    返回 (img, None)=可继续用；(None, 原因)=必须放弃本张：
      relocate-failed  弹窗或图节点都没了（多半已提交 / 超时关闭）
      image-changed    图被换了一张，之前算的坐标作废
    """
    img = None
    try:
        img = popup.ele('css:#tianai-captcha-slider-bg-img', timeout=2)
    except Exception:
        img = None
    if not img:
        return None, 'relocate-failed'

    sig = _bg_img_signature(img)
    if expect_sig and sig and sig != expect_sig:
        return None, 'image-changed'
    return img, None


def _solve_tianai_word_click(page, popup):
    """点选文字：OCR 提示字 → 定位大字 → 按序点击 → 确定。

    任何返回 False 的子步都会顺手把这次弹窗的 tip/bg/识别详情落盘（开了
    CAPTCHA_DEBUG_DIR 时），便于事后复盘到底卡在"提示字读不出/字框没找全/
    投票分太低/分配失败"哪一环，而不是只能看到"solved=False, 刷新了"。

    每一点都会留下诊断痕迹，出问题时按这个顺序看现场（目录里都有）：
      1. log.txt        逐步日志，最先看这个
      2. bg_with_boxes.png  原图 + det 框（绿=命中并且被点击，红=没认出）
      3. meta.json      机器可读的完整中间结果
      4. variants/      每框 15 路识别变体（需 CAPTCHA_DEBUG_VERBOSE=1）

    返回值语义不变：True=已点完确认按钮（外部不区分"点对了"还是"点错了"，
    通过 _court_result_signal 统一判断）。
    """
    import cv2

    subject = _subject_name_safe(page)
    outcome = 'unknown'
    dbg_dir = None

    # 下面每一步都可能提前 return，而 finally 里的落盘要用到这些中间结果。
    # 统一在这里初始化为"空"，落盘代码就不必逐个做 `'x' in dir()` 判断——
    # 那种写法本身就脆弱：一旦某处漏判就是 UnboundLocalError，而它发生在
    # finally 里会被 except 吞掉，表现成"落盘只有 meta.json、没有图"。
    tip_bgr = bg_bgr = None
    targets = None
    boxes, box_votes, box_dumps = [], [], []
    assignment = None

    # 开启本轮会话日志：此后所有 _log 也会进这个缓冲，结束时统一写 log.txt。
    # 用 threading.local 隔离，批量多线程跑时各公司的日志不会串台。
    _CAPTCHA_SESSION.lines = []
    _CAPTCHA_SESSION.dir = None
    _log(f'点选开始  主体={subject}')

    try:
        tip_img = popup.ele('css:#tianai-captcha-tip-img', timeout=3)
        bg_img = popup.ele('css:#tianai-captcha-slider-bg-img', timeout=3)
        if not (tip_img and bg_img):
            _log('取图失败：未找到 tip / bg 图节点（tip=%s bg=%s）→ '
                 '站点 DOM 可能已改版' % (bool(tip_img), bool(bg_img)))
            outcome = 'no-elements'
            return False

        tip_bgr = _decode_captcha_img(_get_base64_img_bytes(tip_img))
        bg_bgr = _decode_captcha_img(_get_base64_img_bytes(bg_img))
        if tip_bgr is None or bg_bgr is None:
            _log('取图失败：tip/bg 解码为空（tip_ok=%s bg_ok=%s）→ base64 src 异常'
                 % (tip_bgr is not None, bg_bgr is not None))
            outcome = 'decode-failed'
            return False

        # 落盘：原图（不依赖后续识别成败，先落再算）
        if _captcha_debug_enabled():
            dbg_dir = _captcha_debug_dir_for(subject, 'pending')
            if dbg_dir:
                _imwrite(os.path.join(dbg_dir, 'tip.png'), tip_bgr)
                _imwrite(os.path.join(dbg_dir, 'bg.png'), bg_bgr)
        _log(f'取图成功  tip={tip_bgr.shape[1]}x{tip_bgr.shape[0]} '
             f'bg={bg_bgr.shape[1]}x{bg_bgr.shape[0]}')

        # 尺寸与图指纹都在这里"趁热"缓存：OCR 要跑近 1 秒，等算完再回头读
        # rect.size，元素可能已被页面局部刷新换掉（ElementLostError）。
        bg_sig = _bg_img_signature(bg_img)
        nat_w, nat_h, disp_w, disp_h = _bg_img_geometry(bg_img, bg_bgr)

        targets = _read_tip_chars(tip_bgr)
        if not targets:
            _log('提示字识别为空 → 放弃这张图刷新重试。'
                 '看同目录 tip.png 确认提示图是否正常，'
                 '若图正常则是 ddddocr 对这张艺术字失效')
            outcome = 'no-tip'
            return False
        _log(f'提示字识别完成  targets={"".join(targets)}（{len(targets)} 字）')

        assignment, boxes, box_votes, box_dumps = _detect_char_positions(
            bg_bgr, targets
        )
        _log(f'字框定位完成  det 找到 {len(boxes)} 个框，需匹配 {len(targets)} 个目标字')
        for i, ((cx, cy), votes) in enumerate(box_votes):
            if votes:
                top = max(votes.items(), key=lambda kv: kv[1])
                mark = '✓命中' if top[0] in targets else '✗认成非目标字'
                _log(f'  框{i} box={list(boxes[i])} 中心=({cx:.0f},{cy:.0f}) '
                     f'{mark} 最佳={top[0]} {top[1]:.3f} 全票='
                     + str({k: round(v, 3) for k, v in votes.items()}))
            else:
                _log(f'  框{i} box={list(boxes[i])} 中心=({cx:.0f},{cy:.0f}) '
                     f'✗未识别（15 路变体都没投出候选字）')

        if not assignment:
            _log(f'分配失败：{len(boxes)} 个框凑不出 {len(targets)} 个目标字的一对一匹配')
            for ch in targets:
                cand = [(i, round(votes.get(ch, 0), 3))
                        for i, (_, votes) in enumerate(box_votes)
                        if votes.get(ch, 0) > 0]
                _log(f'  目标字「{ch}」候选框={cand if cand else "无（整图都没认出这个字）"}')
            outcome = 'assign-fail'
            return False
        _log('分配成功  ' + '  '.join(
            f'{ch}→({x:.0f},{y:.0f})' for ch, (x, y) in zip(targets, assignment)))

        # 点击前先确认图节点还活着：OCR 期间页面可能局部刷新把它换掉。
        # 失效就重新定位，并用 src 指纹确认图没被换（换了就绝不能接着点）。
        if not (disp_w and disp_h) or not _bg_img_alive(bg_img):
            fixed, why = _relocate_bg_img(popup, bg_sig)
            if fixed is None:
                _log(f'bg 元素失效且无法恢复（{why}）→ 放弃这张图，交外层刷新重试')
                outcome = 'element-lost'
                return False
            _log(f'bg 元素失效 → 已重新定位（{why or "补读尺寸"}）')
            bg_img = fixed
            nw, nh, dw, dh = _bg_img_geometry(bg_img, bg_bgr)
            if dw and dh:
                nat_w, nat_h, disp_w, disp_h = nw, nh, dw, dh
            elif not (disp_w and disp_h):
                _log('bg 显示尺寸读不到（元素持续失效）→ 无法换算点击坐标')
                outcome = 'no-size'
                return False

        # 自然像素 → 页面显示像素 的缩放
        scale_x, scale_y = disp_w / nat_w, disp_h / nat_h
        _log(f'坐标换算  natural={nat_w}x{nat_h} display={disp_w}x{disp_h} '
             f'scale=({scale_x:.3f},{scale_y:.3f})')

        # assignment 已按提示字顺序排好，直接按序点击
        for ch, (cx, cy) in zip(targets, assignment):
            px, py = cx * scale_x, cy * scale_y
            _log(f'点击「{ch}」 原图({cx:.0f},{cy:.0f}) → 页面({px:.0f},{py:.0f})')
            try:
                bg_img.click.at(px, py)
            except Exception as click_exc:
                # 中途失效：重新定位后重试这一个字（已点中的字不受影响）
                fixed, why = _relocate_bg_img(popup, bg_sig)
                if fixed is None:
                    _log(f'点击「{ch}」时元素失效且无法恢复（{why}）：{click_exc!r}')
                    outcome = 'element-lost'
                    return False
                _log(f'点击「{ch}」时元素失效 → 已重新定位（同一张图），重试该字')
                bg_img = fixed
                try:
                    bg_img.click.at(px, py)
                except Exception as retry_exc:
                    _log(f'重试点击「{ch}」仍失败：{retry_exc!r}')
                    outcome = 'element-lost'
                    return False
            time.sleep(0.4)

        time.sleep(0.5)
        try:
            confirm = popup.ele('css:.click-confirm-btn', timeout=2)
            if confirm and confirm.states.is_displayed:
                confirm.click()
                _log('已提交确认按钮')
            else:
                _log('未找到确认按钮（.click-confirm-btn）→ 可能站点改版或已自动提交')
        except Exception as exc:
            # 字已经点完了，提交失败只记不回滚——外层结果判定会给出真实结论
            _log(f'提交确认按钮异常（4 个字已点完，不影响判定）：{exc!r}')
        time.sleep(2)
        outcome = 'solved'
        _log('点选流程走完，等待外部结果判定（注意：solved 只代表点完，不代表点对）')
        return True
    except Exception as exc:
        _log('点选异常 ' + repr(exc))
        _log(traceback.format_exc())
        outcome = 'exception'
        return False
    finally:
        # 落盘：识别详情（命中/未命中都写）。整块再包一层 try/finally，
        # 保证无论落盘成败，线程本地的会话缓冲都会被清掉，不带到下个点选。
        try:
            if dbg_dir is None and _captcha_debug_enabled():
                dbg_dir = _captcha_debug_dir_for(subject, outcome)
            if dbg_dir:
                try:
                    meta = {
                        'subject': subject,
                        'outcome': outcome,
                        'targets': targets,
                        'det_boxes': [list(b) for b in boxes],
                        'assignments': dict(zip(targets or [], assignment or [])),
                        'box_votes': [
                            {
                                'center': list(p),
                                'votes': {k: round(v, 4) for k, v in votes.items()},
                            }
                            for p, votes in box_votes
                        ],
                    }
                    with open(os.path.join(dbg_dir, 'meta.json'), 'w',
                              encoding='utf-8') as f:
                        json.dump(meta, f, ensure_ascii=False, indent=2)
                    # 变体只给调算法的人看：6 框 × 15 路 ≈ 96 个文件，
                    # 默认关（CAPTCHA_DEBUG_VERBOSE=1 才开），否则跑一批就爆。
                    if box_dumps and CAPTCHA_DEBUG_VERBOSE:
                        var_dir = os.path.join(dbg_dir, 'variants')
                        os.makedirs(var_dir, exist_ok=True)
                        for bi, (box, dump) in enumerate(box_dumps):
                            bdir = os.path.join(var_dir, f'box{bi}')
                            os.makedirs(bdir, exist_ok=True)
                            _imwrite(os.path.join(bdir, 'crop.png'),
                                     bg_bgr[max(0, box[1] - 4):box[3] + 4,
                                            max(0, box[0] - 4):box[2] + 4])
                            for tag, img in dump:
                                _imwrite(os.path.join(bdir, f'{tag}.png'), img)
                    # 画框（命中与未命中分色）便于肉眼比对
                    if bg_bgr is not None:
                        vis = bg_bgr.copy()
                        hit_centers = {(int(x), int(y))
                                       for x, y in (assignment or [])}
                        for bi, (box, _) in enumerate(box_dumps):
                            hit = (int((box[0] + box[2]) / 2),
                                   int((box[1] + box[3]) / 2)) in hit_centers
                            color = (0, 255, 0) if hit else (0, 0, 255)
                            cv2.rectangle(vis, (box[0], box[1]),
                                          (box[2], box[3]), color, 2)
                            cv2.putText(vis, str(bi), (box[0], box[1] - 4),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        _imwrite(os.path.join(dbg_dir, 'bg_with_boxes.png'), vis)
                except Exception as dump_exc:
                    _log('debug 落盘失败', repr(dump_exc))
                dbg_dir = _captcha_finalize_debug_dir(dbg_dir, outcome)
                _write_session_log(dbg_dir, subject, outcome)
        finally:
            _CAPTCHA_SESSION.lines = None
            _CAPTCHA_SESSION.dir = None


def _subject_name_safe(page):
    """从页面兜底抓主体名（不依赖外部 subject 字典，专给 debug log 用）。"""
    try:
        cur = page.ele('css:input.search-input, input[placeholder*="姓名"]', timeout=0.5)
        if cur:
            v = (cur.value or '').strip()
            if v:
                return v
    except Exception:
        pass
    try:
        return (page.title or '')[:32]
    except Exception:
        return ''


def _find_tianai_gap_x(piece_bytes, bg_bytes):
    """在背景图中定位拼图缺口位置，返回 (缺口x, 拼图可见左缘透明边距)（背景自然像素）。

    拼图块 PNG 带大片透明边，直接整图匹配会把透明边也当特征，
    先按 alpha 裁剪到实际拼图再 Canny 边缘匹配；透明左边距也要返回，
    拖动距离 = (缺口x - 透明边距)×缩放 - 拼图元素当前偏移。
    失败返回 (None, None)。
    """
    import cv2
    import numpy as np

    bg = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)
    piece = cv2.imdecode(np.frombuffer(piece_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
    if bg is None or piece is None or bg.size == 0 or piece.size == 0:
        return None, None
    margin = 0
    if piece.ndim == 3 and piece.shape[2] == 4:
        ys, xs = np.where(piece[:, :, 3] > 32)
        if not len(xs):
            return None, None
        margin = int(xs.min())
        piece = piece[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    if piece.ndim == 3 and piece.shape[2] == 4:
        piece = piece[:, :, :3]
    elif piece.ndim == 2:
        piece = cv2.cvtColor(piece, cv2.COLOR_GRAY2BGR)
    if piece.shape[0] >= bg.shape[0] or piece.shape[1] >= bg.shape[1]:
        return None, None

    piece_edge = cv2.Canny(cv2.cvtColor(piece, cv2.COLOR_BGR2GRAY), 100, 200)
    bg_edge = cv2.Canny(cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY), 100, 200)
    result = cv2.matchTemplate(bg_edge, piece_edge, cv2.TM_CCOEFF_NORMED)
    _, _, _, max_loc = cv2.minMaxLoc(result)
    return max_loc[0], margin


def _solve_tianai_slider(page, popup):
    """滑块拼图：cv2 匹配缺口位置，拖动把手。

    实测 DOM：背景 #tianai-captcha-slider-bg-img、拼图块
    #tianai-captcha-slider-move-img、把手 #tianai-captcha-slider-move-btn。
    """
    bg_img = popup.ele('css:#tianai-captcha-slider-bg-img', timeout=3)
    piece_img = popup.ele('css:#tianai-captcha-slider-move-img', timeout=3)
    handle = popup.ele('css:#tianai-captcha-slider-move-btn', timeout=3)
    if not (bg_img and piece_img and handle):
        return False

    bg_bytes = _get_base64_img_bytes(bg_img)
    piece_bytes = _get_base64_img_bytes(piece_img)
    if not (bg_bytes and piece_bytes):
        return False

    gap_x, piece_margin = _find_tianai_gap_x(piece_bytes, bg_bytes)
    if gap_x is None:
        return False

    # 与点选同理：读尺寸时元素可能已被页面换掉。这里安静返回 False 让外层
    # 刷新换图重试即可，别把 ElementLostError 的整段栈刷到 GUI 日志区。
    try:
        nat_w = bg_img.run_js('return this.naturalWidth;') or 0
        disp_w = bg_img.rect.size[0]
    except Exception as exc:
        _log(f'滑块：读图尺寸时元素已失效（{exc!r}）→ 放弃本张，交外层刷新重试')
        return False
    if not nat_w or not disp_w:
        return False
    scale = disp_w / nat_w
    gap_x = (gap_x - piece_margin) * scale

    # 拖动距离 = 缺口位置(显示像素) - 拼图元素当前相对背景左缘的偏移（拼图块随把手 1:1 移动）
    try:
        piece_offset = piece_img.rect.location[0] - bg_img.rect.location[0]
    except Exception:
        piece_offset = 0
    distance = gap_x - piece_offset
    if distance <= 0:
        return False

    try:
        page.actions.move_to(handle).hold()
        page.actions.move(offset_x=distance, offset_y=0, duration=1.2)
        page.actions.release()
    except Exception as exc:
        _log(f'滑块：拖动时元素已失效（{exc!r}）→ 放弃本张，交外层刷新重试')
        return False
    time.sleep(2)
    return True


def _find_popup(page, timeout=1):
    """安全查找天爱弹窗容器；页面导航瞬间 CDP 可能抛错，统一返回 falsy。"""
    try:
        return page.ele('css:.tianai-captcha-ui-overlay', timeout=timeout)
    except Exception:
        return None


def _popup_visible(popup):
    """弹窗是否仍在显示（元素被移除视为已关闭）。"""
    try:
        return bool(popup.states.is_displayed)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 结果判定：以「表单页基线 → 查询后的变化」为准，不再依赖猜出来的选择器
#
# 2026-09-01 实测（验证码/probe_result_dom.py，人工过验证码后逐秒采样）确认：
#   * 结果容器真实 class 是 Resultlist（list 小写 l），代码原先写的 .ResultList
#     差一个字符、完全匹配不上——这正是"检出不了结果 → 反复点查询"的直接原因。
#     且该容器在【表单页就已存在】（隐藏且为空），所以"存在"本身也不能当信号。
#   * 「查询结果」文字同样在表单页就存在（隐藏页签），按文字匹配会误报。
#   * 真正随查询而变的是：a.View 结果行 0 → N、可见的 p.bg-default.mybg 标题
#     变为「查询结果」、以及无数据提示文字。
#   * 5 号站打开页面即自带默认名单（a.View 已有行），故"有行=有结果"不成立，
#     必须与基线做差分。
# 因此改为：表单页先拍基线，之后一律以「相对基线的变化」判定结果是否出现。
# ---------------------------------------------------------------------------

_COURT_STATE_JS = r"""
return (function () {
    function vis(el) {
        return !!(el && (el.offsetParent !== null || el.clientHeight > 0));
    }
    var views = document.querySelectorAll('a.View');
    var names = [];
    for (var i = 0; i < views.length && names.length < 5; i++) {
        if (vis(views[i])) { names.push((views[i].innerText || '').trim()); }
    }
    var heads = [];
    var ps = document.querySelectorAll('p.bg-default.mybg');
    for (var j = 0; j < ps.length; j++) {
        if (vis(ps[j])) { heads.push((ps[j].innerText || '').trim()); }
    }
    var body = document.body ? document.body.innerText : '';
    var pats = ['没有符合条件的数据', '没有查询到', '无符合条件', '未查询到',
                '暂无数据', '没有找到', '无相关数据'];
    var noHit = '';
    for (var k = 0; k < pats.length; k++) {
        if (body.indexOf(pats[k]) >= 0) { noHit = pats[k]; break; }
    }
    return JSON.stringify({rows: names.length, names: names,
                           heads: heads, noHit: noHit});
})()
"""


def _court_state(page):
    """取当前页面「结果相关状态」快照；取值失败返回 None。"""
    try:
        raw = page.run_js(_COURT_STATE_JS)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _court_baseline(page, stable_timeout=6):
    """拍表单页基线（务必在首次点查询之前调用）。

    5 号站打开后那张默认名单是异步渲染的，基线若拍早了会把"列表还没出来"
    记成 0 行，等列表一渲染就会被误判成"出结果了"，直接截到一张没查过的图。
    所以要求连续两次读数一致才采信；始终不稳定就取最后一次读数兜底。
    """
    last = None
    deadline = time.time() + stable_timeout
    while time.time() < deadline:
        cur = _court_state(page)
        if cur is None:
            time.sleep(0.3)
            continue
        if cur == last:
            return cur
        last = cur
        time.sleep(0.3)
    return last or {'rows': 0, 'names': [], 'heads': [], 'noHit': ''}


def _court_result_appeared(page, base):
    """结果是否已出现；返回命中的信号名（空串 = 未出现）。

    判定完全基于「相对表单页基线的变化」，三条口径覆盖 4/5 号站两种结构：
      - 无数据提示文字出现（原本没有才算）
      - 可见标题 p.bg-default.mybg 文本发生变化
      - a.View 结果行数 / 前几行姓名发生变化
    弹窗消失≠通过（弹窗会超时自动关闭，此时页面仍在表单页），故一律以变化为准。
    """
    cur = _court_state(page)
    if not cur:
        return ''
    if cur.get('noHit') and cur.get('noHit') != base.get('noHit'):
        return 'text:' + cur['noHit']
    if cur.get('heads') != base.get('heads'):
        return 'head:' + '|'.join(cur.get('heads') or [])
    if cur.get('rows') != base.get('rows'):
        return 'rows:%s->%s' % (base.get('rows'), cur.get('rows'))
    if cur.get('names') != base.get('names'):
        return 'names:changed'
    return ''


def _court_result_signal(page, base, timeout):
    """等待结果出现，返回命中的信号名；超时返回空串。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        signal = _court_result_appeared(page, base)
        if signal:
            return signal
        time.sleep(0.3)
    return ''


def _court_result_ready(page, base):
    """结果已变化且天爱验证码弹窗已关闭，才允许进入截图流程。"""
    if not _court_result_appeared(page, base):
        return False
    popup = _find_popup(page, timeout=0.1)
    return not popup or not _popup_visible(popup)


def _wait_court_result(page, base, timeout=MANUAL_RESULT_WAIT):
    """等待结果页出现且验证码弹窗关闭（结果渲染需要时间）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _court_result_ready(page, base):
            return True
        time.sleep(MANUAL_POLL_INTERVAL)
    return False


def _dump_failure_dom(page, reason, base=None):
    """结果判定失败时落盘页面证据（基线 / 当前状态 / 叶子节点 / 正文片段）。

    站点改版或判定失效时，靠这份快照照实修判定，不必再猜。
    落盘显式 utf-8（中文路径与中文页面内容都可能出问题）。
    """
    try:
        out_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))),
            '验证码', 'test_output',
        )
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(
            out_dir, f'court_fail_{time.strftime("%Y%m%d_%H%M%S")}.txt'
        )

        def _js(script, fallback):
            try:
                return page.run_js(script)
            except Exception as exc:
                return f'<js-error {exc!r}>'

        signal = _court_result_appeared(page, base or {}) or '(未检出)'
        nodes = _js(
            "return Array.prototype.slice.call(document.querySelectorAll('body *'))"
            ".filter(function(e){return e.children.length===0 && e.offsetParent!==null;})"
            ".slice(0,150).map(function(e){return e.tagName+'.'+e.className;}).join('\\n');"
        )
        text = _js("return (document.body?document.body.innerText:'').slice(0,2000);")
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(f'reason: {reason}\n')
            fh.write(f'url: {getattr(page, "url", "")}\n')
            fh.write(f'baseline: {json.dumps(base or {}, ensure_ascii=False)}\n')
            fh.write(f'current : {json.dumps(_court_state(page), ensure_ascii=False)}\n')
            fh.write(f'result_signal: {signal}\n')
            fh.write(f'\n--- leaf nodes ---\n{nodes}\n')
            fh.write(f'\n--- body text ---\n{text}\n')
        return path
    except Exception:
        return None


def _manual_fallback(page, base, timeout=MANUAL_TIMEOUT):
    """自动识别连续失败后的人工兜底：前台模式下浏览器已在屏幕上，等用户手动完成。

    通过临时修改标签页标题提示用户；轮询期间重新查找弹窗（不依赖旧元素引用，
    避免容器被页面重建后误判为已消失）。返回 True 表示验证已过（结果已出现）。
    """
    try:
        origin_title = page.run_js('return document.title;')
    except Exception:
        origin_title = None
    try:
        page.run_js('document.title = arguments[0];', '【需人工】请在浏览器中手动完成验证码')
    except Exception:
        pass
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _court_result_ready(page, base):
                return True
            cur = _find_popup(page, timeout=0.3)
            if not cur:
                # 弹窗消失：用户完成（结果在渲染）或验证码超时关闭，等结果区分。
                return _wait_court_result(page, base, timeout=MANUAL_RESULT_WAIT)
            time.sleep(MANUAL_POLL_INTERVAL)
        return False
    finally:
        if origin_title is not None:
            try:
                page.run_js('document.title = arguments[0];', origin_title)
            except Exception:
                pass


def _manual_wait_for_result(page, result_checker, timeout=MANUAL_TIMEOUT,
                            title='【需人工】请在浏览器中手动完成验证码'):
    """等待人工完成非天爱验证码流程；每 0.3 秒检查一次结果。"""
    try:
        origin_title = page.run_js('return document.title;')
    except Exception:
        origin_title = None
    try:
        try:
            page.run_js('document.title = arguments[0];', title)
        except Exception:
            pass
        deadline = time.time() + timeout
        while time.time() < deadline:
            if result_checker(page):
                return True
            time.sleep(MANUAL_POLL_INTERVAL)
        return False
    finally:
        if origin_title is not None:
            try:
                page.run_js('document.title = arguments[0];', origin_title)
            except Exception:
                pass


def _court_form(page, timeout=10):
    """取查询表单三件套（姓名 / 证件号 / 查询按钮）；任一缺失返回 None。

    DrissionPage 的 ele() 超时返回 falsy 的 NoneElement（不抛异常），
    必须逐个判真值——否则后续 .input() 抛 ElementNotFoundError，
    会直接冲出整个动作函数，连重试机会都没有。
    """
    try:
        page.wait.ele_displayed('#pName', timeout=timeout)
        name_ele = page.ele('#pName', timeout=8)
        card_ele = page.ele('#pCardNum', timeout=8)
        query_btn = page.ele('css:button.btn-zxgk', timeout=8)
    except Exception:
        return None
    if not (name_ele and card_ele and query_btn):
        return None
    return name_ele, card_ele, query_btn


def _observe_after_query(page, base, timeout=14):
    """点查询后的观察窗口：同时盯「弹窗出现」与「结果出现」，谁先出算谁。

    旧实现先死等弹窗 8s，等不到就立刻重填重查。但弹窗是异步加载（该站很慢），
    8s 扑空就重点查询，既造成用户看到的"重复点击"，高频查询又会触发站点风控。
    这里收敛成单一窗口，并把"无弹窗也无结果"明确成一个可区分的超时态。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        popup = _find_popup(page, timeout=0.3)
        if popup and _popup_visible(popup):
            return 'popup', popup
        if _court_result_appeared(page, base):
            return 'result', None
        time.sleep(0.3)
    return 'timeout', None


def action_court_captcha(page, subject, overall_timeout=180):
    """执行信息公开网：天爱验证码（点选文字/滑块拼图随机出现）。

    策略：滑块自动求解；点选文字用 ddddocr 普通模型单引擎（完整字集直接识别，
    提示字仅作结果过滤 + 概率置信度 + 多角度投票）OCR 求解。开启环境变量 CAPTCHA_DEBUG_DIR
    时每次点选都会把 tip/bg/识别详情落盘到该目录，事后用 test_captcha_click
    复盘失败原因。
    求解不通过再刷新换图重试；自动多轮失败后进入人工兜底（前台模式下等用户手动完成）。

    关于"验证码已通过却又重复点击查询"的修复（本次重点）：
    旧流程把「重新填表 + 点查询」当作通用重试动作，而成功出口只有"检出结果"一条。
    实测确认根因：结果容器真实 class 是 Resultlist（list 小写 l），代码原先写的
    .ResultList 差一个字符，而 querySelector 对 class 名大小写敏感，完全匹配不上；
    且该容器与「查询结果」文字在表单页就已存在（隐藏），于是无论按 class 还是按
    文字都判不出结果。后果是带着已经出来的结果回到外层重新点击查询——验证码再弹、
    再解，循环往复，单站可拖十几分钟，把后续站点全堵住。现从三方面收紧：
      1) 判定改为「表单页基线 → 查询后差分」，不再依赖猜出来的选择器；
      2) 外层每轮开头先查结果是否已出，已出直接收工，绝不重复点击；
      3) 点查询后统一走观察窗口（弹窗 / 结果谁先出现算谁），并加整体 deadline
         与重试冷却，最坏情况有上界，也不会高频触发风控。
    """
    name = _subject_name(subject)
    id_card = _subject_id(subject)
    base = None
    manual_offered = False
    deadline = time.time() + overall_timeout

    # 有效验证码提交和完整查询流程都最多 5 次；主动刷新验证码不消耗额度。
    submission_attempts = 0
    query_attempts = 0
    form = None
    form_deadline = time.time() + COURT_FORM_STARTUP_TIMEOUT
    while (
        submission_attempts < CAPTCHA_MAX_ATTEMPTS
        and query_attempts < CAPTCHA_MAX_ATTEMPTS
        and time.time() < deadline
    ):
        if base is not None and _court_result_ready(page, base):
            return True

        if form is None:
            form = _court_form(page)
        if not form:
            if time.time() >= form_deadline:
                _dump_failure_dom(page, 'court-form-unavailable', base)
                raise RuntimeError(
                    f"执行信息公开网页面 {COURT_FORM_STARTUP_TIMEOUT} 秒内未出现查询表单"
                )
            time.sleep(MANUAL_POLL_INTERVAL)
            continue
        name_ele, card_ele, query_btn = form
        if base is None:
            base = _court_baseline(page)

        try:
            name_ele.input(name, clear=True)
            card_ele.input(id_card, clear=True)
            query_btn.click(by_js=True)
            query_attempts += 1
        except Exception:
            form = None
            continue

        outcome, popup = _observe_after_query(page, base)
        if outcome == 'result':
            return True
        if outcome == 'timeout':
            time.sleep(3)
            form = None
            continue

        # 当前验证码一直存在时只主动刷新换图，直到成功、额度耗尽或总时限到。
        while time.time() < deadline:
            popup = _find_popup(page, timeout=1.5)
            if not popup or not _popup_visible(popup):
                if _wait_court_result(page, base, timeout=MANUAL_RESULT_WAIT):
                    return True
                break

            _tianai_content_ready(popup)
            solved = False
            mode = _tianai_mode(popup)
            _log(f'弹窗 mode={mode}')
            try:
                if mode == 'slider':
                    solved = _solve_tianai_slider(page, popup)
                else:
                    solved = _solve_tianai_word_click(page, popup)
            except Exception as exc:
                _log(f'弹窗求解异常 mode={mode}: {exc!r}', '\n', traceback.format_exc())

            if solved:
                submission_attempts += 1
                if _wait_court_result(page, base, timeout=MANUAL_RESULT_WAIT):
                    return True
                if submission_attempts >= CAPTCHA_MAX_ATTEMPTS:
                    break

            # 主动刷新不增加 attempts；刷新失败时重新找弹窗，避免旧引用失效。
            cur = _find_popup(page, timeout=1.5)
            if not cur:
                if _wait_court_result(page, base, timeout=MANUAL_RESULT_WAIT):
                    return True
                break
            if not _tianai_refresh(page, cur):
                time.sleep(MANUAL_POLL_INTERVAL)

        if _manual_allowed() and not manual_offered:
            manual_offered = True
            if _manual_fallback(page, base, timeout=MANUAL_TIMEOUT):
                return True
        if _court_result_ready(page, base):
            return True
        form = None
        time.sleep(3)

    _dump_failure_dom(page, 'captcha-flow-exhausted', base)
    raise RuntimeError("执行信息公开网验证码连续识别失败")


def _get_base64_img_bytes(img_element):
    if not img_element:
        return None
    try:
        src = img_element.attr("src")
        if src and "base64," in src:
            import base64

            return base64.b64decode(src.split("base64,", 1)[1])
    except Exception:
        pass
    return None


def _find_slider_distance_cv2(slider_bytes, bg_bytes):
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("证监会滑块验证码模式需要先安装 opencv-python 和 numpy") from exc

    slider = cv2.imdecode(np.frombuffer(slider_bytes, np.uint8), cv2.IMREAD_COLOR)
    bg = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)

    slider_edge = cv2.Canny(cv2.cvtColor(slider, cv2.COLOR_BGR2GRAY), 100, 200)
    bg_edge = cv2.Canny(cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY), 100, 200)
    _, _, _, max_loc = cv2.minMaxLoc(
        cv2.matchTemplate(bg_edge, slider_edge, cv2.TM_CCOEFF_NORMED)
    )
    return max_loc[0], bg.shape[1]


def action_court_captcha_legacy(page, subject):
    """旧版字符验证码流程（已弃用，保留备查）。"""
    try:
        import ddddocr
    except ImportError as exc:
        raise RuntimeError("最高院验证码模式需要先安装 ddddocr") from exc

    name = _subject_name(subject)
    id_card = _subject_id(subject)
    ocr = ddddocr.DdddOcr(show_ad=False)

    for retry in range(5):
        try:
            page.wait.ele_displayed('#pName', timeout=10)
            name_ele = page.ele('#pName', timeout=8)
            card_ele = page.ele('#pCardNum', timeout=8)
            captcha_ele = page.ele('#captchaImg', timeout=8)
            code_ele = page.ele('#yzm', timeout=8)
        except Exception:
            # 页面加载慢/被安全策略拦截时，等待后进入下一轮重试，而非整站放弃
            time.sleep(2)
            continue

        name_ele.input(name, clear=True)
        card_ele.input(id_card, clear=True)

        captcha_ele.click()
        time.sleep(0.6)

        img_bytes = captcha_ele.get_screenshot(as_bytes=True)
        code_text = ocr.classification(img_bytes)
        code_ele.input(code_text, clear=True)
        page.ele('text=查询', timeout=5).click(by_js=True)

        is_error = False
        for _ in range(10):
            error_element = page.ele('.important', timeout=0.2)
            if error_element and ("验证码错误" in error_element.text or "验证码已过期" in error_element.text):
                is_error = True
                break

            if (
                page.ele('css:.ResultList', timeout=0.1)
                or page.ele('text=没有符合条件的数据', timeout=0.1)
                or page.ele('text=查询结果', timeout=0.1)
            ):
                break

        if not is_error:
            time.sleep(0.5)
            return

    raise RuntimeError("最高院字符验证码连续识别失败")


def _element_visible(page, selectors):
    """返回一组候选选择器中是否有可见元素。"""
    for selector in selectors:
        try:
            element = page.ele(selector, timeout=0.1)
            if element and _popup_visible(element):
                return True
        except Exception:
            continue
    return False


def _jiangsu_result_appeared(page):
    """判断江苏税务查询是否已渲染结果，而不是仅仅没有错误提示。"""
    return _element_visible(page, (
        'css:#searchResult',
        'css:.table_main',
        'css:.table_main tbody tr',
        'text=暂无数据',
        'text=没有查询到',
    ))


def _wait_result(page, result_checker, timeout=MANUAL_RESULT_WAIT):
    """以 0.3 秒间隔等待一个站点结果判定器。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if result_checker(page):
            return True
        time.sleep(MANUAL_POLL_INTERVAL)
    return False


def action_csrc_shixin_slider(page, subject):
    """中国证监会证券期货市场失信记录查询平台滑块验证码。"""
    name = _subject_name(subject)
    id_card = _subject_id(subject)

    page.ele('css:input[placeholder*="必须填写姓名"]', timeout=10).input(name, clear=True)
    page.ele('css:input[placeholder*="需要填写完整"]', timeout=10).input(id_card, clear=True)
    page.ele("css:.searchBtn", timeout=8).click(by_js=True)
    time.sleep(2)

    for retry_count in range(5):
        try:
            bg = (
                page.ele("css:.verify-img-panel img", timeout=2)
                or page.ele("css:.popup-bg", timeout=2)
            )
            slider = (
                page.ele("css:.verify-sub-block img", timeout=2)
                or page.ele("css:.popup-slide", timeout=2)
            )
            drag = (
                page.ele("css:.verify-move-block", timeout=2)
                or page.ele("css:.slider-btn", timeout=2)
            )

            if not (bg and slider and drag) or bg.rect.size[0] == 0:
                break

            bg_bytes = _get_base64_img_bytes(bg)
            slider_bytes = _get_base64_img_bytes(slider)
            if not (bg_bytes and slider_bytes):
                time.sleep(1)
                continue

            x, original_width = _find_slider_distance_cv2(slider_bytes, bg_bytes)
            bg_width = bg.rect.size[0]
            if bg_width == 0:
                break

            distance = x * (bg_width / original_width)
            page.actions.move_to(drag).hold()
            page.actions.move(offset_x=distance, offset_y=0, duration=1.2)
            page.actions.release()
            time.sleep(3)
        except Exception as exc:
            if "没有位置及大小" in str(exc) or "ElementLostError" in str(exc):
                break
            time.sleep(1)
    else:
        raise RuntimeError("证监会滑块验证码连续识别失败")

    time.sleep(2)


def action_jiangsu_tax(page, subject):
    """江苏税务局独立脚本模式，保留验证码 OCR 重试。"""
    try:
        import ddddocr
    except ImportError as exc:
        raise RuntimeError("江苏税务局模式需要先安装 ddddocr") from exc

    name = _subject_name(subject)
    id_card = _subject_id(subject)
    ocr = ddddocr.DdddOcr(show_ad=False)

    input_name = page.ele('#name', timeout=10)
    input_nsrsbh = page.ele('#nsrsbh', timeout=10)
    input_rand = page.ele('#rand', timeout=10)
    captcha_ele = page.ele('#randImage', timeout=10)
    search_btn = page.ele('@onclick=refreshIf()', timeout=10)

    for retry in range(5):
        input_name.input(name, clear=True)
        input_nsrsbh.input(id_card, clear=True)

        if retry > 0:
            captcha_ele.click()
            time.sleep(0.5)

        img_bytes = captcha_ele.get_screenshot(as_bytes=True)
        code_text = ocr.classification(img_bytes)
        input_rand.input(code_text, clear=True)
        search_btn.click(by_js=True)

        try:
            page.wait.eles_loaded(['text=验证码错误，请重新输入', '.table_main', '#searchResult'], timeout=4)
        except Exception:
            time.sleep(1)

        error_ele = page.ele('text=验证码错误，请重新输入', timeout=0.2)
        if not error_ele:
            time.sleep(0.5)
            return

    raise RuntimeError("江苏税务局验证码连续识别失败")
