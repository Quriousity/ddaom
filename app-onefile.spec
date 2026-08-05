# -*- mode: python ; coding: utf-8 -*-
# 단일 exe(onefile) 스펙. 배포 기본은 app.spec(onedir) 이다 — 이쪽은 파일 하나로
# 들고 다녀야 할 때만 쓴다. 대가: 실행할 때마다 임시폴더에 풀어서 기동이 느리고
# 백신 오탐이 늘어난다.
# 빌드: pyinstaller app-onefile.spec
from PyInstaller.utils.hooks import collect_all

onnx_datas, onnx_bins, onnx_hidden = collect_all("onnxruntime")
rapid_datas, rapid_bins, rapid_hidden = collect_all("rapidocr_onnxruntime")

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=onnx_bins + rapid_bins,
    datas=[("app/models", "models"), ("app/icon.png", ".")] + onnx_datas + rapid_datas,
    hiddenimports=onnx_hidden + rapid_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "jupyter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ddaom",
    icon="assets/icon.ico",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # GUI 앱 — 콘솔창 없음
)
