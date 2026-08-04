"""공용 위젯 — 토글 스위치, 담은 목록의 한 행."""
from __future__ import annotations

from PySide6.QtCore import (Property, QEasingCurve, QEvent, QPropertyAnimation,
                            QSize, Qt, Signal)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QLineEdit,
                               QToolButton, QWidget)

from .theme import ACCENT

_TRACK_ON = QColor(ACCENT)          # 테마 액센트(인디고)와 통일
_TRACK_OFF = QColor("#3f3f46")      # zinc-700
_KNOB = QColor("#fafafa")


class ToggleSwitch(QAbstractButton):
    """iOS 풍 온/오프 스위치. checked 가 상태의 진실이다."""

    def __init__(self, parent=None, checked: bool = False,
                 on_color: str | None = None):
        super().__init__(parent)
        self._track_on = QColor(on_color) if on_color else _TRACK_ON
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
        if not self.isEnabled():
            p.setOpacity(0.35)  # 쓸 수 없는 스위치는 눌러보기 전에 보여야 한다
        w, h = self.width(), self.height()
        r = h / 2
        # 트랙: 상태 색 보간
        t = self._offset
        on = self._track_on
        track = QColor(
            int(_TRACK_OFF.red() + (on.red() - _TRACK_OFF.red()) * t),
            int(_TRACK_OFF.green() + (on.green() - _TRACK_OFF.green()) * t),
            int(_TRACK_OFF.blue() + (on.blue() - _TRACK_OFF.blue()) * t))
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


class TrayRow(QWidget):
    """담은 목록의 한 행 — [p1] [고칠 수 있는 글자] [✕].

    글자 편집은 복사에만 영향을 준다. 파괴는 언제나 담을 때 잡아둔 좌표 기준이다.
    """
    removed = Signal()
    edited = Signal(str)
    picked = Signal()      # 이 행을 골랐다 (해당 페이지로 점프)

    def __init__(self, badge: str, text: str, editable: bool = True, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 1, 2, 1)
        lay.setSpacing(6)

        lbl = QLabel(badge)
        lbl.setObjectName("trayBadge")
        lbl.setFixedWidth(24)
        lay.addWidget(lbl)

        self.edit = QLineEdit(text)
        self.edit.setObjectName("trayRowEdit")
        self.edit.setFrame(False)
        self.edit.setReadOnly(not editable)
        self.edit.setCursorPosition(0)
        self.edit.editingFinished.connect(lambda: self.edited.emit(self.edit.text()))
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit, 1)

        btn = QToolButton()
        btn.setText("✕")
        btn.setObjectName("trayRemove")
        btn.setToolTip("목록에서 빼기")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.removed.emit)
        lay.addWidget(btn)

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == QEvent.FocusIn:
            self.picked.emit()
        return super().eventFilter(obj, ev)
