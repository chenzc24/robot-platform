# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

root = Path(SPEC).resolve().parents[2]
backend = root / "backend"

datas = [(str(backend / "static"), "static")]

a = Analysis(
    [str(root / "desktop" / "launcher.py")],
    pathex=[str(backend)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StrokeReview",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="StrokeReview",
)
