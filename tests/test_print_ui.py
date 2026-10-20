"""Kiểm thử in bằng `QPrinter` (ra tệp PDF — không bao giờ gửi tới máy in giấy), hộp thoại «In tài liệu» và Ctrl+P."""

from __future__ import annotations

import os
import time
from pathlib import Path

import fitz  # PyMuPDF
import pytest
from PySide6.QtWidgets import QApplication

from qtpdfpro.core.printing import PrintOptions
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import print_job
from qtpdfpro.ui.main_window import MainWindow
from qtpdfpro.ui.print_dialog import PDF_TARGET, PrintDialog
from qtpdfpro.ui.tool_catalog import get_tool


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _mixed_pdf(path: Path) -> Path:
    """3 trang: A4 dọc, A4 ngang (có chú thích tô sáng), A5 dọc."""
    doc = fitz.open()
    for w, h in [(595, 842), (842, 595), (420, 595)]:
        page = doc.new_page(width=w, height=h)
        page.insert_text((60, 80), f"Trang {doc.page_count}", fontsize=16)
        if w > h:
            page.add_highlight_annot(fitz.Rect(60, 64, 200, 86))
    doc.save(str(path))
    doc.close()
    return path


def _image_colorspaces(path: Path) -> set[str]:
    with fitz.open(str(path)) as doc:
        return {img[5] for page in doc for img in page.get_images()}


@pytest.fixture()
def no_real_printers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hộp thoại chỉ thấy mục «Lưu bản in thành tệp PDF» — kiểm thử không phụ thuộc máy in của máy chạy test."""
    monkeypatch.setattr(print_job, "available_printers", lambda: [])
    monkeypatch.setattr(print_job, "default_printer_name", lambda: "")


def test_qprinter_pdf_output_pages_orientation_grayscale(tmp_path: Path) -> None:
    _app()
    pdf = _mixed_pdf(tmp_path / "tron.pdf")
    with fitz.open(str(pdf)) as doc:
        out = tmp_path / "qt_ban_in.pdf"
        steps = []
        res = print_job.print_document(
            print_job.create_printer(output_file=out), doc, [0, 1, 2],
            PrintOptions(grayscale=True, copies=2, max_dpi=300), doc_name="tron",
            progress=lambda d, t: steps.append(d),
        )
        assert res.sheets_printed == 6 and steps == [1, 2, 3, 4, 5, 6] and res.dpi == 300
        with fitz.open(str(out)) as printed:
            assert printed.page_count == 6  # PDF không tự nhân bản → nhân trong lệnh in
            assert all(p.rect.width < p.rect.height for p in printed)  # đa số trang dọc → A4 dọc
            assert printed[0].rect.width == pytest.approx(595, abs=1)
        assert _image_colorspaces(out) == {"DeviceGray"}

        # Ép giấy ngang, chỉ trang 2 (trang ngang) — in màu
        out2 = tmp_path / "ngang.pdf"
        print_job.print_document(print_job.create_printer(output_file=out2), doc, [1],
                                 PrintOptions(orientation="landscape", paper="A5", max_dpi=300))
        with fitz.open(str(out2)) as printed:
            assert printed.page_count == 1
            assert (printed[0].rect.width, printed[0].rect.height) == pytest.approx((595, 420), abs=1)
        assert _image_colorspaces(out2) == {"DeviceRGB"}

        # Dừng giữa chừng → không để lại tệp dở
        out3 = tmp_path / "huy.pdf"
        res = print_job.print_document(print_job.create_printer(output_file=out3), doc, [0, 1, 2],
                                       PrintOptions(max_dpi=300), should_cancel=lambda: len(steps) >= 7,
                                       progress=lambda d, t: steps.append(d))
        assert res.cancelled and res.sheets_printed == 1 and not out3.exists()


@pytest.mark.skipif(
    os.environ.get("QTPDFPRO_NATIVE_PRINT_TEST") != "1",
    reason="Chỉ chạy khi đặt QTPDFPRO_NATIVE_PRINT_TEST=1: in qua hàng đợi in của Windows có thể làm Windows "
           "đổi máy in mặc định (chế độ «Để Windows quản lý máy in mặc định»)",
)
def test_native_windows_driver_print_to_file(tmp_path: Path) -> None:
    """Đường in qua trình điều khiển Windows (QWin32PrintEngine) bằng máy in ảo «Microsoft Print to PDF» ghi ra tệp."""
    _app()
    name = "Microsoft Print to PDF"
    if name not in print_job.available_printers():
        pytest.skip("Máy không có máy in ảo Microsoft Print to PDF")
    pdf = _mixed_pdf(tmp_path / "tron.pdf")
    out = tmp_path / "trinh_dieu_khien.prn"  # đuôi khác .pdf → giữ NativeFormat, trình điều khiển ghi PDF vào tệp
    with fitz.open(str(pdf)) as doc:
        printer = print_job.create_printer(name, out)
        assert printer.outputFormat() == printer.OutputFormat.NativeFormat
        res = print_job.print_document(printer, doc, [0, 1], PrintOptions(max_dpi=300))
    assert res.sheets_printed == 2
    deadline = time.time() + 20
    while time.time() < deadline and not (out.exists() and out.stat().st_size > 0):
        time.sleep(0.2)
    with fitz.open(str(out), filetype="pdf") as printed:
        assert printed.page_count == 2


def test_print_dialog_prints_custom_range_and_remembers_settings(
    tmp_path: Path, sample_vietnamese_pdf: Path, no_real_printers: None
) -> None:
    app = _app()
    settings = AppSettings.load()
    with fitz.open(str(sample_vietnamese_pdf)) as doc:
        dlg = PrintDialog(doc, settings, doc_name=sample_vietnamese_pdf.name, doc_path=str(sample_vietnamese_pdf),
                          current_page=1)
        assert dlg.printer_target == PDF_TARGET
        assert dlg.rb_all.text() == "Tất cả (2 trang)" and dlg.rb_current.text() == "Trang hiện tại (trang 2)"
        assert dlg.plan is not None and dlg.plan.sheet_count == 2

        # Khoảng trang sai → báo lỗi, không cho in
        dlg.set_page_range("1, 7")
        assert dlg.plan is None and not dlg.print_btn.isEnabled()
        assert "ngoài tài liệu" in dlg.range_error.text()
        assert dlg.start_print() is False

        dlg.set_page_range("2-")
        dlg.paper_combo.setCurrentIndex(dlg.paper_combo.findData("A5"))
        dlg.color_combo.setCurrentIndex(dlg.color_combo.findData(True))
        dlg.quality_combo.setCurrentIndex(dlg.quality_combo.findData(300))
        dlg.copies_spin.setValue(2)
        plan = dlg.refresh_plan()
        assert plan is not None and plan.page_indices == [1] and "× 2 bản" in dlg.summary_label.text()
        assert dlg.preview.sheet is plan.sheets[0] and dlg.preview.image is not None
        assert dlg.duplex_combo.isEnabled() is False  # in ra tệp PDF không có 2 mặt

        out = tmp_path / "ban_in_hop_thoai.pdf"
        dlg.output_path = str(out)
        assert dlg.start_print() is True
        assert dlg.is_running() and not dlg.print_btn.isEnabled() and dlg.cancel_btn.text() == "Dừng in"
        assert dlg.wait_for_worker(30000)
        deadline = time.time() + 10
        while dlg.result is None and time.time() < deadline:
            app.processEvents()
        assert dlg.result is not None and not dlg.result.cancelled
        assert dlg.result.sheets_printed == 2 and "Đã lưu bản in" in dlg.result_message

    with fitz.open(str(out)) as printed:
        assert printed.page_count == 2
        assert printed[0].rect.width == pytest.approx(420, abs=1)
    assert _image_colorspaces(out) == {"DeviceGray"}
    saved = AppSettings.load().print_settings
    assert saved["paper"] == "A5" and saved["grayscale"] is True and saved["max_dpi"] == 300
    assert saved["printer"] == PDF_TARGET and "copies" not in saved

    # Mở lại: nhớ thiết lập lần trước, số bản về 1, phạm vi về «Tất cả»
    with fitz.open(str(sample_vietnamese_pdf)) as doc:
        again = PrintDialog(doc, AppSettings.load())
        assert again.paper_combo.currentData() == "A5" and again.color_combo.currentData() is True
        assert again.copies_spin.value() == 1 and again.page_scope() == "all"
        again.reject()


def test_print_dialog_preview_navigation(tmp_path: Path, no_real_printers: None) -> None:
    _app()
    pdf = _mixed_pdf(tmp_path / "tron.pdf")
    with fitz.open(str(pdf)) as doc:
        dlg = PrintDialog(doc, AppSettings.load(), current_page=1)
        dlg.rb_current.setChecked(True)
        plan = dlg.refresh_plan()
        assert plan is not None and plan.page_indices == [1]
        dlg.rb_all.setChecked(True)
        plan = dlg.refresh_plan()
        assert plan.sheet_count == 3 and not dlg.btn_prev.isEnabled()
        dlg.go_preview(1)
        assert dlg.preview.sheet.rotate == 270 and "xoay 90°" in dlg.nav_label.text()
        dlg.go_preview(99)
        assert dlg.preview_index == 2 and not dlg.btn_next.isEnabled()
        dlg.subset_combo.setCurrentIndex(dlg.subset_combo.findData("even"))
        assert dlg.refresh_plan().page_indices == [1]
        dlg.reject()


def test_main_window_ctrl_p_opens_print_dialog(sample_vietnamese_pdf: Path, monkeypatch: pytest.MonkeyPatch,
                                               no_real_printers: None) -> None:
    app = _app()
    tool = get_tool("print")
    assert tool is not None and tool.ready and tool.needs_document

    win = MainWindow(settings=AppSettings.load())
    assert win.act_print in win.actions() and win.act_print.shortcut().toString() == "Ctrl+P"
    tab = win.open_pdf_path(sample_vietnamese_pdf)
    app.processEvents()
    tab.viewer.go_to_page(1)
    app.processEvents()

    opened = []

    def fake_exec(self) -> int:  # không mở hộp thoại modal thật trong pytest
        opened.append(self)
        self.result_message = "🖨 Đã gửi 2 tờ tới «Máy in thử»"
        return 1

    monkeypatch.setattr(PrintDialog, "exec", fake_exec)
    win.act_print.trigger()
    assert len(opened) == 1
    dlg = opened[0]
    assert dlg.doc is tab.reader.doc and dlg.current_page == 1 and dlg.page_count == 2
    assert win._toast is not None and "Máy in thử" in win._toast.text()

    tab.tool_btn_print.click()
    win.run_tool("print")
    assert len(opened) == 3
    win.close()
