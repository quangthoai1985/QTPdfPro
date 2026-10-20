"""Kiểm thử «Chuyển đổi hàng loạt»: engine `core/batch.py`, lệnh CLI `batch` và hộp thoại GUI.

Dữ liệu: `samples/nd30/*.pdf` (văn bản hành chính mẫu) và fixture `sample_vietnamese_pdf`.
Mọi tệp DOCX / báo cáo đều ghi vào `tmp_path`, không ghi vào `samples/`.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from qtpdfpro.cli import main as cli_main
from qtpdfpro.core.batch import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_RUNNING,
    BatchProgress,
    collect_pdf_paths,
    convert_batch,
    default_batch_options,
    plan_output_paths,
    write_batch_report,
)

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "nd30"
SAMPLE_PDFS = sorted(SAMPLES.glob("*.pdf"))


def test_samples_present() -> None:
    assert {p.name for p in SAMPLE_PDFS} >= {"quyet_dinh_mau.pdf", "ke_hoach_mau.pdf", "cong_van_mau.pdf"}


def test_collect_pdf_paths_folders_recursive_and_dedupe(tmp_path: Path) -> None:
    src = tmp_path / "vao"
    (src / "con").mkdir(parents=True)
    for name in ("b.pdf", "A.PDF"):
        shutil.copy(SAMPLE_PDFS[0], src / name)
    shutil.copy(SAMPLE_PDFS[0], src / "con" / "c.pdf")
    (src / "ghi_chu.txt").write_text("không phải PDF", encoding="utf-8")

    flat = collect_pdf_paths([src])
    assert [p.name for p in flat] == ["A.PDF", "b.pdf"]
    deep = collect_pdf_paths([src], recursive=True)
    assert [p.name for p in deep] == ["A.PDF", "b.pdf", "c.pdf"]
    # Tệp chỉ định trực tiếp trùng với tệp trong thư mục → chỉ giữ một lần
    mixed = collect_pdf_paths([src / "b.pdf", src, str(src / "B.pdf")])
    assert [p.name for p in mixed] == ["b.pdf", "A.PDF"]


def test_plan_output_paths_unique_names(tmp_path: Path) -> None:
    a = tmp_path / "x" / "van_ban.pdf"
    b = tmp_path / "y" / "van_ban.pdf"
    c = tmp_path / "y" / "khac.pdf"
    out = tmp_path / "ra"
    assert [p.name for p in plan_output_paths([a, b, c], out)] == ["van_ban.docx", "van_ban_2.docx", "khac.docx"]
    assert all(p.parent == out.resolve() for p in plan_output_paths([a, b], out))
    # Không có thư mục ra → lưu cạnh tệp PDF gốc
    assert plan_output_paths([a, b], None) == [a.with_suffix(".docx"), b.with_suffix(".docx")]


def test_convert_batch_samples_scores_and_errors(tmp_path: Path, sample_vietnamese_pdf: Path) -> None:
    broken = tmp_path / "hong.pdf"
    broken.write_bytes(b"day khong phai tep PDF")
    inputs = [*SAMPLE_PDFS, sample_vietnamese_pdf, broken]
    out_dir = tmp_path / "docx_ra"
    samples_before = sorted(SAMPLES.iterdir())

    events: list[BatchProgress] = []
    report = convert_batch(inputs, out_dir, progress_cb=events.append)

    assert report.total == len(inputs)
    assert report.ok_count == len(inputs) - 1
    assert report.failed_count == 1 and not report.cancelled
    for item in report.items[: len(SAMPLE_PDFS)]:
        assert item.status == STATUS_OK, item.error
        assert item.mode_used == "nd30"
        assert item.nd30_score is not None and item.nd30_score >= 90
        assert item.fidelity_score is not None and item.fidelity_score >= 95
        assert item.layout_verdict is None and item.layout_verdict_text == ""  # mặc định không kiểm chứng Word
        docx = Path(item.docx_path)
        assert docx.exists() and docx.parent == out_dir.resolve()
        assert docx.stem == Path(item.pdf_path).stem
    viet = report.items[len(SAMPLE_PDFS)]
    assert viet.status == STATUS_OK and Path(viet.docx_path).exists()
    assert viet.fidelity_score is not None and viet.fidelity_score > 50
    bad = report.items[-1]
    assert bad.status == STATUS_FAILED and bad.fidelity_score is None
    assert "Không mở được tệp PDF" in bad.error  # lỗi báo bằng tiếng Việt
    assert not Path(bad.docx_path).exists() or Path(bad.docx_path).stat().st_size == 0
    assert report.average_fidelity is not None and report.average_nd30 is not None
    # Không ghi gì vào thư mục mẫu
    assert sorted(SAMPLES.iterdir()) == samples_before

    # Tiến trình: mỗi tệp có sự kiện «đang chuyển» và «kết thúc», tỷ lệ không giảm, kết thúc ở 100%
    fractions = [ev.fraction for ev in events]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0
    started = [ev.item.index for ev in events if ev.item is not None and ev.item.status == STATUS_RUNNING]
    assert started == list(range(len(inputs)))

    payload = report.to_dict()
    assert payload["ok"] == report.ok_count and len(payload["items"]) == len(inputs)
    json.dumps(payload, ensure_ascii=False)  # báo cáo phải tuần tự hoá được


def test_convert_batch_cancel_and_report_files(tmp_path: Path) -> None:
    calls = {"n": 0}

    def _cancel_after_first() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    report = convert_batch(SAMPLE_PDFS, tmp_path / "ra", should_cancel=_cancel_after_first)
    assert report.cancelled is True
    assert [it.status for it in report.items] == [STATUS_OK] + [STATUS_CANCELLED] * (len(SAMPLE_PDFS) - 1)

    csv_path = write_batch_report(report, tmp_path / "bao_cao.csv")
    raw = csv_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM để Excel đọc đúng tiếng Việt
    rows = list(csv.reader(raw.decode("utf-8-sig").splitlines()))
    assert rows[0][:4] == ["STT", "Tệp PDF", "Tệp Word", "Trạng thái"]
    assert len(rows) == 1 + len(SAMPLE_PDFS)
    assert rows[1][3] == "Hoàn tất" and rows[2][3] == "Đã huỷ"

    json_path = write_batch_report(report, tmp_path / "bao_cao.json")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["cancelled"] == len(SAMPLE_PDFS) - 1


def test_default_batch_options() -> None:
    opts = default_batch_options()
    assert (opts.mode, opts.nd30_policy, opts.verify_layout) == ("auto", "faithful", False)


def test_cli_batch_folder_json(tmp_path: Path, sample_vietnamese_pdf: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "vao"
    src.mkdir()
    shutil.copy(SAMPLES / "quyet_dinh_mau.pdf", src / "quyet_dinh_mau.pdf")
    shutil.copy(sample_vietnamese_pdf, src / sample_vietnamese_pdf.name)
    out_dir = tmp_path / "ra"
    report_csv = tmp_path / "bc.csv"

    code = cli_main(["batch", str(src), "-o", str(out_dir), "--json", "--report", str(report_csv)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 2 and payload["ok"] == 2 and payload["failed"] == 0
    by_name = {Path(it["pdf_path"]).name: it for it in payload["items"]}
    assert by_name["quyet_dinh_mau.pdf"]["mode_used"] == "nd30"
    assert by_name["quyet_dinh_mau.pdf"]["nd30_score"] >= 90
    assert all(Path(it["docx_path"]).exists() for it in payload["items"])
    assert payload["report_path"] == str(report_csv.resolve()) and report_csv.exists()


def test_cli_batch_text_output_and_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "khong_co.pdf"
    code = cli_main(["batch", str(SAMPLES / "cong_van_mau.pdf"), str(missing), "-o", str(tmp_path / "ra")])
    out = capsys.readouterr().out
    assert code == 1  # có tệp thất bại
    assert "cong_van_mau.docx" in out and "Thất bại" in out and "1/2 tệp thành công" in out

    empty = tmp_path / "rong"
    empty.mkdir()
    assert cli_main(["batch", str(empty)]) == 1
    assert "không tìm thấy tệp PDF" in capsys.readouterr().err


def test_batch_dialog_drop_convert_and_report(tmp_path: Path, sample_vietnamese_pdf: Path) -> None:
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDropEvent
    from PySide6.QtWidgets import QApplication

    from qtpdfpro.core.settings import AppSettings
    from qtpdfpro.ui.batch_dialog import BatchConvertDialog

    app = QApplication.instance() or QApplication([])
    settings = AppSettings.load()
    dlg = BatchConvertDialog(settings, pdf_paths=[SAMPLES / "cong_van_mau.pdf"])
    dlg.show()
    app.processEvents()
    assert dlg.table.rowCount() == 1
    assert dlg.mode_combo.currentData() == "auto"
    assert dlg.chk_verify.isChecked() is False
    assert dlg.dest_combo.currentData() == "beside"  # chưa từng chọn thư mục lưu
    assert dlg.selected_out_dir() is None and dlg.out_dir_edit.isEnabled() is False

    # Kéo thả: một tệp PDF mới, một tệp trùng và một tệp không phải PDF
    note = tmp_path / "ghi_chu.txt"
    note.write_text("x", encoding="utf-8")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in (sample_vietnamese_pdf, SAMPLES / "cong_van_mau.pdf", note)])
    drop = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    dlg.dropEvent(drop)
    assert [p.name for p in dlg.pdf_paths] == ["cong_van_mau.pdf", sample_vietnamese_pdf.name]
    assert dlg.add_paths([SAMPLES]) == 2  # thêm cả thư mục, bỏ tệp đã có
    assert dlg.table.rowCount() == len(SAMPLE_PDFS) + 1

    # Bỏ tệp đã chọn
    dlg.table.selectRow(dlg.table.rowCount() - 1)
    dlg.remove_selected()
    assert dlg.table.rowCount() == len(SAMPLE_PDFS)

    out_dir = tmp_path / "ket_qua"
    dlg.set_out_dir(out_dir)
    assert dlg.out_dir_edit.isEnabled() is True and dlg.selected_out_dir() == str(out_dir)
    assert dlg.start_batch(confirm_overwrite=False) is True
    assert dlg.is_running() is True and dlg.start_btn.isEnabled() is False
    assert dlg.stop_btn.isEnabled() is True and dlg.out_dir_edit.isEnabled() is False
    assert dlg.add_paths([SAMPLES / "ke_hoach_mau.pdf"]) == 0  # không sửa danh sách khi đang chạy
    assert dlg.wait_for_worker(120_000)
    for _ in range(3):
        app.processEvents()

    assert dlg.is_running() is False and dlg.report is not None
    assert dlg.report.ok_count == dlg.report.total == len(SAMPLE_PDFS)
    assert dlg.open_folder_btn.isEnabled() and dlg.save_report_btn.isEnabled()
    assert dlg.start_btn.isEnabled() is True and dlg.stop_btn.isEnabled() is False
    assert dlg.result_folder() == out_dir.resolve()
    assert settings.batch_output_dir == str(out_dir)
    for row in range(dlg.table.rowCount()):
        assert dlg.table.item(row, dlg.COL_STATUS).text() == "Hoàn tất"
        assert dlg.table.item(row, dlg.COL_FIDELITY).text().endswith("%")
        assert dlg.table.item(row, dlg.COL_NOTE).text().endswith(".docx")
    nd30_cells = [dlg.table.item(r, dlg.COL_ND30).text() for r in range(dlg.table.rowCount())]
    assert any(c.endswith("%") for c in nd30_cells)
    assert "thành công" in dlg.summary_label.text()

    saved = dlg.save_report(tmp_path / "bao_cao.csv")
    assert saved is not None and saved.exists()
    dlg.close()
    app.processEvents()


def test_main_window_runs_batch_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QApplication

    from qtpdfpro.core.settings import AppSettings
    from qtpdfpro.ui import batch_dialog
    from qtpdfpro.ui.main_window import MainWindow
    from qtpdfpro.ui.tool_catalog import get_tool

    assert get_tool("batch_convert").ready is True
    opened: list[object] = []
    monkeypatch.setattr(batch_dialog.BatchConvertDialog, "exec", lambda self: opened.append(self) or 0)

    app = QApplication.instance() or QApplication([])
    win = MainWindow(settings=AppSettings.load())
    win.run_tool("batch_convert")
    app.processEvents()
    assert len(opened) == 1 and isinstance(opened[0], batch_dialog.BatchConvertDialog)
    assert win.act_batch_convert.shortcut().toString() == "Ctrl+Shift+B"
    win.close()
    app.processEvents()
