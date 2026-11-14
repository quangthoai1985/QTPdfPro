"""Thanh sidebar «Chỉnh sửa» bên trái (lấy cảm hứng từ PdfCraft Edit panel).

Hiển thị khi thẻ «Chỉnh sửa» đang mở; cho phép thao tác nhanh trên trang hiện tại (Xoay trái/phải,
Lật ngang, Lật dọc, Chèn/Nhân bản/Xoá trang, Cắt lề trang), Thêm nội dung (Văn bản, Chèn ảnh,
Đầu trang & Chân trang, Đóng dấu nước, Liên kết, Đánh số Bates, Nền trang, Đính kèm tệp) và
Tuỳ chọn khác (Ghép tệp PDF, Che thông tin nhạy cảm, Nén PDF, Điền & Ký biểu mẫu).
"""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.ui import icons


class EditSidebar(QFrame):
    """Bảng công cụ «Chỉnh sửa» bên trái khung đọc PDF."""

    actionTriggered = Signal(str)
    closeRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("editSidebar")
        self.setFixedWidth(212)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self.quick_buttons: Dict[str, QToolButton] = {}
        self.tool_buttons: Dict[str, QAbstractButton] = {}  # type: ignore[name-defined]
        self.action_buttons: Dict[str, QPushButton] = {}
        self._tool_checkables: Dict[str, list] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─── Tiêu đề ───
        header = QFrame()
        header.setObjectName("editSidebarHeader")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(12, 8, 8, 8)
        hlay.setSpacing(6)
        title = QLabel("Chỉnh sửa")
        title.setObjectName("editSidebarTitle")
        self.btn_close = QToolButton()
        self.btn_close.setObjectName("editSidebarCloseBtn")
        self.btn_close.setToolTip("Đóng bảng Chỉnh sửa")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setIconSize(QSize(15, 15))
        icons.bind(self.btn_close, "x", 15)
        self.btn_close.clicked.connect(self.closeRequested)
        hlay.addWidget(title, 1)
        hlay.addWidget(self.btn_close)
        root.addWidget(header)

        # ─── Vùng cuộn chứa 3 nhóm công cụ ───
        scroll = QScrollArea()
        scroll.setObjectName("editSidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(120)

        body = QWidget()
        body.setObjectName("editSidebarBody")
        blay = QVBoxLayout(body)
        blay.setContentsMargins(10, 8, 10, 12)
        blay.setSpacing(4)

        # ── 1. CHỈNH SỬA TRANG ──
        blay.addWidget(self._section_label("CHỈNH SỬA TRANG"))

        quick_grid = QGridLayout()
        quick_grid.setContentsMargins(0, 2, 0, 4)
        quick_grid.setSpacing(4)
        # Hàng 1: Xoay trái, Xoay phải, Lật ngang, Lật dọc
        self.btn_rotate_left = self._quick_btn(
            "page_rotate_left", "rotate-ccw", "Xoay trái 90° trang hiện tại"
        )
        self.btn_rotate_right = self._quick_btn(
            "page_rotate_right", "rotate-cw", "Xoay phải 90° trang hiện tại"
        )
        self.btn_flip_h = self._quick_btn(
            "flip_horizontal", "flip-horizontal-2", "Lật ngang trang hiện tại (Flip Horizontal)"
        )
        self.btn_flip_v = self._quick_btn(
            "flip_vertical", "flip-vertical-2", "Lật dọc trang hiện tại (Flip Vertical)"
        )
        # Hàng 2: Chèn/nhân bản trang, Xoá trang, Trích trang, Cắt khung
        self.btn_insert_page = self._quick_btn(
            "", "file-plus-2", "Chèn trang trắng / Nhân bản trang hiện tại"
        )
        insert_menu = QMenu(self.btn_insert_page)
        insert_menu.addAction("Chèn trang trắng sau trang này", lambda: self.actionTriggered.emit("page_insert_blank"))
        insert_menu.addAction("Nhân bản trang hiện tại", lambda: self.actionTriggered.emit("page_duplicate"))
        insert_menu.addAction("Tổ chức && chèn từ tệp PDF khác…", lambda: self.actionTriggered.emit("organize"))
        self.btn_insert_page.setMenu(insert_menu)
        self.btn_insert_page.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.quick_buttons["page_insert"] = self.btn_insert_page

        self.btn_delete_page = self._quick_btn(
            "page_delete", "trash-2", "Xoá trang hiện tại"
        )
        self.btn_extract_page = self._quick_btn(
            "extract_pages", "file-output", "Trích trang ra tệp PDF mới…"
        )
        self.btn_crop_quick = self._quick_btn(
            "tool:crop", "crop", "Kéo khung cắt trang (Crop)", checkable_tool="crop"
        )

        quick_grid.addWidget(self.btn_rotate_left, 0, 0)
        quick_grid.addWidget(self.btn_rotate_right, 0, 1)
        quick_grid.addWidget(self.btn_flip_h, 0, 2)
        quick_grid.addWidget(self.btn_flip_v, 0, 3)
        quick_grid.addWidget(self.btn_insert_page, 1, 0)
        quick_grid.addWidget(self.btn_delete_page, 1, 1)
        quick_grid.addWidget(self.btn_extract_page, 1, 2)
        quick_grid.addWidget(self.btn_crop_quick, 1, 3)
        blay.addLayout(quick_grid)

        self.btn_organize = self._list_btn("organize", "layout-grid", "Sắp xếp && ghép trang")
        self.btn_crop_dialog = self._list_btn("crop_margins", "crop", "Cắt lề trang…")
        blay.addWidget(self.btn_organize)
        blay.addWidget(self.btn_crop_dialog)

        blay.addWidget(self._divider())

        # ── 2. THÊM NỘI DUNG ──
        blay.addWidget(self._section_label("THÊM NỘI DUNG"))

        self.btn_text = self._list_btn("tool:text", "type", "Văn bản (Hộp chữ)", checkable_tool="text")
        self.btn_image = self._list_btn("tool:image", "image-plus", "Chèn ảnh", checkable_tool="image")
        self.btn_header_footer = self._menu_btn(
            "header_footer_menu",
            "heading",
            "Đầu && Chân trang",
            [
                ("Thêm đầu trang && chân trang…", "header_footer"),
                ("Đánh số trang…", "page_numbers"),
            ],
        )
        self.btn_watermark = self._menu_btn(
            "watermark_menu",
            "droplet",
            "Đóng dấu nước",
            [
                ("Đóng dấu nước trực tiếp vào tài liệu…", "watermark_inplace"),
                ("Xuất bản đóng dấu nước mới…", "watermark"),
            ],
        )
        self.btn_link = self._list_btn("tool:link", "link-2", "Liên kết", checkable_tool="link")

        blay.addWidget(self.btn_text)
        blay.addWidget(self.btn_image)
        blay.addWidget(self.btn_header_footer)
        blay.addWidget(self.btn_watermark)
        blay.addWidget(self.btn_link)

        # Mở rộng / Thu gọn (Bates, Nền trang, Đính kèm tệp)
        self.more_container = QWidget()
        mlay = QVBoxLayout(self.more_container)
        mlay.setContentsMargins(0, 0, 0, 0)
        mlay.setSpacing(2)
        self.btn_bates = self._list_btn("bates_numbering", "hash", "Đánh số Bates…")
        self.btn_background = self._list_btn("page_background", "palette", "Nền trang…")
        self.btn_attach = self._list_btn("attach_file", "paperclip", "Đính kèm tệp…")
        mlay.addWidget(self.btn_bates)
        mlay.addWidget(self.btn_background)
        mlay.addWidget(self.btn_attach)
        self.more_container.setVisible(False)
        blay.addWidget(self.more_container)

        self.btn_more_toggle = QPushButton("Mở rộng ▾")
        self.btn_more_toggle.setObjectName("editMoreToggleBtn")
        self.btn_more_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_more_toggle.clicked.connect(self._toggle_more)
        blay.addWidget(self.btn_more_toggle)

        blay.addWidget(self._divider())

        # ── 3. TUỲ CHỌN KHÁC ──
        blay.addWidget(self._section_label("TUỲ CHỌN KHÁC"))

        self.btn_combine = self._list_btn("combine", "combine", "Ghép tệp PDF")
        self.btn_redact = self._menu_btn(
            "redact_menu",
            "eye-off",
            "Che thông tin nhạy cảm",
            [
                ("Kéo khung đánh dấu che trên trang", "tool:redact"),
                ("Tìm chữ && đánh dấu che hàng loạt…", "redact_search"),
                ("Áp dụng xoá vĩnh viễn vùng đã che", "redact_apply"),
                ("Làm sạch siêu dữ liệu && thông tin ẩn", "sanitize_doc"),
            ],
            checkable_tool="redact",
        )
        self.btn_compress = self._list_btn("compress", "file-archive", "Nén && tối ưu PDF")
        self.btn_prepare_form = self._list_btn("fill_mode", "signature", "Điền && Ký biểu mẫu")

        blay.addWidget(self.btn_combine)
        blay.addWidget(self.btn_redact)
        blay.addWidget(self.btn_compress)
        blay.addWidget(self.btn_prepare_form)
        blay.addStretch(1)

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    # ─── Tiện ích dựng nút ────────────────────────────────────────────────

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("editSectionLabel")
        return lbl

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setObjectName("editSidebarSep")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        return line

    def _quick_btn(
        self,
        action_key: str,
        icon_name: str,
        tooltip: str,
        *,
        checkable_tool: str = "",
    ) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("editQuickBtn")
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(42, 32)
        btn.setIconSize(QSize(16, 16))
        icons.bind(btn, icon_name, 16)
        if checkable_tool:
            btn.setCheckable(True)
            self._tool_checkables.setdefault(checkable_tool, []).append(btn)
        if action_key:
            btn.clicked.connect(lambda _c=False, k=action_key: self.actionTriggered.emit(k))
            self.quick_buttons[action_key] = btn
        return btn

    def _list_btn(
        self,
        action_key: str,
        icon_name: str,
        text: str,
        *,
        checkable_tool: str = "",
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("editListBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIconSize(QSize(16, 16))
        icons.bind(btn, icon_name, 16)
        if checkable_tool:
            btn.setCheckable(True)
            self._tool_checkables.setdefault(checkable_tool, []).append(btn)
        btn.clicked.connect(lambda _c=False, k=action_key: self.actionTriggered.emit(k))
        self.action_buttons[action_key] = btn
        return btn

    def _menu_btn(
        self,
        key: str,
        icon_name: str,
        text: str,
        items: list[tuple[str, str]],
        *,
        checkable_tool: str = "",
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("editListBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIconSize(QSize(16, 16))
        icons.bind(btn, icon_name, 16)
        if checkable_tool:
            btn.setCheckable(True)
            self._tool_checkables.setdefault(checkable_tool, []).append(btn)
        menu = QMenu(btn)
        for label, act_key in items:
            menu.addAction(label, lambda k=act_key: self.actionTriggered.emit(k))
        btn.setMenu(menu)
        self.action_buttons[key] = btn
        return btn

    def _toggle_more(self) -> None:
        show = not self.more_container.isVisible()
        self.more_container.setVisible(show)
        self.btn_more_toggle.setText("Thu gọn ▴" if show else "Mở rộng ▾")

    def set_expanded_more(self, expanded: bool) -> None:
        self.more_container.setVisible(bool(expanded))
        self.btn_more_toggle.setText("Thu gọn ▴" if expanded else "Mở rộng ▾")

    def sync_checked_tool(self, tool: Optional[str]) -> None:
        """Đánh dấu nút công cụ tương tác đang chọn (`text`, `image`, `link`, `crop`, `redact`)."""
        for tkey, btns in self._tool_checkables.items():
            active = tool == tkey
            for btn in btns:
                btn.blockSignals(True)
                btn.setChecked(active)
                btn.blockSignals(False)
