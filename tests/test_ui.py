"""Kiểm thử tự động giao diện đồ hoạ PySide6 của QT PDF Pro (`MainWindow`, `PDFScrollViewer`) và bộ ghép số văn bản đóng dấu."""

from __future__ import annotations

import re
from pathlib import Path
from PySide6.QtWidgets import QApplication

from qtpdfpro.core.converter import _splice_overlapping_stamped_text
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.convert_dialog import ConvertToDocxDialog
from qtpdfpro.ui.main_window import MainWindow
from qtpdfpro.ui.theme import get_stylesheet


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

    # Bố cục 2 tầng: tầng 2 (thanh chức năng) + thanh dọc phải; không còn cột «Tất cả công cụ»
    assert win.function_bar.isVisible() is True
    assert tab.right_rail.isVisible() is True
    assert not hasattr(tab, "tools_panel") and not hasattr(win, "action_toggle_left_tools")

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
    win._search_in_document("Độc lập")
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
    assert win.btn_theme_toggle.text() == "" and "Tối" in win.btn_theme_toggle.toolTip()

    win.btn_theme_toggle.click()
    app.processEvents()
    assert win.settings.theme == "dark"
    assert tab.viewer._canvas_theme == "dark"
    assert win.btn_theme_toggle.text() == "" and "Sáng" in win.btn_theme_toggle.toolTip()

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


def test_home_page_pdfcraft_layout(sample_vietnamese_pdf: Path) -> None:
    """Trang chủ kiểu PdfCraft: tab tài liệu ở dải tiêu đề."""
    from qtpdfpro.ui.command_palette import CommandPaletteDialog
    from qtpdfpro.ui import commands

    app = QApplication.instance() or QApplication([])
    win = MainWindow(settings=AppSettings.load())
    win.show()
    app.processEvents()

    # Mở ứng dụng → Trang chủ, nút ⌂ được chọn, không có điều khiển trang
    assert win.stack.currentWidget() is win.home_page
    assert win.btn_home.isChecked() is True
    assert win.function_bar.isVisible() is False  # tầng 2 (thẻ, công cụ, đổi trang) chỉ khi có tài liệu
    # Thanh top: Mở + nút ☰; chưa có tài liệu thì chưa có hàng tab
    assert win.btn_open.isVisible() and win.top_bar.btn_menu.isVisible()
    assert win.doc_tab_bar.isVisible() is False

    # Danh mục lệnh: khoá duy nhất; tìm không dấu
    keys = [c.key for c in commands.COMMANDS]
    assert len(keys) == len(set(keys))
    assert "nd30_check" in [c.key for c in commands.search("kiem tra the thuc", has_document=False)]

    # Trang chủ mới (Task 6): 8 ô công cụ nhanh, không còn danh mục / công cụ đề xuất
    assert not hasattr(win.home_page, "catalog")
    assert len(win.home_page.quick_tiles) == 8

    # Công cụ chưa làm không còn hiện trong ứng dụng; khoá lạ bị bỏ qua
    win.run_command("pdf_to_excel")
    app.processEvents()
    assert win._toast is None and "pdf_to_excel" not in commands.BY_KEY
    assert all(k in commands.BY_KEY for k in ("ocr", "edit_mode", "organize", "combine", "split", "extract_pages",
                                               "annot.stamp", "annot.highlight"))

    # Mở tài liệu → tab hiện ở dải tiêu đề, chuyển sang khung tài liệu
    tab = win.open_pdf_path(sample_vietnamese_pdf)
    app.processEvents()
    assert tab is not None
    assert win.doc_tab_bar.count() == 1 and win.doc_tabs.count() == 1
    assert win.doc_tab_bar.isVisible() is True
    assert win.stack.currentWidget() is win.doc_tabs
    assert win.function_bar.isVisible() is True and win.function_bar.current_tab() == "read"
    # «Xuất Word» (nút chính) và «Thuộc tính» nằm ở thẻ Chuyển đổi / Đọc của tầng 2
    assert "doc_info" in win.function_bar.tool_buttons
    win.set_function_tab("convert")
    app.processEvents()
    assert win.function_bar.tool_buttons["split:convert_word:word"].isVisible() is True
    win.set_function_tab("read")

    # Về Trang chủ và quay lại tài liệu
    win.action_go_home()
    app.processEvents()
    assert win.stack.currentWidget() is win.home_page
    assert win.home_page.btn_resume.isVisible() is True
    win.action_go_home()
    app.processEvents()
    assert win.stack.currentWidget() is win.doc_tabs

    # Bảng lệnh Ctrl+K (nguồn `ui/commands.py`): tìm "word" ra lệnh xuất Word + mục tìm trong tài liệu
    pal = CommandPaletteDialog(win, query="word", has_document=True)
    labels = [pal.list.item(i).text() for i in range(pal.list.count())]
    assert "trong tài liệu đang mở" in labels[0]
    assert any("Xuất Word chuẩn NĐ30" in s for s in labels)
    pal.close()

    # Đóng tab cuối → quay về Trang chủ
    win.close_tab_at(0)
    app.processEvents()
    assert win.doc_tab_bar.count() == 0 and win.doc_tab_bar.isVisible() is False
    assert win.stack.currentWidget() is win.home_page
    win.close()
    app.processEvents()


def test_function_bar_buttons_run_commands_and_follow_document(sample_vietnamese_pdf: Path, monkeypatch) -> None:
    """Tầng 2: ẩn ở Trang chủ; nút công cụ gọi đúng lệnh; «Lưu ▾» chỉ hiện ở thẻ Đọc khi có thay đổi chưa lưu;
    Alt+1…5 chuyển thẻ; F3 / «◧ Bảng công cụ» không còn."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence
    from PySide6.QtTest import QTest

    app = QApplication.instance() or QApplication([])
    win = MainWindow(settings=AppSettings.load())
    win.show()
    app.processEvents()
    assert win.function_bar.isVisible() is False
    shortcuts = {s.toString() for a in win.actions() for s in a.shortcuts()}
    assert QKeySequence("F3").toString() not in shortcuts

    tab = win.open_pdf_path(sample_vietnamese_pdf)
    app.processEvents()
    fb = win.function_bar
    assert fb.isVisible() is True and fb.current_tab() == "read"

    # Nút trên tầng 2 gọi đúng công cụ (QAction dùng chung)
    called: list[str] = []
    monkeypatch.setattr(win, "action_pdf_tool", lambda key: called.append(key))
    win.set_function_tab("security")
    fb.tool_buttons["protect"].click()
    assert called == ["protect"]
    assert fb.tool_buttons["sig_inspect"].text() == "Soi chữ ký số"  # nhãn ngắn; chú giải mang tên đầy đủ
    assert "Soi chữ ký số & con dấu" in fb.tool_buttons["sig_inspect"].toolTip()
    QTest.keyClick(win, Qt.Key.Key_1, Qt.KeyboardModifier.AltModifier)  # Alt+1 → thẻ Đọc
    app.processEvents()
    assert fb.current_tab() == "read"
    fb.tool_buttons["rotate_left"].click()
    app.processEvents()
    assert tab.reader._page_rotations.get(tab.viewer.current_page) == 270

    # Đổi trang / thu phóng ở cụm điều khiển xem
    fb.btn_next_page.click()
    app.processEvents()
    assert tab.viewer.current_page == 1 and fb.page_spin.value() == 2 and fb.total_page_lbl.text() == "/ 2"
    fb.zoom_combo.activated.emit(fb.zoom_combo.findText("150%"))
    app.processEvents()
    assert tab.viewer.zoom_percent == 150 and fb.zoom_combo.currentText() == "150%"

    # Có thay đổi chưa lưu (tô sáng từ công cụ Chọn chữ) → «Lưu ▾» cuối vùng công cụ của thẻ Đọc
    assert "split:save:save" not in fb.tool_buttons
    tab._highlight_selection(0, [(72, 85, 300, 104)])
    app.processEvents()
    assert "split:save:save" in fb.tool_buttons
    assert fb.tool_buttons["split:save:save"].objectName() == "primaryConvertBtn"
    win.set_function_tab("convert")  # thẻ Chuyển đổi: «Xuất Word» là nút chính duy nhất
    assert fb.tool_buttons["split:save:save"].objectName() != "primaryConvertBtn"
    tab.annot_controller.undo()
    app.processEvents()
    assert "split:save:save" not in fb.tool_buttons

    # Về Trang chủ → ẩn tầng 2
    win.action_go_home()
    app.processEvents()
    assert fb.isVisible() is False
    win.close_tab_at(0, force=True)
    win.close()
    app.processEvents()


def test_convert_dialog_initial_mode_and_nd30_policy(sample_vietnamese_pdf: Path) -> None:
    app = QApplication.instance() or QApplication([])
    settings = AppSettings.load()
    dlg = ConvertToDocxDialog(sample_vietnamese_pdf, 2, 0, settings, initial_mode="exact")
    assert dlg.mode_combo.currentData() == "exact"
    assert dlg.policy_combo.isEnabled() is False
    dlg.mode_combo.setCurrentIndex(dlg.mode_combo.findData("nd30"))
    app.processEvents()
    assert dlg.policy_combo.isEnabled() is True
    assert dlg.policy_combo.currentData() == "faithful"
    dlg.close()


def test_theme_styles_radio_and_checkbox_indicators(isolated_app_data: Path) -> None:
    """Radio/checkbox đang chọn phải có kiểu QSS riêng (kiểu `windows11` + QSS không vẽ chấm radio)."""
    for theme in ("dark", "light"):
        qss = get_stylesheet(theme)
        assert "QRadioButton::indicator:checked" in qss
        assert "QCheckBox::indicator:checked" in qss
        assert re.search(r"@[a-z_]+", qss) is None  # mọi khoá màu đã được thay
    icon = isolated_app_data / "theme" / "check_ffffff.svg"
    assert icon.exists()
    assert f'url("{icon.as_posix()}")' in get_stylesheet("dark")


def test_app_icon_has_all_sizes() -> None:
    """Icon ứng dụng có đủ cỡ cho thanh tiêu đề (16), thanh tác vụ (24–48) và Explorer (256)."""
    from qtpdfpro.ui.app import ICON_PATH, app_icon

    app = QApplication.instance() or QApplication([])
    assert ICON_PATH.exists()
    icon = app_icon()
    assert not icon.isNull()
    sizes = {s.width() for s in icon.availableSizes()}
    assert {16, 24, 32, 48, 256} <= sizes
    app.processEvents()
