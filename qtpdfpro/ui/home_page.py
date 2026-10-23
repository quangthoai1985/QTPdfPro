"""Trang chủ (Home) theo bố cục PdfCraft.

- Cột trái: bảng "Tất cả công cụ" (`ToolCatalogPanel`) có ô tìm nhanh, lọc theo nhóm chế độ.
- Nội dung chính theo thứ tự việc người dùng hay làm: lời chào gọn → «Bắt đầu» (thẻ «Mở tệp PDF» kéo thả cạnh thẻ
  văn bản hành chính NĐ30; xếp chồng khi hẹp) → «Gần đây» (tên tệp, đường dẫn, số trang, dung lượng, nút quay lại
  tài liệu đang mở) → lưới «Công cụ đề xuất» → chân trang (quyền riêng tư, GitHub, bản phát hành).
- Công cụ chưa phát triển hiển thị nhãn "Coming Soon".
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro import __app_name__, __github_repo__, __version__
from qtpdfpro.ui.tool_catalog import (
    CATEGORIES,
    CATEGORY_TITLES,
    COMING_SOON_LABEL,
    RECOMMENDED,
    ToolSpec,
    get_tool,
    tools_for,
)


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


class _ClickableFrame(QFrame):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


# ─── Bảng "Tất cả công cụ" ─────────────────────────────────────────────────


class _ElidedLabel(QLabel):
    """Nhãn một dòng tự rút gọn «…» khi hẹp: tên công cụ dài không đẩy nhãn «Soon» ra khỏi cột."""

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event) -> None:
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, rect.width())
        painter = QPainter(self)
        # drawItemText theo vai trò chữ của nhãn để vẫn ăn màu `color:` của QSS
        self.style().drawItemText(
            painter, rect, int(self.alignment()), self.palette(), self.isEnabled(), text, self.foregroundRole()
        )


class CatalogRow(_ClickableFrame):
    """Một dòng công cụ trong danh mục: biểu tượng + tên, nhãn «Coming Soon» canh phải."""

    def __init__(self, tool: ToolSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tool = tool
        self.setObjectName("catalogRow" if tool.ready else "catalogRowSoon")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 7, 8, 7)
        lay.setSpacing(8)
        icon = QLabel(tool.icon)
        icon.setFixedWidth(22)
        name = _ElidedLabel(tool.name)
        name.setObjectName("catalogRowName" if tool.ready else "catalogRowNameSoon")
        lay.addWidget(icon)
        lay.addWidget(name, 1)
        if not tool.ready:
            badge = QLabel("Soon")
            badge.setObjectName("soonBadgeSmall")
            lay.addWidget(badge)
        self.setToolTip(
            tool.summary if tool.ready else f"{COMING_SOON_LABEL} — dự kiến {tool.milestone}. {tool.summary}"
        )



class ToolCatalogPanel(QFrame):
    """Cột trái liệt kê toàn bộ công cụ, có ô tìm nhanh & lọc theo nhóm chế độ."""

    toolActivated = Signal(str)
    closeRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("catalogPanel")
        self.setMinimumWidth(250)
        self.setMaximumWidth(300)
        self._category = "all"
        self._buttons: dict[str, CatalogRow] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 8, 8)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self.title_lbl = QLabel("Tất cả công cụ")
        self.title_lbl.setObjectName("panelTitle")
        btn_close = QPushButton("✕")
        btn_close.setObjectName("ghostIconBtn")
        btn_close.setFixedSize(26, 26)
        btn_close.setToolTip("Thu gọn bảng công cụ (F3)")
        btn_close.clicked.connect(self.closeRequested.emit)
        head.addWidget(self.title_lbl, 1)
        head.addWidget(btn_close)
        lay.addLayout(head)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Tìm công cụ (gõ không dấu cũng được)…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        lay.addWidget(self.search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("catalogBody")
        self._body_lay = QVBoxLayout(body)
        self._body_lay.setContentsMargins(0, 0, 4, 0)
        self._body_lay.setSpacing(2)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        self.empty_lbl = QLabel("Không có công cụ nào khớp từ khoá.")
        self.empty_lbl.setObjectName("mutedLabel")
        self.empty_lbl.setWordWrap(True)
        self.refresh()

    def set_category(self, category: str) -> None:
        self._category = category
        title = dict(CATEGORIES).get(category, "Tất cả công cụ").replace("&&", "&")
        self.title_lbl.setText(title)
        self.refresh()

    def refresh(self) -> None:
        while self._body_lay.count():
            item = self._body_lay.takeAt(0)
            w = item.widget()
            if w is not None and w is not self.empty_lbl:
                w.deleteLater()
        self._buttons.clear()
        tools = tools_for(self._category, self.search.text())
        if not tools:
            self._body_lay.addWidget(self.empty_lbl)
            self.empty_lbl.show()
        else:
            self.empty_lbl.hide()
        current_cat = None
        for t in tools:
            if self._category == "all" and t.category != current_cat:
                current_cat = t.category
                hdr = QLabel(CATEGORY_TITLES.get(t.category, ""))
                hdr.setObjectName("catalogSection")
                self._body_lay.addWidget(hdr)
            row = CatalogRow(t)
            row.clicked.connect(lambda key=t.key: self.toolActivated.emit(key))
            self._body_lay.addWidget(row)
            self._buttons[t.key] = row
        self._body_lay.addStretch(1)

    def tool_keys(self) -> List[str]:
        return list(self._buttons.keys())


# ─── Thẻ công cụ đề xuất ───────────────────────────────────────────────────


class ToolCard(_ClickableFrame):
    def __init__(self, tool: ToolSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tool = tool
        self.setObjectName("toolCard" if tool.ready else "toolCardSoon")
        self.setMinimumSize(QSize(200, 128))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(6)

        head = QHBoxLayout()
        icon = QLabel(tool.icon)
        icon.setObjectName("toolCardIcon")
        name = QLabel(tool.name)
        name.setObjectName("toolCardName")
        name.setWordWrap(True)
        head.addWidget(icon)
        head.addWidget(name, 1)
        lay.addLayout(head)

        summary = QLabel(tool.summary)
        summary.setObjectName("toolCardSummary")
        summary.setWordWrap(True)
        lay.addWidget(summary, 1)

        foot = QLabel(tool.status_text if tool.ready else f"{COMING_SOON_LABEL} · {tool.milestone}")
        foot.setObjectName("toolCardAction" if tool.ready else "soonBadge")
        foot.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        lay.addWidget(foot, 0, Qt.AlignmentFlag.AlignLeft)
        self.setToolTip(tool.summary if tool.ready else f"Tính năng đang phát triển — dự kiến {tool.milestone}")


class OpenFileCard(_ClickableFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("openFileCard")
        self.setMinimumSize(QSize(200, 150))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(4)
        icon = QLabel("📂")
        icon.setObjectName("openFileIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Mở tệp PDF")
        title.setObjectName("openFileTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Kéo thả PDF vào đây hoặc bấm để chọn tệp  ·  Ctrl+O")
        hint.setObjectName("toolCardSummary")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addStretch(1)
        lay.addWidget(icon)
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
        icon = QLabel("📄")
        icon.setObjectName("recentIcon")
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
        lay.addWidget(icon)
        lay.addLayout(texts, 1)
        lay.addWidget(meta)
        self.setToolTip(str(path))


# ─── Trang chủ ─────────────────────────────────────────────────────────────


class HomePage(QWidget):
    """Màn hình chào mừng kiểu PdfCraft."""

    toolActivated = Signal(str)
    openRequested = Signal()
    recentActivated = Signal(str)
    resumeRequested = Signal()
    linkRequested = Signal(str)
    filesDropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._cards: list[QWidget] = []
        self._grid_cols = 0

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.catalog = ToolCatalogPanel(self)
        self.catalog.toolActivated.connect(self.toolActivated.emit)
        self.catalog.closeRequested.connect(lambda: self.catalog.setVisible(False))
        root.addWidget(self.catalog)

        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("homeContent")
        self._content_lay = QVBoxLayout(content)
        self._content_lay.setContentsMargins(40, 32, 40, 32)
        self._content_lay.setSpacing(22)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # 1. Lời chào (gọn: tên ứng dụng + nhãn phiên bản + một dòng giới thiệu)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel(f"Chào mừng đến với {__app_name__}")
        title.setObjectName("homeTitle")
        version_chip = QLabel(f"v{__version__}")
        version_chip.setObjectName("versionChip")
        title_row.addWidget(title)
        title_row.addWidget(version_chip, 0, Qt.AlignmentFlag.AlignBottom)
        title_row.addStretch(1)
        subtitle = QLabel("Bàn làm việc PDF mã nguồn mở — chạy cục bộ, riêng tư, tự động hoá được bằng dòng lệnh.")
        subtitle.setObjectName("homeSubtitle")
        subtitle.setWordWrap(True)
        self._content_lay.addLayout(title_row)
        self._content_lay.addWidget(subtitle)

        # 2. Bắt đầu nhanh: thẻ «Mở tệp» (kéo thả) cạnh thẻ nổi bật văn bản hành chính NĐ30
        self._start_grid = QGridLayout()
        self._start_grid.setHorizontalSpacing(16)
        self._start_grid.setVerticalSpacing(16)
        self.open_card = OpenFileCard()
        self.open_card.clicked.connect(self.openRequested.emit)
        self._start_cols = 0

        hero = QFrame()
        hero.setObjectName("homeHero")
        hero_lay = QVBoxLayout(hero)
        hero_lay.setContentsMargins(20, 16, 20, 16)
        hero_lay.setSpacing(10)
        hero_head = QHBoxLayout()
        hero_icon = QLabel("🏛️")
        hero_icon.setObjectName("heroIcon")
        hero_texts = QVBoxLayout()
        hero_texts.setSpacing(2)
        hero_title = QLabel("Văn bản hành chính chuẩn Nghị định 30/2020/NĐ-CP")
        hero_title.setObjectName("heroTitle")
        hero_title.setWordWrap(True)
        hero_desc = QLabel(
            "Đối chiếu thể thức và chuyển PDF sang Word giữ nguyên bố cục: Quốc hiệu – Tiêu ngữ, khối ký, "
            "đường kẻ đúng toạ độ, con dấu, chữ ký số."
        )
        hero_desc.setObjectName("heroDesc")
        hero_desc.setWordWrap(True)
        hero_texts.addWidget(hero_title)
        hero_texts.addWidget(hero_desc)
        hero_head.addWidget(hero_icon, 0, Qt.AlignmentFlag.AlignTop)
        hero_head.addLayout(hero_texts, 1)
        hero_lay.addLayout(hero_head)

        hero_btns = QHBoxLayout()
        hero_btns.setSpacing(8)
        self.btn_hero_convert = QPushButton("📄 Chuyển PDF sang Word chuẩn NĐ30")
        self.btn_hero_convert.setObjectName("primaryConvertBtn")
        self.btn_hero_convert.clicked.connect(lambda: self.toolActivated.emit("pdf_to_word_nd30"))
        self.btn_hero_check = QPushButton("✅ Kiểm tra thể thức")
        self.btn_hero_check.setObjectName("pillBtn")
        self.btn_hero_check.clicked.connect(lambda: self.toolActivated.emit("nd30_check"))
        for b in (self.btn_hero_convert, self.btn_hero_check):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            hero_btns.addWidget(b)
        hero_btns.addStretch(1)
        hero_lay.addLayout(hero_btns)
        self.hero = hero
        self._relayout_start(2)
        self._content_lay.addLayout(self._start_grid)

        # 3. Gần đây — việc người dùng làm nhiều nhất là mở lại tệp vừa dùng nên đặt ngay dưới «Bắt đầu»
        recent_head = QHBoxLayout()
        recent_title = QLabel("Gần đây")
        recent_title.setObjectName("sectionTitle")
        self.btn_resume = QPushButton("↩ Quay lại tài liệu đang mở")
        self.btn_resume.setObjectName("pillBtn")
        self.btn_resume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_resume.setVisible(False)
        self.btn_resume.clicked.connect(self.resumeRequested.emit)
        recent_head.addWidget(recent_title)
        recent_head.addStretch(1)
        recent_head.addWidget(self.btn_resume)
        self._content_lay.addLayout(recent_head)

        self.recent_box = QFrame()
        self.recent_box.setObjectName("recentBox")
        self._recent_lay = QVBoxLayout(self.recent_box)
        self._recent_lay.setContentsMargins(4, 4, 4, 4)
        self._recent_lay.setSpacing(2)
        self._content_lay.addWidget(self.recent_box)
        self.recent_rows: list[RecentRow] = []

        # 4. Công cụ đề xuất
        rec = QFrame()
        rec.setObjectName("sectionCard")
        rec_lay = QVBoxLayout(rec)
        rec_lay.setContentsMargins(20, 18, 20, 20)
        rec_lay.setSpacing(14)
        rec_title = QLabel("Công cụ đề xuất")
        rec_title.setObjectName("sectionTitle")
        rec_lay.addWidget(rec_title)
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(14)
        rec_lay.addLayout(self._grid)
        for key in RECOMMENDED:
            tool = get_tool(key)
            if tool is None:
                continue
            card = ToolCard(tool)
            card.clicked.connect(lambda key=key: self.toolActivated.emit(key))
            self._cards.append(card)
        self._relayout_cards(4)
        self._content_lay.addWidget(rec)
        self._content_lay.addStretch(1)

        # 5. Chân trang: quyền riêng tư một dòng + liên kết GitHub
        footer = QHBoxLayout()
        footer.setSpacing(6)
        priv = QLabel(
            f"🔒 {__app_name__} chạy hoàn toàn ngoại tuyến trên máy bạn: không thu thập dữ liệu, "
            "không cần tài khoản, không gửi tài liệu lên đám mây."
        )
        priv.setObjectName("privacyText")
        priv.setWordWrap(True)
        footer.addWidget(priv, 1)
        for text, url in (
            ("⟨/⟩ GitHub", f"https://github.com/{__github_repo__}"),
            ("↗ Bản phát hành", f"https://github.com/{__github_repo__}/releases"),
        ):
            link = QPushButton(text)
            link.setObjectName("ghostBtn")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(lambda _c=False, u=url: self.linkRequested.emit(u))
            footer.addWidget(link)
        self._content_lay.addLayout(footer)

    # ── Lưới thẻ đáp ứng theo chiều rộng ──
    def _relayout_start(self, cols: int) -> None:
        """Hàng «Bắt đầu»: 2 cột (Mở tệp | NĐ30) khi đủ rộng, xếp chồng khi hẹp."""
        cols = 1 if cols < 2 else 2
        if cols == self._start_cols:
            return
        self._start_cols = cols
        self._start_grid.removeWidget(self.open_card)
        self._start_grid.removeWidget(self.hero)
        if cols == 2:
            self._start_grid.addWidget(self.open_card, 0, 0)
            self._start_grid.addWidget(self.hero, 0, 1)
            self._start_grid.setColumnStretch(0, 4)
            self._start_grid.setColumnStretch(1, 6)
        else:
            self._start_grid.addWidget(self.open_card, 0, 0)
            self._start_grid.addWidget(self.hero, 1, 0)
            self._start_grid.setColumnStretch(0, 1)
            self._start_grid.setColumnStretch(1, 0)

    def _relayout_cards(self, cols: int) -> None:
        cols = max(1, cols)
        if cols == self._grid_cols:
            return
        self._grid_cols = cols
        for card in self._cards:
            self._grid.removeWidget(card)
        for i, card in enumerate(self._cards):
            self._grid.addWidget(card, i // cols, i % cols)
        for c in range(6):
            self._grid.setColumnStretch(c, 1 if c < cols else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - API Qt
        super().resizeEvent(event)
        avail = self.width() - (self.catalog.width() if self.catalog.isVisible() else 0) - 80
        self._relayout_cards(max(1, min(4, avail // 230)))
        self._relayout_start(2 if avail >= 760 else 1)

    # ── Danh sách gần đây ──
    def set_recent_files(self, paths: List[str], has_open_docs: bool = False) -> None:
        self.btn_resume.setVisible(has_open_docs)
        while self._recent_lay.count():
            item = self._recent_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.recent_rows = []
        existing = [Path(p) for p in paths if Path(p).exists()]
        if not existing:
            empty = QLabel("Chưa có tệp nào. Bấm «Mở tệp» hoặc kéo thả PDF vào cửa sổ để bắt đầu.")
            empty.setObjectName("mutedLabel")
            empty.setContentsMargins(12, 10, 12, 10)
            self._recent_lay.addWidget(empty)
            return
        for p in existing[:6]:
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
