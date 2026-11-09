"""Nguồn lệnh duy nhất `ui/commands.py`, `QAction` dùng chung của `MainWindow` và bảng lệnh Ctrl+K."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFileDialog

from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import commands, icons
from qtpdfpro.ui.main_window import MainWindow
from ui_helpers import open_window


def test_command_keys_and_shortcuts_unique():
    keys = [c.key for c in commands.COMMANDS]
    assert len(keys) == len(set(keys))
    # Từng tổ hợp phím (lệnh có nhiều phím: "Ctrl+Y, Ctrl+Shift+Z") — so theo QKeySequence để "ctrl+s" = "Ctrl+S"
    sc = [QKeySequence(s).toString() for c in commands.COMMANDS if c.register_shortcut for s in c.shortcuts()]
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


def test_every_registered_shortcut_has_window_action(qapp):
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


# Spec §5.2 «Giữ nguyên» (V / H do QShortcut của từng tab) + «Thêm» Alt+1…5; F3 đã bỏ.
SPEC_SHORTCUTS = (
    "Ctrl+O", "Ctrl+S", "Ctrl+Shift+S", "Ctrl+P", "Ctrl+I", "Ctrl+F4", "Ctrl+F", "Ctrl+T", "Ctrl+K", "Ctrl+Z",
    "Ctrl+Y", "Ctrl++", "Ctrl+-", "Ctrl+1", "Ctrl+0", "F4", "F8", "F11", "Ctrl+Shift+W", "Ctrl+Shift+B",
    "Ctrl+Shift+R", "Ctrl+Shift+N", "Ctrl+Shift+O", "Ctrl+Shift+M", "Ctrl+Shift+T", "Alt+Home", "Ctrl+E",
    "Ctrl+Shift+F", "Alt+1", "Alt+2", "Alt+3", "Alt+4", "Alt+5",
)


def test_spec_shortcut_list_is_bound(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    bound = {QKeySequence(k).toString() for act in win.actions() for k in act.shortcuts()}
    bound |= {sc.key().toString() for sc in win.findChildren(QShortcut)}  # Alt+1…5 là QShortcut của cửa sổ
    missing = [k for k in SPEC_SHORTCUTS if QKeySequence(k).toString() not in bound]
    assert not missing, missing
    assert QKeySequence("F3").toString() not in bound
    tab_keys = {sc.key().toString() for sc in tab._pointer_shortcuts}  # V / H: QShortcut theo từng tab
    assert tab_keys == {"V", "H"}
    win.close()


def _record_open_dialogs(monkeypatch) -> list[str]:
    asked: list[str] = []
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: asked.append("open") or ([], ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: asked.append("source") or ("", ""))
    return asked


def test_palette_command_needing_document_cancelled_on_home(qapp, monkeypatch):
    win = MainWindow(settings=AppSettings.load())
    asked = _record_open_dialogs(monkeypatch)
    assert commands.get("doc_info").needs_document
    win.run_command("doc_info")
    assert asked == ["open"]  # hỏi mở tệp; huỷ → không đổi gì
    assert win.active_tab() is None and win.stack.currentWidget() is win.home_page
    win.close()


def test_quiet_command_shortcut_silent_but_palette_asks_to_open(qapp, monkeypatch):
    win = MainWindow(settings=AppSettings.load())
    asked = _record_open_dialogs(monkeypatch)
    for key in ("save", "undo", "close_tab", "zoom_in"):
        assert commands.get(key).quiet_without_document
        win.command_actions[key].trigger()  # đường phím tắt / QAction: im lặng
    assert asked == []
    win.run_command("save")  # đường Ctrl+K (spec §5.3): hỏi mở tệp rồi chạy
    assert asked == ["open"]
    assert win.active_tab() is None and win.stack.currentWidget() is win.home_page
    win.close()


def test_source_picking_tools_do_not_force_opening_a_tab(qapp, monkeypatch):
    win = MainWindow(settings=AppSettings.load())
    asked = _record_open_dialogs(monkeypatch)
    called: list[tuple] = []
    monkeypatch.setattr(win, "action_signature_library", lambda: called.append(("signatures",)))
    monkeypatch.setattr(win, "action_pdf_tool", lambda key: called.append(("pdf_tool", key)))
    monkeypatch.setattr(win, "action_organize", lambda mode="organize": called.append(("organize", mode)))
    for key in ("signatures", "compress", "organize"):
        win.run_command(key)
    assert called == [("signatures",), ("pdf_tool", "compress"), ("organize", "organize")]
    assert asked == [] and win.active_tab() is None


def test_needs_document_flags():
    """Lệnh dùng được khi chưa mở tài liệu / bắt buộc có tài liệu (spec §4)."""
    for k in ("print", "edit_mode", "pointer_select", "rotate_left", "find"):
        assert commands.get(k).needs_document, k
    win_free = ("ocr", "organize", "convert_word", "verify_docx", "split", "extract_pages", "watermark", "page_numbers", "protect",
                "unlock")
    assert not any(commands.get(k).needs_document for k in win_free)


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
    assert icons.current_color() == theme.theme_tokens("light")["text"]
    win._apply_theme("dark")
    assert icons.current_color() == theme.theme_tokens("dark")["text"]
    win.close()
