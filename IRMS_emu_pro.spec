# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)
datas = [(str(ROOT / "irms" / "web"), "irms/web")]
for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
    path = ROOT / filename
    if path.exists():
        datas.append((str(path), "licenses"))

a = Analysis(
    [str(ROOT / "lancer_irms.pyw")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("irms") + ["tkinter", "tkinter.ttk", "tkinter.messagebox"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="IRMS-emu-pro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
