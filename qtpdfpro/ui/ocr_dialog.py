"""Giao diện «OCR tiếng Việt» (mục B3): tải bộ mô hình ngầm lần đầu + hộp thoại nhận dạng PDF ảnh quét.

- `OcrModelController` (thuộc `MainWindow`, `window.ocr_models`): lần đầu người dùng bấm «OCR tiếng Việt» là bắt
  đầu tải bộ mô hình (~88 MB, `core/ocr_models.install_models`) trong `QThread` — không hỏi, không chặn giao diện;
  đóng hộp thoại vẫn tải tiếp, xong báo thông báo nổi. Thoát ứng dụng giữa chừng thì huỷ và đợi luồng dừng.
- `OcrDialog`: tệp nguồn (mặc định tệp của tab đang đọc), đầu ra PDF tìm kiếm được / Word / văn bản, trang, nơi lưu;
  bấm «Nhận dạng» khi mô hình chưa tải xong thì tự chạy ngay khi tải xong. Phần lõi chạy trong `_OcrWorker`
  (dừng được giữa các trang). Kết quả ở `ocr_result` (`OcrResult`); `MainWindow` hỏi mở tệp kết quả.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import fitz  # PyMuPDF
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core import ocr, ocr_models
from qtpdfpro.core.pdf_io import default_output, format_size, same_file

OUTPUT_KINDS = [
    ("pdf", "PDF tìm kiếm được — giữ nguyên ảnh quét, thêm lớp chữ chọn / chép / tìm được", ".pdf", "Tài liệu PDF (*.pdf)"),
    ("docx", "Word (.docx) — dựng lại văn bản (văn bản hành chính tự theo chuẩn NĐ30)", ".docx", "Tài liệu Word (*.docx)"),
    ("txt", "Văn bản thuần (.txt, UTF-8)", ".txt", "Văn bản (*.txt)"),
]


# ─── Tải bộ mô hình ngầm ───────────────────────────────────────────────────


class _InstallWorker(QThread):
    progress = Signal(int, int)
    failed = Signal(str)

    def __init__(self, should_cancel: Callable[[], bool], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._should_cancel = should_cancel

    def run(self) -> None:
        try:
            ocr_models.install_models(progress_cb=lambda d, t: self.progress.emit(int(d), int(t)),
                                      should_cancel=self._should_cancel)
        except ocr_models.OcrModelCancelled:
            self.failed.emit("")
        except Exception as exc:  # báo về luồng giao diện
            self.failed.emit(str(exc))


class OcrModelController(QObject):
    """Tải + cài bộ mô hình OCR một lần, ở luồng nền; tín hiệu cho hộp thoại và cửa sổ chính."""

    progress = Signal(int, int)  # đã tải, tổng (byte)
    finished = Signal(bool, str)  # thành công?, thông báo lỗi ("" = bị huỷ)

    def __init__(self, parent: QObject | None = None, notify: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(parent)
        self._notify = notify
        self._worker: Optional[_InstallWorker] = None
        self._cancel = False
        self._error = ""
        self.done_bytes = 0
        self.total_bytes = ocr_models.BUNDLE_ASSET.size
        self.last_error = ""

    @property
    def installing(self) -> bool:
        return self._worker is not None

    def is_installed(self) -> bool:
        return ocr_models.is_installed()

    def ensure_started(self) -> bool:
        """True nếu mô hình đã sẵn sàng; chưa có thì bắt đầu tải ngầm (nếu chưa tải) và trả về False."""
        if self.is_installed():
            return True
        if self._worker is None:
            self._cancel = False
            self._error = ""
            self.last_error = ""
            self.done_bytes = 0
            self._worker = _InstallWorker(lambda: self._cancel, self)
            self._worker.progress.connect(self._on_progress)
            self._worker.failed.connect(self._on_failed)
            self._worker.finished.connect(self._on_thread_finished)
            self._worker.start()
        return False

    def cancel_and_wait(self) -> None:
        """Huỷ tải (khi thoát ứng dụng) và đợi luồng dừng."""
        if self._worker is not None:
            self._cancel = True
            self._worker.wait()
            QApplication.processEvents()

    def wait(self) -> None:
        """Đợi tải xong và xử lý tín hiệu (dùng cho kiểm thử)."""
        if self._worker is not None:
            self._worker.wait()
        for _ in range(3):
            QApplication.processEvents()

    def _on_progress(self, done: int, total: int) -> None:
        self.done_bytes, self.total_bytes = done, total or self.total_bytes
        self.progress.emit(done, total)

    def _on_failed(self, message: str) -> None:
        self._error = message  # "" = người dùng / ứng dụng huỷ

    def _on_thread_finished(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        ok = self.is_installed()
        message = "" if ok else self._error
        self.last_error = message
        if self._notify is not None and (ok or message):
            self._notify("✅ Đã cài bộ mô hình OCR tiếng Việt — sẵn sàng nhận dạng."
                         if ok else f"⚠️ Chưa tải được bộ mô hình OCR: {message}")
        self.finished.emit(ok, message)


# ─── Nhận dạng ─────────────────────────────────────────────────────────────


class _OcrWorker(QThread):
    progress = Signal(int, int, str)
    done = Signal(object)  # OcrResult
    failed = Signal(object)  # Exception

    def __init__(self, job: Callable[..., ocr.OcrResult], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.job = job
        self.cancel = False

    def run(self) -> None:
        try:
            self.done.emit(self.job(progress_cb=lambda d, t, m: self.progress.emit(d, t, m),
                                    should_cancel=lambda: self.cancel))
        except Exception as exc:  # báo về luồng giao diện
            self.failed.emit(exc)


class OcrDialog(QDialog):
    TOOL_TITLE = "OCR tiếng Việt"

    def __init__(
        self,
        parent: QWidget | None = None,
        source: Optional[str | Path] = None,
        password: Optional[str] = None,
        models: Optional[OcrModelController] = None,
        is_locked: Optional[Callable[[Path], bool]] = None,
        engine_factory: Optional[Callable[[], ocr.OcrEngine]] = None,
    ) -> None:
        super().__init__(parent)
        self.models = models or OcrModelController(self)
        self._is_locked = is_locked or (lambda _p: False)
        self._engine_factory = engine_factory  # bài test thay bộ máy giả
        self.source_path: Optional[Path] = None
        self.source_password: Optional[str] = None
        self.source_pages = 0
        self.ocr_result: Optional[ocr.OcrResult] = None
        self._worker: Optional[_OcrWorker] = None
        self._error: Optional[Exception] = None
        self._pending_start = False

        self.setWindowTitle(f"{self.TOOL_TITLE} — nhận dạng chữ PDF ảnh quét")
        self.setMinimumWidth(640)
        root = QVBoxLayout(self)
        root.setSpacing(10)

        src_box = QGroupBox("Tệp PDF ảnh quét")
        src_lay = QHBoxLayout(src_box)
        self.source_label = QLabel("Chưa chọn tệp")
        self.source_label.setWordWrap(True)
        btn_src = QPushButton("Chọn tệp…")
        btn_src.clicked.connect(self.browse_source)
        src_lay.addWidget(self.source_label, 1)
        src_lay.addWidget(btn_src)
        root.addWidget(src_box)

        out_box = QGroupBox("Kết quả")
        out_lay = QVBoxLayout(out_box)
        self.kind_group = QButtonGroup(self)
        self.kind_buttons: dict[str, QRadioButton] = {}
        for i, (key, label, _ext, _flt) in enumerate(OUTPUT_KINDS):
            btn = QRadioButton(label)
            self.kind_group.addButton(btn, i)
            self.kind_buttons[key] = btn
            out_lay.addWidget(btn)
        self.kind_buttons["pdf"].setChecked(True)
        self.kind_group.idToggled.connect(self._on_kind_changed)
        form = QFormLayout()
        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText("Tất cả trang — ví dụ: 1-3,5")
        form.addRow("Trang:", self.pages_edit)
        out_lay.addLayout(form)
        self.skip_text_check = QCheckBox("Bỏ qua trang đã có lớp chữ (PDF gõ máy)")
        self.skip_text_check.setChecked(True)
        self.clean_check = QCheckBox("Bỏ nét con dấu đỏ / chữ ký xanh khi nhận dạng")
        self.clean_check.setChecked(True)
        out_lay.addWidget(self.skip_text_check)
        out_lay.addWidget(self.clean_check)
        root.addWidget(out_box)

        save_box = QGroupBox("Lưu thành")
        save_lay = QHBoxLayout(save_box)
        self.out_edit = QLineEdit()
        btn_out = QPushButton("Chọn nơi lưu…")
        btn_out.clicked.connect(self.browse_output)
        save_lay.addWidget(self.out_edit, 1)
        save_lay.addWidget(btn_out)
        root.addWidget(save_box)

        self.model_label = QLabel("")
        self.model_label.setWordWrap(True)
        self.model_label.setObjectName("hintLabel")
        self.model_progress = QProgressBar()
        self.model_progress.setRange(0, 100)
        root.addWidget(self.model_label)
        root.addWidget(self.model_progress)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.run_btn = QPushButton("Nhận dạng")
        self.run_btn.setObjectName("primaryBtn")
        self.run_btn.setDefault(True)
        self.run_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("Dừng")
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self.stop)
        self.close_btn = QPushButton("Đóng")
        self.close_btn.clicked.connect(self.reject)
        for b in (self.run_btn, self.stop_btn, self.close_btn):
            btns.addWidget(b)
        root.addLayout(btns)

        self.models.progress.connect(self._on_model_progress)
        self.models.finished.connect(self._on_models_finished)
        self.models.ensure_started()
        self._refresh_model_state()
        if source:
            self.set_source(source, password)

    # ─── Bộ mô hình ────────────────────────────────────────────────────────

    def _refresh_model_state(self) -> None:
        if self.models.is_installed():
            self.model_label.setText("✅ Bộ mô hình OCR tiếng Việt đã sẵn sàng (chạy trên máy, không gửi tài liệu đi đâu).")
            self.model_progress.setVisible(False)
        elif self.models.installing:
            total = self.models.total_bytes or ocr_models.BUNDLE_ASSET.size
            done = self.models.done_bytes
            self.model_label.setText(
                f"⏬ Đang tải bộ mô hình OCR tiếng Việt ({format_size(total)}, chỉ lần đầu): "
                f"{format_size(done)} / {format_size(total)}. Có thể bấm «Nhận dạng» — sẽ chạy ngay khi tải xong."
            )
            self.model_progress.setVisible(True)
            self.model_progress.setValue(int(done * 100 / total) if total else 0)
        else:
            err = self.models.last_error
            self.model_label.setText(
                f"⚠️ Chưa tải được bộ mô hình OCR: {err} Bấm «Nhận dạng» để thử tải lại."
                if err else "Bộ mô hình OCR chưa được cài — sẽ tự tải khi bấm «Nhận dạng»."
            )
            self.model_progress.setVisible(False)

    def _on_model_progress(self, _done: int, _total: int) -> None:
        self._refresh_model_state()

    def _on_models_finished(self, ok: bool, message: str) -> None:
        self._refresh_model_state()
        if self._pending_start:
            self._pending_start = False
            if ok:
                self.start()
            else:
                self.run_btn.setEnabled(True)
                self.status_label.setText("")
                if message:
                    QMessageBox.warning(self, self.TOOL_TITLE, f"Chưa tải được bộ mô hình OCR:\n{message}")

    # ─── Tệp nguồn & nơi lưu ───────────────────────────────────────────────

    @property
    def kind(self) -> str:
        return OUTPUT_KINDS[max(0, self.kind_group.checkedId())][0]

    def _ext(self) -> str:
        return next(ext for key, _l, ext, _f in OUTPUT_KINDS if key == self.kind)

    def _on_kind_changed(self, _id: int, checked: bool) -> None:
        if not checked:
            return
        self.skip_text_check.setEnabled(self.kind == "pdf")
        text = self.out_edit.text().strip()
        if text:
            self.out_edit.setText(str(Path(text).with_suffix(self._ext())))

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
                    text = message or f"Tệp «{p.name}» được bảo vệ bằng mật khẩu. Nhập mật khẩu:"
                    password, ok = QInputDialog.getText(self, "Tệp PDF có mật khẩu", text, QLineEdit.EchoMode.Password)
                    if not ok or not password:
                        return False
                    message = f"Sai mật khẩu của «{p.name}». Nhập lại:"
            self.source_pages = doc.page_count
            scanned = sum(1 for page in doc if ocr.page_text_chars(page) < ocr.TEXT_PAGE_CHARS)
        finally:
            doc.close()
        self.source_path = p
        self.source_password = password
        bits = [f"<b>{p.name}</b>", f"{self.source_pages} trang", format_size(p.stat().st_size)]
        bits.append(f"{scanned} trang ảnh quét" if scanned else "các trang đều đã có lớp chữ")
        self.source_label.setText(" · ".join(bits))
        self.source_label.setToolTip(str(p))
        self.out_edit.setText(str(default_output(p, "_ocr").with_suffix(self._ext())))
        self.status_label.setText("")
        return True

    def browse_source(self) -> None:
        start = str(self.source_path.parent) if self.source_path else ""
        chosen, _ = QFileDialog.getOpenFileName(self, "Chọn tệp PDF ảnh quét", start, "Tài liệu PDF (*.pdf)")
        if chosen:
            self.set_source(chosen)

    def browse_output(self) -> None:
        flt = next(f for key, _l, _e, f in OUTPUT_KINDS if key == self.kind)
        chosen, _ = QFileDialog.getSaveFileName(self, "Lưu kết quả nhận dạng", self.out_edit.text().strip(), flt)
        if chosen:
            self.out_edit.setText(chosen)

    def output_path(self) -> Optional[Path]:
        text = self.out_edit.text().strip().strip('"')
        if not text:
            return None
        out = Path(text)
        if out.suffix.lower() != self._ext():
            out = out.with_name(out.name + self._ext())
        return out.resolve()

    # ─── Chạy ──────────────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._worker is not None

    def start(self) -> None:
        if self.running:
            return
        if self.source_path is None:
            QMessageBox.warning(self, self.TOOL_TITLE, "Hãy chọn tệp PDF ảnh quét.")
            return
        out = self.output_path()
        if out is None:
            QMessageBox.warning(self, self.TOOL_TITLE, "Hãy chọn nơi lưu kết quả.")
            return
        if same_file(out, self.source_path):
            QMessageBox.warning(self, self.TOOL_TITLE, "Tệp kết quả trùng tệp nguồn — hãy chọn tên khác.")
            return
        if self._is_locked(out):
            QMessageBox.warning(self, "Tệp đang mở", f"«{out.name}» đang mở ở một tab — hãy đóng tab đó hoặc chọn tên khác.")
            return
        if self._engine_factory is None and not self.models.ensure_started():
            self._pending_start = True
            self.run_btn.setEnabled(False)
            self.status_label.setText("Sẽ bắt đầu nhận dạng ngay khi tải xong bộ mô hình…")
            self._refresh_model_state()
            return
        self._launch(out)

    def _launch(self, out: Path) -> None:
        src, pwd, kind = self.source_path, self.source_password, self.kind
        pages, skip, clean = self.pages_edit.text().strip(), self.skip_text_check.isChecked(), self.clean_check.isChecked()
        factory = self._engine_factory

        def job(progress_cb, should_cancel) -> ocr.OcrResult:
            engine = factory() if factory else ocr.OcrEngine.load()
            common = dict(pages=pages, password=pwd, engine=engine, progress_cb=progress_cb, should_cancel=should_cancel)
            if kind == "docx":
                return ocr.ocr_to_docx(src, out, **common)
            if kind == "txt":
                return ocr.ocr_to_text(src, out, **common)
            return ocr.ocr_pdf(src, out, skip_text_pages=skip, clean_ink=clean, **common)

        self.ocr_result = None
        self._error = None
        self.run_btn.setEnabled(False)
        self.stop_btn.setVisible(True)
        self.stop_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status_label.setText("Đang nạp bộ mô hình OCR…")
        self._worker = _OcrWorker(job, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_thread_finished)
        self._worker.start()

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel = True
            self.stop_btn.setEnabled(False)
            self.status_label.setText("Đang dừng sau trang hiện tại…")

    def _on_progress(self, done: int, total: int, message: str) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.status_label.setText(message)

    def _on_done(self, res: ocr.OcrResult) -> None:
        self.ocr_result = res

    def _on_failed(self, exc: Exception) -> None:
        self._error = exc

    def _on_thread_finished(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.wait()
        self.run_btn.setEnabled(True)
        self.stop_btn.setVisible(False)
        self.progress.setVisible(False)
        err, res = self._error, self.ocr_result
        if isinstance(err, ocr.OcrCancelled):
            self.status_label.setText("Đã dừng nhận dạng.")
            return
        if err is not None:
            self.status_label.setText("")
            QMessageBox.warning(self, f"Không nhận dạng được — {self.TOOL_TITLE}", str(err))
            return
        if res is None:
            return
        self.status_label.setText(self.result_summary())
        self.accept()

    def result_summary(self) -> str:
        res = self.ocr_result
        if res is None:
            return ""
        text = f"Đã nhận dạng {res.pages_ocr}/{res.pages_total} trang — {res.lines} dòng, {res.chars} ký tự ({res.seconds:.0f} giây)."
        if res.pages_skipped:
            text += f" Bỏ qua {res.pages_skipped} trang đã có lớp chữ."
        return f"{text}\n{res.note}" if res.note else text

    def wait_finished(self) -> None:
        """Đợi luồng nhận dạng xong và xử lý kết quả (dùng cho kiểm thử)."""
        if self._worker is not None:
            self._worker.wait()
        for _ in range(3):
            QApplication.processEvents()

    def reject(self) -> None:
        if self.running:
            return  # đợi xử lý xong (hoặc bấm «Dừng»), không huỷ QThread đang chạy
        self._pending_start = False
        super().reject()

    def done(self, result: int) -> None:  # noqa: D401 - API Qt
        # bộ tải mô hình sống cùng cửa sổ chính: ngắt tín hiệu để hộp thoại đã đóng không nhận nữa
        for signal, slot in ((self.models.progress, self._on_model_progress),
                             (self.models.finished, self._on_models_finished)):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        super().done(result)
