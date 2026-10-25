"""Khởi động GUI: cửa sổ chính mở phóng to toàn màn hình (như PdfCraft), không nằm thu nhỏ trên thanh tác vụ."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import app as gui_app
from qtpdfpro.ui.main_window import MainWindow


def test_show_main_window_maximized_and_not_minimized():
    QApplication.instance() or QApplication([])
    win = MainWindow(settings=AppSettings.load())
    try:
        win.setWindowState(Qt.WindowMinimized)
        gui_app.show_main_window(win)
        QApplication.processEvents()
        assert win.isVisible()
        assert win.windowState() & Qt.WindowMaximized
        assert not win.windowState() & Qt.WindowMinimized
    finally:
        win.close()


def test_force_foreground_ignores_invalid_handle():
    gui_app._force_foreground(0)  # không ném lỗi
