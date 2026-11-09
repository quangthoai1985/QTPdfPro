"""Trang chủ (hiện khi chưa có tài liệu nào ở phía trước).

Thứ tự việc người dùng hay làm, nội dung căn giữa rộng tối đa 1100 px, không còn cột «Tất cả công cụ»:
lời chào + chip phiên bản → «Bắt đầu» (thẻ «Mở tệp PDF» + thẻ văn bản hành chính NĐ30; xếp chồng khi hẹp)
→ «Gần đây» (≤ 6 tệp) → «Công cụ nhanh» (8 ô, 4 cột — hẹp thì 2 cột) → một dòng về quyền riêng tư.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro import __app_name__, __version__
from qtpdfpro.ui import commands, icons

CONTENT_MAX_WIDTH = 1100
CONTENT_MARGIN = 40
WIDE_MIN_WIDTH = 760  # dưới mức này: «Bắt đầu» xếp chồng, ô công cụ 2 cột
RECENT_LIMIT = 6


def _human_size(n_bytes: int) -> str:
    if n_bytes >= 1024 * 1024:
        return f"{n_bytes / (1024 * 1024):.1f} MB".replace(".", ",")
    if n_bytes >= 1024:
        return f"{n_bytes / 1024:.0f} KB"
    return f"{n_bytes} B"


def pdf_page_count(path: Path) -> Optional[int]:
    """Đếm số trang PDF nhanh (không kết xuất); trả về None nếu không đọc được."""
    try:
        import fitz  # PyMuPDF

        with fitz.open(str(path)) as doc:
            return len(doc)
    except Exception:
        return None


def _icon_label(name: str, size: int, object_name: str = "homeIcon") -> QToolButton:
    """Biểu tượng tô lại theo giao diện (qua `icons.bind`); không nhận chuột để thẻ cha bắt cú nhấp."""
    btn = QToolButton()
    btn.setObjectName(object_name)
    btn.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    btn.setIconSize(QSize(size, size))
    icons.bind(btn, name, size)
    return btn


class _ClickableFrame(QFrame):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class OpenFileCard(_ClickableFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("openFileCard")
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(4)
        title = QLabel("Mở tệp PDF")
        title.setObjectName("openFileTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Kéo thả PDF vào đây hoặc bấm để chọn tệp  ·  Ctrl+O")
        hint.setObjectName("homeHint")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addStretch(1)
        lay.addWidget(_icon_label("folder-open", 32), 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addStretch(1)


class RecentRow(_ClickableFrame):
    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.setObjectName("recentRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        name = QLabel(path.name)
        name.setObjectName("recentName")
        folder = QLabel(str(path.parent))
        folder.setObjectName("recentPath")
        texts.addWidget(name)
        texts.addWidget(folder)
        meta_bits = []
        pages = pdf_page_count(path)
        if pages is not None:
            meta_bits.append(f"{pages} trang")
        try:
            meta_bits.append(_human_size(path.stat().st_size))
        except OSError:
            pass
        meta = QLabel("  ·  ".join(meta_bits))
        meta.setObjectName("recentMeta")
        lay.addWidget(_icon_label("file-text", 20))
        lay.addLayout(texts, 1)
        lay.addWidget(meta)
        self.setToolTip(str(path))


class HomePage(QWidget):
    """Màn hình chào mừng."""

    commandRequested = Signal(str)
    openRequested = Signal()
    recentActivated = Signal(str)
    resumeRequested = Signal()
    filesDropped = Signal(list)
    versionClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._tile_cols = 0
        self._start_cols = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll = scroll
        root.addWidget(scroll)

        content = QWidget()
        content.setObjectName("homeContent")
        outer = QHBoxLayout(content)
        outer.setContentsMargins(CONTENT_MARGIN, 32, CONTENT_MARGIN, 32)
        outer.addStretch(1)
        self.column = QWidget()
        self.column.setObjectName("homeColumn")
        self.column.setMaximumWidth(CONTENT_MAX_WIDTH)
        self.column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        outer.addWidget(self.column, 100)
        outer.addStretch(1)
        scroll.setWidget(content)
        col = QVBoxLayout(self.column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(22)

        # 1. Lời chào + chip phiên bản (bấm → «Có gì mới»)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel(f"Chào mừng đến với {__app_name__}")
        title.setObjectName("homeTitle")
        self.version_chip = QPushButton(f"v{__version__}")
        self.version_chip.setObjectName("versionChip")
        self.version_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.version_chip.setToolTip("Có gì mới ở phiên bản này")
        self.version_chip.clicked.connect(self.versionClicked.emit)
        title_row.addWidget(title)
        title_row.addWidget(self.version_chip, 0, Qt.AlignmentFlag.AlignBottom)
        title_row.addStretch(1)
        subtitle = QLabel("Bàn làm việc PDF mã nguồn mở — chạy cục bộ, riêng tư, tự động hoá được bằng dòng lệnh.")
        subtitle.setObjectName("homeSubtitle")
        subtitle.setWordWrap(True)
        col.addLayout(title_row)
        col.addWidget(subtitle)

        # 2. Bắt đầu: «Mở tệp PDF» + «Văn bản hành chính NĐ30»
        col.addWidget(self._section_title("Bắt đầu"))
        self._start_grid = QGridLayout()
        self._start_grid.setHorizontalSpacing(16)
        self._start_grid.setVerticalSpacing(16)
        self.open_card = OpenFileCard()
        self.open_card.clicked.connect(self.openRequested.emit)
        self.nd30_card = self._build_nd30_card()
        self._relayout_start(2)
        col.addLayout(self._start_grid)

        # 3. Gần đây
        recent_head = QHBoxLayout()
        recent_head.addWidget(self._section_title("Gần đây"))
        recent_head.addStretch(1)
        # Có tài liệu đang mở mà đang xem Trang chủ: lối quay lại (không trùng nút lệnh nào)
        self.btn_resume = QPushButton("Quay lại tài liệu đang mở")
        self.btn_resume.setObjectName("pillBtn")
        self.btn_resume.setCursor(Qt.CursorShape.PointingHandCursor)
        icons.bind(self.btn_resume, "undo-2", 16)
        self.btn_resume.setVisible(False)
        self.btn_resume.clicked.connect(self.resumeRequested.emit)
        recent_head.addWidget(self.btn_resume)
        col.addLayout(recent_head)
        self.recent_box = QFrame()
        self.recent_box.setObjectName("recentBox")
        self._recent_lay = QVBoxLayout(self.recent_box)
        self._recent_lay.setContentsMargins(4, 4, 4, 4)
        self._recent_lay.setSpacing(2)
        col.addWidget(self.recent_box)
        self.recent_rows: list[RecentRow] = []

        # 4. Công cụ nhanh
        col.addWidget(self._section_title("Công cụ nhanh"))
        self._tile_grid = QGridLayout()
        self._tile_grid.setHorizontalSpacing(12)
        self._tile_grid.setVerticalSpacing(12)
        self.quick_tiles: dict[str, QPushButton] = {}
        for key in commands.HOME_QUICK_TOOLS:
            cmd = commands.get(key)
            tile = QPushButton(cmd.label)  # nhãn đã nhân đôi `&&` cho Qt
            tile.setObjectName("quickTile")
            tile.setCursor(Qt.CursorShape.PointingHandCursor)
            tile.setToolTip(cmd.summary)
            tile.setMinimumHeight(52)
            tile.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            icons.bind(tile, cmd.icon, 20)
            tile.clicked.connect(lambda _c=False, k=key: self.commandRequested.emit(k))
            self.quick_tiles[key] = tile
        self._relayout_tiles(4)
        col.addLayout(self._tile_grid)
        col.addStretch(1)

        # 5. Chân trang
        self.privacy_lbl = QLabel(
            f"{__app_name__} chạy hoàn toàn ngoại tuyến trên máy bạn: không thu thập dữ liệu, "
            "không cần tài khoản, không gửi tài liệu lên đám mây."
        )
        self.privacy_lbl.setObjectName("privacyText")
        self.privacy_lbl.setWordWrap(True)
        col.addWidget(self.privacy_lbl)

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def _build_nd30_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("homeHero")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(12)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = QLabel("Văn bản hành chính chuẩn Nghị định 30/2020/NĐ-CP")
        title.setObjectName("heroTitle")
        title.setWordWrap(True)
        desc = QLabel(
            "Đối chiếu thể thức và chuyển PDF sang Word giữ nguyên bố cục: Quốc hiệu – Tiêu ngữ, khối ký, "
            "đường kẻ đúng toạ độ, con dấu, chữ ký số."
        )
        desc.setObjectName("heroDesc")
        desc.setWordWrap(True)
        texts.addWidget(title)
        texts.addWidget(desc)
        head.addWidget(_icon_label("landmark", 28), 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(texts, 1)
        lay.addLayout(head)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.btn_nd30_convert = QPushButton("Chuyển sang Word chuẩn NĐ30")
        self.btn_nd30_convert.setObjectName("primaryConvertBtn")
        self.btn_nd30_convert.clicked.connect(lambda: self.commandRequested.emit("convert_word_nd30"))
        self.btn_nd30_check = QPushButton("Kiểm tra thể thức")
        self.btn_nd30_check.setObjectName("pillBtn")
        icons.bind(self.btn_nd30_check, "badge-check", 16)
        self.btn_nd30_check.clicked.connect(lambda: self.commandRequested.emit("nd30_check"))
        for b in (self.btn_nd30_convert, self.btn_nd30_check):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)
        return card

    # ── Bố cục đáp ứng theo chiều rộng nội dung ──
    def _relayout_start(self, cols: int) -> None:
        """«Bắt đầu»: 2 cột (Mở tệp | NĐ30) khi đủ rộng, xếp chồng khi hẹp."""
        cols = 1 if cols < 2 else 2
        if cols == self._start_cols:
            return
        self._start_cols = cols
        self._start_grid.removeWidget(self.open_card)
        self._start_grid.removeWidget(self.nd30_card)
        if cols == 2:
            self._start_grid.addWidget(self.open_card, 0, 0)
            self._start_grid.addWidget(self.nd30_card, 0, 1)
            self._start_grid.setColumnStretch(0, 4)
            self._start_grid.setColumnStretch(1, 6)
        else:
            self._start_grid.addWidget(self.open_card, 0, 0)
            self._start_grid.addWidget(self.nd30_card, 1, 0)
            self._start_grid.setColumnStretch(0, 1)
            self._start_grid.setColumnStretch(1, 0)

    def _relayout_tiles(self, cols: int) -> None:
        cols = max(1, cols)
        if cols == self._tile_cols:
            return
        self._tile_cols = cols
        for tile in self.quick_tiles.values():
            self._tile_grid.removeWidget(tile)
        for i, tile in enumerate(self.quick_tiles.values()):
            self._tile_grid.addWidget(tile, i // cols, i % cols)
        for c in range(4):
            self._tile_grid.setColumnStretch(c, 1 if c < cols else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - API Qt
        super().resizeEvent(event)
        width = min(CONTENT_MAX_WIDTH, self.width() - 2 * CONTENT_MARGIN)
        wide = width >= WIDE_MIN_WIDTH
        self._relayout_tiles(4 if wide else 2)
        self._relayout_start(2 if wide else 1)

    # ── Danh sách gần đây ──
    def set_recent_files(self, paths: List[str], has_open_docs: bool = False) -> None:
        self.btn_resume.setVisible(has_open_docs)
        while self._recent_lay.count():
            item = self._recent_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()  # deleteLater chỉ chạy ở vòng lặp chính: ẩn ngay để không vẽ chồng lên hàng mới
                w.setParent(None)
                w.deleteLater()
        self.recent_rows = []
        existing = [Path(p) for p in paths if Path(p).exists()]
        if not existing:
            empty = QLabel("Chưa có tệp nào. Bấm «Mở tệp» hoặc kéo thả PDF vào cửa sổ để bắt đầu.")
            empty.setObjectName("mutedLabel")
            empty.setContentsMargins(12, 10, 12, 10)
            self._recent_lay.addWidget(empty)
            return
        for p in existing[:RECENT_LIMIT]:
            row = RecentRow(p)
            row.clicked.connect(lambda path=str(p): self.recentActivated.emit(path))
            self._recent_lay.addWidget(row)
            self.recent_rows.append(row)

    # ── Kéo thả ──
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - API Qt
        if event.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(".pdf") for u in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - API Qt
        files = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile().lower().endswith(".pdf")]
        if files:
            self.filesDropped.emit(files)
        event.acceptProposedAction()
