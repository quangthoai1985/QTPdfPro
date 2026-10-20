"""Hộp thoại báo cáo đối chiếu thể thức Nghị định 30/2020/NĐ-CP và kiểm chứng bố cục DOCX."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core.layout_verify import LayoutVerifyReport, verify_docx_layout
from qtpdfpro.core.nd30_engine import analyze_pdf_nd30
from qtpdfpro.core.nd30_standard import DocxLayoutPlan, ND30Report, build_docx_plan

_STATUS = {
    "ok": ("✔ Đạt", "#16A34A"),
    "warn": ("! Cần xem lại", "#D97706"),
    "fail": ("✘ Chưa đạt", "#DC2626"),
    "na": ("– Không áp dụng", "#64748B"),
}


class _AnalyzeWorker(QThread):
    done = Signal(object, object)
    failed = Signal(str)

    def __init__(self, pdf_path: Path, password: Optional[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.password = password

    def run(self) -> None:
        try:
            ad, rep = analyze_pdf_nd30(self.pdf_path, password=self.password)
            self.done.emit(rep, build_docx_plan(ad, "faithful"))
        except Exception as exc:  # pragma: no cover - lỗi hiển thị cho người dùng
            self.failed.emit(str(exc))


class ND30ReportDialog(QDialog):
    """Hiển thị bảng đối chiếu thể thức NĐ30 của một tệp PDF."""

    convertRequested = Signal()

    def __init__(self, pdf_path: str | Path, password: Optional[str] = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pdf_path = Path(pdf_path)
        self.report: Optional[ND30Report] = None
        self.plan: Optional[DocxLayoutPlan] = None
        self.setWindowTitle(f"Kiểm tra thể thức NĐ30 — {self.pdf_path.name}")
        self.resize(900, 640)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        self.header_lbl = QLabel("Đang đo lề, cỡ chữ, khoảng cách dòng/đoạn và nhận diện các thành phần thể thức…")
        self.header_lbl.setObjectName("dialogHeadline")
        self.header_lbl.setWordWrap(True)
        lay.addWidget(self.header_lbl)

        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        lay.addWidget(self.busy)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Thành phần thể thức", "Đo được trên PDF", "Quy định NĐ30", "Kết quả"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.table, 1)

        self.plan_lbl = QLabel("")
        self.plan_lbl.setWordWrap(True)
        self.plan_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.plan_lbl)

        btns = QHBoxLayout()
        self.copy_btn = QPushButton("Sao chép báo cáo")
        self.copy_btn.clicked.connect(self._copy)
        self.convert_btn = QPushButton("📄 Chuyển sang Word chuẩn NĐ30…")
        self.convert_btn.setObjectName("primaryConvertBtn")
        self.convert_btn.setEnabled(False)
        self.convert_btn.clicked.connect(self._on_convert)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.reject)
        btns.addWidget(self.copy_btn)
        btns.addStretch(1)
        btns.addWidget(self.convert_btn)
        btns.addWidget(close_btn)
        lay.addLayout(btns)

        self._worker = _AnalyzeWorker(self.pdf_path, password, self)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, report: ND30Report, plan: DocxLayoutPlan) -> None:
        self.report, self.plan = report, plan
        self.busy.hide()
        kind = "Văn bản hành chính" if report.is_admin_document else "Không nhận ra phần đầu văn bản hành chính"
        color = "#16A34A" if report.score >= 90 else ("#D97706" if report.score >= 70 else "#DC2626")
        self.header_lbl.setText(
            f"<b>{kind}</b> — Điểm thể thức: <span style='color:{color};font-size:16px;'><b>{report.score:.1f}%</b></span> "
            f"({report.ok_count} đạt · {report.warn_count} cần xem lại · {report.fail_count} chưa đạt)"
        )
        self.table.setRowCount(len(report.checks))
        for r, c in enumerate(report.checks):
            label, hex_color = _STATUS.get(c.status, ("?", "#64748B"))
            measured = c.measured + (f"\n{c.note}" if c.note else "")
            for col, txt in enumerate((c.name, measured, c.expected, label)):
                item = QTableWidgetItem(txt)
                if col == 3:
                    item.setForeground(QColor(hex_color))
                self.table.setItem(r, col, item)
        self.table.resizeRowsToContents()
        spacing = (
            f"giãn dòng {plan.line_multiple:g} lines".replace(".", ",")
            if plan.line_exact_pt is None
            else f"giãn dòng Exactly {plan.line_exact_pt:g} pt".replace(".", ",")
        )
        self.plan_lbl.setText(
            "<b>Thông số Word ước lượng (giữ đúng bố cục PDF):</b> "
            f"lề trên {plan.margin_top_mm:g} mm · dưới {plan.margin_bottom_mm:g} mm · trái {plan.margin_left_mm:g} mm · "
            f"phải {plan.margin_right_mm:g} mm · cỡ chữ {plan.body_size:g} pt · {spacing} · cách đoạn "
            f"{plan.para_spacing_pt:g} pt · thụt đầu dòng {plan.first_indent_mm:g} mm."
            + ("<br/>" + "<br/>".join(plan.notes) if plan.notes else "")
        )
        self.convert_btn.setEnabled(True)

    def _on_failed(self, msg: str) -> None:
        self.busy.hide()
        self.header_lbl.setText(f"<b>Không phân tích được tệp:</b> {msg}")

    def _on_convert(self) -> None:
        self.convertRequested.emit()
        self.accept()

    def _copy(self) -> None:
        if self.report is None:
            return
        lines = [f"Đối chiếu thể thức NĐ30 — {self.pdf_path.name}: {self.report.score:.1f}%"]
        for c in self.report.checks:
            lines.append(f"[{_STATUS.get(c.status, ('?',))[0]}] {c.name}: {c.measured} | Quy định: {c.expected} {c.note}".rstrip())
        QGuiApplication.clipboard().setText("\n".join(lines))


class _VerifyWorker(QThread):
    done = Signal(object)

    def __init__(self, pdf_path: Path, docx_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pdf_path, self.docx_path = pdf_path, docx_path

    def run(self) -> None:
        self.done.emit(verify_docx_layout(self.pdf_path, self.docx_path))


class LayoutVerifyDialog(QDialog):
    """Dựng DOCX bằng Microsoft Word và so vị trí từng dòng với PDF gốc."""

    def __init__(self, pdf_path: str | Path, docx_path: str | Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pdf_path, self.docx_path = Path(pdf_path), Path(docx_path)
        self.result: Optional[LayoutVerifyReport] = None
        self.setWindowTitle(f"Kiểm chứng DOCX với PDF — {self.docx_path.name}")
        self.resize(720, 360)
        lay = QVBoxLayout(self)
        self.lbl = QLabel(
            f"Đang mở <b>{self.docx_path.name}</b> bằng Microsoft Word, xuất lại PDF và so từng dòng với "
            f"<b>{self.pdf_path.name}</b>…"
        )
        self.lbl.setWordWrap(True)
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        lay.addWidget(self.lbl, 1)
        lay.addWidget(self.busy)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        lay.addLayout(row)
        self._worker = _VerifyWorker(self.pdf_path, self.docx_path, self)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, rep: LayoutVerifyReport) -> None:
        self.result = rep
        self.busy.hide()
        self.lbl.setText(layout_check_html(rep))

    def closeEvent(self, event) -> None:  # noqa: N802 - API Qt
        if self._worker.isRunning():
            self._worker.wait(200)
        super().closeEvent(event)


def layout_check_html(rep: LayoutVerifyReport) -> str:
    """Định dạng kết quả kiểm chứng bố cục thành HTML ngắn gọn."""
    if not rep.available:
        return f"<b>Kiểm chứng bằng Microsoft Word:</b> {rep.verdict_text}. {rep.note}"
    color = {"match": "#16A34A", "minor": "#D97706"}.get(rep.verdict, "#DC2626")
    samples = "".join(f"<li>{s}</li>" for s in rep.samples[:6])
    return (
        f"<b>Kiểm chứng bằng Microsoft Word:</b> <span style='color:{color};'><b>{rep.verdict_text}</b></span> "
        f"(điểm bố cục {rep.score:.1f})<br/>"
        f"• Số trang: PDF {rep.pdf_pages} → Word {rep.docx_pages}<br/>"
        f"• Dòng khớp nội dung: {rep.matched_lines}/{rep.pdf_lines}; dòng bị đẩy sang trang khác: {rep.moved_page_lines}<br/>"
        f"• Lệch vị trí: dọc tối đa {rep.max_dy_pt:.2f} pt (TB {rep.mean_dy_pt:.2f}), "
        f"ngang tối đa {rep.max_dx_pt:.2f} pt (TB {rep.mean_dx_pt:.2f}) — 1 pt ≈ 0,35 mm"
        + (f"<ul>{samples}</ul>" if samples else "")
    )
