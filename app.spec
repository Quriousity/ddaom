# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 스펙 (명세 §2.2, §9).
# 빌드: pyinstaller app.spec  (Windows 에서 실행해야 Windows exe 가 나온다)
from PyInstaller.utils.hooks import collect_all

# onnxruntime DLL 누락 방지 (§9) — collect_all 이 가장 확실하다
onnx_datas, onnx_bins, onnx_hidden = collect_all("onnxruntime")
# rapidocr 의 config.yaml + 동봉 cls 모델 (det/rec 은 우리 번들로 대체되지만 cls 는 패키지 것)
rapid_datas, rapid_bins, rapid_hidden = collect_all("rapidocr_onnxruntime")

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=onnx_bins + rapid_bins,
    datas=[("app/models", "models"), ("app/icon.png", ".")] + onnx_datas + rapid_datas,  # §2.1 모델 + 아이콘
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
    [],
    exclude_binaries=True,
    name="ttaom",
    icon="assets/icon.ico",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # GUI 앱 — 콘솔창 없음
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ttaom",  # onedir (§2: onefile 은 기동 지연 + 백신 오탐)
)
