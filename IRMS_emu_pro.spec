# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
ROOT=Path(SPECPATH)
datas=[(str(ROOT/"irms"/"web"),"irms/web")]
for name in ("LICENSE","THIRD_PARTY_NOTICES.md","QT_NOTICE_301.txt"):
    if (ROOT/name).exists():datas.append((str(ROOT/name),"licenses"))
a=Analysis([str(ROOT/"lancer_irms.pyw")],pathex=[str(ROOT)],binaries=[],datas=datas,
    hiddenimports=collect_submodules("irms")+["PySide6.QtCore","PySide6.QtGui","PySide6.QtWidgets","tkinter.messagebox"],
    hookspath=[],hooksconfig={},runtime_hooks=[],excludes=["PyQt5","PyQt6","PySide2","PySide6.QtWebEngineCore","PySide6.QtWebEngineWidgets","PySide6.QtQml","PySide6.QtQuick"],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name="IRMS-emu-pro",debug=False,
        bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False)
