"""Kiểm thử giao diện OCR (`ui/ocr_dialog.py`): tải mô hình ngầm lần đầu, hộp thoại nhận dạng, nối vào cửa sổ chính.

Không gọi mạng thật (thay `ocr_models.install_models`), không cần mô hình thật (bộ máy OCR giả) và không mở hộp
thoại modal thật (`QMessageBox.*`, `OcrDialog.exec` được giả lập).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from qtpdfpro.core import ocr, ocr_models
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import ocr_dialog as od
from qtpdfpro.ui.main_window import STRIP_TOOLS, MainWindow
from qtpdfpro.ui.tool_catalog import get_tool
from tests.test_ocr import _scanned_pdf, fake_engine, needs_font


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write_fake_bundle() -> None:
    root = ocr_models.bundle_dir()
    root.mkdir(parents=True, exist_ok=True)
    files = {"det.onnx": b"d" * 10, "vocab.txt": b"abc"}
    for name, body in files.items():
        (root / name).write_bytes(body)
    manifest = {"id": "ocr-vi", "version": ocr_models.BUNDLE_VERSION,
                "files": {n: {"sha256": hashlib.sha256(b).hexdigest(), "size": len(b)} for n, b in files.items()}}
    (root / ocr_models.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture()
def fake_install(monkeypatch: pytest.MonkeyPatch):
    """`install_models` giả: báo tiến trình rồi ghi bộ mô hình giả; đếm số lần gọi."""
    monkeypatch.delenv(ocr_models.MODELS_ENV, raising=False)
    calls = []

    def _install(progress_cb=None, should_cancel=None, **_kw):
        calls.append(1)
        for done in (0, 50, 100):
            if should_cancel and should_cancel():
                raise ocr_models.OcrModelCancelled("huỷ")
            if progress_cb:
                progress_cb(done, 100)
            time.sleep(0.02)
        _write_fake_bundle()
        return ocr_models.find_bundle()

    monkeypatch.setattr(ocr_models, "install_models", _install)
    return calls


def test_tool_is_ready_and_on_convert_strip():
    tool = get_tool("ocr")
    assert tool is not None and tool.ready and tool.category == "convert"
    assert ("🔤 OCR tiếng Việt", "ocr") in STRIP_TOOLS["convert"]


def test_controller_installs_models_in_background_once(fake_install):
    _app()
    notes = []
    ctl = od.OcrModelController(notify=notes.append)
    results = []
    ctl.finished.connect(lambda ok, msg: results.append((ok, msg)))
    assert ctl.ensure_started() is False and ctl.installing
    assert ctl.ensure_started() is False  # đang tải: không tải lần hai
    ctl.wait()
    assert results == [(True, "")] and ctl.is_installed() and not ctl.installing
    assert fake_install == [1] and notes and notes[0].startswith("✅")
    assert ctl.ensure_started() is True


def test_controller_reports_failure(monkeypatch: pytest.MonkeyPatch):
    _app()
    monkeypatch.delenv(ocr_models.MODELS_ENV, raising=False)

    def _fail(**_kw):
        raise ocr_models.OcrModelError("Không kết nối được tới GitHub.")

    monkeypatch.setattr(ocr_models, "install_models", _fail)
    notes = []
    ctl = od.OcrModelController(notify=notes.append)
    ctl.ensure_started()
    ctl.wait()
    assert not ctl.is_installed() and "GitHub" in ctl.last_error and notes[0].startswith("⚠️")


@needs_font
def test_dialog_runs_ocr_with_fake_engine(tmp_path: Path, fake_install):
    _app()
    _write_fake_bundle()
    pdf = _scanned_pdf(tmp_path / "scan.pdf", [(70, 120, "Bộ trưởng Bộ Giáo dục", 14)])
    dlg = od.OcrDialog(source=pdf, engine_factory=lambda: fake_engine(["Bộ trưởng Bộ Giáo dục"]))
    assert "1 trang ảnh quét" in dlg.source_label.text()
    assert dlg.out_edit.text().endswith("scan_ocr.pdf")
    dlg.kind_buttons["txt"].setChecked(True)
    assert dlg.out_edit.text().endswith("scan_ocr.txt") and not dlg.skip_text_check.isEnabled()
    dlg.kind_buttons["pdf"].setChecked(True)
    dlg.start()
    dlg.wait_finished()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.ocr_result is not None and dlg.ocr_result.pages_ocr == 1
    assert Path(dlg.ocr_result.output_path).exists() and "1/1 trang" in dlg.result_summary()


@needs_font
def test_dialog_starts_after_background_download(tmp_path: Path, fake_install, monkeypatch: pytest.MonkeyPatch):
    _app()
    monkeypatch.setattr(ocr.OcrEngine, "load", classmethod(lambda cls, threads=0: fake_engine(["Văn bản"])))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(f"không chờ cảnh báo: {a[2:]}"))
    pdf = _scanned_pdf(tmp_path / "scan.pdf", [(70, 120, "Văn bản", 14)])
    ctl = od.OcrModelController()
    dlg = od.OcrDialog(source=pdf, models=ctl)
    assert ctl.installing and "Đang tải bộ mô hình" in dlg.model_label.text()
    dlg.start()  # mô hình chưa xong → chờ, tải xong tự chạy
    assert not dlg.run_btn.isEnabled() and "ngay khi tải xong" in dlg.status_label.text()
    ctl.wait()
    deadline = time.time() + 10
    while dlg.ocr_result is None and time.time() < deadline:
        dlg.wait_finished()
    assert dlg.ocr_result is not None and dlg.ocr_result.pages_ocr == 1
    assert "sẵn sàng" in dlg.model_label.text()


def test_main_window_starts_model_download_on_first_click(fake_install, monkeypatch: pytest.MonkeyPatch):
    _app()
    opened = []
    monkeypatch.setattr(od.OcrDialog, "exec", lambda self: opened.append(self) or 0)
    win = MainWindow(AppSettings())
    try:
        win.run_tool("ocr")
        assert opened and opened[0].models is win.ocr_models
        win.ocr_models.wait()
        assert fake_install == [1] and win.ocr_models.is_installed()
        assert win.act_ocr.shortcut().toString() == "Ctrl+Shift+R"
    finally:
        win.ocr_models.cancel_and_wait()
        win.close()
