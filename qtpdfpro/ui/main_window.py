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
    QCheckBox,
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
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolButton,
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
from qtpdfpro.ui.function_bar import FunctionBar
from qtpdfpro.ui.top_bar import TopBar
from qtpdfpro.ui.signature_dialog import SignatureCreateDialog, SignatureManagerDialog
from qtpdfpro.ui.ocr_layer_service import OcrLayerService, shared_ocr_engine
from qtpdfpro.ui.text_select_tool import TextSelectTool
from qtpdfpro.ui.pdf_tools_dialog import PDF_TOOL_DIALOGS
from qtpdfpro.ui import commands, icons
from qtpdfpro.ui.theme import get_stylesheet, theme_tokens
from qtpdfpro.ui.tool_catalog import COMING_SOON_LABEL, get_tool
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

# Thanh dọc phải: (chú giải, biểu tượng, chỉ số ngăn trong `sidebar_tabs`) — ngăn 3 «Soi bố cục» mở bằng công cụ
# «Soi bố cục» / F8 (không có nút riêng)
RAIL_PANELS: tuple[tuple[str, str, int], ...] = (
    ("Trang (ảnh thu nhỏ các trang)", "gallery-vertical-end", 0),
    ("Mục lục (Bookmarks)", "list-tree", 1),
    ("Tìm kiếm (Ctrl+F)", "search", 2),
    ("Chú thích (tô sáng, ghi chú, dấu đóng…)", "message-square", 4),
)


class PDFDocumentTab(QWidget):
    """Một tab tài liệu PDF:
    - Giữa: dòng thông báo mảnh tắt được (`notice_bar`) + khung vẽ PDF tốc độ cao (`PDFScrollViewer`); khi chỉnh
      sửa thì thêm thanh chú thích (`edit_toolbar` / `fill_toolbar`) phía trên khung đọc.
    - Phải: ngăn 5 trang (Trang, Mục lục, Tìm kiếm, Soi bố cục, Chú thích — không có hàng tab chữ) + thanh biểu
      tượng dọc `rail_panel_buttons` là chỗ chuyển ngăn duy nhất.
    Công cụ, đổi trang, thu phóng nằm ở tầng 2 của `MainWindow` (`ui/function_bar.py`).
    """

    modifiedChanged = Signal(bool)
    editModeChanged = Signal(bool)
    statusMessage = Signal(str)
    toolsetChanged = Signal(str)  # "edit" | "fill" khi vào / đổi bộ công cụ chỉnh sửa, "" khi thoát → tầng 2 đổi thẻ
    noticeCommandRequested = Signal(str)  # liên kết của dòng thông báo → MainWindow.run_command(khoá)
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
        self.is_admin_document = False

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root_layout.addWidget(self.splitter, 1)

        # ─── Giữa: dòng thông báo mảnh + khung xem PDF ───────────────────────
        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self._build_notice_bar())

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
        for bar in (self.edit_toolbar, self.fill_toolbar):  # một lệnh một nút: đã có ở tầng 2
            for btn in (bar.btn_undo, bar.btn_redo, bar.btn_organize, bar.btn_save):
                btn.setVisible(False)
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

        insp_layout.addWidget(self.chk_overlay)
        insp_layout.addWidget(legend_lbl)
        insp_layout.addWidget(self.layout_info_lbl, 1)
        insp_layout.addWidget(self.extract_page_text_btn)
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

        # Ghép khung đọc + ngăn phải vào Splitter (hàng tab chữ của ngăn ẩn: chuyển ngăn bằng thanh dọc)
        self.sidebar_tabs.tabBar().hide()
        self.splitter.addWidget(center_container)
        self.splitter.addWidget(self.sidebar_tabs)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([1000, 265])

        # ─── Thanh biểu tượng dọc bên phải: chuyển ngăn ─────────────────────
        self.right_rail = self._build_right_rail()
        root_layout.addWidget(self.right_rail)

        # Mở tệp nhanh: không phân tích bố cục mọi trang lúc mở. Thanh thông báo tính sau khi tab đã hiện
        # (`_analyze_document`), bảng biểu dò dần từng trang lúc rảnh (`_scan_tables_step`).
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
        self.sidebar_tabs.currentChanged.connect(self._sync_rail_buttons)
        self.sidebar_tabs.currentChanged.connect(lambda _i: self._refresh_annotation_list_if_visible())
        self._sync_rail_buttons()
        self._apply_pointer_mode()
        self._analysis_timer.start()

    # Đường dẫn tệp đã tắt dòng thông báo (✕) trong phiên chạy — mở lại tệp đó không hiện lại
    _dismissed_notice_paths: set[str] = set()

    def _build_notice_bar(self) -> QFrame:
        """Dòng thông báo mảnh: biểu tượng · câu ngắn · một liên kết chữ · ✕ (spec §2.3)."""
        bar = QFrame()
        bar.setObjectName("noticeBar")
        bar.setMaximumHeight(34)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 3, 6, 3)
        lay.setSpacing(8)
        self.notice_icon = QLabel()
        self.notice_icon.setObjectName("noticeIcon")
        self.notice_icon.setFixedSize(16, 16)
        self.notice_lbl = QLabel()
        self.notice_lbl.setObjectName("noticeLbl")
        self.notice_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)  # không nới cửa sổ
        self.notice_link = QPushButton()
        self.notice_link.setObjectName("linkBtn")
        self.notice_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.notice_link.setFlat(True)
        self.notice_link.clicked.connect(self._on_notice_link)
        self.notice_close = QToolButton()
        self.notice_close.setObjectName("noticeClose")
        self.notice_close.setToolTip("Ẩn thông báo (không hiện lại cho tệp này)")
        self.notice_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.notice_close.setIconSize(QSize(14, 14))
        icons.bind(self.notice_close, "x", 14)
        self.notice_close.clicked.connect(self.dismiss_notice)
        lay.addWidget(self.notice_icon)
        lay.addWidget(self.notice_lbl, 1)
        lay.addWidget(self.notice_link)
        lay.addWidget(self.notice_close)
        self.notice_bar = bar
        self._notice_command = ""
        self.notice_dismissed = str(self.reader.path) in self._dismissed_notice_paths
        self.refresh_notice_icon()
        bar.setVisible(False)
        return bar

    def refresh_notice_icon(self) -> None:
        self.notice_icon.setPixmap(icons.icon("info", size=16).pixmap(16, 16))

    def show_notice(self, text: str, link_text: str, command_key: str) -> None:
        """Hiện dòng thông báo (trừ khi người dùng đã tắt cho tệp này). `command_key` = khoá lệnh của
        `ui/commands.py`, hoặc «saveSearchableRequested» (tài liệu ảnh quét → Lưu thành PDF tìm kiếm được)."""
        self.notice_lbl.setText(text)
        self.notice_lbl.setToolTip(text)
        self.notice_link.setText(link_text)
        self._notice_command = command_key
        self.notice_bar.setVisible(not self.notice_dismissed)

    def hide_notice(self) -> None:
        self.notice_bar.setVisible(False)

    def dismiss_notice(self) -> None:
        self.notice_dismissed = True
        self._dismissed_notice_paths.add(str(self.reader.path))
        self.notice_bar.setVisible(False)

    def _on_notice_link(self) -> None:
        if self._notice_command == "saveSearchableRequested":
            self.saveSearchableRequested.emit()
        elif self._notice_command:
            self.noticeCommandRequested.emit(self._notice_command)

    def _build_right_rail(self) -> QFrame:
        """Thanh biểu tượng dọc: Trang · Mục lục · Tìm kiếm · Chú thích; bấm lại ngăn đang mở → ẩn ngăn."""
        rail = QFrame()
        rail.setObjectName("rightRail")
        rail.setFixedWidth(48)
        rlayout = QVBoxLayout(rail)
        rlayout.setContentsMargins(5, 8, 5, 8)
        rlayout.setSpacing(6)
        self.rail_panel_buttons: List[QPushButton] = []
        self._rail_panel_indices: List[int] = []
        for tip, icon_name, tab_idx in RAIL_PANELS:
            btn = QPushButton()
            btn.setObjectName("railPanelBtn")
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(38, 38)
            btn.setIconSize(QSize(20, 20))
            icons.bind(btn, icon_name, 20)
            btn.clicked.connect(lambda _chk=False, idx=tab_idx: self._on_rail_tab_clicked(idx))
            rlayout.addWidget(btn)
            self.rail_panel_buttons.append(btn)
            self._rail_panel_indices.append(tab_idx)
        rlayout.addStretch(1)
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
        for idx, btn in zip(self._rail_panel_indices, self.rail_panel_buttons):
            btn.blockSignals(True)
            btn.setChecked(vis and idx == cur_idx)
            btn.blockSignals(False)

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
        """Dòng thông báo theo kết quả phân tích (ảnh quét / văn bản hành chính / chữ ký số / bảng biểu)."""
        sigs, tables = self._banner_sigs, self._banner_tables
        if self.is_scanned_document:
            self.show_notice("Tài liệu ảnh quét — công cụ Chọn chữ (V) nhận dạng chữ ngay trên máy để chọn và sao chép.",
                             "Lưu thành PDF tìm kiếm được", "saveSearchableRequested")
        elif self.is_admin_document:
            sig_txt = f" có {sigs} chữ ký số / con dấu" if sigs else ""
            self.show_notice(f"Văn bản hành chính{sig_txt} — Xuất Word chuẩn NĐ30 giữ đúng thể thức.",
                             "Xuất Word chuẩn NĐ30", "convert_word_nd30")
        elif sigs > 0:
            self.show_notice(f"Tài liệu có {sigs} chữ ký số / con dấu — giữ nguyên con dấu, chữ ký khi sang Word.",
                             "Xuất Word giữ vị trí 1:1", "convert_word_exact")
        elif tables > 0:
            self.show_notice(f"Phát hiện {tables} bảng biểu — sang Word giữ nguyên đường kẻ bảng và phông chữ.",
                             "Xuất Word giữ vị trí 1:1", "convert_word_exact")
        else:
            self.hide_notice()

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
            self.toolsetChanged.emit(toolset)
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
        self.toolsetChanged.emit("")

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
        if getattr(self, "_layer_armed", False):
            self._request_ocr_layer()

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
    """Cửa sổ chính QT PDF Pro.

    - Tầng 1 (`top_bar`, `ui/top_bar.py`): Trang chủ · Mở · tab tài liệu (cùng hàng) · nhãn bản mới · ô «Tìm lệnh»
      (Ctrl+K) · nút biểu tượng Sáng/Tối · menu ☰.
    - Tầng 2 (`function_bar`, `ui/function_bar.py`, chỉ khi xem tài liệu): 5 thẻ Đọc · Chuyển đổi · Chỉnh sửa ·
      Điền & Ký · Bảo mật (Alt+1…5), công cụ của thẻ (thừa thì vào `⋯`), Chọn chữ / Bàn tay, đổi trang, thu phóng.
    - Thân: Trang chủ (`HomePage`) hoặc vùng tài liệu (`PDFDocumentTab`).
    """

    def __init__(self, settings: Optional[AppSettings] = None) -> None:
        super().__init__()
        self.settings = settings or AppSettings.load()
        self.setWindowTitle(f"{__app_name__} v{__version__} — Đọc PDF & Chuyển PDF sang Word chuẩn NĐ30")
        self.resize(1400, 880)
        self.setAcceptDrops(True)
        self._toast: Optional[QLabel] = None
        self.updater = UpdateController(self, self.settings)
        self.default_app = DefaultAppController(self, self.settings)
        self.ocr_models = OcrModelController(self, notify=lambda text: self._show_toast(text, 6000))

        self.recent_menu = QMenu("Tệp mở gần đây", self)
        self._build_command_actions()
        central = QWidget()
        central.setObjectName("appRoot")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._build_top_bar()
        root.addWidget(self.top_bar)
        root.addWidget(self._build_function_bar())
        self._build_central_area()
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._build_statusbar()
        self._apply_theme(self.settings.theme)
        self._show_home()
        self._sync_toolbar_with_active_tab()

    # ─── Lệnh: một `QAction` cho mỗi lệnh của `ui/commands.py` (dùng chung cho nút, menu, phím tắt) ───────

    def _build_command_actions(self) -> None:
        """Tạo `command_actions` từ `commands.COMMANDS`, gắn vào cửa sổ (phím tắt chạy không phụ thuộc menu) và
        tên cũ cho code / test khác."""
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
            act.setIconText(cmd.button_text())  # nút tầng 2 (`QToolButton.setDefaultAction`) hiện nhãn ngắn
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

        self.menuBar().setVisible(False)

    # ─── Tầng 1: Dải tiêu đề & tab tài liệu ────────────────────────────────

    def _build_top_bar(self) -> None:
        """Tầng 1 (`TopBar`): Trang chủ · Mở · tab tài liệu · nhãn bản mới · Tìm lệnh · Sáng/Tối · ☰."""
        self.top_bar = TopBar(self.command_actions, self.recent_menu, self)
        self.btn_home, self.btn_open = self.top_bar.btn_home, self.top_bar.btn_open
        self.btn_update_badge = self.top_bar.btn_update_badge
        self.btn_update_badge.clicked.connect(self.updater.on_badge_clicked)
        self.toolbar_search_input = self.top_bar.search
        self.btn_theme_toggle = self.top_bar.btn_theme
        self.doc_tab_bar = self.top_bar.tab_bar
        self.top_bar.paletteRequested.connect(self.action_command_palette)
        self.doc_tab_bar.tabBarClicked.connect(self._on_header_tab_clicked)
        self.doc_tab_bar.currentChanged.connect(self._on_header_tab_changed)
        self.doc_tab_bar.tabCloseRequested.connect(self.close_tab_at)
        self.doc_tab_bar.tabMoved.connect(self._on_header_tab_moved)
        self._refresh_recent_menu()

    def show_update_badge(self, text: str = "", ready: bool = False) -> None:
        """Hiện/ẩn nhãn nhắc bản mới ở thanh trên cùng (`text` rỗng = ẩn)."""
        self.top_bar.show_update_badge(text, ready)

    def _sync_tab_bar(self) -> None:
        self.doc_tab_bar.setVisible(self.doc_tab_bar.count() > 0)

    # ─── Tầng 2: Thanh chức năng ───────────────────────────────────────────

    def _build_function_bar(self) -> FunctionBar:
        """Tầng 2 (`FunctionBar`) + bí danh cũ cho cụm điều khiển xem; Alt+1…5 chuyển thẻ khi có tài liệu."""
        fb = self.function_bar = FunctionBar(self.command_actions, self)
        fb.tabRequested.connect(self.set_function_tab)
        self.page_spin, self.total_page_lbl, self.zoom_combo = fb.page_spin, fb.total_page_lbl, fb.zoom_combo
        self.btn_prev_page, self.btn_next_page = fb.btn_prev_page, fb.btn_next_page
        fb.page_spin.valueChanged.connect(self._on_spin_page_changed)
        fb.btn_prev_page.clicked.connect(self.action_prev_page)
        fb.btn_next_page.clicked.connect(self.action_next_page)
        fb.zoom_combo.activated.connect(self._on_zoom_combo_activated)
        self._tab_shortcuts: List[QShortcut] = []
        for i, (key, _label) in enumerate(commands.TABS, start=1):
            sc = QShortcut(QKeySequence(f"Alt+{i}"), self)
            sc.activated.connect(lambda k=key: self._on_tab_shortcut(k))
            self._tab_shortcuts.append(sc)
        fb.setVisible(False)
        return fb

    def _on_tab_shortcut(self, key: str) -> None:
        if self.active_tab() is None:
            return  # chưa có tài liệu → Alt+1…5 không làm gì
        self._show_documents()
        self.set_function_tab(key)

    def set_function_tab(self, key: str) -> None:
        """Chọn thẻ ở tầng 2: Chỉnh sửa / Điền & Ký bật chế độ chỉnh sửa với bộ công cụ tương ứng, thẻ khác thoát
        chế độ chỉnh sửa (về Chọn chữ / Bàn tay)."""
        if key not in commands.TAB_LAYOUT:
            return
        self.function_bar.set_tab(key)
        tab = self.active_tab()
        if tab is None:
            return
        if key == "edit":
            tab.enter_edit_mode(None, "edit")
        elif key == "fill":
            tab.enter_fill_mode()
        else:
            tab.exit_edit_mode()
        if key in ("edit", "fill") and not tab.edit_mode:  # không chỉnh sửa được (tệp không phải PDF)
            self.function_bar.set_tab("read")

    def _sync_function_tab_with_tab(self, tab: Optional[PDFDocumentTab] = None) -> None:
        """Tầng 2 theo trạng thái của tab đang xem (vào / thoát chỉnh sửa bằng đường khác, đổi tab tài liệu)."""
        tab = tab or self.active_tab()
        if tab is None or tab is not self.active_tab():
            return
        cur = self.function_bar.current_tab()
        if tab.edit_mode:
            want = tab.toolset
        else:
            want = "read" if cur in ("edit", "fill") else cur
        if want != cur:
            self.function_bar.set_tab(want)

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
        if hasattr(self, "function_bar"):
            self.function_bar.refresh_icons()
        if hasattr(self, "top_bar"):
            self.top_bar.set_theme(normalized)
            for i in range(self.doc_tab_bar.count()):
                self.doc_tab_bar.setTabIcon(i, icons.icon("file-text", size=16))
        if hasattr(self, "status_theme_lbl"):
            mode_txt = "Sáng (Light)" if normalized == "light" else "Tối (Dark)"
            self.status_theme_lbl.setText(f"Giao diện: {mode_txt}  |  ")
        if hasattr(self, "doc_tabs"):
            for i in range(self.doc_tabs.count()):
                w = self.doc_tabs.widget(i)
                if isinstance(w, PDFDocumentTab):
                    w.viewer.set_canvas_theme(normalized)
                    w.refresh_notice_icon()

    # ─── Điều hướng Trang chủ / Tài liệu ───────────────────────────────────

    def _show_home(self) -> None:
        self.stack.setCurrentWidget(self.home_page)
        self.btn_home.setChecked(True)
        self.function_bar.setVisible(False)
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
        self.function_bar.setVisible(True)
        self._sync_toolbar_with_active_tab()

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
        tab.pointerModeRequested.connect(self.set_pointer_mode)
        tab.saveSearchableRequested.connect(self.action_save_searchable)
        tab.viewer.pageChanged.connect(lambda _p: self._sync_toolbar_with_active_tab())
        tab.viewer.zoomChanged.connect(lambda _z: self._sync_toolbar_with_active_tab())
        tab.extract_page_text_btn.clicked.connect(self.action_extract_current_page_text)
        tab.noticeCommandRequested.connect(self.run_command)
        tab.toolsetChanged.connect(lambda _ts, t=tab: self._sync_function_tab_with_tab(t))
        tab.edit_toolbar.saveRequested.connect(self.action_save)
        tab.edit_toolbar.organizeRequested.connect(lambda: self.run_command("organize"))
        tab.modifiedChanged.connect(lambda _m, t=tab: self._update_tab_title(t))
        tab.modifiedChanged.connect(lambda _m: self._sync_toolbar_with_active_tab())
        tab.statusMessage.connect(lambda text: self.statusBar().showMessage(text, 6000))

        safe_tab_title = path.name.replace("&", "&&")
        idx = self.doc_tabs.addTab(tab, safe_tab_title)
        self.doc_tab_bar.blockSignals(True)
        self.doc_tab_bar.insertTab(idx, icons.icon("file-text", size=16), safe_tab_title)
        self.doc_tab_bar.setTabToolTip(idx, str(path))
        self.doc_tab_bar.blockSignals(False)
        self._sync_tab_bar()
        self.doc_tabs.setTabToolTip(idx, str(path))
        self.doc_tabs.setCurrentIndex(idx)
        self._show_documents()
        self.set_function_tab("read")  # tài liệu mới mở luôn ở thẻ Đọc

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
        self._sync_tab_bar()
        if isinstance(w, PDFDocumentTab):
            w.close_document()
            w.deleteLater()
        if self.doc_tabs.count() == 0:
            self.set_function_tab("read")
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
        self._sync_function_tab_with_tab()
        self._sync_toolbar_with_active_tab()

    def _sync_toolbar_with_active_tab(self) -> None:
        tab = self.active_tab()
        for key in ("close_tab", "save", "save_as"):  # menu ☰: chỉ bật khi có tài liệu
            self.command_actions[key].setEnabled(tab is not None)
        if tab is None:
            self.function_bar.set_page(0, 0)
            self.function_bar.set_save_visible(False)
            self.status_zoom_lbl.setText("Thu phóng: --")
            return
        total = tab.reader.page_count
        cur = tab.viewer.current_page
        self.function_bar.set_page(cur + 1, total)
        self.function_bar.set_zoom(tab.viewer.zoom_mode, tab.viewer.zoom_percent)
        self.function_bar.set_save_visible(tab.reader.has_unsaved_changes)
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
            "edit_mode": self.action_edit_mode,
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
            "fill_sign": lambda: self.set_function_tab("fill"),
        }

    def _enter_annot_tool(self, tool: str, toolset: str) -> None:
        """Chọn công cụ chú thích (bật chế độ chỉnh sửa / Điền & Ký); «Tẩy» giữ bộ công cụ đang dùng."""
        tab = self.active_tab()
        if tab is None:
            return
        if tool == "eraser" and tab.edit_mode:
            toolset = tab.toolset
        tab.enter_edit_mode(tool, toolset)

    def action_edit_mode(self) -> None:
        """Ctrl+E: thẻ «Chỉnh sửa»; đang ở đó thì về thẻ «Đọc»."""
        tab = self.active_tab()
        if tab is None:
            return
        self.set_function_tab("read" if tab.edit_mode and tab.toolset == "edit" else "edit")

    def action_fill_sign(self) -> None:
        """Ctrl+Shift+F: thẻ «Điền & Ký»; đang ở đó thì về thẻ «Đọc» (như Ctrl+E)."""
        tab = self.active_tab()
        if tab is None:
            self.run_command("fill_sign")
            return
        self.set_function_tab("read" if tab.edit_mode and tab.toolset == "fill" else "fill")

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
        mark = "● " if tab.reader.has_unsaved_changes else ""
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
                self._search_in_document(dlg.search_text)
            else:
                self.run_command(dlg.selected_key)

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

    def _search_in_document(self, query: str) -> None:
        """Tìm `query` trong tài liệu đang mở (ngăn «Tìm kiếm» bên phải)."""
        query = query.strip()
        if not query:
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
        for i in range(self.doc_tabs.count()):
            w = self.doc_tabs.widget(i)
            if isinstance(w, PDFDocumentTab):
                w.chk_overlay.blockSignals(True)
                w.chk_overlay.setChecked(checked)
                w.chk_overlay.blockSignals(False)
                w.viewer.set_show_layout_overlay(checked)
        tab = self.active_tab()
        if checked and tab is not None:  # bật lớp phủ → hiện luôn ngăn «Soi bố cục» (không có nút riêng ở thanh dọc)
            tab.sidebar_tabs.setVisible(True)
            tab.sidebar_tabs.setCurrentIndex(3)
            tab._sync_rail_buttons()

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
