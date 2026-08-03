"""공용 위젯 — 토글 스위치."""
from __future__ import annotations

from PySide6.QtCore import (Property, QEasingCurve, QPropertyAnimation, QSize,
                            Qt)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton

from .theme import ACCENT

_TRACK_ON = QColor(ACCENT)          # 테마 액센트(인디고)와 통일
_TRACK_OFF = QColor("#3f3f46")      # zinc-700
_KNOB = QColor("#fafafa")


class ToggleSwitch(QAbstractButton):
    """iOS 풍 온/오프 스위치. checked 가 상태의 진실이다."""

    def __init__(self, parent=None, checked: bool = False):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self._offset = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, checked: bool):
        self._anim.stop()
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, v: float):
        self._offset = v
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def sizeHint(self) -> QSize:
        return QSize(34, 18)  # 13px 폰트 라인하이트에 맞춘 크기

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = h / 2
        # 트랙: 상태 색 보간
        t = self._offset
        track = QColor(
            int(_TRACK_OFF.red() + (_TRACK_ON.red() - _TRACK_OFF.red()) * t),
            int(_TRACK_OFF.green() + (_TRACK_ON.green() - _TRACK_OFF.green()) * t),
            int(_TRACK_OFF.blue() + (_TRACK_ON.blue() - _TRACK_OFF.blue()) * t))
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(0, 0, w, h, r, r)
        # 노브
        margin = 3
        d = h - 2 * margin
        x = margin + (w - 2 * margin - d) * t
        p.setBrush(_KNOB)
        p.drawEllipse(int(x), margin, d, d)
        p.end()
