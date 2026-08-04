"""PDF 뷰어 위젯 — 렌더/줌/팬/영역 담기 (명세 §5, 2026-08-04 단순화).

조작은 두 가지뿐이고, 둘 다 '담는다'로 끝난다:
  - 자동 스캔된 텍스트 박스를 클릭 → textBoxClicked (복사 + 담기)
  - 드래그로 영역 지정 → areaCollected (담기)
담긴 것이 곧 파괴 대상이라 드래그 미리보기부터 빨강이다. 목록 관리는 메인윈도우 몫.
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
from .selection import DragPreviewItem, TextBoxItem, TrayRegionItem

Point = tuple[float, float]


class PdfView(QGraphicsView):
    areaCollected = Signal(int, object)  # page_no, fitz.Rect — 드래그를 놓았다
    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    # 박스 클릭 → page_no, 폴리곤 pt, 텍스트. 복사와 담기는 메인윈도우가 판단한다
    # (뷰는 목록을 보관하지 않는다 — 진실은 MainWindow.tray_items 하나뿐)
    textBoxClicked = Signal(int, object, str)
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
        self._preview = None      # 드래그하는 동안만 존재하는 사각형
        # 자동 스캔된 텍스트 박스: page_no -> [(폴리곤 pt, 텍스트)]
        self.text_boxes: dict[int, list] = {}
        self.boxes_visible = True
        # 표시 전용 사본: page_no -> [(region, 강조여부)]. 진실은 MainWindow.tray_items
        self.tray_regions: dict[int, list] = {}

        self._dragging = False
        self._drag_start = QPointF()
        self._space_pan = False
        self._mouse_pan = False          # 우클릭/휠클릭 드래그 팬
        self._pan_last = QPointF()

    # ---------- 문서/페이지 ----------

    def set_document(self, doc: Document):
        self.doc = doc
        self.page_no = 0
        self.text_boxes = {}
        self.clear_preview()
        self.fit_page()
        self._request_scan()

    def show_page(self, page_no: int):
        if not self.doc or not (0 <= page_no < self.doc.page_count):
            return
        self.page_no = page_no
        self.clear_preview()
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

    def set_tray_regions(self, regions: dict[int, list]):
        """{page_no: [(fitz.Rect | 폴리곤 pt, 강조여부), …]} — 표시만 갱신한다."""
        self.tray_regions = regions
        self._render()

    # ---------- 렌더/줌 ----------

    def _render(self):
        if not self.doc:
            return
        png = self.doc.render_page_png(self.page_no, self.zoom)
        img = QImage.fromData(png, "png")
        pm = QPixmap.fromImage(img)
        self.scene().clear()
        self._preview = None
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

    # ---------- 드래그 미리보기 ----------

    def clear_preview(self):
        if self._preview is not None and self._preview.scene() is self.scene():
            self.scene().removeItem(self._preview)
        self._preview = None

    def _redraw_overlays(self):
        """줌/페이지 변경 후 PDF 좌표 -> 씬 아이템 재구성."""
        # 자동 스캔 텍스트 박스 (호버→클릭 복사)
        if self.boxes_visible:
            for poly_pt, text in self.text_boxes.get(self.page_no, []):
                pts = [QPointF(*coords.pdf_to_scene_point(x, y, self.zoom))
                       for x, y in poly_pt]
                self.scene().addItem(TextBoxItem(pts, text, poly_pt))
        # 담은 목록에 들어간 영역 (빨강) — 파괴가 아니라 예약이다
        for region, hi in self.tray_regions.get(self.page_no, []):
            self.scene().addItem(TrayRegionItem(self._region_points(region), hi))

    def _region_points(self, region) -> list[QPointF]:
        """Rect(드래그 영역) 든 폴리곤(글자 박스) 이든 씬 좌표 네 점 이상으로."""
        if isinstance(region, fitz.Rect):
            x0, y0, x1, y1 = coords.pdf_to_scene_rect(region, self.zoom)
            return [QPointF(x0, y0), QPointF(x1, y0), QPointF(x1, y1), QPointF(x0, y1)]
        return [QPointF(*coords.pdf_to_scene_point(x, y, self.zoom)) for x, y in region]

    # ---------- 마우스/키 ----------

    def mousePressEvent(self, ev):
        if not self.doc or self._space_pan:
            return super().mousePressEvent(ev)
        if ev.button() in (Qt.RightButton, Qt.MiddleButton):
            # 모드 없는 팬 — 우클릭/휠클릭 드래그로 문서를 잡고 이동
            self._mouse_pan = True
            self._pan_last = ev.position()
            self.setCursor(Qt.ClosedHandCursor)
            ev.accept()
            return
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start = self.mapToScene(ev.position().toPoint())
            self.clear_preview()
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._mouse_pan:
            d = ev.position() - self._pan_last
            self._pan_last = ev.position()
            h, v = self.horizontalScrollBar(), self.verticalScrollBar()
            h.setValue(h.value() - int(d.x()))
            v.setValue(v.value() - int(d.y()))
            ev.accept()
            return
        if self._dragging:
            sp = self.mapToScene(ev.position().toPoint())
            self._update_rect_preview(self._drag_start, sp)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._mouse_pan and ev.button() in (Qt.RightButton, Qt.MiddleButton):
            self._mouse_pan = False
            self.unsetCursor()
            ev.accept()
            return
        if self._dragging and ev.button() == Qt.LeftButton:
            self._dragging = False
            sp = self.mapToScene(ev.position().toPoint())
            moved = max(abs(sp.x() - self._drag_start.x()),
                        abs(sp.y() - self._drag_start.y()))
            if moved <= config.CLICK_DRAG_THRESHOLD_PX:
                # 드래그가 아니라 클릭 — 텍스트 박스면 복사 + 담기
                self.clear_preview()
                for item in self.scene().items(sp):
                    if isinstance(item, TextBoxItem):
                        self.textBoxClicked.emit(self.page_no, item.poly_pt, item.text)
                        break
                ev.accept()
                return
            r = coords.scene_to_pdf_rect(self._drag_start.x(), self._drag_start.y(),
                                         sp.x(), sp.y(), self.zoom)
            r = coords.clamp_rect(r, self.doc.page_rect(self.page_no))
            self.clear_preview()
            if r.width > 2 and r.height > 2:  # 2pt 미만 드래그는 무시
                # 놓는 즉시 담긴다 — 파괴가 아니라 예약이라 몇 번이든 반복할 수 있다
                self.areaCollected.emit(self.page_no, r)
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
            self.clear_preview()
            ev.accept()
            return
        if ev.key() == Qt.Key_Up:        # ↑/↓ = 페이지 이동 (스크롤은 휠·팬 담당)
            self.prev_page()
            ev.accept()
            return
        if ev.key() == Qt.Key_Down:
            self.next_page()
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

    def contextMenuEvent(self, ev):
        ev.accept()  # 우클릭은 팬 전용 — 컨텍스트 메뉴 없음

    # ---------- 선택 프리뷰 ----------

    def _update_rect_preview(self, a: QPointF, b: QPointF):
        self.clear_preview()
        self._preview = DragPreviewItem(QRectF(a, b).normalized())
        self.scene().addItem(self._preview)
