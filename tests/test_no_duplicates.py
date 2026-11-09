"""Mỗi lệnh chỉ có một nút trên màn hình (spec §9 mục 2) + công cụ chú thích ở tầng 2 (spec §3)."""

from __future__ import annotations

import fitz
import pytest

from qtpdfpro.core import fill_sign as fs
from qtpdfpro.ui import commands
from ui_helpers import copy_pdf, open_window


def _visible_keys(win, tab):
    keys = win.top_bar.visible_command_keys() + win.function_bar.visible_command_keys()
    keys += [b.property("command_key") for b in tab.rail_panel_buttons]
    return [k for k in keys if k]


def _duplicate_commands(win, tab) -> list[str]:
    """Khoá lệnh có hơn một nút trên màn hình hiện tại (rỗng = đạt)."""
    flat = [x for k in _visible_keys(win, tab) for x in commands.expand_layout_item(k)]
    return sorted({x for x in flat if flat.count(x) > 1})


def _modify(tab):
    tab.annot_controller.session.add_markup(0, "highlight", [fitz.Rect(72, 90, 200, 105)],
                                            tab.annot_controller.style("highlight").copy())
    tab._on_annotations_changed(0)


@pytest.mark.parametrize("modified", [False, True])
def test_each_command_appears_once_per_screen(qapp, sample_pdf, modified):
    win, tab = open_window(sample_pdf)
    if modified:
        _modify(tab)
    for key, _label in commands.TABS:
        win.set_function_tab(key)
        qapp.processEvents()
        assert _duplicate_commands(win, tab) == [], (key, sorted(_visible_keys(win, tab)))
    win.close_tab_at(0, force=True)
    win.close()


@pytest.mark.parametrize("tab_key, extra, modified, expected", [
    ("edit", "undo", False, "undo"),                         # cùng phần tử đặt hai lần
    ("fill", "annot.eraser", False, "annot.eraser"),
    ("edit", "annot.highlight", False, "annot.highlight"),   # trùng với một mục của nhóm «Đánh dấu chữ ▾»
    ("read", "split:save:save", True, "save"),               # trùng «Lưu ▾» tự thêm khi có thay đổi chưa lưu
    ("read", "fit_width", False, "fit_width"),               # trùng mục của ô thu phóng
    ("read", "find", False, "find"),                         # trùng nút thanh dọc
])
def test_duplicate_detector_is_not_vacuous(qapp, sample_pdf, monkeypatch, tab_key, extra, modified, expected):
    win, tab = open_window(sample_pdf)
    if modified:
        _modify(tab)
    monkeypatch.setitem(commands.TAB_LAYOUT, tab_key, commands.TAB_LAYOUT[tab_key] + (extra,))
    win.set_function_tab("security")
    win.set_function_tab(tab_key)  # dựng lại tầng 2 với bố cục bị đặt trùng
    qapp.processEvents()
    assert expected in _duplicate_commands(win, tab)
    win.close_tab_at(0, force=True)
    win.close()


def test_rail_buttons_carry_command_keys(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    assert [b.property("command_key") for b in tab.rail_panel_buttons] == [
        "panel_pages", "panel_toc", "find", "panel_annotations"]
    win.command_actions["panel_toc"].trigger()
    assert tab.sidebar_tabs.isVisible() and tab.sidebar_tabs.currentIndex() == 1
    win.command_actions["panel_toc"].trigger()  # bấm lại ngăn đang mở → ẩn ngăn (spec §2.4)
    assert not tab.sidebar_tabs.isVisible()
    win.command_actions["panel_annotations"].trigger()
    assert tab.sidebar_tabs.isVisible() and tab.sidebar_tabs.currentIndex() == 4
    win.close()


def _expanded(win):
    return {k for item in win.function_bar.visible_command_keys() for k in commands.expand_layout_item(item)}


def test_annotation_tools_live_in_function_bar(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    win.set_function_tab("edit")
    keys = _expanded(win)
    assert {"annot.select", "annot.highlight", "annot.pen", "annot.stamp", "annot.eraser"} <= set(keys)
    for gone in ("tool_buttons", "btn_save", "btn_exit", "btn_organize", "btn_undo", "date_box", "btn_manage_sig"):
        assert not hasattr(tab.edit_toolbar, gone) and not hasattr(tab.fill_toolbar, gone), gone
    btn = win.function_bar.tool_buttons["annot.stamp"]
    assert btn.text() == "Dấu đóng" and btn.toolButtonStyle().name == "ToolButtonIconOnly"
    assert btn.toolTip() == "Dấu đóng (D)"
    win.set_function_tab("fill")
    keys = _expanded(win)
    assert {"annot.fill_text", "annot.fill_check", "annot.fill_date", "signatures"} <= set(keys)
    assert "annot.highlight" not in keys
    win.close()


def test_edit_tab_tools_drive_active_tab_controller(qapp, sample_pdf, tmp_path):   # Review Focus 1
    win, tab1 = open_window(sample_pdf)
    tab2 = win.open_pdf_path(copy_pdf(sample_pdf, tmp_path / "b.pdf"))
    win.set_function_tab("edit")
    win.command_actions["annot.rect"].trigger()
    assert tab2.annot_controller.tool == "rect" and tab2.edit_mode
    win.top_bar.tab_bar.setCurrentIndex(0)
    assert tab1.edit_mode and win.function_bar.current_tab() == "edit"
    win.command_actions["annot.pen"].trigger()
    assert tab1.annot_controller.tool == "pen" and tab2.annot_controller.tool == "rect"
    # Thân nút «Vẽ ▾» theo công cụ của tab đang xem
    assert win.function_bar.tool_buttons["group:draw"].defaultAction() is win.command_actions["annot.pen"]
    win.top_bar.tab_bar.setCurrentIndex(1)
    assert win.command_actions["annot.rect"].isChecked() and not win.command_actions["annot.pen"].isChecked()
    win.close()


def test_group_body_remembers_tool_from_any_route(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    win.set_function_tab("edit")
    fb = win.function_bar
    draw = fb.tool_buttons["group:draw"]
    win.command_actions["annot.ellipse"].trigger()  # như chọn từ ⋯ / Ctrl+K
    assert draw.defaultAction() is win.command_actions["annot.ellipse"] and draw.isChecked()
    tab.annot_controller.set_tool("arrow")  # như phím chữ cái A
    assert draw.defaultAction() is win.command_actions["annot.arrow"]
    win.command_actions["annot.select"].trigger()
    assert draw.defaultAction() is win.command_actions["annot.arrow"] and not draw.isChecked()
    assert fb.tool_buttons["annot.select"].isChecked()
    win.set_function_tab("read")
    win.set_function_tab("edit")  # dựng lại nút: vẫn nhớ kiểu vừa dùng
    draw = fb.tool_buttons["group:draw"]
    assert draw.defaultAction() is win.command_actions["annot.arrow"]
    draw.click()  # bấm thẳng thân nút = dùng lại kiểu đó
    assert tab.annot_controller.tool == "arrow"
    win.close()


def test_pointer_buttons_unchecked_while_annotating(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    fb = win.function_bar
    assert fb.btn_pointer_select.isChecked()
    win.set_function_tab("edit")
    assert not fb.btn_pointer_select.isChecked() and not fb.btn_pointer_hand.isChecked()
    fb.btn_pointer_hand.click()  # rời chế độ chỉnh sửa, về Đọc với Bàn tay
    assert not tab.edit_mode and fb.current_tab() == "read"
    assert fb.btn_pointer_hand.isChecked() and not fb.btn_pointer_select.isChecked()
    win.close()


def test_save_visible_in_read_tab_only_when_modified(qapp, sample_pdf, monkeypatch):  # Review Focus 2
    win, tab = open_window(sample_pdf)
    win.set_function_tab("read")
    assert "split:save:save" not in win.function_bar.visible_command_keys()
    tab.text_select.highlightRequested.emit(0, [fitz.Rect(72, 90, 200, 105)])
    assert "split:save:save" in win.function_bar.visible_command_keys()
    win.command_actions["save"].trigger()
    assert not tab.reader.has_unsaved_changes and "split:save:save" not in win.function_bar.visible_command_keys()
    win.close()


def test_style_row_only_for_tools_with_style(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    win.set_function_tab("edit")
    win.command_actions["annot.select"].trigger()
    assert not tab.edit_toolbar.isVisible()
    win.command_actions["annot.highlight"].trigger()
    assert tab.edit_toolbar.color_box.isVisible()
    win.command_actions["annot.eraser"].trigger()
    assert not tab.edit_toolbar.isVisible()
    win.set_function_tab("read")
    assert not tab.edit_toolbar.isVisible() and not tab.fill_toolbar.isVisible()
    win.close()


def test_date_formats_button_sets_format_and_tool(qapp, sample_pdf):
    win, tab = open_window(sample_pdf)
    win.set_function_tab("fill")
    fb = win.function_bar
    btn = fb.tool_buttons["date_formats"]
    labels = [a.text() for a in btn.menu().actions()]
    assert labels == [fs.format_date(k).replace("&", "&&") for k, _p in fs.DATE_FORMATS]
    fb.date_format_actions["dmy"].setText("cũ")  # như nhãn dựng từ hôm qua: mở menu → nhãn theo hôm nay
    btn.menu().aboutToShow.emit()
    assert fb.date_format_actions["dmy"].text() == fs.format_date("dmy")
    fb.date_format_actions["nd30"].trigger()
    ctl = tab.annot_controller
    assert ctl.date_format == "nd30" and ctl.tool == "fill_date" and tab.toolset == "fill"
    assert fb.date_format_actions["nd30"].isChecked() and btn.isChecked()
    assert not hasattr(tab.fill_toolbar, "date_box")
    win.close()


def test_min_width_with_document_in_every_tab(qapp, sample_pdf):
    win, tab = open_window(sample_pdf, width=1280)
    for key, _label in commands.TABS:
        win.set_function_tab(key)
        qapp.processEvents()
        assert win.minimumSizeHint().width() <= 1280, key
        if key in ("edit", "fill"):  # «Lưu ▾» luôn hiện ở thẻ chỉnh sửa, công cụ khác tràn vào ⋯ trước
            assert win.function_bar.tool_buttons["split:save:save"].isVisible(), key
            assert "split:save:save" not in win.function_bar.overflow_keys()
    win.resize(900, 700)
    win.set_function_tab("edit")
    qapp.processEvents()
    fb = win.function_bar
    assert fb.overflow_keys() and fb.tool_buttons["split:save:save"].isVisible()
    assert fb.overflow_button.isVisible()
    assert fb.overflow_button.x() < fb.tool_buttons["split:save:save"].x()  # ⋯ đứng trước «Lưu ▾»
    win.close()
