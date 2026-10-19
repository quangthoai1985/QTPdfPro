"""Khởi tạo QApplication và điểm vào giao diện đồ hoạ của QT PDF Pro."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import QApplication

from qtpdfpro import __app_name__, __version__
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.main_window import MainWindow


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qtpdfpro",
        description=f"{__app_name__} v{__version__} — Giao diện đọc PDF & chuyển PDF sang DOCX.",
    )
    parser.add_argument("files", nargs="*", help="Các tệp PDF cần mở ngay khi khởi động")
    args = parser.parse_args(argv)

    app = QApplication.instance() or QApplication([])
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)

    settings = AppSettings.load()
    win = MainWindow(settings=settings)
    win.show()

    for f in args.files:
        p = Path(f)
        if p.exists():
            win.open_pdf_path(p)

    return app.exec()
