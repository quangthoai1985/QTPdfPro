"""Khởi tạo QApplication và điểm vào giao diện đồ hoạ của QT PDF Pro."""

from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from qtpdfpro import __app_name__, __github_repo__, __version__
from qtpdfpro.core.single_instance import normalize_paths
from qtpdfpro.ui.single_instance import SingleInstance

if TYPE_CHECKING:  # nạp MainWindow (PyMuPDF, ONNX…) chỉ khi là tiến trình chính — tiến trình phụ thoát nhanh
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


def _force_foreground(hwnd: int) -> None:
    """Đưa cửa sổ lên trên cùng dù Windows đang khoá tiền cảnh (foreground lock).

    Windows chỉ cho tiến trình vừa được người dùng mở giành tiền cảnh trong thời gian ngắn; khởi động
    chậm (nạp PySide6, PyMuPDF, ONNX…), người dùng bấm sang cửa sổ khác trong lúc chờ, hoặc ứng dụng
    được mở lại bởi script cập nhật / bộ cài thì `SetForegroundWindow` bị từ chối → cửa sổ nằm sau,
    chỉ nhấp nháy trên thanh tác vụ. Gắn tạm hàng đợi nhập của luồng đang giữ tiền cảnh rồi kích hoạt.
    """
    if sys.platform != "win32" or not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        foreground = user32.GetForegroundWindow()
        if foreground == hwnd:
            return
        fg_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        our_thread = kernel32.GetCurrentThreadId()
        attached = bool(fg_thread and fg_thread != our_thread and user32.AttachThreadInput(our_thread, fg_thread, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(our_thread, fg_thread, False)
    except (AttributeError, OSError):
        pass


def show_main_window(win: MainWindow) -> None:
    """Mở cửa sổ chính phóng to toàn màn hình (như PdfCraft) và đưa lên trước.

    `resize(1400, 880)` của `MainWindow` vẫn là cỡ khi người dùng bấm «Thu nhỏ cửa sổ» (Restore Down).
    """
    win.showMaximized()
    win.raise_()
    win.activateWindow()
    _force_foreground(int(win.winId()))


def bring_to_front(win: MainWindow) -> None:
    """Đưa cửa sổ đang chạy lên trước khi tiến trình khác gửi tệp tới: khôi phục nếu đang thu nhỏ, giữ
    nguyên trạng thái phóng to / thường người dùng đã chọn."""
    if not win.isVisible():
        show_main_window(win)
        return
    state = win.windowState()
    if state & Qt.WindowState.WindowMinimized:
        win.setWindowState((state & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
    win.show()
    win.raise_()
    win.activateWindow()
    _force_foreground(int(win.winId()))


def open_files_from_instance(win: MainWindow, files: List[str]) -> None:
    """Yêu cầu từ tiến trình QT PDF Pro khác (mở PDF từ Explorer khi ứng dụng đang chạy): mỗi tệp một tab.

    Danh sách rỗng (bấm lối tắt khi ứng dụng đang mở) chỉ đưa cửa sổ lên trước, như Foxit Reader.
    """
    bring_to_front(win)
    for f in files:
        win.open_pdf_path(Path(f))  # tệp đã mở thì chuyển tới tab đó; tệp không còn thì báo
    if files:
        bring_to_front(win)  # mở tệp lớn mất vài giây — người dùng có thể đã bấm sang cửa sổ khác


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qtpdfpro",
        description=f"{__app_name__} v{__version__} — Giao diện đọc PDF & chuyển PDF sang DOCX.",
    )
    parser.add_argument("files", nargs="*", help="Các tệp PDF cần mở ngay khi khởi động")
    # Bộ cài (installer.iss) mở ứng dụng kèm cờ này: nó vừa đề nghị đặt mặc định rồi, không hỏi lại
    parser.add_argument("--skip-default-prompt", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    files = normalize_paths(args.files)

    _set_windows_app_id()
    app = QApplication.instance() or QApplication([])

    # Một cửa sổ duy nhất (V1): đã có QT PDF Pro đang chạy → gửi tệp sang đó (mở thành tab mới) rồi thoát
    instance = SingleInstance(parent=app)
    role = instance.start(files)
    if role == SingleInstance.FORWARDED:
        return 0

    from qtpdfpro.core.settings import AppSettings
    from qtpdfpro.ui.main_window import MainWindow
    from qtpdfpro.ui.theme import install_ui_fonts

    _create_app_mutex()
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    install_ui_fonts(app)  # Inter như PdfCraft, nạp trước khi dựng cửa sổ

    settings = AppSettings.load()
    if args.skip_default_prompt and not settings.default_app_prompted:
        settings.default_app_prompted = True
        settings.save()
    win = MainWindow(settings=settings)
    show_main_window(win)

    for f in files:
        p = Path(f)
        if p.exists():
            win.open_pdf_path(p)
    # Tệp mở từ Explorer trong lúc cửa sổ còn đang dựng (đã xếp hàng) → mở ngay; về sau mở khi nhận được
    instance.attach(lambda fs: open_files_from_instance(win, fs))
    app.aboutToQuit.connect(instance.shutdown)
    # Lần nữa khi vòng lặp sự kiện đã chạy (mở tệp lớn ở trên có thể mất vài giây)
    QTimer.singleShot(0, lambda: _force_foreground(int(win.winId())))

    # Trình cập nhật (core/updater.py): tự kiểm tra tối đa 1 lần/ngày, tải ngầm QTPdfPro_Update.zip, cài khi thoát
    # (bản đóng gói); dọn bản cũ «.old» sau lần cập nhật trước
    win.updater.on_startup()
    # «Có gì mới» sau khi cập nhật (hiện một lần); hiện rồi thì hộp thoại trình xem mặc định để lần mở sau
    shown = win.whats_new.on_startup()
    if not shown:
        win.default_app.on_startup()  # bản cài lần đầu chạy: hỏi một lần «Đặt làm trình xem PDF mặc định»
    return app.exec()
