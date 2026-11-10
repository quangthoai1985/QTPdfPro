"""Tiện ích dùng chung cho bài test GUI (mở cửa sổ + tài liệu mẫu)."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import fitz
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.main_window import MainWindow, PDFDocumentTab


def open_window(pdf: Path, settings: AppSettings | None = None, width: int = 1400, height: int = 900
                ) -> tuple[MainWindow, PDFDocumentTab]:
    """Hiện `MainWindow`, mở `pdf`, thu phóng 100%, về trang đầu."""
    app = QApplication.instance() or QApplication([])
    win = MainWindow(settings=settings or AppSettings.load())
    win.resize(width, height)
    win.show()
    app.processEvents()
    tab = win.open_pdf_path(pdf)
    assert tab is not None
    tab.viewer.set_zoom_mode("percent", 100)
    tab.viewer.go_to_page(0)
    for _ in range(3):
        app.processEvents()
    return win, tab


def copy_pdf(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return dst


def make_sample_pdf(path: Path) -> Path:
    """PDF 2 trang chữ tiếng Việt (Times New Roman của Windows nếu có)."""
    font = Path(r"C:\Windows\Fonts\times.ttf")
    kw = {"fontname": "tnr", "fontfile": str(font)} if font.exists() else {"fontname": "helv"}
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "Cộng hoà xã hội chủ nghĩa Việt Nam", fontsize=14, **kw)
    page.insert_text((72, 130), "Độc lập - Tự do - Hạnh phúc", fontsize=14, **kw)
    page.insert_text((300, 400), "Ô bảng một", fontsize=11, **kw)
    doc.new_page(width=595, height=842).insert_text((72, 100), "Trang hai", fontsize=14, **kw)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    doc.close()
    return path


def clipboard_text(expected: str | None = None, timeout: float = 1.5) -> str:
    """Chữ trong bảng nhớ tạm của Windows. Một số máy có chương trình theo dõi bảng nhớ tạm (lịch sử bảng nhớ tạm,
    đồng bộ…) giữ nó trong chốc lát ngay sau khi ghi → đọc ngay có thể ra chuỗi rỗng / cũ (đo được 18/40 lần sai
    khi chỉ dùng Qt). Đọc lại tới khi khớp `expected` hoặc hết `timeout` giây; trả về lần đọc cuối."""
    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    text = QGuiApplication.clipboard().text()
    while expected is not None and text != expected and time.monotonic() < deadline:
        if app is not None:
            app.processEvents()
        time.sleep(0.02)
        text = QGuiApplication.clipboard().text()
    return text
