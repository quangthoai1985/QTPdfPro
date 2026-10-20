"""Hộp thoại công cụ văn phòng: Nén PDF, Đóng dấu nước, Đánh số trang, Đặt mật khẩu, Gỡ mật khẩu.

Khung chung `PdfToolDialog`: tệp nguồn (mặc định tệp của tab đang đọc, hỏi mật khẩu nếu cần), tuỳ chọn riêng
từng công cụ, ô xem trước (dấu nước, số trang), nơi lưu (mặc định cạnh tệp gốc + hậu tố) và chạy phần lõi
`qtpdfpro/core/` trong `QThread`. Tệp có chữ ký số → hỏi trước (chữ ký sẽ mất hiệu lực); tệp hạn chế quyền →
hỏi mật khẩu chủ rồi chạy lại. Kết quả nằm ở `tool_result` (`ToolResult`); `MainWindow` hỏi mở tệp mới thành tab.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

import fitz  # PyMuPDF
from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core import compress, page_stamp, pdf_security
from qtpdfpro.core.page_ops import parse_page_selection
from qtpdfpro.core.pdf_io import (
    PdfToolError,
    ToolResult,
    default_output,
    format_size,
    has_signature,
    is_protected,
    same_file,
)

WATERMARK_PRESETS = ["BẢN SAO", "MẬT", "TÀI LIỆU NỘI BỘ", "DỰ THẢO", "LƯU HÀNH NỘI BỘ",
                     "BẢN SAO\nKHÔNG CÓ GIÁ TRỊ PHÁP LÝ"]
COLOR_CHOICES = [("Đỏ", "#DC2626"), ("Xám", "#6B7280"), ("Xanh dương", "#1D4ED8"), ("Xanh lá", "#15803D"),
                 ("Cam", "#EA580C"), ("Đen", "#000000")]
FONT_CHOICES = [("Times New Roman", "serif"), ("Arial", "sans")]


class _ToolWorker(QThread):
    """Chạy một hàm lõi ở luồng nền."""

    done = Signal(object)  # ToolResult
    failed = Signal(object)  # Exception

    def __init__(self, job: Callable[[], ToolResult], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.job = job

    def run(self) -> None:
        try:
            self.done.emit(self.job())
        except Exception as exc:  # báo về luồng giao diện
            self.failed.emit(exc)


class PdfToolDialog(QDialog):
    """Khung chung của các hộp thoại công cụ PDF ghi ra tệp mới."""

    TOOL_TITLE = "Công cụ PDF"
    OUTPUT_SUFFIX = "_ket_qua"
    RUN_LABEL = "Thực hiện"
    HINT = ""
    CHECK_SIGNED = True  # hỏi trước khi xử lý tệp có chữ ký số
    PREVIEW = False

    def __init__(
        self,
        parent: QWidget | None = None,
        source: Optional[str | Path] = None,
        password: Optional[str] = None,
        is_locked: Optional[Callable[[Path], bool]] = None,
    ) -> None:
        super().__init__(parent)
        self.source_path: Optional[Path] = None
        self.source_password: Optional[str] = None
        self.source_pages = 0
        self.source_signed = False
        self.source_protected = False
        self.tool_result: Optional[ToolResult] = None
        self._is_locked = is_locked or (lambda _p: False)
        self._worker: Optional[_ToolWorker] = None
        self._running = False
        self._error: Optional[Exception] = None
        self._allow_signed = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self.render_preview)

        self.setWindowTitle(self.TOOL_TITLE)
        self.setMinimumWidth(620)
        root = QVBoxLayout(self)
        root.setSpacing(10)

        src_box = QGroupBox("Tệp PDF nguồn")
        src_lay = QHBoxLayout(src_box)
        self.source_label = QLabel("Chưa chọn tệp")
        self.source_label.setWordWrap(True)
        btn_src = QPushButton("Chọn tệp…")
        btn_src.clicked.connect(self.browse_source)
        src_lay.addWidget(self.source_label, 1)
        src_lay.addWidget(btn_src)
        root.addWidget(src_box)

        body = QHBoxLayout()
        opts = QWidget()
        opts_lay = QVBoxLayout(opts)
        opts_lay.setContentsMargins(0, 0, 0, 0)
        self.build_options(opts_lay)
        opts_lay.addStretch(1)
        body.addWidget(opts, 1)
        if self.PREVIEW:
            pv_box = QGroupBox("Xem trước")
            pv_lay = QVBoxLayout(pv_box)
            self.preview_label = QLabel("…")
            self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview_label.setFixedSize(230, 310)
            self.preview_caption = QLabel("")
            self.preview_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pv_lay.addWidget(self.preview_label)
            pv_lay.addWidget(self.preview_caption)
            body.addWidget(pv_box)
        root.addLayout(body)

        if self.HINT:
            hint = QLabel(self.HINT)
            hint.setWordWrap(True)
            hint.setObjectName("hintLabel")
            root.addWidget(hint)

        out_box = QGroupBox("Lưu thành tệp mới")
        out_lay = QHBoxLayout(out_box)
        self.out_edit = QLineEdit()
        btn_out = QPushButton("Chọn nơi lưu…")
        btn_out.clicked.connect(self.browse_output)
        out_lay.addWidget(self.out_edit, 1)
        out_lay.addWidget(btn_out)
        root.addWidget(out_box)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.run_btn = QPushButton(self.RUN_LABEL)
        self.run_btn.setObjectName("primaryBtn")
        self.run_btn.setDefault(True)
        self.run_btn.clicked.connect(self.start)
        self.close_btn = QPushButton("Đóng")
        self.close_btn.clicked.connect(self.reject)
        btns.addWidget(self.run_btn)
        btns.addWidget(self.close_btn)
        root.addLayout(btns)

        if source:
            self.set_source(source, password)

    # ─── Phần riêng của từng công cụ ───────────────────────────────────────

    def build_options(self, layout: QVBoxLayout) -> None:  # pragma: no cover - lớp con định nghĩa
        pass

    def make_job(self, src: Path, out: Path, password: Optional[str], allow_signed: bool) -> Callable[[], ToolResult]:
        raise NotImplementedError

    def validate(self) -> Optional[str]:
        """Thông báo lỗi tuỳ chọn (None = hợp lệ)."""
        return None

    def apply_preview(self, doc: fitz.Document, page_index: int) -> None:
        """Áp công cụ lên tài liệu 1 trang `doc` (bản sao trang `page_index`) để xem trước."""

    def preview_page_index(self) -> int:
        return 0

    def on_source_changed(self) -> None:
        self.schedule_preview()

    @property
    def result_password(self) -> Optional[str]:
        """Mật khẩu để mở tệp kết quả (kết quả giữ nguyên mật khẩu của tệp gốc)."""
        return self.source_password

    def result_summary(self) -> str:
        res = self.tool_result
        if res is None:
            return ""
        return res.note or f"Đã lưu {Path(res.output_path).name}"

    # ─── Tệp nguồn & nơi lưu ───────────────────────────────────────────────

    def _ask_password(self, name: str, message: str = "") -> Optional[str]:
        text = message or f"Tệp «{name}» được bảo vệ bằng mật khẩu. Nhập mật khẩu:"
        pwd, ok = QInputDialog.getText(self, "Tệp PDF có mật khẩu", text, QLineEdit.EchoMode.Password)
        return pwd if ok and pwd else None

    def set_source(self, path: str | Path, password: Optional[str] = None) -> bool:
        p = Path(path).resolve()
        try:
            doc = fitz.open(str(p))
        except Exception as exc:
            QMessageBox.warning(self, "Không mở được tệp", f"Không mở được «{p.name}»:\n{exc}")
            return False
        try:
            if not doc.is_pdf:
                QMessageBox.warning(self, "Không phải PDF", f"«{p.name}» không phải tệp PDF.")
                return False
            if doc.needs_pass:  # đọc trước khi đăng nhập (xem ghi chú trong core/pdf_io.py)
                message = ""
                while not (password and doc.authenticate(password)):
                    password = self._ask_password(p.name, message)
                    if password is None:
                        return False
                    message = f"Sai mật khẩu của «{p.name}». Nhập lại:"
            self.source_pages = doc.page_count
            self.source_signed = has_signature(doc)
            self.source_protected = is_protected(doc)
        finally:
            doc.close()
        self.source_path = p
        self.source_password = password
        bits = [f"<b>{p.name}</b>", f"{self.source_pages} trang", format_size(p.stat().st_size)]
        if self.source_protected:
            bits.append("🔐 có mật khẩu / hạn chế quyền")
        if self.source_signed:
            bits.append("✍ có chữ ký số")
        self.source_label.setText(" · ".join(bits))
        self.source_label.setToolTip(str(p))
        self.out_edit.setText(str(default_output(p, self.OUTPUT_SUFFIX)))
        self.status_label.setText("")
        self.on_source_changed()
        return True

    def browse_source(self) -> None:
        start = str(self.source_path.parent) if self.source_path else ""
        chosen, _ = QFileDialog.getOpenFileName(self, "Chọn tệp PDF", start, "Tài liệu PDF (*.pdf)")
        if chosen:
            self.set_source(chosen)

    def browse_output(self) -> None:
        current = self.out_edit.text().strip()
        chosen, _ = QFileDialog.getSaveFileName(self, "Lưu tệp kết quả", current, "Tài liệu PDF (*.pdf)")
        if chosen:
            self.out_edit.setText(chosen)

    def output_path(self) -> Optional[Path]:
        text = self.out_edit.text().strip().strip('"')
        if not text:
            return None
        out = Path(text)
        if out.suffix.lower() != ".pdf":
            out = out.with_name(out.name + ".pdf")
        return out.resolve()

    # ─── Chạy ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        if self.source_path is None:
            QMessageBox.warning(self, self.TOOL_TITLE, "Hãy chọn tệp PDF nguồn.")
            return
        problem = self.validate()
        if problem:
            QMessageBox.warning(self, self.TOOL_TITLE, problem)
            return
        out = self.output_path()
        if out is None:
            QMessageBox.warning(self, self.TOOL_TITLE, "Hãy chọn nơi lưu tệp kết quả.")
            return
        if same_file(out, self.source_path):
            QMessageBox.warning(self, self.TOOL_TITLE, "Tệp kết quả trùng tệp nguồn — hãy chọn tên khác.")
            return
        if self._is_locked(out):
            QMessageBox.warning(self, "Tệp đang mở", f"«{out.name}» đang mở ở một tab — hãy đóng tab đó hoặc chọn tên khác.")
            return
        if self.CHECK_SIGNED and self.source_signed and not self._allow_signed:
            answer = QMessageBox.question(
                self, "Văn bản có chữ ký số",
                f"«{self.source_path.name}» có chữ ký số. {self.TOOL_TITLE} ghi lại toàn bộ tệp nên chữ ký số "
                "trong tệp kết quả sẽ mất hiệu lực (tệp gốc vẫn giữ nguyên).\n\nVẫn tiếp tục?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._allow_signed = True
        self._launch(self.make_job(self.source_path, out, self.source_password, self._allow_signed))

    def _launch(self, job: Callable[[], ToolResult]) -> None:
        self._running = True
        self.tool_result = None
        self._error = None
        self.run_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText("Đang xử lý…")
        self._worker = _ToolWorker(job, self)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_thread_finished)
        self._worker.start()

    def _on_done(self, res: ToolResult) -> None:
        self.tool_result = res

    def _on_failed(self, exc: Exception) -> None:
        self._error = exc

    def _on_thread_finished(self) -> None:
        if self._worker is not None:
            self._worker.wait()
        self._running = False
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        err, res = self._error, self.tool_result
        if err is not None:
            self.status_label.setText("")
            if isinstance(err, PermissionError) and self.source_path is not None:
                pwd = self._ask_password(self.source_path.name, f"{err}\n\nNhập mật khẩu:")
                if pwd:
                    self.source_password = pwd
                    self.start()
                return
            QMessageBox.warning(self, f"Không thực hiện được — {self.TOOL_TITLE}", str(err))
            return
        if res is None:
            return
        if not res.written:
            self.status_label.setText(res.note)
            QMessageBox.information(self, self.TOOL_TITLE, res.note)
            return
        self.status_label.setText(self.result_summary())
        self.accept()

    def wait_finished(self) -> None:
        """Đợi luồng nền xong và xử lý kết quả (dùng cho kiểm thử)."""
        if self._worker is not None:
            self._worker.wait()
        for _ in range(3):
            QApplication.processEvents()

    def reject(self) -> None:
        if self._running:
            return  # đợi xử lý xong, không huỷ QThread đang chạy
        super().reject()

    # ─── Xem trước ─────────────────────────────────────────────────────────

    def schedule_preview(self, *_args) -> None:
        if self.PREVIEW:
            self._preview_timer.start()

    def render_preview(self) -> None:
        if not self.PREVIEW:
            return
        if self.source_path is None:
            self.preview_label.setText("Chưa chọn tệp")
            return
        idx = max(0, min(self.source_pages - 1, self.preview_page_index()))
        try:
            with fitz.open(str(self.source_path)) as src:
                if src.needs_pass:
                    src.authenticate(self.source_password or "")
                one = fitz.open()
                one.insert_pdf(src, from_page=idx, to_page=idx)
            try:
                self.apply_preview(one, idx)
                page = one[0]
                zoom = min(self.preview_label.width() / page.rect.width, self.preview_label.height() / page.rect.height)
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                samples = pix.samples  # giữ bộ đệm sống tới khi QImage.copy() xong
                img = QImage(samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            finally:
                one.close()
        except Exception as exc:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(f"Không xem trước được:\n{exc}")
            self.preview_label.setWordWrap(True)
            self.preview_caption.setText("")
            return
        self.preview_label.setPixmap(QPixmap.fromImage(img))
        self.preview_caption.setText(f"Trang {idx + 1}/{self.source_pages}")


def _spin(lo: int, hi: int, value: int, suffix: str = "") -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(value)
    if suffix:
        s.setSuffix(suffix)
    return s


def _combo(items, current=None) -> QComboBox:
    c = QComboBox()
    for label, data in items:
        c.addItem(label, userData=data)
    if current is not None:
        idx = c.findData(current)
        if idx >= 0:
            c.setCurrentIndex(idx)
    return c


# ─── Nén PDF ──────────────────────────────────────────────────────────────


class CompressDialog(PdfToolDialog):
    TOOL_TITLE = "Nén PDF"
    OUTPUT_SUFFIX = compress.SUFFIX
    RUN_LABEL = "Nén"
    HINT = ("Ảnh được giảm độ phân giải và nén JPEG; chữ, hình vẽ vector giữ nguyên. Phông chữ nhúng tập con, "
            "dọn đối tượng thừa. Tệp có mật khẩu giữ nguyên mật khẩu. Kết quả không nhỏ hơn thì không ghi tệp.")

    def build_options(self, layout: QVBoxLayout) -> None:
        box = QGroupBox("Mức nén")
        lay = QVBoxLayout(box)
        self.level_group = QButtonGroup(self)
        self.level_buttons: dict[str, QRadioButton] = {}
        for key, lv in compress.COMPRESS_LEVELS.items():
            rb = QRadioButton(f"{lv.label} — {lv.description}")
            self.level_group.addButton(rb)
            self.level_buttons[key] = rb
            lay.addWidget(rb)
        self.level_buttons["medium"].setChecked(True)
        layout.addWidget(box)

    @property
    def level(self) -> str:
        for key, rb in self.level_buttons.items():
            if rb.isChecked():
                return key
        return "medium"

    def make_job(self, src, out, password, allow_signed):
        level = self.level
        return lambda: compress.compress_pdf(src, out, level, password, allow_signed)


# ─── Đóng dấu nước ────────────────────────────────────────────────────────


class WatermarkDialog(PdfToolDialog):
    TOOL_TITLE = "Đóng dấu nước"
    OUTPUT_SUFFIX = page_stamp.WATERMARK_SUFFIX
    RUN_LABEL = "Đóng dấu nước"
    PREVIEW = True

    def build_options(self, layout: QVBoxLayout) -> None:
        box = QGroupBox("Nội dung && kiểu chữ")
        form = QFormLayout(box)
        self.text_edit = QPlainTextEdit("BẢN SAO")
        self.text_edit.setFixedHeight(56)
        self.text_edit.setPlaceholderText("Chữ tiếng Việt, có thể xuống dòng")
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("— Chọn mẫu có sẵn —", userData=None)
        for text in WATERMARK_PRESETS:
            self.preset_combo.addItem(text.replace("\n", " / "), userData=text)
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        self.font_combo = _combo(FONT_CHOICES, "sans")
        self.bold_check = QCheckBox("Đậm")
        self.bold_check.setChecked(True)
        font_row = QHBoxLayout()
        font_row.addWidget(self.font_combo, 1)
        font_row.addWidget(self.bold_check)
        self.size_spin = _spin(6, 300, 56, " pt")
        self.color_combo = _combo(COLOR_CHOICES, "#DC2626")
        form.addRow("Nội dung:", self.text_edit)
        form.addRow("Mẫu nhanh:", self.preset_combo)
        form.addRow("Phông chữ:", font_row)
        form.addRow("Cỡ chữ:", self.size_spin)
        form.addRow("Màu:", self.color_combo)
        layout.addWidget(box)

        box2 = QGroupBox("Vị trí && độ mờ")
        form2 = QFormLayout(box2)
        self.opacity_spin = _spin(2, 100, 20, " %")
        self.angle_spin = _spin(-180, 180, 45, "°")
        self.layout_combo = _combo([(label, key) for key, label in page_stamp.WATERMARK_LAYOUTS], "center")
        self.behind_check = QCheckBox("Đặt dưới nội dung trang (ảnh quét nền trắng sẽ che mất dấu)")
        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("Bỏ trống = tất cả · vd 1-3,5 · le · chan")
        form2.addRow("Độ đậm:", self.opacity_spin)
        form2.addRow("Góc xoay:", self.angle_spin)
        form2.addRow("Bố cục:", self.layout_combo)
        form2.addRow("", self.behind_check)
        form2.addRow("Các trang:", self.pages_edit)
        layout.addWidget(box2)

        self.text_edit.textChanged.connect(self.schedule_preview)
        for w in (self.size_spin, self.opacity_spin, self.angle_spin):
            w.valueChanged.connect(self.schedule_preview)
        for c in (self.font_combo, self.color_combo, self.layout_combo):
            c.currentIndexChanged.connect(self.schedule_preview)
        self.bold_check.toggled.connect(self.schedule_preview)
        self.behind_check.toggled.connect(self.schedule_preview)
        self.pages_edit.textChanged.connect(self.schedule_preview)

    def _apply_preset(self, _idx: int) -> None:
        text = self.preset_combo.currentData()
        if text:
            self.text_edit.setPlainText(text)

    def options(self) -> page_stamp.WatermarkOptions:
        return page_stamp.WatermarkOptions(
            text=self.text_edit.toPlainText().strip(), font_size=float(self.size_spin.value()),
            opacity=self.opacity_spin.value() / 100.0, angle=float(self.angle_spin.value()),
            color=self.color_combo.currentData(), font_family=self.font_combo.currentData(),
            bold=self.bold_check.isChecked(), layout=self.layout_combo.currentData(),
            pages=self.pages_edit.text().strip(), behind=self.behind_check.isChecked(),
        )

    def validate(self) -> Optional[str]:
        if not self.text_edit.toPlainText().strip():
            return "Hãy nhập nội dung dấu nước."
        return None

    def make_job(self, src, out, password, allow_signed):
        opts = self.options()
        return lambda: page_stamp.watermark_pdf(src, out, opts, password, allow_signed)

    def preview_page_index(self) -> int:
        try:
            pages = parse_page_selection(self.pages_edit.text().strip(), self.source_pages)
        except ValueError:
            return 0
        return pages[0] if pages else 0

    def apply_preview(self, doc: fitz.Document, page_index: int) -> None:
        opts = self.options()
        if opts.text:
            page_stamp.apply_watermark(doc, replace(opts, pages=""))

    def result_summary(self) -> str:
        res = self.tool_result
        return f"Đã đóng dấu nước {res.pages_changed}/{res.pages} trang." if res else ""


# ─── Đánh số trang ────────────────────────────────────────────────────────


class PageNumberDialog(PdfToolDialog):
    TOOL_TITLE = "Đánh số trang"
    OUTPUT_SUFFIX = page_stamp.NUMBER_SUFFIX
    RUN_LABEL = "Đánh số trang"
    PREVIEW = True

    def build_options(self, layout: QVBoxLayout) -> None:
        self.nd30_btn = QPushButton("🏛️ Dùng mẫu «Chuẩn NĐ30»")
        self.nd30_btn.setToolTip("Nghị định 30/2020/NĐ-CP: số Ả Rập giữa lề trên, Times New Roman 13, không hiện số trang 1")
        self.nd30_btn.clicked.connect(self.apply_nd30_preset)
        layout.addWidget(self.nd30_btn)

        box = QGroupBox("Mẫu số && vị trí")
        form = QFormLayout(box)
        self.format_combo = QComboBox()
        for template, example in page_stamp.NUMBER_FORMATS:
            self.format_combo.addItem(example, userData=template)
        self.template_edit = QLineEdit("{n}")
        self.template_edit.setToolTip("{n} = số trang, {total} = tổng số trang")
        self.format_combo.currentIndexChanged.connect(
            lambda _i: self.template_edit.setText(self.format_combo.currentData() or "{n}")
        )
        self.position_combo = _combo([(label, key) for key, label in page_stamp.POSITIONS], "bottom-center")
        self.start_spin = _spin(0, 99999, 1)
        self.skip_first_check = QCheckBox("Không hiện số ở trang đầu (vẫn tính số)")
        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("Bỏ trống = tất cả · vd 2-10")
        form.addRow("Kiểu số:", self.format_combo)
        form.addRow("Mẫu ({n}, {total}):", self.template_edit)
        form.addRow("Vị trí:", self.position_combo)
        form.addRow("Bắt đầu từ số:", self.start_spin)
        form.addRow("", self.skip_first_check)
        form.addRow("Các trang:", self.pages_edit)
        layout.addWidget(box)

        box2 = QGroupBox("Kiểu chữ && lề")
        form2 = QFormLayout(box2)
        self.font_combo = _combo(FONT_CHOICES, "serif")
        self.bold_check = QCheckBox("Đậm")
        font_row = QHBoxLayout()
        font_row.addWidget(self.font_combo, 1)
        font_row.addWidget(self.bold_check)
        self.size_spin = _spin(6, 48, 12, " pt")
        self.margin_spin = _spin(0, 100, 10, " mm")
        self.side_spin = _spin(0, 100, 20, " mm")
        form2.addRow("Phông chữ:", font_row)
        form2.addRow("Cỡ chữ:", self.size_spin)
        form2.addRow("Cách mép trên / dưới:", self.margin_spin)
        form2.addRow("Cách mép trái / phải:", self.side_spin)
        layout.addWidget(box2)

        self.template_edit.textChanged.connect(self.schedule_preview)
        self.position_combo.currentIndexChanged.connect(self._on_position_changed)
        for w in (self.start_spin, self.size_spin, self.margin_spin, self.side_spin):
            w.valueChanged.connect(self.schedule_preview)
        self.font_combo.currentIndexChanged.connect(self.schedule_preview)
        for chk in (self.bold_check, self.skip_first_check):
            chk.toggled.connect(self.schedule_preview)
        self.pages_edit.textChanged.connect(self.schedule_preview)
        self._on_position_changed()

    def _on_position_changed(self, *_args) -> None:
        pos = self.position_combo.currentData() or ""
        self.side_spin.setEnabled(not pos.endswith("center"))
        self.schedule_preview()

    def apply_nd30_preset(self) -> None:
        self.load_options(page_stamp.nd30_page_number_options())

    def load_options(self, o: page_stamp.PageNumberOptions) -> None:
        idx = self.format_combo.findData(o.template)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)
        self.template_edit.setText(o.template)
        self.position_combo.setCurrentIndex(max(0, self.position_combo.findData(o.position)))
        self.start_spin.setValue(int(o.start))
        self.skip_first_check.setChecked(bool(o.skip_first))
        self.font_combo.setCurrentIndex(max(0, self.font_combo.findData(o.font_family)))
        self.bold_check.setChecked(bool(o.bold))
        self.size_spin.setValue(int(round(o.font_size)))
        self.margin_spin.setValue(int(round(o.margin_mm)))
        self.side_spin.setValue(int(round(o.side_margin_mm)))
        self.pages_edit.setText(o.pages)

    def options(self) -> page_stamp.PageNumberOptions:
        return page_stamp.PageNumberOptions(
            template=self.template_edit.text().strip() or "{n}", position=self.position_combo.currentData(),
            start=self.start_spin.value(), skip_first=self.skip_first_check.isChecked(),
            font_size=float(self.size_spin.value()), font_family=self.font_combo.currentData(),
            bold=self.bold_check.isChecked(), margin_mm=float(self.margin_spin.value()),
            side_margin_mm=float(self.side_spin.value()), pages=self.pages_edit.text().strip(),
        )

    def validate(self) -> Optional[str]:
        if "{n}" not in self.template_edit.text():
            return "Mẫu số trang phải có {n} (vd «Trang {n}», «{n} / {total}»)."
        return None

    def make_job(self, src, out, password, allow_signed):
        opts = self.options()
        return lambda: page_stamp.number_pages(src, out, opts, password, allow_signed)

    def _targets(self) -> list[int]:
        try:
            return sorted(parse_page_selection(self.pages_edit.text().strip(), self.source_pages))
        except ValueError:
            return list(range(self.source_pages))

    def preview_page_index(self) -> int:
        pages = self._targets()
        if not pages:
            return 0
        return pages[1] if self.skip_first_check.isChecked() and len(pages) > 1 else pages[0]

    def apply_preview(self, doc: fitz.Document, page_index: int) -> None:
        opts = self.options()
        pages = self._targets()
        if page_index not in pages or (opts.skip_first and pages and page_index == pages[0]):
            return
        k = pages.index(page_index)
        total = str(opts.start + len(pages) - 1)
        template = opts.template.replace("{total}", total).replace("{tong}", total)
        page_stamp.apply_page_numbers(
            doc, replace(opts, template=template, start=opts.start + k, skip_first=False, pages="")
        )

    def result_summary(self) -> str:
        res = self.tool_result
        return f"Đã đánh số {res.pages_changed}/{res.pages} trang." if res else ""


# ─── Đặt / gỡ mật khẩu ────────────────────────────────────────────────────


def _password_edit(placeholder: str = "") -> QLineEdit:
    e = QLineEdit()
    e.setEchoMode(QLineEdit.EchoMode.Password)
    e.setPlaceholderText(placeholder)
    return e


class ProtectDialog(PdfToolDialog):
    TOOL_TITLE = "Đặt mật khẩu PDF"
    OUTPUT_SUFFIX = pdf_security.PROTECT_SUFFIX
    RUN_LABEL = "Đặt mật khẩu"
    HINT = ("Mã hoá AES-256. Hạn chế quyền cần mật khẩu chủ khác mật khẩu mở. Hãy ghi nhớ mật khẩu — mất mật khẩu "
            "mở thì không ai mở lại được tệp. Hạn chế quyền chỉ được các trình đọc PDF tuân thủ chuẩn tôn trọng.")

    def build_options(self, layout: QVBoxLayout) -> None:
        box = QGroupBox("Mật khẩu")
        form = QFormLayout(box)
        self.user_edit = _password_edit("Bỏ trống = mở không cần mật khẩu")
        self.user_confirm = _password_edit()
        self.owner_edit = _password_edit("Để đổi quyền hoặc gỡ bảo vệ")
        self.owner_confirm = _password_edit()
        self.show_check = QCheckBox("Hiện mật khẩu")
        self.show_check.toggled.connect(self._toggle_echo)
        form.addRow("Mật khẩu mở tệp:", self.user_edit)
        form.addRow("Nhập lại:", self.user_confirm)
        form.addRow("Mật khẩu chủ:", self.owner_edit)
        form.addRow("Nhập lại:", self.owner_confirm)
        form.addRow("", self.show_check)
        layout.addWidget(box)

        perm_box = QGroupBox("Cho phép người mở tệp")
        perm_lay = QVBoxLayout(perm_box)
        self.perm_checks: dict[str, QCheckBox] = {}
        for key, label, _bits in pdf_security.PERMISSIONS:
            chk = QCheckBox(label)
            chk.setChecked(True)
            self.perm_checks[key] = chk
            perm_lay.addWidget(chk)
        layout.addWidget(perm_box)

    def _toggle_echo(self, show: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        for e in (self.user_edit, self.user_confirm, self.owner_edit, self.owner_confirm):
            e.setEchoMode(mode)

    def options(self) -> pdf_security.ProtectOptions:
        c = self.perm_checks
        return pdf_security.ProtectOptions(
            user_password=self.user_edit.text(), owner_password=self.owner_edit.text(),
            allow_print=c["print"].isChecked(), allow_copy=c["copy"].isChecked(),
            allow_modify=c["modify"].isChecked(), allow_annotate=c["annotate"].isChecked(),
        )

    def validate(self) -> Optional[str]:
        if self.user_edit.text() != self.user_confirm.text():
            return "Mật khẩu mở nhập lại không khớp."
        if self.owner_edit.text() != self.owner_confirm.text():
            return "Mật khẩu chủ nhập lại không khớp."
        o = self.options()
        if not o.user_password and not o.owner_password:
            return "Hãy nhập mật khẩu mở hoặc mật khẩu chủ."
        if o.restricted and not o.owner_password:
            return "Hạn chế quyền cần có mật khẩu chủ."
        if o.restricted and o.owner_password == o.user_password:
            return "Mật khẩu chủ phải khác mật khẩu mở khi hạn chế quyền."
        return None

    def make_job(self, src, out, password, allow_signed):
        opts = self.options()
        return lambda: pdf_security.protect_pdf(src, out, opts, password, allow_signed)

    @property
    def result_password(self) -> Optional[str]:
        return self.user_edit.text() or None


class UnlockDialog(PdfToolDialog):
    TOOL_TITLE = "Gỡ mật khẩu PDF"
    OUTPUT_SUFFIX = pdf_security.UNLOCK_SUFFIX
    RUN_LABEL = "Gỡ mật khẩu"
    CHECK_SIGNED = False
    HINT = "Tệp đang hạn chế quyền (cấm in, sao chép, sửa…) cần mật khẩu chủ; mật khẩu mở chỉ đủ khi tệp không hạn chế quyền."

    def build_options(self, layout: QVBoxLayout) -> None:
        box = QGroupBox("Mật khẩu hiện tại")
        form = QFormLayout(box)
        self.password_edit = _password_edit("Mật khẩu chủ hoặc mật khẩu mở")
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        form.addRow("Mật khẩu:", self.password_edit)
        form.addRow("Tình trạng:", self.info_label)
        layout.addWidget(box)

    def on_source_changed(self) -> None:
        if self.source_password and not self.password_edit.text():
            self.password_edit.setText(self.source_password)
        try:
            info = pdf_security.security_info(self.source_path)
        except Exception as exc:
            self.info_label.setText(str(exc))
            return
        if not info.encrypted:
            self.info_label.setText("Tệp không có mật khẩu hay hạn chế quyền nào.")
            return
        parts = ["Cần mật khẩu để mở" if info.needs_password else "Mở không cần mật khẩu"]
        denied = [label.lower() for key, label, _b in pdf_security.PERMISSIONS if info.permissions.get(key) is False]
        if denied:
            parts.append("cấm " + ", ".join(denied))
        if info.method and info.method != "?":
            parts.append(info.method)
        self.info_label.setText(" · ".join(parts))

    def validate(self) -> Optional[str]:
        if not (self.password_edit.text() or self.source_password):
            return "Hãy nhập mật khẩu."
        return None

    def make_job(self, src, out, password, allow_signed):
        pwd = self.password_edit.text() or password or ""
        return lambda: pdf_security.unlock_pdf(src, out, pwd)

    def _on_thread_finished(self) -> None:
        err = self._error
        if isinstance(err, PermissionError):
            self._error = PdfToolError(str(err))  # sai mật khẩu: báo lỗi, người dùng sửa ô mật khẩu
        super()._on_thread_finished()

    @property
    def result_password(self) -> Optional[str]:
        return None


PDF_TOOL_DIALOGS = {
    "compress": CompressDialog,
    "watermark": WatermarkDialog,
    "page_numbers": PageNumberDialog,
    "protect": ProtectDialog,
    "unlock": UnlockDialog,
}
