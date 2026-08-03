"""다크 테마 — 테일윈드식 토큰 + QSS. 의존성 없이 전 위젯 일관 스타일."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# ---- 디자인 토큰 (tailwind 팔레트 발췌) ----
BG = "#14161b"          # zinc-950 근처 — 창 바닥
SURFACE = "#1c1f26"     # 툴바·패널
SURFACE_HI = "#252932"  # hover
BORDER = "rgba(255,255,255,0.08)"
TEXT = "#e6e8eb"
TEXT_MUTED = "#9aa1ab"
ACCENT = "#3b82f6"      # blue-500
ACCENT_DIM = "#2f6cd4"
DANGER = "#ef4444"      # red-500
OK = "#22c55e"          # green-500 (토글 스위치와 동일 계열)

QSS = f"""
QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; }}

QToolBar {{
    background: {SURFACE};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    spacing: 4px;
}}
QToolBar QWidget {{ background: transparent; }}
QToolBar QLabel {{ color: {TEXT_MUTED}; background: transparent; }}
QToolBar::separator {{
    background: {BORDER};
    width: 1px;
    margin: 6px 8px;
}}
QToolButton {{
    background: transparent;
    color: {TEXT};
    padding: 6px 12px;
    border-radius: 6px;
    border: none;
}}
QToolButton:hover {{ background: {SURFACE_HI}; }}
QToolButton:pressed {{ background: {ACCENT_DIM}; color: white; }}
QToolButton:disabled {{ color: rgba(230,232,235,0.35); }}
QToolButton#danger:hover {{ background: {DANGER}; color: white; }}

QStatusBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
}}
QStatusBar QLabel {{ color: {TEXT_MUTED}; padding: 0 8px; background: transparent; }}
QStatusBar::item {{ border: none; }}

QListWidget {{
    background: transparent;
    border: none;
    outline: none;
}}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.18); border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.30); }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: rgba(255,255,255,0.18); border-radius: 4px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: rgba(255,255,255,0.30); }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMessageBox, QInputDialog, QFileDialog {{ background: {SURFACE}; }}
QPushButton {{
    background: {SURFACE_HI};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    min-width: 60px;
}}
QPushButton:hover {{ background: #2d323d; }}
QPushButton:default {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton:default:hover {{ background: {ACCENT_DIM}; }}
QLineEdit {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    color: {TEXT};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}

QToolTip {{
    background: {SURFACE_HI};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 8px;
}}
"""


def apply_theme(app) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.Base, QColor(BG))
    pal.setColor(QPalette.AlternateBase, QColor(SURFACE))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.PlaceholderText, QColor(TEXT_MUTED))
    pal.setColor(QPalette.Button, QColor(SURFACE))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ToolTipBase, QColor(SURFACE_HI))
    pal.setColor(QPalette.ToolTipText, QColor(TEXT))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
