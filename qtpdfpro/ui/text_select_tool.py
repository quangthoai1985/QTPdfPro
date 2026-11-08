"""Công cụ «Chọn» của khung đọc (như Acrobat): tô chọn chữ để sao chép; trang ảnh quét → kéo khung để nhận
dạng chữ (OCR) đúng vùng đó.

Gắn vào `PDFScrollViewer.set_interaction` khi chế độ con trỏ là «Chọn» (phím V); chế độ «Bàn tay» (phím H) gỡ
công cụ để chuột trái kéo cuộn trang. Lõi chọn chữ / ghép đoạn / nhận dạng vùng ở `core/text_select.py`.

- Kéo bắt đầu trên chữ → chọn theo dòng, đúng thứ tự đọc, **liền qua nhiều trang** (giữ chuột ở mép dưới khung
  đọc thì tự cuộn); kéo từ chỗ trống (hoặc giữ Alt) → khung chữ nhật trên một trang.
- Nhấp đúp = một từ, nhấp ba lần = cả dòng, Shift+nhấp = mở rộng (cả sang trang khác), Ctrl+A = cả trang.
- Ctrl+C sao chép, Ctrl+Shift+C sao chép nối dòng thành đoạn; chuột phải: menu đầy đủ.
- Trang ảnh quét (hoặc khung không có chữ thật): ảnh vùng kết xuất ở luồng giao diện, nhận dạng ở `QThread`
  (chỉ ONNX Runtime + numpy, không gọi PyMuPDF ngoài luồng chính), kết quả hiện trong bong bóng sửa được và tự
  chép vào bộ nhớ tạm. Chưa có bộ mô hình → tải ngầm qua `MainWindow.ocr_models` rồi tự nhận dạng.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import fitz  # PyMuPDF

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QKeyEvent, QKeySequence, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core import text_select as ts
from qtpdfpro.core.reader import PDFDocumentReader
from qtpdfpro.ui.ocr_layer_service import OcrLayerService, shared_ocr_engine

SELECTION_COLOR = QColor(37, 99, 235, 72)
OCR_COLOR = QColor(22, 163, 74, 64)
POPUP_WIDTH = 400

# ─── Bộ nhận dạng dùng chung (nạp mô hình một lần cho cả ứng dụng) ──────────

# `shared_ocr_engine` (OcrEngine dùng chung, nạp một lần) ở ui/ocr_layer_service.py, nhập ở đầu tệp


class _RegionOcrWorker(QThread):
    done = Signal(object)  # ts.RegionText
    failed = Signal(str)

    def __init__(self, region: ts.RegionImage, engine_factory: Callable[[], object], parent: QObject | None = None):
        super().__init__(parent)
        self.region = region
        self._engine_factory = engine_factory

    def run(self) -> None:
        try:
            self.done.emit(ts.recognize_region(self._engine_factory(), self.region))
        except Exception as exc:  # báo về luồng giao diện
            self.failed.emit(str(exc))


# ─── Bong bóng kết quả nhận dạng ───────────────────────────────────────────


class OcrResultPopup(QFrame):
    """Bong bóng nổi trên khung đọc: trạng thái nhận dạng + chữ đọc được (sửa được) + nút Sao chép.

    Kéo phần tiêu đề / nền để dời bong bóng đi chỗ khác (`user_moved` — từ đó công cụ không tự đặt lại vị trí cho tới
    lần nhận dạng sau)."""

    copyRequested = Signal()
    joinToggled = Signal(bool)
    closeRequested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("ocrPopup")  # màu nền / viền theo giao diện Sáng / Tối: ui/theme.py
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(POPUP_WIDTH)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Kéo để dời bong bóng")
        self.user_moved = False
        self._drag_offset: Optional[QPoint] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        head = QHBoxLayout()
        self.title_lbl = QLabel()
        self.title_lbl.setWordWrap(True)
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("ghostIconBtn")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setToolTip("Đóng (Esc)")
        self.btn_close.clicked.connect(self.closeRequested)
        head.addWidget(self.title_lbl, 1)
        head.addWidget(self.btn_close, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        lay.addWidget(self.progress)
        self.text_edit = QPlainTextEdit()
        self.text_edit.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.text_edit.setToolTip("")
        lay.addWidget(self.text_edit)
        row = QHBoxLayout()
        self.chk_join = QCheckBox("Nối dòng thành đoạn")
        self.chk_join.setToolTip("Gộp các dòng bị ngắt giữa câu thành đoạn liền (dán vào Word gọn hơn)")
        self.chk_join.toggled.connect(self.joinToggled)
        self.btn_copy = QPushButton("📋 Sao chép")
        self.btn_copy.setObjectName("primaryConvertBtn")
        self.btn_copy.clicked.connect(self.copyRequested)
        row.addWidget(self.chk_join)
        row.addStretch(1)
        row.addWidget(self.btn_copy)
        lay.addLayout(row)
        self.hide()

    def show_busy(self, text: str, done: int = 0, total: int = 0) -> None:
        self.title_lbl.setText(text)
        self.progress.setVisible(True)
        if total > 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(done * 1000 / total))
        else:
            self.progress.setRange(0, 0)  # chạy vòng
        self.text_edit.setVisible(False)
        self.chk_join.setVisible(False)
        self.btn_copy.setVisible(False)
        self._show()

    def show_result(self, title: str, text: str) -> None:
        self.title_lbl.setText(title)
        self.progress.setVisible(False)
        self.set_text(text)
        for w in (self.text_edit, self.chk_join, self.btn_copy):
            w.setVisible(True)
        self._show()

    def set_text(self, text: str) -> None:
        """Đặt chữ và co ô nhập theo số dòng (tối đa ~8 dòng, dài hơn thì cuộn)."""
        self.text_edit.setPlainText(text)
        lines = max(2, min(8, text.count("\n") + 1 + len(text) // 60))
        self.text_edit.setFixedHeight(lines * self.text_edit.fontMetrics().lineSpacing() + 30)
        self.adjustSize()

    def show_message(self, text: str) -> None:
        self.title_lbl.setText(text)
        for w in (self.progress, self.text_edit, self.chk_join, self.btn_copy):
            w.setVisible(False)
        self._show()

    def text(self) -> str:
        return self.text_edit.toPlainText()

    # Kéo để dời (nhấn trên tiêu đề / nền — các ô nhập, nút tự xử lý chuột của chúng)
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            parent = self.parentWidget()
            pos = self.mapToParent(event.position().toPoint()) - self._drag_offset
            if parent is not None:
                pos.setX(min(max(0, pos.x()), max(0, parent.width() - self.width())))
                pos.setY(min(max(0, pos.y()), max(0, parent.height() - self.height())))
            self.move(pos)
            self.user_moved = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if self._drag_offset is not None:
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _show(self) -> None:
        self.adjustSize()
        self.show()
        self.raise_()


def place_beside(target: QRect, w: int, h: int, area_w: int, area_h: int, gap: int = 8) -> QPoint:
    """Góc trên-trái cho bong bóng `w`×`h` đặt cạnh vùng `target` trong khung `area_w`×`area_h` mà không che vùng đó:
    thử dưới → phải → trái → trên (phía trên thường là đoạn chữ người dùng vừa đọc); không chỗ nào đủ thì chọn chỗ
    che ít nhất."""
    def clamp(v: int, lo: int, hi: int) -> int:
        return min(max(lo, v), max(lo, hi))

    x_al = clamp(target.left(), gap, area_w - w - gap)
    y_al = clamp(target.top(), gap, area_h - h - gap)
    cands = [
        QPoint(x_al, target.bottom() + gap),
        QPoint(target.right() + gap, y_al),
        QPoint(target.left() - w - gap, y_al),
        QPoint(x_al, target.top() - h - gap),
    ]
    area = QRect(0, 0, area_w, area_h)
    for c in cands:
        box = QRect(c.x(), c.y(), w, h)
        if area.contains(box) and not box.intersects(target):
            return c

    def overlap(c: QPoint) -> int:
        box = QRect(clamp(c.x(), gap, area_w - w - gap), clamp(c.y(), gap, area_h - h - gap), w, h)
        inter = box.intersected(target)
        return inter.width() * inter.height() if not inter.isEmpty() else 0

    best = min(cands, key=overlap)
    return QPoint(clamp(best.x(), gap, area_w - w - gap), clamp(best.y(), gap, area_h - h - gap))


# ─── Công cụ Chọn ──────────────────────────────────────────────────────────


@dataclass
class _Drag:
    page: int
    start: fitz.Point
    current: fitz.Point
    mode: str  # "text" (theo dòng chữ) | "area" (khung chữ nhật)
    current_page: int = -1  # trang dưới con trỏ khi kéo chọn chữ (≠ `page` khi kéo sang trang khác)


class TextSelectTool(QObject):
    """Bộ xử lý chuột «Chọn chữ» (giao diện `CanvasInteraction` của `PDFScrollViewer`)."""

    message = Signal(str)
    selectionChanged = Signal()
    highlightRequested = Signal(int, list)  # trang, khung dòng (toạ độ trang chưa xoay)
    searchRequested = Signal(str)
    pointerModeRequested = Signal(str)  # "hand" từ menu chuột phải
    saveSearchableRequested = Signal()  # menu chuột phải trên trang ảnh quét → «Lưu thành PDF tìm kiếm được»

    def __init__(
        self,
        reader: PDFDocumentReader,
        models_provider: Optional[Callable[[], object]] = None,
        parent: QObject | None = None,
        layer: Optional[OcrLayerService] = None,
    ) -> None:
        super().__init__(parent)
        self.reader = reader
        self.models_provider = models_provider  # → OcrModelController (MainWindow.ocr_models) hoặc None
        self.layer = layer  # lớp chữ nhận dạng ngầm của trang ảnh quét (Đợt 2)
        self.engine_factory: Callable[[], object] = shared_ocr_engine  # test thay bằng engine giả
        self.join_lines = False
        self.viewer = None
        self._words: Dict[int, List[ts.Word]] = {}
        self._scanned: Dict[int, bool] = {}
        self._drag: Optional[_Drag] = None
        self._sel_page: Optional[int] = None  # trang đầu của vùng chọn (vùng nhận dạng: trang của vùng)
        self._sel_map: Dict[int, List[ts.Word]] = {}  # trang → từ đã chọn (nhiều trang khi kéo liền qua trang)
        self._sel_area: Optional[fitz.Rect] = None  # khung đã kéo (chọn vùng / vùng nhận dạng)
        self._anchor: Optional[fitz.Point] = None  # điểm đầu để Shift+nhấp mở rộng
        self._anchor_page: Optional[int] = None
        self._ocr: Optional[ts.RegionText] = None
        self._ocr_target: Optional[tuple] = None  # (trang, khung) đang / sẽ nhận dạng
        self._ocr_queued = False
        self._worker: Optional[_RegionOcrWorker] = None
        self._waiting_models = False
        self._models_connected = None
        self._last_double: Optional[tuple] = None  # (thời điểm, trang, điểm) — nhận nhấp ba lần
        self._hover_cursor = Qt.CursorShape.IBeamCursor
        self._popup: Optional[OcrResultPopup] = None
        self._scroll_hooked = False

    # ─── Dữ liệu trang ────────────────────────────────────────────────────

    def words(self, page_index: int) -> List[ts.Word]:
        """Từ của trang: chữ thật của PDF; trang ảnh quét đã nhận dạng ngầm thì là từ của lớp chữ nhận dạng."""
        if self.layer is not None and self.is_scanned(page_index):
            layer_words = self.layer.words(page_index)
            if layer_words is not None:
                return layer_words
        if page_index not in self._words:
            try:
                self._words[page_index] = ts.page_words(self.reader.doc[page_index])
            except Exception:
                self._words[page_index] = []
        return self._words[page_index]

    def is_scanned(self, page_index: int) -> bool:
        if page_index not in self._scanned:
            try:
                self._scanned[page_index] = ts.is_scanned_page(self.reader.doc[page_index])
            except Exception:
                self._scanned[page_index] = False
        return self._scanned[page_index]

    def needs_ocr(self, page_index: int) -> bool:
        """Trang ảnh quét CHƯA có lớp chữ nhận dạng → kéo chuột = khung nhận dạng vùng (Đợt 1)."""
        return self.is_scanned(page_index) and not (self.layer is not None and self.layer.has_layer(page_index))

    def request_layer(self, page_index: int) -> bool:
        """Xin nhận dạng ngầm trang (khi máy đã có bộ mô hình)."""
        return self.layer.request(page_index) if self.layer is not None else False

    def on_layer_ready(self, page_index: int) -> None:
        """Lớp chữ của trang vừa xong: từ đó chọn chữ như PDF thường."""
        self._words.pop(page_index, None)
        if self._sel_page == page_index and self._ocr is None and not self.ocr_busy:
            self._set_selection(None, [])
        self._repaint()

    def reset(self) -> None:
        """Tài liệu vừa mở lại / đổi trang → bỏ bộ nhớ đệm từ và vùng chọn."""
        self._words.clear()
        self._scanned.clear()
        self.clear_selection()

    # ─── Vùng chọn ────────────────────────────────────────────────────────

    @property
    def has_selection(self) -> bool:
        return any(self._sel_map.values()) or self._ocr is not None

    @property
    def selection_page(self) -> Optional[int]:
        return self._sel_page

    @property
    def selection_pages(self) -> List[int]:
        """Các trang có chữ đang chọn (theo thứ tự trang)."""
        if self._ocr is not None:
            return [self._ocr.page_index]
        return sorted(p for p, w in self._sel_map.items() if w)

    @property
    def ocr_result(self) -> Optional[ts.RegionText]:
        return self._ocr

    @property
    def ocr_busy(self) -> bool:
        return self._worker is not None or self._waiting_models

    @property
    def popup(self) -> Optional[OcrResultPopup]:
        return self._popup

    def selection_rects(self, page_index: Optional[int] = None) -> List[fitz.Rect]:
        """Khung tô của vùng chọn trên trang `page_index` (mặc định: trang đầu của vùng chọn)."""
        if self._ocr is not None:
            return list(self._ocr.page_rects) if page_index in (None, self._ocr.page_index) else []
        page = self._sel_page if page_index is None else page_index
        return ts.selection_rects(self._sel_map.get(page, [])) if page is not None else []

    def selected_text(self, join_lines: Optional[bool] = None) -> str:
        """Chữ đang chọn. `join_lines=None`: như đang hiển thị (chữ chọn trên trang: giữ ngắt dòng; chữ nhận dạng:
        đúng nội dung bong bóng, kể cả chỗ người dùng đã sửa)."""
        if self._ocr is not None:
            popup = self._popup
            popup_join = popup.chk_join.isChecked() if popup is not None else self.join_lines
            shown = popup is not None and popup.isVisible() and popup.text_edit.isVisible()
            if shown and (join_lines is None or join_lines == popup_join):
                return popup.text().strip()
            return self._ocr.text(popup_join if join_lines is None else join_lines)
        join = bool(join_lines)
        return ts.join_page_texts([ts.selection_text(self._sel_map[p], join) for p in self.selection_pages], join)

    def _set_selection(self, page_index: Optional[int], words: List[ts.Word], area: Optional[fitz.Rect] = None) -> None:
        self._sel_page = page_index
        self._sel_map = {page_index: list(words)} if page_index is not None and words else {}
        self._sel_area = area
        self._ocr = None
        self.selectionChanged.emit()
        self._repaint()

    def _set_multi_selection(self, sel: Dict[int, List[ts.Word]]) -> None:
        """Vùng chọn chữ qua nhiều trang (kéo liền / Shift+nhấp sang trang khác)."""
        self._sel_map = {p: list(w) for p, w in sorted(sel.items()) if w}
        self._sel_page = min(self._sel_map) if self._sel_map else None
        self._sel_area = None
        self._ocr = None
        self.selectionChanged.emit()
        self._repaint()

    def clear_selection(self) -> None:
        self._drag = None
        self._anchor = None
        self._anchor_page = None
        self._ocr_target = None
        self._ocr_queued = False
        self._waiting_models = False
        self._set_selection(None, [])
        if self._popup is not None:
            self._popup.hide()

    def select_all(self, page_index: int) -> None:
        if not 0 <= page_index < self.reader.page_count:
            return
        if self.needs_ocr(page_index):
            self.request_layer(page_index)
            self.message.emit("Trang ảnh quét chưa nhận dạng xong — kéo khung quanh chữ (hoặc chuột phải › "
                              "Nhận dạng chữ cả trang).")
            return
        words = self.words(page_index)
        self._set_selection(page_index, words)
        self._announce()

    def bounding_rect(self) -> Optional[fitz.Rect]:
        """Khung bao vùng chọn trên trang đầu (toạ độ trang chưa xoay) — cho «Sao chép ảnh» / «Nhận dạng vùng này» /
        đặt bong bóng."""
        if self._sel_area is not None:
            return fitz.Rect(self._sel_area)
        rects = self.selection_rects()
        if not rects:
            return None
        out = fitz.Rect(rects[0])
        for r in rects[1:]:
            out |= r
        return out + (-2, -2, 2, 2)

    def copy(self, join_lines: Optional[bool] = None) -> bool:
        text = self.selected_text(join_lines)
        if not text:
            self.message.emit("Chưa chọn chữ nào — kéo chuột qua chữ cần sao chép.")
            return False
        QGuiApplication.clipboard().setText(text)
        joined = " (đã nối dòng thành đoạn)" if join_lines else ""
        self.message.emit(f"Đã sao chép {len(text):,} ký tự{joined}.".replace(",", "."))
        return True

    def copy_image(self) -> bool:
        rect = self.bounding_rect()
        if rect is None or self._sel_page is None or len(self.selection_pages) > 1:
            return False
        try:
            region = ts.render_region(self.reader.doc[self._sel_page], rect, dpi=200,
                                      view_rotation=self.reader.get_page_rotation(self._sel_page))
            img = QImage.fromData(ts.region_png(region), "PNG")
        except Exception as exc:
            self.message.emit(f"Không chụp được ảnh vùng chọn: {exc}")
            return False
        QGuiApplication.clipboard().setImage(img)
        self.message.emit(f"Đã sao chép ảnh vùng chọn ({img.width()}×{img.height()} điểm ảnh, 200 dpi).")
        return True

    def _announce(self) -> None:
        text = self.selected_text()
        if text:
            self.message.emit(f"Đã chọn {len(text):,} ký tự — Ctrl+C để sao chép, chuột phải để xem thêm."
                              .replace(",", "."))

    # ─── Nhận dạng vùng (trang ảnh quét) ──────────────────────────────────

    def recognize(self, page_index: int, rect: fitz.Rect) -> None:
        """Nhận dạng chữ trong khung `rect` của trang (kết quả: bong bóng + tự chép vào bộ nhớ tạm)."""
        rect = fitz.Rect(rect).normalize()
        self._set_selection(page_index, [], rect)
        self._ocr_target = (page_index, rect)
        popup = self._ensure_popup()
        popup.user_moved = False  # vùng mới → đặt bong bóng lại cạnh vùng chọn
        models = self.models_provider() if self.models_provider is not None else None
        if models is not None:
            self._connect_models(models)
            if not models.ensure_started():
                self._waiting_models = True
                popup.show_busy("⏳ Lần đầu dùng: đang tải bộ mô hình OCR tiếng Việt (~88 MB, chỉ tải một lần)… "
                                "Tải xong sẽ tự nhận dạng vùng này.", models.done_bytes, models.total_bytes)
                self._place_popup()
                return
        popup.show_busy("⏳ Đang nhận dạng chữ trong vùng chọn…")
        self._place_popup()
        self._start_worker()

    def _connect_models(self, models) -> None:
        if self._models_connected is models:
            return
        self._models_connected = models
        models.progress.connect(self._on_models_progress)
        models.finished.connect(self._on_models_finished)

    def _on_models_progress(self, done: int, total: int) -> None:
        if self._waiting_models and self._popup is not None:
            mb = lambda v: f"{v / 1048576:.1f}".replace(".", ",")  # noqa: E731
            self._popup.show_busy(f"⏳ Đang tải bộ mô hình OCR tiếng Việt: {mb(done)} / {mb(total)} MB… "
                                  "Tải xong sẽ tự nhận dạng vùng này.", done, total)

    def _on_models_finished(self, ok: bool, message: str) -> None:
        if not self._waiting_models:
            return
        self._waiting_models = False
        if ok and self._ocr_target is not None:
            if self._popup is not None:
                self._popup.show_busy("⏳ Đang nhận dạng chữ trong vùng chọn…")
            self._start_worker()
            self.request_layer(self._ocr_target[0])  # có mô hình rồi → nhận dạng ngầm cả trang luôn
        elif self._popup is not None:
            self._popup.show_message(f"⚠️ Chưa tải được bộ mô hình OCR: {message}" if message
                                     else "Đã huỷ tải bộ mô hình OCR.")

    def _start_worker(self) -> None:
        if self._ocr_target is None:
            return
        if self._worker is not None:  # đang nhận dạng vùng trước → nhận dạng vùng mới ngay sau đó
            self._ocr_queued = True
            return
        page_index, rect = self._ocr_target
        try:
            region = ts.render_region(self.reader.doc[page_index], rect,
                                      view_rotation=self.reader.get_page_rotation(page_index))
        except Exception as exc:
            if self._popup is not None:
                self._popup.show_message(f"⚠️ Không đọc được vùng chọn: {exc}")
            return
        worker = _RegionOcrWorker(region, self.engine_factory, self)
        worker.done.connect(self._on_ocr_done)
        worker.failed.connect(self._on_ocr_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def _on_worker_finished(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        if self._ocr_queued:
            self._ocr_queued = False
            self._start_worker()

    def _on_ocr_done(self, res: ts.RegionText) -> None:
        target = self._ocr_target
        if self._ocr_queued or target is None or target[0] != res.page_index:
            return  # người dùng đã chọn vùng khác / huỷ
        popup = self._ensure_popup()
        if not res.lines:
            self._ocr = None
            popup.show_message("Không thấy chữ trong vùng chọn — thử kéo khung rộng hơn quanh dòng chữ.")
            self._place_popup()
            self._repaint()
            return
        self._ocr = res
        popup.chk_join.blockSignals(True)
        popup.chk_join.setChecked(self.join_lines)
        popup.chk_join.blockSignals(False)
        secs = f"{res.seconds:.1f}".replace(".", ",")
        popup.show_result(f"🔤 Đã nhận dạng {len(res.lines)} dòng ({secs} giây) và chép vào bộ nhớ tạm — "
                          "sửa được trước khi chép lại.", res.text(self.join_lines))
        self._place_popup()
        QGuiApplication.clipboard().setText(res.text(self.join_lines))
        self.message.emit(f"Đã nhận dạng {len(res.lines)} dòng chữ trong vùng chọn — đã chép vào bộ nhớ tạm (Ctrl+V để dán).")
        self.selectionChanged.emit()
        self._repaint()

    def _on_ocr_failed(self, message: str) -> None:
        if self._popup is not None:
            self._popup.show_message(f"⚠️ Không nhận dạng được: {message}")
            self._place_popup()

    def wait_ocr(self) -> None:
        """Đợi nhận dạng xong và xử lý tín hiệu (kiểm thử)."""
        for _ in range(50):
            worker = self._worker
            if worker is None:
                break
            worker.wait()
            QApplication.processEvents()
        QApplication.processEvents()

    def cancel(self) -> None:
        """Đóng tab: đợi luồng nhận dạng đang chạy dừng."""
        self._ocr_target = None
        self._ocr_queued = False
        if self._worker is not None:
            self._worker.wait()

    # ─── Bong bóng ────────────────────────────────────────────────────────

    def _ensure_popup(self) -> OcrResultPopup:
        if self._popup is None:
            parent = self.viewer.viewport() if self.viewer is not None else None
            self._popup = OcrResultPopup(parent)
            self._popup.copyRequested.connect(self._copy_from_popup)
            self._popup.joinToggled.connect(self._on_popup_join)
            self._popup.closeRequested.connect(self._close_popup)
        return self._popup

    def _copy_from_popup(self) -> None:
        if self._popup is None:
            return
        text = self._popup.text().strip()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.message.emit(f"Đã sao chép {len(text):,} ký tự chữ nhận dạng.".replace(",", "."))

    def _on_popup_join(self, on: bool) -> None:
        self.join_lines = bool(on)
        if self._ocr is not None and self._popup is not None:
            self._popup.set_text(self._ocr.text(self.join_lines))
            self._place_popup()

    def _close_popup(self) -> None:
        if self._popup is not None:
            self._popup.hide()

    def _place_popup(self) -> None:
        popup, viewer = self._popup, self.viewer
        if popup is None or viewer is None or not popup.isVisible() or self._sel_page is None or popup.user_moved:
            return
        rect = self.bounding_rect()
        vp = viewer.viewport()
        popup.adjustSize()
        if rect is None:
            popup.move(vp.width() - popup.width() - 12, 12)
            return
        wr = viewer.page_rect_to_widget(self._sel_page, rect).translated(QPointF(viewer.widget().pos()))
        popup.move(place_beside(wr.toAlignedRect(), popup.width(), popup.height(), vp.width(), vp.height()))

    def _hook_viewer(self, viewer) -> None:
        self.viewer = viewer
        if not self._scroll_hooked:
            self._scroll_hooked = True
            viewer.verticalScrollBar().valueChanged.connect(lambda _v: self._place_popup())
            viewer.horizontalScrollBar().valueChanged.connect(lambda _v: self._place_popup())

    def _repaint(self) -> None:
        if self.viewer is not None:
            self.viewer.widget().update()

    # ─── Giao diện CanvasInteraction ─────────────────────────────────────

    def cursor(self) -> Qt.CursorShape:
        return self._hover_cursor

    def _cursor_for(self, page_index: Optional[int], pt: Optional[fitz.Point]) -> Qt.CursorShape:
        if page_index is None or pt is None:
            return Qt.CursorShape.ArrowCursor
        if self.needs_ocr(page_index) or not ts.near_text(self.words(page_index), pt):
            return Qt.CursorShape.CrossCursor
        return Qt.CursorShape.IBeamCursor

    def _pointer_target(self, viewer, page_index: Optional[int], pt: Optional[fitz.Point], event) -> tuple:
        """(trang, điểm trên trang đó) dưới con trỏ khi đang kéo — khung đọc chỉ báo toạ độ theo trang lúc nhấn chuột;
        kéo sang trang khác (kể cả khe giữa hai trang, hoặc ra ngoài vùng trang) thì lấy trang gần con trỏ nhất."""
        page_near = getattr(viewer, "page_near", None)
        if page_near is not None and event is not None:
            pos = event.position()
            near = page_near(pos)
            if near is not None:
                return near, viewer.widget_to_page(near, pos)
        return page_index, pt

    def _text_range(self, page0: int, p0, page1: int, p1) -> Dict[int, List[ts.Word]]:
        return ts.select_pages_range(self._range_words, page0, p0, page1, p1)

    def _range_words(self, page_index: int) -> List[ts.Word]:
        """Từ của trang để chọn liền qua trang: trang ảnh quét chưa nhận dạng thì không có từ (bỏ qua)."""
        if not 0 <= page_index < self.reader.page_count or self.needs_ocr(page_index):
            return []
        return self.words(page_index)

    def press(self, viewer, page_index: int, pt: fitz.Point, event: QMouseEvent) -> None:
        self._hook_viewer(viewer)
        mods = event.modifiers()
        now = time.monotonic()
        last = self._last_double
        if (last is not None and last[1] == page_index and now - last[0] <= QApplication.doubleClickInterval() / 1000
                and math.hypot(pt.x - last[2].x, pt.y - last[2].y) < 4 and not self.needs_ocr(page_index)):
            self._last_double = None
            line = ts.select_line(self.words(page_index), pt)  # nhấp ba lần → cả dòng
            if line:
                self._set_selection(page_index, line)
                self._announce()
            return
        scanned = self.needs_ocr(page_index)  # trang ảnh quét chưa có lớp chữ nhận dạng
        words = self.words(page_index)
        if (mods & Qt.KeyboardModifier.ShiftModifier and self._anchor is not None and self._anchor_page is not None
                and not scanned and self._ocr is None):
            a_page = self._anchor_page
            self._drag = _Drag(a_page, fitz.Point(self._anchor), pt, "text", page_index)
            self._set_multi_selection(self._text_range(a_page, self._anchor, page_index, pt))
            return
        if self._popup is not None and not self.ocr_busy:
            self._popup.hide()
        area = bool(mods & Qt.KeyboardModifier.AltModifier) or scanned or not ts.near_text(words, pt)
        self._drag = _Drag(page_index, fitz.Point(pt), fitz.Point(pt), "area" if area else "text", page_index)
        if scanned:
            self.request_layer(page_index)
            busy = self.layer is not None and self.layer.busy_page == page_index
            self.message.emit("Trang ảnh quét đang được nhận dạng ngầm — trong lúc chờ, kéo khung quanh chữ để nhận "
                              "dạng ngay vùng đó." if busy else
                              "Trang ảnh quét — kéo khung quanh chữ cần chép, chữ sẽ được nhận dạng (OCR).")

    def move(self, viewer, page_index: Optional[int], pt: Optional[fitz.Point], event: QMouseEvent,
             dragging: bool) -> None:
        self._hook_viewer(viewer)
        d = self._drag
        if not dragging or d is None or pt is None:
            shape = self._cursor_for(page_index, pt)
            if shape != self._hover_cursor:
                self._hover_cursor = shape
                viewer.refresh_cursor(shape)
            return
        if d.mode == "text":
            cur, cpt = self._pointer_target(viewer, page_index, pt, event)
            d.current_page, d.current = cur, fitz.Point(cpt)
            self._sel_map = self._text_range(d.page, d.start, cur, cpt)
            self._sel_page = min(self._sel_map) if self._sel_map else None
            self._sel_area, self._ocr = None, None
            return
        d.current = fitz.Point(pt)
        if not self.needs_ocr(d.page):
            area = fitz.Rect(d.start, pt).normalize()
            picked = ts.select_area(self.words(d.page), area)
            self._sel_page, self._sel_area, self._ocr = d.page, None, None
            self._sel_map = {d.page: picked} if picked else {}

    def release(self, viewer, page_index: int, pt: fitz.Point, event: QMouseEvent) -> None:
        d, self._drag = self._drag, None
        if d is None:
            return
        cur, cpt = self._pointer_target(viewer, page_index, pt, event) if d.mode == "text" else (page_index, pt)
        moved = math.hypot(cpt.x - d.start.x, cpt.y - d.start.y) if cur == d.page else float("inf")
        if moved < 1.5:  # nhấp chuột: bỏ chọn
            if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._anchor, self._anchor_page = fitz.Point(pt), page_index
                self._set_selection(None, [])
            return
        words = self.words(d.page)
        if d.mode == "text":
            self._anchor, self._anchor_page = fitz.Point(d.start), d.page
            self._set_multi_selection(self._text_range(d.page, d.start, cur, cpt))
            self._announce()
            return
        rect = fitz.Rect(d.start, pt).normalize()
        picked = [] if self.needs_ocr(d.page) else ts.select_area(words, rect)
        if picked:
            self._set_selection(d.page, picked, rect)
            self._announce()
        elif rect.width >= ts.MIN_OCR_SIDE_PT and rect.height >= ts.MIN_OCR_SIDE_PT:
            self.recognize(d.page, rect)  # trang ảnh quét / khung không có chữ thật → nhận dạng
        else:
            self._set_selection(None, [])

    def double_click(self, viewer, page_index: int, pt: fitz.Point, event: QMouseEvent) -> None:
        self._hook_viewer(viewer)
        self._last_double = (time.monotonic(), page_index, fitz.Point(pt))
        if self.needs_ocr(page_index):
            return
        word = ts.select_word(self.words(page_index), pt)
        if word:
            self._anchor = fitz.Point(word[0][0], (word[0][1] + word[0][3]) / 2)
            self._anchor_page = page_index
            self._set_selection(page_index, word)
            self._announce()

    def key_press(self, viewer, event: QKeyEvent) -> bool:
        self._hook_viewer(viewer)
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy(None)
            return True
        ctrl_shift = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        if event.key() == Qt.Key.Key_C and (event.modifiers() & ctrl_shift) == ctrl_shift:
            self.copy(True)
            return True
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.select_all(viewer.current_page)
            return True
        if event.key() == Qt.Key.Key_Escape and (self.has_selection or (self._popup and self._popup.isVisible())):
            self.clear_selection()
            return True
        return False

    def paint(self, viewer, painter: QPainter, page_index: int) -> None:
        t = viewer.page_transform(page_index)
        d = self._drag
        color = OCR_COLOR if self._ocr is not None else SELECTION_COLOR
        for r in self.selection_rects(page_index):
            painter.fillRect(viewer.page_rect_to_widget(page_index, r, t), color)
        if self._sel_page == page_index:
            target = self._ocr_target
            if target is not None and target[0] == page_index and (self.ocr_busy or self._ocr is not None):
                painter.setPen(QPen(QColor("#16A34A"), 1.2, Qt.PenStyle.DashLine))
                painter.setBrush(QBrush(QColor(22, 163, 74, 18 if self._ocr is not None else 36)))
                painter.drawRect(viewer.page_rect_to_widget(page_index, target[1], t))
        if d is not None and d.page == page_index and d.mode == "area":
            painter.setPen(QPen(QColor("#2563EB"), 1.0, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(37, 99, 235, 24)))
            painter.drawRect(viewer.page_rect_to_widget(page_index, fitz.Rect(d.start, d.current).normalize(), t))
        if self.layer is not None and self.layer.busy_page == page_index:
            self._paint_busy_chip(viewer, painter, page_index)

    def _paint_busy_chip(self, viewer, painter: QPainter, page_index: int) -> None:
        """Nhãn nhỏ góc trên-phải trang: đang nhận dạng ngầm."""
        prect = viewer._page_rects_px[page_index]
        text = "⏳ Đang nhận dạng chữ…"
        fm = painter.fontMetrics()
        w, h = fm.horizontalAdvance(text) + 18, fm.height() + 10
        chip = QRectF(prect.right() - w - 10, prect.top() + 10, w, h)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(15, 23, 42, 200)))
        painter.drawRoundedRect(chip, h / 2, h / 2)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def context_menu(self, viewer, page_index: Optional[int], pt: Optional[fitz.Point], global_pos: QPoint) -> None:
        self._hook_viewer(viewer)
        menu = self.build_context_menu(page_index, viewer)
        menu.exec(global_pos)

    def build_context_menu(self, page_index: Optional[int], parent: QWidget | None = None) -> QMenu:
        """Menu chuột phải (tách riêng để kiểm thử không phải mở menu modal)."""
        menu = QMenu(parent)
        text = self.selected_text()
        has_text = bool(text)
        a = menu.addAction("📋 Sao chép\tCtrl+C", lambda: self.copy(None))
        a.setEnabled(has_text)
        a = menu.addAction("📋 Sao chép nối dòng thành đoạn\tCtrl+Shift+C", lambda: self.copy(True))
        a.setEnabled(has_text)
        pages = self.selection_pages
        a = menu.addAction("🖼 Sao chép ảnh vùng chọn", self.copy_image)
        a.setEnabled(self.bounding_rect() is not None and len(pages) <= 1)
        if len(pages) > 1:
            a.setToolTip("Chỉ chụp được ảnh vùng chọn nằm trên một trang")
        menu.addSeparator()
        sel_page = self._sel_page
        by_page = {p: ts.selection_rects(self._sel_map[p]) for p in pages} if self._ocr is None else {}

        def _highlight() -> None:
            for p, rs in by_page.items():
                if rs:
                    self.highlightRequested.emit(p, rs)
            self.clear_selection()

        a = menu.addAction("🖍 Tô sáng vùng chọn", _highlight)
        a.setEnabled(any(by_page.values()))
        short = " ".join(text.split())
        a = menu.addAction(f"🔎 Tìm «{short[:30]}{'…' if len(short) > 30 else ''}» trong tài liệu",
                           lambda: self.searchRequested.emit(short))
        a.setEnabled(has_text and len(short) <= 120)
        rect = self.bounding_rect()
        a = menu.addAction("🔤 Nhận dạng chữ (OCR) vùng này",
                           lambda: self.recognize(sel_page, rect) if sel_page is not None and rect else None)
        a.setEnabled(rect is not None and sel_page is not None and self._ocr is None and not self.ocr_busy)
        a.setToolTip("Dùng khi chữ chép ra bị lỗi phông / mã hoá, hoặc vùng là ảnh")
        if page_index is not None and self.is_scanned(page_index):
            page = self.reader.doc[page_index]
            full = page.rect * page.derotation_matrix
            a = menu.addAction("🔤 Nhận dạng chữ cả trang này (OCR)", lambda: self.recognize(page_index, full))
            a.setEnabled(not self.ocr_busy)
            menu.addAction("💾 Lưu thành PDF tìm kiếm được…", self.saveSearchableRequested.emit)
        menu.addSeparator()
        if page_index is not None:
            menu.addAction("Chọn tất cả chữ trên trang\tCtrl+A", lambda: self.select_all(page_index))
        menu.addAction("✋ Chuyển sang Bàn tay (kéo để cuộn)\tH", lambda: self.pointerModeRequested.emit("hand"))
        return menu
