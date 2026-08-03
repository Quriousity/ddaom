"""선택/텍스트박스 아이템 (명세 §3, 2026-08-04 단순화).

아이템은 씬 좌표(=렌더 픽셀)로 그려지지만, 진실은 항상 PDF point 다.
줌이 바뀌면 pdf_view 가 저장된 PDF 좌표로 아이템을 다시 그린다.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsPolygonItem, QGraphicsRectItem

_PEN = QPen(QColor(30, 120, 255), 1.5, Qt.DashLine)
_BRUSH = QBrush(QColor(30, 120, 255, 40))


class RectSelectionItem(QGraphicsRectItem):
    def __init__(self, rect: QRectF):
        super().__init__(rect)
        self.setPen(_PEN)
        self.setBrush(_BRUSH)
        self.setZValue(10)


_PEN_BOX = QPen(QColor(30, 160, 90, 70), 1.0, Qt.SolidLine)
_BRUSH_BOX = QBrush(QColor(30, 160, 90, 0))
_PEN_BOX_HOVER = QPen(QColor(30, 160, 90, 220), 1.5, Qt.SolidLine)
_BRUSH_BOX_HOVER = QBrush(QColor(30, 160, 90, 55))


class TextBoxItem(QGraphicsPolygonItem):
    """자동 스캔된 줄 텍스트 박스 — 호버 하이라이트, 클릭 시 복사."""

    def __init__(self, points: list[QPointF], text: str):
        super().__init__(QPolygonF(points))
        self.text = text
        self.setPen(_PEN_BOX)
        self.setBrush(_BRUSH_BOX)
        self.setZValue(3)  # 선택(10)·리댁션(5) 아래
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def hoverEnterEvent(self, ev):
        self.setPen(_PEN_BOX_HOVER)
        self.setBrush(_BRUSH_BOX_HOVER)
        super().hoverEnterEvent(ev)

    def hoverLeaveEvent(self, ev):
        self.setPen(_PEN_BOX)
        self.setBrush(_BRUSH_BOX)
        super().hoverLeaveEvent(ev)
