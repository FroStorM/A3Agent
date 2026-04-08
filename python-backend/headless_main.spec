# -*- mode: python ; coding: utf-8 -*-

import sys
import os
import shutil
import json
import tempfile
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

_spec_dir = globals().get("SPECPATH") or os.getcwd()
_spec_dir = os.path.abspath(_spec_dir)

# -------------------------------------------------------
# 构建一个干净的 ga_config 临时目录用于打包
# 只包含：memory/*.md（SOP文件）+ 空的 mykey.json
# 不包含：temp/（运行时日志）、私人 API key
# -------------------------------------------------------
def _build_clean_ga_config():
    """在临时目录创建干净的 ga_config，只含 SOP 文件和空模板。"""
    staging = os.path.join(_spec_dir, "build", "_ga_config_staging")
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging, exist_ok=True)

    # 写入空的 mykey.json 模板（不含任何真实 key）
    with open(os.path.join(staging, "mykey.json"), "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4, ensure_ascii=False)

    # 复制 memory 目录里的 .md 文件（SOP）
    src_memory = os.path.join(_spec_dir, "memory")
    if os.path.isdir(src_memory):
        dst_memory = os.path.join(staging, "memory")
        os.makedirs(dst_memory, exist_ok=True)
        for root, dirs, files in os.walk(src_memory):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "skill_search") and not d.startswith(".")]
            rel = os.path.relpath(root, src_memory)
            out_dir = dst_memory if rel == "." else os.path.join(dst_memory, rel)
            os.makedirs(out_dir, exist_ok=True)
            for name in files:
                if name.startswith(".") or name.endswith(".pyc"):
                    continue
                if not name.endswith(".md"):
                    continue
                shutil.copy2(os.path.join(root, name), os.path.join(out_dir, name))

    # 复制 assets 目录
    src_assets = os.path.join(_spec_dir, "assets")
    if os.path.isdir(src_assets):
        dst_assets = os.path.join(staging, "assets")
        shutil.copytree(src_assets, dst_assets, ignore=shutil.ignore_patterns('__pycache__', '.*'))

    return staging

_clean_ga_config = _build_clean_ga_config()

# 收集所有需要的数据文件
_assets_src = os.path.join(_spec_dir, "assets")
datas = [
    (_clean_ga_config, 'ga_config'),  # 干净的默认配置（空 mykey.json + SOP + memory）
]
if os.path.isdir(_assets_src):
    datas.append((_assets_src, 'assets'))  # agentmain.py 在 _MEIPASS/assets/ 下找 tools_schema.json

# 收集所有隐藏导入
hiddenimports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'starlette',
    'pydantic',
    'requests',
    'urllib3',
]

a = Analysis(
    ['headless_main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 使用 --onefile 模式：将所有内容打包到单个exe中
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='python-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
