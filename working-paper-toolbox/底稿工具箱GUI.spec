# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec —— 债承底稿处理工具箱 GUI 单文件打包。

设计要点（与 底稿工具箱GUI.py 的 frozen 分发逻辑配套）：
  - 各功能子模块的 .py 以【数据文件】形式原样打入包内（保持目录结构），
    运行时经 gui_runner / --run-script 通过 sys.path 或 runpy 加载；
    绝不能作为 hiddenimport 打进 PYZ，否则三个同名 toolkit 包会互相冲突。
  - 第三方库均在子进程内动态导入，静态分析不可见，须显式 hiddenimports。
"""

import os
import re

ROOT = os.path.dirname(os.path.abspath(SPEC))

MODULE_DIRS = ["签章页工具", "替换底稿内容", "比较文件夹内容", "底稿pdf材料"]

datas = [(os.path.join(ROOT, "gui_runner.py"), ".")]

# ① 各模块顶层脚本（CLI 入口 / 被 exec 的初始化脚本 / 目录生成脚本）
for d in MODULE_DIRS + ["多级文件夹生成目录"]:
    dpath = os.path.join(ROOT, d)
    for fn in sorted(os.listdir(dpath)):
        fp = os.path.join(dpath, fn)
        if fn.endswith(".py") and not fn.startswith("test") and os.path.isfile(fp):
            datas.append((fp, d))

# ② 各模块的 toolkit / toolbox 实现包（排除测试与缓存）
for d in MODULE_DIRS:
    for pkg in ("toolkit", "toolbox"):
        ppath = os.path.join(ROOT, d, pkg)
        if not os.path.isdir(ppath):
            continue
        for dirpath, dirnames, filenames in os.walk(ppath):
            dirnames[:] = [x for x in dirnames if x != "__pycache__"]
            for fn in sorted(filenames):
                if fn.endswith(".py") and not fn.startswith("test"):
                    rel = os.path.relpath(dirpath, ROOT)
                    datas.append((os.path.join(dirpath, fn), rel))


a = Analysis(
    [os.path.join(ROOT, "底稿工具箱GUI.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # 图像 / Office 文档 / PDF / 表格
        "PIL", "PIL.Image", "PIL.ImageChops", "PIL.JpegImagePlugin",
        "docx", "openpyxl", "pandas", "pypdf",
        # Word COM（长替换、导出 PDF）
        "win32com", "win32com.client", "pythoncom", "win32api",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib", "scipy", "IPython", "pytest",
        "tkinter.test",
        # pandas.plotting 会把多套 Qt 绑定拉进来，GUI 用的是 tkinter，全部排除
        "PyQt5", "PySide6", "PySide2", "shiboken6", "shiboken2", "qtpy",
        # 与本工具箱无关的重型传递依赖
        "sphinx", "docutils", "numba", "llvmlite", "pyarrow", "zmq",
        # anaconda 环境中被传递引入的机器学习/可视化生态（本项目完全不使用）
        "torch", "torchvision", "torchaudio", "cv2", "shapely",
        "opt_einsum", "networkx", "sympy", "jax", "tensorflow",
        "onnxruntime", "openai", "holoviews", "bokeh", "panel",
        "datashader", "nbconvert", "notebook", "jupyter_client",
        "numpydoc", "numexpr", "bottleneck", "polars", "narwhals",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# ---- 显式补充 Tcl/Tk 及 CPython 标准库扩展的运行时依赖 ----
# conda 布局下，标准库 .pyd（pyexpat/_lzma/_ctypes/_ssl/_hashlib/_bz2/_sqlite3）
# 与 Tcl/Tk 的依赖 DLL 都在 %PREFIX%\Library\bin，PyInstaller 不会自动收集。
import sys as _sys

_SEARCH_DIRS = [
    os.path.join(_sys.prefix, "Library", "bin"),
    os.path.join(_sys.prefix, "DLLs"),
    _sys.prefix,
]


def _find_in_search(name):
    """在 conda 运行库目录中查找 DLL，返回绝对路径或 None。"""
    for d in _SEARCH_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def _pe_imported_dlls(path):
    """解析 PE 导入表，返回该文件直接依赖的 DLL 名列表（纯 struct 实现）。"""
    import struct

    with open(path, "rb") as fh:
        data = fh.read()
    if data[:2] != b"MZ":
        return []
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    coff = pe_off + 4
    num_sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    ddir_off = opt + (112 if magic == 0x20B else 96)
    import_rva = struct.unpack_from("<I", data, ddir_off + 8)[0]
    sec_off = opt + opt_size
    sections = []
    for i in range(num_sections):
        s = sec_off + i * 40
        vsz, va = struct.unpack_from("<II", data, s + 8)
        rawsz, raw = struct.unpack_from("<II", data, s + 16)
        sections.append((va, max(vsz, rawsz), raw))
    off = None
    for va, size, raw in sections:
        if va <= import_rva < va + size:
            off = raw + (import_rva - va)
            break
    if off is None:
        return []

    def rva2off(rva):
        for va, size, raw in sections:
            if va <= rva < va + size:
                return raw + (rva - va)
        return None

    def cstr(o):
        return data[o:data.index(b"\x00", o)].decode("ascii", "replace")

    names = []
    while True:
        ent = data[off:off + 20]
        if len(ent) < 20 or ent == b"\x00" * 20:
            break
        name_rva = struct.unpack_from("<I", ent, 12)[0]
        if name_rva == 0:
            break
        names.append(cstr(rva2off(name_rva)))
        off += 20
    return names


_SYSTEM_DLL_RE = re.compile(
    r"^(api-ms-|ext-ms-|kernel32|user32|gdi32|shell32|advapi32|ws2_32|wsock32"
    r"|ole32|oleaut32|comctl32|comdlg32|bcrypt|ncrypt|crypt32|wintrust"
    r"|msvcrt|vcruntime|ucrtbase|python\d+|ntdll)", re.I)


def _collect_conda_dlls(seed_names):
    """从 seed 出发递归解析 Library\\bin 内 DLL 的导入闭包。

    返回 [(打包名, 源路径, "BINARY"), ...]；系统 DLL 自动跳过。
    """
    collected = {}
    queue = [n for n in seed_names]
    while queue:
        name = queue.pop(0)
        key = name.lower()
        if key in collected or _SYSTEM_DLL_RE.match(key):
            continue
        src = _find_in_search(name)
        if src is None:
            continue
        collected[key] = (name, src, "BINARY")
        print(f"[spec] 补充运行库: {name} <- {src}")
        for dep in _pe_imported_dlls(src):
            if dep.lower() not in collected:
                queue.append(dep)
    return list(collected.values())


# 种子清单：Pillow(_imaging/_imagingft/_webp)、lxml(etree)、
# 以及 Tcl/Tk、标准库扩展所需（原有清单保持不变）。
_seed_dlls = [
    # Pillow 图像编解码链（conda 版 _imaging.pyd 的直接依赖）
    "tiff.dll", "libjpeg.dll", "openjp2.dll", "zlib.dll",
    "freetype.dll", "libwebp.dll", "libwebpmux.dll", "libwebpdemux.dll",
    "avif.dll",
    # lxml / python-docx 的 etree
    "libxml2.dll", "libxslt.dll", "libexslt.dll", "iconv.dll",
    # tiff/freetype 的二级依赖
    "deflate.dll", "Lerc.dll", "liblzma.dll", "zstd.dll", "libpng16.dll",
    # Tcl / Tk
    "tcl86t.dll", "tk86t.dll",
    # pyexpat
    "expat.dll", "libexpat.dll",
    # _lzma / _bz2 / _sqlite3 / _ssl / _hashlib / zlib
    "lzma.dll", "libbz2.dll", "sqlite3.dll",
    "libcrypto-3-x64.dll", "libssl-3-x64.dll", "zlib1.dll",
    # _ctypes
    "ffi.dll", "ffi-7.dll", "ffi-8.dll",
]

_extra_dlls = _collect_conda_dlls(_seed_dlls)
_seen = {os.path.basename(t[0]).lower() for t in a.binaries}
for _name, _src, _kind in _extra_dlls:
    if _name.lower() not in _seen:
        a.binaries.append((_name, _src, _kind))

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="底稿工具箱GUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
