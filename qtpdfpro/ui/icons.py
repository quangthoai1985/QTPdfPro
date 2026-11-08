"""Biểu tượng Lucide (SVG) tô màu theo giao diện Sáng/Tối.

SVG gốc nằm ở `assets/icons/<tên>.svg` (tải bằng `tools/fetch_lucide_icons.py`, giấy phép ISC). `icon()` thay
`currentColor` bằng màu hiện tại rồi dựng bằng `QSvgRenderer`; `bind()` ghi nhớ nút (tham chiếu yếu) để
`set_icon_color()` tô lại khi đổi giao diện.
"""

from __future__ import annotations

import logging
import weakref
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton

ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"

ICON_NAMES: tuple[str, ...] = (
    "house", "folder-open", "menu", "sun", "moon", "search", "text-cursor", "hand",
    "chevron-left", "chevron-right", "rotate-ccw", "rotate-cw", "book-open", "printer", "info",
    "file-text", "scan-text", "badge-check", "microscope", "scan-eye", "files", "mouse-pointer-2",
    "highlighter", "pen-line", "type", "message-square", "stamp", "eraser", "undo-2", "redo-2",
    "layers", "combine", "scissors", "file-output", "file-archive", "droplet", "list-ordered",
    "save", "pen-tool", "signature", "square-check", "calendar", "shield-check", "lock",
    "lock-open", "layout-panel-top", "list", "panel-right", "x", "ellipsis", "code-xml",
)

_DEFAULT_COLOR = "#E6E8EC"  # màu chữ giao diện Tối (`_DARK_TOKENS["text"]`)
_color = _DEFAULT_COLOR
_cache: dict[tuple[str, str, int, float], QIcon] = {}
_bound: list[tuple[weakref.ref, str, int]] = []


def icon_path(name: str) -> Path:
    return ICON_DIR / f"{name}.svg"


def current_color() -> str:
    return _color


def _device_ratio() -> float:
    screen = QGuiApplication.primaryScreen()
    return float(screen.devicePixelRatio()) if screen is not None else 1.0


def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    color = color or _color
    ratio = _device_ratio()
    key = (name, color, size, ratio)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    path = icon_path(name)
    try:
        svg = path.read_text(encoding="utf-8")
    except OSError:
        logging.warning("Thiếu biểu tượng: %s", path)
        return QIcon()
    renderer = QSvgRenderer(QByteArray(svg.replace("currentColor", color).encode("utf-8")))
    if not renderer.isValid():
        logging.warning("Biểu tượng SVG không hợp lệ: %s", path)
        return QIcon()
    side = max(1, round(size * ratio))
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, side, side))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    result = QIcon(pixmap)
    _cache[key] = result
    return result


def bind(button: QAbstractButton, name: str, size: int = 18) -> None:
    """Đặt biểu tượng cho nút và ghi nhớ để tô lại khi đổi màu."""
    button.setIcon(icon(name, size=size))
    _bound[:] = [entry for entry in _bound if entry[0]() is not button]
    _bound.append((weakref.ref(button), name, size))


def set_icon_color(color: str) -> None:
    """Đổi màu biểu tượng hiện tại, xoá đệm và tô lại mọi nút đã `bind`."""
    global _color
    _color = color
    _cache.clear()
    alive = []
    for ref, name, size in _bound:
        button = ref()
        if button is None:
            continue
        try:
            button.setIcon(icon(name, size=size))
        except RuntimeError:  # đối tượng C++ đã bị huỷ
            continue
        alive.append((ref, name, size))
    _bound[:] = alive
