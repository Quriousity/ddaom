"""메인 윈도우 (명세 §5, 2026-08-04 단순화).

UX: 페이지를 열면 자동 스캔된 텍스트 박스를 클릭 → 즉시 복사.
영역을 드래그로 지정한 뒤엔 세 가지뿐:
  ① 클립보드에 복사 (텍스트)   ② 이미지로 저장   ③ 영역 파괴 → PDF 저장
모드 전환·리댁션 대기 목록은 없다.
OCR·리댁션은 QThreadPool 에서 실행한다. UI 블로킹 금지.
"""
from __future__ import annotations

import os
import traceback

from PySide6.QtCore import (QObject, QRunnable, QSize, Qt, QThreadPool, QTimer,
                            Signal, Slot)
from PySide6.QtGui import QAction, QIcon, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QToolBar, QWidget)

from .. import config
from ..core import clipboard, extractor, redactor
from ..core.document import BadPassword, Document, NeedsPassword
from ..core.ocr_engine import default_engine
from .pdf_view import PdfView
from .widgets import ToggleSwitch


class _Worker(QRunnable):
    class Signals(QObject):
        done = Signal(object)
        error = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Worker.Signals()

    @Slot()
    def run(self):
        try:
            self.signals.done.emit(self.fn(*self.args, **self.kwargs))
        except Exception:
            self.signals.error.emit(traceback.format_exc())


def _next_image_path(doc_path: str, page_no: int) -> str:
    """원본 폴더에 {원본명}_p{페이지}_{연번2자리}.png — 절대 덮어쓰지 않는 첫 번호."""
    d = os.path.dirname(doc_path)
    stem = os.path.splitext(os.path.basename(doc_path))[0]
    for i in range(1, 100):
        p = os.path.join(d, f"{stem}_p{page_no + 1}_{i:02d}.png")
        if not os.path.exists(p):
            return p
    return os.path.join(d, f"{stem}_p{page_no + 1}_99.png")


def _next_redacted_path(doc_path: str, out_ext: str | None = None) -> str:
    """원본 폴더에 {원본명}_redacted.{확장자} — 있으면 _redacted2, _redacted3 …

    이미지 원본이면 out_ext=".png" 로 호출해 결과도 이미지로 만든다.
    """
    d = os.path.dirname(doc_path)
    stem, ext = os.path.splitext(os.path.basename(doc_path))
    ext = out_ext or ext
    p = os.path.join(d, f"{stem}_redacted{ext}")
    n = 2
    while os.path.exists(p):
        p = os.path.join(d, f"{stem}_redacted{n}{ext}")
        n += 1
    return p


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF 영역 도구")
        self.resize(1280, 860)

        self.doc: Document | None = None
        self.doc_path: str | None = None
        self.pool = QThreadPool.globalInstance()
        self._busy = False
        # ⚠ 워커 참조 유지 — 없으면 GC 로 완료 시그널이 유실된다
        self._workers: set[_Worker] = set()

        self.view = PdfView(self)
        # 문서 영역과 같은 톤 — 색 단차 제거
        self.view.setBackgroundBrush(self.palette().window())
        self.view.setFrameShape(QListWidget.Shape.NoFrame)

        # 썸네일: 중앙정렬 + 페이지번호는 썸네일 아래 (IconMode 그리드)
        self.thumbs = QListWidget()
        sidebar_w = config.THUMB_WIDTH + 44
        self.thumbs.setFixedWidth(sidebar_w)
        self.thumbs.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbs.setMovement(QListWidget.Movement.Static)
        self.thumbs.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumbs.setIconSize(QSize(config.THUMB_WIDTH, int(config.THUMB_WIDTH * 1.45)))
        self.thumbs.setFrameShape(QListWidget.Shape.NoFrame)
        self.thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 선택 = 테두리 강조선만 (썸네일을 덮지 않는다), 경계는 1px 헤어라인
        self.thumbs.setStyleSheet(
            "QListWidget { background: transparent; outline: none;"
            "  border-right: 1px solid rgba(128,128,128,70); }"
            "QListWidget::item { background: transparent; border: 2px solid transparent;"
            "  margin: 6px 0px; }"  # 좌우 margin 0 — 가로 중앙은 그리드가 맡는다
            "QListWidget::item:selected { background: transparent;"
            "  border: 2px solid palette(highlight); border-radius: 3px; }")
        self.thumbs.currentRowChanged.connect(self._on_thumb_clicked)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.thumbs)
        lay.addWidget(self.view, 1)
        self.setCentralWidget(central)

        self._make_toolbar()
        self._make_statusbar()

        self.view.selectionChanged.connect(self._on_selection_changed)
        self.view.pageChanged.connect(self._on_page_changed)
        self.view.zoomChanged.connect(lambda z: self._update_status())
        self.view.textBoxClicked.connect(self._on_text_box_clicked)
        self.view.pageNeedsScan.connect(self._scan_page)
        self._scanning_pages: set[int] = set()

        # OCR 프리로드 — 콜드스타트 제거 (§4.6)
        self.ocr_status = "대기"
        if config.OCR_PRELOAD_ON_START:
            self.ocr_status = "준비 중…"
            self._start_worker(_Worker(lambda: default_engine().preload()),
                               lambda _: self._set_ocr_status("준비됨"),
                               lambda e: self._set_ocr_status("실패"))

    def showEvent(self, ev):
        # 창이 처음 표시된 뒤 페이지 맞춤 — 레이아웃 전 fit 계산으로 6% 줌이 되는 것 방지
        super().showEvent(ev)
        if self.doc and not getattr(self, "_did_first_fit", False):
            self._did_first_fit = True
            QTimer.singleShot(0, self.view.fit_page)

    def _start_worker(self, w: _Worker, on_done, on_error):
        self._workers.add(w)

        def _done(res):
            self._workers.discard(w)
            on_done(res)

        def _err(e):
            self._workers.discard(w)
            on_error(e)

        w.signals.done.connect(_done)
        w.signals.error.connect(_err)
        self.pool.start(w)

    # ---------- 툴바/단축키 ----------

    def _make_toolbar(self):
        tb = QToolBar("main")
        tb.setMovable(False)
        self.addToolBar(tb)

        a_open = QAction("열기", self)
        a_open.setShortcut(QKeySequence.Open)
        a_open.triggered.connect(self.open_file_dialog)
        tb.addAction(a_open)
        tb.addSeparator()

        # 영역 지정 후 할 수 있는 세 가지 — 이게 전부다
        self.a_copy = QAction("클립보드에 복사", self)
        self.a_copy.setShortcut(QKeySequence.Copy)
        self.a_copy.triggered.connect(self.copy_selection_text)
        tb.addAction(self.a_copy)

        self.a_save_img = QAction("이미지로 저장", self)
        self.a_save_img.setShortcut(QKeySequence.Save)
        self.a_save_img.triggered.connect(self.save_selection_image)
        tb.addAction(self.a_save_img)

        self.a_destroy = QAction("영역 파괴 → PDF 저장", self)
        self.a_destroy.setShortcut("Ctrl+D")
        self.a_destroy.triggered.connect(self.destroy_selection)
        tb.addAction(self.a_destroy)
        btn_destroy = tb.widgetForAction(self.a_destroy)
        if btn_destroy:  # 파괴 버튼은 hover 시 빨강 (theme.py #danger)
            btn_destroy.setObjectName("danger")
        tb.addSeparator()

        # 글자 인식 표시 — 토글 스위치 (T)
        box_wrap = QWidget()
        box_lay = QHBoxLayout(box_wrap)
        box_lay.setContentsMargins(8, 0, 8, 0)
        box_lay.setSpacing(6)
        box_lay.addWidget(QLabel("글자 인식 표시"))
        self.sw_boxes = ToggleSwitch(checked=True)
        self.sw_boxes.setToolTip("글자 영역을 자동 인식해 표시 — 클릭 한 번으로 복사 (T)")
        self.sw_boxes.toggled.connect(self.view.set_boxes_visible)
        box_lay.addWidget(self.sw_boxes)
        tb.addWidget(box_wrap)
        # 단축키 T 는 그대로
        a_boxes_key = QAction(self)
        a_boxes_key.setShortcut("T")
        a_boxes_key.triggered.connect(self.sw_boxes.toggle)
        self.addAction(a_boxes_key)
        tb.addSeparator()

        a_fit = QAction("맞춤", self)
        a_fit.setShortcut("Ctrl+0")
        a_fit.triggered.connect(self.view.fit_page)
        tb.addAction(a_fit)
        a_zi = QAction("확대", self)
        a_zi.setShortcut(QKeySequence.ZoomIn)
        a_zi.triggered.connect(self.view.zoom_in)
        tb.addAction(a_zi)
        a_zo = QAction("축소", self)
        a_zo.setShortcut(QKeySequence.ZoomOut)
        a_zo.triggered.connect(self.view.zoom_out)
        tb.addAction(a_zo)

        self._update_action_enabled(None)

    def _update_action_enabled(self, sel):
        has = sel is not None
        for a in (self.a_copy, self.a_save_img, self.a_destroy):
            a.setEnabled(has)

    def _make_statusbar(self):
        self.lbl_page = QLabel("- / -")
        self.lbl_zoom = QLabel("100%")
        self.lbl_sel = QLabel("드래그=영역 지정 · 클릭=글자 복사 · 우클릭 드래그=이동")
        self.lbl_ocr = QLabel("OCR: -")
        for w in (self.lbl_page, self.lbl_zoom, self.lbl_sel, self.lbl_ocr):
            self.statusBar().addPermanentWidget(w)

    # ---------- 파일 ----------

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "문서 열기", "",
            "문서/이미지 (*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if path:
            self.open_file(path)

    def open_file(self, path: str):
        password = None
        while True:
            try:
                doc = Document(path, password=password)
                break
            except NeedsPassword:
                password, ok = QInputDialog.getText(self, "암호", "PDF 암호를 입력하세요:")
                if not ok:
                    return
            except BadPassword:
                QMessageBox.warning(self, "암호 오류", "암호가 틀렸습니다.")
                password, ok = QInputDialog.getText(self, "암호", "PDF 암호를 입력하세요:")
                if not ok:
                    return
        if self.doc:
            self.doc.close()
        self.doc = doc
        self.doc_path = path
        self._doc_password = password
        self.setWindowTitle(f"PDF 영역 도구 — {os.path.basename(path)}")
        self.view.set_document(doc)
        self._fill_thumbs()
        self._update_status()

    def _fill_thumbs(self):
        # 1페이지 문서엔 썸네일 사이드바가 무의미하다 — 숨긴다
        if self.doc.page_count <= 1:
            self.thumbs.hide()
            return
        self.thumbs.show()
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        for i in range(self.doc.page_count):
            png = self.doc.render_thumb_png(i, config.THUMB_WIDTH)
            pm = QPixmap.fromImage(QImage.fromData(png, "png"))
            icon = QIcon()
            icon.addPixmap(pm, QIcon.Mode.Normal)
            icon.addPixmap(pm, QIcon.Mode.Selected)  # 선택 시 파란 틴트 방지
            item = QListWidgetItem(icon, f"{i + 1}")
            self.thumbs.addItem(item)
        self.thumbs.setCurrentRow(0)
        self.thumbs.blockSignals(False)
        # 그리드 폭 = 실제 뷰포트 폭 → 썸네일 가로 중앙 정렬 (스크롤바 유무 반영)
        QTimer.singleShot(0, self._update_thumb_grid)

    def _update_thumb_grid(self):
        w = self.thumbs.viewport().width()
        if w > 20:
            self.thumbs.setGridSize(QSize(w, int(config.THUMB_WIDTH * 1.45) + 34))

    # ---------- 텍스트 박스 자동 스캔 (호버→클릭 복사) ----------

    def _scan_page(self, page_no: int):
        if not self.doc or page_no in self._scanning_pages:
            return
        self._scanning_pages.add(page_no)
        self._set_ocr_status("페이지 스캔 중…")
        doc = self.doc
        self._start_worker(
            _Worker(extractor.scan_page_boxes, doc, page_no),
            lambda res, p=page_no, d=doc: self._on_scan_done(d, p, res),
            lambda e, p=page_no: self._on_scan_error(p, e))

    def _on_scan_done(self, doc, page_no: int, result):
        self._scanning_pages.discard(page_no)
        if doc is not self.doc:  # 그 사이 다른 문서를 열었다
            return
        boxes, source = result
        self.view.set_page_boxes(page_no, boxes)
        self._set_ocr_status("준비됨")
        if page_no == self.view.page_no:
            self.statusBar().showMessage(
                f"텍스트 상자 {len(boxes)}개 "
                f"({'글자층' if source == 'text-layer' else 'OCR'}) — 클릭하면 복사", 4000)

    def _on_scan_error(self, page_no: int, tb: str):
        self._scanning_pages.discard(page_no)
        self._set_ocr_status("준비됨")
        self.statusBar().showMessage("페이지 스캔 실패", 4000)

    def _on_text_box_clicked(self, text: str):
        clipboard.set_text(text)
        self.statusBar().showMessage(f"복사됨: {text[:60]}", 4000)

    # ---------- ① 클립보드에 복사 (텍스트) ----------

    def _require_selection(self):
        if not self.doc:
            self.statusBar().showMessage("먼저 PDF 를 여세요", 3000)
            return None
        if not self.view.selection:
            self.statusBar().showMessage("영역을 먼저 드래그하세요", 3000)
            return None
        return self.view.selection

    def copy_selection_text(self):
        sel = self._require_selection()
        if not sel or self._busy:
            return
        self._busy = True
        self._set_ocr_status("인식 중…")
        self._start_worker(
            _Worker(extractor.extract_text, self.doc, sel.page_no,
                    rect=sel.rect, polygon=sel.polygon),
            self._on_text_done, self._on_worker_error)

    def _on_text_done(self, result):
        text, source = result
        self._busy = False
        self._set_ocr_status("준비됨")
        if text:
            clipboard.set_text(text)
            first = text.splitlines()[0][:40]
            self.statusBar().showMessage(
                f"복사됨 ({'글자층' if source == 'text-layer' else 'OCR'}): {first}…", 5000)
        else:
            self.statusBar().showMessage("영역에서 텍스트를 찾지 못했습니다", 4000)

    # ---------- ② 이미지로 저장 ----------

    def save_selection_image(self):
        sel = self._require_selection()
        if not sel:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "이미지로 저장", _next_image_path(self.doc_path, sel.page_no),
            "PNG (*.png);;JPEG (*.jpg);;WEBP (*.webp)")
        if not path:
            return
        img = extractor.extract_image(self.doc, sel.page_no,
                                      rect=sel.rect, polygon=sel.polygon)
        if path.lower().endswith((".jpg", ".jpeg")) and img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(path)
        clipboard.set_image(img)  # 저장하면서 클립보드에도 넣어준다 (§4.4 흰 배경 합성)
        self.statusBar().showMessage(f"저장됨 (+클립보드): {path}", 5000)

    # ---------- ③ 영역 파괴 → PDF 저장 ----------

    def destroy_selection(self):
        sel = self._require_selection()
        if not sel or not self.doc_path or self._busy:
            return
        if self.doc.is_image_source:  # 이미지 원본 → 결과도 이미지(PNG 재렌더)
            dst, _ = QFileDialog.getSaveFileName(
                self, "파괴된 이미지 저장",
                _next_redacted_path(self.doc_path, out_ext=".png"), "PNG (*.png)")
        else:
            dst, _ = QFileDialog.getSaveFileName(
                self, "파괴된 PDF 저장", _next_redacted_path(self.doc_path), "PDF (*.pdf)")
        if not dst:
            return
        if os.path.abspath(dst) == os.path.abspath(self.doc_path):
            QMessageBox.warning(self, "거부", "원본 덮어쓰기는 금지입니다. 다른 이름을 쓰세요.")
            return
        self._destroy_to(sel, dst)

    def _destroy_to(self, sel, dst: str):
        entry = sel.polygon if sel.polygon else sel.rect
        self._busy = True
        if self.doc.is_image_source:
            w = _Worker(redactor.redact_image, self.doc_path,
                        {sel.page_no: [entry]}, dst)
        else:
            w = _Worker(redactor.redact, self.doc_path, {sel.page_no: [entry]}, dst,
                        password=getattr(self, "_doc_password", None))
        self._start_worker(w, self._on_destroy_done, self._on_worker_error)

    def _on_destroy_done(self, report: redactor.RedactionReport):
        self._busy = False
        # 검증이 기능의 일부다 (§4.5) — 결과를 반드시 보여준다
        if report.ok:
            QMessageBox.information(self, "파괴 완료", report.summary())
            self.view.clear_selection()
        else:
            QMessageBox.critical(self, "파괴 검증 실패", report.summary())

    # ---------- 상태 ----------

    def _on_worker_error(self, tb: str):
        self._busy = False
        self._set_ocr_status("준비됨")
        QMessageBox.critical(self, "오류", tb[-1500:])

    def _on_selection_changed(self, sel):
        self._update_action_enabled(sel)
        if sel is None:
            self.lbl_sel.setText("드래그=영역 지정 · 클릭=글자 복사 · 우클릭 드래그=이동")
        else:
            b = sel.bbox()
            self.lbl_sel.setText(f"선택 {b.width:.0f}×{b.height:.0f}pt — "
                                 f"복사(Ctrl+C)/저장(Ctrl+S)/파괴(Ctrl+D)")

    def _on_page_changed(self, page_no: int):
        self.thumbs.blockSignals(True)
        self.thumbs.setCurrentRow(page_no)
        self.thumbs.blockSignals(False)
        self._update_status()

    def _on_thumb_clicked(self, row: int):
        if row >= 0:
            self.view.show_page(row)

    def _set_ocr_status(self, s: str):
        self.ocr_status = s
        self.lbl_ocr.setText(f"OCR: {s}")

    def _update_status(self):
        if self.doc:
            self.lbl_page.setText(f"{self.view.page_no + 1} / {self.doc.page_count}")
            self.lbl_zoom.setText(f"{self.view.zoom * 100:.0f}%")
        self.lbl_ocr.setText(f"OCR: {self.ocr_status}")
