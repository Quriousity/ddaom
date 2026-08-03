"""UI 스모크 테스트 — offscreen 플랫폼에서 기동·열기·선택·복사·파괴 흐름 검증.

실행: QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_ui_smoke.py -v
"""
import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.pdf_view import Selection  # noqa: E402
from app.ui.selection import TextBoxItem  # noqa: E402
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

    def test_actions_disabled_without_selection(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        qapp.processEvents()
        assert not win.a_copy.isEnabled()
        assert not win.a_save_img.isEnabled()
        assert not win.a_destroy.isEnabled()
        win.view._set_selection(Selection(0, rect=fitz.Rect(60, 80, 400, 300)))
        assert win.a_copy.isEnabled()
        assert win.a_save_img.isEnabled()
        assert win.a_destroy.isEnabled()

    def test_select_and_copy_text(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        page_rect = win.doc.page_rect(0)
        win.view._set_selection(Selection(0, rect=fitz.Rect(page_rect)))
        win.copy_selection_text()
        _wait_pool(win, qapp)
        clip = qapp.clipboard().text()
        assert LINES[0] in clip

    def test_save_selection_image(self, win, qapp, tmp_path, monkeypatch):
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        win.view._set_selection(Selection(0, rect=fitz.Rect(60, 80, 400, 300)))
        dst = str(tmp_path / "out.png")
        monkeypatch.setattr(
            "app.ui.main_window.QFileDialog.getSaveFileName",
            staticmethod(lambda *a, **k: (dst, "PNG (*.png)")))
        win.save_selection_image()
        qapp.processEvents()
        assert os.path.exists(dst)
        assert not qapp.clipboard().image().isNull()  # 저장 + 클립보드 동시

    def test_destroy_selection(self, win, qapp, tmp_path):
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        # SECRET 줄 영역을 잡아 파괴
        d = fitz.open(os.path.join(OUT, "text.pdf"))
        w0 = next(w for w in d[0].get_text("words") if "900101" in w[4])
        d.close()
        sel = Selection(0, rect=fitz.Rect(w0[0] - 5, w0[1] - 5, w0[2] + 5, w0[3] + 5))
        win.view._set_selection(sel)
        dst = str(tmp_path / "destroyed.pdf")
        # 다이얼로그 없이 내부 경로로 직접 (검증 다이얼로그는 information — monkeypatch)
        import app.ui.main_window as mw
        infos = []
        orig_info = mw.QMessageBox.information
        mw.QMessageBox.information = staticmethod(
            lambda *a, **k: infos.append(a[2] if len(a) > 2 else ""))
        try:
            win._destroy_to(sel, dst)
            _wait_pool(win, qapp)
        finally:
            mw.QMessageBox.information = orig_info
        assert os.path.exists(dst)
        assert infos and "OK" in infos[0]
        d2 = fitz.open(dst)
        assert "900101" not in d2[0].get_text()
        assert "김철수" in d2[0].get_text()
        d2.close()

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


class TestTextBoxes:
    def test_scan_and_click_copy(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)   # 자동 스캔 완료 대기
        boxes = win.view.text_boxes.get(0)
        assert boxes, "페이지 텍스트 박스가 스캔되지 않았다"
        # 씬에 TextBoxItem 이 깔렸다
        items = [i for i in win.view.scene().items() if isinstance(i, TextBoxItem)]
        assert len(items) == len(boxes)
        # 클릭 복사 경로: 시그널 -> 클립보드
        target = next(t for _, t in boxes if "김철수" in t)
        win.view.textBoxClicked.emit(target)
        qapp.processEvents()
        assert "김철수" in qapp.clipboard().text()

    def test_boxes_toggle(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        win.view.set_boxes_visible(False)
        assert not [i for i in win.view.scene().items() if isinstance(i, TextBoxItem)]
        win.view.set_boxes_visible(True)
        assert [i for i in win.view.scene().items() if isinstance(i, TextBoxItem)]

    def test_scan_ocr_page(self, win, qapp):
        win.open_file(os.path.join(OUT, "scan.pdf"))
        _wait_pool(win, qapp)
        boxes = win.view.text_boxes.get(0)
        assert boxes
        assert any("김철수" in t for _, t in boxes)

    def test_toggle_switch_wired(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        assert win.sw_boxes.isChecked()
        win.sw_boxes.toggle()   # off
        qapp.processEvents()
        assert not win.view.boxes_visible
        assert not [i for i in win.view.scene().items() if isinstance(i, TextBoxItem)]
        win.sw_boxes.toggle()   # on
        qapp.processEvents()
        assert win.view.boxes_visible
