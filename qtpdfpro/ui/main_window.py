"""Cửa sổ chính và Tab đọc tài liệu PDF của QT PDF Pro."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

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
    """Một tab tài liệu PDF hoàn chỉnh gồm Sidebar 4 ngăn và Khung xem PDF."""

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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        layout.addWidget(self.splitter)

        # 1. Sidebar bên trái (4 ngăn)
        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setMinimumWidth(230)
        self.sidebar_tabs.setMaximumWidth(380)

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
        self.chk_overlay = QCheckBox("Hiển thị khung bố cục trên trang PDF")
        self.chk_overlay.setChecked(self.settings.show_layout_overlay)
        self.chk_overlay.toggled.connect(self._on_overlay_toggled)

        self.layout_info_lbl = QLabel()
        self.layout_info_lbl.setWordWrap(True)
        self.layout_info_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)

        legend_lbl = QLabel(
            "<b>Chú giải màu khung nhận diện:</b><br/>"
            "• <span style='color:#3B82F6;'>■ Xanh dương</span>: Khối văn bản &amp; phông chữ<br/>"
            "• <span style='color:#22C55E;'>■ Xanh lá</span>: Bảng biểu (hàng × cột)<br/>"
            "• <span style='color:#F97316;'>■ Cam</span>: Hình ảnh nhúng<br/>"
            "• <span style='color:#A855F7;'>■ Tím</span>: Đường kẻ / Khung vector"
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

        # 2. Khung vẽ PDF ở giữa/phải
        self.viewer = PDFScrollViewer(self.reader, self)
        self.viewer.set_continuous_mode(self.settings.continuous_scroll)
        self.viewer.set_show_layout_overlay(self.settings.show_layout_overlay)
        self.viewer.set_zoom_mode(
            self.settings.default_zoom_mode, self.settings.default_zoom_percent
        )

        self.splitter.addWidget(self.sidebar_tabs)
        self.splitter.addWidget(self.viewer)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([260, 960])

        self._populate_thumbnails()
        self._populate_toc()
        self.viewer.pageChanged.connect(self._on_viewer_page_changed)
        self._update_inspector(0)

    def close_document(self) -> None:
        self.reader.close()

    def _populate_thumbnails(self) -> None:
        self.thumb_list.blockSignals(True)
        self.thumb_list.clear()
        # Kết xuất hình thu nhỏ nhanh cho tối đa 60 trang đầu, các trang sau dùng nhãn nhẹ
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
            f"• <b>Đồ hoạ Vector</b>: {ly.vector_count} nét vẽ/khung<br/>"
            f"• <b>Phông chữ chuẩn hoá</b>: <code>{fonts_str}</code><br/>"
            f"• <b>Chế độ DOCX khuyên dùng</b>: <span style='color:#22C55E;'>{mode_label}</span>"
        )

    def focus_search(self) -> None:
        self.sidebar_tabs.setVisible(True)
        self.sidebar_tabs.setCurrentIndex(2)
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
    """Cửa sổ chính của ứng dụng QT PDF Pro."""

    def __init__(self, settings: Optional[AppSettings] = None) -> None:
        super().__init__()
        self.settings = settings or AppSettings.load()
        self.setWindowTitle(f"{__app_name__} v{__version__} — Đọc PDF & Chuyển PDF sang DOCX Chuẩn xác")
        self.resize(1280, 820)
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
        self.act_toggle_sidebar = QAction("Ẩn/Hiện thanh bên (Sidebar)", self)
        self.act_toggle_sidebar.setShortcut(QKeySequence("F4"))
        self.act_toggle_sidebar.triggered.connect(self.action_toggle_sidebar)
        view_menu.addAction(self.act_toggle_sidebar)

        self.act_toggle_overlay = QAction("Soi khung bố cục trên trang PDF", self)
        self.act_toggle_overlay.setCheckable(True)
        self.act_toggle_overlay.setChecked(self.settings.show_layout_overlay)
        self.act_toggle_overlay.setShortcut(QKeySequence("F8"))
        self.act_toggle_overlay.toggled.connect(self.action_toggle_layout_overlay)
        view_menu.addAction(self.act_toggle_overlay)

        view_menu.addSeparator()
        self.act_toggle_theme = QAction("Đổi giao diện Sáng / Tối", self)
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

        btn_open = QPushButton("Mở PDF")
        btn_open.setToolTip("Mở tệp tài liệu PDF (Ctrl+O)")
        btn_open.clicked.connect(self.action_open_pdf)
        tb.addWidget(btn_open)

        tb.addSeparator()

        self.btn_prev_page = QPushButton("◀ Trang trước")
        self.btn_prev_page.clicked.connect(self.action_prev_page)
        tb.addWidget(self.btn_prev_page)

        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setPrefix("Trang ")
        self.page_spin.valueChanged.connect(self._on_spin_page_changed)
        tb.addWidget(self.page_spin)

        self.total_page_lbl = QLabel("/ 0 ")
        tb.addWidget(self.total_page_lbl)

        self.btn_next_page = QPushButton("Trang sau ▶")
        self.btn_next_page.clicked.connect(self.action_next_page)
        tb.addWidget(self.btn_next_page)

        tb.addSeparator()

        btn_zoom_out = QPushButton("−")
        btn_zoom_out.setFixedWidth(32)
        btn_zoom_out.setToolTip("Thu nhỏ (Ctrl+-)")
        btn_zoom_out.clicked.connect(lambda: self._with_active_tab(lambda t: t.viewer.zoom_out()))
        tb.addWidget(btn_zoom_out)

        self.zoom_combo = QComboBox()
        self.zoom_combo.setMinimumWidth(135)
        self.zoom_combo.addItem("Vừa chiều ngang", ("fit_width", 100))
        self.zoom_combo.addItem("Vừa trang", ("fit_page", 100))
        for pct in (50, 75, 100, 125, 150, 200, 300):
            self.zoom_combo.addItem(f"{pct}%", ("percent", pct))
        self.zoom_combo.activated.connect(self._on_zoom_combo_activated)
        tb.addWidget(self.zoom_combo)

        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedWidth(32)
        btn_zoom_in.setToolTip("Phóng to (Ctrl++)")
        btn_zoom_in.clicked.connect(lambda: self._with_active_tab(lambda t: t.viewer.zoom_in()))
        tb.addWidget(btn_zoom_in)

        tb.addSeparator()

        btn_rot_left = QPushButton("↺ Xoay trái")
        btn_rot_left.clicked.connect(
            lambda: self._with_active_tab(lambda t: t.viewer.rotate_current_page(-90))
        )
        tb.addWidget(btn_rot_left)

        btn_rot_right = QPushButton("↻ Xoay phải")
        btn_rot_right.clicked.connect(
            lambda: self._with_active_tab(lambda t: t.viewer.rotate_current_page(90))
        )
        tb.addWidget(btn_rot_right)

        btn_search = QPushButton("Tìm kiếm")
        btn_search.setToolTip("Tìm kiếm văn bản trong PDF (Ctrl+F)")
        btn_search.clicked.connect(lambda: self._with_active_tab(lambda t: t.focus_search()))
        tb.addWidget(btn_search)

        tb.addSeparator()

        self.btn_convert_docx = QPushButton("Chuyển sang Word (.docx)")
        self.btn_convert_docx.setObjectName("primaryConvertBtn")
        self.btn_convert_docx.setToolTip(
            "Chuyển đổi PDF sang DOCX chuẩn xác từng thành phần (Ctrl+Shift+W)"
        )
        self.btn_convert_docx.clicked.connect(self.action_convert_to_docx)
        tb.addWidget(self.btn_convert_docx)

    def _build_central_area(self) -> None:
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)

        # Trang chào mừng khi chưa mở tài liệu
        welcome = QWidget()
        w_layout = QVBoxLayout(welcome)
        w_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setMaximumWidth(640)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(14)

        title_lbl = QLabel(
            f"<h1 style='margin-bottom:4px;'>{__app_name__} v{__version__}</h1>"
            "<p style='font-size:14px;color:#9CA3AF;'>"
            "Trình đọc PDF tốc độ cao &amp; Chuyển đổi PDF sang Word (.docx) chuẩn xác từng thành phần."
            "</p>"
        )
        title_lbl.setWordWrap(True)
        card_layout.addWidget(title_lbl)

        features_lbl = QLabel(
            "<b>Điểm nổi bật:</b>"
            "<ul>"
            "<li><b>Đọc PDF mượt mà</b>: Đa tab, mục lục, tìm kiếm tô sáng vị trí, soi khung bố cục trực tiếp trên trang.</li>"
            "<li><b>Chuyển PDF sang DOCX chuẩn xác</b>: Kết hợp tái tạo cấu trúc thông minh (Hybrid Flow) &amp; "
            "Khung vị trí tuyệt đối 1:1 (Exact Frame), kèm Bộ Hậu xử lý Chuẩn xác OpenXML chống lệch dòng, "
            "vỡ bảng hay lỗi phông tiếng Việt.</li>"
            "</ul>"
        )
        features_lbl.setWordWrap(True)
        card_layout.addWidget(features_lbl)

        btn_row = QHBoxLayout()
        open_welcome_btn = QPushButton("Mở tệp PDF để đọc...")
        open_welcome_btn.setMinimumHeight(38)
        open_welcome_btn.clicked.connect(self.action_open_pdf)

        conv_welcome_btn = QPushButton("Chọn tệp PDF chuyển ngay sang Word (.docx)...")
        conv_welcome_btn.setObjectName("primaryConvertBtn")
        conv_welcome_btn.setMinimumHeight(38)
        conv_welcome_btn.clicked.connect(self.action_convert_to_docx)

        btn_row.addWidget(open_welcome_btn)
        btn_row.addWidget(conv_welcome_btn)
        card_layout.addLayout(btn_row)

        card_layout.addWidget(QLabel("<b>Tệp mở gần đây (nhấp đúp để mở):</b>"))
        self.welcome_recent_list = QListWidget()
        self.welcome_recent_list.setMaximumHeight(170)
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
        self.status_zoom_lbl = QLabel("Thu phóng: 100%")
        sb.addWidget(self.status_doc_lbl, 1)
        sb.addPermanentWidget(self.status_zoom_lbl)

    def _apply_theme(self, theme: str) -> None:
        self.settings.theme = theme
        self.setStyleSheet(get_stylesheet(theme))

    def active_tab(self) -> Optional[PDFDocumentTab]:
        if self.doc_tabs.count() == 0:
            return None
        w = self.doc_tabs.currentWidget()
        return w if isinstance(w, PDFDocumentTab) else None

    def _with_active_tab(self, fn) -> None:
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

        # Tránh ký tự & bị biến thành phím tắt mnemonic trên tiêu đề tab
        safe_tab_title = path.name.replace("&", "&&")
        idx = self.doc_tabs.addTab(tab, safe_tab_title)
        self.doc_tabs.setTabToolTip(idx, str(path))
        self.doc_tabs.setCurrentIndex(idx)
        self.stack.setCurrentWidget(self.doc_tabs)

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

        pw, ph = tab.reader.get_page_size(cur)
        self.status_doc_lbl.setText(
            f"{tab.reader.path.name} — Trang {cur + 1}/{total} ({pw:.0f}×{ph:.0f} pt)"
        )
        self.status_zoom_lbl.setText(f"Thu phóng: {tab.viewer.zoom_percent}%")

    # ─── Các hành động trên Menu & Toolbar ──────────────────────────────

    def action_open_pdf(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn tệp PDF để mở",
            "",
            "Tài liệu PDF (*.pdf);;Tất cả các tệp (*.*)",
        )
        for f in files:
            self.open_pdf_path(f)

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

    def action_toggle_sidebar(self) -> None:
        tab = self.active_tab()
        if tab is not None:
            vis = not tab.sidebar_tabs.isVisible()
            tab.sidebar_tabs.setVisible(vis)

    def action_toggle_layout_overlay(self, checked: bool) -> None:
        self.settings.show_layout_overlay = checked
        self.settings.save()
        for i in range(self.doc_tabs.count()):
            w = self.doc_tabs.widget(i)
            if isinstance(w, PDFDocumentTab):
                w.chk_overlay.setChecked(checked)
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
                if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                local_path = url.toLocalFile()
                if local_path.lower().endswith(".pdf"):
                    self.open_pdf_path(local_path)
        event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        while self.doc_tabs.count() > 0:
            self.close_tab_at(0)
        super().closeEvent(event)
