"""Hộp thoại «Chuyển đổi hàng loạt» nhiều tệp PDF sang Word (.docx) kèm bảng điểm từng tệp."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core.batch import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_TEXT,
    BatchItemResult,
    BatchProgress,
    BatchReport,
    collect_pdf_paths,
    convert_batch,
    plan_output_paths,
    write_batch_report,
)
from qtpdfpro.core.converter import ConversionOptions
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.core.word_com_bridge import is_ms_word_available
from qtpdfpro.ui.convert_dialog import MODE_CHOICES, POLICY_CHOICES

_STATUS_COLOR = {
    STATUS_PENDING: "#64748B",
    STATUS_RUNNING: "#2563EB",
    STATUS_OK: "#16A34A",
    STATUS_FAILED: "#DC2626",
    STATUS_CANCELLED: "#64748B",
}

_VERDICT_TEXT = {
    "match": "Trùng khớp",
    "minor": "Lệch nhỏ",
    "deviated": "Lệch đáng kể",
    "unavailable": "Không có MS Word",
}

REPORT_FILE_NAME = "bao_cao_chuyen_doi_hang_loat.csv"


def _score_color(score: float) -> str:
    return "#16A34A" if score >= 90 else ("#D97706" if score >= 70 else "#DC2626")


def _fmt_pct(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1f}%".replace(".", ",")


class _BatchWorker(QThread):
    """Luồng nền chạy `convert_batch`, báo tiến trình từng tệp về giao diện."""

    progress = Signal(object)  # BatchProgress
    finishedOk = Signal(object)  # BatchReport
    failed = Signal(str)

    def __init__(
        self,
        pdf_paths: List[Path],
        out_dir: Optional[str],
        options: ConversionOptions,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pdf_paths = list(pdf_paths)
        self.out_dir = out_dir
        self.options = options
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            report = convert_batch(
                self.pdf_paths,
                self.out_dir,
                options=self.options,
                progress_cb=self.progress.emit,
                should_cancel=lambda: self._cancel,
            )
            self.finishedOk.emit(report)
        except Exception as exc:  # pragma: no cover - lỗi ngoài dự kiến hiển thị cho người dùng
            self.failed.emit(str(exc))


class BatchConvertDialog(QDialog):
    """Chọn / kéo thả nhiều PDF, chọn thư mục lưu, chạy chuyển đổi và xem bảng điểm từng tệp."""

    COLUMNS = [
        "Tệp PDF",
        "Trạng thái",
        "Chế độ",
        "Số trang",
        "Chuẩn xác",
        "Thể thức NĐ30",
        "Kiểm chứng Word",
        "Tệp Word / Ghi chú",
    ]
    COL_FILE, COL_STATUS, COL_MODE, COL_PAGES, COL_FIDELITY, COL_ND30, COL_VERIFY, COL_NOTE = range(8)

    def __init__(
        self,
        settings: AppSettings,
        parent: QWidget | None = None,
        pdf_paths: Optional[Iterable[str | Path]] = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.pdf_paths: List[Path] = []
        self.report: Optional[BatchReport] = None
        self._results: dict[str, BatchItemResult] = {}
        self._worker: Optional[_BatchWorker] = None
        self._running = False
        self._close_when_done = False

        self.setWindowTitle("Chuyển đổi hàng loạt PDF sang Word (.docx)")
        self.resize(1000, 700)
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        headline = QLabel(
            "🗂️ <b>Chuyển đổi hàng loạt</b> — kéo thả nhiều tệp PDF (hoặc cả thư mục) vào cửa sổ này. "
            "Văn bản hành chính tự dùng engine chuẩn thể thức NĐ30."
        )
        headline.setObjectName("dialogHeadline")
        headline.setWordWrap(True)
        root.addWidget(headline)

        # 1. Danh sách tệp
        files_group = QGroupBox("1. Danh sách tệp PDF")
        files_lay = QVBoxLayout(files_group)
        tools_row = QHBoxLayout()
        self.add_files_btn = QPushButton("＋ Thêm tệp PDF…")
        self.add_files_btn.clicked.connect(self._browse_files)
        self.add_folder_btn = QPushButton("＋ Thêm thư mục…")
        self.add_folder_btn.clicked.connect(self._browse_folder)
        self.remove_btn = QPushButton("Bỏ tệp đã chọn")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn = QPushButton("Xoá danh sách")
        self.clear_btn.clicked.connect(self.clear_files)
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("mutedLabel")
        for w in (self.add_files_btn, self.add_folder_btn, self.remove_btn, self.clear_btn):
            tools_row.addWidget(w)
        tools_row.addStretch(1)
        tools_row.addWidget(self.count_lbl)
        files_lay.addLayout(tools_row)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_FILE, QHeaderView.ResizeMode.Stretch)
        for col in range(self.COL_STATUS, self.COL_NOTE):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_NOTE, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self.table.setToolTip("Nhấp đúp vào tệp đã chuyển xong để mở bằng Word.")
        files_lay.addWidget(self.table, 1)
        root.addWidget(files_group, 1)

        # 2. Nơi lưu & chế độ
        opt_group = QGroupBox("2. Nơi lưu && Chế độ chuyển đổi")
        opt_form = QFormLayout(opt_group)

        self.dest_combo = QComboBox()
        self.dest_combo.addItem("Vào thư mục chọn bên dưới", userData="folder")
        self.dest_combo.addItem("Cạnh từng tệp PDF gốc (cùng tên, đuôi .docx)", userData="beside")
        self.dest_combo.setCurrentIndex(self.dest_combo.findData("folder" if self.settings.batch_output_dir else "beside"))
        self.dest_combo.currentIndexChanged.connect(self._sync_dest_widgets)
        opt_form.addRow("Lưu tệp Word:", self.dest_combo)

        dir_row = QHBoxLayout()
        self.out_dir_edit = QLineEdit(self.settings.batch_output_dir)
        self.out_dir_edit.setPlaceholderText("Chọn thư mục lưu các tệp Word…")
        self.browse_out_btn = QPushButton("Chọn thư mục…")
        self.browse_out_btn.clicked.connect(self._browse_out_dir)
        dir_row.addWidget(self.out_dir_edit, 1)
        dir_row.addWidget(self.browse_out_btn)
        opt_form.addRow("Thư mục lưu:", dir_row)

        self.mode_combo = QComboBox()
        for label, key in MODE_CHOICES:
            self.mode_combo.addItem(label, userData=key)
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData("auto")))
        opt_form.addRow("Thuật toán:", self.mode_combo)

        self.policy_combo = QComboBox()
        for label, key in POLICY_CHOICES:
            self.policy_combo.addItem(label, userData=key)
        self.policy_combo.setCurrentIndex(max(0, self.policy_combo.findData(self.settings.nd30_policy)))
        opt_form.addRow("Thể thức NĐ30:", self.policy_combo)
        self.mode_combo.currentIndexChanged.connect(self._sync_mode_widgets)

        self._word_available = is_ms_word_available()
        self.chk_verify = QCheckBox(
            "Kiểm chứng từng tệp bằng Microsoft Word (dựng lại DOCX && so vị trí từng dòng — chậm hơn nhiều)"
        )
        self.chk_verify.setChecked(False)
        self.chk_verify.setEnabled(self._word_available)
        if not self._word_available:
            self.chk_verify.setToolTip("Máy chưa cài Microsoft Word nên không thể kiểm chứng bố cục.")
        opt_form.addRow("", self.chk_verify)
        root.addWidget(opt_group)
        self._sync_mode_widgets()
        self._sync_dest_widgets()

        # 3. Tiến trình
        prog_group = QGroupBox("3. Tiến trình && Báo cáo tổng hợp")
        prog_lay = QVBoxLayout(prog_group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label = QLabel("Thêm tệp PDF rồi bấm «Bắt đầu chuyển đổi».")
        self.status_label.setWordWrap(True)
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        prog_lay.addWidget(self.progress_bar)
        prog_lay.addWidget(self.status_label)
        prog_lay.addWidget(self.summary_label)
        root.addWidget(prog_group)

        # 4. Nút điều khiển
        btn_row = QHBoxLayout()
        self.open_folder_btn = QPushButton("📂 Mở thư mục kết quả")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self.open_result_folder)
        self.save_report_btn = QPushButton("Lưu báo cáo (.csv)…")
        self.save_report_btn.setEnabled(False)
        self.save_report_btn.clicked.connect(self._browse_save_report)
        self.stop_btn = QPushButton("Dừng")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("Dừng sau khi tệp đang chuyển xong")
        self.stop_btn.clicked.connect(lambda: self.request_stop(close_after=False))
        self.start_btn = QPushButton("Bắt đầu chuyển đổi")
        self.start_btn.setObjectName("primaryConvertBtn")
        self.start_btn.clicked.connect(self.start_batch)
        self.close_btn = QPushButton("Đóng")
        self.close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.open_folder_btn)
        btn_row.addWidget(self.save_report_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.close_btn)
        root.addLayout(btn_row)

        if pdf_paths:
            self.add_paths(pdf_paths)
        self._refresh_table()

    # ─── Danh sách tệp ────────────────────────────────────────────────────

    def is_running(self) -> bool:
        return self._running

    def add_paths(self, paths: Iterable[str | Path]) -> int:
        """Thêm tệp PDF / thư mục (chỉ lấy tệp .pdf có thật, bỏ trùng). Trả về số tệp mới."""
        if self.is_running():
            return 0
        existing = {str(p).lower() for p in self.pdf_paths}
        added = 0
        for pdf in collect_pdf_paths(paths):
            if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
                continue
            if str(pdf).lower() in existing:
                continue
            existing.add(str(pdf).lower())
            self.pdf_paths.append(pdf)
            added += 1
        if added:
            self._refresh_table()
        return added

    def remove_selected(self) -> None:
        if self.is_running():
            return
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.pdf_paths):
                del self.pdf_paths[r]
        self._refresh_table()

    def clear_files(self) -> None:
        if self.is_running():
            return
        self.pdf_paths.clear()
        self._results.clear()
        self._refresh_table()

    def _browse_files(self) -> None:
        chosen, _ = QFileDialog.getOpenFileNames(self, "Chọn các tệp PDF cần chuyển sang Word", "", "Tài liệu PDF (*.pdf)")
        if chosen:
            self.add_paths(chosen)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa các tệp PDF")
        if folder:
            if self.add_paths([folder]) == 0:
                self.status_label.setText(f"Không có tệp PDF mới trong thư mục: {folder}")

    def _browse_out_dir(self) -> None:
        start = self.out_dir_edit.text().strip() or (str(self.pdf_paths[0].parent) if self.pdf_paths else "")
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu các tệp Word (.docx)", start)
        if folder:
            self.out_dir_edit.setText(folder)
            self.dest_combo.setCurrentIndex(self.dest_combo.findData("folder"))

    def uses_out_dir(self) -> bool:
        return self.dest_combo.currentData() == "folder"

    def set_out_dir(self, folder: str | Path) -> None:
        self.out_dir_edit.setText(str(folder))
        self.dest_combo.setCurrentIndex(self.dest_combo.findData("folder"))

    def _sync_dest_widgets(self) -> None:
        editable = self.uses_out_dir() and not self.is_running()
        self.out_dir_edit.setEnabled(editable)
        self.browse_out_btn.setEnabled(editable)

    def _sync_mode_widgets(self) -> None:
        mode = str(self.mode_combo.currentData() or "auto")
        self.policy_combo.setEnabled(mode in ("auto", "nd30"))

    def _set_editing_enabled(self, enabled: bool) -> None:
        for w in (
            self.add_files_btn,
            self.add_folder_btn,
            self.remove_btn,
            self.clear_btn,
            self.dest_combo,
            self.mode_combo,
            self.start_btn,
        ):
            w.setEnabled(enabled)
        self._sync_dest_widgets()
        self.policy_combo.setEnabled(enabled and str(self.mode_combo.currentData()) in ("auto", "nd30"))
        self.chk_verify.setEnabled(enabled and self._word_available)
        self.stop_btn.setEnabled(not enabled)

    # ─── Bảng kết quả ─────────────────────────────────────────────────────

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.pdf_paths))
        for row, pdf in enumerate(self.pdf_paths):
            name_item = QTableWidgetItem(pdf.name)
            name_item.setToolTip(str(pdf))
            self.table.setItem(row, self.COL_FILE, name_item)
            res = self._results.get(str(pdf).lower())
            self._fill_row(row, res)
        n = len(self.pdf_paths)
        self.count_lbl.setText(f"{n} tệp PDF" if n else "Chưa có tệp — kéo thả PDF vào đây")
        self.start_btn.setEnabled(n > 0 and not self.is_running())

    def _set_cell(self, row: int, col: int, text: str, color: Optional[str] = None, tip: str = "") -> None:
        item = QTableWidgetItem(text)
        if color:
            item.setForeground(QColor(color))
        if tip:
            item.setToolTip(tip)
        if col in (self.COL_PAGES, self.COL_FIDELITY, self.COL_ND30):
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col, item)

    def _fill_row(self, row: int, res: Optional[BatchItemResult]) -> None:
        status = res.status if res is not None else STATUS_PENDING
        self._set_cell(row, self.COL_STATUS, STATUS_TEXT.get(status, status), _STATUS_COLOR.get(status))
        if res is None or res.status != STATUS_OK:
            for col in (self.COL_MODE, self.COL_PAGES, self.COL_FIDELITY, self.COL_ND30, self.COL_VERIFY):
                self._set_cell(row, col, "")
            err = res.error if res is not None else ""
            self._set_cell(row, self.COL_NOTE, err, _STATUS_COLOR[STATUS_FAILED] if err else None, err)
            return
        self._set_cell(row, self.COL_MODE, res.mode_used)
        self._set_cell(row, self.COL_PAGES, str(res.pages_converted))
        fid = res.fidelity_score
        self._set_cell(row, self.COL_FIDELITY, _fmt_pct(fid), _score_color(fid) if fid is not None else None)
        nd = res.nd30_score
        self._set_cell(
            row,
            self.COL_ND30,
            _fmt_pct(nd),
            _score_color(nd) if nd is not None else None,
            "" if nd is not None else "Không phải văn bản hành chính (không chấm thể thức NĐ30)",
        )
        if res.layout_verdict is None:
            self._set_cell(row, self.COL_VERIFY, "—")
        else:
            verdict_color = {"match": "#16A34A", "minor": "#D97706", "deviated": "#DC2626"}.get(res.layout_verdict)
            self._set_cell(row, self.COL_VERIFY, _VERDICT_TEXT.get(res.layout_verdict, res.layout_verdict), verdict_color)
        tip = res.docx_path + ("\n" + "\n".join(res.notes) if res.notes else "")
        self._set_cell(row, self.COL_NOTE, Path(res.docx_path).name, tip=tip)

    # ─── Chạy chuyển đổi ──────────────────────────────────────────────────

    def selected_out_dir(self) -> Optional[str]:
        """Thư mục lưu đã chọn; None = lưu cạnh từng tệp PDF gốc."""
        if not self.uses_out_dir():
            return None
        return self.out_dir_edit.text().strip() or None

    def build_options(self) -> ConversionOptions:
        return ConversionOptions(
            mode=str(self.mode_combo.currentData() or "auto"),
            nd30_policy=str(self.policy_combo.currentData() or "faithful"),
            normalize_vietnamese=self.settings.normalize_vietnamese,
            fix_table_padding=self.settings.fix_table_padding,
            prevent_line_overflow=self.settings.prevent_line_overflow,
            exact_background_dpi=self.settings.exact_background_dpi,
            verify_layout=self.chk_verify.isChecked() and self._word_available,
        )

    def start_batch(self, confirm_overwrite: bool = True) -> bool:
        """Bắt đầu chuyển đổi trên luồng nền. Trả về False nếu thiếu thông tin hoặc người dùng huỷ."""
        if self.is_running():
            return False
        if not self.pdf_paths:
            QMessageBox.warning(self, "Chưa có tệp", "Hãy thêm ít nhất một tệp PDF cần chuyển đổi.")
            return False
        out_dir = self.selected_out_dir()
        if self.uses_out_dir() and out_dir is None:
            QMessageBox.warning(self, "Thiếu thư mục lưu", "Hãy chọn thư mục lưu các tệp Word.")
            return False

        if confirm_overwrite:
            existing = [p for p in plan_output_paths(self.pdf_paths, out_dir) if p.exists()]
            if existing:
                names = "\n".join(f"• {p.name}" for p in existing[:8]) + ("\n…" if len(existing) > 8 else "")
                answer = QMessageBox.question(
                    self,
                    "Ghi đè tệp Word đã có?",
                    f"{len(existing)} tệp Word đã tồn tại và sẽ bị ghi đè:\n{names}\n\nTiếp tục chuyển đổi?",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return False

        self.settings.batch_output_dir = out_dir or ""
        self.settings.nd30_policy = str(self.policy_combo.currentData() or "faithful")
        self.settings.save()

        self.report = None
        self._results.clear()
        self._refresh_table()
        self._running = True
        self._set_editing_enabled(False)
        self.open_folder_btn.setEnabled(False)
        self.save_report_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.summary_label.setText("")
        self.status_label.setText(f"Đang chuyển đổi {len(self.pdf_paths)} tệp PDF…")

        self._worker = _BatchWorker(self.pdf_paths, out_dir, self.build_options(), self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finishedOk.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        return True

    def request_stop(self, close_after: bool = False) -> None:
        """Dừng sau khi tệp đang chuyển xong (các tệp còn lại đánh dấu «Đã huỷ»)."""
        if not self.is_running():
            return
        self._close_when_done = self._close_when_done or close_after
        assert self._worker is not None
        self._worker.request_cancel()
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Đang dừng — chờ tệp hiện tại chuyển xong…")

    def wait_for_worker(self, timeout_ms: int = -1) -> bool:
        """Chờ luồng nền kết thúc (dùng khi kiểm thử). Tín hiệu còn xếp hàng cần `processEvents()`."""
        if self._worker is None:
            return True
        return self._worker.wait(timeout_ms) if timeout_ms >= 0 else self._worker.wait()

    def _on_progress(self, ev: BatchProgress) -> None:
        self.progress_bar.setValue(int(round(ev.fraction * 100)))
        self.status_label.setText(ev.message)
        if ev.item is not None and 0 <= ev.item.index < len(self.pdf_paths):
            self._results[str(self.pdf_paths[ev.item.index]).lower()] = ev.item
            self._fill_row(ev.item.index, ev.item)
            if ev.item.status == STATUS_RUNNING:
                self.table.scrollToItem(self.table.item(ev.item.index, self.COL_FILE))

    def _finish_worker(self) -> None:
        # Tín hiệu kết thúc là câu lệnh cuối của run() → luồng thoát ngay; chờ để không huỷ QThread đang chạy
        if self._worker is not None:
            self._worker.wait(10000)
        self._running = False

    def _on_finished(self, report: BatchReport) -> None:
        self._finish_worker()
        self.report = report
        for item in report.items:
            if 0 <= item.index < len(self.pdf_paths):
                self._results[str(self.pdf_paths[item.index]).lower()] = item
        self._refresh_table()
        self._set_editing_enabled(True)
        self.progress_bar.setValue(100)
        self.open_folder_btn.setEnabled(report.ok_count > 0)
        self.save_report_btn.setEnabled(report.total > 0)

        parts = [f"<b>{report.ok_count}/{report.total}</b> tệp chuyển thành công"]
        if report.failed_count:
            parts.append(f"<span style='color:#DC2626;'><b>{report.failed_count}</b> thất bại</span>")
        if report.cancelled_count:
            parts.append(f"{report.cancelled_count} đã huỷ")
        if report.average_fidelity is not None:
            parts.append(f"điểm chuẩn xác trung bình <b>{_fmt_pct(report.average_fidelity)}</b>")
        if report.average_nd30 is not None:
            parts.append(f"thể thức NĐ30 trung bình <b>{_fmt_pct(report.average_nd30)}</b>")
        parts.append(f"{report.elapsed_seconds:.1f} giây".replace(".", ","))
        self.summary_label.setText(" · ".join(parts))
        self.status_label.setText(
            "Đã dừng theo yêu cầu." if report.cancelled else "Hoàn tất. Nhấp đúp một dòng để mở tệp Word."
        )
        if self._close_when_done:
            super().reject()

    def _on_failed(self, err_msg: str) -> None:
        self._finish_worker()
        self._set_editing_enabled(True)
        self.start_btn.setEnabled(bool(self.pdf_paths))
        self.status_label.setText(f"Chuyển đổi hàng loạt thất bại: {err_msg}")
        if self._close_when_done:
            super().reject()

    # ─── Kết quả ──────────────────────────────────────────────────────────

    def result_folder(self) -> Optional[Path]:
        if self.report is None:
            return None
        if self.report.out_dir:
            return Path(self.report.out_dir)
        ok = [it for it in self.report.items if it.ok]
        return Path(ok[0].docx_path).parent if ok else None

    def open_result_folder(self) -> None:
        folder = self.result_folder()
        if folder is None or not folder.exists():
            return
        try:
            os.startfile(str(folder))  # type: ignore[attr-defined]
        except Exception:
            subprocess.Popen(["explorer", str(folder)])

    def save_report(self, path: str | Path) -> Optional[Path]:
        if self.report is None:
            return None
        return write_batch_report(self.report, path)

    def _browse_save_report(self) -> None:
        if self.report is None:
            return
        folder = self.result_folder() or Path.home()
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu báo cáo chuyển đổi hàng loạt",
            str(folder / REPORT_FILE_NAME),
            "Bảng tính CSV (*.csv);;Dữ liệu JSON (*.json)",
        )
        if not chosen:
            return
        if Path(chosen).suffix.lower() not in (".csv", ".json"):
            chosen += ".csv"
        try:
            saved = self.save_report(chosen)
        except OSError as exc:
            QMessageBox.critical(self, "Không lưu được báo cáo", str(exc))
            return
        if saved is not None:
            self.status_label.setText(f"Đã lưu báo cáo: {saved}")

    def _on_row_double_clicked(self, row: int, _col: int) -> None:
        if not (0 <= row < len(self.pdf_paths)):
            return
        res = self._results.get(str(self.pdf_paths[row]).lower())
        if res is not None and res.ok and Path(res.docx_path).exists():
            try:
                os.startfile(res.docx_path)  # type: ignore[attr-defined]
            except Exception:
                pass

    # ─── Kéo thả & đóng ───────────────────────────────────────────────────

    @staticmethod
    def _dropped_paths(event) -> List[str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        paths = []
        for url in mime.urls():
            local = url.toLocalFile()
            if local and (local.lower().endswith(".pdf") or Path(local).is_dir()):
                paths.append(local)
        return paths

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - API Qt
        if not self.is_running() and self._dropped_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - API Qt
        if not self.is_running() and self._dropped_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - API Qt
        paths = self._dropped_paths(event)
        if paths and not self.is_running():
            added = self.add_paths(paths)
            self.status_label.setText(f"Đã thêm {added} tệp PDF." if added else "Không có tệp PDF mới.")
            event.acceptProposedAction()
        else:
            event.ignore()

    def reject(self) -> None:
        if self.is_running():
            answer = QMessageBox.question(
                self,
                "Đang chuyển đổi",
                "Đang chuyển đổi hàng loạt. Dừng sau tệp hiện tại và đóng cửa sổ?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.request_stop(close_after=True)
            return
        super().reject()
