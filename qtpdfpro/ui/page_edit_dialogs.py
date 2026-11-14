"""Các hộp thoại chuyên dụng cho chế độ «Chỉnh sửa» mở rộng: Đầu trang & Chân trang, Đánh số Bates,
Nền trang, Cắt lề trang theo thông số và Chèn liên kết.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core.page_edit import MM
from qtpdfpro.core.page_stamp import POSITIONS


def _color_btn_style(hex_color: str) -> str:
    return f"background-color: {hex_color}; border: 1px solid #94A3B8; border-radius: 4px; min-width: 60px; min-height: 24px;"


class HeaderFooterDialog(QDialog):
    """Hộp thoại thêm Đầu trang && Chân trang trực tiếp vào tài liệu PDF."""

    def __init__(self, page_count: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Đầu trang && Chân trang")
        self.setMinimumWidth(520)
        self._color = "#111827"

        root = QVBoxLayout(self)
        hint = QLabel(
            "Có thể dùng từ khoá tự động: <b>{page}</b> (số trang), <b>{total}</b> (tổng số trang), "
            "<b>{date}</b> (ngày hôm nay)."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        hdr_grp = QGroupBox("Đầu trang (Header)")
        hg = QGridLayout(hdr_grp)
        self.ed_hl = QLineEdit()
        self.ed_hc = QLineEdit()
        self.ed_hr = QLineEdit()
        self.ed_hl.setPlaceholderText("Trái (vd: Tên tài liệu)")
        self.ed_hc.setPlaceholderText("Giữa")
        self.ed_hr.setPlaceholderText("Phải (vd: {date})")
        hg.addWidget(QLabel("Trái"), 0, 0)
        hg.addWidget(QLabel("Giữa"), 0, 1)
        hg.addWidget(QLabel("Phải"), 0, 2)
        hg.addWidget(self.ed_hl, 1, 0)
        hg.addWidget(self.ed_hc, 1, 1)
        hg.addWidget(self.ed_hr, 1, 2)
        root.addWidget(hdr_grp)

        ftr_grp = QGroupBox("Chân trang (Footer)")
        fg = QGridLayout(ftr_grp)
        self.ed_fl = QLineEdit()
        self.ed_fc = QLineEdit("Trang {page} / {total}")
        self.ed_fr = QLineEdit()
        self.ed_fl.setPlaceholderText("Trái")
        self.ed_fc.setPlaceholderText("Giữa (vd: Trang {page} / {total})")
        self.ed_fr.setPlaceholderText("Phải")
        fg.addWidget(QLabel("Trái"), 0, 0)
        fg.addWidget(QLabel("Giữa"), 0, 1)
        fg.addWidget(QLabel("Phải"), 0, 2)
        fg.addWidget(self.ed_fl, 1, 0)
        fg.addWidget(self.ed_fc, 1, 1)
        fg.addWidget(self.ed_fr, 1, 2)
        root.addWidget(ftr_grp)

        form = QFormLayout()
        self.spin_size = QDoubleSpinBox()
        self.spin_size.setRange(6.0, 36.0)
        self.spin_size.setValue(10.0)
        self.spin_size.setSuffix(" pt")

        self.combo_font = QComboBox()
        self.combo_font.addItem("Times New Roman", "serif")
        self.combo_font.addItem("Arial", "sans")
        self.combo_font.addItem("Courier New", "mono")

        self.btn_color = QPushButton(self._color)
        self.btn_color.setStyleSheet(_color_btn_style(self._color))
        self.btn_color.clicked.connect(self._pick_color)

        self.spin_margin = QDoubleSpinBox()
        self.spin_margin.setRange(4.0, 50.0)
        self.spin_margin.setValue(12.0)
        self.spin_margin.setSuffix(" mm")

        self.chk_skip_first = QCheckBox("Bỏ qua trang đầu (trang bìa)")
        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText(f"Tất cả (1-{page_count}), vd: 1-3,5")

        form.addRow("Phông chữ:", self.combo_font)
        form.addRow("Cỡ chữ:", self.spin_size)
        form.addRow("Màu chữ:", self.btn_color)
        form.addRow("Cách mép trên/dưới:", self.spin_margin)
        form.addRow("Phạm vi trang:", self.ed_pages)
        form.addRow("", self.chk_skip_first)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Áp dụng")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Chọn màu chữ")
        if c.isValid():
            self._color = c.name().upper()
            self.btn_color.setText(self._color)
            self.btn_color.setStyleSheet(_color_btn_style(self._color))

    def values(self) -> dict:
        return {
            "header_left": self.ed_hl.text(),
            "header_center": self.ed_hc.text(),
            "header_right": self.ed_hr.text(),
            "footer_left": self.ed_fl.text(),
            "footer_center": self.ed_fc.text(),
            "footer_right": self.ed_fr.text(),
            "font_size": float(self.spin_size.value()),
            "font_family": str(self.combo_font.currentData()),
            "color": self._color,
            "margin_mm": float(self.spin_margin.value()),
            "skip_first": bool(self.chk_skip_first.isChecked()),
            "pages_spec": self.ed_pages.text().strip(),
        }


class BatesDialog(QDialog):
    """Hộp thoại đánh số Bates (Bates Numbering)."""

    def __init__(self, page_count: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Đánh số Bates")
        self.setMinimumWidth(400)
        self._color = "#111827"

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.ed_prefix = QLineEdit("BATES-")
        self.ed_suffix = QLineEdit()
        self.spin_start = QSpinBox()
        self.spin_start.setRange(0, 9999999)
        self.spin_start.setValue(1)
        self.spin_digits = QSpinBox()
        self.spin_digits.setRange(1, 10)
        self.spin_digits.setValue(6)

        self.combo_pos = QComboBox()
        for key, label in POSITIONS:
            self.combo_pos.addItem(label, key)
        self.combo_pos.setCurrentIndex(max(0, self.combo_pos.findData("top-right")))

        self.spin_size = QDoubleSpinBox()
        self.spin_size.setRange(6.0, 28.0)
        self.spin_size.setValue(10.0)
        self.spin_size.setSuffix(" pt")

        self.btn_color = QPushButton(self._color)
        self.btn_color.setStyleSheet(_color_btn_style(self._color))
        self.btn_color.clicked.connect(self._pick_color)

        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText(f"Tất cả (1-{page_count})")

        self.lbl_preview = QLabel()
        for w in (self.ed_prefix, self.ed_suffix):
            w.textChanged.connect(self._update_preview)
        self.spin_start.valueChanged.connect(self._update_preview)
        self.spin_digits.valueChanged.connect(self._update_preview)

        form.addRow("Tiền tố:", self.ed_prefix)
        form.addRow("Hậu tố:", self.ed_suffix)
        form.addRow("Số bắt đầu:", self.spin_start)
        form.addRow("Số chữ số:", self.spin_digits)
        form.addRow("Vị trí đặt:", self.combo_pos)
        form.addRow("Cỡ chữ:", self.spin_size)
        form.addRow("Màu chữ:", self.btn_color)
        form.addRow("Phạm vi trang:", self.ed_pages)
        form.addRow("Xem trước:", self.lbl_preview)
        root.addLayout(form)
        self._update_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Áp dụng")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Chọn màu số Bates")
        if c.isValid():
            self._color = c.name().upper()
            self.btn_color.setText(self._color)
            self.btn_color.setStyleSheet(_color_btn_style(self._color))

    def _update_preview(self) -> None:
        d = self.spin_digits.value()
        s = self.spin_start.value()
        self.lbl_preview.setText(f"<b>{self.ed_prefix.text()}{s:0{d}d}{self.ed_suffix.text()}</b>")

    def values(self) -> dict:
        return {
            "prefix": self.ed_prefix.text(),
            "suffix": self.ed_suffix.text(),
            "start": int(self.spin_start.value()),
            "digits": int(self.spin_digits.value()),
            "position": str(self.combo_pos.currentData()),
            "font_size": float(self.spin_size.value()),
            "color": self._color,
            "pages_spec": self.ed_pages.text().strip(),
        }


class PageBackgroundDialog(QDialog):
    """Hộp thoại thêm màu nền hoặc ảnh nền phía sau nội dung trang."""

    def __init__(self, page_count: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nền trang PDF")
        self.setMinimumWidth(420)
        self._color = "#FEF9C3"
        self._image_bytes: Optional[bytes] = None

        root = QVBoxLayout(self)
        self.rad_color = QRadioButton("Dùng màu nền:")
        self.rad_color.setChecked(True)
        self.rad_image = QRadioButton("Dùng tệp ảnh làm nền:")

        color_row = QHBoxLayout()
        self.btn_color = QPushButton(self._color)
        self.btn_color.setStyleSheet(_color_btn_style(self._color))
        self.btn_color.clicked.connect(self._pick_color)
        color_row.addWidget(self.rad_color)
        color_row.addWidget(self.btn_color)
        color_row.addStretch(1)
        root.addLayout(color_row)

        img_row = QHBoxLayout()
        self.ed_img = QLineEdit()
        self.ed_img.setPlaceholderText("Chọn ảnh PNG / JPG…")
        self.ed_img.setReadOnly(True)
        self.btn_browse = QPushButton("Chọn ảnh…")
        self.btn_browse.clicked.connect(self._pick_image)
        img_row.addWidget(self.rad_image)
        img_row.addWidget(self.ed_img, 1)
        img_row.addWidget(self.btn_browse)
        root.addLayout(img_row)

        form = QFormLayout()
        self.slider_op = QSlider(Qt.Orientation.Horizontal)
        self.slider_op.setRange(10, 100)
        self.slider_op.setValue(35)
        self.lbl_op = QLabel("35%")
        self.slider_op.valueChanged.connect(lambda v: self.lbl_op.setText(f"{v}%"))
        op_row = QHBoxLayout()
        op_row.addWidget(self.slider_op, 1)
        op_row.addWidget(self.lbl_op)

        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText(f"Tất cả (1-{page_count})")
        form.addRow("Độ đậm nền:", op_row)
        form.addRow("Phạm vi trang:", self.ed_pages)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Áp dụng")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _pick_color(self) -> None:
        self.rad_color.setChecked(True)
        c = QColorDialog.getColor(QColor(self._color), self, "Chọn màu nền")
        if c.isValid():
            self._color = c.name().upper()
            self.btn_color.setText(self._color)
            self.btn_color.setStyleSheet(_color_btn_style(self._color))

    def _pick_image(self) -> None:
        self.rad_image.setChecked(True)
        path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh nền", "", "Hình ảnh (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self.ed_img.setText(path)
            self._image_bytes = Path(path).read_bytes()

    def values(self) -> dict:
        use_img = self.rad_image.isChecked() and self._image_bytes is not None
        return {
            "color": None if use_img else self._color,
            "image_bytes": self._image_bytes if use_img else None,
            "opacity": float(self.slider_op.value()) / 100.0,
            "pages_spec": self.ed_pages.text().strip(),
        }


class CropMarginsDialog(QDialog):
    """Hộp thoại cắt lề trang theo 4 cạnh (mm) hoặc khôi phục khổ gốc."""

    def __init__(self, page_w_pt: float, page_h_pt: float, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cắt lề trang")
        self.setMinimumWidth(340)
        self._reset_requested = False

        root = QVBoxLayout(self)
        info = QLabel(
            f"Kích thước hiện tại: <b>{page_w_pt:.0f} × {page_h_pt:.0f} pt</b> "
            f"({page_w_pt / MM:.1f} × {page_h_pt / MM:.1f} mm)"
        )
        root.addWidget(info)

        form = QFormLayout()
        self.spin_top = self._mm_spin()
        self.spin_bottom = self._mm_spin()
        self.spin_left = self._mm_spin()
        self.spin_right = self._mm_spin()
        form.addRow("Cắt mép trên:", self.spin_top)
        form.addRow("Cắt mép dưới:", self.spin_bottom)
        form.addRow("Cắt mép trái:", self.spin_left)
        form.addRow("Cắt mép phải:", self.spin_right)
        root.addLayout(form)

        btn_reset = QPushButton("Khôi phục khổ trang gốc (MediaBox)")
        btn_reset.clicked.connect(self._on_reset)
        root.addWidget(btn_reset)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Cắt trang")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _mm_spin() -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(0.0, 200.0)
        sp.setSingleStep(1.0)
        sp.setValue(0.0)
        sp.setSuffix(" mm")
        return sp

    def _on_reset(self) -> None:
        self._reset_requested = True
        self.accept()

    def values(self) -> dict:
        return {
            "top_pt": float(self.spin_top.value()) * MM,
            "bottom_pt": float(self.spin_bottom.value()) * MM,
            "left_pt": float(self.spin_left.value()) * MM,
            "right_pt": float(self.spin_right.value()) * MM,
            "reset": self._reset_requested,
        }


class LinkInsertDialog(QDialog):
    """Hộp thoại nhập đích liên kết (URL web hoặc nhảy tới số trang)."""

    def __init__(self, page_count: int, current_page_1based: int = 1, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Thêm liên kết")
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        self.rad_url = QRadioButton("Mở địa chỉ Web / URL:")
        self.rad_url.setChecked(True)
        self.ed_url = QLineEdit("https://")
        self.ed_url.setPlaceholderText("https://example.com")

        self.rad_page = QRadioButton(f"Chuyển tới trang trong tài liệu (1–{page_count}):")
        self.spin_page = QSpinBox()
        self.spin_page.setRange(1, max(1, page_count))
        self.spin_page.setValue(max(1, min(page_count, current_page_1based)))

        self.ed_url.textEdited.connect(lambda _t: self.rad_url.setChecked(True))
        self.spin_page.valueChanged.connect(lambda _v: self.rad_page.setChecked(True))

        root.addWidget(self.rad_url)
        root.addWidget(self.ed_url)
        root.addWidget(self.rad_page)
        root.addWidget(self.spin_page)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Thêm liên kết")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> dict:
        if self.rad_url.isChecked():
            return {"uri": self.ed_url.text().strip(), "target_page": None}
        return {"uri": "", "target_page": int(self.spin_page.value()) - 1}
