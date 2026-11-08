"""Nguồn lệnh duy nhất `ui/commands.py`, `QAction` dùng chung của `MainWindow` và bảng lệnh Ctrl+K."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QFileDialog

from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import commands, icons
from qtpdfpro.ui.main_window import MainWindow


def test_command_keys_and_shortcuts_unique():
    keys = [c.key for c in commands.COMMANDS]
    assert len(keys) == len(set(keys))
    sc = [c.shortcut for c in commands.COMMANDS if c.shortcut and c.register_shortcut]
    assert len(sc) == len(set(sc))
    assert "F3" not in sc


def test_layout_groups_and_icons_exist():
    for tab, items in commands.TAB_LAYOUT.items():
        assert tab in dict(commands.TABS)
        for item in items:  # khoá / group: / split: / date_formats / |
            for key in commands.expand_layout_item(item):
                assert key in commands.BY_KEY, (tab, item)
    for c in commands.COMMANDS:
        assert c.icon in icons.ICON_NAMES, c.key
    assert commands.expand_layout_item("|") == ()
    assert commands.expand_layout_item("date_formats") == ("annot.fill_date",)
    assert commands.expand_layout_item("split:convert_word:word") == ("convert_word", *commands.GROUPS["word"])
    for name, members in commands.GROUPS.items():
        assert members and all(commands.get(k).group == name for k in members)
    assert all(k in commands.BY_KEY for k in commands.HOME_QUICK_TOOLS)


def test_search_is_accent_insensitive_and_has_system_commands():
    assert commands.search("xuat word")[0].key == "convert_word"
    assert "close_tab" in [c.key for c in commands.search("dong tai lieu")]
    assert not [c for c in commands.COMMANDS if "soon" in c.keywords.lower()]
    everything = commands.search("")
    assert "palette" not in [c.key for c in everything]  # palette=False
    tab_order = [k for k, _ in commands.TABS] + ["system"]
    assert [c.tab for c in everything] == sorted((c.tab for c in everything), key=tab_order.index)


def test_every_registered_shortcut_has_window_action(qapp, tmp_path):
    win = MainWindow(settings=AppSettings.load())
    for c in commands.COMMANDS:
        act = win.command_actions[c.key]
        assert act in win.actions()
        if c.shortcut and c.register_shortcut:
            assert act.shortcut().toString() == QKeySequence(c.shortcut.split(",")[0]).toString()
        elif not c.register_shortcut:
            assert act.shortcut().isEmpty(), c.key
    assert win.act_save is win.command_actions["save"]
    assert win.pointer_actions["hand"] is win.command_actions["pointer_hand"]
    assert win.command_actions["check_update"] is win.updater.act_check
    win.close()


def test_palette_command_needing_document_cancelled_on_home(qapp, monkeypatch):
    win = MainWindow(settings=AppSettings.load())
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([], ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    win.run_command("compress")
    assert win.active_tab() is None and win.stack.currentWidget() is win.home_page
    win.close()


def test_command_palette_lists_commands_with_shortcuts(qapp):
    from qtpdfpro.ui.command_palette import SEARCH_IN_DOCUMENT_KEY, CommandPaletteDialog

    win = MainWindow(settings=AppSettings.load())
    pal = CommandPaletteDialog(win, query="dong tai lieu", has_document=False)
    keys = [pal.list.item(i).data(pal.KEY_ROLE) for i in range(pal.list.count())]
    assert "close_tab" in keys and SEARCH_IN_DOCUMENT_KEY not in keys
    item = pal.list.item(keys.index("close_tab"))
    assert "Ctrl+F4" in item.data(pal.SHORTCUT_ROLE) and item.data(pal.NOTE_ROLE) == "cần mở tệp"
    pal.close()
    pal = CommandPaletteDialog(win, query="word", has_document=True)
    assert pal.list.item(0).data(pal.KEY_ROLE) == SEARCH_IN_DOCUMENT_KEY
    keys = [pal.list.item(i).data(pal.KEY_ROLE) for i in range(pal.list.count())]
    assert "convert_word" in keys and pal.list.item(keys.index("convert_word")).data(pal.NOTE_ROLE) == ""
    pal.close()
    win.close()


def test_theme_sets_icon_color_from_tokens(qapp):
    from qtpdfpro.ui import theme

    win = MainWindow(settings=AppSettings.load())
    win._apply_theme("light")
    assert icons.current_color() == theme._LIGHT_TOKENS["text"]
    win._apply_theme("dark")
    assert icons.current_color() == theme._DARK_TOKENS["text"]
    win.close()
