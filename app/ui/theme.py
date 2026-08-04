"""다크 테마 — 테일윈드식 토큰 + QSS. 의존성 없이 전 위젯 일관 스타일."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# ---- 디자인 토큰 (tailwind zinc — 푸른기 없는 중성 그레이) ----
BG = "#18181b"          # zinc-900 — 창 바닥 (950 은 너무 검다)
SURFACE = "#18181b"     # 툴바·패널 — 바닥과 한 면, 경계는 헤어라인으로
SURFACE_HI = "#27272a"  # zinc-800 — hover
BORDER = "rgba(255,255,255,0.08)"
TEXT = "#e4e4e7"        # zinc-200
TEXT_MUTED = "#a1a1aa"  # zinc-400
ACCENT = "#6366f1"      # indigo-500 — 모던 웹 액센트 (토글·선택 강조 공용)
ACCENT_DIM = "#4f46e5"  # indigo-600
DANGER = "#ef4444"      # red-500

# 통일 폰트 (Windows: Segoe UI/맑은 고딕, macOS: 시스템 산세리프)
FONT_STACK = '"Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo", "Helvetica Neue", sans-serif'
FONT_SIZE = "13px"

QSS = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: {FONT_STACK};
    font-size: {FONT_SIZE};
    font-weight: 400;
}}

QToolBar {{
    background: {SURFACE};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    spacing: 4px;
}}
QToolBar QWidget {{ background: transparent; }}
QToolBar QLabel {{
    color: {TEXT_MUTED};
    background: transparent;
    font-size: {FONT_SIZE};
    font-weight: 500;
}}
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
    font-size: {FONT_SIZE};
    font-weight: 500;
}}
QToolButton:hover {{ background: {SURFACE_HI}; }}
QToolButton:pressed {{ background: {ACCENT_DIM}; color: white; }}
QToolButton:disabled {{ color: rgba(230,232,235,0.35); }}
/* 접기/펴기 토글: 펴짐 = 액센트 틴트, 접힘 = 흐린 글자.
   해제 상태에도 같은 두께의 투명 테두리 — 상태 전환 시 폭이 변하지 않는다.
   hover 는 같은 액센트의 한 단계 진하기로 자연스럽게 이어진다 */
QToolButton[checkable="true"] {{ color: {TEXT_MUTED};
    border: 1px solid transparent; }}
QToolButton:checked {{
    background: rgba(99,102,241,0.18);
    color: #c7d2fe;                       /* indigo-200 */
    border: 1px solid rgba(99,102,241,0.45);
}}
QToolButton:checked:hover {{ background: rgba(99,102,241,0.30); }}
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
/* 되돌릴 수 없는 실행 버튼 — 색으로 미리 경고한다 */
QPushButton#danger {{
    background: rgba(239,68,68,0.16);
    border-color: rgba(239,68,68,0.45);
    color: #fca5a5;                       /* red-300 */
    font-weight: 600;
}}
QPushButton#danger:hover {{ background: {DANGER}; border-color: {DANGER}; color: white; }}
QPushButton#danger:disabled {{
    background: {SURFACE_HI};
    border-color: {BORDER};
    color: rgba(228,228,231,0.30);
}}

/* 담은 목록 — 여기 있는 것이 곧 파괴 대상이다 */
#trayList {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
}}
#trayList::item {{ border-radius: 4px; margin: 1px 0px; }}
#trayList::item:hover {{ background: rgba(239,68,68,0.14); }}
#trayBadge {{
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
    background: transparent;
}}
#trayRowEdit {{
    background: transparent;
    border: none;
    padding: 2px 0px;
    color: {TEXT};
    selection-background-color: {ACCENT};
}}
#trayRowEdit:focus {{ background: rgba(255,255,255,0.06); border-radius: 3px; }}
#trayRowEdit[readOnly="true"] {{ color: {TEXT_MUTED}; }}
#trayRemove {{
    background: transparent;
    border: none;
    color: {TEXT_MUTED};
    padding: 0px 4px;
    font-size: 12px;
    min-width: 0px;
}}
#trayRemove:hover {{ background: {DANGER}; color: white; border-radius: 3px; }}
#trayHint {{ color: {TEXT_MUTED}; font-size: 12px; background: transparent; }}

QLineEdit {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    color: {TEXT};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}

#tray {{ border-left: 1px solid {BORDER}; }}
#trayTitle {{ color: {TEXT_MUTED}; font-weight: 600; }}
QPlainTextEdit {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px;
    color: {TEXT};
    selection-background-color: {ACCENT};
}}
QPlainTextEdit:focus {{ border-color: {ACCENT}; }}

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
