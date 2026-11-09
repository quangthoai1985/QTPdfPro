"""Tầng 2 `FunctionBar`: 5 thẻ, công cụ theo thẻ, tràn vào `⋯`, cột phải gọn, dòng thông báo mảnh."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton

from qtpdfpro.ui import commands
from ui_helpers import open_window

TAB_TOOLS = {
    "read": ["rotate_left", "rotate_right", "read_mode", "print", "doc_info"],
    "convert": ["split:convert_word:word", "ocr", "nd30_check", "verify_docx", "layout_overlay", "batch_convert"],
    "security": ["sig_inspect", "protect", "unlock"],
}


def test_tabs_and_tools_match_spec(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    assert list(win.function_bar.tab_buttons) == ["read", "convert", "edit", "fill", "security"]
    assert win.function_bar.current_tab() == "read"
    for key, tools in TAB_TOOLS.items():
        win.set_function_tab(key)
        assert list(win.function_bar.tool_buttons) == tools
    assert not hasattr(tab, "tools_panel") and not hasattr(win, "tool_strip")
    win.close()


def test_right_rail_only_panel_switchers(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    assert [b.toolTip().split(" (")[0] for b in tab.rail_panel_buttons] == ["Trang", "Mục lục", "Tìm kiếm", "Chú thích"]
    assert tab.sidebar_tabs.tabBar().isHidden()
    win.close()


def test_notice_line_dismiss_and_single_primary(qapp, admin_pdf):
    win, tab = open_window(admin_pdf)
    tab.wait_for_document_analysis()
    assert tab.notice_bar.isVisible() and tab.notice_link.objectName() == "linkBtn"
    tab.notice_close.click()
    tab._analyze_document()
    assert not tab.notice_bar.isVisible()
    win.set_function_tab("convert")
    primaries = [w for w in win.findChildren(QAbstractButton) if w.isVisible() and w.objectName() == "primaryConvertBtn"]
    assert len(primaries) == 1
    win.close()


def test_overflow_roundtrip_keeps_actions(qapp, sample_pdf):  # Review Focus 3
    win, tab = open_window(sample_pdf, width=1280)
    win.set_function_tab("convert")
    for w in (900, 1280, 900, 1600, 1280):
        win.resize(w, 800)
        qapp.processEvents()
        keys = win.function_bar.visible_command_keys()
        assert sorted(keys) == sorted(set(keys))  # không nhân đôi
        assert set(TAB_TOOLS["convert"]) <= set(win.function_bar.tool_buttons) | set(win.function_bar.overflow_keys())
    win.resize(900, 800)
    qapp.processEvents()
    hidden = win.function_bar.overflow_keys()
    assert hidden
    for k in hidden:  # mục trong ⋯ vẫn là QAction dùng được
        act = win.command_actions[commands.expand_layout_item(k)[0]]
        assert act.isEnabled() and act in win.function_bar.overflow_button.menu().actions()
    win.close()


def test_min_width_and_close_last_doc_in_edit(qapp, sample_pdf):  # Review Focus 4
    win, tab = open_window(sample_pdf)
    assert win.minimumSizeHint().width() <= 1280
    win.set_function_tab("edit")
    assert tab.edit_mode
    win.close_tab_at(0)
    assert win.stack.currentWidget() is win.home_page and not win.function_bar.isVisible()
    QTest.keyClick(win, Qt.Key.Key_3, Qt.KeyboardModifier.AltModifier)  # không có tài liệu → bỏ qua
    win2tab = win.open_pdf_path(sample_pdf)
    assert win.function_bar.current_tab() == "read" and not win2tab.edit_mode
    win.close()
