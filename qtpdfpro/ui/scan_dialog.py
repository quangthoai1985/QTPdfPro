"""Giao diện Scan tài liệu tích hợp từ PDFScanner (WIA đa thiết bị, Mặt kính / ADF, tiền xử lý nền trắng chữ rõ)."""

from __future__ import annotations

import json
import logging
from copy import copy
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

import cv2
import numpy as np
from PySide6.QtCore import (
    QObject,
    QPointF,
    QRectF,
    QRunnable,
    QSignalBlocker,
    QSize,
    QStandardPaths,
    Qt,
    QThread,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core import scanner, scanner_wia
from qtpdfpro.core.settings import AppSettings, get_data_dir
from qtpdfpro.ui import icons
from qtpdfpro.ui.theme import theme_tokens

log = logging.getLogger(__name__)

PAGE_ID = Qt.ItemDataRole.UserRole
KIND_LABELS = {"gray": "xám", "bw": "đen trắng", "color": "màu"}
PROCESSING_MSG = "Đang xử lý ảnh…"
FORMAT_FILTERS = {
    "pdf": "PDF (*.pdf)",
    "jpg": "Ảnh JPG (*.jpg *.jpeg)",
    "png": "Ảnh PNG (*.png)",
    "tif": "Ảnh TIFF (*.tif *.tiff)",
}
SUFFIX_FORMATS = {
    ".pdf": "pdf",
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".png": "png",
    ".tif": "tif",
    ".tiff": "tif",
}
MODE_HINTS = {
    "single": "Bấm Scan là lưu ngay thành file vào thư mục đã chọn.",
    "multi": "Các trang được giữ tạm để xem, xoay, sắp xếp. Xong bấm «Hoàn tất & lưu PDF» hoặc chèn vào tab đang mở.",
}
SCAN_LABELS = {"preview": "Đang xem trước", "single": "Đang scan", "multi": "Đang scan trang"}
OUTPUT_LABELS = [("gray", "Xám"), ("bw", "Đen trắng"), ("color", "Màu")]
MODE_LABELS = [("gray", "Xám"), ("color", "Màu")]
IMAGE_FORMATS = [("jpg", "JPG"), ("png", "PNG"), ("tif", "TIFF")]
PANEL_FIELDS = (
    "white_point",
    "gamma",
    "sharpen",
    "sauvola_k",
    "deskew",
    "speck_isolation_mm",
    "edge_margin_mm",
)

HANDLE_PX = 8
MIN_CROP_PX = 10
FIT_MARGIN = 24
CURSORS = {
    "tl": Qt.CursorShape.SizeFDiagCursor,
    "br": Qt.CursorShape.SizeFDiagCursor,
    "tr": Qt.CursorShape.SizeBDiagCursor,
    "bl": Qt.CursorShape.SizeBDiagCursor,
    "l": Qt.CursorShape.SizeHorCursor,
    "r": Qt.CursorShape.SizeHorCursor,
    "t": Qt.CursorShape.SizeVerCursor,
    "b": Qt.CursorShape.SizeVerCursor,
    "move": Qt.CursorShape.SizeAllCursor,
    None: Qt.CursorShape.CrossCursor,
}


# ─── Tiện ích ảnh & đường dẫn ────────────────────────────────────────────────


def to_qimage(img: np.ndarray) -> QImage:
    """Chuyển numpy (xám 2D hoặc BGR) sang `QImage` độc lập."""
    if img.ndim == 2:
        arr = np.ascontiguousarray(img)
        h, w = arr.shape
        fmt = QImage.Format.Format_Grayscale8
    else:
        arr = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        h, w = arr.shape[:2]
        fmt = QImage.Format.Format_RGB888
    return QImage(arr.data, w, h, arr.strides[0], fmt).copy()


def make_thumbnail(img: np.ndarray, height: int = 160) -> QPixmap:
    h, w = img.shape[:2]
    scale = height / max(1, h)
    small = cv2.resize(img, (max(1, round(w * scale)), height), interpolation=cv2.INTER_AREA)
    return QPixmap.fromImage(to_qimage(small))


def default_save_folder() -> str:
    docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return str(Path(docs or Path.home()) / "QTPdfPro_Scan")


def _unique_path(folder: Path, stem: str, ext: str) -> Path:
    path = folder / f"{stem}{ext}"
    i = 2
    while path.exists():
        path = folder / f"{stem}_{i}{ext}"
        i += 1
    return path


def _state_file_path() -> Path:
    return get_data_dir() / "scanner_state.json"


# ─── Widget dùng chung ───────────────────────────────────────────────────────


class _Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, options: list[tuple], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("scanSegmented")
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: Dict[str, QPushButton] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        for opt in options:
            key, label = opt[0], opt[1]
            b = QPushButton(label)
            b.setObjectName("scanSegment")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if len(opt) > 2:
                icons.bind(b, opt[2], 15)
                b.setIconSize(QSize(15, 15))
            self._group.addButton(b)
            self._buttons[key] = b
            lay.addWidget(b)
            b.clicked.connect(lambda _c=False, k=key: self.changed.emit(k))
        next(iter(self._buttons.values())).setChecked(True)

    def value(self) -> Optional[str]:
        for key, b in self._buttons.items():
            if b.isChecked():
                return key
        return None

    def set_value(self, key: str) -> None:
        if key in self._buttons:
            with QSignalBlocker(self._group):
                self._buttons[key].setChecked(True)

    def select(self, key: str) -> None:
        if key in self._buttons and self.value() != key and self._buttons[key].isEnabled():
            self._buttons[key].setChecked(True)
            self.changed.emit(key)

    def set_label(self, key: str, text: str) -> None:
        self._buttons[key].setText(text)

    def set_option_enabled(self, key: str, enabled: bool) -> None:
        self._buttons[key].setEnabled(enabled)

    def button(self, key: str) -> QPushButton:
        return self._buttons[key]


class _ToggleSwitch(QCheckBox):
    TRACK_W, TRACK_H = 34, 20

    def __init__(self, text: str = "", tokens_fn: Optional[Callable[[], dict]] = None, parent=None) -> None:
        super().__init__(text, parent)
        self._tokens_fn = tokens_fn or (lambda: theme_tokens("dark"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        return QSize(self.TRACK_W + 10 + fm.horizontalAdvance(self.text()), max(self.TRACK_H + 4, fm.height() + 6))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, event) -> None:  # noqa: N802
        tok = self._tokens_fn()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        enabled, on = self.isEnabled(), self.isChecked()
        y = (self.height() - self.TRACK_H) / 2
        track = QRectF(1, y, self.TRACK_W, self.TRACK_H)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(tok["accent"] if (on and enabled) else tok["border_strong"]))
        p.drawRoundedRect(track, self.TRACK_H / 2, self.TRACK_H / 2)
        d = self.TRACK_H - 6
        x = track.right() - d - 3 if on else track.left() + 3
        p.setBrush(QColor(tok["on_accent"] if on else tok["card"]))
        p.drawEllipse(QRectF(x, y + 3, d, d))
        p.setPen(QColor(tok["text"] if enabled else tok["faint"]))
        p.drawText(
            QRectF(self.TRACK_W + 10, 0, self.width() - self.TRACK_W - 10, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )
        p.end()


class _CardHeader(QWidget):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class _Card(QFrame):
    toggled = Signal(bool)

    def __init__(self, title: str, icon_name: Optional[str] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("scanCard")
        self._icon_name = icon_name
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 10, 10)
        outer.setSpacing(6)
        self.header = _CardHeader()
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setToolTip("Bấm để thu gọn / mở rộng")
        self.header.clicked.connect(lambda: self.set_expanded(not self.is_expanded(), emit=True))
        head = QHBoxLayout(self.header)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(16, 16)
        if icon_name:
            head.addWidget(self._icon_label)
        self.title = QLabel(title)
        self.title.setObjectName("scanCardTitle")
        head.addWidget(self.title)
        head.addStretch()
        self._chevron = QLabel()
        self._chevron.setFixedSize(16, 16)
        head.addWidget(self._chevron)
        outer.addWidget(self.header)

        self.content = QWidget()
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 2, 2, 0)
        self.body.setSpacing(7)
        outer.addWidget(self.content)
        self.refresh_icon()

    def is_expanded(self) -> bool:
        return not self.content.isHidden()

    def set_expanded(self, expanded: bool, emit: bool = False) -> None:
        self.content.setVisible(expanded)
        self.refresh_icon()
        if emit:
            self.toggled.emit(expanded)

    def refresh_icon(self) -> None:
        if self._icon_name:
            self._icon_label.setPixmap(icons.icon(self._icon_name, size=16).pixmap(16, 16))
        chev_name = "chevron-up" if self.is_expanded() else "chevron-down"
        self._chevron.setPixmap(icons.icon(chev_name, size=15).pixmap(15, 15))


def _field_box(label: str, widget_or_layout, hint: Optional[str] = None) -> QWidget:
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(3)
    lab = QLabel(label)
    lab.setObjectName("scanFieldLabel")
    v.addWidget(lab)
    if isinstance(widget_or_layout, QWidget):
        v.addWidget(widget_or_layout)
    else:
        v.addLayout(widget_or_layout)
    box.label = lab  # type: ignore[attr-defined]
    box.hint = None  # type: ignore[attr-defined]
    if hint is not None:
        h = QLabel(hint)
        h.setObjectName("scanHint")
        h.setWordWrap(True)
        v.addWidget(h)
        box.hint = h  # type: ignore[attr-defined]
    return box


class _LabeledSlider(QWidget):
    valueChanged = Signal(float)

    def __init__(
        self,
        label: str,
        minimum: float,
        maximum: float,
        step: float,
        decimals: int = 2,
        tooltip: str = "",
    ) -> None:
        super().__init__()
        self._min, self._step, self._decimals = minimum, step, decimals
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, round((maximum - minimum) / step))
        self._slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._label = QLabel(label)
        self._value_label = QLabel()
        self._value_label.setObjectName("scanHint")
        self._value_label.setMinimumWidth(36)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top = QHBoxLayout()
        top.addWidget(self._label)
        top.addStretch()
        top.addWidget(self._value_label)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 0)
        lay.setSpacing(2)
        lay.addLayout(top)
        lay.addWidget(self._slider)
        self.setToolTip(tooltip)
        self._slider.valueChanged.connect(self._changed)
        self._changed()

    def value(self) -> float:
        return round(self._min + self._slider.value() * self._step, self._decimals)

    def setValue(self, value: float) -> None:
        with QSignalBlocker(self._slider):
            self._slider.setValue(round((value - self._min) / self._step))
        self._value_label.setText(f"{self.value():.{self._decimals}f}")

    def _changed(self) -> None:
        self._value_label.setText(f"{self.value():.{self._decimals}f}")
        self.valueChanged.emit(self.value())


class _ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        super().setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, max(40, self.width())))


class _Banner(QFrame):
    ICONS = {"success": "badge-check", "error": "info", "info": "info"}
    visibilityChanged = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("scanBanner")
        self.setProperty("kind", "info")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 8, 8, 8)
        h.setSpacing(10)
        self._icon = QLabel()
        self._icon.setFixedSize(20, 20)
        self._thumb = QLabel()
        self._thumb.hide()
        text = QVBoxLayout()
        text.setSpacing(0)
        self.title = QLabel()
        self.title.setObjectName("scanCardTitle")
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QLabel()
        self.detail.setObjectName("scanHint")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.addWidget(self.title)
        text.addWidget(self.detail)
        self._actions = QHBoxLayout()
        self._actions.setSpacing(6)
        close = QToolButton()
        icons.bind(close, "x", 15)
        close.setToolTip("Đóng")
        close.clicked.connect(self.hide)
        h.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(self._thumb)
        h.addLayout(text, 1)
        h.addLayout(self._actions)
        h.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def setVisible(self, visible: bool) -> None:
        super().setVisible(visible)
        self.visibilityChanged.emit(visible)

    def show_message(self, kind: str, title: str, detail: str = "", actions=(), thumb=None, timeout: int = 20000) -> None:
        self.setProperty("kind", kind)
        self.style().unpolish(self)
        self.style().polish(self)
        self._icon.setPixmap(icons.icon(self.ICONS.get(kind, "info"), size=20).pixmap(20, 20))
        self.title.setText(title)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        if thumb is not None and not thumb.isNull():
            self._thumb.setPixmap(thumb.scaledToHeight(44, Qt.TransformationMode.SmoothTransformation))
            self._thumb.show()
        else:
            self._thumb.setPixmap(QPixmap())
            self._thumb.hide()
        while self._actions.count():
            w = self._actions.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for label, slot in actions:
            b = QToolButton()
            b.setObjectName("scanSecondaryBtn")
            b.setText(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            self._actions.addWidget(b)
        self.show()
        if timeout:
            self._timer.start(timeout)
        else:
            self._timer.stop()


def _tool_button(action: QAction, variant: Optional[str] = None, text: bool = True, expand: bool = False) -> QToolButton:
    b = QToolButton()
    if variant == "primary":
        b.setObjectName("primaryConvertBtn")
    elif variant == "accent":
        b.setObjectName("scanAccentBtn")
    elif variant == "secondary":
        b.setObjectName("scanSecondaryBtn")
    elif variant == "danger":
        b.setObjectName("scanDangerBtn")
    else:
        b.setObjectName("fnToolBtn")
    b.setDefaultAction(action)
    b.setToolButtonStyle(
        Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text else Qt.ToolButtonStyle.ToolButtonIconOnly
    )
    b.setIconSize(QSize(16, 16))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if expand:
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return b


def _vline() -> QFrame:
    line = QFrame()
    line.setObjectName("fnSep")
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFixedWidth(9)
    line.setFixedHeight(20)
    return line


# ─── Khung xem ảnh & kéo khung cắt kiểu VueScan ───────────────────────────────


class ScanImageView(QGraphicsView):
    cropChanged = Signal(QRectF, bool)
    zoomChanged = Signal(float)

    def __init__(
        self,
        placeholder: tuple[str, str, str] = ("", "", ""),
        tokens_fn: Optional[Callable[[], dict]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._tokens_fn = tokens_fn or (lambda: theme_tokens("dark"))
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(self._pixmap_item)

        self._placeholder = placeholder
        self._fit_mode = True
        self._crop_enabled = False
        self._crop: Optional[QRectF] = None
        self._px_per_mm: Optional[float] = None
        self._drag = None

        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

    def has_image(self) -> bool:
        return not self._pixmap_item.pixmap().isNull()

    def image_rect(self) -> QRectF:
        return self._pixmap_item.boundingRect()

    def set_image(self, qimage: QImage, keep_view: bool = False) -> None:
        pm = QPixmap.fromImage(qimage)
        same_size = self.has_image() and pm.size() == self._pixmap_item.pixmap().size()
        self._pixmap_item.setPixmap(pm)
        m = max(pm.width(), pm.height()) * 0.04
        self._scene.setSceneRect(QRectF(pm.rect()).adjusted(-m, -m, m, m))
        if not (keep_view and same_size) or self._fit_mode:
            self.fit()
        self.viewport().update()

    def clear_image(self) -> None:
        self._pixmap_item.setPixmap(QPixmap())
        self._scene.setSceneRect(QRectF())
        self.viewport().update()

    def set_placeholder(self, placeholder: tuple[str, str, str]) -> None:
        self._placeholder = placeholder
        self.viewport().update()

    def zoom(self) -> float:
        return self.transform().m11()

    def fit(self) -> None:
        self._fit_mode = True
        if self.has_image():
            r = self.image_rect()
            vw = self.viewport().width() - 2 * FIT_MARGIN
            vh = self.viewport().height() - 2 * FIT_MARGIN
            if vw > 0 and vh > 0:
                k = min(vw / max(1.0, r.width()), vh / max(1.0, r.height()))
                self.resetTransform()
                self.scale(k, k)
                self.centerOn(self._pixmap_item)
        self.zoomChanged.emit(self.zoom())

    def zoom_actual(self) -> None:
        self._fit_mode = False
        self.resetTransform()
        self.zoomChanged.emit(self.zoom())

    def zoom_by(self, factor: float) -> None:
        if not 0.02 <= self.zoom() * factor <= 16:
            return
        self._fit_mode = False
        self.scale(factor, factor)
        self.zoomChanged.emit(self.zoom())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit_mode:
            self.fit()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self.has_image():
            self.zoom_by(1.25 if event.angleDelta().y() > 0 else 0.8)

    def set_crop_enabled(self, enabled: bool, px_per_mm: Optional[float] = None) -> None:
        self._crop_enabled = enabled
        self._px_per_mm = px_per_mm
        self.setDragMode(QGraphicsView.DragMode.NoDrag if enabled else QGraphicsView.DragMode.ScrollHandDrag)
        self.setMouseTracking(enabled)

    def set_crop(self, rect: Optional[QRectF]) -> None:
        self._crop = QRectF(rect) if rect is not None and not rect.isEmpty() else None
        self.viewport().update()

    def crop(self) -> Optional[QRectF]:
        return QRectF(self._crop) if self._crop is not None else None

    def _hit(self, view_pos: QPointF) -> Optional[str]:
        if self._crop is None:
            return None
        r = self.mapFromScene(self._crop).boundingRect()
        x, y = view_pos.x(), view_pos.y()
        near_l, near_r = abs(x - r.left()) <= HANDLE_PX, abs(x - r.right()) <= HANDLE_PX
        near_t, near_b = abs(y - r.top()) <= HANDLE_PX, abs(y - r.bottom()) <= HANDLE_PX
        in_x = r.left() - HANDLE_PX <= x <= r.right() + HANDLE_PX
        in_y = r.top() - HANDLE_PX <= y <= r.bottom() + HANDLE_PX
        if not (in_x and in_y):
            return None
        vertical = "t" if near_t else "b" if near_b else ""
        horizontal = "l" if near_l else "r" if near_r else ""
        if vertical or horizontal:
            return vertical + horizontal
        return "move"

    def _scene_pos(self, event) -> QPointF:
        return self.mapToScene(event.position().toPoint())

    def _clamped(self, rect: QRectF) -> QRectF:
        return rect.normalized().intersected(self.image_rect())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._crop_enabled and self.has_image() and event.button() == Qt.MouseButton.LeftButton:
            mode = self._hit(event.position()) or "new"
            self._drag = (mode, self._scene_pos(event), QRectF(self._crop) if self._crop else None)
            if mode == "new":
                p = self._scene_pos(event)
                self._crop = QRectF(p, p)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is None:
            if self._crop_enabled and self.has_image():
                self.viewport().setCursor(CURSORS[self._hit(event.position())])
            super().mouseMoveEvent(event)
            return
        mode, start, orig = self._drag
        p = self._scene_pos(event)
        bounds = self.image_rect()
        if mode == "new":
            self._crop = self._clamped(QRectF(start, p))
        elif mode == "move":
            d = p - start
            r = orig.translated(d)
            dx = max(bounds.left() - r.left(), 0.0) + min(bounds.right() - r.right(), 0.0)
            dy = max(bounds.top() - r.top(), 0.0) + min(bounds.bottom() - r.bottom(), 0.0)
            self._crop = r.translated(dx, dy)
        else:
            r = QRectF(orig)
            x = min(max(p.x(), bounds.left()), bounds.right())
            y = min(max(p.y(), bounds.top()), bounds.bottom())
            if "l" in mode:
                r.setLeft(min(x, r.right() - MIN_CROP_PX))
            if "r" in mode:
                r.setRight(max(x, r.left() + MIN_CROP_PX))
            if "t" in mode:
                r.setTop(min(y, r.bottom() - MIN_CROP_PX))
            if "b" in mode:
                r.setBottom(max(y, r.top() + MIN_CROP_PX))
            self._crop = r
        self.viewport().update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            mode, _, orig = self._drag
            self._drag = None
            if self._crop is None or self._crop.width() < MIN_CROP_PX or self._crop.height() < MIN_CROP_PX:
                self._crop = orig
            elif mode != "move" or self._crop != orig:
                self.cropChanged.emit(QRectF(self._crop), mode != "move")
            self.viewport().update()
            return
        super().mouseReleaseEvent(event)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        tok = self._tokens_fn()
        painter.save()
        painter.resetTransform()
        painter.fillRect(self.viewport().rect(), QColor(tok["page"]))
        if self.has_image():
            r = QRectF(self.mapFromScene(self.image_rect()).boundingRect())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            for i, alpha in enumerate((30, 20, 13, 8, 4)):
                painter.setBrush(QColor(0, 0, 0, alpha))
                painter.drawRoundedRect(r.adjusted(-i - 1, -i, i + 1, i + 2), i + 2, i + 2)
        painter.restore()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        if not self.has_image():
            self._draw_placeholder(painter)
            return
        if self._crop is None or not self._crop_enabled:
            return
        tok = self._tokens_fn()
        outside = QPainterPath()
        outside.addRect(self.image_rect())
        inner = QPainterPath()
        inner.addRect(self._crop)
        painter.fillPath(outside.subtracted(inner), QColor(0, 0, 0, 110))

        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(tok["accent"])
        r = QRectF(self.mapFromScene(self._crop).boundingRect())
        painter.setPen(QPen(accent, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)
        painter.setBrush(QColor(tok["card"]))
        for hx in (r.left(), r.right()):
            for hy in (r.top(), r.bottom()):
                painter.drawEllipse(QPointF(hx, hy), 5, 5)
        cx, cy = r.center().x(), r.center().y()
        for x, y, w, h in (
            (cx - 9, r.top() - 3, 18, 6),
            (cx - 9, r.bottom() - 3, 18, 6),
            (r.left() - 3, cy - 9, 6, 18),
            (r.right() - 3, cy - 9, 6, 18),
        ):
            painter.drawRoundedRect(QRectF(x, y, w, h), 3, 3)
        if self._px_per_mm:
            w_mm = self._crop.width() / self._px_per_mm
            h_mm = self._crop.height() / self._px_per_mm
            text = f"{w_mm:.0f} × {h_mm:.0f} mm"
            font = QFont(self.font())
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            fm = painter.fontMetrics()
            box = QRectF(r.left() + 10, r.top() + 10, fm.horizontalAdvance(text) + 18, fm.height() + 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawRoundedRect(box, box.height() / 2, box.height() / 2)
            painter.setPen(QColor(tok["on_accent"]))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def _draw_placeholder(self, painter: QPainter) -> None:
        icon_name, title, text = self._placeholder
        if not (title or text):
            return
        tok = self._tokens_fn()
        painter.save()
        painter.resetTransform()
        area = self.viewport().rect().adjusted(32, 32, -32, -32)
        width = min(area.width(), 460)
        flags = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap
        title_font = QFont(self.font())
        title_font.setPointSize(13)
        title_font.setBold(True)
        body_font = QFont(self.font())
        body_font.setPointSize(10)
        painter.setFont(body_font)
        body_h = painter.fontMetrics().boundingRect(0, 0, width, 1000, flags, text).height() if text else 0
        painter.setFont(title_font)
        title_h = painter.fontMetrics().boundingRect(0, 0, width, 1000, flags, title).height() if title else 0
        icon_px = 48 if icon_name else 0
        y = area.center().y() - (icon_px + 16 + title_h + 8 + body_h) / 2
        x = area.center().x() - width / 2
        if icon_name:
            pm = icons.icon(icon_name, tok["muted"], icon_px).pixmap(icon_px, icon_px)
            painter.drawPixmap(int(area.center().x() - icon_px / 2), int(y), pm)
        y += icon_px + 14
        painter.setPen(QColor(tok["text"]))
        painter.drawText(QRectF(x, y, width, title_h), flags, title)
        y += title_h + 8
        painter.setFont(body_font)
        painter.setPen(QColor(tok["muted"]))
        painter.drawText(QRectF(x, y, width, body_h + 4), flags, text)
        painter.restore()


# ─── Thẻ thiết lập bên trái ───────────────────────────────────────────────────


def _combo(items: list[tuple]) -> QComboBox:
    combo = QComboBox()
    for label, data in items:
        combo.addItem(label, data)
    combo.setCursor(Qt.CursorShape.PointingHandCursor)
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return combo


def _select_data(combo: QComboBox, data) -> None:
    idx = combo.findData(data)
    if idx >= 0:
        combo.setCurrentIndex(idx)


class ScanSettingsPanel(QWidget):
    scanOptionsChanged = Signal()
    areaChanged = Signal(str)
    processingChanged = Signal()
    applyAllRequested = Signal()
    refreshDevicesRequested = Signal()
    commonDialogRequested = Signal()
    saveOptionsChanged = Signal()

    def __init__(self, tokens_fn: Callable[[], dict], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens_fn = tokens_fn
        self._base = scanner.Settings()
        self._preferred_device: Optional[str] = None
        self._save_folder = default_save_folder()

        # ── 1. Máy scan ──
        self.device = _combo([("Đang tìm máy scan…", None)])
        self.refresh_btn = QToolButton()
        icons.bind(self.refresh_btn, "refresh-cw", 15)
        self.refresh_btn.setToolTip("Tìm lại máy scan")
        self.refresh_btn.clicked.connect(self.refreshDevicesRequested)
        dev_row = QHBoxLayout()
        dev_row.setSpacing(4)
        dev_row.addWidget(self.device, 1)
        dev_row.addWidget(self.refresh_btn)

        self.source = _combo([(label, key) for key, label in scanner.SCAN_SOURCES])
        self.source.setToolTip("Chọn Tự động, Mặt kính (Flatbed) hoặc Khay nạp giấy tự động (ADF).")

        self.dpi = _combo([(f"{d} dpi", d) for d in scanner.DPI_CHOICES])
        _select_data(self.dpi, 300)
        self.dpi.setToolTip("300 dpi là chuẩn cho văn bản; 400–600 dpi cho chữ nhỏ.")

        self.scan_mode = _Segmented(MODE_LABELS)
        self.scan_mode.setToolTip("Chọn Màu khi tài liệu có dấu đỏ hoặc chữ ký màu.")

        self.area = _combo([(label, key) for key, (label, _) in scanner.PAPER_SIZES.items()])
        _select_data(self.area, "a4")

        self.common_dlg_btn = QPushButton("Quét qua hộp thoại Windows / hãng…")
        self.common_dlg_btn.setObjectName("scanSecondaryBtn")
        self.common_dlg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.common_dlg_btn.setToolTip("Mở trình quét chuẩn của Windows nếu máy scan cần hộp thoại riêng của hãng")
        self.common_dlg_btn.clicked.connect(self.commonDialogRequested)

        scan_card = _Card("Máy scan", "scan-line")
        scan_card.body.addWidget(_field_box("Thiết bị (WIA)", dev_row))
        scan_card.body.addWidget(_field_box("Nguồn giấy", self.source))
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.addWidget(_field_box("Độ phân giải", self.dpi), 0, 0)
        grid.addWidget(_field_box("Chế độ màu", self.scan_mode), 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        scan_card.body.addLayout(grid)
        scan_card.body.addWidget(_field_box("Khổ giấy", self.area))
        scan_card.body.addWidget(self.common_dlg_btn)

        # ── 2. Xử lý ảnh ──
        self.preset = QComboBox()
        self.preset.setCursor(Qt.CursorShape.PointingHandCursor)
        for p in scanner.PRESETS:
            self.preset.addItem(p.name)
            self.preset.setItemData(self.preset.count() - 1, p.description, Qt.ItemDataRole.ToolTipRole)
        self.preset.addItem(scanner.CUSTOM)
        self.preset_field = _field_box("Mẫu có sẵn", self.preset, hint=" ")
        self.preset_desc = self.preset_field.hint  # type: ignore[attr-defined]

        self.output = _Segmented(OUTPUT_LABELS)
        self.white = _LabeledSlider("Điểm trắng", 0.70, 1.00, 0.01, tooltip="Sáng hơn mức này thành trắng tinh.")
        self.gamma = _LabeledSlider("Độ đậm chữ", 0.60, 2.50, 0.05, tooltip="Lớn hơn 1 làm chữ đậm hơn.")
        self.sharpen = _LabeledSlider("Làm nét", 0.0, 2.0, 0.1, decimals=1)
        self.k = _LabeledSlider("Độ mảnh nét (đen trắng)", 0.05, 0.50, 0.01)
        self.deskew = _ToggleSwitch("Tự chỉnh nghiêng trang", tokens_fn)
        self.specks = _ToggleSwitch("Xoá chấm bụi", tokens_fn)
        self.edges = _ToggleSwitch("Xoá vệt tối ở mép giấy", tokens_fn)

        self.apply_all = QToolButton()
        self.apply_all.setText("Áp dụng cho mọi trang")
        self.apply_all.setObjectName("scanSecondaryBtn")
        self.apply_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_all.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.reset = QToolButton()
        self.reset.setText("Mặc định")
        self.reset.setObjectName("scanSecondaryBtn")
        self.reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.proc_card = _Card("Xử lý ảnh", "sliders-horizontal")
        pb = self.proc_card.body
        pb.addWidget(self.preset_field)
        pb.addWidget(_field_box("Xuất ra file", self.output))
        for w in (self.white, self.gamma, self.sharpen, self.k):
            pb.addWidget(w)
        for w in (self.deskew, self.specks, self.edges):
            pb.addWidget(w)
        row_btn = QHBoxLayout()
        row_btn.setSpacing(6)
        row_btn.addWidget(self.apply_all)
        row_btn.addWidget(self.reset)
        pb.addLayout(row_btn)

        # ── 3. Lưu file & Tích hợp ──
        self.folder_label = _ElidedLabel(self._save_folder)
        self.folder_btn = QToolButton()
        self.folder_btn.setObjectName("scanSecondaryBtn")
        self.folder_btn.setText("Chọn…")
        self.folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_btn.clicked.connect(self._choose_folder)
        self.open_folder_btn = QToolButton()
        icons.bind(self.open_folder_btn, "folder-open", 15)
        self.open_folder_btn.setToolTip("Mở thư mục lưu file")
        self.open_folder_btn.clicked.connect(self._open_folder)
        f_row = QHBoxLayout()
        f_row.setSpacing(4)
        f_row.addWidget(self.folder_label, 1)
        f_row.addWidget(self.folder_btn)
        f_row.addWidget(self.open_folder_btn)

        self.ask_name = _ToggleSwitch("Hỏi tên file khi lưu", tokens_fn)
        self.ask_name.setChecked(True)
        self.auto_open_pdf = _ToggleSwitch("Mở ngay trong QT PDF Pro sau khi lưu PDF", tokens_fn)
        self.auto_open_pdf.setChecked(True)
        self.single_format = _Segmented([("pdf", "PDF"), ("image", "Ảnh")])
        self.image_format = _Segmented(IMAGE_FORMATS)
        self.single_format_field = _field_box("Định dạng khi Scan", self.single_format)
        self.image_format_field = _field_box("Định dạng ảnh", self.image_format)

        self.save_card = _Card("Lưu file", "save")
        sb = self.save_card.body
        sb.addWidget(_field_box("Thư mục mặc định", f_row))
        sb.addWidget(self.single_format_field)
        sb.addWidget(self.image_format_field)
        sb.addWidget(self.ask_name)
        sb.addWidget(self.auto_open_pdf)

        self.cards = (scan_card, self.proc_card, self.save_card)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(8)
        for c in self.cards:
            lay.addWidget(c)
        lay.addStretch(1)

        # Kết nối tín hiệu
        self.device.currentIndexChanged.connect(self.scanOptionsChanged)
        self.source.currentIndexChanged.connect(self.scanOptionsChanged)
        self.dpi.currentIndexChanged.connect(self._on_dpi_changed)
        self.scan_mode.changed.connect(self.scanOptionsChanged)
        self.area.activated.connect(lambda _: self.areaChanged.emit(self.area.currentData()))
        self.preset.currentIndexChanged.connect(self._preset_chosen)
        self.output.changed.connect(self._user_changed)
        for w in (self.white, self.gamma, self.sharpen, self.k):
            w.valueChanged.connect(self._user_changed)
        for w in (self.deskew, self.specks, self.edges):
            w.toggled.connect(self._user_changed)
        self.apply_all.clicked.connect(self.applyAllRequested)
        self.reset.clicked.connect(lambda: self._preset_chosen(0))
        self.ask_name.toggled.connect(self.saveOptionsChanged)
        self.auto_open_pdf.toggled.connect(self.saveOptionsChanged)
        self.single_format.changed.connect(self._on_save_format_changed)
        self.image_format.changed.connect(self.saveOptionsChanged)

        self._load_settings(self._base, "gray")
        self._update_preset_desc()
        self._update_k_visible()
        self._on_save_format_changed()

    def refresh_icons(self) -> None:
        for c in self.cards:
            c.refresh_icon()
        self.refresh_btn.setIcon(icons.icon("refresh-cw", size=15))
        self.open_folder_btn.setIcon(icons.icon("folder-open", size=15))

    def set_devices(self, devices: List[tuple[str, str]]) -> None:
        current = self.device.currentData() or self._preferred_device
        with QSignalBlocker(self.device):
            self.device.clear()
            if not devices:
                self.device.addItem("Không tìm thấy máy scan", None)
            else:
                for dev_id, name in devices:
                    self.device.addItem(name, dev_id)
                _select_data(self.device, current)
        self.scanOptionsChanged.emit()

    def set_mode(self, mode: str) -> None:
        single = mode == "single"
        self.single_format_field.setVisible(single)
        self.image_format_field.setVisible(not single or self.single_format.value() == "image")
        self.apply_all.setVisible(not single)
        self._on_save_format_changed()

    def scan_options(self) -> dict:
        return {
            "device_id": self.device.currentData(),
            "source": self.source.currentData() or "auto",
            "dpi": self.dpi.currentData() or 300,
            "mode": self.scan_mode.value() or "gray",
            "area": self.area.currentData() or "a4",
        }

    def area_key(self) -> str:
        return self.area.currentData() or "a4"

    def area_label(self) -> str:
        return self.area.currentText()

    def select_area(self, key: str) -> None:
        with QSignalBlocker(self.area):
            _select_data(self.area, key)

    def processing(self) -> tuple[scanner.Settings, str]:
        defaults = scanner.Settings()
        s = replace(
            self._base,
            dpi=self.dpi.currentData() or 300,
            white_point=self.white.value(),
            gamma=self.gamma.value(),
            sharpen=self.sharpen.value(),
            sauvola_k=self.k.value(),
            deskew=self.deskew.isChecked(),
            speck_isolation_mm=defaults.speck_isolation_mm if self.specks.isChecked() else 0.0,
            edge_margin_mm=defaults.edge_margin_mm if self.edges.isChecked() else 0.0,
        )
        return s, self.output.value() or "gray"

    def show_page(self, page: scanner.Page) -> None:
        self._base = page.settings
        self.output.set_option_enabled("color", page.is_color)
        self._load_settings(page.settings, page.output)
        with QSignalBlocker(self.preset):
            self.preset.setCurrentIndex(self._match_preset(page.settings, page.output))
        self._update_preset_desc()

    def clear_page(self) -> None:
        self.output.set_option_enabled("color", True)

    def save_folder(self) -> str:
        return self._save_folder

    def set_save_folder(self, folder: str | Path) -> None:
        self._save_folder = str(folder)
        self.folder_label.setText(self._save_folder)
        self.saveOptionsChanged.emit()

    def ask_filename(self) -> bool:
        return self.ask_name.isChecked()

    def should_auto_open_pdf(self) -> bool:
        return self.auto_open_pdf.isChecked()

    def single_save_format(self) -> str:
        return "pdf" if self.single_format.value() == "pdf" else (self.image_format.value() or "jpg")

    def image_save_format(self) -> str:
        return self.image_format.value() or "jpg"

    def _load_settings(self, s: scanner.Settings, output: str) -> None:
        blockers = [QSignalBlocker(w) for w in (self.deskew, self.specks, self.edges)]
        self.white.setValue(s.white_point)
        self.gamma.setValue(s.gamma)
        self.sharpen.setValue(s.sharpen)
        self.k.setValue(s.sauvola_k)
        self.deskew.setChecked(s.deskew)
        self.specks.setChecked(s.speck_isolation_mm > 0)
        self.edges.setChecked(s.edge_margin_mm > 0)
        self.output.set_value(output)
        for b in blockers:
            b.unblock()
        self._update_k_visible()

    def _on_dpi_changed(self) -> None:
        self.scanOptionsChanged.emit()
        self.processingChanged.emit()

    def _on_save_format_changed(self) -> None:
        if self.single_format_field.isVisible():
            self.image_format_field.setVisible(self.single_format.value() == "image")
        self.saveOptionsChanged.emit()

    def _preset_chosen(self, index: int) -> None:
        if index >= len(scanner.PRESETS):
            self._update_preset_desc()
            return
        preset = scanner.PRESETS[index]
        self._base = replace(scanner.Settings(**preset.overrides), dpi=self._base.dpi)
        self._load_settings(self._base, preset.output)
        self.scan_mode.set_value(preset.scan_mode)
        self._update_preset_desc()
        self.scanOptionsChanged.emit()
        self.processingChanged.emit()

    def _user_changed(self, *_) -> None:
        self._update_k_visible()
        s, output = self.processing()
        with QSignalBlocker(self.preset):
            self.preset.setCurrentIndex(self._match_preset(s, output))
        self._update_preset_desc()
        self.processingChanged.emit()

    def _match_preset(self, s: scanner.Settings, output: str) -> int:
        for i, p in enumerate(scanner.PRESETS):
            ref = scanner.Settings(**p.overrides)
            if p.output == output and all(
                abs(getattr(s, f) - getattr(ref, f)) < 1e-6 for f in PANEL_FIELDS
            ):
                return i
        return len(scanner.PRESETS)

    def _update_preset_desc(self) -> None:
        i = self.preset.currentIndex()
        self.preset_desc.setText(
            scanner.PRESETS[i].description if i < len(scanner.PRESETS) else "Thông số do bạn tự chỉnh."
        )

    def _update_k_visible(self) -> None:
        self.k.setVisible(self.output.value() == "bw")

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Thư mục lưu file", self._save_folder)
        if folder:
            self.set_save_folder(folder)

    def _open_folder(self) -> None:
        folder = Path(self._save_folder)
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def state(self) -> dict:
        s, output = self.processing()
        return {
            "scan": self.scan_options(),
            "settings": s.to_dict(),
            "output": output,
            "save_folder": self._save_folder,
            "ask_filename": self.ask_filename(),
            "auto_open_pdf": self.should_auto_open_pdf(),
            "single_format": self.single_format.value(),
            "image_format": self.image_format.value(),
            "collapsed": [i for i, c in enumerate(self.cards) if not c.is_expanded()],
        }

    def restore(self, state: dict) -> None:
        scan = state.get("scan", {})
        with QSignalBlocker(self.dpi), QSignalBlocker(self.area), QSignalBlocker(self.source):
            _select_data(self.dpi, scan.get("dpi", 300))
            _select_data(self.area, scan.get("area", "a4"))
            _select_data(self.source, scan.get("source", "auto"))
        self.scan_mode.set_value(scan.get("mode", "gray"))
        self._preferred_device = scan.get("device_id")
        self._base = scanner.Settings.from_dict(state.get("settings"))
        self._load_settings(self._base, state.get("output", "gray"))
        with QSignalBlocker(self.preset):
            self.preset.setCurrentIndex(self._match_preset(*self.processing()))
        self._update_preset_desc()
        self.set_save_folder(state.get("save_folder") or default_save_folder())
        self.ask_name.setChecked(state.get("ask_filename", True))
        self.auto_open_pdf.setChecked(state.get("auto_open_pdf", True))
        self.single_format.set_value(state.get("single_format", "pdf"))
        self.image_format.set_value(state.get("image_format", "jpg"))
        for i, c in enumerate(self.cards):
            c.set_expanded(i not in state.get("collapsed", []))
        self._on_save_format_changed()


# ─── Luồng nền: liệt kê máy scan, scan, xử lý ảnh, xuất PDF/ảnh ─────────────


class DeviceListThread(QThread):
    found = Signal(list)
    failed = Signal(str)

    def run(self) -> None:
        try:
            with scanner_wia.com_apartment():
                devices = scanner_wia.list_scanners()
            self.found.emit(devices)
        except Exception as exc:
            log.exception("Không liệt kê được máy scan")
            self.failed.emit(str(exc))


class ScanThread(QThread):
    progress = Signal(int)
    scanned = Signal(object, int, str)  # img, dpi, purpose
    failed = Signal(str)

    def __init__(
        self,
        device_id: Optional[str],
        dpi: int,
        mode: str,
        area: Optional[tuple],
        purpose: str,
        source: str = "auto",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.device_id = device_id
        self.dpi = dpi
        self.mode = mode
        self.area = area
        self.purpose = purpose
        self.source = source
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def _on_progress(self, percent: int) -> bool:
        self.progress.emit(percent)
        return not self._cancel

    def run(self) -> None:
        try:
            with scanner_wia.com_apartment():
                if self.purpose == "multi" and self.source == "adf":
                    scanner_wia.scan_adf_pages(
                        dpi=self.dpi,
                        mode=self.mode,
                        area=self.area,
                        device_id=self.device_id,
                        progress=self._on_progress,
                        on_page=self._emit_adf_page,
                    )
                else:
                    img, actual_dpi = scanner_wia.scan_with_info(
                        dpi=self.dpi,
                        mode=self.mode,
                        area=self.area,
                        device_id=self.device_id,
                        source=self.source,
                        progress=self._on_progress,
                    )
                    self.scanned.emit(img, actual_dpi, self.purpose)
        except scanner_wia.ScanError as exc:
            log.warning("Scan lỗi: %s", exc)
            self.failed.emit(str(exc))
        except Exception as exc:
            log.exception("Scan lỗi không mong đợi")
            self.failed.emit(f"Lỗi không mong đợi: {exc}")

    def _emit_adf_page(self, img: np.ndarray, actual_dpi: int, _page_num: int) -> bool:
        self.scanned.emit(img, actual_dpi, self.purpose)
        return not self._cancel


class CommonDialogThread(QThread):
    scanned = Signal(object, int)
    cancelled = Signal()
    failed = Signal(str)

    def run(self) -> None:
        try:
            with scanner_wia.com_apartment():
                res = scanner_wia.scan_via_common_dialog()
            if res is None:
                self.cancelled.emit()
            else:
                self.scanned.emit(res[0], res[1])
        except Exception as exc:
            self.failed.emit(str(exc))


class _RenderSignals(QObject):
    done = Signal(int, int, object, float)
    failed = Signal(int, str)


class _RenderTask(QRunnable):
    def __init__(self, page: scanner.Page, settings: scanner.Settings, output: str, gen: int, latest, signals) -> None:
        super().__init__()
        self.page = page
        self.settings = copy(settings)
        self.output = output
        self.gen = gen
        self.latest = latest
        self.signals = signals

    def run(self) -> None:
        if self.latest() != self.gen:
            return
        try:
            img = self.page.render(self.settings, self.output)
            angle = self.page.prepared(self.settings).skew_angle
            self.signals.done.emit(self.gen, self.page.id, img, angle)
        except Exception as exc:
            log.exception("Xử lý ảnh trang scan lỗi")
            self.signals.failed.emit(self.gen, str(exc))


class ExportThread(QThread):
    progress = Signal(int, int)
    exported = Signal(object, str, int, object)
    failed = Signal(object, str)

    def __init__(self, jobs: list, path: str, fmt: str = "pdf", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        if fmt != "pdf" and len(jobs) != 1:
            raise ValueError("Lưu ảnh chỉ áp dụng cho một trang")
        self.jobs = jobs
        self.path = path
        self.fmt = fmt
        self.on_saved = None
        self.on_failed = None

    def run(self) -> None:
        try:
            blobs, dpis, thumb = [], [], None
            for i, (page, settings, output) in enumerate(self.jobs, 1):
                img = page.render(settings, output)
                if thumb is None:
                    h, w = img.shape[:2]
                    thumb = cv2.resize(img, (max(1, round(w * 96 / max(1, h))), 96), interpolation=cv2.INTER_AREA)
                if self.fmt == "pdf":
                    blobs.append(scanner.encode_page(img, output, page.dpi))
                    dpis.append(page.dpi)
                else:
                    scanner.save_image(self.path, img, output, page.dpi, self.fmt)
                self.progress.emit(i, len(self.jobs))
            if self.fmt == "pdf":
                scanner.save_pdf(self.path, blobs, title=Path(self.path).stem, dpis=dpis)
            self.exported.emit(self, self.path, Path(self.path).stat().st_size, thumb)
        except Exception as exc:
            log.exception("Lưu file scan lỗi")
            self.failed.emit(self, str(exc))


class _PageCardDelegate(QStyledItemDelegate):
    SIZE = QSize(114, 170)

    def __init__(self, tokens_fn: Callable[[], dict], parent=None) -> None:
        super().__init__(parent)
        self._tokens_fn = tokens_fn

    def sizeHint(self, option, index) -> QSize:
        return self.SIZE

    def paint(self, painter: QPainter, option, index) -> None:
        tok = self._tokens_fn()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(option.rect).adjusted(4, 6, -4, -6)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.setPen(QPen(QColor(tok["accent"]), 2))
            painter.setBrush(QColor(tok["accent_soft"]))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tok["hover"]) if hover else Qt.GlobalColor.transparent)
        painter.drawRoundedRect(r.adjusted(1, 1, -1, -1), 10, 10)

        area = QRectF(r.left() + 12, r.top() + 10, r.width() - 24, r.height() - 56)
        ic = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(ic, QIcon) and ic.availableSizes():
            pm = ic.pixmap(ic.availableSizes()[0])
            k = min(area.width() / max(1, pm.width()), area.height() / max(1, pm.height()))
            w, h = pm.width() * k, pm.height() * k
            target = QRectF(area.center().x() - w / 2, area.bottom() - h, w, h)
            painter.drawPixmap(target, pm, QRectF(pm.rect()))
            painter.setPen(QPen(QColor(tok["border"]), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(target)

        lines = (index.data(Qt.ItemDataRole.DisplayRole) or "").split("\n")
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(tok["accent"] if selected else tok["text"]))
        painter.drawText(QRectF(r.left(), r.bottom() - 40, r.width(), 18), Qt.AlignmentFlag.AlignCenter, lines[0])
        if len(lines) > 1:
            font.setBold(False)
            font.setPointSize(max(7, font.pointSize() - 1))
            painter.setFont(font)
            painter.setPen(QColor(tok["muted"]))
            painter.drawText(QRectF(r.left(), r.bottom() - 22, r.width(), 18), Qt.AlignmentFlag.AlignCenter, lines[1])
        painter.restore()


# ─── Hộp thoại Scan chính trong QT PDF Pro ───────────────────────────────────


class ScanDialog(QDialog):
    """Cửa sổ Scan tài liệu ra PDF nền trắng, chữ rõ — hỗ trợ mọi máy scan WIA."""

    pdfSaved = Signal(str, bool)  # đường dẫn PDF, mở ngay thành tab mới
    insertPagesRequested = Signal(bytes)  # PDF bytes của các trang để chèn vào tab đang mở
    renderFinished = Signal()

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        *,
        has_active_doc: bool = False,
        interactive: bool = True,
        cache_dir: Optional[Path] = None,
        auto_refresh_devices: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.app_settings = settings or AppSettings.load()
        self._has_active_doc = has_active_doc
        self.interactive = interactive
        self.cache_dir = Path(cache_dir) if cache_dir else scanner.default_cache_dir()

        self.setWindowTitle("Scan tài liệu — WIA đa thiết bị (Mặt kính & ADF)")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(1300, 840)
        self.setMinimumSize(980, 620)
        self.setAcceptDrops(True)

        self.mode = "single"
        self.pages: Dict[int, scanner.Page] = {}
        self.session: Optional[scanner.ScanSession] = None
        self.preview_raw: Optional[np.ndarray] = None
        self.preview_dpi: Optional[int] = None
        self.preview_page: Optional[scanner.Page] = None
        self.bed_in = scanner.DEFAULT_BED_IN
        self.area_in = scanner.paper_area("a4")
        self._view = "preview"
        self._finishing = False
        self._scan_thread: Optional[QThread] = None
        self._scan_target = None
        self._scan_text = ""
        self._exports: set[ExportThread] = set()
        self._device_thread: Optional[DeviceListThread] = None
        self._render_gen = 0
        self._keep_view = True
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._render_signals = _RenderSignals()
        self._render_signals.done.connect(self._on_rendered)
        self._render_signals.failed.connect(self._on_render_failed)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(120)
        self._render_timer.timeout.connect(self._start_render)
        self._manifest_timer = QTimer(self)
        self._manifest_timer.setSingleShot(True)
        self._manifest_timer.setInterval(500)
        self._manifest_timer.timeout.connect(self._write_manifest)

        self._build_actions()
        self._build_ui()
        self._apply_local_styles()
        self._restore_state()
        self.set_mode(self.mode)
        self._sync_crop()
        self._show_view("preview")
        self._set_status("Đặt tài liệu lên mặt kính hoặc khay ADF rồi bấm «Xem trước» (F5) hoặc «Scan».")

        if auto_refresh_devices:
            QTimer.singleShot(0, self.refresh_devices)
        if interactive:
            QTimer.singleShot(250, self._offer_restore)

    def _tokens(self) -> dict:
        return theme_tokens(self.app_settings.theme)

    def _apply_local_styles(self) -> None:
        tok = self._tokens()
        self.setStyleSheet(
            f"""
            QFrame#scanSidebar {{ background-color: {tok["bar"]}; border-right: 1px solid {tok["border"]}; }}
            QFrame#scanTopBar, QFrame#scanContextBar, QFrame#scanActions {{
                background-color: {tok["bar"]}; border-bottom: 1px solid {tok["border"]};
            }}
            QFrame#scanActions {{ border-top: 1px solid {tok["border"]}; border-bottom: none; }}
            QFrame#scanCard {{
                background-color: {tok["card"]}; border: 1px solid {tok["border"]}; border-radius: 10px;
            }}
            QLabel#scanCardTitle {{ font-weight: 600; color: {tok["text"]}; }}
            QLabel#scanFieldLabel {{ font-size: 12px; font-weight: 600; color: {tok["muted"]}; }}
            QLabel#scanHint {{ font-size: 12px; color: {tok["muted"]}; }}
            QFrame#scanSegmented {{
                background-color: {tok["page"]}; border: 1px solid {tok["border"]}; border-radius: 8px;
            }}
            QPushButton#scanSegment {{
                background: transparent; border: none; border-radius: 6px; padding: 5px 8px;
                color: {tok["muted"]}; font-weight: 600;
            }}
            QPushButton#scanSegment:checked {{
                background-color: {tok["card"]}; color: {tok["text"]}; border: 1px solid {tok["border"]};
            }}
            QToolButton#scanSecondaryBtn, QPushButton#scanSecondaryBtn {{
                background-color: {tok["card"]}; color: {tok["text"]}; border: 1px solid {tok["border_strong"]};
                border-radius: 6px; padding: 5px 10px; font-weight: 500;
            }}
            QToolButton#scanSecondaryBtn:hover, QPushButton#scanSecondaryBtn:hover {{
                border-color: {tok["accent"]}; background-color: {tok["hover"]};
            }}
            QToolButton#scanAccentBtn {{
                background-color: {tok["accent_soft"]}; color: {tok["accent_text"]};
                border: 1px solid {tok["accent"]}; border-radius: 6px; padding: 5px 12px; font-weight: 600;
            }}
            QToolButton#scanDangerBtn {{
                background-color: transparent; color: #EF4444; border: 1px solid #EF4444;
                border-radius: 6px; padding: 5px 10px; font-weight: 600;
            }}
            QFrame#scanBanner {{
                background-color: {tok["accent_soft"]}; border: 1px solid {tok["accent"]}; border-radius: 8px;
            }}
            QListWidget#scanPageStrip {{
                background-color: {tok["bar"]}; border-top: 1px solid {tok["border"]};
            }}
            """
        )

    def _set_status(self, msg: str) -> None:
        self.status_lbl.setText(msg)

    def _action(self, text: str, slot, shortcuts=(), icon_name: Optional[str] = None, tip: Optional[str] = None, checkable: bool = False) -> QAction:
        act = QAction(text, self)
        if icon_name:
            act.setIcon(icons.icon(icon_name))
        if shortcuts:
            act.setShortcuts([QKeySequence(s) for s in shortcuts])
        keys = f" ({shortcuts[0]})" if shortcuts else ""
        act.setToolTip((tip or text.replace("&&", "&")) + keys)
        act.setCheckable(checkable)
        act.triggered.connect(slot)
        self.addAction(act)
        return act

    def _build_actions(self) -> None:
        A = self._action
        self.act_preview = A("Xem trước", self.start_preview, ["F5"], "eye", "Scan toàn mặt kính ở độ phân giải đã chọn")
        self.act_scan = A("Scan && lưu file", self.scan_primary, ["Ctrl+Return", "Ctrl+Enter"], "scan-line")
        self.act_cancel = A("Huỷ", self.cancel_scan, ["Esc"], "x", "Huỷ lần scan đang chạy")
        self.act_finish = A("Hoàn tất && lưu PDF", self.finish_document, (), "check", "Ghép các trang thành PDF (Ctrl+S)")
        self.act_insert_doc = A("Chèn vào PDF đang mở", self.insert_into_open_pdf, (), "file-plus-2", "Chèn các trang vừa scan vào tài liệu đang mở")
        self.act_discard = A("Bỏ tài liệu", self.discard_document, (), "trash-2", "Xoá mọi trang đang scan tạm")
        self.act_save_pdf = A("Lưu PDF", self.save_preview_pdf, (), "file-text", "Lưu vùng trong khung thành PDF (Ctrl+S)")
        self.act_save_image = A("Lưu ảnh", self.save_preview_image, ["Ctrl+Shift+S"], "image", "Lưu vùng trong khung thành ảnh")
        self.act_add_to_doc = A("Thêm vào tài liệu", self.add_preview_to_document, (), "file-plus-2", "Thêm vùng xem trước thành 1 trang")
        self.act_save = A("Lưu", self.save_shortcut, ["Ctrl+S"])
        self.act_open = A("Mở ảnh…", self.open_images, ["Ctrl+O"], "image-plus", "Thêm ảnh có sẵn vào tài liệu")
        self.act_rot_left = A("Xoay trái", lambda: self.rotate_page(-90), ["Ctrl+L"], "rotate-ccw")
        self.act_rot_right = A("Xoay phải", lambda: self.rotate_page(90), ["Ctrl+R"], "rotate-cw")
        self.act_move_prev = A("Dời trước", lambda: self.move_page(-1), ["Alt+Left"], "chevron-left")
        self.act_move_next = A("Dời sau", lambda: self.move_page(1), ["Alt+Right"], "chevron-right")
        self.act_delete = A("Xoá trang", self.delete_page, ["Delete"], "trash-2")
        self.act_fit = A("Vừa khung", lambda: self._current_view().fit(), ["Ctrl+0"], "maximize")
        self.act_zoom_in = A("Phóng to", lambda: self._current_view().zoom_by(1.25), ["Ctrl++", "Ctrl+="], "zoom-in")
        self.act_zoom_out = A("Thu nhỏ", lambda: self._current_view().zoom_by(0.8), ["Ctrl+-"], "zoom-out")
        self.act_actual = A("Kích thước thật (100%)", lambda: self._current_view().zoom_actual(), ["Ctrl+1"])
        self.act_compare = A("Ảnh gốc", lambda: self.request_render(True), ["Ctrl+G"], "eye", "Xem ảnh gốc chưa xử lý", checkable=True)
        self.act_refresh = A("Tìm lại máy scan", self.refresh_devices, (), "refresh-cw")

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main(), 1)

    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("scanSidebar")
        side.setFixedWidth(360)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QWidget()
        hv = QVBoxLayout(head)
        hv.setContentsMargins(12, 12, 12, 8)
        hv.setSpacing(6)
        self.mode_switch = _Segmented([("single", "Một trang", "file-text"), ("multi", "Nhiều trang", "files")])
        self.mode_switch.changed.connect(self.set_mode)
        hv.addWidget(self.mode_switch)
        self.mode_hint = QLabel()
        self.mode_hint.setObjectName("scanHint")
        self.mode_hint.setWordWrap(True)
        hv.addWidget(self.mode_hint)
        v.addWidget(head)

        self.panel = ScanSettingsPanel(self._tokens)
        self.panel.processingChanged.connect(self._on_processing_changed)
        self.panel.applyAllRequested.connect(self._apply_to_all)
        self.panel.scanOptionsChanged.connect(self._update_actions)
        self.panel.areaChanged.connect(self._on_area_key_changed)
        self.panel.refreshDevicesRequested.connect(self.refresh_devices)
        self.panel.commonDialogRequested.connect(self.scan_with_common_dialog)
        self.panel.saveOptionsChanged.connect(self._update_actions)

        scroll = QScrollArea()
        scroll.setWidget(self.panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        v.addWidget(scroll, 1)

        actions = QFrame()
        actions.setObjectName("scanActions")
        av = QVBoxLayout(actions)
        av.setContentsMargins(12, 10, 12, 12)
        av.setSpacing(7)

        self.scan_box = QWidget()
        sb = QVBoxLayout(self.scan_box)
        sb.setContentsMargins(0, 0, 0, 2)
        sb.setSpacing(4)
        row = QHBoxLayout()
        self.scan_label = QLabel()
        row.addWidget(self.scan_label, 1)
        row.addWidget(_tool_button(self.act_cancel, "secondary"))
        sb.addLayout(row)
        self.scan_progress = QProgressBar()
        self.scan_progress.setTextVisible(False)
        sb.addWidget(self.scan_progress)
        self.scan_box.hide()
        av.addWidget(self.scan_box)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(_tool_button(self.act_preview, "secondary", expand=True), 2)
        self.scan_btn = _tool_button(self.act_scan, "primary", expand=True)
        buttons.addWidget(self.scan_btn, 3)
        av.addLayout(buttons)

        self.dest_label = _ElidedLabel()
        self.dest_label.setObjectName("scanHint")
        av.addWidget(self.dest_label)

        self.finish_btn = _tool_button(self.act_finish, "accent", expand=True)
        av.addWidget(self.finish_btn)
        self.insert_doc_btn = _tool_button(self.act_insert_doc, "secondary", expand=True)
        self.insert_doc_btn.setVisible(self._has_active_doc)
        av.addWidget(self.insert_doc_btn)

        v.addWidget(actions)
        return side

    def _build_main(self) -> QWidget:
        main = QWidget()
        v = QVBoxLayout(main)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        top = QFrame()
        top.setObjectName("scanTopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(14, 8, 12, 8)
        tl.setSpacing(6)
        self.view_switch = _Segmented([("preview", "Xem trước", "eye"), ("document", "Tài liệu", "files")])
        self.view_switch.setFixedWidth(300)
        self.view_switch.changed.connect(self._show_view)
        self.view_title = QLabel("Xem trước")
        self.view_title.setObjectName("scanCardTitle")
        tl.addWidget(self.view_switch)
        tl.addWidget(self.view_title)
        tl.addStretch()
        tl.addWidget(_tool_button(self.act_zoom_out, text=False))
        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(44)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tl.addWidget(self.zoom_label)
        tl.addWidget(_tool_button(self.act_zoom_in, text=False))
        tl.addWidget(_tool_button(self.act_fit, text=False))
        tl.addWidget(_vline())
        tl.addWidget(_tool_button(self.act_compare))
        v.addWidget(top)

        self.banner = _Banner()
        banner_box = QWidget()
        bl = QVBoxLayout(banner_box)
        bl.setContentsMargins(14, 8, 14, 0)
        bl.addWidget(self.banner)
        banner_box.setVisible(False)
        self.banner.visibilityChanged.connect(banner_box.setVisible)
        v.addWidget(banner_box)

        self.stack = QStackedWidget()

        # Trang 0: Xem trước
        self.preview_view = ScanImageView(tokens_fn=self._tokens)
        self.preview_view.set_crop_enabled(True, px_per_mm=scanner.PREVIEW_DPI / 25.4)
        self.preview_view.cropChanged.connect(self._on_crop_changed)
        self.preview_view.zoomChanged.connect(self._on_zoom)
        preview_page = QWidget()
        pv = QVBoxLayout(preview_page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)
        pbar = QFrame()
        pbar.setObjectName("scanContextBar")
        pbl = QHBoxLayout(pbar)
        pbl.setContentsMargins(14, 6, 12, 6)
        pbl.setSpacing(6)
        self.preview_info = QLabel()
        self.preview_info.setObjectName("scanHint")
        pbl.addWidget(self.preview_info, 1)
        self.add_to_doc_btn = _tool_button(self.act_add_to_doc, "secondary")
        pbl.addWidget(self.add_to_doc_btn)
        pbl.addWidget(_tool_button(self.act_save_image, "secondary"))
        pbl.addWidget(_tool_button(self.act_save_pdf, "accent"))
        pv.addWidget(pbar)
        pv.addWidget(self.preview_view, 1)
        self.stack.addWidget(preview_page)

        # Trang 1: Tài liệu nhiều trang
        self.page_view = ScanImageView(
            (
                "files",
                "Chưa có trang nào",
                "Bấm «Scan trang 1» (Ctrl+Enter) để scan trang đầu tiên.\n"
                "Có thể thêm ảnh có sẵn bằng «Mở ảnh» (Ctrl+O) hoặc kéo thả file ảnh vào cửa sổ.",
            ),
            tokens_fn=self._tokens,
        )
        self.page_view.zoomChanged.connect(self._on_zoom)
        doc_page = QWidget()
        dv = QVBoxLayout(doc_page)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(0)
        dbar = QFrame()
        dbar.setObjectName("scanContextBar")
        dbl = QHBoxLayout(dbar)
        dbl.setContentsMargins(14, 6, 12, 6)
        dbl.setSpacing(6)
        self.doc_info = QLabel()
        self.doc_info.setObjectName("scanHint")
        dbl.addWidget(self.doc_info, 1)
        for a in (
            self.act_rot_left,
            self.act_rot_right,
            None,
            self.act_move_prev,
            self.act_move_next,
            None,
            self.act_delete,
            None,
            self.act_open,
        ):
            dbl.addWidget(_vline()) if a is None else dbl.addWidget(_tool_button(a, text=False))
        dbl.addWidget(_vline())
        dbl.addWidget(_tool_button(self.act_discard, "danger"))
        dv.addWidget(dbar)
        dv.addWidget(self.page_view, 1)

        self.page_list = QListWidget()
        self.page_list.setObjectName("scanPageStrip")
        self.page_list.setFlow(QListView.Flow.LeftToRight)
        self.page_list.setWrapping(False)
        self.page_list.setIconSize(QSize(86, 122))
        self.page_list.setItemDelegate(_PageCardDelegate(self._tokens, self.page_list))
        self.page_list.setUniformItemSizes(True)
        self.page_list.setMouseTracking(True)
        self.page_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.page_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.page_list.setSpacing(2)
        self.page_list.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.page_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.page_list.setFixedHeight(_PageCardDelegate.SIZE.height() + 22)
        self.page_list.currentItemChanged.connect(self._on_current_page_changed)
        self.page_list.itemClicked.connect(lambda _: self._show_view("document"))
        self.page_list.model().rowsMoved.connect(self._on_pages_reordered)
        self.page_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.page_list.customContextMenuRequested.connect(self._page_menu)
        dv.addWidget(self.page_list)
        self.stack.addWidget(doc_page)
        v.addWidget(self.stack, 1)

        foot = QFrame()
        foot.setObjectName("scanTopBar")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(14, 5, 14, 5)
        self.status_lbl = QLabel()
        self.status_lbl.setObjectName("scanHint")
        fl.addWidget(self.status_lbl, 1)
        self.export_progress = QProgressBar()
        self.export_progress.setFixedWidth(150)
        self.export_progress.setTextVisible(False)
        self.export_progress.hide()
        fl.addWidget(self.export_progress)
        v.addWidget(foot)
        return main

    # ─── Cập nhật trạng thái nút ──────────────────────────────────────────

    def _update_actions(self, *_) -> None:
        scanning = self._scan_thread is not None
        has_device = self.panel.scan_options()["device_id"] is not None
        multi = self.mode == "multi"
        count = self.page_list.count()
        row = self.page_list.currentRow()
        has_page = self.current_page() is not None
        has_preview = self.preview_raw is not None
        editable = has_page and not self._finishing

        self.act_preview.setEnabled(has_device and not scanning)
        self.act_scan.setEnabled(has_device and not scanning and not (multi and self._finishing))
        if multi:
            self.act_scan.setText(f"Scan trang {count + 1}")
            self.act_scan.setToolTip("Scan và thêm thành trang mới của tài liệu (Ctrl+Enter)")
        else:
            fmt = self.panel.single_save_format()
            self.act_scan.setText("Scan && lưu file")
            self.act_scan.setToolTip(f"Scan vùng đã chọn và lưu ngay thành {fmt.upper()} (Ctrl+Enter)")
        self.act_cancel.setEnabled(scanning)
        self.dest_label.setVisible(not multi)
        if not multi:
            fmt = self.panel.single_save_format().upper()
            self.dest_label.setText(
                f"Lưu {fmt} · hỏi tên file mỗi lần"
                if self.panel.ask_filename()
                else f"Lưu {fmt} vào {self.panel.save_folder()}"
            )
        for a in (self.act_save_pdf, self.act_save_image):
            a.setEnabled(has_preview)
        self.act_save_image.setText(f"Lưu ảnh {self.panel.image_save_format().upper()}")
        self.act_add_to_doc.setEnabled(has_preview and not self._finishing)
        self.act_finish.setEnabled(count > 0 and not self._finishing)
        self.act_finish.setText(f"Hoàn tất && lưu PDF ({count} trang)" if count else "Hoàn tất && lưu PDF")
        can_insert = self._has_active_doc and not self._finishing and (
            (multi and count > 0) or (not multi and has_preview) or (multi and self._view == "preview" and has_preview)
        )
        self.act_insert_doc.setEnabled(can_insert)
        self.insert_doc_btn.setVisible(self._has_active_doc)
        self.act_discard.setEnabled(count > 0 and not self._finishing)
        for a in (self.act_rot_left, self.act_rot_right, self.act_delete):
            a.setEnabled(editable)
        self.act_move_prev.setEnabled(editable and row > 0)
        self.act_move_next.setEnabled(editable and row < count - 1)
        self.act_open.setEnabled(not self._finishing)
        self.act_refresh.setEnabled(self._device_thread is None and not scanning)
        self.view_switch.set_label("document", f"Tài liệu · {count} trang")
        self.mode_switch.set_label("multi", f"Nhiều trang · {count}" if count and not multi else "Nhiều trang")
        self.page_list.setVisible(count > 0)

    def _current_view(self) -> ScanImageView:
        return self.preview_view if self._view == "preview" else self.page_view

    def _on_preview_tab(self) -> bool:
        return self._view == "preview"

    def _on_zoom(self, z: float) -> None:
        if self.sender() is self._current_view():
            self.zoom_label.setText(f"{z * 100:.0f}%")

    def set_mode(self, mode: str) -> None:
        mode = "multi" if mode == "multi" else "single"
        self.mode = mode
        multi = mode == "multi"
        self.mode_switch.set_value(mode)
        self.mode_hint.setText(MODE_HINTS[mode])
        self.view_switch.setVisible(multi)
        self.view_title.setVisible(not multi)
        self.finish_btn.setVisible(multi)
        self.add_to_doc_btn.setVisible(multi)
        self.panel.set_mode(mode)
        scan_text = "Scan trang 1" if multi else "Scan & lưu file"
        self.preview_view.set_placeholder(
            (
                "eye",
                "Chưa có ảnh xem trước",
                "Đặt tài liệu úp xuống mặt kính hoặc nạp vào khay ADF rồi bấm «Xem trước» (F5).\n"
                f"Hoặc bấm «{scan_text}» để scan ngay theo khổ giấy đã chọn.",
            )
        )
        if not multi and self._view == "document":
            self._show_view("preview")
        self._update_actions()

    def _show_view(self, key: str) -> None:
        self._view = key
        self.stack.setCurrentIndex(0 if key == "preview" else 1)
        self.view_switch.set_value(key)
        if key == "preview":
            self.panel.clear_page()
        else:
            page = self.current_page()
            if page is not None:
                self.panel.show_page(page)
        self.zoom_label.setText(f"{self._current_view().zoom() * 100:.0f}%")
        self.request_render(keep_view=True)
        self._update_actions()

    # ─── Máy scan WIA ────────────────────────────────────────────────────

    def refresh_devices(self) -> None:
        if self._device_thread is not None:
            return
        thread = DeviceListThread(self)
        thread.found.connect(self._on_devices)
        thread.failed.connect(self._on_devices_failed)
        thread.finished.connect(self._on_device_thread_done)
        self._device_thread = thread
        self._update_actions()
        thread.start()

    def _on_device_thread_done(self) -> None:
        self._device_thread = None
        self._update_actions()

    def _on_devices(self, devices: list) -> None:
        self.panel.set_devices(devices)
        if not devices:
            self._set_status("Không tìm thấy máy scan WIA. Bạn vẫn có thể mở ảnh hoặc dùng nút hộp thoại Windows.")
        else:
            names = ", ".join(n for _, n in devices)
            self._set_status(f"Đã nhận {len(devices)} máy scan: {names}")
        self._update_actions()

    def _on_devices_failed(self, message: str) -> None:
        self.panel.set_devices([])
        self._set_status(f"Không truy cập được WIA: {message}")

    def start_preview(self) -> None:
        opts = self.panel.scan_options()
        self._start_scan(opts["dpi"], opts["mode"], None, "preview", opts["source"])

    def scan_primary(self) -> None:
        if self.mode == "single":
            fmt = self.panel.single_save_format()
            path = None
            if self.panel.ask_filename() and self.interactive:
                path = self._ask_save_path(fmt)
                if not path:
                    return
            self._scan_target = (path, fmt)
            self._start_page_scan("single")
        else:
            self._start_page_scan("multi")

    def _start_page_scan(self, purpose: str) -> None:
        opts = self.panel.scan_options()
        area = None if opts["area"] == "full" else self.area_in
        self._start_scan(opts["dpi"], opts["mode"], area, purpose, opts["source"])

    def _start_scan(self, dpi: int, mode: str, area: Optional[tuple], purpose: str, source: str) -> None:
        if self._scan_thread is not None:
            return
        thread = ScanThread(
            self.panel.scan_options()["device_id"],
            dpi,
            mode,
            area,
            purpose,
            source=source,
            parent=self,
        )
        thread.progress.connect(self._on_scan_progress)
        thread.scanned.connect(self._on_scanned)
        thread.failed.connect(self._on_scan_failed)
        thread.finished.connect(self._on_scan_finished)
        self._scan_thread = thread
        self._scan_text = SCAN_LABELS[purpose] + (f" {self.page_list.count() + 1}" if purpose == "multi" else "")
        self.scan_progress.setRange(0, 100)
        self.scan_progress.setValue(0)
        self.scan_label.setText(f"{self._scan_text} · đang khởi động…")
        self.scan_box.show()
        self._set_status("Đang khởi động máy scan…")
        self._update_actions()
        thread.start()

    def scan_with_common_dialog(self) -> None:
        if self._scan_thread is not None:
            return
        thread = CommonDialogThread(self)
        thread.scanned.connect(self._on_common_scanned)
        thread.cancelled.connect(lambda: self._set_status("Đã đóng hộp thoại scan."))
        thread.failed.connect(self._on_scan_failed)
        thread.finished.connect(self._on_scan_finished)
        self._scan_thread = thread
        self._scan_text = "Đang scan qua hộp thoại Windows"
        self.scan_progress.setRange(0, 0)
        self.scan_label.setText(self._scan_text)
        self.scan_box.show()
        self._update_actions()
        thread.start()

    def _on_common_scanned(self, img: np.ndarray, dpi: int) -> None:
        purpose = "multi" if self.mode == "multi" else "single"
        if purpose == "single":
            fmt = self.panel.single_save_format()
            self._scan_target = (None, fmt)
        self._on_scanned(img, dpi, purpose)

    def _on_scan_progress(self, percent: int) -> None:
        self.scan_progress.setValue(percent)
        text = "đang khởi động đèn…" if percent == 0 else f"{percent}%"
        self.scan_label.setText(f"{self._scan_text} · {text}")
        self._set_status(f"{self._scan_text}… {percent}%" if percent else "Đang khởi động đèn máy scan…")

    def cancel_scan(self) -> None:
        if isinstance(self._scan_thread, ScanThread):
            self._scan_thread.cancel()
            self.act_cancel.setEnabled(False)
            self.scan_label.setText("Đang huỷ…")

    def _on_scan_finished(self) -> None:
        self._scan_thread = None
        self._scan_target = None
        self.scan_box.hide()
        self._update_actions()

    def _on_scan_failed(self, message: str) -> None:
        self._set_status(message)
        if "huỷ" not in message.lower():
            self.banner.show_message("error", "Scan không thành công", message, timeout=0)

    def _on_scanned(self, img: np.ndarray, dpi: int, purpose: str) -> None:
        if purpose == "preview":
            self._set_preview(img, dpi)
            return
        page = self._new_page(img, dpi)
        if purpose == "single":
            path, fmt = self._scan_target or (None, self.panel.single_save_format())
            self._save_pages([page], fmt, path or self._auto_path(fmt))
            self._set_status(f"Đã scan ({img.shape[1]}×{img.shape[0]} px, {dpi} dpi), đang lưu…")
        else:
            self._add_page(page)
            self._set_status(f"Đã scan trang {self.page_list.count()} ({img.shape[1]}×{img.shape[0]} px, {dpi} dpi).")

    def _new_page(self, img: np.ndarray, dpi: int, source: str = "scan") -> scanner.Page:
        s, output = self.panel.processing()
        page = scanner.Page(img, replace(s, dpi=dpi), source=source)
        page.apply(s, output)
        return page

    # ─── Xem trước & khung cắt ────────────────────────────────────────────

    def _set_preview(self, img: np.ndarray, dpi: int) -> None:
        self.preview_raw, self.preview_dpi = img, dpi
        self.bed_in = (img.shape[1] / dpi, img.shape[0] / dpi)
        self._fit_area_to_bed()
        if dpi != scanner.PREVIEW_DPI:
            k = scanner.PREVIEW_DPI / dpi
            proxy = cv2.resize(
                img,
                (max(1, round(img.shape[1] * k)), max(1, round(img.shape[0] * k))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            proxy = img
        s, output = self._preview_processing()
        self.preview_page = scanner.Page(proxy, s)
        self.preview_page.apply(s, output)
        self.preview_view.set_image(to_qimage(proxy))
        self._sync_crop()
        self._show_view("preview")
        self._update_preview_info()
        self._set_status(f"Vùng scan: {self._area_text()}. Kéo khung để chỉnh; có thể lưu ngay vùng này.")

    def load_synthetic_preview(self, dpi: int = 300) -> None:
        """Giả lập ảnh xem trước A4 (dùng cho kiểm thử không cần máy scan)."""
        bed = np.full((round(scanner.DEFAULT_BED_IN[1] * dpi), round(scanner.DEFAULT_BED_IN[0] * dpi), 3), 236, np.uint8)
        page = scanner.degraded_page(angle=0.8)
        if dpi != 300:
            page = cv2.resize(page, None, fx=dpi / 300, fy=dpi / 300, interpolation=cv2.INTER_AREA)
        h, w = min(page.shape[0], bed.shape[0]), min(page.shape[1], bed.shape[1])
        bed[:h, :w] = page[:h, :w]
        self._set_preview(bed, dpi)

    def _preview_processing(self) -> tuple[scanner.Settings, str]:
        s, output = self.panel.processing()
        return replace(s, dpi=scanner.PREVIEW_DPI, deskew=False), output

    def _preview_crop_page(self) -> Optional[scanner.Page]:
        if self.preview_raw is None or self.preview_dpi is None:
            return None
        d = self.preview_dpi
        h, w = self.preview_raw.shape[:2]
        x, y, cw, ch = (0.0, 0.0, w / d, h / d) if self.panel.area_key() == "full" else self.area_in
        x0, y0 = max(0, round(x * d)), max(0, round(y * d))
        x1, y1 = min(w, round((x + cw) * d)), min(h, round((y + ch) * d))
        return self._new_page(np.ascontiguousarray(self.preview_raw[y0:y1, x0:x1]), d)

    def save_preview_pdf(self) -> None:
        page = self._preview_crop_page()
        if page is not None:
            self._save_pages([page], "pdf")

    def save_preview_image(self) -> None:
        page = self._preview_crop_page()
        if page is not None:
            self._save_pages([page], self.panel.image_save_format())

    def add_preview_to_document(self) -> None:
        page = self._preview_crop_page()
        if page is not None and not self._finishing:
            self._add_page(page)
            self._set_status(f"Đã thêm vùng xem trước thành trang {self.page_list.count()}.")

    def insert_into_open_pdf(self) -> None:
        """Dựng PDF từ các trang đang có (tài liệu nhiều trang hoặc vùng xem trước) và gửi sang tab PDF đang mở."""
        if not self._has_active_doc or self._finishing:
            return
        pages = self._ordered_pages() if (self.mode == "multi" and self.pages) else []
        if not pages and self.preview_raw is not None:
            p = self._preview_crop_page()
            if p is not None:
                pages = [p]
        if not pages:
            return
        blobs, dpis = [], []
        for p in pages:
            img = p.render(p.settings, p.output)
            blobs.append(scanner.encode_page(img, p.output, p.dpi))
            dpis.append(p.dpi)
        pdf_bytes = scanner.build_pdf_bytes(blobs, dpis=dpis)
        self.insertPagesRequested.emit(pdf_bytes)
        if self.mode == "multi" and self.pages:
            self._clear_document()
            self._show_view("preview")
        self._set_status(f"Đã chèn {len(pages)} trang scan vào tài liệu đang mở (Ctrl+Z để hoàn tác).")

    def save_shortcut(self) -> None:
        if self._view == "document" and self.pages:
            self.finish_document()
        elif self.preview_raw is not None:
            self.save_preview_pdf()
        elif self.pages:
            self.finish_document()

    def _fit_area_to_bed(self) -> None:
        key = self.panel.area_key()
        if key == "custom":
            x, y, w, h = self.area_in
            w, h = min(w, self.bed_in[0]), min(h, self.bed_in[1])
            self.area_in = (min(max(x, 0.0), max(0.0, self.bed_in[0] - w)), min(max(y, 0.0), max(0.0, self.bed_in[1] - h)), w, h)
        else:
            self.area_in = scanner.paper_area(key, origin=self.area_in[:2], bed=self.bed_in)

    def _on_area_key_changed(self, _key: str) -> None:
        self._fit_area_to_bed()
        self._sync_crop()
        self._update_preview_info()
        self._set_status(f"Vùng scan: {self._area_text()}")

    def _on_crop_changed(self, rect: QRectF, resized: bool) -> None:
        self.area_in = tuple(v / scanner.PREVIEW_DPI for v in (rect.x(), rect.y(), rect.width(), rect.height()))  # type: ignore[assignment]
        if resized or self.panel.area_key() == "full":
            self.panel.select_area("custom")
        self._update_preview_info()
        self._set_status(f"Vùng scan: {self._area_text()}")

    def _sync_crop(self) -> None:
        self.preview_view.set_crop(QRectF(*(v * scanner.PREVIEW_DPI for v in self.area_in)))

    def _area_text(self) -> str:
        x, y, w, h = self.area_in
        return f"{w * 25.4:.0f} × {h * 25.4:.0f} mm, cách góc {x * 25.4:.0f}/{y * 25.4:.0f} mm"

    def _update_preview_info(self) -> None:
        _x, _y, w, h = self.area_in
        area = f"{self.panel.area_label()} · {w * 25.4:.0f} × {h * 25.4:.0f} mm"
        if self.preview_raw is None:
            self.preview_info.setText(f"Vùng scan: {area}")
        else:
            self.preview_info.setText(f"Ảnh xem trước {self.preview_dpi} dpi · Vùng: {area}")
        self._update_actions()

    # ─── Tài liệu nhiều trang ─────────────────────────────────────────────

    def _ordered_pages(self) -> List[scanner.Page]:
        return [self.pages[self.page_list.item(i).data(PAGE_ID)] for i in range(self.page_list.count())]

    def current_page(self) -> Optional[scanner.Page]:
        item = self.page_list.currentItem()
        return self.pages.get(item.data(PAGE_ID)) if item else None

    def _item_for(self, page_id: int) -> Optional[QListWidgetItem]:
        for i in range(self.page_list.count()):
            if self.page_list.item(i).data(PAGE_ID) == page_id:
                return self.page_list.item(i)
        return None

    def _add_page(self, page: scanner.Page, cache: bool = True) -> None:
        if self.mode != "multi":
            self.set_mode("multi")
        if cache:
            self._cache_page(page)
        self.pages[page.id] = page
        item = QListWidgetItem(QIcon(make_thumbnail(page.oriented_raw())), "")
        item.setData(PAGE_ID, page.id)
        self.page_list.addItem(item)
        self._renumber()
        self._show_view("document")
        self.page_list.setCurrentItem(item)
        self.page_list.scrollToItem(item)
        self._queue_thumbnails([page])
        self._write_manifest()
        self._update_actions()

    def _cache_page(self, page: scanner.Page) -> None:
        try:
            if self.session is None:
                self.session = scanner.ScanSession.create(self.cache_dir)
            self.session.add(page)
        except Exception as exc:
            log.warning("Không lưu tạm được trang scan: %s", exc)

    def _write_manifest(self) -> None:
        self._manifest_timer.stop()
        if self.session is not None:
            try:
                self.session.update(self._ordered_pages())
            except Exception:
                log.warning("Không ghi được session.json", exc_info=True)

    def _queue_thumbnails(self, pages: List[scanner.Page]) -> None:
        for page in pages:
            self._pool.start(
                _RenderTask(page, page.settings, page.output, -1, lambda: -1, self._render_signals),
                0,
            )

    def _renumber(self) -> None:
        for i in range(self.page_list.count()):
            item = self.page_list.item(i)
            page = self.pages[item.data(PAGE_ID)]
            item.setText(f"Trang {i + 1}\n{KIND_LABELS[page.output]}")

    def _on_pages_reordered(self, *_) -> None:
        self._renumber()
        self._write_manifest()
        self._update_actions()
        page = self.current_page()
        if page:
            self.doc_info.setText(self._page_info(page))

    def _page_info(self, page: scanner.Page, angle: Optional[float] = None) -> str:
        row = self.page_list.row(self._item_for(page.id)) + 1
        h, w = page.raw.shape[:2]
        text = f"Trang {row}/{self.page_list.count()} · {w}×{h} px · {page.dpi} dpi · {'màu' if page.is_color else 'xám'}"
        if angle:
            text += f" · chỉnh nghiêng {angle:+.2f}°"
        if page.source != "scan":
            text += f" · {Path(page.source).name}"
        return text

    def _on_current_page_changed(self, *_) -> None:
        page = self.current_page()
        if page is None:
            self.panel.clear_page()
            self.page_view.clear_image()
            self.doc_info.setText("Tài liệu trống" if self.mode == "multi" else "")
        elif not self._on_preview_tab():
            self.panel.show_page(page)
            self.doc_info.setText(self._page_info(page))
            self.request_render(keep_view=False)
        self._update_actions()

    def rotate_page(self, degrees: int) -> None:
        page = self.current_page()
        if page is None or self._finishing:
            return
        page.rotate(degrees)
        it = self._item_for(page.id)
        if it is not None:
            it.setIcon(QIcon(make_thumbnail(page.oriented_raw())))
        self._write_manifest()
        self._show_view("document")
        self.request_render(keep_view=False)

    def move_page(self, delta: int) -> None:
        row = self.page_list.currentRow()
        new_row = row + delta
        if row < 0 or self._finishing or not 0 <= new_row < self.page_list.count():
            return
        item = self.page_list.takeItem(row)
        self.page_list.insertItem(new_row, item)
        self.page_list.setCurrentRow(new_row)
        self._on_pages_reordered()

    def delete_page(self) -> None:
        item = self.page_list.currentItem()
        if item is None or self._finishing:
            return
        page = self.pages.pop(item.data(PAGE_ID), None)
        self.page_list.takeItem(self.page_list.row(item))
        if self.session is not None and page is not None:
            self.session.remove(page)
        self._renumber()
        if self.pages:
            self._write_manifest()
        elif self.session is not None:
            self.session.discard()
            self.session = None
        self._on_current_page_changed()

    def discard_document(self) -> None:
        if not self.pages or self._finishing:
            return
        if self.interactive:
            answer = QMessageBox.question(
                self,
                "Bỏ tài liệu",
                f"Xoá {len(self.pages)} trang của tài liệu đang scan?\nCác trang chưa lưu sẽ mất.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._clear_document()
        self._set_status("Đã bỏ tài liệu. Sẵn sàng scan tài liệu mới.")

    def _clear_document(self) -> None:
        self._manifest_timer.stop()
        self.page_list.clear()
        self.pages.clear()
        if self.session is not None:
            self.session.discard()
            self.session = None
        self._on_current_page_changed()

    def finish_document(self) -> None:
        pages = self._ordered_pages()
        if not pages or self._finishing:
            return
        self._write_manifest()
        path = self._choose_save_path("pdf")
        if not path:
            self._set_status("Chưa lưu — các trang vẫn được giữ tạm.")
            return
        self._finishing = True
        self._update_actions()
        self._save_pages(pages, "pdf", path, on_saved=self._on_document_saved, on_failed=self._on_document_failed)

    def _on_document_saved(self) -> None:
        self._finishing = False
        self._clear_document()
        self._show_view("preview")

    def _on_document_failed(self) -> None:
        self._finishing = False
        self._update_actions()

    def _page_menu(self, pos) -> None:
        if self.page_list.itemAt(pos) is None:
            return
        menu = QMenu(self)
        for a in (self.act_rot_left, self.act_rot_right, None, self.act_move_prev, self.act_move_next, None, self.act_delete):
            menu.addSeparator() if a is None else menu.addAction(a)
        menu.exec(self.page_list.mapToGlobal(pos))

    def open_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Mở ảnh", "", scanner.IMAGE_FILTER)
        if paths:
            self.add_image_files(paths)

    def add_image_files(self, paths: List[str | Path]) -> None:
        if self._finishing:
            return
        added, no_dpi = 0, []
        for path in paths:
            try:
                img, dpi = scanner.imread(path)
            except Exception as exc:
                self.banner.show_message("error", "Không mở được ảnh", f"{path}\n{exc}", timeout=0)
                continue
            if not dpi:
                no_dpi.append(Path(path).name)
                dpi = 300
            self._add_page(self._new_page(img, dpi, source=str(path)))
            added += 1
        msg = f"Đã thêm {added} ảnh vào tài liệu."
        if no_dpi:
            msg += " Ảnh không ghi dpi, tạm coi 300 dpi: " + ", ".join(no_dpi[:3])
        self._set_status(msg)

    def add_synthetic_page(self, output: Optional[str] = None) -> None:
        s, panel_output = self.panel.processing()
        page = scanner.Page(scanner.degraded_page(), replace(s, dpi=300), source="trang giả lập")
        page.apply(s, output or panel_output)
        self._add_page(page)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = [
            u.toLocalFile()
            for u in event.mimeData().urls()
            if u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in scanner.IMAGE_EXTS
        ]
        if paths:
            self.add_image_files(paths)

    # ─── Phiên bỏ dở ──────────────────────────────────────────────────────

    def _offer_restore(self) -> None:
        if self.pages:
            return
        for folder in scanner.find_orphan_sessions(self.cache_dir):
            session = scanner.ScanSession.open(folder)
            if session is None:
                continue
            n = session.page_count()
            if n == 0:
                session.discard()
                continue
            box = QMessageBox(self)
            box.setWindowTitle("Mở lại tài liệu đang scan dở?")
            box.setIcon(QMessageBox.Icon.Question)
            box.setText(f"Lần trước còn {n} trang scan chưa lưu thành PDF (lúc {session.created:%H:%M ngày %d/%m/%Y}).")
            box.setInformativeText("Mở lại để xem, sắp xếp và lưu tiếp?")
            reopen = box.addButton("Mở lại", QMessageBox.ButtonRole.AcceptRole)
            delete = box.addButton("Xoá các trang", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("Để sau", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(reopen)
            box.exec()
            if box.clickedButton() is reopen:
                self.restore_session(session)
            elif box.clickedButton() is delete:
                session.discard()
                continue
            else:
                session.release()
            return

    def restore_session(self, session: scanner.ScanSession) -> int:
        pages = session.load_pages()
        if not pages:
            session.discard()
            return 0
        if self.session is not None:
            for p in pages:
                self._add_page(p)
            session.discard()
        else:
            self.session = session
            for p in pages:
                self._add_page(p, cache=False)
        self.page_list.setCurrentRow(0)
        self._set_status(f"Đã mở lại {len(pages)} trang scan dở.")
        return len(pages)

    # ─── Xử lý ảnh bất đồng bộ ────────────────────────────────────────────

    def _on_processing_changed(self) -> None:
        if self._on_preview_tab():
            self.request_render(keep_view=True)
            return
        page = self.current_page()
        if page is None or self._finishing:
            return
        settings, output = self.panel.processing()
        page.apply(settings, output)
        if page.output != output:
            self.panel.show_page(page)
        self._renumber()
        self._manifest_timer.start()
        self.request_render(keep_view=True)

    def _apply_to_all(self) -> None:
        if self._finishing:
            return
        settings, output = self.panel.processing()
        for page in self.pages.values():
            page.apply(settings, output)
        self._renumber()
        self._write_manifest()
        self._set_status(f"Đã áp dụng thông số cho {len(self.pages)} trang.")
        self._queue_thumbnails([p for p in self._ordered_pages() if p is not self.current_page()])
        self.request_render(keep_view=True)

    def request_render(self, keep_view: bool = True) -> None:
        self._keep_view = (self._keep_view and keep_view) if self._render_timer.isActive() else keep_view
        self._render_timer.start()

    def _render_target(self):
        if self._on_preview_tab():
            if self.preview_page is None:
                return None
            self.preview_page.apply(*self._preview_processing())
            return self.preview_page, self.preview_view
        page = self.current_page()
        return (page, self.page_view) if page is not None else None

    def _start_render(self) -> None:
        target = self._render_target()
        if target is None:
            return
        page, view = target
        self._render_gen += 1
        if self.act_compare.isChecked():
            view.set_image(to_qimage(page.oriented_raw()), keep_view=self._keep_view or view is self.preview_view)
            self.renderFinished.emit()
            return
        self._set_status(PROCESSING_MSG)
        self._pool.start(
            _RenderTask(page, page.settings, page.output, self._render_gen, lambda: self._render_gen, self._render_signals),
            1,
        )

    def _on_rendered(self, gen: int, page_id: int, img: np.ndarray, angle: float) -> None:
        item = self._item_for(page_id)
        if item is not None:
            item.setIcon(QIcon(make_thumbnail(img)))
        if gen != self._render_gen:
            return
        if self.preview_page is not None and page_id == self.preview_page.id:
            self.preview_view.set_image(to_qimage(img), keep_view=True)
        else:
            page = self.current_page()
            if page is None or page.id != page_id:
                return
            self.page_view.set_image(to_qimage(img), keep_view=self._keep_view)
            self.doc_info.setText(self._page_info(page, angle))
        self._keep_view = True
        if self.status_lbl.text() == PROCESSING_MSG:
            self._set_status("Sẵn sàng.")
        self.renderFinished.emit()

    def _on_render_failed(self, _gen: int, message: str) -> None:
        self._set_status(f"Lỗi xử lý ảnh: {message}")

    # ─── Lưu file ─────────────────────────────────────────────────────────

    def _auto_path(self, fmt: str) -> str:
        folder = Path(self.panel.save_folder())
        folder.mkdir(parents=True, exist_ok=True)
        return str(_unique_path(folder, datetime.now().strftime("Scan_%Y-%m-%d_%H%M%S"), scanner.EXTENSIONS[fmt]))

    def _ask_save_path(self, fmt: str) -> Optional[str]:
        folder = Path(self.panel.save_folder())
        stem = datetime.now().strftime("Scan_%Y-%m-%d_%H%M%S")
        filters = [FORMAT_FILTERS["pdf"]] if fmt == "pdf" else [FORMAT_FILTERS[f] for f in ("jpg", "png", "tif")]
        title = "Lưu PDF" if fmt == "pdf" else "Lưu ảnh"
        path, chosen = QFileDialog.getSaveFileName(
            self,
            title,
            str(folder / f"{stem}{scanner.EXTENSIONS[fmt]}"),
            ";;".join(filters),
            FORMAT_FILTERS[fmt],
        )
        if not path:
            return None
        if Path(path).suffix.lower() not in SUFFIX_FORMATS:
            chosen_fmt = next((f for f, flt in FORMAT_FILTERS.items() if flt == chosen), fmt)
            path += scanner.EXTENSIONS[chosen_fmt]
        self.panel.set_save_folder(Path(path).parent)
        return path

    def _choose_save_path(self, fmt: str) -> Optional[str]:
        if self.panel.ask_filename() and self.interactive:
            return self._ask_save_path(fmt)
        return self._auto_path(fmt)

    def _save_pages(self, pages: list, fmt: str, path: Optional[str] = None, on_saved=None, on_failed=None) -> bool:
        if path is None:
            path = self._choose_save_path(fmt)
            if not path:
                self._set_status("Chưa lưu file.")
                return False
        fmt = SUFFIX_FORMATS.get(Path(path).suffix.lower(), fmt)
        jobs = [(p, copy(p.settings), p.output) for p in pages]
        thread = ExportThread(jobs, path, fmt, self)
        thread.on_saved = on_saved
        thread.on_failed = on_failed
        thread.progress.connect(self._on_export_progress)
        thread.exported.connect(self._on_saved)
        thread.failed.connect(self._on_save_failed)
        self._exports.add(thread)
        self.export_progress.setRange(0, len(jobs))
        self.export_progress.setValue(0)
        self.export_progress.show()
        self._set_status(f"Đang lưu {Path(path).name}…")
        self._update_actions()
        thread.start()
        return True

    def _on_export_progress(self, done: int, total: int) -> None:
        self.export_progress.setRange(0, total)
        self.export_progress.setValue(done)
        if total > 1:
            self._set_status(f"Đang tạo PDF… trang {done}/{total}")

    def _export_done(self, thread: ExportThread) -> None:
        thread.wait()
        self._exports.discard(thread)
        self.export_progress.setVisible(bool(self._exports))
        self._update_actions()

    def _on_saved(self, thread: ExportThread, path: str, size: int, thumb) -> None:
        self._export_done(thread)
        n = len(thread.jobs)
        if thread.on_saved:
            thread.on_saved()
        self._set_status(f"Đã lưu {path} ({size / 1024:.0f} KB).")
        pm = QPixmap.fromImage(to_qimage(thumb)) if thumb is not None else None
        detail = f"{n} trang · {size / 1024:.0f} KB · {Path(path).parent}"
        actions: list[tuple[str, Callable[[], None]]] = []
        if Path(path).suffix.lower() == ".pdf":
            actions.append(("Mở trong QT PDF Pro", lambda p=path: self.pdfSaved.emit(p, True)))
            self.pdfSaved.emit(path, self.panel.should_auto_open_pdf())
        else:
            actions.append(("Mở file", lambda p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(p))))
        actions.append(("Mở thư mục", lambda p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(p).parent)))))
        self.banner.show_message("success", f"Đã lưu {Path(path).name}", detail, thumb=pm, actions=actions)

    def _on_save_failed(self, thread: ExportThread, message: str) -> None:
        self._export_done(thread)
        if thread.on_failed:
            thread.on_failed()
        self._set_status(f"Không lưu được file: {message}")
        self.banner.show_message("error", "Không lưu được file", message, timeout=0)

    # ─── Lưu / khôi phục thiết lập & đóng cửa sổ ─────────────────────────

    def _save_state(self) -> None:
        data = {
            "mode": self.mode,
            "panel": self.panel.state(),
            "area_in": list(self.area_in),
        }
        try:
            p = _state_file_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _restore_state(self) -> None:
        p = _state_file_path()
        if not p.is_file():
            self._update_preview_info()
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self.mode = "multi" if data.get("mode") == "multi" else "single"
            if isinstance(data.get("panel"), dict):
                self.panel.restore(data["panel"])
            area = data.get("area_in")
            if isinstance(area, list) and len(area) == 4:
                self.area_in = tuple(float(v) for v in area)  # type: ignore[assignment]
            self._fit_area_to_bed()
        except Exception:
            log.warning("Không khôi phục được cấu hình Scan đã lưu", exc_info=True)
        self._update_preview_info()

    def _wait_background(self) -> None:
        self._render_timer.stop()
        self._manifest_timer.stop()
        if self._device_thread is not None:
            self._device_thread.wait(3000)
        if self._scan_thread is not None:
            if isinstance(self._scan_thread, ScanThread):
                self._scan_thread.cancel()
            self._scan_thread.wait(3000)
        for t in list(self._exports):
            t.wait(5000)
        self._pool.waitForDone(5000)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._scan_thread is not None or self._exports:
            if self.interactive:
                QMessageBox.information(self, "Scan tài liệu", "Đang scan hoặc đang lưu file. Hãy đợi xong rồi đóng.")
                event.ignore()
                return
        keep = False
        if self.pages and self.interactive:
            box = QMessageBox(self)
            box.setWindowTitle("Tài liệu chưa lưu")
            box.setIcon(QMessageBox.Icon.Question)
            box.setText(f"Tài liệu nhiều trang còn {len(self.pages)} trang chưa lưu thành PDF.")
            keep_btn = None
            if self.session is not None:
                box.setInformativeText("«Giữ lại»: lần mở sau sẽ hỏi để làm tiếp.\n«Bỏ các trang»: xoá hẳn.")
                keep_btn = box.addButton("Giữ lại", QMessageBox.ButtonRole.AcceptRole)
            drop_btn = box.addButton("Bỏ các trang", QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = box.addButton("Huỷ", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(keep_btn or cancel_btn)
            box.exec()
            clicked = box.clickedButton()
            if clicked is None or clicked not in (keep_btn, drop_btn):
                event.ignore()
                return
            keep = clicked is keep_btn
        if self.session is not None:
            if keep:
                self._write_manifest()
                self.session.release()
            else:
                self.session.discard()
            self.session = None
        if self.interactive:
            self._save_state()
        self._wait_background()
        event.accept()
