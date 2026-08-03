"""메인 윈도우 — 메뉴/툴바/단축키/썸네일/리댁션 패널/상태바 (명세 §5).

OCR·리댁션은 QThreadPool 에서 실행한다. UI 블로킹 금지.
"""
from __future__ import annotations

import os
import traceback

import fitz
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QImage, QKeySequence, QPixmap, QIcon
from PySide6.QtWidgets import (QFileDialog, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox,
                               QPushButton, QSplitter, QToolBar, QVBoxLayout,
                               QWidget)

from .. import config
from ..core import clipboard, extractor, redactor
from ..core.document import BadPassword, Document, NeedsPassword
from ..core.ocr_engine import default_engine
from .pdf_view import PdfView, Tool


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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF 영역 도구")
        self.resize(1280, 860)

        self.doc: Document | None = None
        self.doc_path: str | None = None
        self.pool = QThreadPool.globalInstance()
        self._busy = False

        self.view = PdfView(self)
        self.thumbs = QListWidget()
        self.thumbs.setFixedWidth(config.THUMB_WIDTH + 40)
        self.thumbs.setIconSize(QPixmap(config.THUMB_WIDTH, config.THUMB_WIDTH).size())
        self.thumbs.currentRowChanged.connect(self._on_thumb_clicked)

        # 리댁션 패널
        panel = QWidget()
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(4, 4, 4, 4)
        pv.addWidget(QLabel("리댁션 대기 목록"))
        self.redact_list = QListWidget()
        pv.addWidget(self.redact_list)
        btn_del = QPushButton("선택 항목 삭제")
        btn_del.clicked.connect(self._remove_redaction_entry)
        pv.addWidget(btn_del)
        self.btn_apply = QPushButton("일괄 적용 → 새 PDF 저장")
        self.btn_apply.clicked.connect(self._apply_redactions)
        pv.addWidget(self.btn_apply)
        panel.setFixedWidth(240)

        split = QSplitter()
        split.addWidget(self.thumbs)
        split.addWidget(self.view)
        split.addWidget(panel)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)

        self._make_toolbar()
        self._make_statusbar()

        self.view.selectionChanged.connect(self._on_selection_changed)
        self.view.pageChanged.connect(self._on_page_changed)
        self.view.zoomChanged.connect(lambda z: self._update_status())

        # OCR 프리로드 — 콜드스타트 제거 (§4.6)
        if config.OCR_PRELOAD_ON_START:
            self.ocr_status = "준비 중…"
            w = _Worker(lambda: default_engine().preload())
            w.signals.done.connect(lambda _: self._set_ocr_status("준비됨"))
            w.signals.error.connect(lambda e: self._set_ocr_status("실패"))
            self.pool.start(w)
        else:
            self.ocr_status = "대기"

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

        group = QActionGroup(self)
        self.a_rect = QAction("사각형 (R)", self, checkable=True, checked=True)
        self.a_poly = QAction("폴리곤 (P)", self, checkable=True)
        self.a_pan = QAction("팬 (H)", self, checkable=True)
        for a, key, tool in ((self.a_rect, "R", Tool.RECT),
                             (self.a_poly, "P", Tool.POLY),
                             (self.a_pan, "H", Tool.PAN)):
            a.setShortcut(key)
            a.triggered.connect(lambda _, t=tool: self.view.set_tool(t))
            group.addAction(a)
            tb.addAction(a)
        tb.addSeparator()

        a_copy = QAction("텍스트 복사", self)
        a_copy.setShortcut(QKeySequence.Copy)
        a_copy.triggered.connect(self.copy_text)
        tb.addAction(a_copy)

        a_copy_img = QAction("이미지 복사", self)
        a_copy_img.setShortcut("Ctrl+Shift+C")
        a_copy_img.triggered.connect(self.copy_image)
        tb.addAction(a_copy_img)

        a_save_img = QAction("이미지 저장", self)
        a_save_img.setShortcut("Ctrl+Shift+S")
        a_save_img.triggered.connect(self.save_image)
        tb.addAction(a_save_img)

        a_redact = QAction("리댁션 추가", self)
        a_redact.setShortcut(QKeySequence.Delete)
        a_redact.triggered.connect(self.add_redaction)
        tb.addAction(a_redact)
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

        a_prev = QAction("이전", self)
        a_prev.setShortcut(QKeySequence.MoveToPreviousPage)  # PgUp
        a_prev.triggered.connect(self.view.prev_page)
        tb.addAction(a_prev)
        a_next = QAction("다음", self)
        a_next.setShortcut(QKeySequence.MoveToNextPage)  # PgDn
        a_next.triggered.connect(self.view.next_page)
        tb.addAction(a_next)

    def _make_statusbar(self):
        self.lbl_page = QLabel("- / -")
        self.lbl_zoom = QLabel("100%")
        self.lbl_sel = QLabel("선택 없음")
        self.lbl_ocr = QLabel("OCR: -")
        for w in (self.lbl_page, self.lbl_zoom, self.lbl_sel, self.lbl_ocr):
            self.statusBar().addPermanentWidget(w)

    # ---------- 파일 ----------

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "PDF 열기", "", "PDF (*.pdf)")
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
        self._refresh_redact_list()
        self._update_status()

    def _fill_thumbs(self):
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        for i in range(self.doc.page_count):
            png = self.doc.render_thumb_png(i, config.THUMB_WIDTH)
            img = QImage.fromData(png, "png")
            item = QListWidgetItem(QIcon(QPixmap.fromImage(img)), f"{i + 1}")
            self.thumbs.addItem(item)
        self.thumbs.setCurrentRow(0)
        self.thumbs.blockSignals(False)

    # ---------- 선택/추출 ----------

    def _require_selection(self):
        if not self.doc:
            self.statusBar().showMessage("먼저 PDF 를 여세요", 3000)
            return None
        if not self.view.selection:
            self.statusBar().showMessage("영역을 먼저 선택하세요", 3000)
            return None
        return self.view.selection

    def copy_text(self):
        sel = self._require_selection()
        if not sel or self._busy:
            return
        self._busy = True
        self._set_ocr_status("인식 중…")
        w = _Worker(extractor.extract_text, self.doc, sel.page_no,
                    rect=sel.rect, polygon=sel.polygon)
        w.signals.done.connect(self._on_text_done)
        w.signals.error.connect(self._on_worker_error)
        self.pool.start(w)

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

    def copy_image(self):
        sel = self._require_selection()
        if not sel:
            return
        img = extractor.extract_image(self.doc, sel.page_no,
                                      rect=sel.rect, polygon=sel.polygon)
        clipboard.set_image(img)  # 흰 배경 합성 (§4.4)
        self.statusBar().showMessage(f"이미지 복사됨 ({img.width}×{img.height}px)", 4000)

    def save_image(self):
        sel = self._require_selection()
        if not sel:
            return
        base = os.path.splitext(os.path.basename(self.doc_path or "clip"))[0]
        path, filt = QFileDialog.getSaveFileName(
            self, "이미지 저장", f"{base}_p{sel.page_no + 1}.png",
            "PNG (*.png);;JPEG (*.jpg);;WEBP (*.webp)")
        if not path:
            return
        transparent = sel.polygon is not None and path.lower().endswith(".png")
        img = extractor.extract_image(self.doc, sel.page_no,
                                      rect=sel.rect, polygon=sel.polygon,
                                      transparent_outside=transparent)
        if path.lower().endswith((".jpg", ".jpeg")) and img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(path)
        self.statusBar().showMessage(f"저장됨: {path}", 5000)

    # ---------- 리댁션 ----------

    def add_redaction(self):
        sel = self._require_selection()
        if not sel:
            return
        self.view.add_selection_to_redactions()
        self._refresh_redact_list()

    def _refresh_redact_list(self):
        self.redact_list.clear()
        for page_no in sorted(self.view.redactions):
            for i, s in enumerate(self.view.redactions[page_no]):
                kind = "폴리곤" if isinstance(s, list) else "사각형"
                r = s if not isinstance(s, list) else None
                size = (f"{r.width:.0f}×{r.height:.0f}pt" if r is not None else
                        f"{len(s)}점")
                item = QListWidgetItem(f"p{page_no + 1} {kind} {size}")
                item.setData(Qt.UserRole, (page_no, i))
                self.redact_list.addItem(item)
        n = sum(len(v) for v in self.view.redactions.values())
        self.btn_apply.setEnabled(n > 0)
        self.btn_apply.setText(f"일괄 적용 → 새 PDF 저장 ({n})")

    def _remove_redaction_entry(self):
        item = self.redact_list.currentItem()
        if not item:
            return
        page_no, idx = item.data(Qt.UserRole)
        self.view.remove_redaction(page_no, idx)
        self._refresh_redact_list()

    def _apply_redactions(self):
        if not self.doc_path or not self.view.redactions or self._busy:
            return
        base, ext = os.path.splitext(self.doc_path)
        dst, _ = QFileDialog.getSaveFileName(
            self, "리댁션 PDF 저장", f"{base}_redacted{ext}", "PDF (*.pdf)")
        if not dst:
            return
        if os.path.abspath(dst) == os.path.abspath(self.doc_path):
            QMessageBox.warning(self, "거부", "원본 덮어쓰기는 금지입니다. 다른 이름을 쓰세요.")
            return
        self._busy = True
        self.btn_apply.setEnabled(False)
        w = _Worker(redactor.redact, self.doc_path, dict(self.view.redactions), dst,
                    password=getattr(self, "_doc_password", None))
        w.signals.done.connect(self._on_redact_done)
        w.signals.error.connect(self._on_worker_error)
        self.pool.start(w)

    def _on_redact_done(self, report: redactor.RedactionReport):
        self._busy = False
        self._refresh_redact_list()
        # 검증이 기능의 일부다 (§4.5) — 결과를 반드시 보여준다
        if report.ok:
            QMessageBox.information(self, "리댁션 완료", report.summary())
            self.view.redactions = {}
            self.view.show_page(self.view.page_no)
            self._refresh_redact_list()
        else:
            QMessageBox.critical(self, "리댁션 검증 실패", report.summary())

    # ---------- 상태 ----------

    def _on_worker_error(self, tb: str):
        self._busy = False
        self._set_ocr_status("준비됨")
        self._refresh_redact_list()
        QMessageBox.critical(self, "오류", tb[-1500:])

    def _on_selection_changed(self, sel):
        if sel is None:
            self.lbl_sel.setText("선택 없음")
        else:
            b = sel.bbox()
            self.lbl_sel.setText(f"{sel.kind} {b.width:.0f}×{b.height:.0f}pt")

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
