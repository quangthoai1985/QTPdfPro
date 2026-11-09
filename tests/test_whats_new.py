"""«Có gì mới»: luật hiện ghi chú, tệp ghi chú đi kèm, thứ tự khởi động và hộp thoại."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest

from qtpdfpro import __version__
from qtpdfpro.core import whats_new as wn
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import icons
from qtpdfpro.ui import whats_new_dialog as wnd
from qtpdfpro.ui.main_window import MainWindow

N = [wn.VersionNotes("1.4.0", "", "", ()), wn.VersionNotes("1.3.0", "", "", ()), wn.VersionNotes("1.2.1", "", "", ())]


class FakeDialog:
    def __init__(self, shown, notes):
        self.shown, self.notes = shown, notes

    def exec(self):
        self.shown.append(self.notes)
        return 1


def test_notes_to_show_rules():
    assert wn.notes_to_show("1.3.0", "", False, N) == []  # cài mới
    assert [n.version for n in wn.notes_to_show("1.3.0", "", True, N)] == ["1.3.0"]  # cập nhật từ bản cũ
    assert wn.notes_to_show("1.3.0", "1.3.0", True, N) == []
    assert [n.version for n in wn.notes_to_show("1.4.0", "1.2.1", True, N)] == ["1.4.0", "1.3.0"]


def test_broken_file_gives_empty(tmp_path):
    p = tmp_path / "w.json"
    p.write_text("{hỏng", encoding="utf-8")
    assert wn.load_notes(p) == []
    assert wn.load_notes(tmp_path / "khong_co.json") == []
    p.write_text('{"versions": 5}', encoding="utf-8")
    assert wn.load_notes(p) == []


def test_bundled_notes_valid():
    notes = wn.load_notes()
    assert notes and 3 <= len(notes[0].items) <= 6
    assert all(i.icon in icons.ICON_NAMES for n in notes for i in n.items)
    assert all(n.date and n.headline for n in notes)


def test_startup_shows_once_then_records(qapp, monkeypatch):
    s = AppSettings.load()
    s.existed = True
    s.last_seen_version = "1.0.0"
    win = MainWindow(settings=s)
    shown = []
    win.whats_new.dialog_factory = lambda notes, parent: FakeDialog(shown, notes)
    monkeypatch.setattr(wn, "load_notes", lambda path=None: [wn.VersionNotes(__version__, "", "", ())])
    assert win.whats_new.on_startup() is True
    win.whats_new._show_due()
    assert shown and AppSettings.load().last_seen_version == __version__
    win.close()


def test_fresh_install_records_without_dialog(qapp):
    s = AppSettings.load()
    s.existed = False
    win = MainWindow(settings=s)
    assert win.whats_new.on_startup() is False and s.last_seen_version == __version__
    assert AppSettings.load().last_seen_version == __version__
    win.close()


def test_settings_existed_flag(tmp_path):
    assert AppSettings().existed is False
    assert AppSettings.load().existed is False  # chưa có settings.json
    s = AppSettings()
    s.save()
    assert AppSettings.load().existed is True
    assert "existed" not in AppSettings.settings_file().read_text(encoding="utf-8")


def test_dialog_structure_and_github(qapp, monkeypatch):
    opened = []
    monkeypatch.setattr(wnd.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    notes = wn.load_notes()
    dlg = wnd.WhatsNewDialog(notes[:1] + [wn.VersionNotes("1.2.0", "2026-01-01", "Cũ", (wn.NoteItem("save", "A", "b"),))])
    assert dlg.btn_start.isDefault() and dlg.btn_start.objectName() == "primaryConvertBtn"
    assert dlg.btn_github.objectName() != "primaryConvertBtn"
    assert dlg.older_body.isHidden()
    dlg.older_toggle.click()
    assert not dlg.older_body.isHidden()
    dlg.btn_github.click()
    assert opened == [f"https://github.com/quangthoai1985/QTPdfPro/releases/tag/v{notes[0].version}"]
    dlg.deleteLater()


def test_show_current_prefers_current_version_else_newest(qapp):
    win = MainWindow(settings=AppSettings.load())
    shown = []
    win.whats_new.dialog_factory = lambda notes, parent: FakeDialog(shown, notes)
    win.whats_new.show_current()
    assert len(shown) == 1 and len(shown[0]) == 1
    cur = wn.notes_for(__version__, wn.load_notes())
    assert shown[0][0].version == (cur or wn.load_notes()[0]).version
    win.close()


def test_menu_and_home_chip_open_dialog(qapp):
    win = MainWindow(settings=AppSettings.load())
    shown = []
    win.whats_new.dialog_factory = lambda notes, parent: FakeDialog(shown, notes)
    win.command_actions["whats_new"].trigger()
    win.home_page.versionClicked.emit()
    assert len(shown) == 2
    win.close()


def _due_window(monkeypatch):
    s = AppSettings.load()
    s.existed = True
    s.last_seen_version = "1.0.0"
    win = MainWindow(settings=s)
    shown = []
    win.whats_new.dialog_factory = lambda notes, parent: FakeDialog(shown, notes)
    monkeypatch.setattr(wn, "load_notes", lambda path=None: [wn.VersionNotes(__version__, "", "", ())])
    monkeypatch.setattr(wnd, "STARTUP_DELAY_MS", 0)
    return win, shown


def test_startup_timer_shows_when_window_visible(qapp, monkeypatch):
    win, shown = _due_window(monkeypatch)
    win.show()
    assert win.whats_new.on_startup() is True
    QTest.qWait(50)
    assert len(shown) == 1
    win.close()


def test_startup_timer_skips_hidden_or_destroyed_window(qapp, monkeypatch):
    win, shown = _due_window(monkeypatch)  # chưa show: cửa sổ ẩn
    assert win.whats_new.on_startup() is True
    QTest.qWait(50)
    assert shown == [] and win.whats_new.settings.last_seen_version == "1.0.0"
    win2, shown2 = _due_window(monkeypatch)
    win2.show()
    win2.whats_new.on_startup()
    win2.deleteLater()  # huỷ ngay: bộ hẹn giờ là con của cửa sổ nên không còn chạy
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QTest.qWait(50)
    assert shown2 == []
