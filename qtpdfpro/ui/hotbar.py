"""Thanh công cụ nổi nhanh (`FloatingHotbar` — tương tự Hotbar của PdfCraft).

Đặt nổi ở bên trái vùng đọc PDF, có tay nắm 6 chấm ở đỉnh để kéo thả tự do trong vùng khung đọc.
Cung cấp các công cụ dùng nhiều nhất (Chọn, Bàn tay, Cắt trang, Ghi chú, Tô sáng, Bút vẽ,
Hộp chữ, Chèn ảnh, Đóng dấu, Chữ ký) và nút Tuỳ chỉnh (bật/tắt từng nút, đặt lại vị trí, ẩn thanh).
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from qtpdfpro.ui import icons

# (khoá công cụ, tên biểu tượng Lucide, chú giải tiếng Việt)
HOTBAR_ITEMS: Tuple[Tuple[str, str, str], ...] = (
    ("select", "mouse-pointer-2", "Chọn chữ / Chọn đối tượng (V)"),
    ("hand", "hand", "Bàn tay kéo cuộn trang (H)"),
    ("crop", "crop", "Cắt lề trang (C)"),
    ("note", "message-square", "Ghi chú dán (N)"),
    ("highlight", "highlighter", "Tô sáng văn bản"),
    ("pen", "pen-line", "Bút vẽ tay (P)"),
    ("text", "type", "Văn bản / Hộp chữ (T)"),
    ("image", "image-plus", "Chèn ảnh vào trang (I)"),
    ("stamp", "stamp", "Đóng dấu (D)"),
    ("fill_sign", "signature", "Điền && Ký — Chữ ký (S)"),
)


class _HotbarGrip(QLabel):
    """Tay nắm 6 chấm ở đỉnh Hotbar — nhấn giữ chuột trái để kéo thả vị trí thanh nổi."""

    def __init__(self, hotbar: "FloatingHotbar") -> None:
        super().__init__(hotbar)
        self._hotbar = hotbar
        self._drag_offset: Optional[QPoint] = None
        self.setObjectName("hotbarGrip")
        self.setFixedSize(32, 16)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Kéo để di chuyển thanh công cụ nhanh")
        self.refresh_icon()

    def refresh_icon(self) -> None:
        self.setPixmap(icons.icon("grip-horizontal", size=14).pixmap(14, 14))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._hotbar.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            target = event.globalPosition().toPoint() - self._drag_offset
            self._hotbar.move_clamped(target)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._hotbar._user_positioned = True
            event.accept()
            return
        super().mouseReleaseEvent(event)


class FloatingHotbar(QFrame):
    """Thanh công cụ nhanh dạng viên thuốc dọc nổi trên khung đọc PDF."""

    toolTriggered = Signal(str)
    hideRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("floatingHotbar")
        self.setFixedWidth(40)
        self._user_positioned = False
        self._visible_tools: set[str] = {k for k, _i, _t in HOTBAR_ITEMS}
        self.tool_buttons: Dict[str, QToolButton] = {}

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(15, 23, 42, 38))
        self.setGraphicsEffect(shadow)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 5)
        lay.setSpacing(2)

        self.grip = _HotbarGrip(self)
        lay.addWidget(self.grip, 0, Qt.AlignmentFlag.AlignHCenter)

        for key, icon_name, tip in HOTBAR_ITEMS:
            btn = QToolButton(self)
            btn.setObjectName("hotbarBtn")
            btn.setCheckable(True)
            btn.setFixedSize(30, 30)
            btn.setIconSize(QSize(16, 16))
            btn.setToolTip(tip.replace("&&", "&"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            icons.bind(btn, icon_name, 16)
            btn.clicked.connect(lambda _c=False, k=key: self.toolTriggered.emit(k))
            lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self.tool_buttons[key] = btn

        sep = QFrame(self)
        sep.setObjectName("hotbarSep")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        self.btn_settings = QToolButton(self)
        self.btn_settings.setObjectName("hotbarBtn")
        self.btn_settings.setFixedSize(30, 28)
        self.btn_settings.setIconSize(QSize(15, 15))
        self.btn_settings.setToolTip("Tuỳ chỉnh thanh công cụ nhanh (Hotbar)")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        icons.bind(self.btn_settings, "settings", 15)
        self.btn_settings.clicked.connect(self._open_customize_menu)
        lay.addWidget(self.btn_settings, 0, Qt.AlignmentFlag.AlignHCenter)

        self.adjustSize()

    def move_clamped(self, pos: QPoint) -> None:
        """Di chuyển thanh nổi nhưng luôn giữ lọt trong vùng widget cha."""
        parent = self.parentWidget()
        if parent is None:
            self.move(pos)
            return
        max_x = max(8, parent.width() - self.width() - 8)
        max_y = max(8, parent.height() - self.height() - 8)
        x = max(8, min(pos.x(), max_x))
        y = max(8, min(pos.y(), max_y))
        self.move(x, y)

    def reposition_for_parent(self, top_offset: int = 14) -> None:
        """Cập nhật vị trí mặc định ở góc trái khung đọc (hoặc kẹp lại nếu người dùng đã kéo)."""
        if not self._user_positioned:
            self.move_clamped(QPoint(12, max(12, top_offset)))
        else:
            self.move_clamped(self.pos())

    def reset_position(self, top_offset: int = 14) -> None:
        self._user_positioned = False
        self.reposition_for_parent(top_offset=top_offset)

    def set_visible_tools(self, keys: Iterable[str]) -> None:
        self._visible_tools = set(keys)
        for key, btn in self.tool_buttons.items():
            btn.setVisible(key in self._visible_tools)
        self.adjustSize()
        self.move_clamped(self.pos())

    def visible_tools(self) -> List[str]:
        return [k for k, _i, _t in HOTBAR_ITEMS if k in self._visible_tools]

    def sync_state(self, active_key: Optional[str]) -> None:
        """Đánh dấu nút tương ứng với chế độ/công cụ hiện hành (`select`, `hand`, `crop`, `text`, ...)."""
        for key, btn in self.tool_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(key == active_key)
            btn.blockSignals(False)

    def _open_customize_menu(self) -> None:
        menu = QMenu(self)
        for key, _icon, tip in HOTBAR_ITEMS:
            label = tip.split(" (")[0].replace("&", "&&")
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(key in self._visible_tools)
            act.toggled.connect(lambda checked, k=key: self._toggle_tool_visibility(k, checked))
        menu.addSeparator()
        menu.addAction("Đặt lại vị trí mặc định", lambda: self.reset_position())
        menu.addAction("Ẩn thanh công cụ nhanh", self.hideRequested.emit)
        menu.exec(self.btn_settings.mapToGlobal(QPoint(self.btn_settings.width() + 4, 0)))

    def _toggle_tool_visibility(self, key: str, visible: bool) -> None:
        if visible:
            self._visible_tools.add(key)
        elif len(self._visible_tools) > 1:
            self._visible_tools.discard(key)
        self.set_visible_tools(self._visible_tools)
