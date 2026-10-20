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


# Trùng `AppMutex` trong installer.iss: bộ cài / gỡ cài đặt nhận ra QT PDF Pro đang mở và đề nghị đóng trước
APP_MUTEX_NAME = "QTPdfPro.AppMutex"
_app_mutex_handle = None


def _create_app_mutex() -> None:
    """Giữ một mutex có tên suốt vòng đời tiến trình (Windows tự giải phóng khi thoát)."""
    global _app_mutex_handle
    if sys.platform != "win32" or _app_mutex_handle is not None:
        return
    try:
        _app_mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, APP_MUTEX_NAME)
    except (AttributeError, OSError):
        _app_mutex_handle = None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qtpdfpro",
        description=f"{__app_name__} v{__version__} — Giao diện đọc PDF & chuyển PDF sang DOCX.",
    )
    parser.add_argument("files", nargs="*", help="Các tệp PDF cần mở ngay khi khởi động")
    # Bộ cài (installer.iss) mở ứng dụng kèm cờ này: nó vừa đề nghị đặt mặc định rồi, không hỏi lại
    parser.add_argument("--skip-default-prompt", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    _set_windows_app_id()
    _create_app_mutex()
    app =QApplication.instance() or QApplication([])
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())

    settings = AppSettings.load()
    if args.skip_default_prompt and not settings.default_app_prompted:
        settings.default_app_prompted = True
        settings.save()
    win = MainWindow(settings=settings)
    win.show()

    for f in args.files:
        p = Path(f)
        if p.exists():
            win.open_pdf_path(p)

    # Trình cập nhật (core/updater.py): tự kiểm tra tối đa 1 lần/ngày, tải ngầm QTPdfPro_Update.zip, cài khi thoát
    # (bản đóng gói); dọn bản cũ «.old» sau lần cập nhật trước
    win.updater.on_startup()
    win.default_app.on_startup()  # bản cài lần đầu chạy: hỏi một lần «Đặt làm trình xem PDF mặc định»
    return app.exec()
