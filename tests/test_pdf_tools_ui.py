"""Kiểm thử giao diện công cụ văn phòng (`ui/pdf_tools_dialog.py`) và tích hợp với `MainWindow`.

Hộp thoại modal (`exec`, `QMessageBox`, `QInputDialog`) luôn được giả lập bằng `monkeypatch` để `pytest` không treo.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from qtpdfpro.core import pdf_security as sec
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import pdf_tools_dialog as ptd
from qtpdfpro.ui.main_window import MainWindow
from qtpdfpro.ui.tool_catalog import get_tool
from test_pdf_tools import _make_image_pdf, _make_pdf  # cùng thư mục tests/ (pytest thêm vào sys.path)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _run(dlg: ptd.PdfToolDialog):
    dlg.start()
    dlg.wait_finished()
    return dlg.tool_result


@pytest.fixture()
def answers(monkeypatch):
    """Ghi lại & trả lời sẵn các hộp thoại QMessageBox."""
    log: dict[str, list] = {"question": [], "warning": [], "information": []}
    state = {"question": QMessageBox.StandardButton.Yes}

    def question(*args, **_k):
        log["question"].append(args[2] if len(args) > 2 else "")
        return state["question"]

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: log["warning"].append(a[2])))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: log["information"].append(a[2])))
    log["state"] = state  # type: ignore[assignment]
    return log


def test_catalog_marks_office_tools_ready() -> None:
    for key in ("compress", "watermark", "page_numbers", "protect", "unlock"):
        tool = get_tool(key)
        assert tool is not None and tool.ready and key in ptd.PDF_TOOL_DIALOGS


def test_compress_dialog_and_open_result_tab(tmp_path: Path, answers, monkeypatch) -> None:
    app = _app()
    src = _make_image_pdf(tmp_path / "anh.pdf")
    win = MainWindow(settings=AppSettings.load())
    win.show()
    win.open_pdf_path(src)
    app.processEvents()

    def fake_exec(self):  # chạy như người dùng bấm «Nén» rồi hộp thoại tự đóng
        self.level_buttons["strong"].setChecked(True)
        res = _run(self)
        return bool(res and res.written)

    monkeypatch.setattr(ptd.CompressDialog, "exec", fake_exec)
    win.run_tool("compress")
    app.processEvents()
    out = tmp_path / "anh_nen.pdf"
    assert out.exists() and out.stat().st_size < src.stat().st_size / 2
    assert answers["question"] and "Mở tệp kết quả" in answers["question"][-1]
    assert win.doc_tabs.count() == 2 and win.active_tab().reader.path == out.resolve()
    for i in reversed(range(win.doc_tabs.count())):
        win.close_tab_at(i, force=True)
    win.close()


def test_compress_dialog_not_smaller_stays_open(tmp_path: Path, answers, monkeypatch) -> None:
    _app()
    src = _make_pdf(tmp_path / "nho.pdf", 1)
    from qtpdfpro.core import compress

    monkeypatch.setattr(compress, "compress_document", lambda doc, level="medium": b"0" * 10**6)
    dlg = ptd.CompressDialog(source=src)
    res = _run(dlg)
    assert res is not None and not res.written
    assert answers["information"] and "không ghi tệp" in answers["information"][-1]
    assert dlg.result() == 0 and not (tmp_path / "nho_nen.pdf").exists()


def test_watermark_dialog_preview_and_run(tmp_path: Path, answers) -> None:
    _app()
    src = _make_pdf(tmp_path / "goc.pdf", 3, rotations=[0, 90, 0])
    dlg = ptd.WatermarkDialog(source=src)
    assert dlg.out_edit.text().endswith("goc_dau_nuoc.pdf")
    dlg.preset_combo.setCurrentIndex(dlg.preset_combo.findData("BẢN SAO\nKHÔNG CÓ GIÁ TRỊ PHÁP LÝ"))
    assert dlg.text_edit.toPlainText() == "BẢN SAO\nKHÔNG CÓ GIÁ TRỊ PHÁP LÝ"
    dlg.size_spin.setValue(30)
    dlg.layout_combo.setCurrentIndex(dlg.layout_combo.findData("tile"))
    dlg.pages_edit.setText("2-3")
    dlg.render_preview()
    assert not dlg.preview_label.pixmap().isNull()
    assert dlg.preview_caption.text() == "Trang 2/3"
    res = _run(dlg)
    assert res.written and res.pages_changed == 2 and dlg.result() == 1
    with fitz.open(res.output_path) as doc:
        assert "KHÔNG CÓ GIÁ TRỊ PHÁP LÝ" in doc[1].get_text() and "BẢN SAO" not in doc[0].get_text()

    dlg2 = ptd.WatermarkDialog(source=src)
    dlg2.text_edit.setPlainText("   ")
    dlg2.start()
    assert answers["warning"] and "nội dung dấu nước" in answers["warning"][-1]


def test_page_number_dialog_nd30_preset(tmp_path: Path, answers) -> None:
    _app()
    src = _make_pdf(tmp_path / "goc.pdf", 3)
    dlg = ptd.PageNumberDialog(source=src)
    dlg.apply_nd30_preset()
    opts = dlg.options()
    assert (opts.position, opts.skip_first, opts.font_family, opts.font_size) == ("top-center", True, "serif", 13)
    assert not dlg.side_spin.isEnabled()
    dlg.render_preview()
    assert dlg.preview_caption.text() == "Trang 2/3" and not dlg.preview_label.pixmap().isNull()
    dlg.format_combo.setCurrentIndex(dlg.format_combo.findData("Trang {n} / {total}"))
    assert dlg.template_edit.text() == "Trang {n} / {total}"
    res = _run(dlg)
    assert res.written and res.pages_changed == 2
    with fitz.open(res.output_path) as doc:
        assert "Trang 3 / 3" in doc[2].get_text() and "Trang" not in doc[0].get_text()
    dlg.template_edit.setText("Trang")
    dlg.start()
    assert "{n}" in answers["warning"][-1]


def test_signed_source_asks_before_running(tmp_path: Path, answers) -> None:
    _app()
    src = _make_pdf(tmp_path / "ky.pdf", 1, signed=True)
    dlg = ptd.PageNumberDialog(source=src)
    assert dlg.source_signed and "chữ ký số" in dlg.source_label.text()
    answers["state"]["question"] = QMessageBox.StandardButton.No
    dlg.start()
    dlg.wait_finished()
    assert dlg.tool_result is None and "chữ ký số" in answers["question"][-1]
    answers["state"]["question"] = QMessageBox.StandardButton.Yes
    assert _run(dlg).written


def test_protect_and_unlock_dialogs(tmp_path: Path, answers, monkeypatch) -> None:
    _app()
    src = _make_pdf(tmp_path / "goc.pdf", 2)
    dlg = ptd.ProtectDialog(source=src)
    dlg.user_edit.setText("mo1")
    dlg.user_confirm.setText("mo2")
    dlg.start()
    assert "không khớp" in answers["warning"][-1]
    dlg.user_confirm.setText("mo1")
    dlg.perm_checks["copy"].setChecked(False)
    dlg.start()
    assert "mật khẩu chủ" in answers["warning"][-1]
    dlg.owner_edit.setText("chu1")
    dlg.owner_confirm.setText("chu1")
    res = _run(dlg)
    assert res.written and res.encrypted and dlg.result_password == "mo1"
    prot = Path(res.output_path)
    with fitz.open(str(prot)) as doc:
        assert doc.needs_pass and doc.authenticate("mo1") == 2

    # Gỡ: mở tệp hỏi mật khẩu (giả lập nhập mật khẩu mở), mật khẩu mở không đủ → báo lỗi, mật khẩu chủ → được
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("mo1", True)))
    un = ptd.UnlockDialog(source=prot)
    assert un.source_password == "mo1" and un.password_edit.text() == "mo1"
    assert "Cần mật khẩu để mở" in un.info_label.text()
    assert _run(un) is None and "mật khẩu chủ" in answers["warning"][-1]
    un.password_edit.setText("chu1")
    res2 = _run(un)
    assert res2.written and not res2.encrypted
    with fitz.open(res2.output_path) as doc:
        assert not doc.needs_pass and "Noi dung trang 2" in doc[1].get_text()


def test_tool_on_restricted_tab_asks_owner_password(tmp_path: Path, answers, monkeypatch) -> None:
    """Tab mở bằng mật khẩu mở của tệp cấm sửa → công cụ hỏi mật khẩu chủ rồi chạy lại."""
    app = _app()
    src = _make_pdf(tmp_path / "goc.pdf", 2)
    prot = Path(sec.protect_pdf(src, tmp_path / "bv.pdf",
                                sec.ProtectOptions("mo", "chu", allow_modify=False)).output_path)
    win = MainWindow(settings=AppSettings.load())
    tab = win.open_pdf_path(prot, password="mo")
    app.processEvents()
    assert tab is not None and tab.reader.password == "mo"
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("chu", True)))
    seen = {}

    def fake_exec(self):
        self.start()
        self.wait_finished()  # lỗi quyền → hỏi mật khẩu chủ → chạy lại
        self.wait_finished()
        seen["dlg"] = self
        return bool(self.tool_result and self.tool_result.written)

    monkeypatch.setattr(ptd.WatermarkDialog, "exec", fake_exec)
    answers["state"]["question"] = QMessageBox.StandardButton.No  # không mở tab kết quả
    win.run_tool("watermark")
    res = seen["dlg"].tool_result
    assert res is not None and res.written and res.encrypted
    with fitz.open(res.output_path) as doc:
        assert doc.authenticate("mo") == 2 and "BẢN SAO" in doc[0].get_text()
    assert win.doc_tabs.count() == 1
    win.close_tab_at(0, force=True)
    win.close()
