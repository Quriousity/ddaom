"""PDF 뷰어 위젯 — 렌더/줌/팬/영역 지정 (명세 §5, 2026-08-04 단순화).

조작은 두 가지뿐이다:
  - 자동 스캔된 텍스트 박스를 클릭 → textBoxClicked (즉시 복사)
  - 드래그로 영역 지정 → selectionChanged (복사/저장/파괴는 메인윈도우 몫)
팬은 스페이스 드래그, 줌은 Ctrl+휠.

좌표 규칙: 씬 좌표 = PDF point * zoom. 선택의 진실은 항상 PDF point 로 보관하고
줌이 바뀌면 씬 아이템을 다시 그린다. 좌표 산술은 core.coords 만 쓴다 (§4.1).
"""
from __future__ import annotations

import fitz
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from .. import config
from ..core import coords
from ..core.document import Document
from .selection import RectSelectionItem, TextBoxItem

Point = tuple[float, float]


class Selection:
    """현재 선택 — PDF point 가 진실."""

    def __init__(self, page_no: int, rect: fitz.Rect | None = None,
                 polygon: list[Point] | None = None):
        self.page_no = page_no
        self.rect = rect
        self.polygon = polygon

    def bbox(self) -> fitz.Rect:
        return coords.polygon_bbox(self.polygon) if self.polygon else self.rect


class PdfView(QGraphicsView):
    selectionChanged = Signal(object)   # Selection | None
    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    textBoxClicked = Signal(str)        # 박스 클릭 → 텍스트 (즉시 복사용)
    pageNeedsScan = Signal(int)         # 이 페이지의 텍스트 박스가 아직 없다

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

        self._pix_item: QGraphicsPixmapItem | None = None
        self._sel_item = None
        self.selection: Selection | None = None
        # 자동 스캔된 텍스트 박스: page_no -> [(폴리곤 pt, 텍스트)]
        self.text_boxes: dict[int, list] = {}
        self.boxes_visible = True

        self._dragging = False
        self._drag_start = QPointF()
        self._space_pan = False

    # ---------- 문서/페이지 ----------

    def set_document(self, doc: Document):
        self.doc = doc
        self.page_no = 0
        self.text_boxes = {}
        self.clear_selection()
        self.fit_page()
        self._request_scan()

    def show_page(self, page_no: int):
        if not self.doc or not (0 <= page_no < self.doc.page_count):
            return
        self.page_no = page_no
        self.clear_selection()
        self._render()
        self.pageChanged.emit(page_no)
        self._request_scan()

    def next_page(self):
        self.show_page(self.page_no + 1)

    def prev_page(self):
        self.show_page(self.page_no - 1)

    def _request_scan(self):
        if config.SCAN_ON_PAGE_SHOW and self.page_no not in self.text_boxes:
            self.pageNeedsScan.emit(self.page_no)

    def set_page_boxes(self, page_no: int, boxes: list):
        """스캔 결과 수신 (백그라운드 워커에서 호출됨)."""
        self.text_boxes[page_no] = boxes
        if page_no == self.page_no:
            self._render()

    def set_boxes_visible(self, visible: bool):
        self.boxes_visible = visible
        self._render()

    # ---------- 렌더/줌 ----------

    def _render(self):
        if not self.doc:
            return
        png = self.doc.render_page_png(self.page_no, self.zoom)
        img = QImage.fromData(png, "png")
        pm = QPixmap.fromImage(img)
        self.scene().clear()
        self._sel_item = None
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

    # ---------- 선택 ----------

    def clear_selection(self):
        self.selection = None
        if self._sel_item is not None and self._sel_item.scene() is self.scene():
            self.scene().removeItem(self._sel_item)
        self._sel_item = None
        self.selectionChanged.emit(None)

    def _set_selection(self, sel: Selection):
        self.selection = sel
        self.selectionChanged.emit(sel)

    def _redraw_overlays(self):
        """줌/페이지 변경 후 PDF 좌표 -> 씬 아이템 재구성."""
        # 자동 스캔 텍스트 박스 (호버→클릭 복사)
        if self.boxes_visible:
            for poly_pt, text in self.text_boxes.get(self.page_no, []):
                pts = [QPointF(*coords.pdf_to_scene_point(x, y, self.zoom))
                       for x, y in poly_pt]
                self.scene().addItem(TextBoxItem(pts, text))
        # 현재 선택
        sel = self.selection
        if sel and sel.page_no == self.page_no and sel.rect is not None:
            x0, y0, x1, y1 = coords.pdf_to_scene_rect(sel.rect, self.zoom)
            self._sel_item = RectSelectionItem(QRectF(x0, y0, x1 - x0, y1 - y0))
            self.scene().addItem(self._sel_item)

    # ---------- 마우스/키 ----------

    def mousePressEvent(self, ev):
        if not self.doc or self._space_pan:
            return super().mousePressEvent(ev)
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start = self.mapToScene(ev.position().toPoint())
            self.clear_selection()
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._dragging:
            sp = self.mapToScene(ev.position().toPoint())
            self._update_rect_preview(self._drag_start, sp)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._dragging and ev.button() == Qt.LeftButton:
            self._dragging = False
            sp = self.mapToScene(ev.position().toPoint())
            moved = max(abs(sp.x() - self._drag_start.x()),
                        abs(sp.y() - self._drag_start.y()))
            if moved <= config.CLICK_DRAG_THRESHOLD_PX:
                # 드래그가 아니라 클릭 — 텍스트 박스면 즉시 복사
                self.clear_selection()
                for item in self.scene().items(sp):
                    if isinstance(item, TextBoxItem):
                        self.textBoxClicked.emit(item.text)
                        break
                ev.accept()
                return
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
        if ev.key() == Qt.Key_Escape:
            self.clear_selection()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):
        if ev.key() == Qt.Key_Space and not ev.isAutoRepeat():
            self._space_pan = False
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
