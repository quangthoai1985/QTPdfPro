"""Khởi tạo QApplication và điểm vào giao diện đồ hoạ của QT PDF Pro."""

from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from qtpdfpro import __app_name__, __github_repo__, __version__
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.main_window import MainWindow

# Sinh lại bằng `python tools/make_app_icon.py`; build.bat nhúng vào .exe (--icon) và chép kèm (--add-data)
ICON_PATH = Path(__file__).resolve().parent / "assets" / "app_icon.ico"


def app_icon() -> QIcon:
    """Icon ứng dụng (tệp .ico nhiều cỡ 16–256 px) cho cửa sổ, hộp thoại và thanh tác vụ."""
    return QIcon(str(ICON_PATH))


def _set_windows_app_id() -> None:
    """Khi chạy bằng python.exe, tách khỏi nhóm «Python» trên thanh tác vụ để Windows hiện icon của app.

    Bản .exe không cần (Windows lấy icon nhúng trong .exe); đặt ID riêng ở đó còn làm cửa sổ
    tách khỏi lối tắt đã ghim của chính .exe.
    """
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(__github_repo__.replace("/", "."))
    except (AttributeError, OSError):
        pass


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qtpdfpro",
        description=f"{__app_name__} v{__version__} — Giao diện đọc PDF & chuyển PDF sang DOCX.",
    )
    parser.add_argument("files", nargs="*", help="Các tệp PDF cần mở ngay khi khởi động")
    args = parser.parse_args(argv)

    _set_windows_app_id()
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())

    settings = AppSettings.load()
    win = MainWindow(settings=settings)
    win.show()

    for f in args.files:
        p = Path(f)
        if p.exists():
            win.open_pdf_path(p)

    win.updater.on_startup()  # tự kiểm tra bản mới (tối đa 1 lần/ngày, chạy nền) + dọn bản cũ sau khi cập nhật
    return app.exec()
