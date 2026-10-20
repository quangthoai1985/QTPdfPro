"""Cửa sổ chính và Tab đọc tài liệu PDF của QT PDF Pro (bố cục lấy cảm hứng từ PdfCraft)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QImage,
    QKeySequence,
    QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
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
    QTabBar,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro import __app_name__, __github_repo__, __version__
from qtpdfpro.core.converter import is_admin_document
from qtpdfpro.core.reader import PDFDocumentReader, SearchHit
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.core.word_com_bridge import is_ms_word_available
from qtpdfpro.ui.annotation_tools import AnnotationController, AnnotationListPanel, EditToolbar
from qtpdfpro.ui.batch_dialog import BatchConvertDialog
from qtpdfpro.ui.command_palette import SEARCH_IN_DOCUMENT_KEY, CommandPaletteDialog
from qtpdfpro.ui.convert_dialog import ConvertToDocxDialog
from qtpdfpro.ui.dialogs import AboutDialog, DocumentInfoDialog, PageTextDialog
from qtpdfpro.ui.home_page import HomePage
from qtpdfpro.ui.nd30_dialog import LayoutVerifyDialog, ND30ReportDialog
from qtpdfpro.ui.organizer_dialog import PageOrganizerDialog
from qtpdfpro.ui.pdf_canvas import PDFScrollViewer
from qtpdfpro.ui.print_dialog import PrintDialog
from qtpdfpro.ui.theme import get_stylesheet
from qtpdfpro.ui.tool_catalog import CATEGORIES, COMING_SOON_LABEL, TOOLS, get_tool
from qtpdfpro.ui.update_dialog import UpdateController


class PDFDocumentTab(QWidget):
    """Một tab tài liệu PDF hoàn chỉnh theo bố cục 3 cột kiểu PdfCraft:
    - Cột trái: Bảng 'Tất cả công cụ' (All Tools) có ô lọc nhanh & thẻ thao tác 1 chạm
    - Cột giữa: Thanh thông báo chữ ký số/con dấu + Khung vẽ PDF tốc độ cao (PDFScrollViewer)
    - Cột phải: Ngăn thông tin 5 tab (Trang, Mục lục, Tìm kiếm, Soi bố cục, Chú thích) + Thanh điều khiển dọc
    - Chế độ «Chỉnh sửa» (Ctrl+E): thanh công cụ chú thích phía trên khung đọc (tô màu, đánh dấu, vẽ, chèn chữ…)
    """

    modifiedChanged = Signal(bool)
    editModeChanged = Signal(bool)
    statusMessage = Signal(str)

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
        self._tool_buttons: List[tuple[str, str, QPushButton]] = []
        self._tool_sections: List[tuple[str, QLabel]] = []
        self._tool_category = "all"
        self.is_admin_document = False

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

        # Chế độ chỉnh sửa: bộ điều khiển chú thích + thanh công cụ 2 tầng (ẩn cho tới khi bật)
        self.annot_controller = AnnotationController(self.reader, self.settings.annot_author or None, self)
        self.edit_toolbar = EditToolbar(self.annot_controller, self.viewer, self)
        self.edit_toolbar.setVisible(False)
        self.edit_toolbar.exitRequested.connect(self.exit_edit_mode)
        self.annot_controller.documentChanged.connect(self._on_annotations_changed)
        self.annot_controller.message.connect(self.statusMessage)
        self.annot_controller.toolChanged.connect(lambda _k: self.viewer.refresh_cursor())
        self.annot_controller.selectionChanged.connect(self._on_annotation_selection)
        center_layout.addWidget(self.edit_toolbar)
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

        # Ngăn 5: Chú thích (danh sách chú thích, đi tới, sửa, xoá)
        self.annot_panel = AnnotationListPanel()
        self.annot_panel.activated.connect(self.go_to_annotation)
        self.annot_panel.editRequested.connect(lambda pg, x: self.annot_controller.edit_annotation(pg, x, self))
        self.annot_panel.deleteRequested.connect(self.annot_controller.delete_annotation)
        self.annot_panel.startEditingRequested.connect(lambda: self.enter_edit_mode())
        self.editModeChanged.connect(lambda on: self.annot_panel.btn_start.setVisible(not on))
        self.sidebar_tabs.addTab(self.annot_panel, "Chú thích")
        self._annot_list_dirty = True

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
        self.sidebar_tabs.currentChanged.connect(lambda _i: self._refresh_annotation_list_if_visible())
        self._update_inspector(0)
        self._sync_rail_status()
        self._sync_rail_buttons()

    def _build_left_tools_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("leftToolsPanel")
        panel.setMinimumWidth(255)
        panel.setMaximumWidth(300)

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

        lbl_conv = self._make_section_label("CHUYỂN ĐỔI SANG WORD", "convert")
        body_layout.addWidget(lbl_conv)

        self.tool_btn_convert_nd30 = self._make_tool_card(
            "🏛️ Xuất Word chuẩn NĐ30\nVăn bản hành chính, giữ đúng PDF",
            primary=True,
            category="convert",
        )
        self.tool_btn_nd30_check = self._make_tool_card(
            "✅ Kiểm tra thể thức NĐ30\nLề, giãn dòng, cách đoạn, thành phần",
            category="convert",
        )
        self.tool_btn_convert_exact = self._make_tool_card(
            "📐 Xuất Word giữ vị trí 1:1\nKhung chữ theo toạ độ tuyệt đối",
            category="convert",
        )
        self.tool_btn_convert_hybrid = self._make_tool_card(
            "📝 Xuất Word dạng dòng chảy\nTài liệu thường (pdf2docx)",
            category="convert",
        )
        self.tool_btn_convert_dialog = self._make_tool_card(
            "⚙️ Tuỳ chỉnh xuất DOCX…\nTrang, chính sách NĐ30, kiểm chứng",
            category="convert",
        )
        for b in (
            self.tool_btn_convert_nd30,
            self.tool_btn_nd30_check,
            self.tool_btn_convert_exact,
            self.tool_btn_convert_hybrid,
            self.tool_btn_convert_dialog,
        ):
            body_layout.addWidget(b)

        lbl_edit = self._make_section_label("CHỈNH SỬA PDF", "edit")
        body_layout.addWidget(lbl_edit)
        self.tool_btn_edit_mode = self._make_tool_card(
            "✏️ Chỉnh sửa && chú thích (Ctrl+E)\nTô màu, đánh dấu, vẽ, chèn chữ", category="edit"
        )
        self.tool_btn_highlight = self._make_tool_card(
            "🖍 Tô sáng văn bản\nKéo chuột qua chữ để tô màu", category="edit"
        )
        self.tool_btn_stamp = self._make_tool_card(
            "🔖 Đóng dấu\nĐÃ DUYỆT, BẢN SAO, MẬT, KHẨN…", category="edit"
        )
        self.tool_btn_organize = self._make_tool_card(
            "🧩 Sắp xếp && cắt ghép trang\nKéo thả, xoay, xoá, ghép, tách", category="edit"
        )
        self.tool_btn_save = self._make_tool_card("💾 Lưu thay đổi (Ctrl+S)\nGhi bổ sung, giữ chữ ký số", category="edit")
        self.tool_btn_edit_mode.clicked.connect(lambda: self.enter_edit_mode())
        self.tool_btn_highlight.clicked.connect(lambda: self.enter_edit_mode("highlight"))
        self.tool_btn_stamp.clicked.connect(lambda: self.enter_edit_mode("stamp"))
        for b in (self.tool_btn_edit_mode, self.tool_btn_highlight, self.tool_btn_stamp,
                  self.tool_btn_organize, self.tool_btn_save):
            body_layout.addWidget(b)

        lbl_inspect = self._make_section_label("SOI BỐ CỤC & VĂN BẢN", "read")
        body_layout.addWidget(lbl_inspect)

        self.tool_btn_overlay = self._make_tool_card(
            "🔍 Soi khung bố cục (F8)\nChữ, bảng, con dấu, vector", category="read"
        )
        self.tool_btn_extract_text = self._make_tool_card(
            "📋 Trích xuất văn bản\nXem && sao chép trang hiện tại", category="read"
        )
        self.tool_btn_search = self._make_tool_card(
            "🔎 Tìm kiếm toàn văn (Ctrl+F)\nTô sáng mọi vị trí khớp", category="read"
        )
        body_layout.addWidget(self.tool_btn_overlay)
        body_layout.addWidget(self.tool_btn_extract_text)
        body_layout.addWidget(self.tool_btn_search)

        lbl_page = self._make_section_label("THAO TÁC TRANG & TÀI LIỆU", "read")
        body_layout.addWidget(lbl_page)

        self.tool_btn_rot_left = self._make_tool_card("↺ Xoay trang sang trái 90°", category="read")
        self.tool_btn_rot_right = self._make_tool_card("↻ Xoay trang sang phải 90°", category="read")
        self.tool_btn_fit_width = self._make_tool_card("↔ Phóng vừa khít chiều ngang", category="read")
        self.tool_btn_fit_page = self._make_tool_card("📄 Thu phóng vừa trọn trang", category="read")
        self.tool_btn_doc_info = self._make_tool_card("ℹ️ Thông tin && Metadata tài liệu", category="read")
        self.tool_btn_print = self._make_tool_card("🖨 In tài liệu (Ctrl+P)\nXem trước, khổ giấy, 2 mặt", category="read")

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
        body_layout.addWidget(self.tool_btn_print)

        self.tool_btn_all_tools = self._make_tool_card(
            "🧰 Xem tất cả công cụ… (Ctrl+K)\nKể cả các công cụ " + COMING_SOON_LABEL, category="*"
        )
        body_layout.addWidget(self.tool_btn_all_tools)
        body_layout.addStretch(1)

        scroll.setWidget(tools_body)
        layout.addWidget(scroll, 1)
        return panel

    def _make_section_label(self, text: str, category: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("catalogSection")
        self._tool_sections.append((category, lbl))
        return lbl

    def _make_tool_card(self, text: str, primary: bool = False, category: str = "read") -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("toolCardPrimaryBtn" if primary else "toolCardBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tool_buttons.append((text.lower(), category, btn))
        return btn

    def set_tool_category(self, category: str) -> None:
        """Lọc thẻ công cụ theo chế độ chọn trên thanh chế độ (all/read/convert/edit/sign)."""
        self._tool_category = category or "all"
        self._filter_left_tools(self.tool_filter_input.text())

    def _filter_left_tools(self, query: str) -> None:
        q = query.strip().lower()
        cat = self._tool_category
        shown: set[str] = set()
        for label_text, btn_cat, btn in self._tool_buttons:
            in_cat = cat == "all" or btn_cat in (cat, "*")
            vis = in_cat and (not q or q in label_text)
            btn.setVisible(vis)
            if vis:
                shown.add(btn_cat)
        for sec_cat, lbl in self._tool_sections:
            lbl.setVisible(sec_cat in shown)

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
            ("💬\nChú\nthích", 4, "Hiện/Ẩn danh sách chú thích (tô sáng, ghi chú, dấu đóng…)"),
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

        try:
            self.is_admin_document = self.reader.page_count > 0 and is_admin_document(self.reader.doc, 0)
        except Exception:
            self.is_admin_document = False

        if self.is_admin_document:
            sig_txt = f" có {total_sigs} chữ ký số / con dấu" if total_sigs else ""
            self.banner_info_lbl.setText(
                f"🏛️ <b>Văn bản hành chính{sig_txt}</b> — Xuất Word chuẩn thể thức NĐ30: giữ đúng lề, giãn dòng, "
                "Quốc hiệu – Tiêu ngữ &amp; khối ký trong bảng không viền, đường kẻ và con dấu như PDF gốc."
            )
            self.banner_convert_btn.setText("⚡ Xuất Word chuẩn NĐ30 ngay")
            self.signature_banner.setVisible(True)
        elif total_sigs > 0:
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
        self.viewer.set_interaction(None)
        self.reader.close()

    # ─── Chế độ chỉnh sửa (chú thích) ─────────────────────────────────────

    @property
    def edit_mode(self) -> bool:
        return self.viewer.interaction is not None

    def enter_edit_mode(self, tool: Optional[str] = None) -> None:
        """Bật thanh công cụ chú thích; `tool` chọn sẵn công cụ (vd "highlight", "stamp")."""
        if not self.reader.is_pdf:
            self.statusMessage.emit("Chỉ chỉnh sửa được tệp PDF.")
            return
        was = self.edit_mode
        self.edit_toolbar.setVisible(True)
        self.edit_toolbar.set_shortcuts_enabled(True)
        if tool:
            self.annot_controller.set_tool(tool)
        self.viewer.set_interaction(self.annot_controller)
        self._sync_history()
        self.viewer.setFocus()
        if not was:
            self.editModeChanged.emit(True)
            self.statusMessage.emit("Chế độ chỉnh sửa — chọn công cụ trên thanh phía trên trang (Ctrl+E để thoát).")

    def exit_edit_mode(self) -> None:
        if not self.edit_mode:
            return
        self.viewer.set_interaction(None)
        self.edit_toolbar.set_shortcuts_enabled(False)
        self.edit_toolbar.setVisible(False)
        self.editModeChanged.emit(False)

    def toggle_edit_mode(self) -> None:
        if self.edit_mode:
            self.exit_edit_mode()
        else:
            self.enter_edit_mode()

    def _sync_history(self) -> None:
        if not self.reader.has_edit_session:
            self.edit_toolbar.update_history(False, False)
            return
        ses = self.annot_controller.session
        self.edit_toolbar.update_history(ses.can_undo, ses.can_redo, ses.undo_label, ses.redo_label)

    def _on_annotations_changed(self, page_index: int) -> None:
        self.viewer.refresh_pages([page_index])
        self._refresh_thumbnail(page_index)
        self._annot_list_dirty = True
        self._refresh_annotation_list_if_visible()
        self._sync_history()
        self.modifiedChanged.emit(self.reader.has_unsaved_changes)

    def _on_annotation_selection(self) -> None:
        sel = self.annot_controller.selected
        if sel is not None:
            self.annot_panel.select(*sel)
        self.viewer.widget().update()

    def _refresh_annotation_list_if_visible(self) -> None:
        if self._annot_list_dirty and self.sidebar_tabs.isVisible() and self.sidebar_tabs.currentIndex() == 4:
            self.refresh_annotation_list()

    def refresh_annotation_list(self) -> None:
        self.annot_panel.set_items(self.annot_controller.session.list_annotations())
        self._annot_list_dirty = False

    def show_annotation_panel(self) -> None:
        self.sidebar_tabs.setVisible(True)
        self.sidebar_tabs.setCurrentIndex(4)
        self._sync_rail_buttons()
        self.refresh_annotation_list()

    def go_to_annotation(self, page_index: int, xref: int) -> None:
        rect = self.annot_controller.session.annotation_rect(page_index, xref)
        if rect is None:
            return
        self.viewer.scroll_to_rect(page_index, rect)
        self.annot_controller.select(page_index, xref)

    def after_save(self) -> None:
        """Làm mới hiển thị sau khi lưu (tệp có thể vừa được mở lại / đổi đường dẫn)."""
        self.viewer.refresh_pages(range(self.reader.page_count))
        self._annot_list_dirty = True
        self._refresh_annotation_list_if_visible()
        self._sync_history()
        self.modifiedChanged.emit(self.reader.has_unsaved_changes)

    def _refresh_thumbnail(self, page_index: int) -> None:
        item = self.thumb_list.item(page_index)
        if item is None or page_index >= 60:
            return
        buf = self.reader.render_page(page_index, scale=0.18)
        qimg = QImage(buf.rgb_bytes, buf.width, buf.height, buf.stride, QImage.Format.Format_RGB888).copy()
        item.setIcon(QIcon(QPixmap.fromImage(qimg)))

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
    """Cửa sổ chính QT PDF Pro theo bố cục PdfCraft.

    - Tầng 1 (dải tiêu đề): nút Trang chủ, các tab tài liệu, «＋ Mở», Trợ giúp, nút Sáng/Tối.
    - Tầng 2 (thanh chế độ): «☰ Menu», các chế độ Tất cả công cụ · Đọc · Chuyển đổi · Chỉnh sửa ·
      Ký số & Bảo mật, điều hướng trang/thu phóng (khi mở tài liệu), ô tìm công cụ (Ctrl+K), xuất Word.
    - Thân: Trang chủ (`HomePage`) hoặc vùng tài liệu (`PDFDocumentTab`).
    """

    def __init__(self, settings: Optional[AppSettings] = None) -> None:
        super().__init__()
        self.settings = settings or AppSettings.load()
        self.setWindowTitle(f"{__app_name__} v{__version__} — Đọc PDF & Chuyển PDF sang Word chuẩn NĐ30")
        self.resize(1400, 880)
        self.setAcceptDrops(True)
        self._mode_category = "all"
        self._toast: Optional[QLabel] = None
        self.updater = UpdateController(self, self.settings)

        self._build_actions_and_menus()
        central = QWidget()
        central.setObjectName("appRoot")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_title_strip())
        root.addWidget(self._build_mode_bar())
        self._build_central_area()
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._build_statusbar()
        self._apply_theme(self.settings.theme)
        self._show_home()

    # ─── Hành động & Menu (gắn vào nút «☰ Menu») ───────────────────────────

    def _build_actions_and_menus(self) -> None:
        self.main_menu = QMenu(self)

        file_menu = self.main_menu.addMenu("Tệp")
        self.act_open = QAction("Mở tệp PDF...", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self.action_open_pdf)
        file_menu.addAction(self.act_open)

        self.act_convert = QAction("Chuyển PDF sang Word (.docx)...", self)
        self.act_convert.setShortcut(QKeySequence("Ctrl+Shift+W"))
        self.act_convert.triggered.connect(self.action_convert_to_docx)
        file_menu.addAction(self.act_convert)

        self.act_batch_convert = QAction("Chuyển đổi hàng loạt PDF sang Word...", self)
        self.act_batch_convert.setShortcut(QKeySequence("Ctrl+Shift+B"))
        self.act_batch_convert.triggered.connect(lambda: self.run_tool("batch_convert"))
        file_menu.addAction(self.act_batch_convert)

        self.recent_menu = QMenu("Tệp mở gần đây", self)
        file_menu.addMenu(self.recent_menu)
        self._refresh_recent_menu()

        file_menu.addSeparator()
        self.act_print = QAction("In...", self)
        self.act_print.setShortcut(QKeySequence("Ctrl+P"))
        self.act_print.triggered.connect(lambda: self.run_tool("print"))
        file_menu.addAction(self.act_print)

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

        view_menu = self.main_menu.addMenu("Xem")
        self.act_home = QAction("Trang chủ", self)
        self.act_home.setShortcut(QKeySequence("Alt+Home"))
        self.act_home.triggered.connect(self.action_go_home)
        view_menu.addAction(self.act_home)
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
        act_fit_width.triggered.connect(lambda: self._with_active_tab(lambda t: t.viewer.set_zoom_mode("fit_width")))
        view_menu.addAction(act_fit_width)
        act_fit_page = QAction("Vừa trang", self)
        act_fit_page.setShortcut(QKeySequence("Ctrl+0"))
        act_fit_page.triggered.connect(lambda: self._with_active_tab(lambda t: t.viewer.set_zoom_mode("fit_page")))
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
        self.act_toggle_overlay = QAction("Soi khung bố cục && chữ ký trên trang PDF", self)
        self.act_toggle_overlay.setCheckable(True)
        self.act_toggle_overlay.setChecked(self.settings.show_layout_overlay)
        self.act_toggle_overlay.setShortcut(QKeySequence("F8"))
        self.act_toggle_overlay.toggled.connect(self.action_toggle_layout_overlay)
        view_menu.addAction(self.act_toggle_overlay)
        self.act_read_mode = QAction("Chế độ đọc tập trung (toàn màn hình)", self)
        self.act_read_mode.setShortcut(QKeySequence("F11"))
        self.act_read_mode.triggered.connect(self.action_read_mode)
        view_menu.addAction(self.act_read_mode)
        view_menu.addSeparator()
        self.act_toggle_theme = QAction("Đổi giao diện Sáng / Tối", self)
        self.act_toggle_theme.setShortcut(QKeySequence("Ctrl+Shift+T"))
        self.act_toggle_theme.triggered.connect(self.action_toggle_theme)
        view_menu.addAction(self.act_toggle_theme)

        tools_menu = self.main_menu.addMenu("Công cụ && Chuyển đổi")
        self.act_palette = QAction("Tìm công cụ và lệnh...", self)
        self.act_palette.setShortcut(QKeySequence("Ctrl+K"))
        self.act_palette.triggered.connect(lambda: self.action_command_palette(""))
        tools_menu.addAction(self.act_palette)
        act_find = QAction("Tìm kiếm trong PDF...", self)
        act_find.setShortcut(QKeySequence.StandardKey.Find)
        act_find.triggered.connect(lambda: self._with_active_tab(lambda t: t.focus_search()))
        tools_menu.addAction(act_find)
        act_extract_txt = QAction("Trích xuất văn bản trang hiện tại...", self)
        act_extract_txt.setShortcut(QKeySequence("Ctrl+T"))
        act_extract_txt.triggered.connect(self.action_extract_current_page_text)
        tools_menu.addAction(act_extract_txt)
        tools_menu.addSeparator()
        self.act_nd30_check = QAction("Kiểm tra thể thức Nghị định 30...", self)
        self.act_nd30_check.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.act_nd30_check.triggered.connect(lambda: self.run_tool("nd30_check"))
        tools_menu.addAction(self.act_nd30_check)
        act_nd30_convert = QAction("Chuyển sang Word chuẩn NĐ30...", self)
        act_nd30_convert.triggered.connect(lambda: self.run_tool("pdf_to_word_nd30"))
        tools_menu.addAction(act_nd30_convert)
        act_verify = QAction("Kiểm chứng DOCX với PDF (MS Word)...", self)
        act_verify.triggered.connect(lambda: self.run_tool("verify_docx"))
        tools_menu.addAction(act_verify)
        tools_menu.addAction(self.act_convert)

        edit_menu = self.main_menu.addMenu("Chỉnh sửa PDF")
        self.act_edit_mode = QAction("Chế độ chỉnh sửa && chú thích", self)
        self.act_edit_mode.setShortcut(QKeySequence("Ctrl+E"))
        self.act_edit_mode.triggered.connect(lambda: self.run_tool("edit_pdf"))
        edit_menu.addAction(self.act_edit_mode)
        self.act_undo = QAction("Hoàn tác chú thích", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(lambda: self._with_active_tab(lambda t: t.annot_controller.undo()))
        edit_menu.addAction(self.act_undo)
        self.act_redo = QAction("Làm lại chú thích", self)
        self.act_redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.act_redo.triggered.connect(lambda: self._with_active_tab(lambda t: t.annot_controller.redo()))
        edit_menu.addAction(self.act_redo)
        act_annots = QAction("Danh sách chú thích", self)
        act_annots.triggered.connect(lambda: self.run_tool("comments"))
        edit_menu.addAction(act_annots)
        edit_menu.addSeparator()
        self.act_organize = QAction("Sắp xếp && cắt ghép trang...", self)
        self.act_organize.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.act_organize.triggered.connect(lambda: self.run_tool("organize"))
        edit_menu.addAction(self.act_organize)
        self.act_combine = QAction("Ghép tệp PDF...", self)
        self.act_combine.setShortcut(QKeySequence("Ctrl+Shift+M"))
        self.act_combine.triggered.connect(lambda: self.run_tool("combine"))
        edit_menu.addAction(self.act_combine)
        act_split = QAction("Tách tệp PDF...", self)
        act_split.triggered.connect(lambda: self.run_tool("split"))
        edit_menu.addAction(act_split)
        act_extract = QAction("Trích trang...", self)
        act_extract.triggered.connect(lambda: self.run_tool("extract_pages"))
        edit_menu.addAction(act_extract)
        edit_menu.addSeparator()
        self.act_save = QAction("Lưu thay đổi", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self.action_save)
        edit_menu.addAction(self.act_save)
        self.act_save_as = QAction("Lưu thành tệp mới...", self)
        self.act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_save_as.triggered.connect(self.action_save_as)
        edit_menu.addAction(self.act_save_as)
        act_flat = QAction("Xuất bản làm phẳng chú thích...", self)
        act_flat.triggered.connect(self.action_export_flattened)
        edit_menu.addAction(act_flat)

        help_menu = self.main_menu.addMenu("Trợ giúp")
        act_about = QAction(f"Giới thiệu {__app_name__}...", self)
        act_about.triggered.connect(self.action_show_about)
        help_menu.addAction(act_about)
        help_menu.addSeparator()
        self.updater.add_menu_actions(help_menu)

        # Menu nằm trong nút «☰ Menu» nên phải gắn hành động vào cửa sổ để phím tắt hoạt động
        for menu in (file_menu, view_menu, tools_menu, edit_menu, help_menu):
            self.addActions([a for a in menu.actions() if not a.isSeparator() and a.menu() is None])
        self.menuBar().setVisible(False)

    # ─── Tầng 1: Dải tiêu đề & tab tài liệu ────────────────────────────────

    def _build_title_strip(self) -> QFrame:
        strip = QFrame()
        strip.setObjectName("titleStrip")
        lay = QHBoxLayout(strip)
        lay.setContentsMargins(8, 4, 10, 0)
        lay.setSpacing(4)

        self.btn_home = QPushButton("⌂")
        self.btn_home.setObjectName("homeTabBtn")
        self.btn_home.setCheckable(True)
        self.btn_home.setToolTip("Trang chủ (Alt+Home)")
        self.btn_home.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_home.clicked.connect(self.action_go_home)
        lay.addWidget(self.btn_home)

        self.doc_tab_bar = QTabBar()
        self.doc_tab_bar.setObjectName("docTabBar")
        self.doc_tab_bar.setTabsClosable(True)
        self.doc_tab_bar.setMovable(True)
        self.doc_tab_bar.setDocumentMode(True)
        self.doc_tab_bar.setExpanding(False)
        self.doc_tab_bar.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.doc_tab_bar.setDrawBase(False)
        self.doc_tab_bar.tabBarClicked.connect(self._on_header_tab_clicked)
        self.doc_tab_bar.currentChanged.connect(self._on_header_tab_changed)
        self.doc_tab_bar.tabCloseRequested.connect(self.close_tab_at)
        self.doc_tab_bar.tabMoved.connect(self._on_header_tab_moved)
        lay.addWidget(self.doc_tab_bar, 0, Qt.AlignmentFlag.AlignBottom)

        btn_open = QPushButton("＋  Mở")
        btn_open.setObjectName("ghostBtn")
        btn_open.setToolTip("Mở tệp PDF (Ctrl+O)")
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.clicked.connect(self.action_open_pdf)
        lay.addWidget(btn_open)
        lay.addStretch(1)

        btn_github = QPushButton("⟨/⟩ GitHub")
        btn_github.setObjectName("ghostBtn")
        btn_github.setToolTip("Mã nguồn, báo lỗi & góp ý trên GitHub")
        btn_github.clicked.connect(lambda: self._open_link(f"https://github.com/{__github_repo__}"))
        lay.addWidget(btn_github)

        btn_help = QPushButton("？")
        btn_help.setObjectName("ghostIconBtn")
        btn_help.setToolTip(f"Giới thiệu {__app_name__}")
        btn_help.clicked.connect(self.action_show_about)
        lay.addWidget(btn_help)

        self.btn_theme_toggle = QPushButton("☀️ Giao diện Sáng")
        self.btn_theme_toggle.setObjectName("themeToggleBtn")
        self.btn_theme_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme_toggle.clicked.connect(self.action_toggle_theme)
        lay.addWidget(self.btn_theme_toggle)
        return strip

    # ─── Tầng 2: Thanh chế độ ──────────────────────────────────────────────

    def _build_mode_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("modeBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)

        btn_menu = QPushButton("☰  Menu")
        btn_menu.setObjectName("ghostBtn")
        btn_menu.setMenu(self.main_menu)
        lay.addWidget(btn_menu)
        lay.addSpacing(10)

        self.mode_buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, label in CATEGORIES:
            b = QPushButton(label)
            b.setObjectName("modeTabBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.set_mode_category(k))
            group.addButton(b)
            lay.addWidget(b)
            self.mode_buttons[key] = b
        self.mode_buttons["all"].setChecked(True)
        # Giữ tên cũ cho các thành phần khác tham chiếu
        self.btn_mode_tools = self.mode_buttons["all"]
        self.btn_mode_tools.setToolTip("Hiện bảng Tất cả công cụ (F3)")
        lay.addStretch(1)

        # Cụm điều khiển tài liệu (chỉ hiện khi đang xem PDF)
        self.doc_controls = QWidget()
        dc = QHBoxLayout(self.doc_controls)
        dc.setContentsMargins(0, 0, 0, 0)
        dc.setSpacing(4)
        self.btn_mode_inspect = QPushButton("📐 Soi bố cục")
        self.btn_mode_inspect.setMinimumWidth(0)
        self.btn_mode_inspect.setObjectName("pillToggleBtn")
        self.btn_mode_inspect.setCheckable(True)
        self.btn_mode_inspect.setChecked(self.settings.show_layout_overlay)
        self.btn_mode_inspect.setToolTip("Bật/Tắt lớp phủ soi khung bố cục & chữ ký số trên trang PDF (F8)")
        self.btn_mode_inspect.toggled.connect(self.action_toggle_layout_overlay)
        dc.addWidget(self.btn_mode_inspect)
        self.btn_prev_page = QPushButton("◀")
        self.btn_prev_page.setObjectName("ghostIconBtn")
        self.btn_prev_page.setToolTip("Trang trước")
        self.btn_prev_page.clicked.connect(self.action_prev_page)
        dc.addWidget(self.btn_prev_page)
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setToolTip("Đi tới trang")
        self.page_spin.valueChanged.connect(self._on_spin_page_changed)
        dc.addWidget(self.page_spin)
        self.total_page_lbl = QLabel("/ 0")
        dc.addWidget(self.total_page_lbl)
        self.btn_next_page = QPushButton("▶")
        self.btn_next_page.setObjectName("ghostIconBtn")
        self.btn_next_page.setToolTip("Trang sau")
        self.btn_next_page.clicked.connect(self.action_next_page)
        dc.addWidget(self.btn_next_page)
        # Thu phóng: chọn nhanh mức hiển thị (nút +/− nằm ở thanh dọc bên phải như PdfCraft)
        self.zoom_combo = QComboBox()
        self.zoom_combo.setToolTip("Mức thu phóng")
        self.zoom_combo.addItem("Vừa ngang", ("fit_width", 100))
        self.zoom_combo.addItem("Vừa trang", ("fit_page", 100))
        for pct in (50, 75, 100, 125, 150, 200, 300):
            self.zoom_combo.addItem(f"{pct}%", ("percent", pct))
        self.zoom_combo.activated.connect(self._on_zoom_combo_activated)
        dc.addWidget(self.zoom_combo)
        lay.addWidget(self.doc_controls)
        lay.addSpacing(8)

        self.toolbar_search_input = QLineEdit()
        self.toolbar_search_input.setObjectName("commandSearch")
        self.toolbar_search_input.setPlaceholderText("🔍 Tìm công cụ & lệnh…  Ctrl+K")
        self.toolbar_search_input.setMinimumWidth(180)
        self.toolbar_search_input.setMaximumWidth(300)
        self.toolbar_search_input.returnPressed.connect(self._on_toolbar_quick_search)
        completer = QCompleter([t.name for t in TOOLS], self.toolbar_search_input)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.activated.connect(self._on_completer_activated)
        self.toolbar_search_input.setCompleter(completer)
        lay.addWidget(self.toolbar_search_input)

        btn_info = QPushButton("ℹ")
        btn_info.setObjectName("ghostIconBtn")
        btn_info.setToolTip("Thuộc tính tài liệu (Ctrl+I)")
        btn_info.clicked.connect(self.action_show_doc_info)
        lay.addWidget(btn_info)

        self.btn_convert_docx = QPushButton("📄 Xuất Word")
        self.btn_convert_docx.setObjectName("primaryConvertBtn")
        self.btn_convert_docx.setToolTip("Chuyển PDF sang Word (.docx) — văn bản hành chính tự dùng chuẩn NĐ30 (Ctrl+Shift+W)")
        self.btn_convert_docx.clicked.connect(self.action_convert_to_docx)
        lay.addWidget(self.btn_convert_docx)
        return bar

    # ─── Thân cửa sổ ───────────────────────────────────────────────────────

    def _build_central_area(self) -> None:
        self.stack = QStackedWidget(self)
        self.home_page = HomePage()
        self.home_page.toolActivated.connect(self.run_tool)
        self.home_page.openRequested.connect(self.action_open_pdf)
        self.home_page.recentActivated.connect(lambda p: self.open_pdf_path(p))
        self.home_page.resumeRequested.connect(self._show_documents)
        self.home_page.linkRequested.connect(self._open_link)
        self.home_page.filesDropped.connect(lambda files: [self.open_pdf_path(f) for f in files])
        self.stack.addWidget(self.home_page)
        # Giữ tên cũ: danh sách gần đây của trang chủ
        self.welcome_recent_list = self.home_page.recent_box
        self.btn_resume_tabs = self.home_page.btn_resume

        self.doc_tabs = QTabWidget()
        self.doc_tabs.setObjectName("docTabs")
        self.doc_tabs.tabBar().hide()  # tab hiển thị ở dải tiêu đề (doc_tab_bar)
        self.doc_tabs.setDocumentMode(True)
        self.doc_tabs.currentChanged.connect(self._on_active_doc_tab_changed)
        self.stack.addWidget(self.doc_tabs)
        self._refresh_welcome_recent_list()

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
        if hasattr(self, "btn_theme_toggle"):
            if normalized == "dark":
                self.btn_theme_toggle.setText("☀️ Giao diện Sáng")
                self.btn_theme_toggle.setToolTip("Đang ở Giao diện Tối — Bấm để chuyển sang Giao diện Sáng (Ctrl+Shift+T)")
            else:
                self.btn_theme_toggle.setText("🌙 Giao diện Tối")
                self.btn_theme_toggle.setToolTip("Đang ở Giao diện Sáng — Bấm để chuyển sang Giao diện Tối (Ctrl+Shift+T)")
        if hasattr(self, "status_theme_lbl"):
            mode_txt = "Sáng (Light)" if normalized == "light" else "Tối (Dark)"
            self.status_theme_lbl.setText(f"Giao diện: {mode_txt}  |  ")
        if hasattr(self, "doc_tabs"):
            for i in range(self.doc_tabs.count()):
                w = self.doc_tabs.widget(i)
                if isinstance(w, PDFDocumentTab):
                    w.viewer.set_canvas_theme(normalized)

    # ─── Điều hướng Trang chủ / Tài liệu ───────────────────────────────────

    def _show_home(self) -> None:
        self.stack.setCurrentWidget(self.home_page)
        self.btn_home.setChecked(True)
        self.doc_controls.setVisible(False)
        self._refresh_welcome_recent_list()
        self.status_doc_lbl.setText(
            f"Trang chủ — {self.doc_tabs.count()} tài liệu đang mở." if self.doc_tabs.count() else
            "Sẵn sàng — Kéo thả tệp PDF vào cửa sổ hoặc bấm Ctrl+O để mở."
        )

    def _show_documents(self) -> None:
        if self.doc_tabs.count() == 0:
            self._show_home()
            return
        self.stack.setCurrentWidget(self.doc_tabs)
        self.btn_home.setChecked(False)
        self.doc_controls.setVisible(True)
        self._sync_toolbar_with_active_tab()

    def set_mode_category(self, category: str) -> None:
        """Chọn chế độ (nhóm công cụ) trên thanh chế độ — lọc bảng công cụ ở Trang chủ & tài liệu."""
        self._mode_category = category
        btn = self.mode_buttons.get(category)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
        self.home_page.catalog.set_category(category)
        self.home_page.catalog.setVisible(True)
        for i in range(self.doc_tabs.count()):
            w = self.doc_tabs.widget(i)
            if isinstance(w, PDFDocumentTab):
                w.set_tool_category(category)
        tab = self.active_tab()
        if tab is not None and self.stack.currentWidget() is self.doc_tabs:
            tab.tools_panel.setVisible(True)
            if category == "edit":
                tab.enter_edit_mode()
            elif category == "read":
                tab.exit_edit_mode()

    def active_tab(self) -> Optional[PDFDocumentTab]:
        if self.doc_tabs.count() == 0:
            return None
        w = self.doc_tabs.currentWidget()
        return w if isinstance(w, PDFDocumentTab) else None

    def _with_active_tab(self, fn: Callable[[PDFDocumentTab], None]) -> None:
        tab = self.active_tab()
        if tab is not None:
            fn(tab)

    def _on_header_tab_clicked(self, index: int) -> None:
        if 0 <= index < self.doc_tabs.count():
            self.doc_tabs.setCurrentIndex(index)
            self._show_documents()

    def _on_header_tab_changed(self, index: int) -> None:
        if 0 <= index < self.doc_tabs.count() and self.doc_tabs.currentIndex() != index:
            self.doc_tabs.setCurrentIndex(index)

    def _on_header_tab_moved(self, from_idx: int, to_idx: int) -> None:
        self.doc_tabs.tabBar().moveTab(from_idx, to_idx)

    # ─── Mở & Quản lý tài liệu ─────────────────────────────────────────────

    def open_pdf_path(self, pdf_path: str | Path, password: Optional[str] = None) -> Optional[PDFDocumentTab]:
        """Mở một tệp PDF vào tab mới (hoặc chuyển tới tab đang mở tệp đó)."""
        path = Path(pdf_path).resolve()
        if not path.exists():
            QMessageBox.warning(self, "Không tìm thấy tệp", f"Tệp không tồn tại:\n{path}")
            return None

        for i in range(self.doc_tabs.count()):
            w = self.doc_tabs.widget(i)
            if isinstance(w, PDFDocumentTab) and w.reader.path == path:
                self.doc_tabs.setCurrentIndex(i)
                self._show_documents()
                return w

        try:
            reader = PDFDocumentReader(path, password=password)
        except PermissionError:
            pwd, ok = QInputDialog.getText(
                self, "Tệp PDF có mật khẩu", f"Nhập mật khẩu để mở '{path.name}':", QLineEdit.EchoMode.Password
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
        tab.set_tool_category(self._mode_category)
        tab.viewer.pageChanged.connect(lambda _p: self._sync_toolbar_with_active_tab())
        tab.viewer.zoomChanged.connect(lambda _z: self._sync_toolbar_with_active_tab())
        tab.extract_page_text_btn.clicked.connect(self.action_extract_current_page_text)
        tab.sidebar_convert_btn.clicked.connect(self.action_convert_to_docx)
        tab.banner_convert_btn.clicked.connect(
            lambda: self.action_convert_to_docx_mode("nd30" if tab.is_admin_document else "auto")
        )
        tab.tool_btn_convert_nd30.clicked.connect(lambda: self.action_convert_to_docx_mode("nd30"))
        tab.tool_btn_nd30_check.clicked.connect(lambda: self.run_tool("nd30_check"))
        tab.tool_btn_convert_hybrid.clicked.connect(lambda: self.action_convert_to_docx_mode("hybrid"))
        tab.tool_btn_convert_exact.clicked.connect(lambda: self.action_convert_to_docx_mode("exact"))
        tab.tool_btn_convert_dialog.clicked.connect(self.action_convert_to_docx)
        tab.tool_btn_extract_text.clicked.connect(self.action_extract_current_page_text)
        tab.tool_btn_doc_info.clicked.connect(self.action_show_doc_info)
        tab.tool_btn_print.clicked.connect(lambda: self.run_tool("print"))
        tab.tool_btn_all_tools.clicked.connect(lambda: self.action_command_palette(""))
        tab.tool_btn_organize.clicked.connect(lambda: self.run_tool("organize"))
        tab.tool_btn_save.clicked.connect(self.action_save)
        tab.edit_toolbar.saveRequested.connect(self.action_save)
        tab.edit_toolbar.organizeRequested.connect(lambda: self.run_tool("organize"))
        tab.modifiedChanged.connect(lambda _m, t=tab: self._update_tab_title(t))
        tab.statusMessage.connect(lambda text: self.statusBar().showMessage(text, 6000))

        safe_tab_title = path.name.replace("&", "&&")
        idx = self.doc_tabs.addTab(tab, safe_tab_title)
        self.doc_tab_bar.blockSignals(True)
        self.doc_tab_bar.insertTab(idx, f"📄 {safe_tab_title}")
        self.doc_tab_bar.setTabToolTip(idx, str(path))
        self.doc_tab_bar.blockSignals(False)
        self.doc_tabs.setTabToolTip(idx, str(path))
        self.doc_tabs.setCurrentIndex(idx)
        self._show_documents()

        self.settings.add_recent_file(path)
        self._refresh_recent_menu()
        self._refresh_welcome_recent_list()
        self._sync_toolbar_with_active_tab()
        return tab

    def close_tab_at(self, index: int, force: bool = False) -> None:
        if not 0 <= index < self.doc_tabs.count():
            return
        w = self.doc_tabs.widget(index)
        if not force and isinstance(w, PDFDocumentTab) and not self._confirm_close_tab(w):
            return
        self.doc_tabs.removeTab(index)
        self.doc_tab_bar.blockSignals(True)
        self.doc_tab_bar.removeTab(index)
        self.doc_tab_bar.blockSignals(False)
        if isinstance(w, PDFDocumentTab):
            w.close_document()
            w.deleteLater()
        if self.doc_tabs.count() == 0:
            self._show_home()
        else:
            self.doc_tab_bar.setCurrentIndex(self.doc_tabs.currentIndex())
        self._refresh_welcome_recent_list()
        self._sync_toolbar_with_active_tab()

    def _on_active_doc_tab_changed(self, index: int) -> None:
        if 0 <= index < self.doc_tab_bar.count() and self.doc_tab_bar.currentIndex() != index:
            self.doc_tab_bar.blockSignals(True)
            self.doc_tab_bar.setCurrentIndex(index)
            self.doc_tab_bar.blockSignals(False)
        self._sync_toolbar_with_active_tab()

    def _sync_toolbar_with_active_tab(self) -> None:
        tab = self.active_tab()
        if tab is None:
            self.page_spin.blockSignals(True)
            self.page_spin.setMaximum(1)
            self.page_spin.setValue(1)
            self.page_spin.blockSignals(False)
            self.total_page_lbl.setText("/ 0 ")
            self.status_zoom_lbl.setText("Thu phóng: --")
            return
        total = tab.reader.page_count
        cur = tab.viewer.current_page
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(1, total))
        self.page_spin.setValue(cur + 1)
        self.page_spin.blockSignals(False)
        self.total_page_lbl.setText(f"/ {total} ")
        if self.stack.currentWidget() is self.doc_tabs:
            pw, ph = tab.reader.get_page_size(cur)
            self.status_doc_lbl.setText(f"{tab.reader.path.name} — Trang {cur + 1}/{total} ({pw:.0f}×{ph:.0f} pt)")
        self.status_zoom_lbl.setText(f"Thu phóng: {tab.viewer.zoom_percent}%")

    # ─── Công cụ ───────────────────────────────────────────────────────────

    def run_tool(self, key: str) -> None:
        """Chạy một công cụ trong danh mục; công cụ chưa có hiển thị thông báo Coming Soon."""
        tool = get_tool(key)
        if tool is None:
            return
        if not tool.ready:
            self._show_toast(f"⏳ {tool.name} — {COMING_SOON_LABEL} (dự kiến {tool.milestone}). Theo dõi tiến độ trên GitHub.")
            return
        if tool.needs_document and self.active_tab() is None:
            self._show_toast(f"Hãy mở một tệp PDF trước khi dùng «{tool.name}».")
            self.action_open_pdf()
            if self.active_tab() is None:
                return
        if self.active_tab() is not None and tool.needs_document:
            self._show_documents()

        handlers: dict[str, Callable[[], None]] = {
            "open": self.action_open_pdf,
            "pdf_to_word_nd30": lambda: self.action_convert_to_docx_mode("nd30"),
            "pdf_to_word_exact": lambda: self.action_convert_to_docx_mode("exact"),
            "pdf_to_word_flow": lambda: self.action_convert_to_docx_mode("hybrid"),
            "nd30_check": self.action_nd30_check,
            "verify_docx": self.action_verify_docx,
            "batch_convert": self.action_batch_convert,
            "layout_inspect": lambda: self._open_inspector(True),
            "sig_inspect": lambda: self._open_inspector(True),
            "search": lambda: self._with_active_tab(lambda t: t.focus_search()),
            "extract_text": self.action_extract_current_page_text,
            "bookmarks": lambda: self._with_active_tab(lambda t: t._on_rail_tab_clicked(1)),
            "read_mode": self.action_read_mode,
            "rotate_view": lambda: self._with_active_tab(lambda t: t.viewer.rotate_current_page(90)),
            "doc_info": self.action_show_doc_info,
            "print": self.action_print,
            "edit_pdf": lambda: self._with_active_tab(lambda t: t.toggle_edit_mode()),
            "highlight_text": lambda: self._with_active_tab(lambda t: t.enter_edit_mode("highlight")),
            "draw_shapes": lambda: self._with_active_tab(lambda t: t.enter_edit_mode("pen")),
            "stamp": lambda: self._with_active_tab(lambda t: t.enter_edit_mode("stamp")),
            "comments": self._open_annotation_panel,
            "organize": lambda: self.action_organize("organize"),
            "combine": lambda: self.action_organize("combine"),
            "split": lambda: self.action_organize("split"),
            "extract_pages": lambda: self.action_organize("extract"),
        }
        fn = handlers.get(key)
        if fn is not None:
            fn()

    def _open_annotation_panel(self) -> None:
        tab = self.active_tab()
        if tab is None:
            return
        tab.enter_edit_mode("note")
        tab.show_annotation_panel()

    # ─── Chỉnh sửa PDF: lưu, sắp xếp & cắt ghép trang ─────────────────────

    def _update_tab_title(self, tab: PDFDocumentTab) -> None:
        idx = self.doc_tabs.indexOf(tab)
        if idx < 0:
            return
        name = tab.reader.path.name.replace("&", "&&")
        mark = "● " if tab.reader.has_unsaved_changes else "📄 "
        self.doc_tab_bar.setTabText(idx, f"{mark}{name}")
        self.doc_tab_bar.setTabToolTip(idx, str(tab.reader.path))
        self.doc_tabs.setTabText(idx, name)
        self.doc_tabs.setTabToolTip(idx, str(tab.reader.path))

    def _save_tab(self, tab: PDFDocumentTab, path: Optional[Path] = None) -> bool:
        signed = tab.reader.has_digital_signature
        try:
            saved = tab.reader.save(path)
        except Exception as exc:
            QMessageBox.critical(
                self, "Không lưu được tệp",
                f"Không ghi được tệp PDF:\n{exc}\n\nTệp có thể đang mở ở chương trình khác hoặc chỉ cho phép đọc — "
                "hãy dùng «Lưu thành tệp mới…» (Ctrl+Shift+S).",
            )
            return False
        tab.after_save()
        self._update_tab_title(tab)
        self.settings.add_recent_file(saved)
        self._refresh_recent_menu()
        note = " — ghi bổ sung, chữ ký số gốc vẫn kiểm tra được" if signed and path is None else ""
        self._show_toast(f"💾 Đã lưu {saved.name}{note}")
        self._sync_toolbar_with_active_tab()
        return True

    def action_save(self) -> None:
        tab = self.active_tab()
        if tab is None:
            return
        if not tab.reader.has_unsaved_changes:
            self._show_toast("Không có thay đổi nào cần lưu.")
            return
        self._save_tab(tab)

    def action_save_as(self) -> None:
        tab = self.active_tab()
        if tab is None:
            return
        src = tab.reader.path
        default = str(src.with_name(f"{src.stem}_da_chinh_sua.pdf"))
        chosen, _ = QFileDialog.getSaveFileName(self, "Lưu thành tệp PDF mới", default, "Tài liệu PDF (*.pdf)")
        if not chosen:
            return
        target = Path(chosen).resolve()
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        if target != src and self._tab_for_path(target) is not None:
            QMessageBox.warning(self, "Tệp đang mở", f"«{target.name}» đang mở ở tab khác — hãy đóng tab đó trước.")
            return
        if tab.reader.has_digital_signature and target != src:
            ok = QMessageBox.question(
                self, "Văn bản có chữ ký số",
                "Lưu thành tệp mới sẽ ghi lại toàn bộ tệp nên chữ ký số gốc không còn kiểm tra được.\n"
                "Muốn giữ chữ ký số, hãy dùng «Lưu» (Ctrl+S — ghi bổ sung vào tệp gốc).\n\nVẫn lưu thành tệp mới?",
            )
            if ok != QMessageBox.StandardButton.Yes:
                return
        self._save_tab(tab, target)

    def action_export_flattened(self) -> None:
        tab = self.active_tab()
        if tab is None:
            return
        src = tab.reader.path
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Xuất bản làm phẳng chú thích", str(src.with_name(f"{src.stem}_lam_phang.pdf")),
            "Tài liệu PDF (*.pdf)",
        )
        if not chosen:
            return
        target = Path(chosen).resolve()
        if self._tab_for_path(target) is not None:
            QMessageBox.warning(self, "Tệp đang mở", f"«{target.name}» đang mở — hãy chọn tên khác.")
            return
        try:
            out = tab.reader.export_flattened(target)
        except Exception as exc:
            QMessageBox.critical(self, "Không xuất được tệp", str(exc))
            return
        self._show_toast(f"Đã xuất bản làm phẳng: {out.name} (chú thích đã vẽ vào nội dung trang)")

    def _tab_for_path(self, path: Path) -> Optional[PDFDocumentTab]:
        target = Path(path).resolve()
        for i in range(self.doc_tabs.count()):
            w = self.doc_tabs.widget(i)
            if isinstance(w, PDFDocumentTab) and w.reader.path == target:
                return w
        return None

    def _confirm_close_tab(self, tab: PDFDocumentTab) -> bool:
        """Hỏi lưu khi đóng tab có chú thích chưa lưu; trả về True nếu được phép đóng."""
        if not tab.reader.has_unsaved_changes:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Lưu thay đổi?")
        box.setText(f"Tài liệu «{tab.reader.path.name}» có chú thích / chỉnh sửa chưa lưu.")
        box.setInformativeText("Lưu vào tệp trước khi đóng?")
        btn_save = box.addButton("Lưu", QMessageBox.ButtonRole.AcceptRole)
        btn_discard = box.addButton("Không lưu", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Huỷ", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_save:
            return self._save_tab(tab)
        return clicked is btn_discard

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - API Qt
        for i in range(self.doc_tabs.count()):
            w = self.doc_tabs.widget(i)
            if isinstance(w, PDFDocumentTab) and w.reader.has_unsaved_changes:
                self.doc_tabs.setCurrentIndex(i)
                self._show_documents()
                if not self._confirm_close_tab(w):
                    event.ignore()
                    return
        self.updater.on_window_closing()
        super().closeEvent(event)

    def action_organize(self, mode: str = "organize") -> None:
        """Mở «Sắp xếp & cắt ghép trang» (mode: organize / combine / split / extract)."""
        tab = self.active_tab()
        sources = []
        files: List[str] = []
        if tab is not None and tab.reader.is_pdf:
            sources.append((str(tab.reader.path), tab.reader.doc, tab.reader.path.name))
        elif mode != "combine":
            chosen, _ = QFileDialog.getOpenFileName(self, "Chọn tệp PDF", "", "Tài liệu PDF (*.pdf)")
            if not chosen:
                return
            files.append(chosen)
        dlg = PageOrganizerDialog(
            self, sources=sources, files=files, mode=mode, theme=self.settings.theme,
            is_locked=lambda p: self._tab_for_path(p) is not None,
            overwrite_handler=self._overwrite_open_document,
        )
        if not dlg.exec():
            return
        paths = dlg.result_paths
        if dlg.result_kind == "file" and paths:
            self._show_toast(f"💾 Đã lưu {paths[0].name} ({paths[0].parent})")
            if dlg.open_results:
                self.open_pdf_path(paths[0])
        elif dlg.result_kind == "parts" and paths:
            folder = paths[0].parent
            self._show_toast(f"✂ Đã tách thành {len(paths)} tệp trong {folder}")
            if dlg.open_results:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _overwrite_open_document(self, path: Path, data: bytes) -> bool:
        """Ghi đè một tệp đang mở trong tab bằng kết quả sắp xếp trang rồi mở lại đúng vị trí."""
        tab = self._tab_for_path(path)
        if tab is None:
            return False
        answer = QMessageBox.question(
            self, "Ghi đè tài liệu đang mở?",
            f"Ghi đè «{path.name}» bằng kết quả sắp xếp / cắt ghép trang?\n"
            "Chú thích chưa lưu của tab đã được gộp vào kết quả.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        idx = self.doc_tabs.indexOf(tab)
        page = tab.viewer.current_page
        self.close_tab_at(idx, force=True)
        target = Path(path).resolve()
        tmp = target.with_name(f".{target.stem}.qtpdfpro-tmp.pdf")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, target)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            QMessageBox.critical(self, "Không ghi được tệp", str(exc))
            self.open_pdf_path(target)
            return False
        new_tab = self.open_pdf_path(target)
        if new_tab is not None:
            cur = self.doc_tabs.indexOf(new_tab)
            if 0 <= idx < self.doc_tabs.count() and cur != idx:
                self.doc_tab_bar.moveTab(cur, idx)
            new_tab.viewer.go_to_page(min(page, new_tab.reader.page_count - 1))
        return True

    def _open_inspector(self, overlay: bool) -> None:
        tab = self.active_tab()
        if tab is None:
            return
        self.action_toggle_layout_overlay(overlay)
        tab.sidebar_tabs.setVisible(True)
        tab.sidebar_tabs.setCurrentIndex(3)
        tab._sync_rail_buttons()

    def _pick_pdf_for_tool(self, title: str) -> Optional[Path]:
        tab = self.active_tab()
        if tab is not None:
            return tab.reader.path
        chosen, _ = QFileDialog.getOpenFileName(self, title, "", "Tài liệu PDF (*.pdf)")
        return Path(chosen) if chosen else None

    def action_nd30_check(self) -> None:
        pdf = self._pick_pdf_for_tool("Chọn văn bản PDF cần kiểm tra thể thức NĐ30")
        if pdf is None:
            return
        dlg = ND30ReportDialog(pdf, parent=self)
        dlg.convertRequested.connect(lambda: self._convert_path_with_mode(pdf, "nd30"))
        dlg.exec()

    def action_verify_docx(self) -> None:
        pdf = self._pick_pdf_for_tool("Chọn tệp PDF gốc")
        if pdf is None:
            return
        default_docx = str(pdf.with_suffix(".docx"))
        docx, _ = QFileDialog.getOpenFileName(
            self, "Chọn tệp Word (.docx) cần kiểm chứng với PDF", default_docx, "Tài liệu Word (*.docx)"
        )
        if not docx:
            return
        if not is_ms_word_available():
            QMessageBox.information(
                self,
                "Cần Microsoft Word",
                "Kiểm chứng bố cục cần Microsoft Word để dựng lại tệp DOCX đúng như khi mở trong Word.",
            )
            return
        LayoutVerifyDialog(pdf, docx, self).exec()

    def action_batch_convert(self) -> None:
        """Mở hộp thoại chuyển đổi hàng loạt nhiều tệp PDF sang Word."""
        BatchConvertDialog(self.settings, parent=self).exec()

    def action_command_palette(self, query: str = "") -> None:
        dlg = CommandPaletteDialog(self, query=query, has_document=self.active_tab() is not None)
        geo = self.geometry()
        dlg.move(geo.x() + (geo.width() - dlg.width()) // 2, geo.y() + 90)
        if dlg.exec() and dlg.selected_key:
            if dlg.selected_key == SEARCH_IN_DOCUMENT_KEY:
                self.toolbar_search_input.setText(dlg.search_text)
                self._on_toolbar_quick_search()
            else:
                self.run_tool(dlg.selected_key)

    def _on_completer_activated(self, text: str) -> None:
        for t in TOOLS:
            if t.name == text:
                QTimer.singleShot(0, lambda: self.toolbar_search_input.clear())
                self.run_tool(t.key)
                return

    def _show_toast(self, text: str, msec: int = 3200) -> None:
        if self._toast is None:
            self._toast = QLabel(self)
            self._toast.setObjectName("toast")
            self._toast.setWordWrap(True)
            self._toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast.setText(text)
        self._toast.setMaximumWidth(560)
        self._toast.adjustSize()
        w = min(560, max(320, self._toast.sizeHint().width() + 24))
        self._toast.resize(w, self._toast.heightForWidth(w) + 20)
        self._toast.move((self.width() - self._toast.width()) // 2, self.height() - self._toast.height() - 48)
        self._toast.show()
        self._toast.raise_()
        self.statusBar().showMessage(text, msec)
        QTimer.singleShot(msec, self._toast.hide)

    def _open_link(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    # ─── Các hành động trên Menu & Thanh công cụ ───────────────────────────

    def action_go_home(self) -> None:
        if self.stack.currentWidget() is self.home_page and self.doc_tabs.count() > 0:
            self._show_documents()
        else:
            self._show_home()

    def action_open_pdf(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn tệp PDF để mở", "", "Tài liệu PDF (*.pdf);;Tất cả các tệp (*.*)")
        for f in files:
            self.open_pdf_path(f)

    def action_convert_to_docx_mode(self, mode: str = "auto") -> None:
        tab = self.active_tab()
        if tab is None:
            chosen, _ = QFileDialog.getOpenFileName(self, "Chọn tệp PDF cần chuyển sang Word (.docx)", "", "Tài liệu PDF (*.pdf)")
            if not chosen:
                return
            tab = self.open_pdf_path(chosen)
            if tab is None:
                return
        self._open_convert_dialog(tab, mode)

    def _convert_path_with_mode(self, pdf: Path, mode: str) -> None:
        tab = self.open_pdf_path(pdf)
        if tab is not None:
            self._open_convert_dialog(tab, mode)

    def action_convert_to_docx(self) -> None:
        self.action_convert_to_docx_mode(self.settings.default_convert_mode)

    def _open_convert_dialog(self, tab: PDFDocumentTab, mode: Optional[str]) -> None:
        dlg = ConvertToDocxDialog(
            pdf_path=tab.reader.path,
            total_pages=tab.reader.page_count,
            current_page=tab.viewer.current_page,
            settings=self.settings,
            parent=self,
            initial_mode=mode,
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
        if not query:
            self.action_command_palette("")
            return
        for t in TOOLS:
            if t.name.lower() == query.lower():
                self.toolbar_search_input.clear()
                self.run_tool(t.key)
                return
        tab = self.active_tab()
        if tab is not None:
            self._show_documents()
            tab.sidebar_tabs.setVisible(True)
            tab.sidebar_tabs.setCurrentIndex(2)
            tab._sync_rail_buttons()
            tab.search_input.setText(query)
            tab.run_search()
        else:
            self.action_command_palette(query)

    def action_toggle_left_tools(self) -> None:
        if self.stack.currentWidget() is self.home_page:
            self.home_page.catalog.setVisible(not self.home_page.catalog.isVisible())
            return
        tab = self.active_tab()
        if tab is not None:
            tab.tools_panel.setVisible(not tab.tools_panel.isVisible())

    def action_toggle_sidebar(self) -> None:
        tab = self.active_tab()
        if tab is not None:
            tab.sidebar_tabs.setVisible(not tab.sidebar_tabs.isVisible())
            tab._sync_rail_buttons()

    def action_read_mode(self) -> None:
        """Chế độ đọc tập trung: ẩn bảng phụ và bật/tắt toàn màn hình."""
        tab = self.active_tab()
        entering = not self.isFullScreen()
        if tab is not None:
            tab.tools_panel.setVisible(not entering)
            tab.sidebar_tabs.setVisible(not entering)
            tab._sync_rail_buttons()
        if entering:
            self.showFullScreen()
            self._show_toast("Chế độ đọc tập trung — nhấn F11 để thoát.")
        else:
            self.showNormal()

    def action_toggle_layout_overlay(self, checked: bool) -> None:
        self.settings.show_layout_overlay = checked
        self.settings.save()
        self.act_toggle_overlay.blockSignals(True)
        self.act_toggle_overlay.setChecked(checked)
        self.act_toggle_overlay.blockSignals(False)
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
        self._apply_theme("light" if self.settings.theme == "dark" else "dark")
        self.settings.save()

    def action_print(self) -> None:
        """Hộp thoại «In tài liệu» cho tab đang mở (in cả chú thích chưa lưu)."""
        tab = self.active_tab()
        if tab is None:
            return
        dlg = PrintDialog(
            tab.reader.doc,
            self.settings,
            doc_name=tab.reader.path.name,
            doc_path=str(tab.reader.path),
            current_page=tab.viewer.current_page,
            theme=self.settings.theme,
            parent=self,
        )
        try:
            if dlg.exec() and dlg.result_message:
                self._show_toast(dlg.result_message)
        finally:
            dlg.deleteLater()  # không giữ bản chụp tài liệu & ảnh xem trước sau khi đóng

    def action_show_doc_info(self) -> None:
        tab = self.active_tab()
        if tab is None:
            self._show_toast("Hãy mở một tệp PDF để xem thuộc tính.")
            return
        DocumentInfoDialog(tab.reader.get_info(), self).exec()

    def action_extract_current_page_text(self) -> None:
        tab = self.active_tab()
        if tab is None:
            return
        cur = tab.viewer.current_page
        txt = tab.reader.get_page_text(cur)
        PageTextDialog(f"Văn bản Trang {cur + 1}/{tab.reader.page_count} — {tab.reader.path.name}", txt, self).exec()

    def action_close_current_tab(self) -> None:
        if self.doc_tabs.count() > 0:
            self.close_tab_at(self.doc_tabs.currentIndex())

    def action_show_about(self) -> None:
        AboutDialog(self).exec()

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
        if hasattr(self, "home_page"):
            self.home_page.set_recent_files(self.settings.recent_files, has_open_docs=self.doc_tabs.count() > 0)

    # ─── Kéo thả tệp PDF vào cửa sổ ────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - API Qt
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - API Qt
        for url in event.mimeData().urls():
            local_file = url.toLocalFile()
            if local_file.lower().endswith(".pdf"):
                self.open_pdf_path(local_file)
        event.acceptProposedAction()
