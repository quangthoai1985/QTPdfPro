"""Hộp thoại «Sắp xếp & cắt ghép trang» — lưới trang thu nhỏ kéo thả kiểu PdfCraft, mạnh hơn ở chỗ làm việc
trên nhiều tệp cùng lúc và «cắt» trực quan:

- Kéo thả để đổi thứ tự (hoặc Ctrl+← / Ctrl+→, «Di chuyển tới vị trí…»), chọn nhiều trang bằng Ctrl/Shift.
- Xoay trái/phải, nhân bản, xoá, chèn trang trắng, đảo thứ tự, thêm trang từ tệp PDF khác (ghép tệp).
- Đặt **điểm cắt** (✂) giữa các trang → lưới tô màu theo từng phần → «Xuất các phần…» thành nhiều tệp;
  hoặc «Chia tệp…» theo mỗi N trang / theo khoảng trang.
- Trích các trang đang chọn thành tệp mới; Hoàn tác / Làm lại mọi thao tác.

Engine dựng tệp nằm ở `qtpdfpro/core/page_ops.py` (giữ chú thích, liên kết, mục lục).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import count
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core import page_ops as po

SOURCE_COLORS = ["#2563EB", "#16A34A", "#EA580C", "#9333EA", "#DB2777", "#0891B2", "#CA8A04", "#4F46E5"]
PART_TINTS = ["#3B82F6", "#F59E0B", "#10B981", "#EC4899", "#8B5CF6", "#06B6D4"]
THUMB_HEIGHT_PX = 240
_uids = count(1)

MODE_TITLES = {
    "organize": "🧩 Sắp xếp && cắt ghép trang",
    "combine": "🧷 Ghép tệp PDF",
    "split": "✂️ Tách tệp PDF",
    "extract": "📤 Trích trang",
}
MODE_HINTS = {
    "organize": "Kéo thả để đổi thứ tự · chuột phải để xem thêm thao tác · ✂ đặt điểm cắt để tách thành nhiều tệp.",
    "combine": "Thêm các tệp PDF cần ghép, kéo thả để sắp xếp rồi bấm «Lưu PDF…».",
    "split": "Đặt điểm cắt ✂ giữa các trang (hoặc «Chia tệp…») rồi bấm «Xuất các phần…».",
    "extract": "Chọn các trang cần trích (Ctrl/Shift + nhấp) rồi bấm «Trích trang đã chọn…».",
}


@dataclass
class _Item:
    uid: int
    ref: po.PageRef
    split_after: bool = False


@dataclass
class _Source:
    key: str
    doc: fitz.Document
    label: str
    color: str
    owned: bool


class _PageGridDelegate(QStyledItemDelegate):
    """Vẽ thẻ trang: ảnh thu nhỏ (đã xoay), số thứ tự, tệp nguồn, góc xoay, điểm cắt, phần."""

    LABEL_H = 38

    def __init__(self, dialog: "PageOrganizerDialog") -> None:
        super().__init__(dialog)
        self.dlg = dialog

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802 - API Qt
        w = self.dlg.thumb_width
        return QSize(w + 28, int(w * 1.414) + self.LABEL_H + 26)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        dlg = self.dlg
        item = dlg.item_at_row(index.row())
        if item is None:
            return
        pal = dlg.colors
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        cell = QRectF(option.rect).adjusted(5, 5, -9, -5)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        part = dlg.part_index_of(index.row())
        painter.setPen(QPen(QColor(pal["sel_border"] if selected else pal["border"]), 2 if selected else 1))
        painter.setBrush(QBrush(QColor(pal["sel_bg"] if selected else pal["card"])))
        painter.drawRoundedRect(cell, 9, 9)
        painter.setBrush(Qt.BrushStyle.NoBrush)  # các khung viền bên dưới không được tô đè lên ảnh trang
        if part is not None:
            strip = QRectF(cell.left() + 8, cell.top() + 4, cell.width() - 16, 4)
            painter.fillRect(strip, QColor(PART_TINTS[part % len(PART_TINTS)]))

        area = QRectF(cell.left() + 10, cell.top() + 12, cell.width() - 20, cell.height() - self.LABEL_H - 18)
        ref = item.ref
        if ref.is_blank:
            w, h = dlg.display_size(index.row())
            size = QSize(int(w), int(h)).scaled(area.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF(0, 0, size.width(), size.height())
            target.moveCenter(area.center())
            painter.fillRect(target.translated(2, 3), QColor(0, 0, 0, 40))
            painter.fillRect(target, QColor("#FFFFFF"))
            painter.setPen(QPen(QColor("#CBD5E1"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(target)
            painter.setPen(QColor("#94A3B8"))
            painter.drawText(target, Qt.AlignmentFlag.AlignCenter, "Trang trắng")
        else:
            pix = dlg.thumbnail(ref)
            if pix is not None and not pix.isNull():
                size = pix.size().scaled(area.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
                target = QRectF(0, 0, size.width(), size.height())
                target.moveCenter(area.center())
                painter.fillRect(target.translated(2, 3), QColor(0, 0, 0, 45))
                painter.drawPixmap(target, pix, QRectF(pix.rect()))
                painter.setPen(QPen(QColor(pal["border"]), 1))
                painter.drawRect(target)
        if ref.rotation:
            badge = QRectF(area.right() - 46, area.top() + 2, 44, 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#2563EB")))
            painter.drawRoundedRect(badge, 9, 9)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, f"↻{ref.rotation}°")
        if part is not None:
            badge = QRectF(area.left() + 2, area.top() + 2, 52, 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(PART_TINTS[part % len(PART_TINTS)])))
            painter.drawRoundedRect(badge, 9, 9)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, f"Phần {part + 1}")

        # Nhãn: số thứ tự + nguồn
        label = QRectF(cell.left() + 8, cell.bottom() - self.LABEL_H, cell.width() - 16, self.LABEL_H - 4)
        bold = QFont(option.font)
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QColor(pal["text"]))
        painter.drawText(QRectF(label.left(), label.top(), label.width(), 18),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, str(index.row() + 1))
        small = QFont(option.font)
        small.setPointSizeF(max(7.0, option.font.pointSizeF() - 1.5))
        painter.setFont(small)
        src = dlg.source(ref.source)
        text = "Trang trắng" if ref.is_blank else f"{src.label if src else '?'} · tr.{ref.page_index + 1}"
        metrics = painter.fontMetrics()
        text = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, int(label.width() - 14))
        line2 = QRectF(label.left() + 12, label.top() + 18, label.width() - 12, 16)
        if src is not None and not ref.is_blank:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(src.color)))
            dot_x = label.center().x() - metrics.horizontalAdvance(text) / 2 - 10
            painter.drawEllipse(QPointF(dot_x, line2.center().y()), 4, 4)
        painter.setPen(QColor(pal["muted"]))
        painter.drawText(QRectF(label.left(), line2.top(), label.width(), 16),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, text)

        if item.split_after:
            x = option.rect.right() - 3
            pen = QPen(QColor("#DC2626"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(x, option.rect.top() + 6), QPointF(x, option.rect.bottom() - 6))
            circle = QRectF(x - 11, option.rect.center().y() - 11, 22, 22)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#DC2626")))
            painter.drawEllipse(circle)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, "✂")
        painter.restore()


class _SplitDialog(QDialog):
    """Chọn cách chia tệp: mỗi N trang, theo khoảng trang, theo điểm cắt đã đặt, hoặc mỗi trang một tệp."""

    def __init__(self, parent: "PageOrganizerDialog", total: int, marker_parts: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chia tệp PDF")
        self.total = total
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Tài liệu hiện có <b>{total} trang</b> (theo thứ tự trên lưới). Chọn cách chia:"))
        self.group = QButtonGroup(self)
        self.rb_every = QRadioButton("Mỗi phần")
        self.spin_every = QSpinBox()
        self.spin_every.setRange(1, max(1, total))
        self.spin_every.setValue(min(2, max(1, total)))
        self.spin_every.setSuffix(" trang")
        row = QHBoxLayout()
        row.addWidget(self.rb_every)
        row.addWidget(self.spin_every)
        row.addStretch(1)
        lay.addLayout(row)
        self.rb_ranges = QRadioButton("Theo khoảng trang (mỗi khoảng một tệp)")
        self.edit_ranges = QLineEdit()
        self.edit_ranges.setPlaceholderText("vd: 1-3, 4-6, 7")
        lay.addWidget(self.rb_ranges)
        lay.addWidget(self.edit_ranges)
        self.rb_markers = QRadioButton(f"Theo điểm cắt ✂ đã đặt trên lưới ({marker_parts} phần)")
        self.rb_markers.setEnabled(marker_parts > 1)
        lay.addWidget(self.rb_markers)
        self.rb_single = QRadioButton("Mỗi trang một tệp")
        lay.addWidget(self.rb_single)
        for i, rb in enumerate((self.rb_every, self.rb_ranges, self.rb_markers, self.rb_single)):
            self.group.addButton(rb, i)
        (self.rb_markers if marker_parts > 1 else self.rb_every).setChecked(True)
        self.preview = QLabel()
        self.preview.setObjectName("mutedLabel")
        lay.addWidget(self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("✂ Tách && lưu…")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Huỷ")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.group.idToggled.connect(lambda *_: self._update_preview())
        self.spin_every.valueChanged.connect(lambda *_: self._update_preview())
        self.edit_ranges.textChanged.connect(lambda *_: (self.rb_ranges.setChecked(True), self._update_preview()))
        self.marker_parts = marker_parts
        self.result_spec: Tuple[str, object] = ("every", 2)
        self._update_preview()

    def spec(self) -> Tuple[str, object]:
        if self.rb_ranges.isChecked():
            return "ranges", self.edit_ranges.text()
        if self.rb_markers.isChecked():
            return "markers", None
        if self.rb_single.isChecked():
            return "every", 1
        return "every", self.spin_every.value()

    def _update_preview(self) -> None:
        kind, value = self.spec()
        try:
            if kind == "ranges":
                n = len(po.parse_split_ranges(str(value), self.total))
            elif kind == "markers":
                n = self.marker_parts
            else:
                n = -(-self.total // int(value))
            self.preview.setText(f"→ Sẽ tạo {n} tệp PDF.")
        except po.PageOpsError as exc:
            self.preview.setText(f"⚠ {exc}")

    def _accept(self) -> None:
        kind, value = self.spec()
        if kind == "ranges":
            try:
                po.parse_split_ranges(str(value), self.total)
            except po.PageOpsError as exc:
                QMessageBox.warning(self, "Khoảng trang không hợp lệ", str(exc))
                return
        self.result_spec = (kind, value)
        self.accept()


class PageOrganizerDialog(QDialog):
    """Lưới trang thu nhỏ để sắp xếp, xoay, xoá, chèn, ghép, tách, trích trang PDF."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        sources: Sequence[Tuple[str, fitz.Document, str]] = (),
        files: Sequence[str] = (),
        mode: str = "organize",
        theme: str = "dark",
        is_locked: Optional[Callable[[Path], bool]] = None,
        overwrite_handler: Optional[Callable[[Path, bytes], bool]] = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode if mode in MODE_TITLES else "organize"
        self.setWindowTitle(MODE_TITLES[self.mode].replace("&&", "&") + " — QT PDF Pro")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.resize(1180, 760)
        self._is_locked = is_locked or (lambda _p: False)
        self._overwrite_handler = overwrite_handler
        dark = theme != "light"
        self.colors = {
            "card": "#1A1D24" if dark else "#FFFFFF",
            "sel_bg": "#1E2A44" if dark else "#E8F0FE",
            "border": "#2A2F3A" if dark else "#E2E5EA",
            "sel_border": "#3B82F6" if dark else "#2563EB",
            "text": "#E6E8EC" if dark else "#0F172A",
            "muted": "#9CA3AF" if dark else "#64748B",
        }
        self._sources: Dict[str, _Source] = {}
        self._items: List[_Item] = []
        self._by_uid: Dict[int, _Item] = {}
        self._undo: List[List[_Item]] = []
        self._redo: List[List[_Item]] = []
        self._thumbs: Dict[Tuple[str, int], QPixmap] = {}
        self._rot_thumbs: Dict[Tuple[str, int, int], QPixmap] = {}
        self._reloading = False
        self.thumb_width = 132
        self.result_paths: List[Path] = []
        self.result_kind = ""  # "file" | "parts" | "overwrite"

        self._build_ui()
        for key, doc, label in sources:
            self._add_source(key, doc, label, owned=False)
            self._items.extend(_Item(next(_uids), r) for r in po.refs_for_document(key, doc.page_count))
        for f in files:
            key = str(Path(f).resolve())
            if key in self._sources:
                continue
            doc = self._open_pdf(Path(key))
            if doc is not None:
                self._add_source(key, doc, Path(key).name, owned=True)
                self._items.extend(_Item(next(_uids), r) for r in po.refs_for_document(key, doc.page_count))
        self._reload()
        if self.mode == "combine" and len({it.ref.source for it in self._items}) < 2:
            QTimer.singleShot(0, self.add_files)
        elif self.mode == "split" and self._items:
            QTimer.singleShot(0, self.open_split_dialog)

    # ─── Dựng giao diện ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)
        head = QHBoxLayout()
        title = QLabel(f"<b style='font-size:16px'>{MODE_TITLES[self.mode].replace('&&', '&amp;')}</b>")
        head.addWidget(title)
        self.summary_lbl = QLabel()
        self.summary_lbl.setObjectName("mutedLabel")
        head.addWidget(self.summary_lbl, 1)
        head.addWidget(QLabel("Cỡ ảnh"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(80, 260)
        self.zoom_slider.setValue(self.thumb_width)
        self.zoom_slider.setFixedWidth(120)
        self.zoom_slider.valueChanged.connect(self._on_zoom)
        head.addWidget(self.zoom_slider)
        root.addLayout(head)

        bar = QHBoxLayout()
        bar.setSpacing(4)

        def tool(text: str, tip: str, fn, shortcut: str = "") -> QPushButton:
            b = QPushButton(text)
            b.setObjectName("pillBtn")
            b.setToolTip(tip + (f" ({shortcut})" if shortcut else ""))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            bar.addWidget(b)
            return b

        tool("＋ Thêm tệp PDF…", "Ghép thêm trang từ tệp PDF khác (chèn sau trang đang chọn)", self.add_files)
        tool("＋ Trang trắng", "Chèn trang trắng sau trang đang chọn", self.insert_blank)
        tool("↺", "Xoay trái 90°", lambda: self.rotate_selected(-90), "Shift+R")
        tool("↻", "Xoay phải 90°", lambda: self.rotate_selected(90), "R")
        tool("⧉ Nhân bản", "Nhân bản các trang đang chọn", self.duplicate_selected, "Ctrl+D")
        tool("🗑 Xoá", "Xoá các trang đang chọn", self.delete_selected, "Delete")
        tool("◀", "Di chuyển trang chọn lên trước", lambda: self.move_selected(-1), "Ctrl+←")
        tool("▶", "Di chuyển trang chọn ra sau", lambda: self.move_selected(1), "Ctrl+→")
        tool("⇅ Đảo thứ tự", "Đảo thứ tự các trang đang chọn (hoặc cả tài liệu)", self.reverse_selected)
        bar.addSpacing(8)
        tool("✂ Cắt sau trang", "Đặt / bỏ điểm cắt sau trang đang chọn — tách thành nhiều tệp", self.toggle_split, "S")
        tool("✂ Chia tệp…", "Chia theo mỗi N trang, theo khoảng trang hoặc theo điểm cắt", self.open_split_dialog)
        bar.addStretch(1)
        self.btn_undo = tool("↶", "Hoàn tác", self.undo, "Ctrl+Z")
        self.btn_redo = tool("↷", "Làm lại", self.redo, "Ctrl+Y")
        root.addLayout(bar)

        self.grid = QListWidget()
        self.grid.setObjectName("pageGrid")
        self.grid.setViewMode(QListView.ViewMode.ListMode)
        self.grid.setFlow(QListView.Flow.LeftToRight)
        self.grid.setWrapping(True)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Snap)
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(2)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.grid.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.grid.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.grid.setDropIndicatorShown(True)
        self.grid.setItemDelegate(_PageGridDelegate(self))
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._context_menu)
        self.grid.itemSelectionChanged.connect(self._update_summary)
        self.grid.model().rowsMoved.connect(self._on_rows_moved)
        root.addWidget(self.grid, 1)

        foot = QHBoxLayout()
        self.status_lbl = QLabel(MODE_HINTS[self.mode])
        self.status_lbl.setObjectName("mutedLabel")
        self.status_lbl.setWordWrap(True)
        foot.addWidget(self.status_lbl, 1)
        self.chk_open = QCheckBox("Mở kết quả sau khi lưu")
        self.chk_open.setChecked(True)
        foot.addWidget(self.chk_open)
        self.btn_extract = QPushButton("📤 Trích trang đã chọn…")
        self.btn_extract.clicked.connect(self.extract_selected)
        self.btn_parts = QPushButton("✂ Xuất các phần…")
        self.btn_parts.clicked.connect(lambda: self.export_parts())
        self.btn_save = QPushButton("💾 Lưu PDF…")
        self.btn_save.setObjectName("primaryConvertBtn")
        self.btn_save.setToolTip("Lưu toàn bộ lưới trang thành một tệp PDF (Ctrl+S)")
        self.btn_save.clicked.connect(self.save_all)
        btn_close = QPushButton("Đóng")
        btn_close.clicked.connect(self.reject)
        for b in (self.btn_extract, self.btn_parts, self.btn_save, btn_close):
            foot.addWidget(b)
        root.addLayout(foot)

        shortcuts = [
            ("Delete", self.delete_selected), ("Ctrl+D", self.duplicate_selected),
            ("R", lambda: self.rotate_selected(90)), ("Shift+R", lambda: self.rotate_selected(-90)),
            ("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo), ("Ctrl+Shift+Z", self.redo),
            ("Ctrl+Left", lambda: self.move_selected(-1)), ("Ctrl+Right", lambda: self.move_selected(1)),
            ("S", self.toggle_split), ("Ctrl+S", self.save_all),
        ]
        for seq, fn in shortcuts:
            QShortcut(QKeySequence(seq), self, activated=fn)

    # ─── Nguồn & ảnh thu nhỏ ──────────────────────────────────────────────

    def _add_source(self, key: str, doc: fitz.Document, label: str, owned: bool) -> _Source:
        if key in self._sources:
            return self._sources[key]
        color = SOURCE_COLORS[len(self._sources) % len(SOURCE_COLORS)]
        src = _Source(key, doc, label, color, owned)
        self._sources[key] = src
        return src

    def source(self, key: str) -> Optional[_Source]:
        return self._sources.get(key)

    def thumbnail(self, ref: po.PageRef) -> Optional[QPixmap]:
        if ref.is_blank:
            return None
        key = (ref.source, ref.page_index)
        rkey = (ref.source, ref.page_index, ref.rotation)
        if rkey in self._rot_thumbs:
            return self._rot_thumbs[rkey]
        base = self._thumbs.get(key)
        if base is None:
            src = self._sources.get(ref.source)
            if src is None or src.doc.is_closed:
                return None
            page = src.doc[ref.page_index]
            scale = THUMB_HEIGHT_PX / max(1.0, page.rect.height)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            samples = pix.samples  # giữ tham chiếu tới bộ đệm cho tới khi QImage chép xong
            img = QImage(samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            base = QPixmap.fromImage(img)
            self._thumbs[key] = base
        pm = base if not ref.rotation else base.transformed(
            QTransform().rotate(ref.rotation), Qt.TransformationMode.SmoothTransformation
        )
        self._rot_thumbs[rkey] = pm
        return pm

    def display_size(self, row: int) -> Tuple[float, float]:
        """Cỡ hiển thị (pt) của trang ở vị trí `row` (trang trắng lấy theo trang liền trước)."""
        for i in range(row, -1, -1):
            ref = self._items[i].ref
            if ref.is_blank and ref.width:
                return ref.width, ref.height
            if not ref.is_blank:
                src = self._sources.get(ref.source)
                if src is None or src.doc.is_closed:
                    return po.A4_SIZE
                page = src.doc[ref.page_index]
                w, h = page.rect.width, page.rect.height
                return (h, w) if ref.rotation in (90, 270) else (w, h)
        return po.A4_SIZE

    # ─── Trạng thái lưới ──────────────────────────────────────────────────

    def item_at_row(self, row: int) -> Optional[_Item]:
        return self._items[row] if 0 <= row < len(self._items) else None

    def refs(self) -> List[po.PageRef]:
        return [it.ref for it in self._items]

    @property
    def page_count(self) -> int:
        return len(self._items)

    def part_index_of(self, row: int) -> Optional[int]:
        if not any(it.split_after for it in self._items[:-1]):
            return None
        return sum(1 for it in self._items[:row] if it.split_after)

    def marker_parts(self) -> List[List[po.PageRef]]:
        cuts = [i + 1 for i, it in enumerate(self._items[:-1]) if it.split_after]
        return po.split_refs(self.refs(), after=cuts)

    def _selected_rows(self) -> List[int]:
        return sorted(self.grid.row(it) for it in self.grid.selectedItems())

    def select_rows(self, rows: Sequence[int]) -> None:
        self.grid.clearSelection()
        for r in rows:
            item = self.grid.item(r)
            if item is not None:
                item.setSelected(True)
        if rows:
            last = self.grid.item(rows[-1])
            if last is not None:
                self.grid.setCurrentItem(last, QItemSelectionModel.SelectionFlag.NoUpdate)
                self.grid.scrollToItem(last)

    def _snapshot(self) -> List[_Item]:
        return [replace(it) for it in self._items]

    def _commit(self, new_items: List[_Item], select_uids: Sequence[int] = (), message: str = "") -> None:
        self._undo.append(self._snapshot())
        if len(self._undo) > 100:
            del self._undo[0]
        self._redo.clear()
        self._items = new_items
        self._reload(select_uids)
        if message:
            self.status_lbl.setText(message)

    def _reload(self, select_uids: Sequence[int] = ()) -> None:
        self._reloading = True
        try:
            self._by_uid = {it.uid: it for it in self._items}
            self.grid.clear()
            for it in self._items:
                li = QListWidgetItem()
                li.setData(Qt.ItemDataRole.UserRole, it.uid)
                li.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                self.grid.addItem(li)
            wanted = set(select_uids)
            rows = [i for i, it in enumerate(self._items) if it.uid in wanted]
        finally:
            self._reloading = False
        self.select_rows(rows)
        self._update_summary()

    def _update_summary(self) -> None:
        used = {it.ref.source for it in self._items if not it.ref.is_blank}
        parts = len(self.marker_parts()) if self._items else 0
        sel = len(self.grid.selectedItems())
        text = f"{self.page_count} trang · {len(used)} tệp nguồn"
        if parts > 1:
            text += f" · {parts} phần"
        if sel:
            text += f" · đang chọn {sel}"
        self.summary_lbl.setText(text)
        self.btn_undo.setEnabled(bool(self._undo))
        self.btn_redo.setEnabled(bool(self._redo))
        self.btn_parts.setEnabled(parts > 1)
        self.btn_extract.setEnabled(sel > 0)
        self.btn_save.setEnabled(self.page_count > 0)

    def _on_rows_moved(self, *_args) -> None:
        if self._reloading:
            return
        order = [self.grid.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.grid.count())]
        if order == [it.uid for it in self._items]:
            return
        self._undo.append(self._snapshot())
        self._redo.clear()
        self._items = [self._by_uid[u] for u in order]
        self.grid.viewport().update()
        self._update_summary()
        self.status_lbl.setText("Đã đổi thứ tự trang (Ctrl+Z để hoàn tác).")

    def _on_zoom(self, value: int) -> None:
        self.thumb_width = value
        self.grid.doItemsLayout()
        self.grid.viewport().update()

    # ─── Thao tác trang ───────────────────────────────────────────────────

    def _require_selection(self) -> List[int]:
        rows = self._selected_rows()
        if not rows:
            self.status_lbl.setText("Hãy chọn ít nhất một trang (nhấp vào ảnh trang; Ctrl/Shift để chọn nhiều).")
        return rows

    def rotate_selected(self, delta: int) -> None:
        rows = self._require_selection()
        if not rows:
            return
        items = self._snapshot()
        for r in rows:
            items[r].ref = items[r].ref.rotated(delta)
        self._commit(items, [items[r].uid for r in rows], f"Đã xoay {len(rows)} trang {abs(delta)}°.")

    def delete_selected(self) -> None:
        rows = self._require_selection()
        if not rows:
            return
        if len(rows) >= len(self._items):
            QMessageBox.information(self, "Không thể xoá", "Tài liệu kết quả phải còn ít nhất một trang.")
            return
        keep = set(range(len(self._items))) - set(rows)
        items = [replace(self._items[i]) for i in sorted(keep)]
        nxt = min(rows[0], len(items) - 1)
        self._commit(items, [items[nxt].uid] if items else [], f"Đã xoá {len(rows)} trang (Ctrl+Z để hoàn tác).")

    def duplicate_selected(self) -> None:
        rows = self._require_selection()
        if not rows:
            return
        items = self._snapshot()
        new_uids = []
        for r in reversed(rows):
            dup = _Item(next(_uids), items[r].ref)
            items.insert(r + 1, dup)
            new_uids.append(dup.uid)
        self._commit(items, new_uids, f"Đã nhân bản {len(rows)} trang.")

    def insert_blank(self) -> None:
        rows = self._selected_rows()
        at = (rows[-1] + 1) if rows else len(self._items)
        w, h = self.display_size(at - 1) if self._items else po.A4_SIZE
        blank = _Item(next(_uids), po.blank_page(w, h))
        items = self._snapshot()
        items.insert(at, blank)
        self._commit(items, [blank.uid], "Đã chèn trang trắng.")

    def move_selected(self, delta: int) -> None:
        rows = self._require_selection()
        if not rows:
            return
        items = self._snapshot()
        uids = [items[r].uid for r in rows]
        moving = [items[r] for r in rows]
        rest = [it for i, it in enumerate(items) if i not in set(rows)]
        pos = max(0, min(len(rest), rows[0] + delta))  # các trang chọn được gom lại thành một khối
        new_items = rest[:pos] + moving + rest[pos:]
        if [it.uid for it in new_items] == [it.uid for it in items]:
            return
        self._commit(new_items, uids, "Đã di chuyển trang.")

    def move_selected_to(self, position: int) -> None:
        rows = self._require_selection()
        if not rows:
            return
        items = self._snapshot()
        uids = [items[r].uid for r in rows]
        moving = [items[r] for r in rows]
        rest = [it for i, it in enumerate(items) if i not in set(rows)]
        pos = max(0, min(len(rest), position - 1))
        self._commit(rest[:pos] + moving + rest[pos:], uids, f"Đã chuyển {len(rows)} trang tới vị trí {position}.")

    def reverse_selected(self) -> None:
        rows = self._selected_rows()
        items = self._snapshot()
        if len(rows) >= 2:
            picked = [items[r] for r in rows][::-1]
            for r, it in zip(rows, picked):
                items[r] = it
            uids = [it.uid for it in picked]
            msg = f"Đã đảo thứ tự {len(rows)} trang đang chọn."
        else:
            items = items[::-1]
            uids = []
            msg = "Đã đảo thứ tự toàn bộ tài liệu."
        self._commit(items, uids, msg)

    def toggle_split(self) -> None:
        rows = self._require_selection()
        if not rows:
            return
        items = self._snapshot()
        r = rows[-1]
        if r >= len(items) - 1:
            self.status_lbl.setText("Không thể đặt điểm cắt sau trang cuối.")
            return
        items[r].split_after = not items[r].split_after
        state = "Đã đặt" if items[r].split_after else "Đã bỏ"
        self._commit(items, [items[r].uid], f"{state} điểm cắt sau trang {r + 1}.")

    def clear_splits(self) -> None:
        items = self._snapshot()
        for it in items:
            it.split_after = False
        self._commit(items, [], "Đã bỏ mọi điểm cắt.")

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(self._snapshot())
        self._items = self._undo.pop()
        self._reload()
        self.status_lbl.setText("Đã hoàn tác.")

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(self._snapshot())
        self._items = self._redo.pop()
        self._reload()
        self.status_lbl.setText("Đã làm lại.")

    def add_files(self, paths: Optional[Sequence[str]] = None) -> int:
        """Thêm trang của các tệp PDF khác (sau trang đang chọn, hoặc cuối lưới); trả về số trang đã thêm."""
        if paths is None:
            chosen, _ = QFileDialog.getOpenFileNames(self, "Chọn tệp PDF cần ghép", "", "Tài liệu PDF (*.pdf)")
            paths = chosen
        if not paths:
            return 0
        new_items: List[_Item] = []
        for p in paths:
            key = str(Path(p).resolve())
            src = self._sources.get(key)
            if src is None:
                doc = self._open_pdf(Path(key))
                if doc is None:
                    continue
                src = self._add_source(key, doc, Path(key).name, owned=True)
            new_items.extend(_Item(next(_uids), r) for r in po.refs_for_document(key, src.doc.page_count))
        if not new_items:
            return 0
        rows = self._selected_rows()
        at = (rows[-1] + 1) if rows else len(self._items)
        items = self._snapshot()
        items[at:at] = new_items
        self._commit(items, [it.uid for it in new_items], f"Đã thêm {len(new_items)} trang từ {len(paths)} tệp.")
        return len(new_items)

    def _open_pdf(self, path: Path) -> Optional[fitz.Document]:
        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            QMessageBox.warning(self, "Không mở được tệp", f"{path.name}:\n{exc}")
            return None
        if not doc.is_pdf:
            doc.close()
            QMessageBox.warning(self, "Không phải PDF", path.name)
            return None
        if doc.needs_pass:
            pwd, ok = QInputDialog.getText(self, "Tệp PDF có mật khẩu", f"Nhập mật khẩu để mở '{path.name}':",
                                           QLineEdit.EchoMode.Password)
            if not ok or not doc.authenticate(pwd):
                doc.close()
                if ok:
                    QMessageBox.warning(self, "Sai mật khẩu", path.name)
                return None
        return doc

    def _context_menu(self, pos) -> None:
        item = self.grid.itemAt(pos)
        if item is not None and not item.isSelected():
            self.grid.clearSelection()
            item.setSelected(True)
        menu = QMenu(self)
        has_sel = bool(self.grid.selectedItems())
        acts = [
            ("↻ Xoay phải 90°", lambda: self.rotate_selected(90), has_sel),
            ("↺ Xoay trái 90°", lambda: self.rotate_selected(-90), has_sel),
            ("⧉ Nhân bản", self.duplicate_selected, has_sel),
            ("🗑 Xoá", self.delete_selected, has_sel),
            None,
            ("Di chuyển tới vị trí…", self._ask_move_to, has_sel),
            ("＋ Chèn trang trắng sau", self.insert_blank, True),
            ("＋ Chèn tệp PDF sau…", self.add_files, True),
            None,
            ("✂ Đặt / bỏ điểm cắt sau trang này", self.toggle_split, has_sel),
            ("Bỏ mọi điểm cắt", self.clear_splits, any(it.split_after for it in self._items)),
            None,
            ("📤 Trích các trang đã chọn…", self.extract_selected, has_sel),
        ]
        for spec in acts:
            if spec is None:
                menu.addSeparator()
                continue
            text, fn, enabled = spec
            act = menu.addAction(text)
            act.setEnabled(enabled)
            act.triggered.connect(lambda _c=False, f=fn: f())
        menu.exec(self.grid.viewport().mapToGlobal(pos))

    def _ask_move_to(self) -> None:
        pos, ok = QInputDialog.getInt(self, "Di chuyển trang", "Đưa các trang đang chọn tới vị trí:",
                                      1, 1, max(1, self.page_count))
        if ok:
            self.move_selected_to(pos)

    # ─── Lưu kết quả ──────────────────────────────────────────────────────

    def _first_stem(self) -> Tuple[Path, str]:
        for it in self._items:
            if not it.ref.is_blank:
                p = Path(it.ref.source)
                return p.parent, p.stem
        return Path.home(), "tai_lieu"

    def _docs(self) -> Dict[str, fitz.Document]:
        return {k: s.doc for k, s in self._sources.items()}

    def _bookmark_titles(self, refs: Sequence[po.PageRef]) -> Optional[Dict[str, str]]:
        used = {r.source for r in refs if not r.is_blank}
        return {k: Path(k).stem for k in used} if len(used) > 1 else None

    def _ask_save_path(self, title: str, default_name: str) -> Optional[Path]:
        folder, _stem = self._first_stem()
        chosen, _ = QFileDialog.getSaveFileName(self, title, str(folder / default_name), "Tài liệu PDF (*.pdf)")
        if not chosen:
            return None
        path = Path(chosen)
        return path if path.suffix.lower() == ".pdf" else path.with_suffix(".pdf")

    def _write(self, refs: Sequence[po.PageRef], target: Path) -> Optional[str]:
        """Dựng & ghi tệp; trả về "file" / "overwrite" khi thành công, None khi lỗi hoặc bị huỷ."""
        try:
            doc = po.assemble_pdf(refs, self._docs(), bookmark_titles=self._bookmark_titles(refs))
        except Exception as exc:
            QMessageBox.critical(self, "Không dựng được tệp PDF", str(exc))
            return None
        try:
            resolved = str(target.resolve())
            if self._is_locked(target):
                data = doc.tobytes(garbage=3, deflate=True)
                if self._overwrite_handler is not None and self._overwrite_handler(target, data):
                    return "overwrite"
                return None
            owned = self._sources.get(resolved)
            if owned is not None and owned.owned and not owned.doc.is_closed:
                owned.doc.close()  # tài liệu kết quả đã độc lập — đóng tệp nguồn để ghi đè được
            po.save_pdf(doc, target)
            return "file"
        except Exception as exc:
            QMessageBox.critical(self, "Không lưu được tệp", f"{target}:\n{exc}")
            return None
        finally:
            doc.close()

    def save_all(self) -> None:
        if not self._items:
            return
        folder, stem = self._first_stem()
        suffix = {"combine": "_gop", "extract": "_trich", "split": "_tach"}.get(self.mode, "_da_sap_xep")
        target = self._ask_save_path("Lưu PDF", f"{stem}{suffix}.pdf")
        if target is None:
            return
        kind = self._write(self.refs(), target)
        if kind:
            self.result_paths = [target]
            self.result_kind = kind
            self.accept()

    def extract_selected(self) -> None:
        rows = self._require_selection()
        if not rows:
            return
        _folder, stem = self._first_stem()
        target = self._ask_save_path("Trích trang đã chọn", f"{stem}_trich.pdf")
        if target is None:
            return
        kind = self._write([self._items[r].ref for r in rows], target)
        if kind == "overwrite":
            self.result_paths, self.result_kind = [target], kind
            self.accept()
        elif kind:
            self.status_lbl.setText(f"Đã trích {len(rows)} trang → {target}")

    def open_split_dialog(self) -> None:
        if not self._items:
            return
        dlg = _SplitDialog(self, self.page_count, len(self.marker_parts()))
        if not dlg.exec():
            return
        kind, value = dlg.result_spec
        refs = self.refs()
        if kind == "markers":
            parts = self.marker_parts()
        elif kind == "ranges":
            parts = [[refs[i] for i in part] for part in po.parse_split_ranges(str(value), len(refs))]
        else:
            parts = po.split_refs(refs, every=int(value))
        self.export_parts(parts)

    def export_parts(self, parts: Optional[List[List[po.PageRef]]] = None) -> None:
        parts = parts if parts is not None else self.marker_parts()
        if len(parts) < 1:
            return
        folder, stem = self._first_stem()
        default_dir = folder / f"{stem}_tach"
        chosen = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu các phần", str(default_dir.parent))
        if not chosen:
            return
        out_dir = Path(chosen)
        names = po.part_file_names(stem, len(parts))
        locked = [n for n in names if self._is_locked(out_dir / n)]
        if locked:
            QMessageBox.warning(self, "Tệp đang mở", "Hãy đóng các tệp đang mở trùng tên:\n" + "\n".join(locked))
            return
        existing = [n for n in names if (out_dir / n).exists()]
        if existing and QMessageBox.question(
            self, "Ghi đè tệp?", f"{len(existing)} tệp đã tồn tại trong thư mục, ghi đè?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            res = po.write_parts(parts, self._docs(), out_dir, stem)
        except Exception as exc:
            QMessageBox.critical(self, "Không tách được tệp", str(exc))
            return
        self.result_paths = [Path(p) for p in res.output_paths]
        self.result_kind = "parts"
        self.accept()

    # ─── Đóng hộp thoại ───────────────────────────────────────────────────

    def done(self, result: int) -> None:  # noqa: D401 - API Qt
        for src in self._sources.values():
            if src.owned and not src.doc.is_closed:
                src.doc.close()
        self._thumbs.clear()
        self._rot_thumbs.clear()
        super().done(result)

    @property
    def open_results(self) -> bool:
        return self.chk_open.isChecked()
