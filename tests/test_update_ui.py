"""Kiểm thử giao diện cập nhật (`ui/update_dialog.py`): tự kiểm tra 1 lần/ngày, thông báo, hộp thoại, khởi động lại.

Không gọi mạng thật (thay `update_check.check_for_update` / `download_asset` / `prepare_install`) và không mở
hộp thoại modal thật (`UpdateDialog.exec`, `QMessageBox.*` được giả lập).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from qtpdfpro import __version__
from qtpdfpro.core import update_check as uc
from qtpdfpro.core.reader import PDFDocumentReader
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import update_dialog as ud
from qtpdfpro.ui.main_window import MainWindow
from qtpdfpro.ui.update_dialog import UpdateDialog


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _release(version: str = "0.9.0", asset: bool = True) -> uc.ReleaseInfo:
    return uc.ReleaseInfo(
        tag=f"v{version}",
        version=version,
        name=f"QT PDF Pro v{version} — Tự cập nhật từ GitHub",
        notes="## Có gì mới\n- Tự phát hiện bản mới và **cập nhật** chỉ với một lần bấm.\n- Sửa lỗi hiển thị tiếng Việt.",
        html_url=f"https://github.com/quangthoai1985/QTPdfPro/releases/tag/v{version}",
        published_at="2026-10-21T03:00:00Z",
        asset=uc.ReleaseAsset(
            name=f"QTPdfPro-v{version}-win64.zip",
            url=f"https://github.com/quangthoai1985/QTPdfPro/releases/download/v{version}/QTPdfPro-v{version}-win64.zip",
            size=129587401,
            sha256="ab" * 32,
        ) if asset else None,
    )  # fmt: skip


def _fake_install(root: Path) -> Path:
    (root / "_internal").mkdir(parents=True)
    (root / "QTPdfPro.exe").write_text("ban cu")
    return root


def _wait_check(win: MainWindow) -> None:
    assert win.updater.wait_for_check(5000)
    _app().processEvents()


def test_auto_check_once_per_day_and_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app()
    calls: list = []
    rel = _release()

    def fake_check(*args, **kwargs):  # noqa: ANN002, ANN003
        calls.append(1)
        return uc.UpdateCheckResult(__version__, rel, True, "Đã có bản v0.9.0.")

    monkeypatch.setattr(uc, "check_for_update", fake_check)
    settings = AppSettings.load()
    win = MainWindow(settings=settings)
    win.show()
    app.processEvents()
    ctl = win.updater

    assert ctl.start_auto_check() is True
    _wait_check(win)
    assert ctl.notice.isVisible() and "Đã có bản v0.9.0" in ctl.notice.label.text()
    assert ctl.notice.btn_update.text() == "Cập nhật"
    assert settings.last_update_check and AppSettings.load().last_update_check == settings.last_update_check
    # Thông báo nằm gọn trong cửa sổ, phía trên thanh trạng thái
    geo = ctl.notice.geometry()
    assert win.rect().contains(geo) and geo.bottom() < win.statusBar().geometry().top()

    assert ctl.start_auto_check() is False  # cùng ngày → không hỏi lại
    assert len(calls) == 1

    ctl.notice.hide()
    settings.last_update_check = ""
    settings.skipped_update_version = "0.9.0"
    assert ctl.start_auto_check() is True
    _wait_check(win)
    assert len(calls) == 2 and not ctl.notice.isVisible()  # bản đã «Bỏ qua» không báo nữa

    settings.last_update_check = ""
    settings.auto_check_updates = False
    assert ctl.start_auto_check() is False
    assert len(calls) == 2
    win.close()


def test_menu_action_and_manual_check(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _app()
    win = MainWindow(settings=AppSettings.load())
    win.show()
    app.processEvents()
    ctl = win.updater
    assert ctl.act_check in win.actions() and ctl.act_check.text() == "Kiểm tra cập nhật..."
    assert ctl.act_auto.isCheckable() and ctl.act_auto.isChecked()
    ctl.act_auto.setChecked(False)
    assert AppSettings.load().auto_check_updates is False
    ctl.act_auto.setChecked(True)

    infos: list = []
    warnings: list = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda parent, title, text, *a: infos.append(text)))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda parent, title, text, *a: warnings.append(text)))
    monkeypatch.setattr(
        uc, "check_for_update",
        lambda *a, **k: uc.UpdateCheckResult(__version__, _release(__version__), False,
                                             f"Bạn đang dùng bản mới nhất (v{__version__})."),
    )  # fmt: skip
    ctl.act_check.trigger()
    _wait_check(win)
    assert infos == [f"Bạn đang dùng bản mới nhất (v{__version__})."]

    def boom(*a, **k):  # noqa: ANN002, ANN003
        raise uc.UpdateError("Không kết nối được tới GitHub (mất mạng).")

    monkeypatch.setattr(uc, "check_for_update", boom)
    ctl.check_now()
    _wait_check(win)
    assert warnings and "mất mạng" in warnings[0]

    # Có bản mới khi kiểm tra bằng tay → mở hộp thoại ngay, kể cả bản đã «Bỏ qua»; chọn «Bỏ qua bản này»
    win.settings.skipped_update_version = "0.9.0"
    monkeypatch.setattr(uc, "check_for_update", lambda *a, **k: uc.UpdateCheckResult(__version__, _release(), True, ""))
    opened: list = []

    def fake_exec(self: UpdateDialog) -> int:
        opened.append(self.release.version)
        self.outcome = "skip"
        return 0

    monkeypatch.setattr(UpdateDialog, "exec", fake_exec)
    win.settings.skipped_update_version = ""
    ctl.check_now()
    _wait_check(win)
    assert opened == ["0.9.0"] and AppSettings.load().skipped_update_version == "0.9.0"
    win.close()


def test_dialog_source_mode_only_links_release_page(isolated_app_data: Path) -> None:
    _app()
    dlg = UpdateDialog(_release(), AppSettings.load(), frozen=False)
    assert dlg.mode == UpdateDialog.MODE_SOURCE
    assert dlg.title_lbl.text() == "Đã có bản QT PDF Pro v0.9.0"
    assert f"Bạn đang dùng v{__version__}" in dlg.facts_lbl.text() and "123,6 MB" in dlg.facts_lbl.text()
    assert "21/10/2026" in dlg.facts_lbl.text()
    assert "Tự phát hiện bản mới" in dlg.notes_view.toPlainText()
    assert "mã nguồn" in dlg.hint_lbl.text()
    assert not dlg.btn_release.isHidden() and dlg.btn_download.isHidden()
    assert not dlg.btn_later.isHidden() and not dlg.btn_skip.isHidden()
    assert dlg.start_download() is False  # không tự thay tệp khi chạy từ mã nguồn
    dlg.btn_skip.click()
    assert dlg.outcome == "skip"


def test_dialog_install_flow_ready_to_restart(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = _app()
    install = _fake_install(tmp_path / "Apps" / "QTPdfPro")
    zip_path = tmp_path / "QTPdfPro-v0.9.0-win64.zip"
    plan = uc.InstallPlan("0.9.0", zip_path, tmp_path / "staging" / "QTPdfPro", install,
                          tmp_path / "apply_update.ps1", tmp_path / "update.log")  # fmt: skip

    def fake_download(asset, dest_dir=None, progress_cb=None, should_cancel=None, timeout=0):  # noqa: ANN001
        for done in (0, asset.size // 2, asset.size):
            progress_cb(done, asset.size)
        return zip_path

    def fake_prepare(zp, version, target_dir=None, should_cancel=None, progress_cb=None):  # noqa: ANN001
        assert (zp, version, target_dir) == (zip_path, "0.9.0", install)
        return plan

    monkeypatch.setattr(uc, "download_asset", fake_download)
    monkeypatch.setattr(uc, "prepare_install", fake_prepare)
    dlg = UpdateDialog(_release(), AppSettings.load(), install_dir=install, frozen=True)
    assert dlg.mode == UpdateDialog.MODE_INSTALL
    assert dlg.btn_download.text() == "Tải về && cập nhật" and not dlg.btn_download.isHidden()
    assert "SHA-256" in dlg.hint_lbl.text()

    assert dlg.start_download() is True
    assert not dlg.btn_cancel.isHidden() and dlg.btn_download.isHidden()
    assert dlg.wait_for_worker(5000)
    app.processEvents()
    assert dlg.plan is plan and dlg.zip_path == zip_path
    assert dlg.progress_bar.value() == 1000
    assert not dlg.btn_restart.isHidden() and dlg.btn_restart.text() == "Khởi động lại && cập nhật"
    assert not dlg.btn_on_exit.isHidden()
    assert "đã kiểm mã SHA-256" in dlg.hint_lbl.text()
    dlg.btn_restart.click()
    assert dlg.outcome == "restart" and dlg.result() == QDialog.DialogCode.Accepted


def test_dialog_manual_mode_cancel_and_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = _app()
    install = _fake_install(tmp_path / "Program Files" / "QTPdfPro")
    monkeypatch.setattr(uc, "can_write_install_dir", lambda path: False)
    zip_path = tmp_path / "QTPdfPro-v0.9.0-win64.zip"
    revealed: list = []
    monkeypatch.setattr(ud, "_reveal_in_explorer", lambda p: revealed.append(p))
    monkeypatch.setattr(uc, "download_asset", lambda asset, **kw: zip_path)
    monkeypatch.setattr(uc, "prepare_install", lambda *a, **k: pytest.fail("không được giải nén khi không ghi được"))

    dlg = UpdateDialog(_release(), AppSettings.load(), install_dir=install, frozen=True)
    assert dlg.mode == UpdateDialog.MODE_MANUAL and dlg.btn_download.text() == "Tải về"
    assert "không ghi được" in dlg.hint_lbl.text()
    dlg.start_download()
    assert dlg.wait_for_worker(5000)
    app.processEvents()
    assert revealed == [zip_path] and not dlg.btn_open_folder.isHidden()
    assert str(zip_path) in dlg.hint_lbl.text() and "Chép đè" in dlg.hint_lbl.text()

    # Huỷ giữa chừng → về trạng thái ban đầu
    def slow_download(asset, dest_dir=None, progress_cb=None, should_cancel=None, timeout=0):  # noqa: ANN001
        while not should_cancel():  # chạy trong luồng nền: chờ cờ huỷ
            time.sleep(0.005)
        raise uc.UpdateCancelled("Đã huỷ tải bản cập nhật.")

    monkeypatch.setattr(uc, "download_asset", slow_download)
    dlg2 = UpdateDialog(_release(), AppSettings.load(), install_dir=install, frozen=True)
    dlg2.start_download()
    assert dlg2.is_running()
    dlg2.btn_cancel.click()
    assert dlg2.wait_for_worker(5000)
    app.processEvents()
    assert not dlg2.is_running() and not dlg2.btn_download.isHidden()
    assert "Đã huỷ" in dlg2.status_lbl.text()

    def bad_hash(*a, **k):  # noqa: ANN002, ANN003
        raise uc.UpdateError("Mã SHA-256 của tệp tải về không khớp với GitHub — tệp hỏng hoặc bị thay đổi, đã xoá.")

    monkeypatch.setattr(uc, "download_asset", bad_hash)
    dlg3 = UpdateDialog(_release(), AppSettings.load(), install_dir=install, frozen=True)
    dlg3.start_download()
    assert dlg3.wait_for_worker(5000)
    app.processEvents()
    assert "SHA-256" in dlg3.status_lbl.text() and not dlg3.btn_retry.isHidden()

    no_asset = UpdateDialog(_release(asset=False), AppSettings.load(), install_dir=install, frozen=True)
    assert no_asset.mode == UpdateDialog.MODE_NO_ASSET and not no_asset.btn_release.isHidden()
    assert "QTPdfPro-v0.9.0-win64.zip" in no_asset.hint_lbl.text()


def test_restart_goes_through_close_event_and_save_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_vietnamese_pdf: Path
) -> None:
    app = _app()
    win = MainWindow(settings=AppSettings.load())
    win.show()
    app.processEvents()
    assert win.open_pdf_path(sample_vietnamese_pdf) is not None
    plan = uc.InstallPlan("0.9.0", tmp_path / "x.zip", tmp_path / "staging" / "QTPdfPro", tmp_path / "QTPdfPro",
                          tmp_path / "apply_update.ps1", tmp_path / "update.log")  # fmt: skip
    launched: list = []
    quits: list = []
    monkeypatch.setattr(uc, "launch_install", lambda p, pid=None, relaunch=True: launched.append((p, relaunch)))
    monkeypatch.setattr(win.updater, "_quit_app", lambda: quits.append(1))

    def fake_exec(self: UpdateDialog) -> int:
        self.outcome, self.plan = "restart", plan
        return 1

    monkeypatch.setattr(UpdateDialog, "exec", fake_exec)
    # Tab có thay đổi chưa lưu và người dùng bấm «Huỷ» ở câu hỏi lưu → không đóng, không cài ngay
    monkeypatch.setattr(PDFDocumentReader, "has_unsaved_changes", property(lambda self: True))
    asked: list = []
    monkeypatch.setattr(win, "_confirm_close_tab", lambda tab: asked.append(tab) or False)
    win.updater.open_dialog(_release())
    assert asked and launched == [] and win.isVisible()
    assert win.updater.pending_plan is plan and win.updater.relaunch_after_install is False

    # Lần thoát sau (đồng ý lưu / không lưu) → chạy trình cập nhật, không tự mở lại
    monkeypatch.setattr(win, "_confirm_close_tab", lambda tab: True)
    assert win.close() is True
    assert launched == [(plan, False)] and quits == [1] and win.updater.pending_plan is None

    # «Khởi động lại & cập nhật» khi không còn gì chưa lưu → đóng ngay và mở lại sau khi cài
    win2 = MainWindow(settings=AppSettings.load())
    win2.show()
    monkeypatch.setattr(win2.updater, "_quit_app", lambda: quits.append(2))
    win2.updater.open_dialog(_release())
    assert launched[-1] == (plan, True) and quits[-1] == 2 and not win2.isVisible()


def test_startup_reports_previous_update_and_cleans(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app = _app()
    settings = AppSettings.load()
    settings.auto_check_updates = False  # không hỏi mạng trong bài này
    win = MainWindow(settings=settings)
    win.show()
    app.processEvents()
    plan = uc.InstallPlan(__version__, tmp_path / "x.zip", tmp_path / "s", tmp_path / "QTPdfPro",
                          tmp_path / "a.ps1", tmp_path / "update.log")  # fmt: skip
    uc.write_pending_marker(plan)
    stale = uc.updates_dir() / "QTPdfPro-v0.1.0-win64.zip"
    stale.write_bytes(b"x")
    toasts: list = []
    monkeypatch.setattr(win, "_show_toast", lambda text, msec=3200: toasts.append(text))
    win.updater.on_startup(delay_ms=0)
    QTest.qWait(800)
    win.updater._cleanup_thread.join(10)
    assert toasts == [f"Đã cập nhật lên QT PDF Pro v{__version__}."]
    assert not stale.exists() and uc.consume_pending_marker() is None
    win.close()
