"""Hộp thoại chữ ký của «Điền & Ký»: tạo chữ ký (vẽ tay · gõ tên · ảnh có sẵn · ảnh chụp tách nền) và thư viện chữ ký.

Mọi xử lý ảnh / lưu trữ nằm ở `core/fill_sign.py`; ở đây chỉ là giao diện. Chữ ký lưu trong thư viện được mã hoá bằng
Windows DPAPI theo tài khoản người dùng.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core import fill_sign as fs

LEGAL_NOTE = (
    "Chữ ký hình ảnh dùng để điền đơn, tờ khai, ký nháy… — <b>không</b> thay thế chữ ký số (USB token VGCA, "
    "Viettel-CA, VNPT-CA) trên văn bản điện tử có giá trị pháp lý."
)
IMAGE_FILTER = "Ảnh (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;Tất cả tệp (*)"


def _checker_pixmap(png: bytes, max_w: int, max_h: int) -> QPixmap:
    """Ảnh PNG có nền trong suốt vẽ trên nền ô bàn cờ (thấy rõ phần đã tách nền)."""
    src = QPixmap()
    src.loadFromData(png, "PNG")
    if src.isNull():
        return QPixmap()
    src = src.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(src.size())
    p = QPainter(out)
    cell = 10
    for y in range(0, out.height(), cell):
        for x in range(0, out.width(), cell):
            p.fillRect(x, y, cell, cell, QColor("#FFFFFF") if (x // cell + y // cell) % 2 else QColor("#E5E7EB"))
    p.drawPixmap(0, 0, src)
    p.end()
    return out


class SignaturePad(QWidget):
    """Khung ký bằng chuột / bút cảm ứng: mỗi lần nhấn–kéo–thả là một nét."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(QSize(480, 180))
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px;")
        self._strokes: List[List[Tuple[float, float]]] = []
        self._drawing = False
        self.color = "#1E3A8A"
        self.pen_width = 2.6

    def strokes(self) -> List[List[Tuple[float, float]]]:
        return [list(s) for s in self._strokes if len(s) >= 2]

    def set_strokes(self, strokes: List[List[Tuple[float, float]]]) -> None:
        self._strokes = [list(s) for s in strokes]
        self.update()
        self.changed.emit()

    def clear(self) -> None:
        self.set_strokes([])

    def undo_stroke(self) -> None:
        if self._strokes:
            self._strokes.pop()
            self.update()
            self.changed.emit()

    def set_color(self, color: str) -> None:
        self.color = color
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton:
            p = event.position()
            self._strokes.append([(p.x(), p.y())])
            self._drawing = True
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if self._drawing and self._strokes:
            p = event.position()
            last = self._strokes[-1][-1]
            if abs(p.x() - last[0]) + abs(p.y() - last[1]) >= 1.0:
                self._strokes[-1].append((p.x(), p.y()))
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if self._drawing:
            self._drawing = False
            if self._strokes and len(self._strokes[-1]) == 1:  # chấm một điểm
                x, y = self._strokes[-1][0]
                self._strokes[-1].append((x + 0.6, y + 0.6))
            self.changed.emit()

    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        base_y = self.height() * 0.72
        p.setPen(QPen(QColor("#CBD5E1"), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(24, base_y), QPointF(self.width() - 24, base_y))
        if not self._strokes:
            p.setPen(QColor("#94A3B8"))
            p.drawText(QRectF(0, 0, self.width(), base_y - 8), Qt.AlignmentFlag.AlignCenter,
                       "Ký vào đây bằng chuột hoặc bút cảm ứng")
        p.setPen(QPen(QColor(self.color), self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        for stroke in self._strokes:
            if not stroke:
                continue
            path = QPainterPath(QPointF(*stroke[0]))
            for x, y in stroke[1:]:
                path.lineTo(QPointF(x, y))
            p.drawPath(path)
        p.end()


class SignatureCreateDialog(QDialog):
    """Tạo chữ ký / chữ ký nháy mới. Kết quả ở `signature` (đã lưu vào thư viện nếu có `library`)."""

    TAB_DRAW, TAB_TYPE, TAB_IMAGE, TAB_PHOTO = range(4)

    def __init__(self, library: Optional[fs.SignatureLibrary] = None, initials: bool = False, name: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        self.signature: Optional[fs.Signature] = None
        self._image_png: Optional[bytes] = None  # thẻ Ảnh: ảnh đã chuẩn hoá
        self._photo_raw: Optional[bytes] = None  # thẻ Ảnh chụp: ảnh gốc
        self._photo_png: Optional[bytes] = None
        self._photo_error = ""
        self._image_raw: Optional[bytes] = None
        self.setWindowTitle("Tạo chữ ký nháy" if initials else "Tạo chữ ký")
        self.resize(620, 520)
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.kind_sig = QRadioButton("Chữ ký")
        self.kind_ini = QRadioButton("Chữ ký nháy (ký tắt)")
        (self.kind_ini if initials else self.kind_sig).setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.kind_sig)
        grp.addButton(self.kind_ini)
        top.addWidget(self.kind_sig)
        top.addWidget(self.kind_ini)
        top.addStretch(1)
        top.addWidget(QLabel("Tên gợi nhớ"))
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("vd: Chữ ký chính")
        self.name_edit.setMaximumWidth(200)
        top.addWidget(self.name_edit)
        lay.addLayout(top)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_draw_tab(), "✏️ Vẽ")
        self.tabs.addTab(self._build_type_tab(initials), "⌨️ Gõ tên")
        self.tabs.addTab(self._build_image_tab(), "🖼️ Ảnh có sẵn")
        self.tabs.addTab(self._build_photo_tab(), "📷 Ảnh chụp trên giấy")
        self.tabs.currentChanged.connect(lambda _i: self._update_ok())
        lay.addWidget(self.tabs, 1)

        note = QLabel(LEGAL_NOTE)
        note.setWordWrap(True)
        note.setObjectName("mutedLabel")
        lay.addWidget(note)

        row = QHBoxLayout()
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("mutedLabel")
        self.status_lbl.setWordWrap(True)
        row.addWidget(self.status_lbl, 1)
        self.btn_cancel = QPushButton("Huỷ")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("Lưu chữ ký")
        self.btn_ok.setObjectName("primaryConvertBtn")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._on_save)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)

        self._photo_timer = QTimer(self)
        self._photo_timer.setSingleShot(True)
        self._photo_timer.setInterval(220)
        self._photo_timer.timeout.connect(self._process_photo)
        self._update_ok()

    # ─── Các thẻ ──────────────────────────────────────────────────────────

    def _color_row(self, on_change: Callable[[str], None]) -> Tuple[QWidget, QButtonGroup]:
        box = QWidget()
        hl = QHBoxLayout(box)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(QLabel("Màu mực"))
        grp = QButtonGroup(box)
        for i, (color, name) in enumerate(fs.INK_COLORS):
            rb = QRadioButton(name)
            rb.setStyleSheet(f"QRadioButton {{ color: {color}; font-weight: 600; }}")
            rb.setChecked(color == "#1E3A8A")
            rb.toggled.connect(lambda on, c=color: on and on_change(c))
            grp.addButton(rb, i)
            hl.addWidget(rb)
        hl.addStretch(1)
        return box, grp

    def _build_draw_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.pad = SignaturePad()
        self.pad.changed.connect(self._update_ok)
        lay.addWidget(self.pad, 1)
        row = QHBoxLayout()
        colors, self.draw_colors = self._color_row(self.pad.set_color)
        row.addWidget(colors, 1)
        btn_undo = QPushButton("↶ Bỏ nét cuối")
        btn_undo.clicked.connect(self.pad.undo_stroke)
        btn_clear = QPushButton("Xoá hết")
        btn_clear.clicked.connect(self.pad.clear)
        row.addWidget(btn_undo)
        row.addWidget(btn_clear)
        lay.addLayout(row)
        return w

    def _build_type_tab(self, initials: bool) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QHBoxLayout()
        form.addWidget(QLabel("Họ tên / chữ ký tắt"))
        self.type_edit = QLineEdit()
        self.type_edit.setPlaceholderText("vd: Nguyễn Văn An" if not initials else "vd: NVA")
        self.type_edit.textChanged.connect(self._on_type_changed)
        form.addWidget(self.type_edit, 1)
        lay.addLayout(form)
        frow = QHBoxLayout()
        frow.addWidget(QLabel("Kiểu chữ"))
        self.font_combo = QComboBox()
        for key, name, _ok in fs.available_script_fonts():
            self.font_combo.addItem(name, key)
        self.font_combo.currentIndexChanged.connect(self._on_type_changed)
        frow.addWidget(self.font_combo, 1)
        lay.addLayout(frow)
        colors, self.type_colors = self._color_row(lambda _c: self._on_type_changed())
        lay.addWidget(colors)
        self.type_preview = QLabel()
        self.type_preview.setMinimumHeight(120)
        self.type_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.type_preview.setStyleSheet("background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px;")
        lay.addWidget(self.type_preview, 1)
        self.type_note = QLabel("")
        self.type_note.setObjectName("mutedLabel")
        self.type_note.setWordWrap(True)
        lay.addWidget(self.type_note)
        return w

    def _build_image_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        btn = QPushButton("📂 Chọn ảnh chữ ký / con dấu…")
        btn.clicked.connect(lambda: self._pick_file(photo=False))
        row.addWidget(btn)
        self.image_clean_chk = QCheckBox("Tách nền trắng")
        self.image_clean_chk.setToolTip("Bỏ nền giấy / nền trắng, giữ nét mực (ảnh PNG đã trong suốt thì giữ nguyên)")
        self.image_clean_chk.setChecked(True)
        self.image_clean_chk.toggled.connect(lambda _v: self._process_image())
        row.addWidget(self.image_clean_chk)
        row.addStretch(1)
        lay.addLayout(row)
        self.image_preview = QLabel("Chưa chọn ảnh. Nên dùng ảnh PNG nền trong suốt hoặc ảnh quét nền trắng.")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setWordWrap(True)
        self.image_preview.setMinimumHeight(200)
        lay.addWidget(self.image_preview, 1)
        return w

    def _build_photo_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        guide = QLabel("Ký lên giấy trắng, chụp thẳng bằng điện thoại (đủ sáng, không rung) rồi chọn ảnh — phần mềm tự "
                       "bỏ nền giấy, bóng tay, mặt bàn và giữ màu mực (con dấu đỏ vẫn đỏ).")
        guide.setWordWrap(True)
        lay.addWidget(guide)
        row = QHBoxLayout()
        btn = QPushButton("📷 Chọn ảnh chụp…")
        btn.clicked.connect(lambda: self._pick_file(photo=True))
        row.addWidget(btn)
        row.addWidget(QLabel("Độ nhạy mực"))
        self.sens_slider = QSlider(Qt.Orientation.Horizontal)
        self.sens_slider.setRange(0, 100)
        self.sens_slider.setValue(50)
        self.sens_slider.setToolTip("Tăng nếu nét bút mờ bị mất; giảm nếu còn vết bẩn / bóng")
        self.sens_slider.valueChanged.connect(lambda _v: self._photo_timer.start())
        row.addWidget(self.sens_slider, 1)
        self.keep_color_chk = QCheckBox("Giữ màu mực")
        self.keep_color_chk.setChecked(True)
        self.keep_color_chk.toggled.connect(lambda _v: self._photo_timer.start())
        row.addWidget(self.keep_color_chk)
        lay.addLayout(row)
        self.photo_preview = QLabel("Chưa chọn ảnh.")
        self.photo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo_preview.setMinimumHeight(200)
        lay.addWidget(self.photo_preview, 1)
        return w

    # ─── Xử lý ────────────────────────────────────────────────────────────

    def _type_color(self) -> str:
        return fs.INK_COLORS[max(0, self.type_colors.checkedId())][0]

    def _typed_signature(self) -> Optional[fs.Signature]:
        text = self.type_edit.text().strip()
        if not text:
            return None
        return fs.Signature("typed", self.kind_ini.isChecked(), text=text, font=self.font_combo.currentData() or
                            "times_italic", color=self._type_color())

    def _on_type_changed(self, *_args) -> None:
        sig = self._typed_signature()
        if sig is None:
            self.type_preview.clear()
            self.type_note.setText("")
        else:
            pix = QPixmap()
            pix.loadFromData(fs.render_signature_png(sig, 90, 520), "PNG")
            self.type_preview.setPixmap(pix)
            key = self.font_combo.currentData()
            used = fs.resolve_script_font(key, sig.text)[1]
            self.type_note.setText(
                "" if used == key else
                "Kiểu chữ này thiếu chữ tiếng Việt có dấu trong tên — tạm dùng Times New Roman nghiêng."
            )
        self._update_ok()

    def set_image_bytes(self, data: bytes, photo: bool) -> None:
        """Nạp ảnh cho thẻ «Ảnh có sẵn» (`photo=False`) hoặc «Ảnh chụp» (`photo=True`) — dùng cả khi kiểm thử."""
        if photo:
            self._photo_raw = data
            self.tabs.setCurrentIndex(self.TAB_PHOTO)
            self._process_photo()
        else:
            self._image_raw = data
            self.tabs.setCurrentIndex(self.TAB_IMAGE)
            self._process_image()

    def _pick_file(self, photo: bool) -> None:
        path, _f = QFileDialog.getOpenFileName(self, "Chọn ảnh chụp chữ ký" if photo else "Chọn ảnh chữ ký",
                                               str(Path.home()), IMAGE_FILTER)
        if path:
            try:
                self.set_image_bytes(Path(path).read_bytes(), photo)
            except OSError as exc:
                self.status_lbl.setText(f"Không đọc được tệp: {exc}")

    def _process_image(self) -> None:
        if self._image_raw is None:
            return
        try:
            # Bật «Tách nền trắng»: ảnh đã trong suốt giữ nguyên, ảnh nền trắng thì tách nền (None = tự quyết)
            clean = None if self.image_clean_chk.isChecked() else False
            self._image_png = fs.prepare_signature_image(self._image_raw, clean)
            self.image_preview.setPixmap(_checker_pixmap(self._image_png, 540, 260))
            self.status_lbl.setText("")
        except fs.FillSignError as exc:
            self._image_png = None
            self.image_preview.setText(str(exc))
        self._update_ok()

    def _process_photo(self) -> None:
        if self._photo_raw is None:
            return
        try:
            self._photo_png = fs.clean_signature_photo(self._photo_raw, self.sens_slider.value(),
                                                       self.keep_color_chk.isChecked())
            self._photo_error = ""
            self.photo_preview.setPixmap(_checker_pixmap(self._photo_png, 540, 260))
        except fs.FillSignError as exc:
            self._photo_png = None
            self._photo_error = str(exc)
            self.photo_preview.setText(str(exc))
        self._update_ok()

    def build_signature(self) -> Optional[fs.Signature]:
        """Chữ ký theo thẻ đang chọn (None nếu chưa đủ dữ liệu)."""
        initials = self.kind_ini.isChecked()
        name = self.name_edit.text().strip()
        tab = self.tabs.currentIndex()
        sig: Optional[fs.Signature] = None
        if tab == self.TAB_DRAW:
            strokes = self.pad.strokes()
            bounds = fs._strokes_bounds(strokes)
            if strokes and bounds is not None:
                # Độ dày nét so với bề rộng chữ ký — giữ đúng tỷ lệ nét như lúc ký trên khung
                pen = self.pad.pen_width * 1.25 / max(40.0, bounds.width)
                sig = fs.Signature("drawn", initials, strokes=strokes, color=self.pad.color, pen=pen)
        elif tab == self.TAB_TYPE:
            sig = self._typed_signature()
        elif tab == self.TAB_IMAGE and self._image_png:
            sig = fs.Signature("image", initials, png=self._image_png)
        elif tab == self.TAB_PHOTO and self._photo_png:
            sig = fs.Signature("image", initials, png=self._photo_png)
        if sig is not None:
            sig.initials = initials
            sig.name = name
        return sig

    def _update_ok(self) -> None:
        self.btn_ok.setEnabled(self.build_signature() is not None)

    def _on_save(self) -> None:
        sig = self.build_signature()
        if sig is None:
            return
        try:
            if self.library is not None:
                self.library.save(sig)
        except (fs.FillSignError, OSError) as exc:
            QMessageBox.warning(self, "Lưu chữ ký", f"Không lưu được chữ ký: {exc}")
            return
        self.signature = sig
        self.accept()


class SignatureManagerDialog(QDialog):
    """Thư viện chữ ký: xem, tạo mới, xoá, chọn chữ ký đang dùng. Kết quả chọn ở `chosen_id`."""

    def __init__(self, library: fs.SignatureLibrary, initials: Optional[bool] = None,
                 parent: QWidget | None = None,
                 create_dialog: Optional[Callable[[QWidget, bool], Optional[fs.Signature]]] = None) -> None:
        super().__init__(parent)
        self.library = library
        self.initials = initials
        self.chosen_id: Optional[str] = None
        self.created: List[fs.Signature] = []
        self._create_dialog = create_dialog or self._default_create
        self.setWindowTitle("Thư viện chữ ký")
        self.resize(560, 460)
        lay = QVBoxLayout(self)
        info = QLabel("Chữ ký lưu trên máy này, mã hoá theo tài khoản Windows của bạn (không gửi đi đâu). "
                      "Nhấp đúp để dùng chữ ký.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.list = QListWidget()
        self.list.setIconSize(QSize(160, 48))
        self.list.setSpacing(4)
        self.list.itemDoubleClicked.connect(lambda _it: self._use())
        self.list.currentRowChanged.connect(lambda _r: self._sync_buttons())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.btn_new = QPushButton("＋ Tạo chữ ký mới…")
        self.btn_new.clicked.connect(lambda: self.create_new(False))
        self.btn_new_ini = QPushButton("＋ Chữ ký nháy…")
        self.btn_new_ini.clicked.connect(lambda: self.create_new(True))
        self.btn_delete = QPushButton("🗑 Xoá")
        self.btn_delete.clicked.connect(self._delete)
        row.addWidget(self.btn_new)
        row.addWidget(self.btn_new_ini)
        row.addWidget(self.btn_delete)
        row.addStretch(1)
        self.btn_use = QPushButton("Dùng chữ ký này")
        self.btn_use.setObjectName("primaryConvertBtn")
        self.btn_use.clicked.connect(self._use)
        btn_close = QPushButton("Đóng")
        btn_close.clicked.connect(self.reject)
        row.addWidget(self.btn_use)
        row.addWidget(btn_close)
        lay.addLayout(row)
        note = QLabel(LEGAL_NOTE)
        note.setWordWrap(True)
        note.setObjectName("mutedLabel")
        lay.addWidget(note)
        self.refresh()

    def _default_create(self, parent: QWidget, initials: bool) -> Optional[fs.Signature]:
        dlg = SignatureCreateDialog(self.library, initials, parent=parent)
        return dlg.signature if dlg.exec() == QDialog.DialogCode.Accepted else None

    def refresh(self, select_id: Optional[str] = None) -> None:
        self.list.clear()
        for sig in self.library.list(self.initials):
            pix = QPixmap()
            try:
                pix.loadFromData(fs.render_signature_png(sig, 48, 160), "PNG")
            except Exception:
                pass
            item = QListWidgetItem(QIcon(pix), sig.label)
            item.setData(Qt.ItemDataRole.UserRole, sig.id)
            self.list.addItem(item)
            if sig.id == select_id:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(self.list.count() - 1)
        self._sync_buttons()

    def _current_id(self) -> Optional[str]:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _sync_buttons(self) -> None:
        has = self._current_id() is not None
        self.btn_use.setEnabled(has)
        self.btn_delete.setEnabled(has)
        self.btn_new_ini.setVisible(self.initials is not False)
        self.btn_new.setVisible(self.initials is not True)

    def create_new(self, initials: bool) -> Optional[fs.Signature]:
        sig = self._create_dialog(self, initials)
        if sig is not None:
            self.created.append(sig)
            self.refresh(select_id=sig.id)
        return sig

    def _delete(self) -> None:
        sig_id = self._current_id()
        if sig_id is None:
            return
        answer = QMessageBox.question(self, "Xoá chữ ký", "Xoá chữ ký đã chọn khỏi thư viện?\n"
                                      "(Chữ ký đã đặt trên tài liệu không bị ảnh hưởng.)")
        if answer == QMessageBox.StandardButton.Yes:
            self.library.delete(sig_id)
            self.refresh()

    def _use(self) -> None:
        sig_id = self._current_id()
        if sig_id is not None:
            self.chosen_id = sig_id
            self.accept()
