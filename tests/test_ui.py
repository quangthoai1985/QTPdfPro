"""Kiểm thử tự động giao diện đồ hoạ PySide6 của QT PDF Pro (`MainWindow`, `PDFScrollViewer`) và bộ ghép số văn bản đóng dấu."""

from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import QApplication

from qtpdfpro.core.converter import _splice_overlapping_stamped_text
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

    # Kiểm tra bố cục 3 cột kiểu PdfCraft (Cột trái Tất cả công cụ, Cột giữa Viewer, Cột phải Sidebar + Right Rail)
    assert tab.tools_panel.isVisible() is True
    assert tab.right_rail.isVisible() is True

    # Lọc công cụ ở cột bên trái
    tab.tool_filter_input.setText("Xoay")
    app.processEvents()
    assert tab.tool_btn_rot_left.isVisible() is True
    assert tab.tool_btn_doc_info.isVisible() is False
    tab.tool_filter_input.setText("")
    app.processEvents()

    # Di chuyển trang & thu phóng
    win.action_next_page()
    app.processEvents()
    assert tab.viewer.current_page == 1

    win.action_prev_page()
    app.processEvents()
    assert tab.viewer.current_page == 0

    tab.viewer.zoom_in(25)
    app.processEvents()

    # Tìm kiếm nhanh từ thanh công cụ trên cùng
    win.toolbar_search_input.setText("Độc lập")
    win._on_toolbar_quick_search()
    app.processEvents()
    assert tab.search_results_list.count() >= 1

    # Bật lớp phủ soi khung bố cục
    win.action_toggle_layout_overlay(True)
    app.processEvents()
    assert tab.viewer.show_layout_overlay is True

    # Đổi giao diện Sáng / Tối bằng nút trên thanh Header
    win.btn_theme_toggle.click()
    app.processEvents()
    assert win.settings.theme == "light"
    assert tab.viewer._canvas_theme == "light"
    assert "Tối" in win.btn_theme_toggle.text()

    win.btn_theme_toggle.click()
    app.processEvents()
    assert win.settings.theme == "dark"
    assert tab.viewer._canvas_theme == "dark"
    assert "Sáng" in win.btn_theme_toggle.text()

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


def test_splice_overlapping_stamped_text_preserves_document_number() -> None:
    """Đảm bảo số hiệu văn bản ('3865') đóng dấu đè vào khoảng trống ('Số:         /QĐ-UBND') được ghép đúng vị trí."""
    host_chars = []
    host_str = "Số:           /QĐ-UBND"
    x = 70.0
    for ch in host_str:
        w = 4.0 if ch == " " else 6.0
        host_chars.append({"c": ch, "bbox": (x, 86.0, x + w, 100.0)})
        x += w

    stamp_chars = []
    sx = 94.0
    for ch in "3865":
        stamp_chars.append({"c": ch, "bbox": (sx, 85.0, sx + 6.5, 99.0)})
        sx += 6.5

    raw = {
        "blocks": [
            {
                "type": 0,
                "lines": [
                    {
                        "bbox": (70.0, 86.0, x, 100.0),
                        "wmode": 0,
                        "dir": (1.0, 0.0),
                        "spans": [
                            {
                                "bbox": (70.0, 86.0, x, 100.0),
                                "text": host_str,
                                "chars": host_chars,
                            }
                        ],
                    },
                    {
                        "bbox": (94.0, 85.0, sx, 99.0),
                        "wmode": 0,
                        "dir": (1.0, 0.0),
                        "spans": [
                            {
                                "bbox": (94.0, 85.0, sx, 99.0),
                                "text": "3865",
                                "chars": stamp_chars,
                            }
                        ],
                    },
                ],
            }
        ]
    }

    cleaned = _splice_overlapping_stamped_text(raw["blocks"])
    lines = cleaned[0]["lines"]
    assert len(lines) == 1
    merged_text = "".join(c["c"] for c in lines[0]["spans"][0]["chars"])
    assert "3865" in merged_text
    assert merged_text.startswith("Số:")
    assert merged_text.endswith("/QĐ-UBND")
