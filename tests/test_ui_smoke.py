"""UI 스모크 테스트 — offscreen 플랫폼에서 기동·열기·선택·복사·파괴 흐름 검증.

실행: QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_ui_smoke.py -v
"""
import os

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.main_window import MainWindow  # noqa: E402
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
        assert win.thumbs.isHidden()  # 1페이지 문서 -> 썸네일 사이드바 숨김
        assert win.view.scene().sceneRect().width() > 0

    def test_multipage_shows_thumbs(self, win, qapp, tmp_path):
        import fitz as _f
        path = str(tmp_path / "three.pdf")
        d = _f.open()
        for i in range(3):
            pg = d.new_page(width=595, height=842)
            pg.insert_text((72, 100), f"page {i + 1}", fontsize=20)
        d.save(path)
        d.close()
        win.open_file(path)
        qapp.processEvents()
        assert not win.thumbs.isHidden()
        assert win.thumbs.count() == 3
        win.thumbs.setCurrentRow(2)   # 썸네일 클릭 -> 페이지 이동
        qapp.processEvents()
        assert win.view.page_no == 2

    def test_actions_disabled_without_selection(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        qapp.processEvents()
        assert win.a_save_img.isEnabled()       # 페이지 저장은 언제나 된다
        assert not win.a_save_doc.isEnabled()   # 담은 게 없으면 파괴할 것도 없다
        win.view.areaCollected.emit(0, fitz.Rect(60, 80, 400, 300))
        qapp.processEvents()
        assert win.a_save_doc.isEnabled()       # 담기면 살아난다

    def test_save_page_image(self, win, qapp, tmp_path, monkeypatch):
        """선택과 무관하게 현재 페이지를 통째로 내보낸다."""
        from PIL import Image
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        dst = str(tmp_path / "out.png")
        monkeypatch.setattr(
            "app.ui.main_window.QFileDialog.getSaveFileName",
            staticmethod(lambda *a, **k: (dst, "PNG (*.png)")))
        assert win.a_save_img.isEnabled()
        win.save_page_image()
        qapp.processEvents()
        assert os.path.exists(dst)
        # 페이지 전체가 나왔는지 — 가로세로 비가 page.rect 와 맞는다
        page = win.doc.page_rect(0)
        img = Image.open(dst)
        assert abs(img.width / img.height - page.width / page.height) < 0.02

    def test_page_image_keeps_clipboard(self, win, qapp, tmp_path, monkeypatch):
        """담아 둔 글자를 페이지 그림이 덮으면 안 된다."""
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        qapp.clipboard().setText("소중한 텍스트")
        monkeypatch.setattr(
            "app.ui.main_window.QFileDialog.getSaveFileName",
            staticmethod(lambda *a, **k: (str(tmp_path / "p.png"), "PNG (*.png)")))
        win.save_page_image()
        qapp.processEvents()
        assert qapp.clipboard().text() == "소중한 텍스트"

    def test_destroy_selection(self, win, qapp, tmp_path):
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        # SECRET 줄 영역을 잡아 파괴
        d = fitz.open(os.path.join(OUT, "text.pdf"))
        w0 = next(w for w in d[0].get_text("words") if "900101" in w[4])
        d.close()
        win.view.areaCollected.emit(0, fitz.Rect(w0[0] - 5, w0[1] - 5,
                                                 w0[2] + 5, w0[3] + 5))
        qapp.processEvents()
        assert len(win.tray_items) == 1
        dst = str(tmp_path / "destroyed.pdf")
        import app.ui.main_window as mw
        from PySide6.QtWidgets import QFileDialog
        answers = []
        orig = (mw.QMessageBox.warning, mw.QMessageBox.question,
                QFileDialog.getSaveFileName)
        mw.QMessageBox.warning = staticmethod(
            lambda *a, **k: answers.append(a[2]) or mw.QMessageBox.Yes)
        mw.QMessageBox.question = staticmethod(lambda *a, **k: mw.QMessageBox.No)
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (dst, ""))
        try:
            win.save_destroyed()                   # 담은 것을 파괴해 저장
            _wait_pool(win, qapp)
        finally:
            (mw.QMessageBox.warning, mw.QMessageBox.question,
             QFileDialog.getSaveFileName) = orig
        assert os.path.exists(dst)
        assert win.tray_items == []                # 성공하면 목록을 비운다
        d = fitz.open(dst)
        assert "900101" not in d[0].get_text()
        d.close()
        d2 = fitz.open(dst)
        assert "900101" not in d2[0].get_text()
        assert "도길동" in d2[0].get_text()
        d2.close()

    def test_zoom_keeps_collected_coords(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        qapp.processEvents()
        win.view.areaCollected.emit(0, fitz.Rect(72, 100, 300, 200))
        qapp.processEvents()
        win.view.set_zoom(win.view.zoom * 2)
        qapp.processEvents()
        r = win.tray_items[0].region
        # §8-3: 줌을 바꿔도 PDF 좌표 불변
        assert abs(r.x0 - 72) < 1e-6 and abs(r.y1 - 200) < 1e-6


class TestTextBoxes:
    def test_scan_and_click_copy(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)   # 자동 스캔 완료 대기
        boxes = win.view.text_boxes.get(0)
        assert boxes, "페이지 텍스트 박스가 스캔되지 않았다"
        # 씬에 TextBoxItem 이 깔렸다
        items = [i for i in win.view.scene().items() if isinstance(i, TextBoxItem)]
        assert len(items) == len(boxes)
        # 클릭 한 번이 복사 + 담기를 같이 한다
        poly, target = next((p, t) for p, t in boxes if "도길동" in t)
        win.view.textBoxClicked.emit(0, poly, target)
        qapp.processEvents()
        assert "도길동" in qapp.clipboard().text()
        assert len(win.tray_items) == 1

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
        assert any("도길동" in t for _, t in boxes)

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


class TestPan:
    def test_right_drag_pans(self, win, qapp):
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtGui import QMouseEvent
        win.open_file(os.path.join(OUT, "text.pdf"))
        qapp.processEvents()
        win.view.set_zoom(3.0)   # 스크롤 가능한 상태로
        qapp.processEvents()
        v0 = win.view.verticalScrollBar().value()
        press = QMouseEvent(QEvent.MouseButtonPress, QPointF(200, 200),
                            _Qt.RightButton, _Qt.RightButton, _Qt.NoModifier)
        move = QMouseEvent(QEvent.MouseMove, QPointF(200, 120),
                           _Qt.NoButton, _Qt.RightButton, _Qt.NoModifier)
        release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(200, 120),
                              _Qt.RightButton, _Qt.RightButton, _Qt.NoModifier)
        win.view.mousePressEvent(press)
        win.view.mouseMoveEvent(move)
        win.view.mouseReleaseEvent(release)
        assert win.view.verticalScrollBar().value() == v0 + 80  # 위로 80px 끌었다
        assert win.tray_items == []  # 팬은 아무것도 담지 않는다


class TestNeverSilentlyUnredacted:
    """'저장은 됐는데 안 지워진' 파일이 나오는 길을 막는다.

    한때 clamp_rect 가 자른 뒤 normalize() 를 불러, 페이지 밖 선택이 좌표가 뒤바뀌며
    '페이지 안의 엉뚱한 사각형'으로 되살아났다. 그 사각형은 아무것도 지우지 않는데
    검증(지정 영역 안의 잔여만 본다)은 통과해서 OK 로 저장됐다.
    """

    def test_clamp_never_flips_coordinates(self):
        from app.core import coords
        page = fitz.Rect(0, 0, 300, 200)
        for outside in (fitz.Rect(400, 50, 500, 120),      # 오른쪽 여백
                        fitz.Rect(50, 300, 200, 400),      # 아래 여백
                        fitz.Rect(-200, -200, -100, -100)):  # 왼쪽 위 바깥
            r = coords.clamp_rect(outside, page)
            assert r.is_empty, f"{outside} 가 {r} 로 되살아났다"
        # 일부만 걸친 선택은 살아남되 페이지 안으로 잘린다
        r = coords.clamp_rect(fitz.Rect(-50, -50, 100, 100), page)
        assert r == fitz.Rect(0, 0, 100, 100)

    def test_offpage_selection_refuses_to_save(self, tmp_path):
        from app.core import redactor
        src, dst = str(tmp_path / "a.pdf"), str(tmp_path / "a_out.pdf")
        d = fitz.open()
        d.new_page(width=300, height=200).insert_text((30, 60), "SECRET", fontsize=14)
        d.save(src); d.close()
        with pytest.raises(ValueError):
            redactor.redact(src, {0: [fitz.Rect(900, 900, 950, 950)]}, dst)
        assert not os.path.exists(dst), "지우지도 않고 파일을 만들었다"

    def test_one_bad_selection_aborts_all(self, tmp_path):
        """유효한 선택과 섞여 있어도 통째로 거부한다 — 반만 지운 파일이 더 위험하다."""
        from app.core import redactor
        src, dst = str(tmp_path / "b.pdf"), str(tmp_path / "b_out.pdf")
        d = fitz.open()
        d.new_page(width=300, height=200).insert_text((30, 60), "SECRET", fontsize=14)
        d.save(src); d.close()
        with pytest.raises(ValueError):
            redactor.redact(src, {0: [fitz.Rect(20, 40, 250, 75),
                                      fitz.Rect(900, 900, 950, 950)]}, dst)
        assert not os.path.exists(dst)

    def test_page_with_no_usable_selection_aborts(self, tmp_path):
        from app.core import redactor
        src, dst = str(tmp_path / "c.pdf"), str(tmp_path / "c_out.pdf")
        d = fitz.open()
        for _ in range(2):
            d.new_page(width=300, height=200).insert_text((30, 60), "SECRET", fontsize=14)
        d.save(src); d.close()
        with pytest.raises(ValueError):
            redactor.redact(src, {0: [fitz.Rect(20, 40, 250, 75)],
                                  1: [fitz.Rect(900, 900, 950, 950)]}, dst)
        assert not os.path.exists(dst)
        d = fitz.open(src)
        assert "SECRET" in d[1].get_text()   # 원본은 그대로
        d.close()

    def test_unknown_page_aborts(self, tmp_path):
        from app.core import redactor
        src, dst = str(tmp_path / "d.pdf"), str(tmp_path / "d_out.pdf")
        d = fitz.open(); d.new_page(width=300, height=200); d.save(src); d.close()
        with pytest.raises(ValueError):
            redactor.redact(src, {5: [fitz.Rect(10, 10, 50, 50)]}, dst)
        assert not os.path.exists(dst)

    def test_empty_selection_aborts(self, tmp_path):
        from app.core import redactor
        src, dst = str(tmp_path / "e.pdf"), str(tmp_path / "e_out.pdf")
        d = fitz.open(); d.new_page(width=300, height=200); d.save(src); d.close()
        with pytest.raises(ValueError):
            redactor.redact(src, {}, dst)
        assert not os.path.exists(dst)

    def test_scan_without_text_layer_is_still_verified(self, tmp_path):
        """글자층이 없는 스캔본 — 텍스트 검사만으론 언제나 통과한다. 픽셀도 본다."""
        from app.core import redactor
        src, dst = str(tmp_path / "scan.pdf"), str(tmp_path / "scan_out.pdf")
        tmp = fitz.open()
        tp = tmp.new_page(width=300, height=200)
        tp.insert_text((30, 60), "SECRET", fontsize=14)
        png = str(tmp_path / "s.png")
        tp.get_pixmap(dpi=150).save(png)
        tmp.close()
        d = fitz.open()
        pg = d.new_page(width=300, height=200)
        pg.insert_image(pg.rect, filename=png)
        d.save(src); d.close()
        rep = redactor.redact(src, {0: [fitz.Rect(20, 40, 250, 75)]}, dst)
        assert rep.ok
        out = fitz.open(dst)
        pix = out[0].get_pixmap(clip=fitz.Rect(20, 40, 250, 75), dpi=72, alpha=False)
        dark = sum(1 for y in range(pix.height) for x in range(pix.width)
                   if sum(pix.pixel(x, y)) < 400)
        out.close()
        assert dark == 0, f"스캔본 픽셀이 남았다 ({dark})"

    def test_margin_drag_makes_no_selection(self, win, qapp, tmp_path):
        """페이지 옆 여백을 드래그해도 선택이 생기면 안 된다 (파괴 대상이 되어버린다)."""
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtGui import QMouseEvent
        win.open_file(_two_line_pdf(tmp_path))
        qapp.processEvents()
        win.view.fit_page()
        qapp.processEvents()
        sr = win.view.scene().sceneRect()
        a = win.view.mapFromScene(QPointF(sr.width() + 40, 40))
        b = win.view.mapFromScene(QPointF(sr.width() + 160, 120))
        win.view.mousePressEvent(QMouseEvent(
            QEvent.MouseButtonPress, QPointF(a), _Qt.LeftButton, _Qt.LeftButton,
            _Qt.NoModifier))
        win.view.mouseMoveEvent(QMouseEvent(
            QEvent.MouseMove, QPointF(b), _Qt.NoButton, _Qt.LeftButton, _Qt.NoModifier))
        win.view.mouseReleaseEvent(QMouseEvent(
            QEvent.MouseButtonRelease, QPointF(b), _Qt.LeftButton, _Qt.LeftButton,
            _Qt.NoModifier))
        qapp.processEvents()
        assert win.tray_items == [], f"여백 드래그가 담겼다: {win.tray_items}"
        assert not win.a_save_doc.isEnabled()


class TestOpenCapability:
    """열 때 세 갈래 — 못 읽음 / 읽지만 파괴 불가 / 다 됨."""

    def _spy(self, monkeypatch, grant=False):
        """모달을 가로챈다. grant=True 면 '이 폴더에 쓰기 허용'을 누른 것으로 친다."""
        from PySide6.QtWidgets import QMessageBox
        seen = {"warning": [], "critical": []}
        for name in ("warning", "critical"):
            monkeypatch.setattr(
                QMessageBox, name,
                staticmethod(lambda *a, _n=name, **k: seen[_n].append(a[2])
                             or QMessageBox.Ok))
        monkeypatch.setattr(
            MainWindow, "_warn_cannot_destroy",
            lambda self, text, fix_dir: (seen["warning"].append(text) or
                                         (grant and fix_dir is not None)))
        return seen

    def test_unreadable_file_is_refused(self, win, qapp, tmp_path, monkeypatch):
        seen = self._spy(monkeypatch)
        bad = tmp_path / "broken.pdf"
        bad.write_bytes(b"%PDF-1.7\nnot a pdf at all\n")   # 헤더만 그럴싸한 쓰레기
        win.open_file(str(bad))
        qapp.processEvents()
        assert seen["critical"], "못 읽는 파일인데 조용히 지나갔다"
        assert win.doc is None, "열 수 없는 파일이 열렸다"

    def test_readable_but_not_destroyable(self, win, qapp, tmp_path, monkeypatch):
        """읽기 전용 폴더의 문서 — 복사는 되고 파괴 경로는 잠긴다."""
        ro = tmp_path / "readonly"
        ro.mkdir()
        src = ro / "doc.pdf"
        d = fitz.open()
        d.new_page(width=200, height=200).insert_text((20, 40), "secret", fontsize=12)
        d.save(str(src)); d.close()
        ro.chmod(0o555)
        seen = self._spy(monkeypatch)
        try:
            win.open_file(str(src))
            qapp.processEvents()
            assert win.doc is not None, "읽을 수 있는 파일인데 열리지 않았다"
            assert seen["warning"], "파괴 불가인데 경고가 없다"
            assert "복사" in seen["warning"][0]
            assert not win.can_destroy
            assert win.a_save_img.isEnabled()          # 페이지 이미지 저장은 된다
            win.view.areaCollected.emit(0, fitz.Rect(10, 10, 100, 100))
            qapp.processEvents()
            assert len(win.tray_items) == 1            # 담기도 된다
            assert not win.a_save_doc.isEnabled()      # 그러나 파괴 저장은 잠긴다
        finally:
            ro.chmod(0o755)

    def test_normal_file_opens_silently(self, win, qapp, tmp_path, monkeypatch):
        seen = self._spy(monkeypatch)
        win.open_file(_two_line_pdf(tmp_path))
        qapp.processEvents()
        assert not seen["warning"] and not seen["critical"], seen
        assert win.can_destroy

    def test_grant_write_button_unlocks_destroy(self, win, qapp, tmp_path, monkeypatch):
        """경고의 '이 폴더에 쓰기 허용' → 권한을 주고 파괴가 풀린다."""
        from app.core import redactor
        ro = tmp_path / "grant"
        ro.mkdir()
        src = ro / "doc.pdf"
        d = fitz.open()
        d.new_page(width=200, height=200).insert_text((20, 40), "secret", fontsize=12)
        d.save(str(src)); d.close()
        ro.chmod(0o555)
        assert redactor.fixable_dir(str(ro / "x.pdf")) == str(ro)  # 내가 소유자다
        self._spy(monkeypatch, grant=True)
        try:
            win.open_file(str(src))
            qapp.processEvents()
            assert win.can_destroy, "쓰기 허용을 눌렀는데 파괴가 풀리지 않았다"
            assert os.access(str(ro), os.W_OK)
        finally:
            ro.chmod(0o755)

    def test_declining_keeps_it_locked(self, win, qapp, tmp_path, monkeypatch):
        ro = tmp_path / "decline"
        ro.mkdir()
        src = ro / "doc.pdf"
        d = fitz.open(); d.new_page(width=200, height=200); d.save(str(src)); d.close()
        ro.chmod(0o555)
        self._spy(monkeypatch, grant=False)   # '그대로 두기'
        try:
            win.open_file(str(src))
            qapp.processEvents()
            assert not win.can_destroy
            assert not os.access(str(ro), os.W_OK), "누르지도 않았는데 권한을 바꿨다"
        finally:
            ro.chmod(0o755)

    def test_grant_write_touches_only_owner_bit(self, tmp_path):
        """u+w 만 켠다 — 재귀하지 않고 다른 권한은 건드리지 않는다."""
        import stat as _stat
        from app.core import redactor
        d = tmp_path / "perm"
        d.mkdir()
        inner = d / "inner.txt"
        inner.write_text("x")
        d.chmod(0o555)
        before_inner = _stat.S_IMODE(inner.stat().st_mode)
        try:
            redactor.grant_write(str(d))
            after = _stat.S_IMODE(d.stat().st_mode)
            assert after == 0o755, oct(after)   # 소유자 쓰기만 추가
            assert _stat.S_IMODE(inner.stat().st_mode) == before_inner  # 안쪽은 그대로
        finally:
            d.chmod(0o755)

    def test_not_fixable_when_not_owner(self):
        """남의 폴더는 chmod 해봐야 소용없다 — 버튼을 내밀지 않는다."""
        from app.core import redactor
        assert redactor.fixable_dir("/System/x.pdf") is None

    def test_capability_recovers_on_next_open(self, win, qapp, tmp_path, monkeypatch):
        """파괴 불가 문서를 연 뒤 정상 문서를 열면 다시 풀려야 한다."""
        ro = tmp_path / "ro2"
        ro.mkdir()
        src = ro / "doc.pdf"
        d = fitz.open(); d.new_page(width=200, height=200); d.save(str(src)); d.close()
        ro.chmod(0o555)
        self._spy(monkeypatch)
        try:
            win.open_file(str(src))
            qapp.processEvents()
            assert not win.can_destroy
        finally:
            ro.chmod(0o755)
        win.open_file(_two_line_pdf(tmp_path))
        qapp.processEvents()
        assert win.can_destroy


class TestSaveBlocked:
    def test_readonly_dir_is_caught_before_work(self, tmp_path):
        """읽기 전용 폴더 — 다 파괴해놓고 마지막에 터지면 안 된다."""
        from app.core import redactor
        ro = tmp_path / "readonly"
        ro.mkdir()
        ro.chmod(0o555)
        try:
            msg = redactor.save_blocker(str(ro / "out.pdf"))
            assert msg and "읽기 전용" in msg
        finally:
            ro.chmod(0o755)

    def test_missing_dir(self, tmp_path):
        from app.core import redactor
        msg = redactor.save_blocker(str(tmp_path / "없는폴더" / "out.pdf"))
        assert msg and "폴더가 없습니다" in msg

    def test_writable_dir_passes(self, tmp_path):
        from app.core import redactor
        assert redactor.save_blocker(str(tmp_path / "out.pdf")) is None

    def test_save_failure_is_legible(self, tmp_path):
        """PyMuPDF 가 메시지 없는 예외를 흘려도 사용자는 이유를 읽을 수 있어야 한다."""
        from app.core import redactor
        src = str(tmp_path / "in.pdf")
        d = fitz.open()
        d.new_page(width=200, height=200).insert_text((20, 40), "secret", fontsize=12)
        d.save(src); d.close()
        ro = tmp_path / "readonly"
        ro.mkdir(); ro.chmod(0o555)
        try:
            with pytest.raises(OSError) as ei:
                redactor.redact(src, {0: [fitz.Rect(10, 20, 120, 50)]},
                                str(ro / "out.pdf"))
            assert "저장할 수 없습니다" in str(ei.value)
            assert "읽기 전용" in str(ei.value)
        finally:
            ro.chmod(0o755)

    def test_ui_blocks_before_starting_worker(self, win, qapp, tmp_path, monkeypatch):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        path = _two_line_pdf(tmp_path)
        win.open_file(path)
        qapp.processEvents()
        win.view.textBoxClicked.emit(0, _boxes(path, 0)[0][0], "a")
        qapp.processEvents()
        ro = tmp_path / "readonly"
        ro.mkdir(); ro.chmod(0o555)
        warned = []
        monkeypatch.setattr(QMessageBox, "warning",
                            staticmethod(lambda *a, **k: warned.append(a[2])
                                         or QMessageBox.Yes))
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            staticmethod(lambda *a, **k: (str(ro / "out.pdf"), "")))
        try:
            win.save_destroyed()
            assert any("읽기 전용" in w for w in warned), warned
            assert not win._busy          # 워커를 시작조차 하지 않았다
            assert len(win.tray_items) == 1  # 목록도 그대로다
        finally:
            ro.chmod(0o755)


class TestSavePathRules:
    def test_image_path_rule(self, tmp_path):
        from app.ui.main_window import _next_image_path
        src = str(tmp_path / "세금계산서.pdf")
        open(src, "w").close()
        p1 = _next_image_path(src, 1)  # 2페이지
        assert p1 == str(tmp_path / "세금계산서_p2_01.png")
        open(p1, "w").close()
        assert _next_image_path(src, 1).endswith("_p2_02.png")  # 연번 증가, 덮어쓰기 없음

    def test_redacted_path_rule(self, tmp_path):
        from app.ui.main_window import _next_redacted_path
        src = str(tmp_path / "계약서.pdf")
        open(src, "w").close()
        p1 = _next_redacted_path(src)
        assert p1 == str(tmp_path / "계약서_redacted.pdf")
        open(p1, "w").close()
        assert _next_redacted_path(src).endswith("_redacted2.pdf")


class TestTray:
    def test_click_collects_and_copies(self, win, qapp, monkeypatch):
        from PySide6.QtWidgets import QMessageBox
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        p1 = [(10, 10), (100, 10), (100, 30), (10, 30)]
        p2 = [(10, 40), (100, 40), (100, 60), (10, 60)]
        win.view.textBoxClicked.emit(0, p1, "사업자 도길동")
        win.view.textBoxClicked.emit(0, p2, "123-45-67890")
        qapp.processEvents()
        assert len(win.tray_items) == 2
        assert win.tray_list.count() == 2
        # 전체 복사 — 담은 글자를 줄바꿈으로 잇는다
        win.btn_tray_copy.click()
        c = qapp.clipboard().text()
        assert "사업자 도길동" in c and "123-45-67890" in c
        # 같은 자리를 또 클릭해도 중복으로 담기지 않는다 (복사는 다시 된다)
        win.view.textBoxClicked.emit(0, p1, "사업자 도길동")
        qapp.processEvents()
        assert len(win.tray_items) == 2
        # 전체 비우기
        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.Yes))
        win.btn_tray_clear.click()
        assert win.tray_items == [] and win.tray_list.count() == 0

    def test_row_x_removes_only_that_row(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        for i in range(3):
            poly = [(10, 10 + i * 30), (100, 10 + i * 30),
                    (100, 30 + i * 30), (10, 30 + i * 30)]
            win.view.textBoxClicked.emit(0, poly, f"항목{i}")
        qapp.processEvents()
        assert len(win.tray_items) == 3
        row = win.tray_list.itemWidget(win.tray_list.item(1))
        row.removed.emit()                      # 가운데 행의 ✕
        qapp.processEvents()
        assert [it.text for it in win.tray_items] == ["항목0", "항목2"]

    def test_row_edit_changes_text_not_region(self, win, qapp):
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        poly = [(10, 10), (100, 10), (100, 30), (10, 30)]
        win.view.textBoxClicked.emit(0, poly, "오타있음")
        qapp.processEvents()
        before = win.tray_items[0].region
        row = win.tray_list.itemWidget(win.tray_list.item(0))
        row.edit.setText("고친 글자")
        row.edit.editingFinished.emit()
        qapp.processEvents()
        assert win.tray_items[0].text == "고친 글자"
        assert win.tray_items[0].region == before   # 파괴는 좌표 기준이다

    def test_drag_collects_repeatedly(self, win, qapp):
        """드래그를 놓으면 바로 담긴다 — 버튼을 거치지 않는다."""
        win.open_file(os.path.join(OUT, "text.pdf"))
        _wait_pool(win, qapp)
        for r in (fitz.Rect(30, 100, 200, 130), fitz.Rect(30, 140, 200, 170)):
            win.view.areaCollected.emit(0, r)
        qapp.processEvents()
        assert len(win.tray_items) == 2
        assert all(it.kind == "area" for it in win.tray_items)
        assert win.a_save_doc.isEnabled()


@pytest.fixture()
def answer(monkeypatch):
    """모달 자동응답 — 마지막에 무엇을 물었는지도 돌려준다."""
    from PySide6.QtWidgets import QMessageBox
    asked = []

    def make(button):
        def _f(*a, **k):
            asked.append(a[2] if len(a) > 2 else "")
            return button
        return _f

    def set_answer(button):
        for name in ("warning", "question", "information"):
            monkeypatch.setattr(QMessageBox, name, staticmethod(make(button)))

    set_answer(QMessageBox.Yes)
    set_answer.asked = asked
    return set_answer


def _two_line_pdf(tmp_path) -> str:
    """OCR 없이 박스 클릭 경로를 태우기 위한 글자층 PDF."""
    path = str(tmp_path / "del.pdf")
    d = fitz.open()
    for lines in (["hong 010-1234-5678", "seoul gangnam"], ["acct 110-222-333333"]):
        pg = d.new_page(width=300, height=300)
        for j, t in enumerate(lines):
            pg.insert_text((40, 60 + j * 40), t, fontsize=12)
    d.save(path)
    d.close()
    return path


def _boxes(path: str, page_no: int) -> list:
    d = fitz.open(path)
    out = []
    for b in d[page_no].get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            x0, y0, x1, y1 = ln["bbox"]
            out.append(([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                        "".join(s["text"] for s in ln["spans"])))
    d.close()
    return out


class TestCollectAndDestroy:
    """모드 없이 — 담은 목록 하나가 복사 대상이자 파괴 대상이다."""

    def test_no_delete_mode_left(self, win):
        """삭제 모드의 흔적이 남아 있으면 안 된다."""
        for gone in ("sw_delete", "delete_mode", "delete_items", "tray_stack",
                     "a_destroy", "execute_deletions", "a_copy", "a_mark",
                     "copy_selection_text", "mark_selection", "save_selection_image"):
            assert not hasattr(win, gone), f"{gone} 가 아직 남아 있다"
        assert not hasattr(win.view, "delete_mode")

    def test_destroy_has_no_shortcut(self, win):
        """되돌릴 수 없는 실행에는 단축키를 주지 않는다. 담기(Ctrl+D)는 되돌릴 수 있다."""
        assert win.a_save_doc.shortcut().isEmpty()

    def test_accumulate_across_pages(self, win, qapp, tmp_path):
        path = _two_line_pdf(tmp_path)
        win.open_file(path)
        qapp.processEvents()
        b0, b1 = _boxes(path, 0), _boxes(path, 1)
        win.view.textBoxClicked.emit(0, b0[0][0], b0[0][1])
        win.view.textBoxClicked.emit(0, b0[1][0], b0[1][1])
        win.view.areaCollected.emit(0, fitz.Rect(30, 100, 200, 130))
        win.view.textBoxClicked.emit(1, b1[0][0], b1[0][1])
        qapp.processEvents()
        assert len(win.tray_items) == 4
        assert sorted({i.page_no for i in win.tray_items}) == [0, 1]
        assert set(win.view.tray_regions) == {0, 1}
        assert win.tray_head.text() == "담은 목록 (4건)"

    def test_row_pick_jumps_page(self, win, qapp, tmp_path):
        path = _two_line_pdf(tmp_path)
        win.open_file(path)
        qapp.processEvents()
        win.view.textBoxClicked.emit(0, _boxes(path, 0)[0][0], "a")
        win.view.textBoxClicked.emit(1, _boxes(path, 1)[0][0], "b")
        qapp.processEvents()
        win.view.show_page(0)
        win._pick_tray_row(1)
        assert win.view.page_no == 1

    def test_save_destroyed_once(self, win, qapp, tmp_path, answer, monkeypatch):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        path = _two_line_pdf(tmp_path)
        dst = str(tmp_path / "out.pdf")
        win.open_file(path)
        qapp.processEvents()
        for poly, txt in _boxes(path, 0):
            win.view.textBoxClicked.emit(0, poly, txt)
        poly1, txt1 = _boxes(path, 1)[0]
        win.view.textBoxClicked.emit(1, poly1, txt1)
        qapp.processEvents()
        assert len({i.page_no for i in win.tray_items}) == 2

        crit = []
        monkeypatch.setattr(QMessageBox, "critical",
                            staticmethod(lambda *a, **k: crit.append(a[2])))
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            staticmethod(lambda *a, **k: (dst, "")))
        monkeypatch.setattr(MainWindow, "open_file", lambda self, p: None)
        answer(QMessageBox.Yes)
        win.a_save_doc.trigger()
        _wait_pool(win, qapp)
        assert not crit, f"검증 실패: {crit}"
        assert os.path.exists(dst)
        assert win.tray_items == []
        out = fitz.open(dst)
        assert out[0].get_text().strip() == ""     # 2페이지가 한 번에 파괴됐다
        assert out[1].get_text().strip() == ""
        out.close()

    def test_failure_keeps_the_list(self, win, qapp, tmp_path, answer, monkeypatch):
        """저장에 실패하면 담은 것을 잃지 않는다 — 다시 시도할 수 있어야 한다."""
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        path = _two_line_pdf(tmp_path)
        win.open_file(path)
        qapp.processEvents()
        win.view.textBoxClicked.emit(0, _boxes(path, 0)[0][0], "a")
        qapp.processEvents()
        ro = tmp_path / "ro_out"
        ro.mkdir(); ro.chmod(0o555)
        seen = []
        monkeypatch.setattr(QMessageBox, "warning",
                            staticmethod(lambda *a, **k: seen.append(a[2])
                                         or QMessageBox.Yes))
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            staticmethod(lambda *a, **k: (str(ro / "x.pdf"), "")))
        try:
            win.a_save_doc.trigger()
            _wait_pool(win, qapp)
            assert len(win.tray_items) == 1, "실패했는데 목록이 사라졌다"
            assert win.a_save_doc.isEnabled(), "다시 시도할 수 없다"
        finally:
            ro.chmod(0o755)

    def test_open_another_doc_warns_and_discards(self, win, qapp, tmp_path, answer):
        from PySide6.QtWidgets import QMessageBox
        path = _two_line_pdf(tmp_path)
        win.open_file(path)
        qapp.processEvents()
        win.view.textBoxClicked.emit(0, _boxes(path, 0)[0][0], "a")
        qapp.processEvents()
        answer(QMessageBox.No)
        win.open_file(os.path.join(OUT, "text.pdf"))
        assert len(win.tray_items) == 1   # 거부하면 문서도 바뀌지 않는다
        answer(QMessageBox.Yes)
        win.open_file(os.path.join(OUT, "text.pdf"))
        qapp.processEvents()
        assert win.tray_items == []       # 이전 문서 좌표를 들고 갈 수는 없다

    def test_boxes_toggle_no_longer_warns(self, win, qapp, tmp_path, monkeypatch):
        """모드가 없으니 글자 인식을 꺼도 담은 것은 그대로다."""
        from PySide6.QtWidgets import QMessageBox
        path = _two_line_pdf(tmp_path)
        win.open_file(path)
        qapp.processEvents()
        win.view.textBoxClicked.emit(0, _boxes(path, 0)[0][0], "a")
        qapp.processEvents()
        warned = []
        monkeypatch.setattr(QMessageBox, "warning",
                            staticmethod(lambda *a, **k: warned.append(a[2])
                                         or QMessageBox.Yes))
        win.sw_boxes.toggle()
        qapp.processEvents()
        assert not warned
        assert len(win.tray_items) == 1
        assert not win.view.boxes_visible
