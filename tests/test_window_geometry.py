"""창 기동 크기 — 화면 없이(QApplication 없이) QRect 계산만 검증한다."""
from PySide6.QtCore import QRect

from app import config
from app.ui.widgets import startup_geometry


def test_full_hd_is_80_percent_and_centered():
    # 1920x1080 에서 작업표시줄을 뺀 흔한 작업영역
    g = startup_geometry(QRect(0, 0, 1920, 1040))
    assert (g.width(), g.height()) == (1536, 832)
    assert (g.x(), g.y()) == (192, 104)


def test_secondary_monitor_keeps_negative_origin():
    # 주 모니터 왼쪽에 붙은 보조 모니터 — 창이 주 모니터로 튀면 안 된다
    g = startup_geometry(QRect(-1920, 0, 1920, 1040))
    assert g.x() == -1920 + 192
    assert g.right() < 0


def test_small_screen_never_exceeds_available():
    # 80% 가 하한보다 작은 화면: 하한이 올라가되 화면은 넘지 않아야 한다
    avail = QRect(0, 0, 1024, 600)
    g = startup_geometry(avail)
    assert g.width() >= int(1024 * config.WINDOW_SCREEN_RATIO)
    assert g.height() == 600  # 하한 600 이 80%(480) 를 이겼지만 화면 높이에서 멈춤
    assert avail.contains(g)


def test_tiny_screen_clamps_to_screen():
    avail = QRect(0, 0, 800, 500)  # 양쪽 다 하한 미만
    g = startup_geometry(avail)
    assert (g.width(), g.height()) == (800, 500)
    assert (g.x(), g.y()) == (0, 0)
