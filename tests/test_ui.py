"""Kiểm thử tự động giao diện đồ hoạ PySide6 của QT PDF Pro (`MainWindow`, `PDFScrollViewer`)."""

from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import QApplication

from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.convert_dialog import ConvertToDocxDialog
from qtpdfpro.ui.main_window import MainWindow


def test_main_window_open_pdf_search_and_layout_overlay(sample_vietnamese_pdf: Path) -> None:
    app = QApplication.instance() or QApplication([])
    settings = AppSettings.load()
    win = MainWindow(settings=settings)
    win.show()
    app.processEvents()

    # Mở tệp PDF vào tab
    tab = win.open_pdf_path(sample_vietnamese_pdf)
    assert tab is not None
    assert win.doc_tabs.count() == 1
    assert tab.reader.page_count == 2

    # Di chuyển trang & thu phóng
    win.action_next_page()
    app.processEvents()
    assert tab.viewer.current_page == 1

    win.action_prev_page()
    app.processEvents()
    assert tab.viewer.current_page == 0

    tab.viewer.zoom_in(25)
    app.processEvents()

    # Tìm kiếm văn bản trên giao diện
    tab.search_input.setText("Độc lập")
    tab.run_search()
    app.processEvents()
    assert tab.search_results_list.count() >= 1

    # Bật lớp phủ soi khung bố cục
    win.action_toggle_layout_overlay(True)
    app.processEvents()
    assert tab.viewer.show_layout_overlay is True

    # Đổi giao diện Sáng / Tối
    win.action_toggle_theme()
    app.processEvents()
    assert win.settings.theme == "light"

    # Kiểm tra khởi tạo hộp thoại chuyển đổi PDF sang DOCX
    dlg = ConvertToDocxDialog(
        pdf_path=sample_vietnamese_pdf,
        total_pages=2,
        current_page=0,
        settings=win.settings,
        parent=win,
    )
    assert dlg.out_edit.text().endswith(".docx")
    dlg.close()

    win.close()
    app.processEvents()
