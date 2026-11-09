"""Tầng 1: thanh trên cùng — Trang chủ · Mở · tab tài liệu · nhãn bản mới · «Tìm lệnh» · Sáng/Tối · ☰.

Mọi hành vi đi qua `QAction` của `MainWindow.command_actions` (nguồn lệnh `ui/commands.py`); thanh này chỉ dựng
giao diện. Menu ☰ liệt kê các mục theo spec §5.1.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTabBar,
    QToolButton,
    QWidget,
)

from . import icons

SEARCH_PLACEHOLDER = "Tìm lệnh…  Ctrl+K"
_THEME_TIPS = {
    "dark": "Đang ở giao diện Tối — bấm để chuyển sang Sáng (Ctrl+Shift+T)",
    "light": "Đang ở giao diện Sáng — bấm để chuyển sang Tối (Ctrl+Shift+T)",
}


class TopBar(QFrame):
    """Hàng duy nhất ở trên cùng cửa sổ."""

    paletteRequested = Signal(str)  # Enter / gõ trong ô tìm → mở Ctrl+K với chuỗi đã gõ

    def __init__(self, actions: dict[str, QAction], recent_menu: QMenu, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        self._actions = actions
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)

        self.btn_home = self._text_button("Trang chủ", "house", "Trang chủ (Alt+Home)", "home")
        self.btn_home.setCheckable(True)
        self.btn_open = self._text_button("Mở", "folder-open", "Mở tệp PDF (Ctrl+O)", "open")
        lay.addWidget(self.btn_home)
        lay.addWidget(self.btn_open)
        lay.addSpacing(6)

        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("docTabBar")
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setMovable(True)
        self.tab_bar.setDocumentMode(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setUsesScrollButtons(True)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.tab_bar.setVisible(False)
        lay.addWidget(self.tab_bar, 1)
        lay.addStretch(0)

        self.btn_update_badge = QPushButton("")
        self.btn_update_badge.setObjectName("updateBadgeBtn")
        self.btn_update_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update_badge.setVisible(False)
        lay.addWidget(self.btn_update_badge)

        self.search = QLineEdit()
        self.search.setObjectName("commandSearch")
        self.search.setPlaceholderText(SEARCH_PLACEHOLDER)
        self.search.setFixedWidth(230)
        self.search.setClearButtonEnabled(False)
        self._search_action = self.search.addAction(icons.icon("search", size=16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.returnPressed.connect(self._open_palette)
        self.search.textEdited.connect(lambda _t: QTimer.singleShot(0, self._open_palette))
        lay.addWidget(self.search)

        self.btn_theme = QToolButton()
        self.btn_theme.setObjectName("iconBtn")
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.setIconSize(QSize(18, 18))
        self.btn_theme.clicked.connect(lambda: self._trigger("toggle_theme"))
        lay.addWidget(self.btn_theme)

        self.menu = QMenu(self)
        self._build_menu(recent_menu)
        self.btn_menu = QToolButton()
        self.btn_menu.setObjectName("iconBtn")
        self.btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_menu.setIconSize(QSize(18, 18))
        self.btn_menu.setToolTip("Menu")
        self.btn_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_menu.setMenu(self.menu)
        icons.bind(self.btn_menu, "menu")
        lay.addWidget(self.btn_menu)

        self.set_theme("dark")

    # ─── Dựng ──────────────────────────────────────────────────────────────

    def _text_button(self, text: str, icon_name: str, tip: str, key: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("topBtn")
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIconSize(QSize(16, 16))
        icons.bind(btn, icon_name, 16)
        btn.clicked.connect(lambda _checked=False, k=key: self._trigger(k))
        return btn

    def _trigger(self, key: str) -> None:
        act = self._actions.get(key)
        if act is not None:
            act.trigger()

    def _build_menu(self, recent_menu: QMenu) -> None:
        a, m = self._actions, self.menu
        m.addAction(a["open"])
        m.addMenu(recent_menu)
        m.addSeparator()
        for key in ("close_tab", "save", "save_as"):
            m.addAction(a[key])
        m.addSeparator()
        m.addAction(a["toggle_sidebar"])
        settings = m.addMenu("Cài đặt")
        for key in ("auto_check_updates", "auto_download_updates", "default_app"):
            settings.addAction(a[key])
        m.addSeparator()
        m.addAction(a["check_update"])
        m.addAction(a["github"])
        m.addAction(a["about"])
        m.addSeparator()
        m.addAction(a["quit"])

    def _open_palette(self) -> None:
        text = self.search.text()
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.paletteRequested.emit(text.strip())

    # ─── Trạng thái ────────────────────────────────────────────────────────

    def set_theme(self, theme: str) -> None:
        """Biểu tượng `sun` khi đang Tối (bấm để sang Sáng), `moon` khi đang Sáng."""
        theme = "light" if theme == "light" else "dark"
        self.btn_theme.setIcon(icons.icon("moon" if theme == "light" else "sun"))
        self.btn_theme.setToolTip(_THEME_TIPS[theme])
        self._search_action.setIcon(icons.icon("search", size=16))
        self.btn_home.setIcon(icons.icon("house", size=16))
        self.btn_open.setIcon(icons.icon("folder-open", size=16))
        self.btn_menu.setIcon(icons.icon("menu"))

    def show_update_badge(self, text: str = "", ready: bool = False) -> None:
        """Hiện/ẩn nhãn nhắc bản mới (`text` rỗng = ẩn)."""
        self.btn_update_badge.setText(text)
        self.btn_update_badge.setProperty("ready", ready)
        self.btn_update_badge.style().unpolish(self.btn_update_badge)
        self.btn_update_badge.style().polish(self.btn_update_badge)
        self.btn_update_badge.setVisible(bool(text))

    def visible_command_keys(self) -> list[str]:
        """Khoá lệnh của các nút lệnh đang hiện (nút ☰ không phải lệnh)."""
        pairs = (("home", self.btn_home), ("open", self.btn_open), ("palette", self.search),
                 ("toggle_theme", self.btn_theme))
        return [key for key, widget in pairs if not widget.isHidden()]
