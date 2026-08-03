"""진입점. 실행: python -m app.main [pdf경로]"""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("PDF 영역 도구")
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        win.open_file(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
