"""Các hộp thoại phụ trợ bằng tiếng Việt của QT PDF Pro."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro import __app_name__, __author__, __github_repo__, __version__
from qtpdfpro.core.reader import DocumentInfo


def vi_buttons(box: QDialogButtonBox | QMessageBox) -> None:
    """Đổi nhãn nút chuẩn của Qt sang tiếng Việt."""
    mapping = {
        QDialogButtonBox.StandardButton.Ok: "Đồng ý",
        QDialogButtonBox.StandardButton.Cancel: "Huỷ",
        QDialogButtonBox.StandardButton.Close: "Đóng",
        QDialogButtonBox.StandardButton.Yes: "Có",
        QDialogButtonBox.StandardButton.No: "Không",
        QDialogButtonBox.StandardButton.Save: "Lưu",
    }
    for std_btn, label in mapping.items():
        btn = box.button(std_btn)  # type: ignore[arg-type]
        if btn is not None:
            btn.setText(label)


class DocumentInfoDialog(QDialog):
    """Hộp thoại hiển thị thông tin chi tiết (Metadata) của tệp PDF."""

    def __init__(self, info: DocumentInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Thông tin tài liệu — {info.file_name}")
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        size_kb = info.file_size_bytes / 1024.0
        size_str = (
            f"{size_kb / 1024.0:.2f} MB ({info.file_size_bytes:,} bytes)"
            if size_kb >= 1024
            else f"{size_kb:.1f} KB ({info.file_size_bytes:,} bytes)"
        )

        rows = [
            ("Tên tệp:", info.file_name),
            ("Đường dẫn:", info.file_path),
            ("Dung lượng:", size_str),
            ("Số trang:", f"{info.page_count} trang"),
            ("Định dạng:", info.pdf_version or "PDF"),
            ("Tiêu đề:", info.title or "(Không có)"),
            ("Tác giả:", info.author or "(Không có)"),
            ("Chủ đề:", info.subject or "(Không có)"),
            ("Ứng dụng tạo:", info.creator or "(Không có)"),
            ("Bộ kết xuất:", info.producer or "(Không có)"),
            ("Ngày tạo:", info.creation_date or "(Không có)"),
        ]
        self._summary_lines = [f"{k} {v}" for k, v in rows]

        for label_txt, val_txt in rows:
            val_label = QLabel(val_txt)
            val_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val_label.setWordWrap(True)
            form.addRow(QLabel(f"<b>{label_txt}</b>"), val_label)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Sao chép thông tin")
        copy_btn.clicked.connect(self._copy_info)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(copy_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _copy_info(self) -> None:
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText("\n".join(self._summary_lines))


class PageTextDialog(QDialog):
    """Hộp thoại xem và sao chép văn bản trích xuất từ trang PDF."""

    def __init__(self, title: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(680, 500)

        layout = QVBoxLayout(self)
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(text)
        self.editor.setReadOnly(False)
        layout.addWidget(self.editor, 1)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Sao chép toàn bộ")
        copy_btn.clicked.connect(self._copy_all)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(copy_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _copy_all(self) -> None:
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(self.editor.toPlainText())


class AboutDialog(QDialog):
    """Hộp thoại Giới thiệu ứng dụng QT PDF Pro."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Giới thiệu {__app_name__}")
        self.resize(480, 300)

        layout = QVBoxLayout(self)
        html = (
            f"<h2>{__app_name__} v{__version__}</h2>"
            "<p><b>Ứng dụng chuyên đọc PDF &amp; chuyển đổi PDF sang Word (.docx) chuẩn xác.</b></p>"
            "<ul>"
            "<li><b>Trình đọc PDF tốc độ cao</b>: Kết xuất sắc nét bằng PyMuPDF, tìm kiếm toàn văn, "
            "cây mục lục, soi khung bố cục trực tiếp trên trang.</li>"
            "<li><b>Chuyển đổi PDF sang DOCX đa chế độ</b>: Tái tạo cấu trúc thông minh (Hybrid Flow), "
            "Giữ nguyên vị trí tuyệt đối 1:1 (Exact Frame), và cầu nối MS Word Reflow, kèm Bộ Hậu xử lý "
            "Chuẩn xác OpenXML &amp; chuẩn hoá tiếng Việt.</li>"
            "</ul>"
            f"<p>Tác giả: <b>{__author__}</b><br/>"
            f"Giấy phép: <b>MIT License</b><br/>"
            f"Kho mã nguồn: <code>https://github.com/{__github_repo__}</code></p>"
        )
        lbl = QLabel(html)
        lbl.setWordWrap(True)
        lbl.setOpenExternalLinks(True)
        layout.addWidget(lbl, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        vi_buttons(btn_box)
        btn_box.rejected.connect(self.reject)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)
