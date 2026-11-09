"""Trang chủ mới: lời chào, Bắt đầu, Gần đây, 8 ô công cụ nhanh, một dòng quyền riêng tư."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from qtpdfpro import __version__
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import commands
from qtpdfpro.ui.main_window import MainWindow


def test_home_sections_and_quick_tools(qapp):
    win = MainWindow(settings=AppSettings.load())
    home = win.home_page
    assert list(home.quick_tiles) == list(commands.HOME_QUICK_TOOLS)
    assert not hasattr(home, "catalog")
    assert home.version_chip.text() == f"v{__version__}"
    primaries = [b for b in home.findChildren(QPushButton) if b.objectName() == "primaryConvertBtn"]
    assert primaries == [home.btn_nd30_convert]
    assert not win.function_bar.isVisible()
    win.close()


def test_quick_tile_runs_command(qapp, monkeypatch):
    win = MainWindow(settings=AppSettings.load())
    seen = []
    monkeypatch.setattr(win, "run_command", seen.append)
    win.home_page.quick_tiles["batch_convert"].click()
    assert seen == ["batch_convert"]
    win.close()


def test_nd30_buttons_and_signals(qapp, monkeypatch):
    win = MainWindow(settings=AppSettings.load())
    monkeypatch.setattr(win, "run_command", lambda key: None)
    home = win.home_page
    got = []
    home.commandRequested.connect(got.append)
    home.btn_nd30_convert.click()
    home.btn_nd30_check.click()
    assert got == ["convert_word_nd30", "nd30_check"]
    home.openRequested.disconnect()  # không mở hộp thoại chọn tệp thật
    shown = []  # chip phiên bản mở «Có gì mới»: không mở hộp thoại thật
    win.whats_new.dialog_factory = lambda notes, parent: type("D", (), {"exec": lambda self: shown.append(1)})()
    opened, chip = [], []
    home.openRequested.connect(lambda: opened.append(1))
    home.versionClicked.connect(lambda: chip.append(1))
    home.version_chip.click()
    home.open_card.clicked.emit()
    assert opened == [1] and chip == [1]
    assert "ngoại tuyến" in home.privacy_lbl.text()
    win.close()


def test_recent_list_limit_and_empty_hint(qapp, tmp_path):
    win = MainWindow(settings=AppSettings.load())
    home = win.home_page
    files = []
    for i in range(8):
        p = tmp_path / f"t{i}.pdf"
        p.write_bytes(b"%PDF-1.4\n")
        files.append(str(p))
    home.set_recent_files(files)
    assert len(home.recent_rows) == 6
    got = []
    home.recentActivated.disconnect()  # không mở tệp thật
    home.recentActivated.connect(got.append)
    home.recent_rows[1].clicked.emit()
    assert got == [files[1]]
    home.set_recent_files([])
    assert home.recent_rows == []
    assert not home.btn_resume.isVisible()
    home.set_recent_files([], has_open_docs=True)
    assert not home.btn_resume.isHidden()
    win.close()


def test_home_responsive_columns(qapp):
    win = MainWindow(settings=AppSettings.load())
    win.resize(1100, 700)
    win.show()
    qapp.processEvents()
    home = win.home_page
    assert home._tile_cols == 4 and home._start_cols == 2
    win.resize(700, 700)
    qapp.processEvents()
    assert home._tile_cols == 2 and home._start_cols == 1
    assert not home._scroll.horizontalScrollBar().isVisible()
    win.close()
