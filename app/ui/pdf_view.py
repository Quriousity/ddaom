"""PDF 뷰어 위젯 — 렌더/줌/팬/선택 (명세 §5).

좌표 규칙: 씬 좌표 = PDF point * zoom. 선택의 진실은 항상 PDF point 로 보관하고
줌이 바뀌면 씬 아이템을 다시 그린다. 좌표 산술은 core.coords 만 쓴다 (§4.1).
"""
from __future__ import annotations

from enum import Enum, auto

import fitz
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from ..core import coords
from ..core.document import Document
from .selection import PolygonSelectionItem, RectSelectionItem, RedactMarkItem

Point = tuple[float, float]


class Tool(Enum):
    RECT = auto()
    POLY = auto()
    PAN = auto()


class Selection:
    """현재 선택 — PDF point 가 진실."""

    def __init__(self, page_no: int, rect: fitz.Rect | None = None,
                 polygon: list[Point] | None = None):
        self.page_no = page_no
        self.rect = rect
        self.polygon = polygon

    @property
    def kind(self) -> str:
        return "polygon" if self.polygon else "rect"

    def bbox(self) -> fitz.Rect:
        return coords.polygon_bbox(self.polygon) if self.polygon else self.rect


class PdfView(QGraphicsView):
    selectionChanged = Signal(object)   # Selection | None
    pageChanged = Signal(int)
    zoomChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)

        self.doc: Document | None = None
        self.page_no = 0
        self.zoom = 1.0
        self.tool = Tool.RECT

        self._pix_item: QGraphicsPixmapItem | None = None
        self._sel_item = None
        self._redact_items: list[RedactMarkItem] = []
        self.selection: Selection | None = None
        self.redactions: dict[int, list] = {}  # page_no -> [fitz.Rect | polygon(pt)]

        self._dragging = False
        self._drag_start = QPointF()
        self._poly_pts_scene: list[QPointF] = []
        self._space_pan = False

    # ---------- 문서/페이지 ----------

    def set_document(self, doc: Document):
        self.doc = doc
        self.page_no = 0
        self.redactions = {}
        self.clear_selection()
        self.fit_page()

    def show_page(self, page_no: int):
        if not self.doc or not (0 <= page_no < self.doc.page_count):
            return
        self.page_no = page_no
        self.clear_selection()
        self._render()
        self.pageChanged.emit(page_no)

    def next_page(self):
        self.show_page(self.page_no + 1)

    def prev_page(self):
        self.show_page(self.page_no - 1)

    # ---------- 렌더/줌 ----------

    def _render(self):
        if not self.doc:
            return
        png = self.doc.render_page_png(self.page_no, self.zoom)
        img = QImage.fromData(png, "png")
        pm = QPixmap.fromImage(img)
        self.scene().clear()
        self._sel_item = None
        self._redact_items = []
        self._pix_item = self.scene().addPixmap(pm)
        self.scene().setSceneRect(0, 0, pm.width(), pm.height())
        self._redraw_overlays()

    def set_zoom(self, zoom: float, anchor_scene: QPointF | None = None):
        zoom = max(0.1, min(zoom, 8.0))
        if not self.doc or abs(zoom - self.zoom) < 1e-9:
            return
        # 앵커 지점(PDF pt) 유지
        if anchor_scene is None:
            anchor_scene = self.mapToScene(self.viewport().rect().center())
        pt = coords.scene_to_pdf_point(anchor_scene.x(), anchor_scene.y(), self.zoom)
        self.zoom = zoom
        self._render()
        nx, ny = coords.pdf_to_scene_point(pt[0], pt[1], self.zoom)
        self.centerOn(nx, ny)
        self.zoomChanged.emit(zoom)

    def fit_page(self):
        if not self.doc:
            return
        rect = self.doc.page_rect(self.page_no)
        vw = max(self.viewport().width() - 8, 50)
        vh = max(self.viewport().height() - 8, 50)
        self.zoom = min(vw / rect.width, vh / rect.height)
        self._render()
        self.zoomChanged.emit(self.zoom)

    def zoom_in(self):
        self.set_zoom(self.zoom * 1.25)

    def zoom_out(self):
        self.set_zoom(self.zoom / 1.25)

    # ---------- 도구/선택 ----------

    def set_tool(self, tool: Tool):
        self.tool = tool
        self._poly_pts_scene = []
        self.setDragMode(QGraphicsView.ScrollHandDrag if tool == Tool.PAN
                         else QGraphicsView.NoDrag)

    def clear_selection(self):
        self.selection = None
        self._poly_pts_scene = []
        if self._sel_item is not None and self._sel_item.scene() is self.scene():
            self.scene().removeItem(self._sel_item)
        self._sel_item = None
        self.selectionChanged.emit(None)

    def _set_selection(self, sel: Selection):
        self.selection = sel
        self.selectionChanged.emit(sel)

    def _redraw_overlays(self):
        """줌/페이지 변경 후 PDF 좌표 -> 씬 아이템 재구성."""
        # 리댁션 대기 영역
        for s in self.redactions.get(self.page_no, []):
            r = coords.polygon_bbox(s) if isinstance(s, list) else s
            x0, y0, x1, y1 = coords.pdf_to_scene_rect(r, self.zoom)
            item = RedactMarkItem(QRectF(x0, y0, x1 - x0, y1 - y0))
            self.scene().addItem(item)
            self._redact_items.append(item)
        # 현재 선택
        sel = self.selection
        if sel and sel.page_no == self.page_no:
            if sel.polygon:
                pts = [QPointF(*coords.pdf_to_scene_point(x, y, self.zoom))
                       for x, y in sel.polygon]
                self._sel_item = PolygonSelectionItem(pts)
            else:
                x0, y0, x1, y1 = coords.pdf_to_scene_rect(sel.rect, self.zoom)
                self._sel_item = RectSelectionItem(QRectF(x0, y0, x1 - x0, y1 - y0))
            self.scene().addItem(self._sel_item)

    # ---------- 리댁션 목록 ----------

    def add_selection_to_redactions(self):
        if not self.selection:
            return
        sel = self.selection
        entry = sel.polygon if sel.polygon else sel.rect
        self.redactions.setdefault(sel.page_no, []).append(entry)
        self.clear_selection()
        self._render()

    def remove_redaction(self, page_no: int, index: int):
        try:
            del self.redactions[page_no][index]
            if not self.redactions[page_no]:
                del self.redactions[page_no]
        except (KeyError, IndexError):
            return
        if page_no == self.page_no:
            self._render()

    # ---------- 마우스/키 ----------

    def mousePressEvent(self, ev):
        if not self.doc or self.tool == Tool.PAN or self._space_pan:
            return super().mousePressEvent(ev)
        if ev.button() == Qt.LeftButton:
            sp = self.mapToScene(ev.position().toPoint())
            if self.tool == Tool.RECT:
                self._dragging = True
                self._drag_start = sp
                self.clear_selection()
            elif self.tool == Tool.POLY:
                self._poly_pts_scene.append(sp)
                self._update_poly_preview()
            ev.accept()
            return
        if ev.button() == Qt.RightButton and self.tool == Tool.POLY and self._poly_pts_scene:
            self._finish_polygon()
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._dragging and self.tool == Tool.RECT:
            sp = self.mapToScene(ev.position().toPoint())
            self._update_rect_preview(self._drag_start, sp)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._dragging and ev.button() == Qt.LeftButton and self.tool == Tool.RECT:
            self._dragging = False
            sp = self.mapToScene(ev.position().toPoint())
            r = coords.scene_to_pdf_rect(self._drag_start.x(), self._drag_start.y(),
                                         sp.x(), sp.y(), self.zoom)
            r = coords.clamp_rect(r, self.doc.page_rect(self.page_no))
            if r.width > 2 and r.height > 2:  # 2pt 미만 드래그는 무시
                self._set_selection(Selection(self.page_no, rect=r))
            else:
                self.clear_selection()
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if self.tool == Tool.POLY and self._poly_pts_scene:
            self._finish_polygon()
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            anchor = self.mapToScene(ev.position().toPoint())
            factor = 1.25 if ev.angleDelta().y() > 0 else 1 / 1.25
            self.set_zoom(self.zoom * factor, anchor)
            ev.accept()
            return
        super().wheelEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Space and not ev.isAutoRepeat():
            self._space_pan = True
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            ev.accept()
            return
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and self.tool == Tool.POLY:
            self._finish_polygon()
            ev.accept()
            return
        if ev.key() == Qt.Key_Escape:
            self.clear_selection()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        if ev.key() == Qt.Key_Space and not ev.isAutoRepeat():
            self._space_pan = False
            if self.tool != Tool.PAN:
                self.setDragMode(QGraphicsView.NoDrag)
            ev.accept()
            return
        super().keyReleaseEvent(ev)

    # ---------- 선택 프리뷰 ----------

    def _update_rect_preview(self, a: QPointF, b: QPointF):
        if self._sel_item is not None and self._sel_item.scene() is self.scene():
            self.scene().removeItem(self._sel_item)
        self._sel_item = RectSelectionItem(QRectF(a, b).normalized())
        self.scene().addItem(self._sel_item)

    def _update_poly_preview(self):
        if self._sel_item is not None and self._sel_item.scene() is self.scene():
            self.scene().removeItem(self._sel_item)
        if len(self._poly_pts_scene) >= 2:
            self._sel_item = PolygonSelectionItem(self._poly_pts_scene)
            self.scene().addItem(self._sel_item)

    def _finish_polygon(self):
        if len(self._poly_pts_scene) >= 3:
            poly_pt = coords.scene_to_pdf_polygon(
                [(p.x(), p.y()) for p in self._poly_pts_scene], self.zoom)
            self._set_selection(Selection(self.page_no, polygon=poly_pt))
        self._poly_pts_scene = []
