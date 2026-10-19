"""Cửa sổ chính và Tab đọc tài liệu PDF của QT PDF Pro (bố cục lấy cảm hứng từ PdfCraft)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import (
    QAction,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QImage,
    QKeySequence,
    QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro import __app_name__, __version__
from qtpdfpro.core.reader import PDFDocumentReader, SearchHit
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.ui.convert_dialog import ConvertToDocxDialog
from qtpdfpro.ui.dialogs import AboutDialog, DocumentInfoDialog, PageTextDialog
from qtpdfpro.ui.pdf_canvas import PDFScrollViewer
from qtpdfpro.ui.theme import get_stylesheet


class PDFDocumentTab(QWidget):
    """Một tab tài liệu PDF hoàn chỉnh theo bố cục 3 cột kiểu PdfCraft:
    - Cột trái: Bảng 'Tất cả công cụ' (All Tools) có ô lọc nhanh & thẻ thao tác 1 chạm
    - Cột giữa: Thanh thông báo chữ ký số/con dấu + Khung vẽ PDF tốc độ cao (PDFScrollViewer)
    - Cột phải: Ngăn thông tin 4 tab (Trang, Mục lục, Tìm kiếm, Soi bố cục) + Thanh điều khiển dọc (Right Rail)
    """

    def __init__(
        self,
        reader: PDFDocumentReader,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.reader = reader
        self.settings = settings
        self._search_hits: List[SearchHit] = []
        self._tool_buttons: List[tuple[str, QPushButton]] = []

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root_layout.addWidget(self.splitter, 1)

        # ─── 1. CỘT TRÁI: Bảng "Tất cả công cụ" kiểu PdfCraft ────────────────
        self.tools_panel = self._build_left_tools_panel()

        # ─── 2. CỘT GIỮA: Banner thông tin chữ ký/con dấu + Khung xem PDF ────
        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.signature_banner = QFrame()
        self.signature_banner.setObjectName("signatureBanner")
        banner_layout = QHBoxLayout(self.signature_banner)
        banner_layout.setContentsMargins(12, 6, 12, 6)
        banner_layout.setSpacing(10)

        self.banner_info_lbl = QLabel()
        self.banner_info_lbl.setWordWrap(True)
        self.banner_convert_btn = QPushButton("⚡ Xuất Word chuẩn 1:1 ngay")
        self.banner_convert_btn.setObjectName("primaryConvertBtn")
        banner_layout.addWidget(self.banner_info_lbl, 1)
        banner_layout.addWidget(self.banner_convert_btn)
        center_layout.addWidget(self.signature_banner)

        self.viewer = PDFScrollViewer(self.reader, self)
        self.viewer.set_canvas_theme(self.settings.theme)
        self.viewer.set_continuous_mode(self.settings.continuous_scroll)
        self.viewer.set_show_layout_overlay(self.settings.show_layout_overlay)
        self.viewer.set_zoom_mode(
            self.settings.default_zoom_mode, self.settings.default_zoom_percent
        )
        center_layout.addWidget(self.viewer, 1)

        # ─── 3. CỘT PHẢI: Ngăn 4 tab (Trang, Mục lục, Tìm kiếm, Soi bố cục) ──
        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setMinimumWidth(240)
        self.sidebar_tabs.setMaximumWidth(390)

        # Ngăn 1: Trang thu nhỏ (Thumbnails)
        self.thumb_list = QListWidget()
        self.thumb_list.setIconSize(QSize(96, 132))
        self.thumb_list.setSpacing(6)
        self.thumb_list.currentRowChanged.connect(self._on_thumb_selected)
        self.sidebar_tabs.addTab(self.thumb_list, "Trang")

        # Ngăn 2: Mục lục (Bookmarks / TOC)
        self.toc_tree = QTreeWidget()
        self.toc_tree.setHeaderHidden(True)
        self.toc_tree.itemClicked.connect(self._on_toc_clicked)
        self.sidebar_tabs.addTab(self.toc_tree, "Mục lục")

        # Ngăn 3: Tìm kiếm toàn văn
        search_panel = QWidget()
        search_layout = QVBoxLayout(search_panel)
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Nhập từ khoá cần tìm...")
        self.search_input.returnPressed.connect(self.run_search)
        self.search_btn = QPushButton("Tìm")
        self.search_btn.clicked.connect(self.run_search)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_btn)

        self.search_count_lbl = QLabel("Nhập từ khoá và bấm Enter để tìm.")
        self.search_results_list = QListWidget()
        self.search_results_list.currentRowChanged.connect(self._on_search_hit_selected)

        search_layout.addLayout(search_row)
        search_layout.addWidget(self.search_count_lbl)
        search_layout.addWidget(self.search_results_list, 1)
        self.sidebar_tabs.addTab(search_panel, "Tìm kiếm")

        # Ngăn 4: Soi bố cục (Layout Inspector)
        inspector_panel = QWidget()
        insp_layout = QVBoxLayout(inspector_panel)
        self.chk_overlay = QCheckBox("Hiển thị khung bố cục && chữ ký trên PDF")
        self.chk_overlay.setChecked(self.settings.show_layout_overlay)
        self.chk_overlay.toggled.connect(self._on_overlay_toggled)

        self.layout_info_lbl = QLabel()
        self.layout_info_lbl.setWordWrap(True)
        self.layout_info_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)

        legend_lbl = QLabel(
            "<b>Chú giải màu khung nhận diện:</b><br/>"
            "• <span style='color:#2563EB;'>■ Xanh dương</span>: Khối văn bản &amp; phông chữ<br/>"
            "• <span style='color:#16A34A;'>■ Xanh lá</span>: Bảng biểu (hàng × cột)<br/>"
            "• <span style='color:#EA580C;'>■ Cam</span>: Hình ảnh nhúng<br/>"
            "• <span style='color:#E11D48;'>■ Đỏ hồng</span>: Chữ ký số / Con dấu hành chính<br/>"
            "• <span style='color:#9333EA;'>■ Tím</span>: Đường kẻ / Khung vector"
        )
        legend_lbl.setWordWrap(True)

        self.extract_page_text_btn = QPushButton("Xem / Sao chép văn bản trang này")
        self.sidebar_convert_btn = QPushButton("Chuyển sang Word (.docx)...")
        self.sidebar_convert_btn.setObjectName("primaryConvertBtn")

        insp_layout.addWidget(self.chk_overlay)
        insp_layout.addWidget(legend_lbl)
        insp_layout.addWidget(self.layout_info_lbl, 1)
        insp_layout.addWidget(self.extract_page_text_btn)
        insp_layout.addWidget(self.sidebar_convert_btn)
        self.sidebar_tabs.addTab(inspector_panel, "Soi bố cục")

        # Ghép 3 cột vào Splitter
        self.splitter.addWidget(self.tools_panel)
        self.splitter.addWidget(center_container)
        self.splitter.addWidget(self.sidebar_tabs)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([235, 820, 265])

        # ─── 4. THANH ĐIỀU KHIỂN DỌC BÊN PHẢI (PdfCraft Vertical Rail) ──────
        self.right_rail = self._build_right_rail()
        root_layout.addWidget(self.right_rail)

        self._populate_thumbnails()
        self._populate_toc()
        self._update_document_banner()
        self.viewer.pageChanged.connect(self._on_viewer_page_changed)
        self.viewer.zoomChanged.connect(self._on_viewer_zoom_changed)
        self.sidebar_tabs.currentChanged.connect(self._sync_rail_buttons)
        self._update_inspector(0)
        self._sync_rail_status()
        self._sync_rail_buttons()

    def _build_left_tools_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("leftToolsPanel")
        panel.setMinimumWidth(245)
        panel.setMaximumWidth(295)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        title_lbl = QLabel("<b>🛠️ Tất cả công cụ</b>")
        btn_hide_tools = QPushButton("✕")
        btn_hide_tools.setFixedSize(26, 26)
        btn_hide_tools.setToolTip("Thu gọn bảng công cụ bên trái")
        btn_hide_tools.clicked.connect(lambda: panel.setVisible(False))
        header_row.addWidget(title_lbl, 1)
        header_row.addWidget(btn_hide_tools)
        layout.addLayout(header_row)

        self.tool_filter_input = QLineEdit()
        self.tool_filter_input.setPlaceholderText("🔍 Tìm nhanh công cụ...")
        self.tool_filter_input.textChanged.connect(self._filter_left_tools)
        layout.addWidget(self.tool_filter_input)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tools_body = QWidget()
        body_layout = QVBoxLayout(tools_body)
        body_layout.setContentsMargins(0, 4, 4, 4)
        body_layout.setSpacing(6)

        lbl_conv = QLabel("<span style='font-size:11px;font-weight:700;color:#64748B;'>CHUYỂN ĐỔI SANG WORD</span>")
        body_layout.addWidget(lbl_conv)

        self.tool_btn_convert_hybrid = self._make_tool_card(
            "📝 Xuất Word — Chuẩn hành chính\nGiữ con dấu, chữ ký, bảng && dòng chảy",
            primary=True,
        )
        self.tool_btn_convert_exact = self._make_tool_card(
            "📐 Xuất Word — Giữ vị trí 1:1\nĐặt khung văn bản theo toạ độ tuyệt đối"
        )
        self.tool_btn_convert_dialog = self._make_tool_card(
            "⚙️ Tuỳ chỉnh xuất DOCX nâng cao...\nChọn trang, DPI ảnh && chế độ hậu xử lý"
        )
        body_layout.addWidget(self.tool_btn_convert_hybrid)
        body_layout.addWidget(self.tool_btn_convert_exact)
        body_layout.addWidget(self.tool_btn_convert_dialog)

        lbl_inspect = QLabel("<span style='font-size:11px;font-weight:700;color:#64748B;'>SOI BỐ CỤC &amp; VĂN BẢN</span>")
        body_layout.addWidget(lbl_inspect)

        self.tool_btn_overlay = self._make_tool_card(
            "🔍 Bật/Tắt khung soi bố cục (F8)\nNhận diện Văn bản, Bảng, Con dấu, Vector"
        )
        self.tool_btn_extract_text = self._make_tool_card(
            "📋 Trích xuất văn bản trang này\nXem && sao chép nhanh nội dung Unicode"
        )
        self.tool_btn_search = self._make_tool_card(
            "🔎 Tìm kiếm toàn văn (Ctrl+F)\nTô sáng trực tiếp mọi vị trí khớp trên PDF"
        )
        body_layout.addWidget(self.tool_btn_overlay)
        body_layout.addWidget(self.tool_btn_extract_text)
        body_layout.addWidget(self.tool_btn_search)

        lbl_page = QLabel("<span style='font-size:11px;font-weight:700;color:#64748B;'>THAO TÁC TRANG &amp; TÀI LIỆU</span>")
        body_layout.addWidget(lbl_page)

        self.tool_btn_rot_left = self._make_tool_card("↺ Xoay trang sang trái 90°")
        self.tool_btn_rot_right = self._make_tool_card("↻ Xoay trang sang phải 90°")
        self.tool_btn_fit_width = self._make_tool_card("↔ Phóng vừa khít chiều ngang")
        self.tool_btn_fit_page = self._make_tool_card("📄 Thu phóng vừa trọn trang")
        self.tool_btn_doc_info = self._make_tool_card("ℹ️ Thông tin && Metadata tài liệu")

        self.tool_btn_rot_left.clicked.connect(lambda: self.viewer.rotate_current_page(-90))
        self.tool_btn_rot_right.clicked.connect(lambda: self.viewer.rotate_current_page(90))
        self.tool_btn_fit_width.clicked.connect(lambda: self.viewer.set_zoom_mode("fit_width"))
        self.tool_btn_fit_page.clicked.connect(lambda: self.viewer.set_zoom_mode("fit_page"))
        self.tool_btn_search.clicked.connect(self.focus_search)
        self.tool_btn_overlay.clicked.connect(
            lambda: self.chk_overlay.setChecked(not self.chk_overlay.isChecked())
        )

        body_layout.addWidget(self.tool_btn_rot_left)
        body_layout.addWidget(self.tool_btn_rot_right)
        body_layout.addWidget(self.tool_btn_fit_width)
        body_layout.addWidget(self.tool_btn_fit_page)
        body_layout.addWidget(self.tool_btn_doc_info)
        body_layout.addStretch(1)

        scroll.setWidget(tools_body)
        layout.addWidget(scroll, 1)
        return panel

    def _make_tool_card(self, text: str, primary: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("toolCardPrimaryBtn" if primary else "toolCardBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tool_buttons.append((text.lower(), btn))
        return btn

    def _filter_left_tools(self, query: str) -> None:
        q = query.strip().lower()
        for label_text, btn in self._tool_buttons:
            btn.setVisible(not q or q in label_text)

    def _build_right_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("rightRail")
        rail.setFixedWidth(56)

        rlayout = QVBoxLayout(rail)
        rlayout.setContentsMargins(4, 8, 4, 8)
        rlayout.setSpacing(6)

        # Nhóm nút đóng/mở các ngăn bên phải (Trang, Mục lục, Tìm kiếm, Soi bố cục)
        self.rail_tab_btns: List[QPushButton] = []
        tab_specs = [
            ("📄\nTrang", 0, "Hiện/Ẩn danh sách trang thu nhỏ"),
            ("📑\nMục lục", 1, "Hiện/Ẩn mục lục tài liệu (Bookmarks)"),
            ("🔍\nTìm", 2, "Hiện/Ẩn bảng tìm kiếm văn bản"),
            ("📐\nBố cục", 3, "Hiện/Ẩn bảng phân tích bố cục & chữ ký"),
        ]
        for label, tab_idx, tip in tab_specs:
            btn = QPushButton(label)
            btn.setObjectName("railIconBtn")
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _chk=False, idx=tab_idx: self._on_rail_tab_clicked(idx))
            rlayout.addWidget(btn)
            self.rail_tab_btns.append(btn)

        rlayout.addStretch(1)

        # Cụm điều khiển Trang & Thu phóng dọc kiểu PdfCraft ở góc phải dưới
        btn_prev = QPushButton("▲")
        btn_prev.setObjectName("railIconBtn")
        btn_prev.setToolTip("Trang trước")
        btn_prev.clicked.connect(
            lambda: self.viewer.go_to_page(max(0, self.viewer.current_page - 1))
        )

        self.lbl_rail_page = QLabel("1/1")
        self.lbl_rail_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_rail_page.setStyleSheet("font-size:11px;font-weight:700;")

        btn_next = QPushButton("▼")
        btn_next.setObjectName("railIconBtn")
        btn_next.setToolTip("Trang sau")
        btn_next.clicked.connect(
            lambda: self.viewer.go_to_page(
                min(self.reader.page_count - 1, self.viewer.current_page + 1)
            )
        )

        btn_zin = QPushButton("＋")
        btn_zin.setObjectName("railIconBtn")
        btn_zin.setToolTip("Phóng to (Ctrl++)")
        btn_zin.clicked.connect(lambda: self.viewer.zoom_in(20))

        self.lbl_rail_zoom = QLabel("100%")
        self.lbl_rail_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_rail_zoom.setStyleSheet("font-size:11px;font-weight:600;")

        btn_zout = QPushButton("－")
        btn_zout.setObjectName("railIconBtn")
        btn_zout.setToolTip("Thu nhỏ (Ctrl+-)")
        btn_zout.clicked.connect(lambda: self.viewer.zoom_out(20))

        btn_fitw = QPushButton("↔")
        btn_fitw.setObjectName("railIconBtn")
        btn_fitw.setToolTip("Vừa khít chiều ngang (Ctrl+1)")
        btn_fitw.clicked.connect(lambda: self.viewer.set_zoom_mode("fit_width"))

        btn_rot = QPushButton("↻")
        btn_rot.setObjectName("railIconBtn")
        btn_rot.setToolTip("Xoay trang 90°")
        btn_rot.clicked.connect(lambda: self.viewer.rotate_current_page(90))

        for w in (
            btn_prev,
            self.lbl_rail_page,
            btn_next,
            btn_zin,
            self.lbl_rail_zoom,
            btn_zout,
            btn_fitw,
            btn_rot,
        ):
            rlayout.addWidget(w)

        return rail

    def _on_rail_tab_clicked(self, tab_idx: int) -> None:
        if self.sidebar_tabs.isVisible() and self.sidebar_tabs.currentIndex() == tab_idx:
            self.sidebar_tabs.setVisible(False)
        else:
            self.sidebar_tabs.setVisible(True)
            self.sidebar_tabs.setCurrentIndex(tab_idx)
        self._sync_rail_buttons()

    def _sync_rail_buttons(self) -> None:
        vis = self.sidebar_tabs.isVisible()
        cur_idx = self.sidebar_tabs.currentIndex()
        for idx, btn in enumerate(self.rail_tab_btns):
            btn.blockSignals(True)
            btn.setChecked(vis and idx == cur_idx)
            btn.blockSignals(False)

    def _sync_rail_status(self) -> None:
        total = max(1, self.reader.page_count)
        cur = self.viewer.current_page + 1
        self.lbl_rail_page.setText(f"{cur}/{total}")
        self.lbl_rail_zoom.setText(f"{self.viewer.zoom_percent}%")

    def _update_document_banner(self) -> None:
        total_sigs = 0
        total_tables = 0
        for pno in range(self.reader.page_count):
            ly = self.reader.get_page_layout(pno)
            total_sigs += ly.signature_count
            total_tables += ly.table_count

        if total_sigs > 0:
            self.banner_info_lbl.setText(
                f"🛡️ <b>Văn bản hành chính có {total_sigs} chữ ký số / con dấu</b> — "
                "QT PDF Pro tự động trích xuất con dấu đỏ trong suốt, chữ ký nháy &amp; số hiệu đóng dấu đè để giữ nguyên 100% khi sang Word."
            )
            self.signature_banner.setVisible(True)
        elif total_tables > 0:
            self.banner_info_lbl.setText(
                f"📊 <b>Phát hiện {total_tables} bảng biểu cấu trúc trong tài liệu</b> — "
                "Sẵn sàng chuyển sang Word (.docx) giữ nguyên đường kẻ bảng và định dạng phông chữ."
            )
            self.signature_banner.setVisible(True)
        else:
            self.signature_banner.setVisible(False)

    def close_document(self) -> None:
        self.reader.close()

    def _populate_thumbnails(self) -> None:
        self.thumb_list.blockSignals(True)
        self.thumb_list.clear()
        for idx in range(self.reader.page_count):
            item = QListWidgetItem(f"Trang {idx + 1}")
            if idx < 60:
                buf = self.reader.render_page(idx, scale=0.18)
                qimg = QImage(
                    buf.rgb_bytes,
                    buf.width,
                    buf.height,
                    buf.stride,
                    QImage.Format.Format_RGB888,
                ).copy()
                item.setIcon(QIcon(QPixmap.fromImage(qimg)))
            self.thumb_list.addItem(item)
        if self.reader.page_count > 0:
            self.thumb_list.setCurrentRow(0)
        self.thumb_list.blockSignals(False)

    def _populate_toc(self) -> None:
        self.toc_tree.clear()
        nodes = self.reader.get_bookmarks()
        if not nodes:
            empty = QTreeWidgetItem(["(Tài liệu không có mục lục)"])
            empty.setData(0, Qt.ItemDataRole.UserRole, -1)
            self.toc_tree.addTopLevelItem(empty)
            return

        stack: List[tuple[int, QTreeWidgetItem]] = []
        for node in nodes:
            tree_item = QTreeWidgetItem([f"{node.title}  (Tr. {node.page_index + 1})"])
            tree_item.setData(0, Qt.ItemDataRole.UserRole, node.page_index)
            while stack and stack[-1][0] >= node.level:
                stack.pop()
            if not stack:
                self.toc_tree.addTopLevelItem(tree_item)
            else:
                stack[-1][1].addChild(tree_item)
            stack.append((node.level, tree_item))
        self.toc_tree.expandToDepth(1)

    def _on_thumb_selected(self, row: int) -> None:
        if 0 <= row < self.reader.page_count and row != self.viewer.current_page:
            self.viewer.go_to_page(row)

    def _on_toc_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        page_idx = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(page_idx, int) and 0 <= page_idx < self.reader.page_count:
            self.viewer.go_to_page(page_idx)

    def _on_viewer_page_changed(self, page_idx: int) -> None:
        self.thumb_list.blockSignals(True)
        self.thumb_list.setCurrentRow(page_idx)
        self.thumb_list.blockSignals(False)
        self._update_inspector(page_idx)
        self._sync_rail_status()

    def _on_viewer_zoom_changed(self, _zoom_pct: int) -> None:
        self._sync_rail_status()

    def _on_overlay_toggled(self, checked: bool) -> None:
        self.viewer.set_show_layout_overlay(checked)
        self.settings.show_layout_overlay = checked
        self.settings.save()

    def _update_inspector(self, page_idx: int) -> None:
        ly = self.reader.get_page_layout(page_idx)
        w_mm = ly.width * 25.4 / 72.0
        h_mm = ly.height * 25.4 / 72.0
        fonts_str = ", ".join(ly.fonts_used) if ly.fonts_used else "(Không phát hiện phông văn bản)"
        mode_label = (
            "Giữ vị trí tuyệt đối 1:1 (Exact Frame)"
            if ly.recommended_mode == "exact"
            else "Chuẩn cấu trúc thông minh (Hybrid Flow)"
        )
        self.layout_info_lbl.setText(
            f"<b>Phân tích Trang {page_idx + 1}/{self.reader.page_count}:</b><br/>"
            f"• <b>Kích thước</b>: {ly.width:.0f} × {ly.height:.0f} pt ({w_mm:.0f} × {h_mm:.0f} mm)<br/>"
            f"• <b>Khối văn bản</b>: {ly.text_block_count} khối ({ly.char_count:,} ký tự)<br/>"
            f"• <b>Bảng biểu</b>: {ly.table_count} bảng<br/>"
            f"• <b>Hình ảnh</b>: {ly.image_count} ảnh<br/>"
            f"• <b>Chữ ký số / Con dấu</b>: {ly.signature_count} vùng<br/>"
            f"• <b>Đồ hoạ Vector</b>: {ly.vector_count} nét vẽ/khung<br/>"
            f"• <b>Phông chữ chuẩn hoá</b>: <code>{fonts_str}</code><br/>"
            f"• <b>Chế độ DOCX khuyên dùng</b>: <span style='color:#16A34A;font-weight:600;'>{mode_label}</span>"
        )

    def focus_search(self) -> None:
        self.sidebar_tabs.setVisible(True)
        self.sidebar_tabs.setCurrentIndex(2)
        self._sync_rail_buttons()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def run_search(self) -> None:
        query = self.search_input.text().strip()
        self.search_results_list.clear()
        if not query:
            self._search_hits = []
            self.viewer.set_search_hits([])
            self.search_count_lbl.setText("Nhập từ khoá và bấm Enter để tìm.")
            return

        self._search_hits = self.reader.search(query)
        self.search_count_lbl.setText(f"Tìm thấy {len(self._search_hits)} kết quả cho '{query}':")

        for hit in self._search_hits:
            item = QListWidgetItem(f"[Tr. {hit.page_index + 1}] {hit.snippet}")
            self.search_results_list.addItem(item)

        if self._search_hits:
            self.search_results_list.setCurrentRow(0)
            self.viewer.set_search_hits(self._search_hits, self._search_hits[0])
        else:
            self.viewer.set_search_hits([])

    def _on_search_hit_selected(self, row: int) -> None:
        if 0 <= row < len(self._search_hits):
            hit = self._search_hits[row]
            self.viewer.scroll_to_hit(hit)


class MainWindow(QMainWindow):
    """Cửa sổ chính của ứng dụng QT PDF Pro (Giao diện Sáng/Tối 1 chạm & Bố cục PdfCraft)."""

    def __init__(self, settings: Optional[AppSettings] = None) -> None:
        super().__init__()
        self.settings = settings or AppSettings.load()
        self.setWindowTitle(
            f"{__app_name__} v{__version__} — Đọc PDF & Chuyển PDF sang DOCX Chuẩn xác"
        )
        self.resize(1360, 860)
        self.setAcceptDrops(True)

        self._build_actions_and_menus()
        self._build_toolbar()
        self._build_central_area()
        self._build_statusbar()
        self._apply_theme(self.settings.theme)

    def _build_actions_and_menus(self) -> None:
        menubar = self.menuBar()

        # Menu Tệp
        file_menu = menubar.addMenu("&Tệp")
        self.act_open = QAction("Mở tệp PDF...", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self.action_open_pdf)
        file_menu.addAction(self.act_open)

        self.act_convert = QAction("Chuyển PDF sang Word (.docx)...", self)
        self.act_convert.setShortcut(QKeySequence("Ctrl+Shift+W"))
        self.act_convert.triggered.connect(self.action_convert_to_docx)
        file_menu.addAction(self.act_convert)

        self.recent_menu = QMenu("Tệp mở gần đây", self)
        file_menu.addMenu(self.recent_menu)
        self._refresh_recent_menu()

        file_menu.addSeparator()
        self.act_doc_info = QAction("Thông tin tài liệu (Metadata)...", self)
        self.act_doc_info.setShortcut(QKeySequence("Ctrl+I"))
        self.act_doc_info.triggered.connect(self.action_show_doc_info)
        file_menu.addAction(self.act_doc_info)

        self.act_close_tab = QAction("Đóng tài liệu hiện tại", self)
        self.act_close_tab.setShortcut(QKeySequence.StandardKey.Close)
        self.act_close_tab.triggered.connect(self.action_close_current_tab)
        file_menu.addAction(self.act_close_tab)

        file_menu.addSeparator()
        act_exit = QAction("Thoát", self)
        act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # Menu Xem
        view_menu = menubar.addMenu("&Xem")
        self.act_zoom_in = QAction("Phóng to", self)
        self.act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.act_zoom_in.triggered.connect(lambda: self._with_active_tab(lambda t: t.viewer.zoom_in()))
        view_menu.addAction(self.act_zoom_in)

        self.act_zoom_out = QAction("Thu nhỏ", self)
        self.act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.act_zoom_out.triggered.connect(lambda: self._with_active_tab(lambda t: t.viewer.zoom_out()))
        view_menu.addAction(self.act_zoom_out)

        act_fit_width = QAction("Vừa chiều ngang", self)
        act_fit_width.setShortcut(QKeySequence("Ctrl+1"))
        act_fit_width.triggered.connect(
            lambda: self._with_active_tab(lambda t: t.viewer.set_zoom_mode("fit_width"))
        )
        view_menu.addAction(act_fit_width)

        act_fit_page = QAction("Vừa trang", self)
        act_fit_page.setShortcut(QKeySequence("Ctrl+0"))
        act_fit_page.triggered.connect(
            lambda: self._with_active_tab(lambda t: t.viewer.set_zoom_mode("fit_page"))
        )
        view_menu.addAction(act_fit_page)

        view_menu.addSeparator()
        self.act_toggle_tools_panel = QAction("Ẩn/Hiện bảng Tất cả công cụ (bên trái)", self)
        self.act_toggle_tools_panel.setShortcut(QKeySequence("F3"))
        self.act_toggle_tools_panel.triggered.connect(self.action_toggle_left_tools)
        view_menu.addAction(self.act_toggle_tools_panel)

        self.act_toggle_sidebar = QAction("Ẩn/Hiện ngăn thông tin (bên phải)", self)
        self.act_toggle_sidebar.setShortcut(QKeySequence("F4"))
        self.act_toggle_sidebar.triggered.connect(self.action_toggle_sidebar)
        view_menu.addAction(self.act_toggle_sidebar)

        self.act_toggle_overlay = QAction("Soi khung bố cục & chữ ký trên trang PDF", self)
        self.act_toggle_overlay.setCheckable(True)
        self.act_toggle_overlay.setChecked(self.settings.show_layout_overlay)
        self.act_toggle_overlay.setShortcut(QKeySequence("F8"))
        self.act_toggle_overlay.toggled.connect(self.action_toggle_layout_overlay)
        view_menu.addAction(self.act_toggle_overlay)

        view_menu.addSeparator()
        self.act_toggle_theme = QAction("Đổi giao diện Sáng / Tối", self)
        self.act_toggle_theme.setShortcut(QKeySequence("Ctrl+Shift+T"))
        self.act_toggle_theme.triggered.connect(self.action_toggle_theme)
        view_menu.addAction(self.act_toggle_theme)

        # Menu Công cụ & Chuyển đổi
        tools_menu = menubar.addMenu("&Công cụ && Chuyển đổi")
        act_find = QAction("Tìm kiếm trong PDF...", self)
        act_find.setShortcut(QKeySequence.StandardKey.Find)
        act_find.triggered.connect(lambda: self._with_active_tab(lambda t: t.focus_search()))
        tools_menu.addAction(act_find)

        act_extract_txt = QAction("Trích xuất văn bản trang hiện tại...", self)
        act_extract_txt.setShortcut(QKeySequence("Ctrl+T"))
        act_extract_txt.triggered.connect(self.action_extract_current_page_text)
        tools_menu.addAction(act_extract_txt)

        tools_menu.addSeparator()
        tools_menu.addAction(self.act_convert)

        # Menu Trợ giúp
        help_menu = menubar.addMenu("Trợ &giúp")
        act_about = QAction(f"Giới thiệu {__app_name__}...", self)
        act_about.triggered.connect(self.action_show_about)
        help_menu.addAction(act_about)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Thanh công cụ chính", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        header_bar = QWidget(tb)
        h_layout = QHBoxLayout(header_bar)
        h_layout.setContentsMargins(4, 2, 4, 2)
        h_layout.setSpacing(6)

        self.btn_home = QPushButton("🏠 Trang chủ")
        self.btn_home.setToolTip("Quay về màn hình Trang chủ / Danh sách công cụ")
        self.btn_home.clicked.connect(self.action_go_home)
        h_layout.addWidget(self.btn_home)

        btn_open = QPushButton("📂 Mở PDF")
        btn_open.setToolTip("Mở tệp tài liệu PDF (Ctrl+O)")
        btn_open.clicked.connect(self.action_open_pdf)
        h_layout.addWidget(btn_open)

        # Cụm nút chế độ kiểu PdfCraft (Tất cả công cụ | Soi bố cục)
        self.btn_mode_tools = QPushButton("🛠️ Tất cả công cụ")
        self.btn_mode_tools.setObjectName("modePillBtn")
        self.btn_mode_tools.setCheckable(True)
        self.btn_mode_tools.setChecked(True)
        self.btn_mode_tools.setToolTip("Hiện/Ẩn cột Tất cả công cụ bên trái (F3)")
        self.btn_mode_tools.clicked.connect(self.action_toggle_left_tools)
        h_layout.addWidget(self.btn_mode_tools)

        self.btn_mode_inspect = QPushButton("📐 Soi bố cục && Chữ ký")
        self.btn_mode_inspect.setObjectName("modePillBtn")
        self.btn_mode_inspect.setCheckable(True)
        self.btn_mode_inspect.setChecked(self.settings.show_layout_overlay)
        self.btn_mode_inspect.setToolTip("Bật/Tắt lớp phủ soi khung bố cục & chữ ký số trên trang PDF (F8)")
        self.btn_mode_inspect.toggled.connect(self.action_toggle_layout_overlay)
        h_layout.addWidget(self.btn_mode_inspect)

        # Điều hướng trang & Thu phóng
        self.btn_prev_page = QPushButton("◀")
        self.btn_prev_page.setFixedWidth(28)
        self.btn_prev_page.setToolTip("Trang trước")
        self.btn_prev_page.clicked.connect(self.action_prev_page)
        h_layout.addWidget(self.btn_prev_page)

        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setPrefix("Trang ")
        self.page_spin.valueChanged.connect(self._on_spin_page_changed)
        h_layout.addWidget(self.page_spin)

        self.total_page_lbl = QLabel("/ 0")
        h_layout.addWidget(self.total_page_lbl)

        self.btn_next_page = QPushButton("▶")
        self.btn_next_page.setFixedWidth(28)
        self.btn_next_page.setToolTip("Trang sau")
        self.btn_next_page.clicked.connect(self.action_next_page)
        h_layout.addWidget(self.btn_next_page)

        btn_zoom_out = QPushButton("−")
        btn_zoom_out.setFixedWidth(28)
        btn_zoom_out.setToolTip("Thu nhỏ (Ctrl+-)")
        btn_zoom_out.clicked.connect(lambda: self._with_active_tab(lambda t: t.viewer.zoom_out()))
        h_layout.addWidget(btn_zoom_out)

        self.zoom_combo = QComboBox()
        self.zoom_combo.setMinimumWidth(115)
        self.zoom_combo.addItem("Vừa chiều ngang", ("fit_width", 100))
        self.zoom_combo.addItem("Vừa trang", ("fit_page", 100))
        for pct in (50, 75, 100, 125, 150, 200, 300):
            self.zoom_combo.addItem(f"{pct}%", ("percent", pct))
        self.zoom_combo.activated.connect(self._on_zoom_combo_activated)
        h_layout.addWidget(self.zoom_combo)

        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedWidth(28)
        btn_zoom_in.setToolTip("Phóng to (Ctrl++)")
        btn_zoom_in.clicked.connect(lambda: self._with_active_tab(lambda t: t.viewer.zoom_in()))
        h_layout.addWidget(btn_zoom_in)

        # Ô tìm kiếm nhanh ngay trên thanh Header giống PdfCraft
        self.toolbar_search_input = QLineEdit()
        self.toolbar_search_input.setPlaceholderText("🔍 Tìm nhanh trong PDF...")
        self.toolbar_search_input.setMinimumWidth(135)
        self.toolbar_search_input.setMaximumWidth(190)
        self.toolbar_search_input.returnPressed.connect(self._on_toolbar_quick_search)
        h_layout.addWidget(self.toolbar_search_input, 1)

        h_layout.addStretch(1)

        self.btn_convert_docx = QPushButton("📄 Chuyển sang Word (.docx)")
        self.btn_convert_docx.setObjectName("primaryConvertBtn")
        self.btn_convert_docx.setToolTip(
            "Chuyển đổi PDF sang DOCX chuẩn xác từng thành phần (Ctrl+Shift+W)"
        )
        self.btn_convert_docx.clicked.connect(self.action_convert_to_docx)
        h_layout.addWidget(self.btn_convert_docx)

        # Nút bật/tắt nhanh Giao diện Sáng / Tối ngay trên góc phải Header
        self.btn_theme_toggle = QPushButton("☀️ Giao diện Sáng")
        self.btn_theme_toggle.setObjectName("themeToggleBtn")
        self.btn_theme_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme_toggle.setToolTip("Bật/Tắt nhanh giữa Giao diện Sáng và Giao diện Tối (Ctrl+Shift+T)")
        self.btn_theme_toggle.clicked.connect(self.action_toggle_theme)
        h_layout.addWidget(self.btn_theme_toggle)

        tb.addWidget(header_bar)

    def _build_central_area(self) -> None:
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)

        # Trang chào mừng / Dashboard kiểu PdfCraft
        welcome = QWidget()
        w_layout = QVBoxLayout(welcome)
        w_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("welcomeCard")
        card.setMaximumWidth(720)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(14)

        title_lbl = QLabel(
            f"<h1 style='margin-bottom:4px;'>{__app_name__} v{__version__}</h1>"
            "<p style='font-size:14px;color:#64748B;'>"
            "Không gian làm việc PDF chuyên nghiệp — Đọc PDF tốc độ cao &amp; Chuyển đổi PDF sang Word (.docx) "
            "bảo toàn 100% con dấu đỏ, chữ ký số, số hiệu đóng dấu và bảng biểu hành chính Việt Nam."
            "</p>"
        )
        title_lbl.setWordWrap(True)
        card_layout.addWidget(title_lbl)

        features_lbl = QLabel(
            "<b>Điểm nổi bật trong phiên bản v0.2.0:</b>"
            "<ul>"
            "<li><b>Bố cục 3 cột hiện đại (PdfCraft Workbench)</b>: Cột Tất cả công cụ bên trái, Khung đọc PDF tốc độ cao ở giữa, "
            "Ngăn Soi bố cục &amp; Thanh điều khiển thu phóng dọc bên phải.</li>"
            "<li><b>Giao diện Sáng / Tối 1 chạm</b>: Chuyển đổi tức thì bằng nút <b>☀️ Sáng / 🌙 Tối</b> trên góc phải thanh công cụ.</li>"
            "<li><b>Chuyển đổi văn bản hành chính Việt Nam chuẩn 100%</b>: Giữ nguyên số văn bản đóng dấu đè (<i>Số: 3865/QĐ-UBND</i>), "
            "con dấu đỏ UBND trong suốt, chữ ký số, chữ ký nháy và bố cục 2 cột Quốc hiệu / Tiêu ngữ.</li>"
            "</ul>"
        )
        features_lbl.setWordWrap(True)
        card_layout.addWidget(features_lbl)

        btn_row = QHBoxLayout()
        open_welcome_btn = QPushButton("📂 Mở tệp PDF để đọc & soi bố cục...")
        open_welcome_btn.setMinimumHeight(40)
        open_welcome_btn.clicked.connect(self.action_open_pdf)

        conv_welcome_btn = QPushButton("📄 Chọn tệp PDF chuyển ngay sang Word (.docx)...")
        conv_welcome_btn.setObjectName("primaryConvertBtn")
        conv_welcome_btn.setMinimumHeight(40)
        conv_welcome_btn.clicked.connect(self.action_convert_to_docx)

        self.btn_resume_tabs = QPushButton("↩ Quay lại tài liệu đang mở")
        self.btn_resume_tabs.setMinimumHeight(40)
        self.btn_resume_tabs.setVisible(False)
        self.btn_resume_tabs.clicked.connect(lambda: self.stack.setCurrentWidget(self.doc_tabs))

        btn_row.addWidget(open_welcome_btn)
        btn_row.addWidget(conv_welcome_btn)
        btn_row.addWidget(self.btn_resume_tabs)
        card_layout.addLayout(btn_row)

        card_layout.addWidget(QLabel("<b>Tệp mở gần đây (nhấp đúp để mở ngay):</b>"))
        self.welcome_recent_list = QListWidget()
        self.welcome_recent_list.setMaximumHeight(175)
        self.welcome_recent_list.itemDoubleClicked.connect(self._on_welcome_recent_activated)
        card_layout.addWidget(self.welcome_recent_list)
        self._refresh_welcome_recent_list()

        w_layout.addWidget(card)
        self.stack.addWidget(welcome)

        # Khung chứa đa tab tài liệu PDF
        self.doc_tabs = QTabWidget()
        self.doc_tabs.setTabsClosable(True)
        self.doc_tabs.setMovable(True)
        self.doc_tabs.tabCloseRequested.connect(self.close_tab_at)
        self.doc_tabs.currentChanged.connect(self._on_active_doc_tab_changed)
        self.stack.addWidget(self.doc_tabs)

    def _build_statusbar(self) -> None:
        sb = QStatusBar(self)
        self.setStatusBar(sb)
        self.status_doc_lbl = QLabel("Sẵn sàng — Kéo thả tệp PDF vào cửa sổ hoặc bấm Ctrl+O để mở.")
        self.status_theme_lbl = QLabel("")
        self.status_zoom_lbl = QLabel("Thu phóng: 100%")
        sb.addWidget(self.status_doc_lbl, 1)
        sb.addPermanentWidget(self.status_theme_lbl)
        sb.addPermanentWidget(self.status_zoom_lbl)

    def _apply_theme(self, theme: str) -> None:
        normalized = "light" if theme == "light" else "dark"
        self.settings.theme = normalized
        self.setStyleSheet(get_stylesheet(normalized))

        # Cập nhật nhãn nút chuyển Sáng/Tối trên thanh công cụ
        if hasattr(self, "btn_theme_toggle"):
            if normalized == "dark":
                self.btn_theme_toggle.setText("☀️ Giao diện Sáng")
                self.btn_theme_toggle.setToolTip(
                    "Đang ở Giao diện Tối — Bấm để chuyển sang Giao diện Sáng (Ctrl+Shift+T)"
                )
            else:
                self.btn_theme_toggle.setText("🌙 Giao diện Tối")
                self.btn_theme_toggle.setToolTip(
                    "Đang ở Giao diện Sáng — Bấm để chuyển sang Giao diện Tối (Ctrl+Shift+T)"
                )

        if hasattr(self, "status_theme_lbl"):
            mode_txt = "Sáng (Light)" if normalized == "light" else "Tối (Dark)"
            self.status_theme_lbl.setText(f"Giao diện: {mode_txt}  |  ")

        # Đồng bộ màu nền vùng vẽ PDF của tất cả các tab đang mở
        if hasattr(self, "doc_tabs"):
            for i in range(self.doc_tabs.count()):
                w = self.doc_tabs.widget(i)
                if isinstance(w, PDFDocumentTab):
                    w.viewer.set_canvas_theme(normalized)

    def active_tab(self) -> Optional[PDFDocumentTab]:
        if self.doc_tabs.count() == 0:
            return None
        w = self.doc_tabs.currentWidget()
        return w if isinstance(w, PDFDocumentTab) else None

    def _with_active_tab(self, fn: Callable[[PDFDocumentTab], None]) -> None:
        tab = self.active_tab()
        if tab is not None:
            fn(tab)

    # ─── Mở & Quản lý Tab PDF ───────────────────────────────────────────

    def open_pdf_path(self, pdf_path: str | Path, password: Optional[str] = None) -> Optional[PDFDocumentTab]:
        """Mở một tệp PDF vào tab mới (hoặc chuyển tới tab đang mở tệp đó)."""
        path = Path(pdf_path).resolve()
        if not path.exists():
            QMessageBox.warning(self, "Không tìm thấy tệp", f"Tệp không tồn tại:\n{path}")
            return None

        # Nếu tệp đã mở ở một tab, chuyển sang tab đó
        for i in range(self.doc_tabs.count()):
            w = self.doc_tabs.widget(i)
            if isinstance(w, PDFDocumentTab) and w.reader.path == path:
                self.doc_tabs.setCurrentIndex(i)
                self.stack.setCurrentWidget(self.doc_tabs)
                self.btn_resume_tabs.setVisible(True)
                return w

        try:
            reader = PDFDocumentReader(path, password=password)
        except PermissionError:
            pwd, ok = QInputDialog.getText(
                self,
                "Tệp PDF có mật khẩu",
                f"Nhập mật khẩu để mở '{path.name}':",
                QLineEdit.EchoMode.Password,
            )
            if not ok or not pwd:
                return None
            try:
                reader = PDFDocumentReader(path, password=pwd)
            except Exception as exc:
                QMessageBox.critical(self, "Sai mật khẩu", str(exc))
                return None
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi mở tệp PDF", f"Không thể mở tệp PDF:\n{exc}")
            return None

        tab = PDFDocumentTab(reader, self.settings, self)
        tab.viewer.pageChanged.connect(lambda _p: self._sync_toolbar_with_active_tab())
        tab.viewer.zoomChanged.connect(lambda _z: self._sync_toolbar_with_active_tab())
        tab.extract_page_text_btn.clicked.connect(self.action_extract_current_page_text)
        tab.sidebar_convert_btn.clicked.connect(self.action_convert_to_docx)
        tab.banner_convert_btn.clicked.connect(lambda: self.action_convert_to_docx_mode("hybrid"))

        # Kết nối các nút ở bảng "Tất cả công cụ" bên trái
        tab.tool_btn_convert_hybrid.clicked.connect(
            lambda: self.action_convert_to_docx_mode("hybrid")
        )
        tab.tool_btn_convert_exact.clicked.connect(
            lambda: self.action_convert_to_docx_mode("exact")
        )
        tab.tool_btn_convert_dialog.clicked.connect(self.action_convert_to_docx)
        tab.tool_btn_extract_text.clicked.connect(self.action_extract_current_page_text)
        tab.tool_btn_doc_info.clicked.connect(self.action_show_doc_info)

        safe_tab_title = path.name.replace("&", "&&")
        idx = self.doc_tabs.addTab(tab, safe_tab_title)
        self.doc_tabs.setTabToolTip(idx, str(path))
        self.doc_tabs.setCurrentIndex(idx)
        self.stack.setCurrentWidget(self.doc_tabs)
        self.btn_resume_tabs.setVisible(True)

        self.settings.add_recent_file(path)
        self._refresh_recent_menu()
        self._refresh_welcome_recent_list()
        self._sync_toolbar_with_active_tab()
        return tab

    def close_tab_at(self, index: int) -> None:
        w = self.doc_tabs.widget(index)
        self.doc_tabs.removeTab(index)
        if isinstance(w, PDFDocumentTab):
            w.close_document()
            w.deleteLater()
        if self.doc_tabs.count() == 0:
            self.stack.setCurrentIndex(0)
            self.btn_resume_tabs.setVisible(False)
        self._sync_toolbar_with_active_tab()

    def _on_active_doc_tab_changed(self, _index: int) -> None:
        self._sync_toolbar_with_active_tab()

    def _sync_toolbar_with_active_tab(self) -> None:
        tab = self.active_tab()
        if tab is None:
            self.page_spin.blockSignals(True)
            self.page_spin.setMaximum(1)
            self.page_spin.setValue(1)
            self.page_spin.blockSignals(False)
            self.total_page_lbl.setText("/ 0 ")
            self.status_doc_lbl.setText("Chưa mở tài liệu nào.")
            self.status_zoom_lbl.setText("Thu phóng: --")
            return

        total = tab.reader.page_count
        cur = tab.viewer.current_page
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(1, total))
        self.page_spin.setValue(cur + 1)
        self.page_spin.blockSignals(False)
        self.total_page_lbl.setText(f"/ {total} ")

        self.btn_mode_tools.blockSignals(True)
        self.btn_mode_tools.setChecked(tab.tools_panel.isVisible())
        self.btn_mode_tools.blockSignals(False)

        pw, ph = tab.reader.get_page_size(cur)
        self.status_doc_lbl.setText(
            f"{tab.reader.path.name} — Trang {cur + 1}/{total} ({pw:.0f}×{ph:.0f} pt)"
        )
        self.status_zoom_lbl.setText(f"Thu phóng: {tab.viewer.zoom_percent}%")

    # ─── Các hành động trên Menu & Toolbar ──────────────────────────────

    def action_go_home(self) -> None:
        if self.stack.currentIndex() == 0 and self.doc_tabs.count() > 0:
            self.stack.setCurrentWidget(self.doc_tabs)
        else:
            self.btn_resume_tabs.setVisible(self.doc_tabs.count() > 0)
            self.stack.setCurrentIndex(0)

    def action_open_pdf(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn tệp PDF để mở",
            "",
            "Tài liệu PDF (*.pdf);;Tất cả các tệp (*.*)",
        )
        for f in files:
            self.open_pdf_path(f)

    def action_convert_to_docx_mode(self, mode: str = "hybrid") -> None:
        self.settings.last_convert_mode = mode
        self.action_convert_to_docx()

    def action_convert_to_docx(self) -> None:
        tab = self.active_tab()
        if tab is None:
            chosen, _ = QFileDialog.getOpenFileName(
                self,
                "Chọn tệp PDF cần chuyển sang Word (.docx)",
                "",
                "Tài liệu PDF (*.pdf)",
            )
            if not chosen:
                return
            tab = self.open_pdf_path(chosen)
            if tab is None:
                return

        dlg = ConvertToDocxDialog(
            pdf_path=tab.reader.path,
            total_pages=tab.reader.page_count,
            current_page=tab.viewer.current_page,
            settings=self.settings,
            parent=self,
        )
        dlg.exec()

    def action_prev_page(self) -> None:
        tab = self.active_tab()
        if tab is not None and tab.viewer.current_page > 0:
            tab.viewer.go_to_page(tab.viewer.current_page - 1)

    def action_next_page(self) -> None:
        tab = self.active_tab()
        if tab is not None and tab.viewer.current_page < tab.reader.page_count - 1:
            tab.viewer.go_to_page(tab.viewer.current_page + 1)

    def _on_spin_page_changed(self, val_1based: int) -> None:
        tab = self.active_tab()
        if tab is not None:
            tab.viewer.go_to_page(val_1based - 1)

    def _on_zoom_combo_activated(self, index: int) -> None:
        data = self.zoom_combo.itemData(index)
        tab = self.active_tab()
        if tab is not None and isinstance(data, tuple):
            mode, pct = data
            tab.viewer.set_zoom_mode(mode, pct)

    def _on_toolbar_quick_search(self) -> None:
        query = self.toolbar_search_input.text().strip()
        tab = self.active_tab()
        if tab is not None and query:
            self.stack.setCurrentWidget(self.doc_tabs)
            tab.sidebar_tabs.setVisible(True)
            tab.sidebar_tabs.setCurrentIndex(2)
            tab._sync_rail_buttons()
            tab.search_input.setText(query)
            tab.run_search()

    def action_toggle_left_tools(self) -> None:
        tab = self.active_tab()
        if tab is not None:
            vis = not tab.tools_panel.isVisible()
            tab.tools_panel.setVisible(vis)
            self.btn_mode_tools.blockSignals(True)
            self.btn_mode_tools.setChecked(vis)
            self.btn_mode_tools.blockSignals(False)

    def action_toggle_sidebar(self) -> None:
        tab = self.active_tab()
        if tab is not None:
            vis = not tab.sidebar_tabs.isVisible()
            tab.sidebar_tabs.setVisible(vis)
            tab._sync_rail_buttons()

    def action_toggle_layout_overlay(self, checked: bool) -> None:
        self.settings.show_layout_overlay = checked
        self.settings.save()
        self.act_toggle_overlay.blockSignals(True)
        self.act_toggle_overlay.setChecked(checked)
        self.act_toggle_overlay.blockSignals(False)
        if hasattr(self, "btn_mode_inspect"):
            self.btn_mode_inspect.blockSignals(True)
            self.btn_mode_inspect.setChecked(checked)
            self.btn_mode_inspect.blockSignals(False)

        for i in range(self.doc_tabs.count()):
            w = self.doc_tabs.widget(i)
            if isinstance(w, PDFDocumentTab):
                w.chk_overlay.blockSignals(True)
                w.chk_overlay.setChecked(checked)
                w.chk_overlay.blockSignals(False)
                w.viewer.set_show_layout_overlay(checked)

    def action_toggle_theme(self) -> None:
        new_theme = "light" if self.settings.theme == "dark" else "dark"
        self._apply_theme(new_theme)
        self.settings.save()

    def action_show_doc_info(self) -> None:
        tab = self.active_tab()
        if tab is None:
            return
        dlg = DocumentInfoDialog(tab.reader.get_info(), self)
        dlg.exec()

    def action_extract_current_page_text(self) -> None:
        tab = self.active_tab()
        if tab is None:
            return
        cur = tab.viewer.current_page
        txt = tab.reader.get_page_text(cur)
        dlg = PageTextDialog(
            f"Văn bản Trang {cur + 1}/{tab.reader.page_count} — {tab.reader.path.name}",
            txt,
            self,
        )
        dlg.exec()

    def action_close_current_tab(self) -> None:
        if self.doc_tabs.count() > 0:
            self.close_tab_at(self.doc_tabs.currentIndex())

    def action_show_about(self) -> None:
        dlg = AboutDialog(self)
        dlg.exec()

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        existing = [p for p in self.settings.recent_files if Path(p).exists()]
        if not existing:
            empty_act = QAction("(Chưa có tệp gần đây)", self)
            empty_act.setEnabled(False)
            self.recent_menu.addAction(empty_act)
            return

        for p in existing:
            act = QAction(p.replace("&", "&&"), self)
            act.triggered.connect(lambda _chk=False, path=p: self.open_pdf_path(path))
            self.recent_menu.addAction(act)

    def _refresh_welcome_recent_list(self) -> None:
        self.welcome_recent_list.clear()
        for p in self.settings.recent_files:
            if Path(p).exists():
                self.welcome_recent_list.addItem(p)

    def _on_welcome_recent_activated(self, item: QListWidgetItem) -> None:
        self.open_pdf_path(item.text())

    # ─── Kéo thả tệp PDF vào cửa sổ ──────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            local_file = url.toLocalFile()
            if local_file.lower().endswith(".pdf"):
                self.open_pdf_path(local_file)
        event.acceptProposedAction()
