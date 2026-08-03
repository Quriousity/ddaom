"""UI 스모크 테스트 — offscreen 플랫폼에서 기동·열기·선택·복사·리댁션 흐름 검증.

실행: QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_ui_smoke.py -v
"""
import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.pdf_view import Selection, Tool  # noqa: E402
from tools.make_samples import LINES, OUT  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def win(qapp):
    w = MainWindow()
    yield w
    if w.doc:
        w.doc.close()
        w.doc = None


def _wait_pool(win, qapp, timeout_ms=60000):
    win.pool.waitForDone(timeout_ms)
    qapp.processEvents()


class TestSmoke:
    def test_open_and_render(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        qapp.processEvents()
        assert win.doc is not None
        assert win.doc.page_count == 1
        assert win.thumbs.count() == 1
        assert win.view.scene().sceneRect().width() > 0

    def test_select_and_copy_text(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        qapp.processEvents()
        page_rect = win.doc.page_rect(0)
        win.view._set_selection(Selection(0, rect=fitz.Rect(page_rect)))
        win.copy_text()
        _wait_pool(win, qapp)
        clip = qapp.clipboard().text()
        assert LINES[0] in clip

    def test_copy_image(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        qapp.processEvents()
        win.view._set_selection(Selection(0, rect=fitz.Rect(60, 80, 400, 300)))
        win.copy_image()
        img = qapp.clipboard().image()
        assert not img.isNull()
        assert img.width() > 100

    def test_add_redaction_flow(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        qapp.processEvents()
        win.view._set_selection(Selection(0, rect=fitz.Rect(60, 480, 400, 520)))
        win.add_redaction()
        assert win.redact_list.count() == 1
        assert 0 in win.view.redactions
        # 목록 삭제
        win.redact_list.setCurrentRow(0)
        win._remove_redaction_entry()
        assert win.redact_list.count() == 0
        assert not win.view.redactions

    def test_zoom_keeps_selection_coords(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        qapp.processEvents()
        r = fitz.Rect(72, 100, 300, 200)
        win.view._set_selection(Selection(0, rect=fitz.Rect(r)))
        z0 = win.view.zoom
        win.view.set_zoom(z0 * 2)
        qapp.processEvents()
        sel = win.view.selection
        assert sel is not None
        # §8-3: 줌을 바꿔도 PDF 좌표 불변
        assert abs(sel.rect.x0 - 72) < 1e-6 and abs(sel.rect.y1 - 200) < 1e-6

    def test_tool_switch(self, win, qapp):
        win.view.set_tool(Tool.POLY)
        assert win.view.tool == Tool.POLY
        win.view.set_tool(Tool.PAN)
        assert win.view.tool == Tool.PAN
