"""Bảng lệnh Ctrl+K: liệt kê mọi lệnh của `ui/commands.py` (công cụ 5 thẻ + lệnh hệ thống) kèm phím tắt."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QFontMetrics, QIcon, QKeyEvent, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.ui import commands, icons

SEARCH_IN_DOCUMENT_KEY = "__search_in_document__"
NEEDS_DOCUMENT_NOTE = "cần mở tệp"

KEY_ROLE = Qt.ItemDataRole.UserRole
SHORTCUT_ROLE = Qt.ItemDataRole.UserRole + 1
NOTE_ROLE = Qt.ItemDataRole.UserRole + 2
GROUP_ROLE = Qt.ItemDataRole.UserRole + 3


class _CommandRowDelegate(QStyledItemDelegate):
    """Một dòng: biểu tượng · tên · tên thẻ (+ «cần mở tệp» mờ) · phím tắt căn phải."""

    ROW_HEIGHT = 34

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802 - API Qt
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        opt.text = ""
        opt.icon = QIcon()  # vẽ nền / vùng chọn theo QSS, biểu tượng và chữ tự vẽ bên dưới
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        rect = option.rect.adjusted(10, 0, -12, 0)
        # Nền dòng chọn là màu nhấn nhạt (QSS) ở cả hai giao diện → giữ màu chữ thường cho dễ đọc
        text_color = opt.palette.color(QPalette.ColorRole.Text)
        muted = opt.palette.color(QPalette.ColorRole.PlaceholderText)

        painter.save()
        painter.setFont(opt.font)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        x = rect.left()
        if icon is not None and not icon.isNull():
            side = 18
            icon.paint(painter, QRect(x, rect.top() + (rect.height() - side) // 2, side, side))
        x += 28
        fm = QFontMetrics(opt.font)
        shortcut = index.data(SHORTCUT_ROLE) or ""
        sc_w = fm.horizontalAdvance(shortcut) + 2 if shortcut else 0
        right = rect.right() - (sc_w + 16 if shortcut else 0)
        center = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        label = index.data(Qt.ItemDataRole.DisplayRole) or ""
        label_w = min(fm.horizontalAdvance(label) + 2, max(0, right - x))
        painter.setPen(text_color)
        painter.drawText(QRect(x, rect.top(), label_w, rect.height()), center,
                         fm.elidedText(label, Qt.TextElideMode.ElideRight, label_w))
        x += label_w + 14
        extra = "  ·  ".join(p for p in (index.data(GROUP_ROLE), index.data(NOTE_ROLE)) if p)
        if extra and x < right:
            painter.setPen(muted)
            painter.drawText(QRect(x, rect.top(), right - x, rect.height()), center,
                             fm.elidedText(extra, Qt.TextElideMode.ElideRight, right - x))
        if shortcut:
            painter.setPen(muted)
            painter.drawText(QRect(rect.right() - sc_w, rect.top(), sc_w, rect.height()),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, shortcut)
        painter.restore()


class CommandPaletteDialog(QDialog):
    """Hộp tìm lệnh; Enter chạy mục đang chọn. Trả về khoá lệnh qua `selected_key` (`window.run_command`)."""

    KEY_ROLE = KEY_ROLE
    SHORTCUT_ROLE = SHORTCUT_ROLE
    NOTE_ROLE = NOTE_ROLE
    GROUP_ROLE = GROUP_ROLE

    def __init__(self, parent: QWidget | None = None, query: str = "", has_document: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("commandPalette")
        self.setWindowTitle("Tìm lệnh")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setModal(True)
        self.resize(640, 460)
        self.selected_key: Optional[str] = None
        self.search_text: str = ""
        self._has_document = has_document

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 10)
        lay.setSpacing(8)
        self.input = QLineEdit(query)
        self.input.setObjectName("paletteInput")
        self.input.setPlaceholderText("Tìm lệnh… (Esc để đóng)")
        self.input.addAction(icons.icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.input.textChanged.connect(self._refresh)
        self.input.installEventFilter(self)
        lay.addWidget(self.input)

        self.list = QListWidget()
        self.list.setObjectName("paletteList")
        self.list.setItemDelegate(_CommandRowDelegate(self.list))
        self.list.setUniformItemSizes(True)
        self.list.itemActivated.connect(self._accept_item)
        self.list.itemClicked.connect(self._accept_item)
        lay.addWidget(self.list, 1)

        hint = QLabel("↑ ↓ để chọn  ·  Enter để chạy  ·  Lệnh ghi «cần mở tệp» sẽ hỏi mở tệp PDF trước")
        hint.setObjectName("mutedLabel")
        lay.addWidget(hint)
        self._refresh()

    def _refresh(self) -> None:
        q = self.input.text()
        self.list.clear()
        if self._has_document and q.strip():
            it = QListWidgetItem(icons.icon("search"), f"Tìm «{q.strip()}» trong tài liệu đang mở")
            it.setData(KEY_ROLE, SEARCH_IN_DOCUMENT_KEY)
            it.setData(SHORTCUT_ROLE, "")
            it.setData(NOTE_ROLE, "")
            it.setData(GROUP_ROLE, "")
            self.list.addItem(it)
        for c in commands.search(q, self._has_document):
            it = QListWidgetItem(icons.icon(c.icon), c.label_text())
            it.setData(KEY_ROLE, c.key)
            it.setData(SHORTCUT_ROLE, c.shortcuts()[0] if c.shortcut else "")
            it.setData(NOTE_ROLE, NEEDS_DOCUMENT_NOTE if c.needs_document and not self._has_document else "")
            it.setData(GROUP_ROLE, commands.TAB_LABELS[c.tab].replace("&&", "&"))
            if c.summary:
                it.setToolTip(c.summary)
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
        self.selected_key = item.data(KEY_ROLE)
        self.search_text = self.input.text().strip()
        self.accept()
