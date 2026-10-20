"""Bảng lệnh tìm nhanh mọi công cụ (Ctrl+K) kiểu PdfCraft."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.ui.tool_catalog import CATEGORIES, COMING_SOON_LABEL, tools_for

SEARCH_IN_DOCUMENT_KEY = "__search_in_document__"


class CommandPaletteDialog(QDialog):
    """Hộp tìm công cụ & lệnh; Enter chạy mục đang chọn. Trả về khoá công cụ qua `selected_key`."""

    def __init__(self, parent: QWidget | None = None, query: str = "", has_document: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("commandPalette")
        self.setWindowTitle("Tìm công cụ và lệnh")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setModal(True)
        self.resize(620, 440)
        self.selected_key: Optional[str] = None
        self.search_text: str = ""
        self._has_document = has_document

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 10)
        lay.setSpacing(8)
        self.input = QLineEdit(query)
        self.input.setObjectName("paletteInput")
        self.input.setPlaceholderText("🔍 Tìm công cụ và lệnh… (Esc để đóng)")
        self.input.textChanged.connect(self._refresh)
        self.input.installEventFilter(self)
        lay.addWidget(self.input)

        self.list = QListWidget()
        self.list.setObjectName("paletteList")
        self.list.itemActivated.connect(self._accept_item)
        self.list.itemClicked.connect(self._accept_item)
        lay.addWidget(self.list, 1)

        hint = QLabel("↑ ↓ để chọn  ·  Enter để chạy  ·  Công cụ «" + COMING_SOON_LABEL + "» đang phát triển")
        hint.setObjectName("mutedLabel")
        lay.addWidget(hint)
        self._refresh()

    def _refresh(self) -> None:
        q = self.input.text()
        self.list.clear()
        if self._has_document and q.strip():
            it = QListWidgetItem(f"🔎  Tìm «{q.strip()}» trong tài liệu đang mở")
            it.setData(Qt.ItemDataRole.UserRole, SEARCH_IN_DOCUMENT_KEY)
            self.list.addItem(it)
        for t in tools_for("all", q):
            group = dict(CATEGORIES).get(t.category, "").replace("&&", "&")
            suffix = "" if t.ready else f"   —   {COMING_SOON_LABEL} ({t.milestone})"
            it = QListWidgetItem(f"{t.icon}  {t.name}    ·  {group}{suffix}")
            it.setData(Qt.ItemDataRole.UserRole, t.key)
            it.setToolTip(t.summary)
            if not t.ready:
                it.setForeground(self.palette().placeholderText())
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - API Qt
        if obj is self.input and isinstance(event, QKeyEvent) and event.type() == QKeyEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentRow() + (1 if key == Qt.Key.Key_Down else -1)
                self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self.list.currentItem()
                if item is not None:
                    self._accept_item(item)
                return True
        return super().eventFilter(obj, event)

    def _accept_item(self, item: QListWidgetItem) -> None:
        self.selected_key = item.data(Qt.ItemDataRole.UserRole)
        self.search_text = self.input.text().strip()
        self.accept()
