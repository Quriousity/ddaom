"""메인 윈도우 (명세 §5, 2026-08-04 단순화).

UX: 조작은 두 가지뿐이고 둘 다 '담는다'로 끝난다.
  - 글자 박스 클릭 → 클립보드 복사 + 담은 목록에 담기
  - 영역 드래그   → 담은 목록에 담기 (놓는 즉시)
이미지 저장은 선택과 무관하게 **현재 페이지 통째로**다.
**모드는 없다.** 담은 목록이 곧 파괴 목록이고, `이대로 저장하기` 가 그것을
한 번에 파괴해 원본 형식으로 저장하는 유일한 출구다. 빼려면 행의 ✕ 를 누른다.
OCR·리댁션은 QThreadPool 에서 실행한다. UI 블로킹 금지.
"""
from __future__ import annotations

import os
import traceback
from dataclasses import dataclass

import fitz
from PySide6.QtCore import (QObject, QRunnable, QSize, Qt, QThreadPool, QTimer,
                            Signal, Slot)
from PySide6.QtGui import (QAction, QCursor, QGuiApplication, QIcon, QImage,
                           QKeySequence, QPixmap)
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPushButton, QSizePolicy, QToolBar,
                               QVBoxLayout, QWidget)

from .. import config
from ..core import capability, clipboard, coords, extractor, redactor
from ..core.document import BadPassword, Document, NeedsPassword
from ..core.ocr_engine import default_engine
from .pdf_view import PdfView
from .widgets import ToggleSwitch, TrayRow, startup_geometry


class _Worker(QRunnable):
    class Signals(QObject):
        done = Signal(object)
        error = Signal(object)   # (예외, 트레이스백) — 예외 자체가 사용자용 설명이다

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Worker.Signals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            try:
                # 예외 자체도 넘긴다 — 일부러 던진 오류는 그 문장이 곧 사용자용 설명이다
                self.signals.error.emit((e, traceback.format_exc()))
            except RuntimeError:
                pass  # 앱 종료 중 — 시그널 대상이 이미 파괴됨
            return
        try:
            self.signals.done.emit(result)
        except RuntimeError:
            pass  # 앱 종료 중


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


@dataclass
class TrayItem:
    """담은 목록의 한 건. 좌표는 언제나 PDF point 다.

    담긴 것이 곧 파괴 대상이다 — 목록 = 파괴 목록. 빼려면 행의 ✕ 를 누른다.
    저장을 누르기 전까지는 아무것도 파괴되지 않는다.
    """
    page_no: int
    region: object          # fitz.Rect(드래그 영역) | [(x, y), …](글자 박스)
    text: str               # 표시·복사용. 고쳐도 파괴는 region 기준이다
    kind: str               # "box" | "area"

    def key(self) -> tuple:
        """같은 자리를 또 담았는지 판정 — 0.1pt 격자로 반올림해 비교한다."""
        if isinstance(self.region, fitz.Rect):
            pts = ((self.region.x0, self.region.y0), (self.region.x1, self.region.y1))
        else:
            pts = tuple(self.region)
        return (self.kind, self.page_no,
                tuple((round(x, 1), round(y, 1)) for x, y in pts))

    def bbox(self) -> fitz.Rect:
        if isinstance(self.region, fitz.Rect):
            return self.region
        return coords.polygon_bbox(self.region)

    def badge(self) -> str:
        return f"p{self.page_no + 1}"

    def label(self) -> str:
        if self.kind == "box":
            return " ".join(self.text.split()) or "글자 상자"
        b = self.bbox()
        return f"영역 {b.width:.0f}×{b.height:.0f}pt"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("따옴")
        # 커서가 있는 모니터에 띄운다 (멀티모니터에서 보고 있던 화면이 맞다)
        screen = (QGuiApplication.screenAt(QCursor.pos())
                  or QGuiApplication.primaryScreen())
        self.setGeometry(startup_geometry(screen.availableGeometry()))

        self.doc: Document | None = None
        self.doc_path: str | None = None
        self.pool = QThreadPool.globalInstance()
        self._busy = False
        # 담은 목록 = 파괴 목록. 이게 유일한 진실이다 (뷰는 표시만 한다)
        self.tray_items: list[TrayItem] = []
        self.can_destroy = True  # 문서를 열 때 판정한다 (capability.probe)
        self._default_dst = ""   # 파괴 결과의 기본 저장 경로 (원본 옆)
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

        # 담은 목록 — 클릭·드래그로 고른 것이 쌓인다. 이게 그대로 파괴 대상이다
        self.tray_panel = QWidget()
        self.tray_panel.setFixedWidth(280)
        self.tray_panel.setObjectName("tray")
        tv = QVBoxLayout(self.tray_panel)
        tv.setContentsMargins(10, 10, 10, 10)
        tv.setSpacing(8)

        self.tray_head = QLabel("담은 목록")
        self.tray_head.setObjectName("trayTitle")
        tv.addWidget(self.tray_head)

        self.tray_list = QListWidget()
        self.tray_list.setObjectName("trayList")
        self.tray_list.setFrameShape(QListWidget.Shape.NoFrame)
        self.tray_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.tray_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tv.addWidget(self.tray_list, 1)

        self.tray_hint = QLabel("글자 상자를 클릭하거나 영역을 드래그해\n담으세요. 담은 것이 파괴 대상입니다.")
        self.tray_hint.setObjectName("trayHint")
        self.tray_hint.setWordWrap(True)
        tv.addWidget(self.tray_hint)

        row = QHBoxLayout()
        self.btn_tray_copy = QPushButton("전체 복사")
        self.btn_tray_copy.setToolTip("담은 글자를 줄바꿈으로 이어 클립보드에 복사")
        self.btn_tray_copy.clicked.connect(self._copy_tray)
        self.btn_tray_clear = QPushButton("전체 비우기")
        self.btn_tray_clear.clicked.connect(self._clear_tray)
        row.addWidget(self.btn_tray_copy)
        row.addWidget(self.btn_tray_clear)
        tv.addLayout(row)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.thumbs)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.tray_panel)
        self.setCentralWidget(central)

        self._make_statusbar()   # 툴바보다 먼저 — _update_actions 가 상태바를 쓴다
        self._make_toolbar()
        self._refresh_tray()

        self.view.areaCollected.connect(self._on_area_collected)
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
        self.a_save_img = QAction("현재 페이지 이미지로 저장", self)
        self.a_save_img.setShortcut(QKeySequence.Save)
        self.a_save_img.setToolTip("지금 보고 있는 페이지를 통째로 PNG 로 저장 (Ctrl+S)")
        self.a_save_img.triggered.connect(self.save_page_image)
        tb.addAction(self.a_save_img)

        # 담은 것을 실제로 파괴해 저장하는 유일한 곳. 되돌릴 수 없으니 단축키는 없다
        self.a_save_doc = QAction("담은 목록 파괴하고 원본형식으로 저장", self)
        self.a_save_doc.setToolTip(
            "담은 목록을 되살릴 수 없게 파괴해 저장 (PDF→PDF, 이미지→PNG)")
        self.a_save_doc.triggered.connect(self.save_destroyed)
        tb.addAction(self.a_save_doc)
        btn_save_doc = tb.widgetForAction(self.a_save_doc)
        if btn_save_doc:  # 되돌릴 수 없는 실행 — hover 시 빨강 (theme.py #danger)
            btn_save_doc.setObjectName("danger")
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

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        self.a_thumbs_toggle = QAction("미리보기", self, checkable=True, checked=True)
        self.a_thumbs_toggle.setShortcut("[")
        self.a_thumbs_toggle.setToolTip("페이지 미리보기 접기/펴기 ( [ )")
        self.a_thumbs_toggle.toggled.connect(lambda _: self._update_panels_visible())
        tb.addAction(self.a_thumbs_toggle)

        self.a_tray_toggle = QAction("담은 목록", self, checkable=True, checked=True)
        self.a_tray_toggle.setShortcut("]")
        self.a_tray_toggle.setToolTip("담은 목록 패널 접기/펴기 ( ] )")
        self.a_tray_toggle.toggled.connect(lambda _: self._update_panels_visible())
        tb.addAction(self.a_tray_toggle)

        self._update_actions()

    def _update_actions(self):
        self.a_save_img.setEnabled(self.doc is not None)
        n = len(self.tray_items)
        self.lbl_sel.setText(
            f"클릭=복사+담기 · 드래그=영역 담기 · 우클릭 드래그=이동"
            + (f" · 담긴 {n}건" if n else ""))
        # 담은 게 있어야 파괴할 게 있다. 파괴 불가 문서면 담기는 되지만 저장은 막힌다
        self.a_save_doc.setEnabled(bool(self.tray_items) and self.can_destroy
                                   and not self._busy)
        if not self.can_destroy:
            self.a_save_doc.setToolTip("이 문서는 파괴할 수 없습니다 — 복사·이미지 저장만 됩니다")
        else:
            self.a_save_doc.setToolTip(
                "담은 목록을 되살릴 수 없게 파괴해 저장 (PDF→PDF, 이미지→PNG)")

    def _make_statusbar(self):
        self.lbl_page = QLabel("- / -")
        self.lbl_zoom = QLabel("100%")
        self.lbl_sel = QLabel("")
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
        if not self._confirm_discard("다른 문서를 열면 "):
            return
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
            except Exception as e:   # 손상·미지원 — 여는 것 자체가 안 된다
                QMessageBox.critical(
                    self, "열 수 없습니다",
                    f"{os.path.basename(path)}\n\n이 파일은 읽을 수 없습니다.\n\n({e})")
                return

        # 이 문서로 무엇을 할 수 있는지 먼저 판정한다 — 다 골라놓은 뒤에 알려주면 늦다
        default_dst = _next_redacted_path(
            path, out_ext=".png" if doc.is_image_source else None)
        cap = capability.probe(doc, default_dst)
        if not cap.can_read:
            doc.close()
            QMessageBox.critical(self, "열 수 없습니다",
                                 f"{os.path.basename(path)}\n\n{cap.read_error}")
            return

        if self.doc:
            self.doc.close()
        self.doc = doc
        self.doc_path = path
        self._doc_password = password
        self._default_dst = default_dst
        self.setWindowTitle(f"따옴 — {os.path.basename(path)}")
        self.view.set_document(doc)
        # 담긴 좌표는 이전 문서의 것이다 — 문서가 바뀌면 무조건 버린다 (위에서 경고했다)
        self.tray_items.clear()
        self._refresh_tray()
        self._fill_thumbs()
        self._update_status()
        self._apply_capability(cap)

    def _apply_capability(self, cap: capability.Capability):
        """③ 다 되면 조용히. ② 파괴가 막혔으면 한 번 경고하고 저장을 잠근다."""
        self.can_destroy = cap.can_destroy
        self._update_actions()
        if cap.silent:
            return

        fix_dir = redactor.fixable_dir(self._default_dst)
        text = (f"{os.path.basename(self.doc_path)}\n\n"
                "이 파일은 읽을 수 있어 복사·이미지 저장은 되지만, 파괴는 할 수 없습니다.\n"
                "파괴 결과는 원본 옆에 새 파일로 저장되는데, 그럴 수 없기 때문입니다.\n\n"
                f"{cap.destroy_error}\n\n")
        text += ("아래 '이 폴더에 쓰기 허용'을 누르면 폴더에 쓰기 권한을 주고 파괴를 풀어줍니다."
                 if fix_dir else
                 "파일을 쓰기 가능한 폴더로 옮긴 뒤 다시 여세요.")
        if self._warn_cannot_destroy(text, fix_dir):
            self._grant_write_and_recheck(fix_dir)

    def _warn_cannot_destroy(self, text: str, fix_dir: str | None) -> bool:
        """경고를 보이고, 사용자가 '쓰기 허용'을 골랐으면 True."""
        if not fix_dir:
            QMessageBox.warning(self, "복사만 됩니다", text)
            return False
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("복사만 됩니다")
        box.setText(text)
        btn_fix = box.addButton("이 폴더에 쓰기 허용", QMessageBox.AcceptRole)
        box.addButton("그대로 두기", QMessageBox.RejectRole)
        box.setDefaultButton(btn_fix)
        box.exec()
        return box.clickedButton() is btn_fix

    def _grant_write_and_recheck(self, fix_dir: str):
        """권한을 주고 능력을 다시 판정한다 — 풀렸으면 파괴 경로를 되살린다."""
        try:
            redactor.grant_write(fix_dir)
        except Exception as e:
            QMessageBox.critical(self, "권한을 바꾸지 못했습니다",
                                 f"{fix_dir}\n\n({e})")
            return
        cap = capability.probe(self.doc, self._default_dst)
        self.can_destroy = cap.can_destroy
        self._update_actions()
        if cap.can_destroy:
            self.statusBar().showMessage(f"쓰기 권한을 주었습니다 — 이제 파괴할 수 있습니다: {fix_dir}",
                                         6000)
        else:
            QMessageBox.warning(self, "아직 막혀 있습니다", cap.destroy_error)

    def _update_panels_visible(self):
        multi = bool(self.doc) and self.doc.page_count > 1
        self.thumbs.setVisible(self.a_thumbs_toggle.isChecked() and multi)
        self.tray_panel.setVisible(self.a_tray_toggle.isChecked())

    def _fill_thumbs(self):
        # 1페이지 문서엔 썸네일 사이드바가 무의미하다 — 토글과 무관하게 숨긴다
        self._update_panels_visible()
        if self.doc.page_count <= 1:
            return
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

    def _on_scan_error(self, page_no: int, err):
        self._scanning_pages.discard(page_no)
        self._set_ocr_status("준비됨")
        self.statusBar().showMessage("페이지 스캔 실패", 4000)

    def _on_text_box_clicked(self, page_no: int, poly_pt, text: str):
        """클릭 한 번이 두 가지를 한다 — 클립보드로 복사하고, 목록에 담는다."""
        clipboard.set_text(text)
        added = self._add_tray_item(TrayItem(page_no, list(poly_pt), text, "box"))
        self.statusBar().showMessage(
            f"복사 + 담김 ({len(self.tray_items)}건): {text[:50]}" if added
            else f"복사됨 (이미 담긴 자리): {text[:50]}", 4000)

    # ---------- 담은 목록 = 파괴 목록 ----------

    def _confirm_discard(self, lead: str) -> bool:
        """담긴 게 있으면 경고한다. 확인하면 정말로 잃는다 (몰래 들고 있지 않는다)."""
        n = len(self.tray_items)
        if n == 0:
            return True
        r = QMessageBox.warning(
            self, "담은 목록이 사라집니다",
            f"{lead}담은 목록 {n}건이 사라집니다.\n계속할까요?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return r == QMessageBox.Yes

    def _on_area_collected(self, page_no: int, rect):
        """드래그를 놓으면 바로 담긴다 — 파괴가 아니라 예약이라 몇 번이든 반복된다."""
        self._add_tray_item(TrayItem(page_no, fitz.Rect(rect), "", "area"))
        self.statusBar().showMessage(
            f"영역 담김 — 총 {len(self.tray_items)}건 (저장하기 전까지 파괴되지 않습니다)", 4000)

    def _add_tray_item(self, item: TrayItem) -> bool:
        """이미 담긴 자리면 중복해서 넣지 않는다. 뺄 때는 행의 ✕ 를 쓴다."""
        k = item.key()
        if any(existing.key() == k for existing in self.tray_items):
            return False
        self.tray_items.append(item)
        self._refresh_tray()
        return True

    def _refresh_tray(self, highlight: int = -1):
        n = len(self.tray_items)
        self.tray_head.setText(f"담은 목록 ({n}건)" if n else "담은 목록")
        self.tray_hint.setVisible(n == 0)
        self.btn_tray_copy.setEnabled(n > 0)
        self.btn_tray_clear.setEnabled(n > 0)
        self.tray_list.clear()
        for i, it in enumerate(self.tray_items):
            row = TrayRow(it.badge(), it.label(), editable=(it.kind == "box"))
            row.removed.connect(lambda _=None, k=it.key(): self._remove_tray_item(k))
            row.edited.connect(lambda t, k=it.key(): self._edit_tray_item(k, t))
            row.picked.connect(lambda _=None, idx=i: self._pick_tray_row(idx))
            entry = QListWidgetItem(self.tray_list)
            entry.setSizeHint(row.sizeHint())
            self.tray_list.addItem(entry)
            self.tray_list.setItemWidget(entry, row)
        self._push_tray_regions(highlight)
        self._update_actions()

    def _push_tray_regions(self, highlight: int = -1):
        """뷰에는 표시용 사본만 넘긴다 — 진실은 tray_items 하나뿐."""
        regions: dict[int, list] = {}
        for i, it in enumerate(self.tray_items):
            regions.setdefault(it.page_no, []).append((it.region, i == highlight))
        self.view.set_tray_regions(regions)

    def _index_of(self, key: tuple) -> int:
        for i, it in enumerate(self.tray_items):
            if it.key() == key:
                return i
        return -1

    def _remove_tray_item(self, key: tuple):
        i = self._index_of(key)
        if i >= 0:
            del self.tray_items[i]
            self._refresh_tray()
            self.statusBar().showMessage(f"목록에서 뺐습니다 — 남은 {len(self.tray_items)}건", 3000)

    def _edit_tray_item(self, key: tuple, text: str):
        """글자만 바뀐다 — 파괴는 담을 때 잡아둔 좌표 기준이다."""
        i = self._index_of(key)
        if i >= 0:
            self.tray_items[i].text = text

    def _pick_tray_row(self, index: int):
        if not (0 <= index < len(self.tray_items)):
            return
        it = self.tray_items[index]
        if it.page_no != self.view.page_no:
            self.view.show_page(it.page_no)
        self._push_tray_regions(index)

    def _clear_tray(self):
        if not self.tray_items:
            return
        r = QMessageBox.question(
            self, "전체 비우기", f"담은 {len(self.tray_items)}건을 모두 비웁니다.\n계속할까요?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        self.tray_items.clear()
        self._refresh_tray()

    def save_destroyed(self):
        """담은 목록을 파괴해 원본과 같은 형식으로 저장한다 — 파괴의 유일한 출구."""
        if self._busy or not self.doc or not self.doc_path or not self.tray_items:
            return
        pages = sorted({it.page_no for it in self.tray_items})
        preview = "\n".join(f"  · {it.badge()} {it.label()[:34]}"
                            for it in self.tray_items[:3])
        if len(self.tray_items) > 3:
            preview += f"\n  · … 외 {len(self.tray_items) - 3}건"
        r = QMessageBox.warning(
            self, "파괴해서 저장",
            f"{len(self.tray_items)}건 · {len(pages)}개 페이지를 파괴합니다.\n"
            f"되돌릴 수 없습니다.\n\n{preview}\n\n계속할까요?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        if self.doc.is_image_source:  # 이미지 원본 → 결과도 이미지(PNG 재렌더)
            dst, _ = QFileDialog.getSaveFileName(
                self, "파괴된 이미지 저장",
                _next_redacted_path(self.doc_path, out_ext=".png"), "PNG (*.png)")
        else:
            dst, _ = QFileDialog.getSaveFileName(
                self, "파괴된 PDF 저장", _next_redacted_path(self.doc_path), "PDF (*.pdf)")
        if not dst or not self._dst_ok(dst):
            return

        sel_map: dict[int, list] = {}
        for it in self.tray_items:
            sel_map.setdefault(it.page_no, []).append(it.region)
        self._busy = True
        self.a_save_doc.setEnabled(False)
        self.statusBar().showMessage("파괴 중…")
        if self.doc.is_image_source:
            w = _Worker(redactor.redact_image, self.doc_path, sel_map, dst)
        else:
            w = _Worker(redactor.redact, self.doc_path, sel_map, dst,
                        password=getattr(self, "_doc_password", None))
        self._start_worker(w, self._on_destroy_done, self._on_worker_error)

    def _on_destroy_done(self, report: redactor.RedactionReport):
        self._busy = False
        if not report.ok:
            # 실패하면 목록을 유지한다 — 다시 시도할 수 있어야 한다
            self._refresh_tray()
            QMessageBox.critical(self, "파괴 검증 실패", report.summary())
            return
        self.tray_items.clear()
        self._refresh_tray()
        r = QMessageBox.question(
            self, "파괴 완료", report.summary() + "\n\n저장본을 열까요?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r == QMessageBox.Yes:
            self.open_file(report.dst_path)

    # ---------- 현재 페이지 이미지로 저장 ----------

    def save_page_image(self):
        """지금 보고 있는 페이지를 통째로 내보낸다 — 드래그 선택과 무관하다."""
        if not self.doc or not self.doc_path:
            self.statusBar().showMessage("먼저 문서를 여세요", 3000)
            return
        page_no = self.view.page_no
        path, _ = QFileDialog.getSaveFileName(
            self, "현재 페이지 이미지로 저장", _next_image_path(self.doc_path, page_no),
            "PNG (*.png);;JPEG (*.jpg);;WEBP (*.webp)")
        if not path:
            return
        # 화면 해상도가 아니라 EXPORT_DPI 로 다시 렌더한다 (§4.4)
        img = extractor.extract_image(self.doc, page_no,
                                      rect=self.doc.page_rect(page_no))
        if path.lower().endswith((".jpg", ".jpeg")) and img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(path)
        # 클립보드는 건드리지 않는다 — 담은 글자를 복사해 둔 걸 페이지 그림이 덮으면 곤란하다
        self.statusBar().showMessage(f"{page_no + 1}쪽 저장됨: {path}", 5000)

    # ---------- 저장 경로 검사 ----------

    def _dst_ok(self, dst: str) -> bool:
        """저장 전에 막는다 — 다 파괴해놓고 마지막에 실패하면 이유를 알 수 없다."""
        if os.path.abspath(dst) == os.path.abspath(self.doc_path):
            QMessageBox.warning(self, "거부", "원본 덮어쓰기는 금지입니다. 다른 이름을 쓰세요.")
            return False
        blocker = redactor.save_blocker(dst)
        if blocker:
            QMessageBox.warning(self, "저장할 수 없음",
                                f"{blocker}\n\n다른 폴더를 고르세요.")
            return False
        return True

    def _copy_tray(self):
        t = "\n".join(it.text for it in self.tray_items if it.text).strip()
        if t:
            clipboard.set_text(t)
            self.statusBar().showMessage(
                f"담은 글자 {len(self.tray_items)}건을 클립보드에 복사했습니다", 4000)
        else:
            self.statusBar().showMessage("복사할 글자가 없습니다 (영역 항목뿐)", 3000)

    # ---------- 상태 ----------

    def _on_worker_error(self, err):
        self._busy = False
        self._set_ocr_status("준비됨")
        self._refresh_tray()  # 실패해도 목록은 남는다 → 저장 버튼을 되살린다
        exc, tb = err if isinstance(err, tuple) else (None, str(err))
        # 파괴를 스스로 멈춘 경우 — 사용자에게 그 문장을 그대로 보인다.
        # 라이브러리 오류를 감싼 것(raise ... from e)이면 추적도 접어서 함께 준다:
        # 그쪽은 우리가 예상한 실패가 아니라 문의로 이어질 일이다.
        if isinstance(exc, (ValueError, RuntimeError, OSError)):
            self._show_destroy_error(str(exc), tb if exc.__cause__ else None)
            return
        QMessageBox.critical(self, "오류", tb[-1500:])

    def _show_destroy_error(self, text: str, detail: str | None) -> None:
        """파괴 실패 알림. detail 이 있으면 '자세히'로 접어 둔다."""
        box = QMessageBox(QMessageBox.Critical, "파괴하지 못했습니다", text,
                          QMessageBox.Ok, self)
        if detail:
            box.setDetailedText(detail)
        box.exec()

    def closeEvent(self, ev):
        if not self._confirm_discard("앱을 닫으면 "):
            ev.ignore()
            return
        super().closeEvent(ev)

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
