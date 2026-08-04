"""선택/텍스트박스 아이템 (명세 §3, 2026-08-04 단순화).

아이템은 씬 좌표(=렌더 픽셀)로 그려지지만, 진실은 항상 PDF point 다.
줌이 바뀌면 pdf_view 가 저장된 PDF 좌표로 아이템을 다시 그린다.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsPolygonItem, QGraphicsRectItem

from .. import config

# 드래그 중 미리보기 — 놓는 순간 파괴 대상이 되므로 처음부터 빨강으로 예고한다
_PEN = QPen(QColor(*config.DELETE_REGION_PEN[:3], 230), 1.5, Qt.DashLine)
_BRUSH = QBrush(QColor(*config.DELETE_REGION_FILL[:3], 45))


class DragPreviewItem(QGraphicsRectItem):
    """드래그하는 동안만 보이는 사각형. 놓으면 담은 목록으로 넘어간다."""

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
    """자동 스캔된 줄 텍스트 박스 — 호버 하이라이트, 클릭 시 복사(또는 삭제 목록에 담기).

    poly_pt 는 원본 PDF point 폴리곤이다. 씬 좌표만 들고 있으면 클릭 시
    파괴할 좌표를 복원할 수 없다 — 진실은 언제나 PDF point 다.
    """

    def __init__(self, points: list[QPointF], text: str,
                 poly_pt: list | None = None):
        super().__init__(QPolygonF(points))
        self.text = text
        self.poly_pt = poly_pt
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


_PEN_DEL = QPen(QColor(*config.DELETE_REGION_PEN), 1.2, Qt.SolidLine)
_BRUSH_DEL = QBrush(QColor(*config.DELETE_REGION_FILL))
_PEN_DEL_HI = QPen(QColor(*config.DELETE_REGION_PEN[:3], 255), 2.0, Qt.SolidLine)
_BRUSH_DEL_HI = QBrush(QColor(*config.DELETE_REGION_FILL[:3], 130))


class TrayRegionItem(QGraphicsPolygonItem):
    """담은 목록에 들어간 영역 — 표시일 뿐이다. 저장 전까지 아무것도 파괴되지 않는다.

    마우스를 받지 않는다: 아래에 깔린 TextBoxItem 을 재클릭해 취소할 수 있어야 한다.
    """

    def __init__(self, points: list[QPointF], highlighted: bool = False):
        super().__init__(QPolygonF(points))
        self.setPen(_PEN_DEL_HI if highlighted else _PEN_DEL)
        self.setBrush(_BRUSH_DEL_HI if highlighted else _BRUSH_DEL)
        self.setZValue(5)  # TextBoxItem(3) 위, 선택(10) 아래
        self.setAcceptedMouseButtons(Qt.NoButton)
