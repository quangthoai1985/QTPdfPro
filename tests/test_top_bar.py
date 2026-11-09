"""Tầng 1: TopBar + menu ☰."""

from __future__ import annotations

from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.main_window import MainWindow
from ui_helpers import open_window


def test_hamburger_menu_contents_in_spec_order(qapp):
    win = MainWindow(settings=AppSettings.load())
    texts = [a.text().replace("&&", "&").split("\t")[0] for a in win.top_bar.menu.actions() if not a.isSeparator()]
    assert texts == ["Mở tệp…", "Tệp mở gần đây", "Đóng tài liệu", "Lưu", "Lưu thành tệp mới…",
                     "Ẩn/hiện ngăn bên phải", "Cài đặt", "Kiểm tra cập nhật…", "Có gì mới trong bản này",
                     "Mã nguồn & báo lỗi (GitHub)", "Giới thiệu QT PDF Pro", "Thoát"]
    assert not win.command_actions["close_tab"].isEnabled()  # chưa có tài liệu
    win.close()


def test_top_bar_has_no_text_menus_and_tabs_inline(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    assert not hasattr(win, "menu_buttons") and not hasattr(win, "tab_strip")
    assert win.top_bar.tab_bar.count() == 1 and win.top_bar.tab_bar.isVisible()
    assert win.command_actions["close_tab"].isEnabled()
    assert win.top_bar.visible_command_keys() == ["home", "open", "palette", "toggle_theme"]
    win.close()


def test_theme_button_is_icon_only_and_toggles(qapp):
    win = MainWindow(settings=AppSettings.load())
    assert win.top_bar.btn_theme.text() == ""
    before = win.settings.theme
    win.top_bar.btn_theme.click()
    assert win.settings.theme != before
    win.close()


def test_search_box_opens_palette_prefilled(qapp, monkeypatch):
    win = MainWindow(settings=AppSettings.load())
    seen: list[str] = []
    monkeypatch.setattr(win, "action_command_palette", lambda query="": seen.append(query))
    win.top_bar.paletteRequested.disconnect()
    win.top_bar.paletteRequested.connect(lambda q: win.action_command_palette(q))
    win.top_bar.search.setText("nén")
    win.top_bar.search.returnPressed.emit()
    assert seen == ["nén"] and win.top_bar.search.text() == ""
    win.close()
