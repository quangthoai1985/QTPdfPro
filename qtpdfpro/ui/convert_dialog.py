"""Hộp thoại Chuyển đổi PDF sang Word (.docx) kèm Kiểm định Độ chính xác."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core.converter import (
    ConversionError,
    ConversionOptions,
    ConversionResult,
    convert_pdf_to_docx,
    parse_page_range,
)
from qtpdfpro.core.settings import AppSettings


class _ConversionWorker(QThread):
    """Luồng nền thực thi chuyển đổi PDF sang DOCX không làm đơ giao diện."""

    progress = Signal(int, int, str)
    finishedOk = Signal(object)  # ConversionResult
    failed = Signal(str)

    def __init__(
        self,
        pdf_path: str,
        docx_path: str,
        options: ConversionOptions,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.docx_path = docx_path
        self.options = options

    def run(self) -> None:
        try:
            res = convert_pdf_to_docx(
                pdf_path=self.pdf_path,
                docx_path=self.docx_path,
                options=self.options,
                progress_cb=lambda cur, tot, msg: self.progress.emit(cur, tot, msg),
            )
            self.finishedOk.emit(res)
        except Exception as exc:
            self.failed.emit(str(exc))


class ConvertToDocxDialog(QDialog):
    """Hộp thoại cấu hình và theo dõi quá trình chuyển PDF sang DOCX chuẩn xác."""

    def __init__(
        self,
        pdf_path: str | Path,
        total_pages: int,
        current_page: int,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pdf_path = Path(pdf_path).resolve()
        self.total_pages = max(1, total_pages)
        self.current_page = max(0, min(self.total_pages - 1, current_page))
        self.settings = settings
        self.last_result: Optional[ConversionResult] = None
        self._worker: Optional[_ConversionWorker] = None

        self.setWindowTitle(f"Chuyển PDF sang Word (.docx) — {self.pdf_path.name}")
        self.resize(650, 560)

        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(10)

        # 1. Tệp đầu vào & đầu ra
        io_group = QGroupBox("1. Tệp nguồn & Tệp Word đầu ra")
        io_form = QFormLayout(io_group)

        src_lbl = QLabel(f"<b>{self.pdf_path}</b> ({self.total_pages} trang)")
        src_lbl.setWordWrap(True)
        io_form.addRow("Tệp PDF gốc:", src_lbl)

        out_row = QHBoxLayout()
        default_out = str(self.pdf_path.with_suffix(".docx"))
        self.out_edit = QLineEdit(default_out)
        browse_btn = QPushButton("Chọn nơi lưu...")
        browse_btn.clicked.connect(self._browse_output)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(browse_btn)
        io_form.addRow("Lưu thành (.docx):", out_row)
        root_layout.addWidget(io_group)

        # 2. Chế độ Engine chuyển đổi
        mode_group = QGroupBox("2. Chế độ Engine Chuyển đổi & Tinh chỉnh")
        mode_form = QFormLayout(mode_group)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem(
            "Chuẩn cấu trúc thông minh (Hybrid Flow + OpenXML Fixer) — Khuyên dùng",
            userData="hybrid",
        )
        self.mode_combo.addItem(
            "Giữ nguyên vị trí tuyệt đối 1:1 (Exact Frame — Biểu mẫu / Hoá đơn / Bằng cấp)",
            userData="exact",
        )
        self.mode_combo.addItem(
            "Tự động phân tích & chọn chế độ tối ưu (Smart Auto)",
            userData="auto",
        )
        self.mode_combo.addItem(
            "Microsoft Word Native Reflow + Bộ tinh chỉnh OpenXML",
            userData="word_com",
        )
        idx_mode = self.mode_combo.findData(self.settings.default_convert_mode)
        if idx_mode >= 0:
            self.mode_combo.setCurrentIndex(idx_mode)
        mode_form.addRow("Thuật toán:", self.mode_combo)

        # Phạm vi trang
        range_box = QVBoxLayout()
        self.rb_all = QRadioButton(f"Tất cả các trang (1 – {self.total_pages})")
        self.rb_current = QRadioButton(f"Chỉ trang đang xem (Trang {self.current_page + 1})")
        custom_row = QHBoxLayout()
        self.rb_custom = QRadioButton("Tuỳ chọn trang:")
        self.custom_range_edit = QLineEdit()
        self.custom_range_edit.setPlaceholderText("Ví dụ: 1-3, 5, 8-10")
        self.custom_range_edit.textEdited.connect(lambda _: self.rb_custom.setChecked(True))
        custom_row.addWidget(self.rb_custom)
        custom_row.addWidget(self.custom_range_edit, 1)

        self.rb_all.setChecked(True)
        range_box.addWidget(self.rb_all)
        range_box.addWidget(self.rb_current)
        range_box.addLayout(custom_row)
        mode_form.addRow("Phạm vi trang:", range_box)

        # Tuỳ chọn chuẩn xác OpenXML
        self.chk_vn = QCheckBox(
            "Chuẩn hoá phông chữ 4 thuộc tính & sửa lỗi tiếng Việt (Unicode NFC / TCVN3)"
        )
        self.chk_vn.setChecked(self.settings.normalize_vietnamese)

        self.chk_table = QCheckBox(
            "Khoá độ rộng cột cố định & thu gọn lề ô bảng (chống ép rớt dòng trong bảng)"
        )
        self.chk_table.setChecked(self.settings.fix_table_padding)

        self.chk_overflow = QCheckBox(
            "Tắt bắt dính lưới dòng (SnapToGrid=0) & vi chỉnh khoảng cách chữ chống tràn trang"
        )
        self.chk_overflow.setChecked(self.settings.prevent_line_overflow)

        dpi_row = QHBoxLayout()
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(96, 300)
        self.dpi_spin.setSingleStep(24)
        self.dpi_spin.setValue(self.settings.exact_background_dpi)
        self.dpi_spin.setSuffix(" DPI")
        dpi_row.addWidget(self.dpi_spin)
        dpi_row.addWidget(QLabel("(Độ nét lớp đồ hoạ nền cho chế độ Vị trí tuyệt đối 1:1)"))
        dpi_row.addStretch(1)

        mode_form.addRow("", self.chk_vn)
        mode_form.addRow("", self.chk_table)
        mode_form.addRow("", self.chk_overflow)
        mode_form.addRow("Độ phân giải nền:", dpi_row)
        root_layout.addWidget(mode_group)

        # 3. Tiến trình & Báo cáo Độ chính xác (Fidelity Report)
        status_group = QGroupBox("3. Tiến trình & Kiểm định Độ chính xác (Fidelity Inspector)")
        status_layout = QVBoxLayout(status_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label = QLabel("Sẵn sàng chuyển đổi.")
        self.report_label = QLabel(
            "<i>Báo cáo kiểm định độ chính xác (số trang, tỷ lệ bảo toàn từ vựng, bảng biểu, "
            "phông chữ) sẽ hiển thị tại đây ngay sau khi hoàn tất.</i>"
        )
        self.report_label.setWordWrap(True)
        self.report_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        status_layout.addWidget(self.progress_bar)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.report_label, 1)
        root_layout.addWidget(status_group, 1)

        # 4. Hàng nút điều khiển
        btn_row = QHBoxLayout()
        self.open_docx_btn = QPushButton("Mở tệp Word (.docx)")
        self.open_docx_btn.setEnabled(False)
        self.open_docx_btn.clicked.connect(self._open_output_file)

        self.open_folder_btn = QPushButton("Mở thư mục chứa tệp")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self._open_output_folder)

        self.convert_btn = QPushButton("Bắt đầu chuyển sang DOCX")
        self.convert_btn.setObjectName("primaryConvertBtn")
        self.convert_btn.clicked.connect(self.start_conversion)

        self.close_btn = QPushButton("Đóng")
        self.close_btn.clicked.connect(self.reject)

        btn_row.addWidget(self.open_docx_btn)
        btn_row.addWidget(self.open_folder_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.convert_btn)
        btn_row.addWidget(self.close_btn)
        root_layout.addLayout(btn_row)

    def _browse_output(self) -> None:
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "Chọn nơi lưu tệp Word (.docx)",
            self.out_edit.text().strip(),
            "Tài liệu Microsoft Word (*.docx)",
        )
        if chosen:
            if not chosen.lower().endswith(".docx"):
                chosen += ".docx"
            self.out_edit.setText(chosen)

    def _resolve_selected_pages(self) -> Optional[list[int]]:
        if self.rb_all.isChecked():
            return None
        if self.rb_current.isChecked():
            return [self.current_page]
        return parse_page_range(self.custom_range_edit.text(), self.total_pages)

    def start_conversion(self) -> None:
        """Khởi chạy quá trình chuyển đổi trên luồng nền."""
        if self._worker is not None and self._worker.isRunning():
            return

        out_str = self.out_edit.text().strip()
        if not out_str:
            QMessageBox.warning(self, "Thiếu đường dẫn", "Vui lòng chọn đường dẫn lưu tệp DOCX.")
            return

        try:
            pages = self._resolve_selected_pages()
        except ConversionError as exc:
            QMessageBox.warning(self, "Phạm vi trang không hợp lệ", str(exc))
            return

        mode = str(self.mode_combo.currentData() or "hybrid")
        self.settings.default_convert_mode = mode
        self.settings.normalize_vietnamese = self.chk_vn.isChecked()
        self.settings.fix_table_padding = self.chk_table.isChecked()
        self.settings.prevent_line_overflow = self.chk_overflow.isChecked()
        self.settings.exact_background_dpi = self.dpi_spin.value()
        self.settings.save()

        opts = ConversionOptions(
            mode=mode,
            pages=pages,
            normalize_vietnamese=self.chk_vn.isChecked(),
            fix_table_padding=self.chk_table.isChecked(),
            prevent_line_overflow=self.chk_overflow.isChecked(),
            exact_background_dpi=self.dpi_spin.value(),
        )

        self.convert_btn.setEnabled(False)
        self.open_docx_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)
        self.progress_bar.setValue(10)
        self.status_label.setText("Đang xử lý chuyển đổi...")

        self._worker = _ConversionWorker(
            pdf_path=str(self.pdf_path),
            docx_path=out_str,
            options=opts,
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finishedOk.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        pct = int(round((current / max(1, total)) * 90)) + 5
        self.progress_bar.setValue(min(98, max(10, pct)))
        self.status_label.setText(message)

    def _on_finished(self, result: ConversionResult) -> None:
        self.last_result = result
        self.progress_bar.setValue(100)
        self.convert_btn.setEnabled(True)
        self.open_docx_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(True)
        self.status_label.setText(
            f"Hoàn tất trong {result.elapsed_seconds:.2f} giây! Đã lưu: {result.docx_path}"
        )

        fid = result.fidelity
        fix = result.fix_report
        fonts_txt = ", ".join(fid.docx_fonts[:6]) if fid.docx_fonts else "Times New Roman"
        notes_html = "".join(f"<li>{n}</li>" for n in fid.notes)

        self.report_label.setText(
            f"<b>Điểm chuẩn xác tổng hợp: <span style='color:#22C55E;'>{fid.overall_score:.1f}%</span></b> "
            f"(Chế độ thực thi: <code>{result.mode_used}</code>)<br/>"
            f"• <b>Bảo toàn từ vựng</b>: {fid.word_retention_ratio * 100:.1f}% "
            f"({fid.docx_word_count}/{fid.pdf_word_count} từ) | "
            f"<b>Bảo toàn ký tự</b>: {fid.char_retention_ratio * 100:.1f}%<br/>"
            f"• <b>Cấu trúc DOCX</b>: {fid.docx_sections} phân đoạn, {fid.docx_paragraphs} đoạn văn, "
            f"{fid.docx_tables} bảng biểu, {fid.docx_frames} khung 1:1, {fid.docx_images} hình ảnh<br/>"
            f"• <b>Tinh chỉnh OpenXML</b>: Đã chuẩn hoá {fix.fonts_normalized} lượt phông chữ "
            f"(<code>{fonts_txt}</code>), {fix.tables_tuned} bảng, {fix.paragraphs_tuned} đoạn văn"
            f"<ul>{notes_html}</ul>"
        )

    def _on_failed(self, err_msg: str) -> None:
        self.progress_bar.setValue(0)
        self.convert_btn.setEnabled(True)
        self.status_label.setText(f"Chuyển đổi thất bại: {err_msg}")
        QMessageBox.critical(
            self,
            "Lỗi chuyển đổi PDF sang DOCX",
            f"Không thể chuyển đổi tệp PDF:\n{err_msg}\n\n"
            "Mẹo: Hãy đảm bảo tệp Word đích không đang được mở trong Microsoft Word.",
        )

    def _open_output_file(self) -> None:
        if self.last_result and Path(self.last_result.docx_path).exists():
            try:
                os.startfile(self.last_result.docx_path)  # type: ignore[attr-defined]
            except Exception:
                pass

    def _open_output_folder(self) -> None:
        if self.last_result:
            p = Path(self.last_result.docx_path)
            if p.exists():
                subprocess.Popen(["explorer", "/select,", str(p)])
            elif p.parent.exists():
                os.startfile(str(p.parent))  # type: ignore[attr-defined]
