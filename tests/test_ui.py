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

    # Bố cục kiểu PdfCraft: cột trái «Tất cả công cụ» mặc định ẩn, công cụ nằm trên thanh công cụ nhanh
    assert tab.tools_panel.isVisible() is False
    assert win.tool_strip.isVisible() is True
    assert tab.right_rail.isVisible() is True

    # F3 bật cột trái rồi lọc công cụ
    win.action_toggle_left_tools()
    app.processEvents()
    assert tab.tools_panel.isVisible() is True
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


def test_home_page_pdfcraft_layout_and_coming_soon(sample_vietnamese_pdf: Path) -> None:
    """Trang chủ kiểu PdfCraft: danh mục công cụ, công cụ đề xuất, Coming Soon, tab tài liệu ở dải tiêu đề."""
    from qtpdfpro.ui.command_palette import CommandPaletteDialog
    from qtpdfpro.ui.home_page import CatalogRow, ToolCard
    from qtpdfpro.ui.tool_catalog import COMING_SOON_LABEL, TOOLS, get_tool, tools_for

    app = QApplication.instance() or QApplication([])
    win = MainWindow(settings=AppSettings.load())
    win.show()
    app.processEvents()

    # Mở ứng dụng → Trang chủ, nút ⌂ được chọn, không có điều khiển trang
    assert win.stack.currentWidget() is win.home_page
    assert win.btn_home.isChecked() is True
    assert win.doc_controls.isVisible() is False
    assert win.btn_convert_docx.isVisible() is False  # «Xuất Word» và «ℹ» nằm trong doc_controls
    # Thanh top: Mở + các menu nằm ngang; chưa có tài liệu thì chưa có hàng tab
    assert win.btn_open.isVisible() and set(win.menu_buttons) == {
        "Tệp", "Xem", "Công cụ", "Chỉnh sửa PDF", "Trợ giúp"}
    assert all(b.isVisible() and b.menu() is not None for b in win.menu_buttons.values())
    assert win.tab_strip.isVisible() is False

    # Danh mục: khoá duy nhất, công cụ chưa có đều có mốc phát hành và nhãn Coming Soon
    keys = [t.key for t in TOOLS]
    assert len(keys) == len(set(keys))
    soon = [t for t in TOOLS if not t.ready]
    assert soon and all(t.milestone for t in soon)
    assert all(t.status_text == COMING_SOON_LABEL for t in soon)
    # Tìm không dấu
    assert [t.key for t in tools_for("all", "kiem tra the thuc")] == ["nd30_check"]

    cards = win.home_page.findChildren(ToolCard)
    assert {c.tool.key for c in cards} >= {"pdf_to_word_nd30", "nd30_check", "organize"}
    rows = win.home_page.catalog.findChildren(CatalogRow)
    assert len(rows) == len(TOOLS)

    # Lọc theo chế độ "Chuyển đổi"
    win.set_mode_category("convert")
    app.processEvents()
    assert set(win.home_page.catalog.tool_keys()) == {t.key for t in TOOLS if t.category == "convert"}
    win.set_mode_category("all")

    # Công cụ Coming Soon → chỉ hiện thông báo, không mở hộp thoại
    win.run_tool("ocr")
    app.processEvents()
    assert win._toast is not None and COMING_SOON_LABEL in win._toast.text()
    assert get_tool("ocr").ready is False
    # Nhóm «Chỉnh sửa PDF» đã dùng được
    assert all(get_tool(k).ready for k in ("edit_pdf", "organize", "combine", "split", "extract_pages",
                                            "comments", "stamp", "highlight_text"))

    # Mở tài liệu → tab hiện ở dải tiêu đề, chuyển sang khung tài liệu
    tab = win.open_pdf_path(sample_vietnamese_pdf)
    app.processEvents()
    assert tab is not None
    assert win.doc_tab_bar.count() == 1 and win.doc_tabs.count() == 1
    assert win.tab_strip.isVisible() is True
    assert win.stack.currentWidget() is win.doc_tabs
    assert win.doc_controls.isVisible() is True and win.btn_convert_docx.isVisible() is True

    # Lọc thẻ công cụ trong khung tài liệu theo chế độ (cột trái ẩn → kiểm bằng isHidden)
    win.set_mode_category("convert")
    app.processEvents()
    assert tab.tool_btn_convert_nd30.isHidden() is False
    assert tab.tool_btn_rot_left.isHidden() is True
    win.set_mode_category("all")
    app.processEvents()
    assert tab.tool_btn_rot_left.isHidden() is False

    # Về Trang chủ và quay lại tài liệu
    win.action_go_home()
    app.processEvents()
    assert win.stack.currentWidget() is win.home_page
    assert win.home_page.btn_resume.isVisible() is True
    win.action_go_home()
    app.processEvents()
    assert win.stack.currentWidget() is win.doc_tabs

    # Bảng lệnh Ctrl+K: tìm "word" ra công cụ chuyển đổi + mục tìm trong tài liệu
    pal = CommandPaletteDialog(win, query="word", has_document=True)
    labels = [pal.list.item(i).text() for i in range(pal.list.count())]
    assert "trong tài liệu đang mở" in labels[0]
    assert any("PDF sang Word chuẩn NĐ30" in s for s in labels)
    pal.close()

    # Đóng tab cuối → quay về Trang chủ
    win.close_tab_at(0)
    app.processEvents()
    assert win.doc_tab_bar.count() == 0 and win.tab_strip.isVisible() is False
    assert win.stack.currentWidget() is win.home_page
    win.close()
    app.processEvents()


def test_tool_strip_replaces_left_panel_and_remembers_choice(sample_vietnamese_pdf: Path, monkeypatch) -> None:
    """Xem tài liệu: cột trái ẩn mặc định, công cụ lên thanh công cụ nhanh theo chế độ; F3 / ✕ được ghi nhớ."""
    from qtpdfpro.ui.main_window import STRIP_TOOLS
    from qtpdfpro.ui.tool_catalog import get_tool

    # Mọi khoá trên thanh công cụ nhanh đều là công cụ trong danh mục hoặc lệnh riêng «:...»
    for entries in STRIP_TOOLS.values():
        for _label, key in entries:
            assert key.startswith(":") or get_tool(key) is not None, key

    app = QApplication.instance() or QApplication([])
    win = MainWindow(settings=AppSettings.load())
    win.show()
    app.processEvents()
    assert win.tool_strip.isVisible() is False  # Trang chủ không có thanh công cụ nhanh

    tab = win.open_pdf_path(sample_vietnamese_pdf)
    app.processEvents()
    assert win.tool_strip.isVisible() is True
    assert tab.tools_panel.isVisible() is False
    assert win.btn_strip_panel.isChecked() is False
    assert set(win.strip_buttons) == {k for _l, k in STRIP_TOOLS["all"]}

    # Đổi chế độ → đổi nút; nút cũ ẩn ngay; cột trái không tự bật
    old_btn = win.strip_buttons["pdf_to_word_nd30"]
    win.set_mode_category("convert")
    app.processEvents()
    assert set(win.strip_buttons) == {k for _l, k in STRIP_TOOLS["convert"]}
    assert old_btn.isHidden() is True
    assert tab.tools_panel.isVisible() is False
    win.set_mode_category("sign")
    app.processEvents()
    assert win.strip_buttons["sign_pdf"].objectName() == "stripToolSoonBtn"  # Coming Soon
    assert win.strip_buttons["protect"].objectName() == "stripToolBtn"

    # Nút trên thanh gọi đúng công cụ
    called: list[str] = []
    monkeypatch.setattr(win, "action_pdf_tool", lambda key: called.append(key))
    win.strip_buttons["protect"].click()
    assert called == ["protect"]
    win.set_mode_category("read")
    app.processEvents()
    win.strip_buttons[":rotate_left"].click()
    app.processEvents()
    assert tab.reader._page_rotations.get(tab.viewer.current_page) == 270

    # Nút «◧ Bảng công cụ» bật cột trái ở mọi tab và ghi nhớ; tab mở sau theo lựa chọn đó
    win.btn_strip_panel.click()
    app.processEvents()
    assert tab.tools_panel.isVisible() is True
    assert AppSettings.load().show_tools_panel is True
    second_pdf = sample_vietnamese_pdf.with_name("ban_sao.pdf")
    second_pdf.write_bytes(sample_vietnamese_pdf.read_bytes())
    tab2 = win.open_pdf_path(second_pdf)
    app.processEvents()
    assert tab2 is not None and tab2.tools_panel.isVisible() is True

    # ✕ trên cột trái tắt ở mọi tab và ghi nhớ; F3 bật lại
    tab2.toolsPanelHideRequested.emit()
    app.processEvents()
    assert tab2.tools_panel.isHidden() is True and tab.tools_panel.isHidden() is True
    assert win.btn_strip_panel.isChecked() is False
    assert AppSettings.load().show_tools_panel is False
    win.action_toggle_left_tools()
    app.processEvents()
    assert tab2.tools_panel.isVisible() is True and win.btn_strip_panel.isChecked() is True

    # Về Trang chủ → ẩn thanh công cụ nhanh
    win.action_go_home()
    app.processEvents()
    assert win.tool_strip.isVisible() is False
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
