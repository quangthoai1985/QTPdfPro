"""Hộp thoại «In tài liệu» (Ctrl+P): chọn máy in, số bản, khoảng trang, khổ giấy, hướng, 2 mặt, màu — xem trước
từng tờ đúng như sẽ in, nhớ thiết lập lần trước và gửi lệnh in trong luồng nền có thanh tiến trình."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from PySide6.QtCore import QRectF, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QResizeEvent, QStandardItemModel
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core.printing import (
    DUPLEX_MODES,
    ORIENTATIONS,
    PAPER_LABELS,
    PAPER_SIZES,
    SCALE_MODES,
    SUBSETS,
    PrintError,
    PrintOptions,
    PrintPlan,
    PrintResult,
    PrintSheet,
    apply_subset,
    page_sizes,
    plan_print,
    printing_allowed,
    render_sheet,
    resolve_print_pages,
    snapshot_pdf_bytes,
)
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import print_job

PDF_TARGET = "__pdf__"  # mục «Lưu bản in thành tệp PDF» trong danh sách máy in
QUALITY_CHOICES = [("Cao — theo máy in (tối đa 600 dpi)", 600), ("Nhanh — 300 dpi", 300)]
COLOR_CHOICES = [("Màu", False), ("Đen trắng (thang xám)", True)]
_PREVIEW_MIN_DPI, _PREVIEW_MAX_DPI = 36, 220


class _PrintWorker(QThread):
    """Luồng nền: mở bản chụp tài liệu riêng (PyMuPDF không dùng chung tài liệu giữa các luồng) rồi in từng tờ."""

    progress = Signal(int, int)
    finishedOk = Signal(object)  # PrintResult
    failed = Signal(str)

    def __init__(self, printer, pdf_bytes: bytes, pages: List[int], options: PrintOptions, doc_name: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.printer = printer
        self.pdf_bytes = pdf_bytes
        self.pages = list(pages)
        self.options = options
        self.doc_name = doc_name
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            doc = fitz.open("pdf", self.pdf_bytes)
        except Exception as exc:  # pragma: no cover - bản chụp hỏng là lỗi ngoài dự kiến
            self.failed.emit(f"Không đọc được tài liệu để in: {exc}")
            return
        try:
            res = print_job.print_document(
                self.printer, doc, self.pages, self.options, doc_name=self.doc_name,
                progress=self.progress.emit, should_cancel=lambda: self._cancel,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        finally:
            doc.close()
        self.finishedOk.emit(res)


class PrintPreviewView(QWidget):
    """Tờ giấy xem trước: vùng không in được (viền gạch), ảnh trang đặt đúng khung của kế hoạch in."""

    resized = Signal()

    def __init__(self, dark: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.dark = dark
        self.sheet: Optional[PrintSheet] = None
        self.image: Optional[QImage] = None
        self.margins: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self.message = ""
        self.setMinimumSize(260, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:  # noqa: N802 - API Qt
        return QSize(460, 600)

    def set_content(self, sheet: Optional[PrintSheet], image: Optional[QImage],
                    margins: Tuple[float, float, float, float], message: str = "") -> None:
        self.sheet, self.image, self.margins, self.message = sheet, image, margins, message
        self.update()

    def paper_rect(self, paper_w: float, paper_h: float) -> QRectF:
        """Khung tờ giấy (điểm ảnh) vừa khung xem, chừa lề 18 px."""
        pad = 18.0
        avail_w, avail_h = max(10.0, self.width() - 2 * pad), max(10.0, self.height() - 2 * pad)
        k = min(avail_w / paper_w, avail_h / paper_h)
        w, h = paper_w * k, paper_h * k
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - API Qt
        super().resizeEvent(event)
        self.resized.emit()

    def paintEvent(self, _event) -> None:  # noqa: N802 - API Qt
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#111318" if self.dark else "#E2E8F0"))
        sheet = self.sheet
        if sheet is None:
            p.setPen(QColor("#9CA3AF" if self.dark else "#64748B"))
            p.drawText(self.rect().adjusted(24, 0, -24, 0), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       self.message or "Chưa có trang để xem trước")
            p.end()
            return
        paper = self.paper_rect(sheet.paper_width, sheet.paper_height)
        k = paper.width() / sheet.paper_width
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for i, alpha in enumerate((60, 35, 18)):  # bóng đổ nhẹ
            p.fillRect(paper.translated(2 + i, 3 + i), QColor(0, 0, 0, alpha))
        p.fillRect(paper, QColor("#FFFFFF"))
        p.save()
        p.setClipRect(paper)
        if self.image is not None:
            x0, y0, x1, y1 = sheet.target
            target = QRectF(paper.x() + x0 * k, paper.y() + y0 * k, (x1 - x0) * k, (y1 - y0) * k)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(target, self.image)
        p.restore()
        ml, mt, mr, mb = self.margins
        if any(m > 0.5 for m in self.margins):
            pen = QPen(QColor(148, 163, 184, 170), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(paper.adjusted(ml * k, mt * k, -mr * k, -mb * k))
        p.setPen(QPen(QColor("#94A3B8"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(paper)
        p.end()


class PrintDialog(QDialog):
    """Hộp thoại in tài liệu đang mở (gồm cả chú thích chưa lưu)."""

    def __init__(
        self,
        doc: fitz.Document,
        settings: AppSettings,
        *,
        doc_name: str = "",
        doc_path: str = "",
        current_page: int = 0,
        theme: str = "dark",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.doc = doc
        self.settings = settings
        self.doc_name = doc_name or "Tài liệu PDF"
        self.doc_path = doc_path
        self.page_count = doc.page_count
        self.current_page = max(0, min(self.page_count - 1, int(current_page)))
        self.output_path: Optional[str] = None  # đặt sẵn (kiểm thử) để bỏ qua hộp thoại chọn nơi lưu
        self.result: Optional[PrintResult] = None
        self.result_message = ""
        self.plan: Optional[PrintPlan] = None
        self.preview_index = 0
        self._sizes = page_sizes(doc)
        self._worker: Optional[_PrintWorker] = None
        self._running = False
        self._close_when_done = False
        self._margin_cache: Dict[Tuple[str, str], Tuple[float, float, float, float]] = {}
        self._margins_pending = False
        self._caps_cache: Dict[str, dict] = {}
        self._image_cache: Dict[tuple, QImage] = {}
        self._allowed = printing_allowed(doc)

        self.setWindowTitle(f"In tài liệu — {self.doc_name}")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.resize(1060, 740)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(70)
        self._refresh_timer.timeout.connect(self.refresh_plan)

        opts = PrintOptions.from_settings(settings.print_settings)
        self._build_ui(theme != "light")
        self._load_options(opts)
        self._connect_changes()
        self._on_printer_changed()
        self.refresh_plan()

    # ─── Dựng giao diện ───────────────────────────────────────────────────

    def _build_ui(self, dark: bool) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)
        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        form_host = QWidget()
        form = QVBoxLayout(form_host)
        form.setContentsMargins(0, 0, 6, 0)
        form.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(form_host)
        scroll.setFixedWidth(400)
        body.addWidget(scroll)

        # 1. Máy in & số bản
        grp_printer = QGroupBox("Máy in")
        lay_printer = QFormLayout(grp_printer)
        self.printer_combo = QComboBox()
        self.printer_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.printer_combo.setMinimumContentsLength(18)
        default = print_job.default_printer_name()
        for name in print_job.available_printers():
            label = f"{name} (mặc định)" if name == default else name
            self.printer_combo.addItem("🖨 " + label.replace("&", "&&"), userData=name)
        self.printer_combo.addItem("💾 Lưu bản in thành tệp PDF…", userData=PDF_TARGET)
        lay_printer.addRow("Máy in:", self.printer_combo)
        self.caps_label = QLabel("")
        self.caps_label.setObjectName("mutedLabel")
        self.caps_label.setWordWrap(True)
        lay_printer.addRow("", self.caps_label)
        copies_row = QHBoxLayout()
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 999)
        self.copies_spin.setValue(1)
        self.chk_collate = QCheckBox("In trọn từng bộ")
        self.chk_collate.setToolTip("Bật: 1-2-3, 1-2-3…  ·  Tắt: 1-1, 2-2, 3-3…")
        copies_row.addWidget(self.copies_spin)
        copies_row.addWidget(self.chk_collate)
        copies_row.addStretch(1)
        lay_printer.addRow("Số bản:", copies_row)
        form.addWidget(grp_printer)

        # 2. Trang in
        grp_pages = QGroupBox("Trang in")
        lay_pages = QVBoxLayout(grp_pages)
        self.scope_group = QButtonGroup(self)
        self.rb_all = QRadioButton(f"Tất cả ({self.page_count} trang)")
        self.rb_current = QRadioButton(f"Trang hiện tại (trang {self.current_page + 1})")
        self.rb_custom = QRadioButton("Tuỳ chọn:")
        for i, rb in enumerate((self.rb_all, self.rb_current, self.rb_custom)):
            self.scope_group.addButton(rb, i)
        self.rb_all.setChecked(True)
        lay_pages.addWidget(self.rb_all)
        lay_pages.addWidget(self.rb_current)
        custom_row = QHBoxLayout()
        custom_row.addWidget(self.rb_custom)
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("vd: 1-3, 5, 8-")
        self.range_edit.setClearButtonEnabled(True)
        custom_row.addWidget(self.range_edit, 1)
        lay_pages.addLayout(custom_row)
        hint = QLabel("8- = từ trang 8 tới hết · -3 = trang 1–3 · end = trang cuối")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        lay_pages.addWidget(hint)
        self.range_error = QLabel("")
        self.range_error.setWordWrap(True)
        self.range_error.setStyleSheet("color: #DC2626;")
        self.range_error.setVisible(False)
        lay_pages.addWidget(self.range_error)
        sub_form = QFormLayout()
        self.subset_combo = QComboBox()
        for key, label in SUBSETS.items():
            self.subset_combo.addItem(label, userData=key)
        self.subset_combo.setToolTip(
            "Máy in không có in 2 mặt tự động: in «Chỉ trang lẻ», lật xấp giấy cho lại vào khay, rồi in «Chỉ trang chẵn»."
        )
        sub_form.addRow("Lọc trang:", self.subset_combo)
        lay_pages.addLayout(sub_form)
        self.chk_reverse = QCheckBox("In ngược thứ tự (trang cuối ra trước)")
        lay_pages.addWidget(self.chk_reverse)
        form.addWidget(grp_pages)

        # 3. Giấy & bố cục
        grp_paper = QGroupBox("Khổ giấy && bố cục")
        lay_paper = QFormLayout(grp_paper)
        self.paper_combo = QComboBox()
        for key in PAPER_SIZES:
            self.paper_combo.addItem(PAPER_LABELS[key], userData=key)
        lay_paper.addRow("Khổ giấy:", self.paper_combo)
        self.orient_combo = QComboBox()
        for key, label in ORIENTATIONS.items():
            self.orient_combo.addItem(label, userData=key)
        lay_paper.addRow("Hướng giấy:", self.orient_combo)
        self.scale_combo = QComboBox()
        for key, label in SCALE_MODES.items():
            self.scale_combo.addItem(label, userData=key)
        lay_paper.addRow("Tỷ lệ:", self.scale_combo)
        self.chk_auto_rotate = QCheckBox("Tự xoay trang ngang / dọc cho vừa giấy")
        lay_paper.addRow("", self.chk_auto_rotate)
        form.addWidget(grp_paper)

        # 4. Tuỳ chọn in
        grp_opts = QGroupBox("Tuỳ chọn in")
        lay_opts = QFormLayout(grp_opts)
        self.duplex_combo = QComboBox()
        for key, label in DUPLEX_MODES.items():
            self.duplex_combo.addItem(label, userData=key)
        lay_opts.addRow("In 2 mặt:", self.duplex_combo)
        self.color_combo = QComboBox()
        for label, gray in COLOR_CHOICES:
            self.color_combo.addItem(label, userData=gray)
        lay_opts.addRow("Màu in:", self.color_combo)
        self.quality_combo = QComboBox()
        for label, dpi in QUALITY_CHOICES:
            self.quality_combo.addItem(label, userData=dpi)
        lay_opts.addRow("Chất lượng:", self.quality_combo)
        self.chk_annots = QCheckBox("In kèm chú thích, con dấu và chữ ký")
        lay_opts.addRow("", self.chk_annots)
        form.addWidget(grp_opts)
        form.addStretch(1)

        # Xem trước
        preview_col = QVBoxLayout()
        preview_col.setSpacing(6)
        self.preview = PrintPreviewView(dark)
        self.preview.resized.connect(self._schedule_preview)
        preview_col.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setToolTip("Tờ trước (PgUp)")
        self.btn_prev.setShortcut("PgUp")
        self.btn_prev.clicked.connect(lambda: self.go_preview(self.preview_index - 1))
        self.btn_next = QPushButton("▶")
        self.btn_next.setToolTip("Tờ sau (PgDown)")
        self.btn_next.setShortcut("PgDown")
        self.btn_next.clicked.connect(lambda: self.go_preview(self.preview_index + 1))
        self.nav_label = QLabel("")
        self.nav_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.nav_label, 1)
        nav.addWidget(self.btn_next)
        preview_col.addLayout(nav)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("mutedLabel")
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_label.setWordWrap(True)
        preview_col.addWidget(self.summary_label)
        body.addLayout(preview_col, 1)

        # Tiến trình & nút
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)
        btn_row = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        btn_row.addWidget(self.status_label, 1)
        self.cancel_btn = QPushButton("Huỷ")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        self.print_btn = QPushButton("🖨 In")
        self.print_btn.setObjectName("primaryConvertBtn")
        self.print_btn.setDefault(True)
        self.print_btn.clicked.connect(self.start_print)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.print_btn)
        root.addLayout(btn_row)
        if not self._allowed:
            self.print_btn.setEnabled(False)
            self.status_label.setText("⛔ Tài liệu này không cho phép in (chủ sở hữu đã tắt quyền in).")

    def _connect_changes(self) -> None:
        self.printer_combo.currentIndexChanged.connect(self._on_printer_changed)
        self.scope_group.idToggled.connect(lambda _i, on: on and self._schedule_refresh())
        self.range_edit.textChanged.connect(self._on_range_edited)
        for combo in (self.subset_combo, self.paper_combo, self.orient_combo, self.scale_combo,
                      self.duplex_combo, self.color_combo, self.quality_combo):
            combo.currentIndexChanged.connect(self._schedule_refresh)
        for chk in (self.chk_reverse, self.chk_auto_rotate, self.chk_annots, self.chk_collate):
            chk.toggled.connect(self._schedule_refresh)
        self.copies_spin.valueChanged.connect(self._schedule_refresh)

    @staticmethod
    def _select_data(combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _load_options(self, opts: PrintOptions) -> None:
        printer = opts.printer
        if self.printer_combo.findData(printer) < 0:
            printer = print_job.default_printer_name()
        if self.printer_combo.findData(printer) < 0:
            printer = self.printer_combo.itemData(0)
        self._select_data(self.printer_combo, printer)
        self.chk_collate.setChecked(opts.collate)
        self._select_data(self.paper_combo, opts.paper)
        self._select_data(self.orient_combo, opts.orientation)
        self._select_data(self.scale_combo, opts.scale)
        self.chk_auto_rotate.setChecked(opts.auto_rotate)
        self._select_data(self.duplex_combo, opts.duplex)
        self._select_data(self.color_combo, opts.grayscale)
        self._select_data(self.quality_combo, opts.max_dpi)
        self.chk_annots.setChecked(opts.annotations)

    # ─── Đọc thiết lập ────────────────────────────────────────────────────

    @property
    def printer_target(self) -> str:
        return str(self.printer_combo.currentData() or "")

    def page_scope(self) -> str:
        return ("all", "current", "custom")[max(0, self.scope_group.checkedId())]

    def current_options(self) -> PrintOptions:
        return PrintOptions(
            printer=self.printer_target,
            copies=self.copies_spin.value(),
            collate=self.chk_collate.isChecked(),
            paper=str(self.paper_combo.currentData()),
            orientation=str(self.orient_combo.currentData()),
            scale=str(self.scale_combo.currentData()),
            auto_rotate=self.chk_auto_rotate.isChecked(),
            duplex=str(self.duplex_combo.currentData()) if self.duplex_combo.isEnabled() else "none",
            grayscale=bool(self.color_combo.currentData()),
            annotations=self.chk_annots.isChecked(),
            subset=str(self.subset_combo.currentData()),
            reverse=self.chk_reverse.isChecked(),
            max_dpi=int(self.quality_combo.currentData()),
        ).normalized()

    def selected_pages(self) -> List[int]:
        """Trang được chọn (0-based, chưa lọc lẻ/chẵn). Ném `PrintError` nếu khoảng trang sai."""
        return resolve_print_pages(self.page_scope(), self.range_edit.text(), self.page_count, self.current_page)

    def set_page_range(self, spec: str) -> None:
        self.rb_custom.setChecked(True)
        self.range_edit.setText(spec)
        self.refresh_plan()

    # ─── Máy in ───────────────────────────────────────────────────────────

    def _capabilities(self, name: str) -> dict:
        if name == PDF_TARGET:
            return {"duplex": False, "color": True, "default_color": True}
        if name not in self._caps_cache:
            self._caps_cache[name] = print_job.printer_capabilities(name)
        return self._caps_cache[name]

    def _printer_margins(self, name: str, paper: str, fetch: bool = True) -> Optional[Tuple[float, float, float, float]]:
        """Lề không in được của máy in (pt). Tạo `QPrinter` mất ~0,2–1 giây nên lưu đệm theo máy in & khổ giấy;
        `fetch=False` chỉ đọc bộ đệm (None nếu chưa có)."""
        if name == PDF_TARGET or print_job.file_printer_suffix(name) == ".pdf":
            return (0.0, 0.0, 0.0, 0.0)
        key = (name, paper)
        if key not in self._margin_cache:
            if not fetch:
                return None
            try:
                printer = print_job.create_printer(name)
                print_job.configure_printer(printer, PrintOptions(paper=paper), False)
                self._margin_cache[key] = print_job.printer_margins_pt(printer)
            except Exception:
                self._margin_cache[key] = (0.0, 0.0, 0.0, 0.0)
        return self._margin_cache[key]

    def _fetch_margins_later(self) -> None:
        """Đọc lề máy in sau khi hộp thoại đã hiện (không làm chậm lúc mở), rồi lập lại kế hoạch."""
        if self._margins_pending:
            return
        self._margins_pending = True

        def fetch() -> None:
            self._margins_pending = False
            if self._running:
                return
            self._printer_margins(self.printer_target, str(self.paper_combo.currentData()))
            self.refresh_plan()

        QTimer.singleShot(30, self, fetch)  # gắn với hộp thoại: không gọi nếu hộp thoại đã bị huỷ

    @staticmethod
    def _set_item_enabled(combo: QComboBox, data, enabled: bool, tip: str = "") -> None:
        model = combo.model()
        idx = combo.findData(data)
        if idx < 0 or not isinstance(model, QStandardItemModel):
            return
        item = model.item(idx)
        item.setEnabled(enabled)
        item.setToolTip("" if enabled else tip)

    def _on_printer_changed(self) -> None:
        name = self.printer_target
        caps = self._capabilities(name)
        notes = []
        no_duplex_tip = "Máy in này không in 2 mặt tự động — dùng «Lọc trang: Chỉ trang lẻ», lật giấy rồi in trang chẵn."
        for key in ("long", "short"):
            self._set_item_enabled(self.duplex_combo, key, caps["duplex"], no_duplex_tip)
        if not caps["duplex"] and self.duplex_combo.currentData() != "none":
            self._select_data(self.duplex_combo, "none")
        self.duplex_combo.setEnabled(name != PDF_TARGET)
        self.duplex_combo.setToolTip("" if caps["duplex"] else no_duplex_tip)
        self._set_item_enabled(self.color_combo, False, caps["color"], "Máy in đen trắng")
        if not caps["color"]:
            self._select_data(self.color_combo, True)
        if name == PDF_TARGET:
            notes.append("Ghi các trang đã dàn khổ giấy ra tệp PDF (không cần máy in).")
        else:
            notes.append("In 2 mặt tự động: có" if caps["duplex"] else "Không in 2 mặt tự động")
            notes.append("Máy in màu" if caps["color"] else "Máy in đen trắng")
            if print_job.file_printer_suffix(name):
                notes.append("sẽ hỏi nơi lưu tệp")
        self.caps_label.setText(" · ".join(notes))
        self._schedule_refresh()

    # ─── Kế hoạch & xem trước ─────────────────────────────────────────────

    def _schedule_refresh(self, *_args) -> None:
        if not self._running:
            self._refresh_timer.start()

    def _schedule_preview(self) -> None:
        if self.plan is not None:
            QTimer.singleShot(0, self, self.update_preview)

    def _on_range_edited(self, _text: str) -> None:
        if not self.rb_custom.isChecked():
            self.rb_custom.setChecked(True)
        self._schedule_refresh()

    def refresh_plan(self, fetch_margins: bool = False) -> Optional[PrintPlan]:
        """Lập lại kế hoạch in theo thiết lập hiện tại và vẽ lại xem trước."""
        self._refresh_timer.stop()
        opts = self.current_options()
        try:
            pages = apply_subset(self.selected_pages(), opts.subset, opts.reverse)
            if not pages:
                raise PrintError("Không có trang nào sau khi lọc trang lẻ / chẵn.")
            margins = self._printer_margins(self.printer_target, opts.paper, fetch=fetch_margins)
            if margins is None:
                margins = (0.0, 0.0, 0.0, 0.0)
                self._fetch_margins_later()
            self.plan = plan_print(self._sizes, pages, opts, margins)
        except PrintError as exc:
            self.plan = None
            self.range_error.setText(str(exc))
            self.range_error.setVisible(True)
            self.print_btn.setEnabled(False)
            self.summary_label.setText("")
            self.nav_label.setText("")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.preview.set_content(None, None, (0, 0, 0, 0), str(exc))
            return None
        self.range_error.setVisible(False)
        self.print_btn.setEnabled(self._allowed and not self._running)
        self.preview_index = max(0, min(self.preview_index, self.plan.sheet_count - 1))
        summary = self.plan.summary()
        if any(s.clipped for s in self.plan.sheets):
            summary += " · ⚠ Có trang lớn hơn vùng in — chọn «Vừa khổ giấy» để không mất mép"
        self.summary_label.setText(summary)
        self.update_preview()
        return self.plan

    def go_preview(self, index: int) -> None:
        if self.plan is None:
            return
        self.preview_index = max(0, min(index, self.plan.sheet_count - 1))
        self.update_preview()

    def _preview_dpi(self, sheet: PrintSheet) -> int:
        paper = self.preview.paper_rect(sheet.paper_width, sheet.paper_height)
        dpr = self.preview.devicePixelRatioF() or 1.0
        dpi = 72.0 * paper.width() / sheet.paper_width * dpr
        return int(max(_PREVIEW_MIN_DPI, min(_PREVIEW_MAX_DPI, round(dpi / 12.0) * 12)))

    def preview_image(self, sheet: PrintSheet) -> Optional[QImage]:
        if sheet.page_index is None or self.plan is None:
            return None
        o = self.plan.options
        dpi = self._preview_dpi(sheet)
        key = (sheet.page_index, sheet.rotate, round(sheet.scale, 4), o.grayscale, o.annotations, dpi)
        img = self._image_cache.get(key)
        if img is None and not self._running:  # khi đang in không chạm vào PyMuPDF ở luồng giao diện
            rendered = render_sheet(self.doc, sheet, dpi, o.grayscale, o.annotations)
            if rendered is None:
                return None
            img = print_job.to_qimage(rendered).copy()
            if len(self._image_cache) > 24:
                self._image_cache.pop(next(iter(self._image_cache)))
            self._image_cache[key] = img
        return img

    def update_preview(self) -> None:
        plan = self.plan
        if plan is None or not plan.sheets:
            return
        sheet = plan.sheets[self.preview_index]
        self.preview.set_content(sheet, self.preview_image(sheet), plan.margins)
        n = plan.sheet_count
        page_txt = f"trang {sheet.page_index + 1} của tài liệu" if sheet.page_index is not None else "tờ trắng"
        extra = " · xoay 90°" if sheet.rotate else ""
        self.nav_label.setText(f"Tờ {self.preview_index + 1} / {n} — {page_txt}{extra} · {sheet.scale * 100:.0f}%")
        self.btn_prev.setEnabled(self.preview_index > 0)
        self.btn_next.setEnabled(self.preview_index < n - 1)

    # ─── In ───────────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        return self._running

    def _ask_output_path(self, suffix: str) -> Optional[str]:
        if self.output_path:
            return self.output_path
        base = Path(self.doc_path) if self.doc_path else Path.home() / self.doc_name
        default = str(base.with_name(f"{base.stem}_ban_in{suffix}"))
        filters = "Tài liệu PDF (*.pdf)" if suffix == ".pdf" else "Tài liệu XPS (*.xps)"
        chosen, _ = QFileDialog.getSaveFileName(self, "Lưu bản in thành tệp", default, filters)
        if not chosen:
            return None
        if not chosen.lower().endswith(suffix):
            chosen += suffix
        if self.doc_path and Path(chosen).resolve() == Path(self.doc_path).resolve():
            QMessageBox.warning(self, "Trùng tệp đang in", "Hãy chọn tên khác — không ghi đè tệp PDF đang mở.")
            return None
        return chosen

    def start_print(self) -> bool:
        """Bắt đầu in trên luồng nền. Trả về False nếu thiết lập sai hoặc người dùng huỷ chọn nơi lưu."""
        if self._running:
            return False
        if not self._allowed:
            QMessageBox.warning(self, "Không được phép in", "Tài liệu này không cho phép in.")
            return False
        plan = self.refresh_plan()
        if plan is None:
            return False
        opts = self.current_options()
        target = self.printer_target
        suffix = ".pdf" if target == PDF_TARGET else print_job.file_printer_suffix(target)
        output = self._ask_output_path(suffix) if suffix else None
        if suffix and output is None:
            return False
        try:
            printer = print_job.create_printer("" if target == PDF_TARGET else target, output)
            pdf_bytes = snapshot_pdf_bytes(self.doc)
        except Exception as exc:
            QMessageBox.critical(self, "Không chuẩn bị được lệnh in", str(exc))
            return False

        self.settings.print_settings = opts.to_settings()
        self.settings.save()

        self._running = True
        self._set_controls_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        where = Path(output).name if output else (target or "máy in mặc định")
        self.status_label.setText(f"Đang chuẩn bị in {plan.sheet_count} trang tới «{where}»…")
        self._worker = _PrintWorker(printer, pdf_bytes, self.selected_pages(), opts, self.doc_name, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finishedOk.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        return True

    def _set_controls_enabled(self, enabled: bool) -> None:
        for w in self.findChildren(QGroupBox):
            w.setEnabled(enabled)
        self.print_btn.setEnabled(enabled and self.plan is not None and self._allowed)
        self.cancel_btn.setText("Huỷ" if enabled else "Dừng in")

    def wait_for_worker(self, timeout_ms: int = -1) -> bool:
        """Chờ luồng in kết thúc (dùng khi kiểm thử). Tín hiệu còn xếp hàng cần `processEvents()`."""
        if self._worker is None:
            return True
        return self._worker.wait(timeout_ms) if timeout_ms >= 0 else self._worker.wait()

    def request_stop(self, close_after: bool = False) -> None:
        if not self._running or self._worker is None:
            return
        self._close_when_done = self._close_when_done or close_after
        self._worker.request_cancel()
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Đang dừng — chờ tờ đang gửi xong…")

    def _on_progress(self, done: int, total: int) -> None:
        self.progress_bar.setValue(int(round(done * 100 / max(1, total))))
        self.status_label.setText(f"Đã gửi {done}/{total} tờ…")

    def _finish_worker(self) -> None:
        if self._worker is not None:
            self._worker.wait(10000)
        self._running = False
        self.cancel_btn.setEnabled(True)
        self._set_controls_enabled(True)

    def _on_finished(self, result: PrintResult) -> None:
        self._finish_worker()
        self.result = result
        if result.cancelled:
            self.progress_bar.setVisible(False)
            self.status_label.setText(f"Đã dừng in sau {result.sheets_printed}/{result.total_sheets} tờ.")
            if self._close_when_done:
                super().reject()
            return
        self.progress_bar.setValue(100)
        if result.output_path:
            self.result_message = f"💾 Đã lưu bản in {result.sheets_printed} trang: {Path(result.output_path).name}"
        else:
            self.result_message = f"🖨 Đã gửi {result.sheets_printed} tờ tới «{result.printer}»"
        self.status_label.setText(self.result_message)
        self.accept()

    def _on_failed(self, message: str) -> None:
        self._finish_worker()
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"⛔ In thất bại: {message}")
        if self._close_when_done:
            super().reject()
            return
        QMessageBox.critical(self, "In thất bại", message)

    def _on_cancel_clicked(self) -> None:
        if self._running:
            self.request_stop(close_after=False)
        else:
            self.reject()

    def reject(self) -> None:
        if self._running:
            self.request_stop(close_after=True)
            return
        super().reject()
