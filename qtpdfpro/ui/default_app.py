"""«Đặt QT PDF Pro làm trình xem PDF mặc định» — menu Trợ giúp + lời nhắc một lần sau khi cài.

Windows không cho ứng dụng tự đặt mình làm mặc định; `core/file_assoc.py` đăng ký ứng dụng (bộ cài đã làm,
bản giải nén tay thì đăng ký khi người dùng bấm) rồi mở trang «Ứng dụng mặc định» của QT PDF Pro để người dùng
bấm «Đặt mặc định» một lần.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenu, QMessageBox

from qtpdfpro import __app_name__
from qtpdfpro.core import file_assoc as fa
from qtpdfpro.core import update_check as uc
from qtpdfpro.core.settings import AppSettings

STARTUP_PROMPT_DELAY_MS = 1500


class DefaultAppController(QObject):
    """Gắn vào `MainWindow` (`window.default_app`)."""

    def __init__(self, window: QMainWindow, settings: AppSettings) -> None:
        super().__init__(window)
        self.window = window
        self.settings = settings
        self.act_set_default = QAction("Đặt QT PDF Pro làm trình xem PDF mặc định...", window)
        self.act_set_default.triggered.connect(lambda _checked=False: self.make_default())

    def add_menu_actions(self, menu: QMenu) -> None:
        menu.addAction(self.act_set_default)

    def is_default(self) -> bool:
        return sys.platform == "win32" and fa.is_default_pdf_app()

    def on_startup(self, delay_ms: int = STARTUP_PROMPT_DELAY_MS) -> None:
        """Bản đóng gói, chưa là trình mở PDF mặc định và chưa hỏi lần nào → hỏi một lần."""
        if sys.platform != "win32" or not uc.is_frozen() or self.settings.default_app_prompted:
            return
        QTimer.singleShot(max(0, delay_ms), self.prompt_once)

    def prompt_once(self) -> None:
        if self.settings.default_app_prompted or self.is_default():
            return
        self.settings.default_app_prompted = True
        self.settings.save()
        answer = QMessageBox.question(
            self.window,
            "Trình xem PDF mặc định",
            f"Đặt {__app_name__} làm ứng dụng mở tệp PDF mặc định?\n\n"
            "Windows sẽ mở trang «Ứng dụng mặc định» của QT PDF Pro — bấm «Đặt mặc định» để hoàn tất.\n"
            "(Có thể làm lại bất cứ lúc nào: ☰ Menu › Trợ giúp.)",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.make_default()

    def make_default(self) -> bool:
        """Đăng ký (nếu cần) rồi mở trang cài đặt. Trả về True nếu đã mở được Cài đặt Windows."""
        if sys.platform != "win32":
            return False
        if self.is_default():
            QMessageBox.information(self.window, "Trình xem PDF mặc định", f"{__app_name__} đã là trình mở PDF mặc định.")
            return True
        if uc.is_frozen():
            exe = Path(sys.executable).resolve()
            try:
                if not fa.is_registered(exe):
                    fa.register_pdf_handler(exe)
            except OSError as exc:
                QMessageBox.warning(self.window, "Trình xem PDF mặc định", f"Không đăng ký được với Windows: {exc}")
                return False
        elif not fa.is_registered():
            QMessageBox.information(
                self.window,
                "Trình xem PDF mặc định",
                "Bạn đang chạy từ mã nguồn — hãy cài bằng QTPdfPro_Setup.exe để đăng ký trình mở PDF với Windows.",
            )
            return False
        if not fa.open_default_apps_settings():
            QMessageBox.warning(self.window, "Trình xem PDF mặc định", "Không mở được Cài đặt Windows.")
            return False
        show = getattr(self.window, "_show_toast", None)
        if callable(show):
            show("Trong Cài đặt Windows, bấm «Đặt mặc định» cho QT PDF Pro.", 8000)
        return True
