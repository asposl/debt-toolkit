# -*- mode: python ; coding: utf-8 -*-
# 诚信核查自动化截图 GUI 打包配置（onedir）
# 入口：GUI/main.py ｜ 用法：在仓库根目录执行 pyinstaller 诚信核查自动化截图.spec --noconfirm

import os
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# 爬虫可选依赖整包收集（含数据文件）：
#   playwright   -> node 驱动（天眼查/文书网工作流）
#   DrissionPage -> 配置文件
#   ddddocr      -> onnx 识别模型
# rapidocr_onnxruntime 已于 2026-09-01 第六轮移除（约 13 MB）：点选验证码改
# ddddocr 单引擎后代码里已无任何 import（只剩注释和一个主动抛错的兼容壳
# _get_rapidocr）。本机仍装着这个包，但 collect_all 它只会白白撑大产物。
for _pkg in ('playwright', 'DrissionPage', 'ddddocr'):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

# PyAutoGUI imports PyScreeze dynamically.  PyInstaller can see the import
# during analysis but may omit it from a later incremental build, leaving the
# screenshot function replaced by PyAutoGUI's misleading fallback exception.
# Keep the complete screenshot import chain explicit in the frozen bundle.
hiddenimports += [
    'pyautogui',
    'pyautogui._pyautogui_win',
    'pyscreeze',
    'PIL.ImageGrab',
]

# conda 环境特有：conda 把 Python 扩展模块的依赖 DLL 集中放在 Library\bin，
# PyInstaller 不会自动收集。以下清单为逐项验证的最小集合：
#   ffi*.dll            -> _ctypes.pyd（缺失则 import ctypes 直接失败）
#   tcl86t/tk86t.dll    -> _tkinter.pyd（缺失则 GUI 无法启动）
#   charset/iconv.dll   -> iconv 转码链
#   libxml2/libxslt/libexslt/liblzma/zlib.dll -> lxml.etree（DrissionPage 依赖）
import sys
_conda_bin = os.path.join(sys.base_prefix, 'Library', 'bin')
_conda_dlls = (
    'ffi.dll', 'ffi-7.dll', 'ffi-8.dll',
    'tcl86t.dll', 'tk86t.dll', 'zlib.dll',
    'charset.dll', 'iconv.dll',
    'libxml2.dll', 'libxslt.dll', 'libexslt.dll', 'liblzma.dll',
    # Pillow 12 image codecs (required by PIL._imaging even when only
    # ImageGrab.grab() and PNG saving are used).
    'libjpeg.dll', 'libtiff.dll', 'tiff.dll',
    'libpng16.dll', 'libwebp.dll', 'libwebpdecoder.dll',
    'libwebpdemux.dll', 'libwebpmux.dll',
    'openjp2.dll', 'lcms2.dll', 'freetype.dll', 'avif.dll',
    'zlib-ng2.dll', 'zstd.dll',
)
if os.path.isdir(_conda_bin):
    for _dll in _conda_dlls:
        _p = os.path.join(_conda_bin, _dll)
        if os.path.isfile(_p):
            binaries.append((_p, '.'))

# Playwright Chromium 浏览器：构建号必须与 modules/scraper/browser.py 的
# 兜底路径（ms-playwright/chromium-1223）一致；main.py 会把 PLAYWRIGHT_BROWSERS_PATH
# 指向 sys._MEIPASS/ms-playwright，DrissionPage 与 playwright 工作流共用。
_localapp = os.environ.get('LOCALAPPDATA', '')
_ms_pw = os.path.join(_localapp, 'ms-playwright')
_chromium = os.path.join(_ms_pw, 'chromium-1223')
if os.path.isdir(_chromium):
    datas.append((_chromium, os.path.join('ms-playwright', 'chromium-1223')))
else:
    raise SystemExit(f'未找到 Chromium 浏览器目录：{_chromium}（请先 playwright install chromium）')
# 无头模式（--verify-bundle 自检等）使用独立的 headless shell
_headless = os.path.join(_ms_pw, 'chromium_headless_shell-1223')
if os.path.isdir(_headless):
    datas.append((_headless, os.path.join('ms-playwright', 'chromium_headless_shell-1223')))


a = Analysis(
    ['GUI\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 测试/文档/Qt 绑定：运行时零引用（ddddocr→onnxruntime 分析链会误拖
        # torch→matplotlib→scipy→dask→IPython→sphinx→PyQt5/PySide6，导致
        # 体积爆炸与多 Qt 绑定冲突，已验证 import 后均不加载）
        'pytest', '_pytest', 'py', 'py.test',
        'torch', 'torchvision', 'torchaudio', 'tensorboard',
        'matplotlib', 'scipy', 'pandas', 'dask',
        'IPython', 'jupyter', 'nbformat', 'black', 'sphinx',
        'PyQt5', 'PySide2', 'PySide6', 'zmq',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='诚信核查自动化截图',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='诚信核查自动化截图',
)
