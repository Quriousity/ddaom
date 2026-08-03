"""선택 아이템 — 사각형/폴리곤 (명세 §3).

아이템은 씬 좌표(=렌더 픽셀)로 그려지지만, 진실은 항상 PDF point 다.
줌이 바뀌면 pdf_view 가 저장된 PDF 좌표로 아이템을 다시 그린다.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsPolygonItem, QGraphicsRectItem

_PEN = QPen(QColor(30, 120, 255), 1.5, Qt.DashLine)
_BRUSH = QBrush(QColor(30, 120, 255, 40))
_PEN_REDACT = QPen(QColor(220, 40, 40), 1.5, Qt.SolidLine)
_BRUSH_REDACT = QBrush(QColor(220, 40, 40, 60))


class RectSelectionItem(QGraphicsRectItem):
    def __init__(self, rect: QRectF):
        super().__init__(rect)
        self.setPen(_PEN)
        self.setBrush(_BRUSH)
        self.setZValue(10)


class PolygonSelectionItem(QGraphicsPolygonItem):
    def __init__(self, points: list[QPointF]):
        super().__init__(QPolygonF(points))
        self.setPen(_PEN)
        self.setBrush(_BRUSH)
        self.setZValue(10)


class RedactMarkItem(QGraphicsRectItem):
    """리댁션 대기 목록에 들어간 영역 표시 (빨강)."""

    def __init__(self, rect: QRectF):
        super().__init__(rect)
        self.setPen(_PEN_REDACT)
        self.setBrush(_BRUSH_REDACT)
        self.setZValue(5)
