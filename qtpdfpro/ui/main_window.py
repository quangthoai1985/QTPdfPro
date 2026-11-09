"""Cửa sổ chính và Tab đọc tài liệu PDF của QT PDF Pro (bố cục lấy cảm hứng từ PdfCraft)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
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
from qtpdfpro.core import fill_sign
from qtpdfpro.core.converter import is_admin_document
from qtpdfpro.core.ocr_layer import CachedOcrEngine
from qtpdfpro.core.reader import PDFDocumentReader, SearchHit
from qtpdfpro.core.settings import AppSettings
from qtpdfpro.core.word_com_bridge import is_ms_word_available
from qtpdfpro.ui.annotation_tools import (
    TOOL_BY_KEY,
    AnnotationController,
    AnnotationListPanel,
    EditToolbar,
    FlowLayout,
)
from qtpdfpro.ui.batch_dialog import BatchConvertDialog
from qtpdfpro.ui.command_palette import SEARCH_IN_DOCUMENT_KEY, CommandPaletteDialog
from qtpdfpro.ui.convert_dialog import ConvertToDocxDialog
from qtpdfpro.ui.dialogs import AboutDialog, DocumentInfoDialog, PageTextDialog
from qtpdfpro.ui.home_page import HomePage
from qtpdfpro.ui.nd30_dialog import LayoutVerifyDialog, ND30ReportDialog
from qtpdfpro.ui.ocr_dialog import OcrDialog, OcrModelController
from qtpdfpro.ui.organizer_dialog import PageOrganizerDialog
from qtpdfpro.ui.pdf_canvas import PDFScrollViewer
from qtpdfpro.ui.print_dialog import PrintDialog
from qtpdfpro.ui.signature_dialog import SignatureCreateDialog, SignatureManagerDialog
from qtpdfpro.ui.ocr_layer_service import OcrLayerService, shared_ocr_engine
from qtpdfpro.ui.text_select_tool import TextSelectTool
from qtpdfpro.ui.pdf_tools_dialog import PDF_TOOL_DIALOGS
from qtpdfpro.ui import commands, icons
from qtpdfpro.ui.theme import get_stylesheet, theme_tokens
from qtpdfpro.ui.tool_catalog import CATEGORIES, COMING_SOON_LABEL, get_tool
from qtpdfpro.ui.default_app import DefaultAppController
from qtpdfpro.ui.update_dialog import UpdateController

# Ô ảnh thu nhỏ ở ngăn «Trang» (px logic); số ảnh kết xuất mỗi lượt trước khi trả quyền cho vòng lặp sự kiện
THUMB_BOX_W, THUMB_BOX_H = 96, 132
THUMB_BATCH = 4
POINTER_MODES = ("select", "hand")  # chuột trái trên khung đọc: chọn chữ (V) | bàn tay kéo cuộn (H)

# Lệnh mà `QAction` tự mang hành vi (bật/tắt hoặc hành động của bộ cập nhật / trình xem mặc định): bấm / phím tắt
# không đi qua `run_command`; `run_command(khoá)` (Ctrl+K…) gọi `QAction.trigger()`.
_ACTION_DRIVEN_COMMANDS = frozenset(
    {"layout_overlay", "check_update", "auto_check_updates", "auto_download_updates", "default_app"})
# Khoá cũ của `tool_catalog` (Trang chủ, cột trái, thanh công cụ nhanh — còn tới Task 4/8) → khoá lệnh mới
_LEGACY_TOOL_KEYS = {
    "pdf_to_word_nd30": "convert_word_nd30", "pdf_to_word_exact": "convert_word_exact",
    "pdf_to_word_flow": "convert_word_flow", "select_text": "pointer_select", "hand_tool": "pointer_hand",
    "search": "find", "rotate_view": "rotate_right", "edit_pdf": "edit_mode", "highlight_text": "annot.highlight",
    "draw_shapes": "annot.pen", "stamp": "annot.stamp",
}

# Thanh công cụ nhanh khi xem tài liệu (thay cho cột trái): nút theo chế độ đang chọn trên thanh chế độ.
# Mỗi mục = (nhãn ngắn, khoá công cụ trong tool_catalog | lệnh riêng bắt đầu bằng «:», chú thích khi trỏ chuột).
STRIP_COMMAND_TIPS = {
    ":rotate_left": "Xoay trang hiện tại sang trái 90° khi xem",
    ":convert_dialog": "Tuỳ chỉnh xuất DOCX — chọn trang, chế độ, chính sách NĐ30, kiểm chứng (Ctrl+Shift+W)",
}
STRIP_TOOLS: dict[str, list[tuple[str, str]]] = {
    "all": [
        ("🏛️ Word NĐ30", "pdf_to_word_nd30"), ("✅ Kiểm tra NĐ30", "nd30_check"),
        ("✏️ Chỉnh sửa", "edit_pdf"), ("🧩 Sắp xếp trang", "organize"), ("🗜️ Nén", "compress"),
        ("💧 Dấu nước", "watermark"), ("🔢 Số trang", "page_numbers"), ("🔐 Mật khẩu", "protect"),
        ("🖨️ In", "print"),
    ],
    "read": [
        ("Aa Chọn chữ", "select_text"), ("🔎 Tìm kiếm", "search"), ("📋 Trích văn bản", "extract_text"), ("📑 Mục lục", "bookmarks"),
        ("↺ Xoay trái", ":rotate_left"), ("↻ Xoay phải", "rotate_view"), ("📖 Đọc tập trung", "read_mode"),
        ("ℹ️ Thuộc tính", "doc_info"), ("🖨️ In", "print"),
    ],
    "convert": [
        ("🏛️ Word NĐ30", "pdf_to_word_nd30"), ("📐 Word giữ vị trí 1:1", "pdf_to_word_exact"),
        ("📝 Word dòng chảy", "pdf_to_word_flow"), ("🔤 OCR tiếng Việt", "ocr"), ("⚙️ Tuỳ chỉnh xuất…", ":convert_dialog"),
        ("✅ Kiểm tra NĐ30", "nd30_check"), ("🔬 Kiểm chứng DOCX", "verify_docx"),
        ("🗂️ Hàng loạt", "batch_convert"),
    ],
    "edit": [
        ("🧩 Sắp xếp trang", "organize"), ("🧷 Ghép tệp", "combine"), ("✂️ Tách tệp", "split"),
        ("📤 Trích trang", "extract_pages"), ("🗜️ Nén", "compress"), ("💧 Dấu nước", "watermark"),
        ("🔢 Số trang", "page_numbers"),
    ],
    "fill": [
        ("🖋️ Điền && Ký", "fill_sign"), ("✍️ Thư viện chữ ký", "signatures"), ("🧾 Biểu mẫu PDF", "forms"),
        ("🖨️ In", "print"),
    ],
    "sign": [
        ("🛡️ Soi chữ ký số", "sig_inspect"), ("🔐 Đặt mật khẩu", "protect"), ("🔓 Gỡ mật khẩu", "unlock"),
        ("✍️ Ký số", "sign_pdf"), ("🔏 Xác thực chữ ký", "verify_signature"),
    ],
}


class PDFDocumentTab(QWidget):
    """Một tab tài liệu PDF hoàn chỉnh theo bố cục 3 cột kiểu PdfCraft:
    - Cột trái: Bảng 'Tất cả công cụ' (All Tools) có ô lọc nhanh & thẻ thao tác 1 chạm — mặc định ẩn
      (công cụ nằm trên thanh công cụ nhanh của `MainWindow`), nút «◧ Bảng công cụ» bật lại theo `settings.show_tools_panel`
    - Cột giữa: Thanh thông báo chữ ký số/con dấu + Khung vẽ PDF tốc độ cao (PDFScrollViewer)
    - Cột phải: Ngăn thông tin 5 tab (Trang, Mục lục, Tìm kiếm, Soi bố cục, Chú thích) + Thanh điều khiển dọc
    - Chế độ «Chỉnh sửa» (Ctrl+E): thanh công cụ chú thích phía trên khung đọc (tô màu, đánh dấu, vẽ, chèn chữ…)
    """

    modifiedChanged = Signal(bool)
    editModeChanged = Signal(bool)
    statusMessage = Signal(str)
    toolRequested = Signal(str)  # khoá công cụ trong tool_catalog (MainWindow.run_command)
    toolsPanelHideRequested = Signal()  # nút ✕ của cột công cụ → MainWindow ẩn ở mọi tab & ghi nhớ
    pointerModeRequested = Signal(str)  # "select" | "hand" (phím V/H, nút thanh dọc, menu) → MainWindow áp mọi tab
    saveSearchableRequested = Signal()  # tài liệu ảnh quét → «Lưu thành PDF tìm kiếm được» (MainWindow)

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
        self.banner_ocr_btn = QPushButton("💾 Lưu thành PDF tìm kiếm được")
        self.banner_ocr_btn.setObjectName("primaryConvertBtn")
        self.banner_ocr_btn.setToolTip("Thêm lớp chữ ẩn (OCR) vào bản sao của tệp: tìm kiếm và chọn chữ được ở mọi "
                                       "trình đọc PDF. Trang đã nhận dạng khi xem không phải nhận dạng lại.")
        self.banner_ocr_btn.setVisible(False)
        self.banner_ocr_btn.clicked.connect(self.saveSearchableRequested)
        banner_layout.addWidget(self.banner_info_lbl, 1)
        banner_layout.addWidget(self.banner_convert_btn)
        banner_layout.addWidget(self.banner_ocr_btn)
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
        # Chế độ «Điền & Ký»: cùng bộ điều khiển, thanh công cụ riêng (gõ chữ, ✓ ✕ ● ─, ngày, chữ ký)
        self.fill_toolbar = EditToolbar(self.annot_controller, self.viewer, self, toolset="fill")
        self.fill_toolbar.setVisible(False)
        self.fill_toolbar.exitRequested.connect(self.exit_edit_mode)
        self.fill_toolbar.manageSignaturesRequested.connect(self.open_signature_library)
        self.annot_controller.signatureNeeded.connect(self._create_signature_for_placement)
        self._toolset = "edit"
        # Công cụ «Chọn chữ» (V) / «Bàn tay» (H) khi không ở chế độ chỉnh sửa — như Acrobat.
        # Trang ảnh quét: `ocr_layer` nhận dạng ngầm trang đang xem thành lớp chữ tạm (khi máy đã có bộ mô hình).
        self.ocr_layer = OcrLayerService(self.reader, parent=self)
        self.text_select = TextSelectTool(
            self.reader, models_provider=lambda: getattr(self.window(), "ocr_models", None), parent=self,
            layer=self.ocr_layer,
        )
        self.text_select.message.connect(self.statusMessage)
        self.text_select.highlightRequested.connect(self._highlight_selection)
        self.text_select.searchRequested.connect(self._search_for_text)
        self.text_select.pointerModeRequested.connect(self.pointerModeRequested)
        self.text_select.saveSearchableRequested.connect(self.saveSearchableRequested)
        self.ocr_layer.message.connect(self.statusMessage)
        self.ocr_layer.pageReady.connect(self._on_ocr_layer_ready)
        self.ocr_layer.busyChanged.connect(lambda: self.viewer.widget().update())
        self.is_scanned_document = False
        self._pointer_mode = settings.pointer_mode if settings.pointer_mode in POINTER_MODES else "select"
        self._pointer_shortcuts: List[QShortcut] = []
        for seq, mode in (("V", "select"), ("H", "hand")):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda m=mode: self.pointerModeRequested.emit(m))
            self._pointer_shortcuts.append(sc)
        center_layout.addWidget(self.edit_toolbar)
        center_layout.addWidget(self.fill_toolbar)
        center_layout.addWidget(self.viewer, 1)

        # ─── 3. CỘT PHẢI: Ngăn 4 tab (Trang, Mục lục, Tìm kiếm, Soi bố cục) ──
        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setMinimumWidth(240)
        self.sidebar_tabs.setMaximumWidth(390)

        # Ngăn 1: Trang thu nhỏ (Thumbnails) — ảnh kết xuất dần theo vùng đang nhìn (`_render_visible_thumbnails`)
        self.thumb_list = QListWidget()
        self.thumb_list.setIconSize(QSize(THUMB_BOX_W, THUMB_BOX_H))
        self.thumb_list.setSpacing(6)
        self.thumb_list.setUniformItemSizes(True)
        self.thumb_list.currentRowChanged.connect(self._on_thumb_selected)
        self.thumb_list.itemClicked.connect(self._on_thumb_clicked)
        self.thumb_list.verticalScrollBar().valueChanged.connect(lambda _v: self._schedule_thumbnails())
        self.thumb_list.viewport().installEventFilter(self)
        self._thumb_done: set[int] = set()
        self._thumb_placeholders: dict[tuple[int, int], QIcon] = {}
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(0)
        self._thumb_timer.timeout.connect(self._render_visible_thumbnails)
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

        # Ngăn 4: Soi bố cục (Layout Inspector) — chỉ phân tích trang khi ngăn đang hiện (`_refresh_inspector`)
        inspector_panel = QWidget()
        self.inspector_panel = inspector_panel
        self._inspector_page: Optional[int] = None  # trang đang hiển thị trong ngăn (None = cần phân tích lại)
        inspector_panel.installEventFilter(self)
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

        # Mở tệp nhanh: không phân tích bố cục mọi trang lúc mở. Thanh thông báo tính sau khi tab đã hiện
        # (`_analyze_document`), bảng biểu dò dần từng trang lúc rảnh (`_scan_tables_step`).
        self.signature_banner.setVisible(False)
        self._banner_sigs = 0
        self._banner_tables = 0
        self._table_scan_next = 0
        self._analysis_timer = QTimer(self)
        self._analysis_timer.setSingleShot(True)
        self._analysis_timer.setInterval(30)
        self._analysis_timer.timeout.connect(self._analyze_document)
        self._table_scan_timer = QTimer(self)
        self._table_scan_timer.setInterval(15)
        self._table_scan_timer.timeout.connect(self._scan_tables_step)

        self._populate_thumbnails()
        self._populate_toc()
        self.viewer.pageChanged.connect(self._on_viewer_page_changed)
        self.viewer.zoomChanged.connect(self._on_viewer_zoom_changed)
        self.sidebar_tabs.currentChanged.connect(self._sync_rail_buttons)
        self.sidebar_tabs.currentChanged.connect(lambda _i: self._refresh_annotation_list_if_visible())
        self._sync_rail_status()
        self._sync_rail_buttons()
        self._apply_pointer_mode()
        self._analysis_timer.start()

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
        btn_hide_tools.clicked.connect(self.toolsPanelHideRequested)
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

        body_layout.addWidget(self._make_section_label("ĐIỀN & KÝ", "fill"))
        self.tool_btn_fill = self._make_tool_card(
            "🖋️ Điền && Ký (Ctrl+Shift+F)\nGõ chữ vào dòng chấm, ✓ ✕, ngày", category="fill"
        )
        self.tool_btn_sign = self._make_tool_card("✍️ Ký tên\nChữ ký vẽ tay, gõ tên hoặc ảnh", category="fill")
        self.tool_btn_fill.clicked.connect(lambda: self.enter_fill_mode())
        self.tool_btn_sign.clicked.connect(lambda: self.enter_fill_mode("fill_sign"))
        body_layout.addWidget(self.tool_btn_fill)
        body_layout.addWidget(self.tool_btn_sign)

        # Công cụ văn phòng & bảo mật: thẻ phát `toolRequested` → MainWindow.run_command mở hộp thoại tương ứng
        self.office_tool_buttons: dict[str, QPushButton] = {}
        office_sections = [
            ("CÔNG CỤ VĂN PHÒNG", "edit", [
                ("compress", "🗜️ Nén PDF\nNhẹ · Vừa · Mạnh, báo dung lượng"),
                ("watermark", "💧 Đóng dấu nước\nBẢN SAO, MẬT… · độ mờ, góc xoay"),
                ("page_numbers", "🔢 Đánh số trang\n6 vị trí · mẫu chuẩn NĐ30"),
            ]),
            ("BẢO MẬT", "sign", [
                ("protect", "🔐 Đặt mật khẩu\nAES-256 · quyền in / sao chép / sửa"),
                ("unlock", "🔓 Gỡ mật khẩu\nKhi biết mật khẩu"),
            ]),
        ]
        for title, cat, cards in office_sections:
            body_layout.addWidget(self._make_section_label(title, cat))
            for key, text in cards:
                btn = self._make_tool_card(text, category=cat)
                btn.clicked.connect(lambda _c=False, k=key: self.toolRequested.emit(k))
                self.office_tool_buttons[key] = btn
                body_layout.addWidget(btn)

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
        """Lọc thẻ công cụ theo chế độ chọn trên thanh chế độ (all/read/convert/edit/fill/sign)."""
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

        # Chế độ con trỏ: Chọn chữ (V) / Bàn tay (H)
        self.pointer_btns: dict[str, QPushButton] = {}
        group = QButtonGroup(rail)
        group.setExclusive(True)
        for mode, label, tip in (
            ("select", "Aa\nChọn", "<b>Chọn chữ (V)</b><br/>Kéo qua chữ để chọn rồi Ctrl+C; kéo từ chỗ trống để chọn "
             "theo khung. Trang ảnh quét: kéo khung quanh chữ để nhận dạng (OCR).<br/>Giữ Space để tạm kéo cuộn."),
            ("hand", "✋\nTay", "<b>Bàn tay (H)</b><br/>Kéo để cuộn trang."),
        ):
            btn = QPushButton(label)
            btn.setObjectName("railIconBtn")
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _c=False, m=mode: self.pointerModeRequested.emit(m))
            group.addButton(btn)
            rlayout.addWidget(btn)
            self.pointer_btns[mode] = btn
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("railSeparator")
        rlayout.addWidget(sep)

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

    def _analyze_document(self) -> None:
        """Chạy một lần ngay sau khi tab hiện: đếm chữ ký số / con dấu (nhanh) + nhận diện văn bản hành chính
        ở trang đầu. Không phải văn bản hành chính và không có chữ ký → dò bảng biểu dần từng trang."""
        if self.reader.is_closed:
            return
        self._banner_sigs = self.reader.count_form_widgets()
        try:
            # Trang đầu không có lớp chữ (ảnh quét) thì không thể nhận ra Quốc hiệu – Tiêu ngữ: bỏ qua bước
            # nhận diện (nó còn mã hoá PNG cả ảnh quét ~0,3 s chỉ để rồi trả False).
            self.is_admin_document = (
                self.reader.page_count > 0
                and self.reader.page_has_text(0)
                and is_admin_document(self.reader.doc, 0)
            )
        except Exception:
            self.is_admin_document = False
        self.is_scanned_document = (
            not self.is_admin_document and self.reader.page_count > 0 and self.ocr_layer.is_scanned(0)
        )
        self._layer_armed = True  # từ giờ đổi trang / bật Chọn chữ mới xin nhận dạng ngầm (không làm chậm lúc mở)
        self._update_document_banner()
        if self.is_scanned_document:
            self._request_ocr_layer()  # máy đã có bộ mô hình → nhận dạng ngầm trang đang xem ngay
        elif not self.is_admin_document and not self._banner_sigs and self.reader.page_count > 0:
            self._table_scan_next = 0
            self._table_scan_timer.start()

    def _request_ocr_layer(self) -> None:
        """Trang đang xem là ảnh quét & đang ở công cụ Chọn chữ → nhận dạng ngầm (+ trang kế)."""
        if self._pointer_mode == "select" and not self.edit_mode and not self.reader.is_closed:
            self.ocr_layer.request(self.viewer.current_page)

    def _on_ocr_layer_ready(self, page_index: int) -> None:
        self.text_select.on_layer_ready(page_index)
        self.viewer.widget().update()

    def _scan_tables_step(self) -> None:
        """Dò bảng biểu một trang mỗi lượt (lúc rảnh) để thanh thông báo không làm chậm việc mở tệp."""
        if self.reader.is_closed or self._table_scan_next >= self.reader.page_count:
            self._table_scan_timer.stop()
            return
        try:
            tables = self.reader.quick_table_count(self._table_scan_next)
        except Exception:
            tables = 0
        self._table_scan_next += 1
        if tables:
            self._banner_tables += tables
            self._update_document_banner()

    def wait_for_document_analysis(self) -> None:
        """Chạy hết phần phân tích nền ngay (bài kiểm thử / khi cần kết quả thanh thông báo)."""
        if self._analysis_timer.isActive():
            self._analysis_timer.stop()
            self._analyze_document()
        while self._table_scan_timer.isActive():
            self._scan_tables_step()

    def _update_document_banner(self) -> None:
        total_sigs = self._banner_sigs
        total_tables = self._banner_tables
        self.banner_ocr_btn.setVisible(self.is_scanned_document)
        self.banner_convert_btn.setVisible(not self.is_scanned_document)

        if self.is_scanned_document:
            self.banner_info_lbl.setText(
                "📷 <b>Tài liệu ảnh quét</b> — công cụ Chọn chữ (V) nhận dạng chữ ngay trên máy để chọn &amp; sao chép; "
                "lưu thành PDF tìm kiếm được để tìm kiếm và chọn chữ ở mọi trình đọc PDF."
            )
            self.signature_banner.setVisible(True)
        elif self.is_admin_document:
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
        for timer in (self._analysis_timer, self._table_scan_timer, self._thumb_timer):
            timer.stop()
        self.text_select.cancel()
        self.ocr_layer.cancel()
        self.viewer.set_interaction(None)
        self.reader.close()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (tên hàm Qt)
        etype = event.type()
        if etype not in (QEvent.Type.Resize, QEvent.Type.Show) or not hasattr(self, "_analysis_timer"):
            return super().eventFilter(obj, event)  # sự kiện lúc đang dựng tab → bỏ qua
        if obj is self.thumb_list.viewport():
            self._schedule_thumbnails()
        elif obj is self.inspector_panel and etype == QEvent.Type.Show:
            QTimer.singleShot(0, self._refresh_inspector)
        return super().eventFilter(obj, event)

    # ─── Chế độ chỉnh sửa (chú thích) ─────────────────────────────────────

    @property
    def edit_mode(self) -> bool:
        return self.viewer.interaction is self.annot_controller

    # ─── Chế độ con trỏ: Chọn chữ / Bàn tay ───────────────────────────────

    @property
    def pointer_mode(self) -> str:
        return self._pointer_mode

    def set_pointer_mode(self, mode: str) -> None:
        """«select» = chuột trái chọn chữ (công cụ `text_select`), «hand» = chuột trái kéo cuộn trang.
        Đang ở chế độ chỉnh sửa thì chỉ ghi nhớ, áp dụng khi thoát."""
        if mode not in POINTER_MODES:
            return
        self._pointer_mode = mode
        if mode == "hand":
            self.text_select.clear_selection()
        self._apply_pointer_mode()

    def _apply_pointer_mode(self) -> None:
        for mode, btn in self.pointer_btns.items():
            btn.setChecked(mode == self._pointer_mode)
            btn.setEnabled(not self.edit_mode)
        for sc in self._pointer_shortcuts:
            sc.setEnabled(not self.edit_mode)  # V / H của thanh chỉnh sửa dùng cho công cụ khác
        if self.edit_mode:
            return
        self.viewer.set_interaction(self.text_select if self._pointer_mode == "select" else None)
        if self._pointer_mode == "select" and getattr(self, "_layer_armed", False):
            self._request_ocr_layer()

    def _highlight_selection(self, page_index: int, rects: list) -> None:
        """Menu chuột phải «Tô sáng vùng chọn» của công cụ Chọn chữ."""
        if page_index is None or not rects or not self.reader.is_pdf:
            return
        try:
            ses = self.annot_controller.session
            ses.add_markup(page_index, "highlight", rects, self.annot_controller.style("highlight").copy())
        except Exception as exc:
            self.statusMessage.emit(f"Không tô sáng được: {exc}")
            return
        self._on_annotations_changed(page_index)
        self.statusMessage.emit(f"Đã tô sáng {len(rects)} dòng chữ — Ctrl+Z để hoàn tác, Ctrl+S để lưu.")

    def _search_for_text(self, text: str) -> None:
        self.sidebar_tabs.setVisible(True)
        self.sidebar_tabs.setCurrentIndex(2)
        self._sync_rail_buttons()
        self.search_input.setText(text)
        self.run_search()

    @property
    def toolset(self) -> str:
        """"edit" (Chỉnh sửa) hoặc "fill" (Điền & Ký) — bộ công cụ đang hiện khi ở chế độ chỉnh sửa."""
        return self._toolset

    @property
    def active_toolbar(self) -> EditToolbar:
        return self.fill_toolbar if self._toolset == "fill" else self.edit_toolbar

    def enter_edit_mode(self, tool: Optional[str] = None, toolset: str = "edit") -> None:
        """Bật thanh công cụ chú thích; `tool` chọn sẵn công cụ (vd "highlight", "stamp").
        `toolset="fill"` bật thanh «Điền & Ký» thay cho thanh «Chỉnh sửa»."""
        if not self.reader.is_pdf:
            self.statusMessage.emit("Chỉ chỉnh sửa được tệp PDF.")
            return
        was = self.edit_mode
        switched = toolset != self._toolset
        self._toolset = toolset
        for bar in (self.edit_toolbar, self.fill_toolbar):
            on = bar is self.active_toolbar
            bar.set_shortcuts_enabled(on)
            bar.setVisible(on)
        current = self.annot_controller.tool
        group = TOOL_BY_KEY[current].group if current in TOOL_BY_KEY else "edit"
        if tool:
            self.annot_controller.set_tool(tool)
        elif group not in (toolset, "both"):  # công cụ của bộ kia → chọn công cụ đầu tiên của bộ này
            self.annot_controller.set_tool("fill_text" if toolset == "fill" else "highlight")
        self.active_toolbar.sync_from_controller()
        self.text_select.clear_selection()
        self.viewer.set_interaction(self.annot_controller)
        self._apply_pointer_mode()
        self._sync_history()
        self.viewer.setFocus()
        if not was:
            self.editModeChanged.emit(True)
        if not was or switched:
            self.statusMessage.emit(
                "Điền & Ký — nhấp vào dòng chấm để gõ chữ, vào ô để đánh dấu; chữ ký: chọn ✍ rồi nhấp chỗ ký."
                if toolset == "fill" else
                "Chế độ chỉnh sửa — chọn công cụ trên thanh phía trên trang (Ctrl+E để thoát)."
            )

    def enter_fill_mode(self, tool: Optional[str] = None) -> None:
        """Bật chế độ «Điền & Ký» (Ctrl+Shift+F)."""
        self.enter_edit_mode(tool, toolset="fill")

    def exit_edit_mode(self) -> None:
        if not self.edit_mode:
            return
        self.viewer.set_interaction(None)
        for bar in (self.edit_toolbar, self.fill_toolbar):
            bar.set_shortcuts_enabled(False)
            bar.setVisible(False)
        self._apply_pointer_mode()  # về lại Chọn chữ / Bàn tay
        self.editModeChanged.emit(False)

    # ─── Điền & Ký: thư viện chữ ký ───────────────────────────────────────

    def open_signature_library(self, initials: bool = False) -> None:
        """Thư viện chữ ký: tạo / xoá / chọn chữ ký đang dùng cho công cụ ✍."""
        ctl = self.annot_controller
        dlg = SignatureManagerDialog(ctl.library, None, self)
        if not ctl.library.list():  # chưa có gì → mở thẳng hộp thoại tạo chữ ký
            dlg.create_new(initials)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.chosen_id:
            sig = ctl.library.get(dlg.chosen_id)
            if sig is not None:
                ctl.set_signature(sig.initials, sig.id)
                self.enter_fill_mode("fill_initials" if sig.initials else "fill_sign")
        else:
            for sig in dlg.created:  # vừa tạo mà không bấm «Dùng» → vẫn chọn chữ ký mới nhất
                ctl.set_signature(sig.initials, sig.id)
        self.fill_toolbar.sync_from_controller()

    def _create_signature_for_placement(self, initials: bool) -> None:
        """Nhấp đặt chữ ký khi thư viện chưa có → tạo chữ ký rồi đặt luôn vào chỗ vừa nhấp."""
        ctl = self.annot_controller
        dlg = SignatureCreateDialog(ctl.library, initials, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.signature is not None:
            ctl.set_signature(dlg.signature.initials, dlg.signature.id)
            if dlg.signature.initials == initials:
                ctl.place_pending_signature()
        self.fill_toolbar.sync_from_controller()

    def toggle_edit_mode(self, toolset: str = "edit") -> None:
        """Bật/tắt chế độ chỉnh sửa; đang ở bộ công cụ kia thì chuyển sang bộ `toolset`."""
        if self.edit_mode and self._toolset == toolset:
            self.exit_edit_mode()
        else:
            self.enter_edit_mode(toolset=toolset)

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
        self.text_select.reset()
        self.ocr_layer.file_changed()  # nội dung tệp đổi → khoá lưu đệm lớp chữ đổi
        self.viewer.refresh_pages(range(self.reader.page_count))
        self._annot_list_dirty = True
        self._refresh_annotation_list_if_visible()
        self._sync_history()
        self.modifiedChanged.emit(self.reader.has_unsaved_changes)

    def _refresh_thumbnail(self, page_index: int) -> None:
        """Trang vừa đổi nội dung → vẽ lại ảnh thu nhỏ (ngay nếu đang nhìn thấy, không thì khi cuộn tới)."""
        self._thumb_done.discard(page_index)
        self._schedule_thumbnails()

    def _thumb_placeholder(self, w_pt: float, h_pt: float) -> QIcon:
        """Ảnh giữ chỗ (trang trắng đúng tỷ lệ) cho trang chưa kết xuất ảnh thu nhỏ."""
        scale = min(THUMB_BOX_W / max(1.0, w_pt), THUMB_BOX_H / max(1.0, h_pt))
        key = (max(1, round(w_pt * scale)), max(1, round(h_pt * scale)))
        icon = self._thumb_placeholders.get(key)
        if icon is None:
            pm = QPixmap(*key)
            pm.fill(QColor("#FFFFFF"))
            painter = QPainter(pm)
            painter.setPen(QColor("#CBD5E1"))
            painter.drawRect(0, 0, key[0] - 1, key[1] - 1)
            painter.end()
            icon = QIcon(pm)
            self._thumb_placeholders[key] = icon
        return icon

    def _populate_thumbnails(self) -> None:
        """Tạo đủ mục cho mọi trang ngay (ảnh giữ chỗ); ảnh thật kết xuất dần theo vùng đang nhìn thấy."""
        self.thumb_list.blockSignals(True)
        self.thumb_list.setUpdatesEnabled(False)
        self.thumb_list.clear()
        self._thumb_done.clear()
        for idx in range(self.reader.page_count):
            item = QListWidgetItem(f"Trang {idx + 1}")
            item.setIcon(self._thumb_placeholder(*self.reader.get_page_size(idx)))
            self.thumb_list.addItem(item)
        if self.reader.page_count > 0:
            self.thumb_list.setCurrentRow(0)
        self.thumb_list.setUpdatesEnabled(True)
        self.thumb_list.blockSignals(False)
        self._schedule_thumbnails()

    def _schedule_thumbnails(self) -> None:
        if not self._thumb_timer.isActive():
            self._thumb_timer.start()

    def _visible_thumb_rows(self) -> range:
        """Các hàng đang nằm trong vùng nhìn của danh sách ảnh thu nhỏ (tìm nhị phân, kèm vài hàng đệm)."""
        lst = self.thumb_list
        n = lst.count()
        if n == 0:
            return range(0)
        vp = lst.viewport().rect()
        lo, hi = 0, n - 1
        while lo < hi:  # hàng đầu tiên có mép dưới nằm dưới mép trên vùng nhìn
            mid = (lo + hi) // 2
            if lst.visualItemRect(lst.item(mid)).bottom() < vp.top():
                lo = mid + 1
            else:
                hi = mid
        last = lo
        while last + 1 < n and lst.visualItemRect(lst.item(last + 1)).top() <= vp.bottom():
            last += 1
        return range(max(0, lo - 2), min(n, last + 4))

    def thumbnail_pixmap(self, page_index: int) -> QPixmap:
        """Ảnh thu nhỏ vừa ô `THUMB_BOX_W × THUMB_BOX_H`, nét theo mật độ điểm ảnh màn hình."""
        dpr = max(1.0, self.thumb_list.devicePixelRatioF())
        w_pt, h_pt = self.reader.get_page_size(page_index)
        scale = min(THUMB_BOX_W / max(1.0, w_pt), THUMB_BOX_H / max(1.0, h_pt)) * dpr
        buf = self.reader.render_page(page_index, scale=scale, cache=False)
        qimg = QImage(buf.rgb_bytes, buf.width, buf.height, buf.stride, QImage.Format.Format_RGB888).copy()
        pm = QPixmap.fromImage(qimg)
        pm.setDevicePixelRatio(dpr)
        return pm

    def _render_visible_thumbnails(self) -> None:
        """Kết xuất ảnh thu nhỏ còn thiếu trong vùng nhìn, mỗi lượt tối đa `THUMB_BATCH` ảnh để giao diện
        vẫn mượt; còn thì hẹn lượt sau."""
        if self.reader.is_closed or not self.thumb_list.isVisible():
            return
        budget = THUMB_BATCH
        for row in self._visible_thumb_rows():
            if row in self._thumb_done:
                continue
            item = self.thumb_list.item(row)
            if item is None:
                continue
            try:
                item.setIcon(QIcon(self.thumbnail_pixmap(row)))
            except Exception:
                pass
            self._thumb_done.add(row)
            budget -= 1
            if budget == 0:
                self._schedule_thumbnails()
                return

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
        """Đổi hàng (chuột / phím mũi tên) → khung đọc chuyển ngay tới trang đó."""
        if 0 <= row < self.reader.page_count and row != self.viewer.current_page:
            self.viewer.go_to_page(row)

    def _on_thumb_clicked(self, item: QListWidgetItem) -> None:
        """Nhấp lại đúng trang đang chọn (đã cuộn lệch khỏi đầu trang) → đưa đầu trang về vùng nhìn."""
        row = self.thumb_list.row(item)
        if 0 <= row < self.reader.page_count:
            self.viewer.go_to_page(row)

    def _on_toc_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        page_idx = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(page_idx, int) and 0 <= page_idx < self.reader.page_count:
            self.viewer.go_to_page(page_idx)

    def _on_viewer_page_changed(self, page_idx: int) -> None:
        self.thumb_list.blockSignals(True)
        self.thumb_list.setCurrentRow(page_idx)
        self.thumb_list.blockSignals(False)
        self._inspector_page = None
        self._refresh_inspector()
        self._sync_rail_status()
        if getattr(self, "_layer_armed", False):
            self._request_ocr_layer()

    def _on_viewer_zoom_changed(self, _zoom_pct: int) -> None:
        self._sync_rail_status()

    def _on_overlay_toggled(self, checked: bool) -> None:
        self.viewer.set_show_layout_overlay(checked)
        self.settings.show_layout_overlay = checked
        self.settings.save()

    def _refresh_inspector(self) -> None:
        """Cập nhật ngăn «Soi bố cục» cho trang hiện tại — chỉ khi ngăn đang hiện (phân tích trang tốn công,
        không làm khi mở tệp hay khi cuộn qua từng trang mà ngăn đang ẩn)."""
        if self.reader.is_closed or not self.inspector_panel.isVisible():
            return
        page = self.viewer.current_page
        if self._inspector_page != page and 0 <= page < self.reader.page_count:
            self._update_inspector(page)

    def _update_inspector(self, page_idx: int) -> None:
        self._inspector_page = page_idx
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

    - Tầng 1 (thanh top `top_bar`): ⌂ Trang chủ, 📂 Mở, các menu nằm ngang (Tệp · Xem · Công cụ · Chỉnh sửa PDF ·
      Trợ giúp), nhãn «🎉 Có bản mới», ô tìm công cụ (Ctrl+K), GitHub, nút Sáng/Tối.
    - Tầng 2 (`tab_strip`, chỉ khi có tài liệu mở): các tab tài liệu.
    - Tầng 3 (thanh chế độ): các chế độ Tất cả công cụ · Đọc · Chuyển đổi · Chỉnh sửa · Ký số & Bảo mật,
      điều hướng trang/thu phóng (khi mở tài liệu), xuất Word.
    - Tầng 4 (chỉ khi xem tài liệu): thanh công cụ nhanh `tool_strip` — nút của chế độ đang chọn
      (`STRIP_TOOLS`), tự xuống dòng; nút «◧ Bảng công cụ» bật cột trái.
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
        self.default_app = DefaultAppController(self, self.settings)
        self.ocr_models = OcrModelController(self, notify=lambda text: self._show_toast(text, 6000))

        self._build_command_actions()
        central = QWidget()
        central.setObjectName("appRoot")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.tab_strip = self._build_tab_strip()
        root.addWidget(self._build_top_bar())
        root.addWidget(self.tab_strip)
        root.addWidget(self._build_mode_bar())
        root.addWidget(self._build_tool_strip())
        self._build_central_area()
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._build_statusbar()
        self._apply_theme(self.settings.theme)
        self._show_home()

    # ─── Lệnh: một `QAction` cho mỗi lệnh của `ui/commands.py` (dùng chung cho nút, menu, phím tắt) ───────

    def _build_command_actions(self) -> None:
        """Tạo `command_actions` từ `commands.COMMANDS`, gắn vào cửa sổ (phím tắt chạy không phụ thuộc menu) và
        dựng tạm 5 menu ngang cũ (Tệp · Xem · Công cụ · Chỉnh sửa PDF · Trợ giúp) tới khi có nút ☰ (Task 3)."""
        reused = {  # hành động sẵn có của bộ cập nhật / trình xem mặc định (giữ kết nối & trạng thái của chúng)
            "check_update": self.updater.act_check,
            "auto_check_updates": self.updater.act_auto,
            "auto_download_updates": self.updater.act_auto_download,
            "default_app": self.default_app.act_set_default,
        }
        self.command_actions: dict[str, QAction] = {}
        for cmd in commands.COMMANDS:
            act = reused.get(cmd.key) or QAction(self)
            act.setText(cmd.label)
            act.setIcon(icons.icon(cmd.icon))
            act.setCheckable(cmd.checkable)
            tip = cmd.label_text() + (f" — {cmd.summary}" if cmd.summary else "")
            act.setToolTip(f"{tip} ({cmd.shortcuts()[0]})" if cmd.shortcut else tip)
            if cmd.register_shortcut and cmd.shortcut:
                act.setShortcuts([QKeySequence(s) for s in cmd.shortcuts()])
            if cmd.key not in _ACTION_DRIVEN_COMMANDS:
                act.triggered.connect(lambda _checked=False, k=cmd.key: self.run_command(k, from_action=True))
            self.addAction(act)
            self.command_actions[cmd.key] = act

        overlay = self.command_actions["layout_overlay"]
        overlay.setChecked(self.settings.show_layout_overlay)
        overlay.toggled.connect(self.action_toggle_layout_overlay)
        self.pointer_actions: dict[str, QAction] = {m: self.command_actions[f"pointer_{m}"] for m in POINTER_MODES}
        for mode, act in self.pointer_actions.items():
            act.setChecked(self.settings.pointer_mode == mode)

        # Tên cũ mà code / test khác còn dùng
        ca = self.command_actions
        self.act_open, self.act_convert, self.act_batch_convert = ca["open"], ca["convert_word"], ca["batch_convert"]
        self.act_ocr, self.act_print, self.act_doc_info = ca["ocr"], ca["print"], ca["doc_info"]
        self.act_close_tab, self.act_home, self.act_palette = ca["close_tab"], ca["home"], ca["palette"]
        self.act_zoom_in, self.act_zoom_out = ca["zoom_in"], ca["zoom_out"]
        self.act_toggle_sidebar, self.act_toggle_overlay = ca["toggle_sidebar"], ca["layout_overlay"]
        self.act_read_mode, self.act_toggle_theme = ca["read_mode"], ca["toggle_theme"]
        self.act_nd30_check, self.act_edit_mode, self.act_fill_sign = ca["nd30_check"], ca["edit_mode"], ca["fill_mode"]
        self.act_undo, self.act_redo = ca["undo"], ca["redo"]
        self.act_organize, self.act_combine = ca["organize"], ca["combine"]
        self.act_save, self.act_save_as = ca["save"], ca["save_as"]

        self._build_legacy_menus()
        self.menuBar().setVisible(False)

    def _build_legacy_menus(self) -> None:
        """5 menu ngang của thanh top hiện tại, dựng từ `command_actions` (xoá khi có nút ☰ — Task 3)."""
        self.main_menu = QMenu(self)
        self.recent_menu = QMenu("Tệp mở gần đây", self)
        layout: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("Tệp", ("open", "convert_word", "batch_convert", "ocr", ":recent", "|", "print", "doc_info",
                     "close_tab", "|", "quit")),
            ("Xem", ("home", "zoom_in", "zoom_out", "fit_width", "fit_page", "|", "pointer_select", "pointer_hand",
                     "|", "toggle_sidebar", "layout_overlay", "read_mode", "|", "toggle_theme")),
            ("Công cụ", ("palette", "find", "extract_text", "|", "nd30_check", "convert_word_nd30", "verify_docx",
                         "convert_word")),
            ("Chỉnh sửa PDF", ("edit_mode", "undo", "redo", "fill_mode", "signatures", "|", "organize", "combine",
                               "split", "extract_pages", "|", "compress", "watermark", "page_numbers", "protect",
                               "unlock", "|", "save", "save_as", "export_flattened")),
            ("Trợ giúp", ("about", "github", "|", "check_update", "auto_check_updates", "auto_download_updates",
                          "|", "default_app")),
        )
        for title, keys in layout:
            menu = self.main_menu.addMenu(title)
            for key in keys:
                if key == "|":
                    menu.addSeparator()
                elif key == ":recent":
                    menu.addMenu(self.recent_menu)
                else:
                    menu.addAction(self.command_actions[key])
        self._refresh_recent_menu()

    # ─── Tầng 1: Dải tiêu đề & tab tài liệu ────────────────────────────────

    def _build_top_bar(self) -> QFrame:
        """Hàng trên cùng: ⌂ Trang chủ · 📂 Mở · các menu nằm ngang · ô tìm lệnh · GitHub · Sáng/Tối."""
        strip = QFrame()
        strip.setObjectName("topBar")
        lay = QHBoxLayout(strip)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)

        self.btn_home = QPushButton("⌂  Trang chủ")
        self.btn_home.setObjectName("homeTabBtn")
        self.btn_home.setCheckable(True)
        self.btn_home.setToolTip("Trang chủ (Alt+Home)")
        self.btn_home.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_home.clicked.connect(self.action_go_home)
        lay.addWidget(self.btn_home)

        self.btn_open = QPushButton("📂  Mở")
        self.btn_open.setObjectName("openTopBtn")
        self.btn_open.setToolTip("Mở tệp PDF (Ctrl+O)")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.clicked.connect(self.action_open_pdf)
        lay.addWidget(self.btn_open)

        sep = QFrame()
        sep.setObjectName("topBarSep")
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(20)
        lay.addSpacing(6)
        lay.addWidget(sep)
        lay.addSpacing(6)

        # Mỗi menu con của `main_menu` thành một nút thả xuống nằm ngang (phím tắt vẫn chạy nhờ `addActions`)
        self.menu_buttons: dict[str, QPushButton] = {}
        for action in self.main_menu.actions():
            submenu = action.menu()
            if submenu is None:
                continue
            btn = QPushButton(action.text())
            btn.setObjectName("menuBarBtn")
            btn.setMenu(submenu)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(btn)
            self.menu_buttons[submenu.title().replace("&&", "&")] = btn

        # Nhãn «🎉 Có bản mới» chỉ hiện khi bộ cập nhật phát hiện bản mới (xem `show_update_badge`)
        self.btn_update_badge = QPushButton("")
        self.btn_update_badge.setObjectName("updateBadgeBtn")
        self.btn_update_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update_badge.setVisible(False)
        self.btn_update_badge.clicked.connect(self.updater.on_badge_clicked)
        lay.addSpacing(8)
        lay.addWidget(self.btn_update_badge)
        lay.addStretch(1)

        self.toolbar_search_input = QLineEdit()
        self.toolbar_search_input.setObjectName("commandSearch")
        self.toolbar_search_input.setPlaceholderText("🔍 Tìm công cụ & lệnh…  Ctrl+K")
        self.toolbar_search_input.setMinimumWidth(180)
        self.toolbar_search_input.setMaximumWidth(300)
        self.toolbar_search_input.returnPressed.connect(self._on_toolbar_quick_search)
        completer = QCompleter([c.label_text() for c in commands.search("")], self.toolbar_search_input)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.activated.connect(self._on_completer_activated)
        self.toolbar_search_input.setCompleter(completer)
        lay.addWidget(self.toolbar_search_input)
        lay.addSpacing(6)

        btn_github = QPushButton("⟨/⟩ GitHub")
        btn_github.setObjectName("ghostBtn")
        btn_github.setToolTip("Mã nguồn, báo lỗi & góp ý trên GitHub")
        btn_github.clicked.connect(lambda: self._open_link(f"https://github.com/{__github_repo__}"))
        lay.addWidget(btn_github)

        self.btn_theme_toggle = QPushButton("☀️ Giao diện Sáng")
        self.btn_theme_toggle.setObjectName("themeToggleBtn")
        self.btn_theme_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme_toggle.clicked.connect(self.action_toggle_theme)
        lay.addWidget(self.btn_theme_toggle)
        return strip

    def show_update_badge(self, text: str = "", ready: bool = False) -> None:
        """Hiện/ẩn nhãn nhắc bản mới ở thanh trên cùng (`text` rỗng = ẩn)."""
        self.btn_update_badge.setText(text)
        self.btn_update_badge.setProperty("ready", ready)
        self.btn_update_badge.style().unpolish(self.btn_update_badge)
        self.btn_update_badge.style().polish(self.btn_update_badge)
        self.btn_update_badge.setVisible(bool(text))

    def _build_tab_strip(self) -> QFrame:
        """Hàng tab tài liệu — chỉ hiện khi có tài liệu đang mở."""
        strip = QFrame()
        strip.setObjectName("titleStrip")
        lay = QHBoxLayout(strip)
        lay.setContentsMargins(10, 4, 10, 0)
        lay.setSpacing(4)

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
        lay.addStretch(1)
        strip.setVisible(False)
        return strip

    def _sync_tab_strip(self) -> None:
        self.tab_strip.setVisible(self.doc_tab_bar.count() > 0)

    # ─── Tầng 3: Thanh chế độ ──────────────────────────────────────────────

    def _build_mode_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("modeBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(4)

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
        self.btn_mode_tools.setToolTip("Công cụ hay dùng — «◧ Bảng công cụ»: bảng Tất cả công cụ bên trái")
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

        # «ℹ» và «Xuất Word» thuộc cụm điều khiển tài liệu: chỉ hiện khi đang xem PDF
        dc.addSpacing(4)
        btn_info = QPushButton("ℹ")
        btn_info.setObjectName("ghostIconBtn")
        btn_info.setToolTip("Thuộc tính tài liệu (Ctrl+I)")
        btn_info.clicked.connect(self.action_show_doc_info)
        dc.addWidget(btn_info)

        self.btn_convert_docx = QPushButton("📄 Xuất Word")
        self.btn_convert_docx.setObjectName("primaryConvertBtn")
        self.btn_convert_docx.setToolTip("Chuyển PDF sang Word (.docx) — văn bản hành chính tự dùng chuẩn NĐ30 (Ctrl+Shift+W)")
        self.btn_convert_docx.clicked.connect(self.action_convert_to_docx)
        dc.addWidget(self.btn_convert_docx)
        return bar

    # ─── Tầng 3: Thanh công cụ nhanh (khi xem tài liệu) ───────────────────

    def _build_tool_strip(self) -> QFrame:
        self.tool_strip = QFrame()
        self.tool_strip.setObjectName("toolStrip")
        self._strip_layout = FlowLayout(self.tool_strip, hspacing=4, vspacing=4)
        self._strip_layout.setContentsMargins(10, 4, 10, 4)

        self.btn_strip_panel = QPushButton("◧ Bảng công cụ")
        self.btn_strip_panel.setObjectName("stripToolBtn")
        self.btn_strip_panel.setCheckable(True)
        self.btn_strip_panel.setChecked(self.settings.show_tools_panel)
        self.btn_strip_panel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_strip_panel.setToolTip("Hiện/Ẩn bảng Tất cả công cụ bên trái")
        self.btn_strip_panel.clicked.connect(self.set_tools_panel_visible)
        self._strip_layout.addWidget(self.btn_strip_panel)

        sep = QFrame()
        sep.setObjectName("toolStripSep")
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(self.btn_strip_panel.sizeHint().height())
        self._strip_layout.addWidget(sep)

        self.strip_buttons: dict[str, QPushButton] = {}
        self._refresh_tool_strip()
        self.tool_strip.setVisible(False)
        return self.tool_strip

    def _refresh_tool_strip(self) -> None:
        """Dựng lại các nút của thanh công cụ nhanh theo chế độ đang chọn."""
        for btn in self.strip_buttons.values():
            self._strip_layout.removeWidget(btn)
            btn.hide()  # deleteLater chỉ xoá khi về vòng lặp sự kiện — ẩn ngay để không đè nút mới
            btn.deleteLater()
        self.strip_buttons = {}
        for label, key in STRIP_TOOLS.get(self._mode_category, STRIP_TOOLS["all"]):
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            tool = get_tool(key)
            if tool is not None:
                ready = tool.ready
                tip = f"{tool.name} — {tool.summary}"
                if not ready:
                    tip += f"  ·  {COMING_SOON_LABEL} (dự kiến {tool.milestone})"
            else:
                ready, tip = True, STRIP_COMMAND_TIPS.get(key, label)
            btn.setObjectName("stripToolBtn" if ready else "stripToolSoonBtn")
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _c=False, k=key: self._run_strip_command(k))
            self._strip_layout.addWidget(btn)
            self.strip_buttons[key] = btn

    def _run_strip_command(self, key: str) -> None:
        if key == ":rotate_left":
            self._with_active_tab(lambda t: t.viewer.rotate_current_page(-90))
        elif key == ":convert_dialog":
            self.action_convert_to_docx()
        else:
            self.run_command(key)

    def activate_pointer_tool(self, mode: str) -> None:
        """Công cụ «Chọn & sao chép chữ» / «Bàn tay» từ danh mục, Ctrl+K hay thanh công cụ nhanh: thoát chế độ chỉnh sửa
        (nếu đang bật), đổi chế độ con trỏ rồi trả bàn phím cho khung đọc để Ctrl+A / Ctrl+C dùng được ngay."""
        tab = self.active_tab()
        if tab is not None and tab.edit_mode:
            tab.exit_edit_mode()
        self.set_pointer_mode(mode)
        if tab is not None:
            tab.viewer.widget().setFocus()

    def set_pointer_mode(self, mode: str) -> None:
        """Chuyển Chọn chữ ↔ Bàn tay ở mọi tab tài liệu và ghi nhớ cho lần mở sau."""
        if mode not in POINTER_MODES:
            return
        if self.settings.pointer_mode != mode:
            self.settings.pointer_mode = mode
            self.settings.save()
        for m, act in self.pointer_actions.items():
            act.setChecked(m == mode)
        for i in range(self.doc_tabs.count()):
            w = self.doc_tabs.widget(i)
            if isinstance(w, PDFDocumentTab):
                w.set_pointer_mode(mode)
        self.statusBar().showMessage(
            "Chọn chữ — kéo qua chữ để chọn, Ctrl+C để chép; trang ảnh quét: kéo khung để nhận dạng. Giữ Space để kéo cuộn."
            if mode == "select" else "Bàn tay — kéo để cuộn trang (V để quay lại chọn chữ).", 6000)

    def set_tools_panel_visible(self, visible: bool) -> None:
        """Hiện/ẩn cột «Tất cả công cụ» ở mọi tab tài liệu và ghi nhớ cho lần mở sau."""
        visible = bool(visible)
        if self.settings.show_tools_panel != visible:
            self.settings.show_tools_panel = visible
            self.settings.save()
        self.btn_strip_panel.setChecked(visible)
        for i in range(self.doc_tabs.count()):
            w = self.doc_tabs.widget(i)
            if isinstance(w, PDFDocumentTab):
                w.tools_panel.setVisible(visible)

    # ─── Thân cửa sổ ───────────────────────────────────────────────────────

    def _build_central_area(self) -> None:
        self.stack = QStackedWidget(self)
        self.home_page = HomePage()
        self.home_page.toolActivated.connect(self.run_command)
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
        icons.set_icon_color(theme_tokens(normalized)["text"])
        for key, act in getattr(self, "command_actions", {}).items():
            act.setIcon(icons.icon(commands.get(key).icon))
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
        self.tool_strip.setVisible(False)
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
        self.tool_strip.setVisible(True)
        self._sync_toolbar_with_active_tab()

    def set_mode_category(self, category: str) -> None:
        """Chọn chế độ (nhóm công cụ) trên thanh chế độ — lọc bảng công cụ ở Trang chủ & tài liệu,
        đổi nút trên thanh công cụ nhanh (cột trái giữ nguyên trạng thái ẩn/hiện của người dùng)."""
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
        self._refresh_tool_strip()
        tab = self.active_tab()
        if tab is not None and self.stack.currentWidget() is self.doc_tabs:
            if category == "edit":
                tab.enter_edit_mode()
            elif category == "fill":
                tab.enter_fill_mode()
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
        tab.tools_panel.setVisible(self.settings.show_tools_panel)
        tab.toolsPanelHideRequested.connect(lambda: self.set_tools_panel_visible(False))
        tab.pointerModeRequested.connect(self.set_pointer_mode)
        tab.saveSearchableRequested.connect(self.action_save_searchable)
        tab.viewer.pageChanged.connect(lambda _p: self._sync_toolbar_with_active_tab())
        tab.viewer.zoomChanged.connect(lambda _z: self._sync_toolbar_with_active_tab())
        tab.extract_page_text_btn.clicked.connect(self.action_extract_current_page_text)
        tab.sidebar_convert_btn.clicked.connect(self.action_convert_to_docx)
        tab.banner_convert_btn.clicked.connect(
            lambda: self.action_convert_to_docx_mode("nd30" if tab.is_admin_document else "auto")
        )
        tab.tool_btn_convert_nd30.clicked.connect(lambda: self.action_convert_to_docx_mode("nd30"))
        tab.tool_btn_nd30_check.clicked.connect(lambda: self.run_command("nd30_check"))
        tab.tool_btn_convert_hybrid.clicked.connect(lambda: self.action_convert_to_docx_mode("hybrid"))
        tab.tool_btn_convert_exact.clicked.connect(lambda: self.action_convert_to_docx_mode("exact"))
        tab.tool_btn_convert_dialog.clicked.connect(self.action_convert_to_docx)
        tab.tool_btn_extract_text.clicked.connect(self.action_extract_current_page_text)
        tab.tool_btn_doc_info.clicked.connect(self.action_show_doc_info)
        tab.tool_btn_print.clicked.connect(lambda: self.run_command("print"))
        tab.tool_btn_all_tools.clicked.connect(lambda: self.action_command_palette(""))
        tab.tool_btn_organize.clicked.connect(lambda: self.run_command("organize"))
        tab.toolRequested.connect(self.run_command)
        tab.tool_btn_save.clicked.connect(self.action_save)
        tab.edit_toolbar.saveRequested.connect(self.action_save)
        tab.edit_toolbar.organizeRequested.connect(lambda: self.run_command("organize"))
        tab.modifiedChanged.connect(lambda _m, t=tab: self._update_tab_title(t))
        tab.statusMessage.connect(lambda text: self.statusBar().showMessage(text, 6000))

        safe_tab_title = path.name.replace("&", "&&")
        idx = self.doc_tabs.addTab(tab, safe_tab_title)
        self.doc_tab_bar.blockSignals(True)
        self.doc_tab_bar.insertTab(idx, f"📄 {safe_tab_title}")
        self.doc_tab_bar.setTabToolTip(idx, str(path))
        self.doc_tab_bar.blockSignals(False)
        self._sync_tab_strip()
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
        self._sync_tab_strip()
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

    def run_command(self, key: str, from_action: bool = False) -> None:
        """Chạy một lệnh của `ui/commands.py` (nhận cả khoá cũ của `tool_catalog` tới khi bỏ hẳn — Task 8).

        Lệnh cần tài liệu mà chưa có tab → hỏi mở tệp rồi chạy nếu đã mở được (spec §5.3). Riêng lệnh
        `quiet_without_document` gọi từ phím tắt / `QAction` (`from_action=True`) thì bỏ qua khi chưa có tài liệu
        và không rời Trang chủ khi đã có. Công cụ «Coming Soon» cũ chỉ hiện thông báo."""
        key = _LEGACY_TOOL_KEYS.get(key, key)
        cmd = commands.BY_KEY.get(key)
        if cmd is not None:
            fn = self._command_handlers().get(key)
            name, needs_document = cmd.label_text(), cmd.needs_document
            quiet = from_action and cmd.quiet_without_document
        else:
            tool = get_tool(key)
            if tool is None:
                return
            if not tool.ready:
                self._show_toast(
                    f"⏳ {tool.name} — {COMING_SOON_LABEL} (dự kiến {tool.milestone}). Theo dõi tiến độ trên GitHub.")
                return
            fn = self._legacy_tool_handlers().get(key)
            name, needs_document, quiet = tool.name, tool.needs_document, False
        if needs_document and self.active_tab() is None:
            if quiet:
                return
            self._show_toast(f"Hãy mở một tệp PDF trước khi dùng «{name}».")
            self.action_open_pdf()
            if self.active_tab() is None:
                return
        if needs_document and not quiet:
            self._show_documents()
        if fn is not None:
            fn()

    run_tool = run_command  # bí danh tạm cho code / test cũ (xoá ở Task 8)

    def _command_handlers(self) -> dict[str, Callable[[], None]]:
        """Khoá lệnh → hàm xử lý (lệnh `_ACTION_DRIVEN_COMMANDS` gọi `QAction.trigger()`)."""
        on_tab = self._with_active_tab
        handlers: dict[str, Callable[[], None]] = {
            # Đọc
            "rotate_left": lambda: on_tab(lambda t: t.viewer.rotate_current_page(-90)),
            "rotate_right": lambda: on_tab(lambda t: t.viewer.rotate_current_page(90)),
            "read_mode": self.action_read_mode,
            "print": self.action_print,
            "doc_info": self.action_show_doc_info,
            # Chuyển đổi
            "convert_word": self.action_convert_to_docx,
            "convert_word_nd30": lambda: self.action_convert_to_docx_mode("nd30"),
            "convert_word_exact": lambda: self.action_convert_to_docx_mode("exact"),
            "convert_word_flow": lambda: self.action_convert_to_docx_mode("hybrid"),
            "ocr": self.action_ocr,
            "nd30_check": self.action_nd30_check,
            "verify_docx": self.action_verify_docx,
            "batch_convert": self.action_batch_convert,
            # Chỉnh sửa
            "undo": lambda: on_tab(lambda t: t.annot_controller.undo()),
            "redo": lambda: on_tab(lambda t: t.annot_controller.redo()),
            "organize": lambda: self.action_organize("organize"),
            "combine": lambda: self.action_organize("combine"),
            "split": lambda: self.action_organize("split"),
            "extract_pages": lambda: self.action_organize("extract"),
            "save": self.action_save,
            "save_as": self.action_save_as,
            "export_flattened": self.action_export_flattened,
            # Điền & Ký, Bảo mật
            "signatures": self.action_signature_library,
            "sig_inspect": lambda: self._open_inspector(True),
            # Hệ thống
            "open": self.action_open_pdf,
            "close_tab": self.action_close_current_tab,
            "home": self.action_go_home,
            "quit": self.close,
            "zoom_in": lambda: on_tab(lambda t: t.viewer.zoom_in()),
            "zoom_out": lambda: on_tab(lambda t: t.viewer.zoom_out()),
            "fit_width": lambda: on_tab(lambda t: t.viewer.set_zoom_mode("fit_width")),
            "fit_page": lambda: on_tab(lambda t: t.viewer.set_zoom_mode("fit_page")),
            "pointer_select": lambda: self.activate_pointer_tool("select"),
            "pointer_hand": lambda: self.activate_pointer_tool("hand"),
            "toggle_sidebar": self.action_toggle_sidebar,
            "toggle_theme": self.action_toggle_theme,
            "palette": lambda: self.action_command_palette(""),
            "find": lambda: on_tab(lambda t: t.focus_search()),
            "extract_text": self.action_extract_current_page_text,
            "edit_mode": lambda: on_tab(lambda t: t.toggle_edit_mode()),  # Task 4: set_function_tab
            "fill_mode": self.action_fill_sign,
            "github": lambda: self._open_link(f"https://github.com/{__github_repo__}"),
            "about": self.action_show_about,
        }
        for key in PDF_TOOL_DIALOGS:  # compress, watermark, page_numbers, protect, unlock
            handlers[key] = lambda k=key: self.action_pdf_tool(k)
        for cmd in commands.COMMANDS:
            if cmd.key.startswith("annot."):
                handlers[cmd.key] = lambda c=cmd: self._enter_annot_tool(c.key.split(".", 1)[1], c.tab)
        for key in _ACTION_DRIVEN_COMMANDS:
            handlers[key] = lambda k=key: self.command_actions[k].trigger()
        return handlers

    def _legacy_tool_handlers(self) -> dict[str, Callable[[], None]]:
        """Khoá `tool_catalog` chưa có lệnh tương ứng (ngăn bên phải có lệnh riêng ở Task 5)."""
        return {
            "layout_inspect": lambda: self._open_inspector(True),
            "bookmarks": lambda: self._with_active_tab(lambda t: t._on_rail_tab_clicked(1)),
            "comments": self._open_annotation_panel,
            "fill_sign": lambda: self.set_mode_category("fill"),
        }

    def _enter_annot_tool(self, tool: str, toolset: str) -> None:
        """Chọn công cụ chú thích (bật chế độ chỉnh sửa / Điền & Ký); «Tẩy» giữ bộ công cụ đang dùng."""
        tab = self.active_tab()
        if tab is None:
            return
        if tool == "eraser" and tab.edit_mode:
            toolset = tab.toolset
        tab.enter_edit_mode(tool, toolset)

    def action_fill_sign(self) -> None:
        """Ctrl+Shift+F: bật/tắt «Điền & Ký» trên tài liệu đang mở (đồng bộ nút chế độ)."""
        tab = self.active_tab()
        if tab is None:
            self.run_command("fill_sign")
            return
        if tab.edit_mode and tab.toolset == "fill":
            tab.exit_edit_mode()
            self.set_mode_category("read")
        else:
            self.set_mode_category("fill")

    def action_signature_library(self) -> None:
        """Thư viện chữ ký — dùng được cả khi chưa mở tài liệu."""
        tab = self.active_tab()
        if tab is not None:
            tab.open_signature_library()
            return
        dlg = SignatureManagerDialog(fill_sign.SignatureLibrary(), None, self)
        dlg.exec()

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
        self.ocr_models.cancel_and_wait()
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

    # ─── Công cụ văn phòng: nén, dấu nước, đánh số trang, mật khẩu ───────

    def _tool_source(self) -> Optional[tuple[Optional[Path], Optional[str]]]:
        """Tệp nguồn cho công cụ PDF = tệp của tab đang đọc (hỏi lưu chú thích chưa lưu); None = huỷ."""
        tab = self.active_tab()
        if tab is None or not tab.reader.is_pdf:
            return None, None
        if tab.reader.has_unsaved_changes:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("Chú thích chưa lưu")
            box.setText(f"«{tab.reader.path.name}» có chú thích / chỉnh sửa chưa lưu.")
            box.setInformativeText("Công cụ đọc tệp trên đĩa — lưu trước để kết quả có cả các chỉnh sửa này?")
            btn_save = box.addButton("Lưu rồi tiếp tục", QMessageBox.ButtonRole.AcceptRole)
            btn_skip = box.addButton("Dùng bản đã lưu", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("Huỷ", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(btn_save)
            box.exec()
            clicked = box.clickedButton()
            if clicked is btn_save:
                if not self._save_tab(tab):
                    return None
            elif clicked is not btn_skip:
                return None
        return tab.reader.path, tab.reader.password

    def action_pdf_tool(self, key: str) -> None:
        """Mở hộp thoại công cụ PDF (`compress`, `watermark`, `page_numbers`, `protect`, `unlock`)."""
        dialog_cls = PDF_TOOL_DIALOGS.get(key)
        if dialog_cls is None:
            return
        picked = self._tool_source()
        if picked is None:
            return
        source, password = picked
        if source is None:
            chosen, _ = QFileDialog.getOpenFileName(
                self, f"{dialog_cls.TOOL_TITLE} — chọn tệp PDF", "", "Tài liệu PDF (*.pdf)"
            )
            if not chosen:
                return
            source = Path(chosen)
        dlg = dialog_cls(self, source=source, password=password,
                         is_locked=lambda p: self._tab_for_path(p) is not None)
        if not dlg.exec() or dlg.tool_result is None or not dlg.tool_result.written:
            return
        self._offer_open_result(dlg.TOOL_TITLE, dlg.result_summary(), Path(dlg.tool_result.output_path),
                                dlg.result_password)

    def _offer_open_result(self, title: str, summary: str, out: Path, password: Optional[str] = None) -> None:
        answer = QMessageBox.question(
            self, title, f"{summary}\n\nĐã lưu: {out}\n\nMở tệp kết quả thành tab mới?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.open_pdf_path(out, password=password)
        else:
            self._show_toast(f"💾 Đã lưu {out.name} ({out.parent})")

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

    def action_save_searchable(self) -> None:
        """Tài liệu ảnh quét → «Lưu thành PDF tìm kiếm được»: hộp thoại OCR (kết quả PDF), trang đã nhận dạng ngầm
        khi xem (`PDFDocumentTab.ocr_layer`) được dùng lại thay vì nhận dạng lại."""
        tab = self.active_tab()
        factory = None
        if tab is not None and tab.ocr_layer.pages and self.ocr_models.is_installed():
            pages = dict(tab.ocr_layer.pages)
            factory = lambda: CachedOcrEngine(pages, shared_ocr_engine)  # noqa: E731
        self.action_ocr(engine_factory=factory)

    def action_ocr(self, engine_factory: Optional[Callable[[], object]] = None) -> None:
        """Ctrl+Shift+R: OCR tiếng Việt — lần đầu tự tải ngầm bộ mô hình (~88 MB); nhận dạng tệp của tab đang đọc."""
        self.ocr_models.ensure_started()
        picked = self._tool_source()
        if picked is None:
            return
        source, password = picked
        dlg = OcrDialog(self, source=source, password=password, models=self.ocr_models,
                        is_locked=lambda p: self._tab_for_path(p) is not None, engine_factory=engine_factory)
        if not dlg.exec() or dlg.ocr_result is None:
            return
        res = dlg.ocr_result
        out = Path(res.output_path)
        if res.output_kind == "pdf":
            self._offer_open_result(dlg.TOOL_TITLE, dlg.result_summary(), out, dlg.source_password)
            return
        answer = QMessageBox.question(self, dlg.TOOL_TITLE, f"{dlg.result_summary()}\n\nĐã lưu: {out}\n\nMở tệp kết quả?")
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))
        else:
            self._show_toast(f"💾 Đã lưu {out.name} ({out.parent})")

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
                self.run_command(dlg.selected_key)

    @staticmethod
    def _command_by_label(text: str) -> Optional[commands.Command]:
        wanted = text.strip().lower()
        return next((c for c in commands.COMMANDS if c.palette and c.label_text().lower() == wanted), None)

    def _on_completer_activated(self, text: str) -> None:
        cmd = self._command_by_label(text)
        if cmd is not None:
            QTimer.singleShot(0, lambda: self.toolbar_search_input.clear())
            self.run_command(cmd.key)

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
        cmd = self._command_by_label(query)
        if cmd is not None:
            self.toolbar_search_input.clear()
            self.run_command(cmd.key)
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
            self.set_tools_panel_visible(tab.tools_panel.isHidden())

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
            tab.tools_panel.setVisible(not entering and self.settings.show_tools_panel)
            tab.sidebar_tabs.setVisible(not entering)
            self.tool_strip.setVisible(not entering)
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
