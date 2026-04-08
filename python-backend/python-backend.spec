# -*- mode: python ; coding: utf-8 -*-

import os

_spec_dir = globals().get("SPECPATH") or os.getcwd()
_spec_dir = os.path.abspath(_spec_dir)

a = Analysis(
    ['headless_main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(_spec_dir, 'memory'), 'memory'),
        (os.path.join(_spec_dir, 'mykey.json'), '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
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
