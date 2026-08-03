"""진입점. 실행: python -m app.main [pdf경로]"""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    import os

    from PySide6.QtGui import QIcon

    from . import config

    app = QApplication(sys.argv)
    app.setApplicationName("따옴")
    icon_path = os.path.join(config.BASE, "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    apply_theme(app)
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        win.open_file(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
