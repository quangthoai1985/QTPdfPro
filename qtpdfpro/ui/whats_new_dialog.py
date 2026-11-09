"""Hộp thoại «Có gì mới trong QT PDF Pro» và bộ điều khiển hiện nó sau khi cập nhật.

Nội dung đến từ `core/whats_new.py` (tệp `assets/whats_new.json`). Bộ điều khiển KHÔNG tự chạy trong
`MainWindow.__init__`: `ui/app.py` gọi `on_startup()` sau khi cửa sổ hiện (test không bật hộp thoại).
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro import __github_repo__, __version__
from qtpdfpro.core import whats_new as wn
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui import icons

STARTUP_DELAY_MS = 700


def release_url(version: str) -> str:
    return f"https://github.com/{__github_repo__}/releases/tag/v{version}"


def _item_card(item: wn.NoteItem) -> QFrame:
    card = QFrame()
    card.setObjectName("whatsNewItem")
    lay = QHBoxLayout(card)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(12)
    ico = QLabel()
    ico.setObjectName("whatsNewIcon")
    ico.setFixedSize(36, 36)
    ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if item.icon:
        ico.setPixmap(icons.icon(item.icon, size=20).pixmap(20, 20))
    lay.addWidget(ico, 0, Qt.AlignmentFlag.AlignTop)
    col = QVBoxLayout()
    col.setSpacing(2)
    head = QHBoxLayout()
    head.setSpacing(8)
    title = QLabel(item.title)
    title.setObjectName("whatsNewItemTitle")
    head.addWidget(title)
    if item.shortcut:
        chip = QLabel(item.shortcut)
        chip.setObjectName("whatsNewKey")
        head.addWidget(chip)
    head.addStretch(1)
    col.addLayout(head)
    text = QLabel(item.text)
    text.setObjectName("whatsNewItemText")
    text.setWordWrap(True)
    col.addWidget(text)
    lay.addLayout(col, 1)
    return card


def _version_block(notes: wn.VersionNotes) -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    for item in notes.items:
        lay.addWidget(_item_card(item))
    return box


class WhatsNewDialog(QDialog):
    """Bản mới nhất mở sẵn; các bản cũ hơn nằm trong một khung thu gọn."""

    def __init__(self, notes: list[wn.VersionNotes], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.notes = list(notes)
        newest = self.notes[0] if self.notes else wn.VersionNotes(__version__, "", "", ())
        self.setObjectName("whatsNewDialog")
        self.setWindowTitle("Có gì mới")
        self.setModal(True)
        self.resize(560, 600)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(12)

        title = QLabel(f"Có gì mới trong QT PDF Pro {newest.version}")
        title.setObjectName("whatsNewTitle")
        title.setWordWrap(True)
        root.addWidget(title)
        sub = " · ".join(p for p in (newest.date, newest.headline) if p)
        if sub:
            sub_lbl = QLabel(sub)
            sub_lbl.setObjectName("whatsNewSub")
            sub_lbl.setWordWrap(True)
            root.addWidget(sub_lbl)

        scroll = QScrollArea()
        scroll.setObjectName("whatsNewScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("whatsNewBody")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 6, 0)
        body_lay.setSpacing(10)
        body_lay.addWidget(_version_block(newest))

        self.older_toggle = QToolButton()
        self.older_body = QWidget()
        older = self.notes[1:]
        if older:
            span = older[-1].version if len(older) == 1 else f"{older[-1].version} – {older[0].version}"
            self.older_toggle.setObjectName("whatsNewToggle")
            self.older_toggle.setText(f"Các bản trước ({span})")
            self.older_toggle.setCheckable(True)
            self.older_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.older_toggle.setArrowType(Qt.ArrowType.RightArrow)
            self.older_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            self.older_toggle.toggled.connect(self._toggle_older)
            body_lay.addWidget(self.older_toggle, 0, Qt.AlignmentFlag.AlignLeft)
            ol = QVBoxLayout(self.older_body)
            ol.setContentsMargins(0, 0, 0, 0)
            ol.setSpacing(8)
            for n in older:
                head = QLabel(f"Bản {n.version}" + (f" · {n.date}" if n.date else "")
                              + (f" · {n.headline}" if n.headline else ""))
                head.setObjectName("whatsNewOlderHead")
                head.setWordWrap(True)
                ol.addWidget(head)
                ol.addWidget(_version_block(n))
            body_lay.addWidget(self.older_body)
        self.older_body.hide()
        body_lay.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_github = QPushButton("Xem đầy đủ trên GitHub")
        self.btn_github.setAutoDefault(False)
        self.btn_github.clicked.connect(self._open_github)
        row.addWidget(self.btn_github)
        row.addStretch(1)
        self.btn_start = QPushButton("Bắt đầu dùng")
        self.btn_start.setObjectName("primaryConvertBtn")
        self.btn_start.setDefault(True)
        self.btn_start.clicked.connect(self.accept)
        row.addWidget(self.btn_start)
        root.addLayout(row)
        self.btn_start.setFocus()

    def _toggle_older(self, on: bool) -> None:
        self.older_toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.older_body.setVisible(on)

    def _open_github(self) -> None:
        version = self.notes[0].version if self.notes else __version__
        QDesktopServices.openUrl(QUrl(release_url(version)))


class WhatsNewController:
    """`window.whats_new`: hiện «Có gì mới» một lần sau khi cập nhật, và mở lại theo yêu cầu."""

    def __init__(self, window: QWidget, settings: AppSettings) -> None:
        self.window = window
        self.settings = settings
        self.dialog_factory: Callable[[list[wn.VersionNotes], QWidget | None], QDialog] = (
            lambda notes, parent: WhatsNewDialog(notes, parent))
        self._due: list[wn.VersionNotes] = []

    def on_startup(self) -> bool:
        """True nếu sắp hiện hộp thoại (để `app.py` bỏ qua hộp thoại khởi động khác lần này)."""
        due = wn.notes_to_show(__version__, self.settings.last_seen_version, self.settings.existed,
                               wn.load_notes())
        if not due:
            self._record()  # cài mới / đã xem / không có ghi chú: ghi để lần sau không hỏi lại
            return False
        self._due = due
        QTimer.singleShot(STARTUP_DELAY_MS, self._show_due)
        return True

    def _record(self) -> None:
        if self.settings.last_seen_version != __version__:
            self.settings.last_seen_version = __version__
            self.settings.save()

    def _show_due(self) -> None:
        if not self._due:
            return
        due, self._due = self._due, []
        try:
            self.dialog_factory(due, self.window).exec()
        finally:
            self._record()

    def show_current(self) -> None:
        notes = wn.load_notes()
        pick = wn.notes_for(__version__, notes) or (notes[0] if notes else None)
        if pick is None:
            return
        self.dialog_factory([pick], self.window).exec()
