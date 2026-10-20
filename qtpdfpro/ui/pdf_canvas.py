"""Khung vẽ và cuộn trang PDF tốc độ cao (PDF Canvas & Viewport).

Hỗ trợ:
- Cuộn liên tục (Continuous Scroll) chỉ kết xuất các trang nằm trong vùng nhìn thấy (Lazy Viewport Rendering)
- Xem từng trang (Single Page Mode)
- Thu phóng theo phần trăm (25% – 400%), Vừa chiều ngang (Fit Width), Vừa trang (Fit Page), Ctrl + Cuộn chuột
- Lớp phủ tô sáng kết quả tìm kiếm (Search Highlights)
- Lớp phủ soi khung bố cục trực quan (Layout Inspector Overlay: Văn bản, Bảng biểu, Hình ảnh, Vector)
- Bộ xử lý thao tác chuột tuỳ chọn (`set_interaction`) cho công cụ chú thích: nhận toạ độ trang chưa xoay
  (hệ của PyMuPDF), vẽ xem trước lên trang; chuột giữa luôn dùng để kéo cuộn
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Protocol, Tuple

import fitz  # PyMuPDF

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QScrollArea, QWidget

from qtpdfpro.core.layout_analyzer import BBox
from qtpdfpro.core.reader import PDFDocumentReader, SearchHit


class CanvasInteraction(Protocol):
    """Giao diện bộ xử lý chuột gắn vào `PDFScrollViewer.set_interaction` (vd công cụ chú thích).

    `pt` là toạ độ trang **chưa xoay** (cùng hệ với chú thích PyMuPDF); khi đang kéo, `page_index` giữ nguyên
    trang lúc bấm chuột kể cả khi con trỏ ra ngoài trang.
    """

    def press(self, viewer: "PDFScrollViewer", page_index: int, pt: fitz.Point, event: QMouseEvent) -> None: ...

    def move(self, viewer: "PDFScrollViewer", page_index: Optional[int], pt: Optional[fitz.Point],
             event: QMouseEvent, dragging: bool) -> None: ...

    def release(self, viewer: "PDFScrollViewer", page_index: int, pt: fitz.Point, event: QMouseEvent) -> None: ...

    def double_click(self, viewer: "PDFScrollViewer", page_index: int, pt: fitz.Point, event: QMouseEvent) -> None: ...

    def key_press(self, viewer: "PDFScrollViewer", event: QKeyEvent) -> bool: ...

    def paint(self, viewer: "PDFScrollViewer", painter: QPainter, page_index: int) -> None: ...

    def cursor(self) -> Qt.CursorShape: ...


class _PageDrawSurface(QWidget):
    """Bề mặt vẽ nội bộ nằm trong QScrollArea."""

    def __init__(self, canvas: "PDFScrollViewer") -> None:
        super().__init__(canvas)
        self._canvas = canvas
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def paintEvent(self, event: QPaintEvent) -> None:
        self._canvas._paint_surface(self, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        handler = self._canvas._interaction
        btn = event.button()
        if handler is not None and btn == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._canvas._interaction_press(event)
            return
        if btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._canvas._start_pan(event.globalPosition().toPoint(), event.position().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._canvas._panning:
            self._canvas._update_pan(event.globalPosition().toPoint())
        elif self._canvas._interaction is not None:
            self._canvas._interaction_move(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._canvas._panning and event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._canvas._end_pan()
        elif self._canvas._interaction is not None and event.button() == Qt.MouseButton.LeftButton:
            self._canvas._interaction_release(event)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._canvas._interaction is not None and event.button() == Qt.MouseButton.LeftButton:
            self._canvas._interaction_double_click(event)
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        handler = self._canvas._interaction
        if handler is not None and handler.key_press(self._canvas, event):
            event.accept()
            return
        super().keyPressEvent(event)


class PDFScrollViewer(QScrollArea):
    """Khung cuộn hiển thị tài liệu PDF với khả năng kết xuất theo vùng nhìn và lớp phủ bố cục."""

    pageChanged = Signal(int)  # 0-based page index
    zoomChanged = Signal(int)  # zoom percentage (e.g. 100, 125)

    PAGE_GAP = 16
    MARGIN_X = 20
    MARGIN_Y = 18

    def __init__(self, reader: PDFDocumentReader, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.reader = reader
        self._zoom_mode: str = "fit_width"  # "fit_width" | "fit_page" | "percent"
        self._zoom_percent: int = 100
        self._continuous: bool = True
        self._current_page: int = 0
        self._show_layout_overlay: bool = False
        self._canvas_theme: str = "dark"

        self._search_hits_by_page: Dict[int, List[SearchHit]] = {}
        self._active_hit: Optional[SearchHit] = None

        self._page_rects_px: List[QRectF] = []
        self._effective_scale: float = 1.25

        self._panning: bool = False
        self._pan_start_global = QPoint()
        self._pan_start_scroll = QPoint()

        self._interaction: Optional[CanvasInteraction] = None
        self._drag_page: Optional[int] = None

        self._surface = _PageDrawSurface(self)
        self.setWidget(self._surface)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.horizontalScrollBar().valueChanged.connect(self._surface.update)

        self._recompute_layout()

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def zoom_percent(self) -> int:
        return self._zoom_percent

    @property
    def zoom_mode(self) -> str:
        return self._zoom_mode

    @property
    def continuous_mode(self) -> bool:
        return self._continuous

    @property
    def show_layout_overlay(self) -> bool:
        return self._show_layout_overlay

    # ─── Bộ xử lý chuột & đổi toạ độ trang ↔ khung vẽ ─────────────────────

    @property
    def interaction(self) -> Optional[CanvasInteraction]:
        return self._interaction

    @property
    def effective_scale(self) -> float:
        return self._effective_scale

    def set_interaction(self, handler: Optional[CanvasInteraction]) -> None:
        """Gắn (hoặc gỡ với `None`) bộ xử lý chuột; khi có, chuột trái không còn kéo cuộn trang."""
        self._interaction = handler
        self._drag_page = None
        self.refresh_cursor()
        self._surface.update()

    def refresh_cursor(self, shape: Optional[Qt.CursorShape] = None) -> None:
        if shape is None:
            shape = self._interaction.cursor() if self._interaction is not None else Qt.CursorShape.ArrowCursor
        self._surface.setCursor(shape)

    def refresh_pages(self, pages: Iterable[int]) -> None:
        """Vẽ lại các trang vừa thay đổi nội dung (chú thích mới / xoá / di chuyển)."""
        self.reader.invalidate_pages(pages)
        self._surface.update()

    def page_at(self, pos: QPointF) -> Optional[int]:
        if not self._page_rects_px:
            return None
        if not self._continuous:
            return self._current_page if self._page_rects_px[self._current_page].contains(pos) else None
        for idx, r in enumerate(self._page_rects_px):
            if r.contains(pos):
                return idx
        return None

    def page_transform(self, page_index: int) -> QTransform:
        """Phép biến đổi toạ độ trang chưa xoay → toạ độ khung vẽ (đã gồm thu phóng và mọi góc xoay)."""
        m = self.reader.page_view_matrix(page_index, self._effective_scale)
        r = self._page_rects_px[page_index]
        return QTransform(m.a, m.b, m.c, m.d, m.e + r.left(), m.f + r.top())

    def widget_to_page(self, page_index: int, pos: QPointF) -> fitz.Point:
        inv, _ok = self.page_transform(page_index).inverted()
        q = inv.map(QPointF(pos))
        return fitz.Point(q.x(), q.y())

    def page_rect_to_widget(self, page_index: int, rect, transform: Optional[QTransform] = None) -> QRectF:
        t = transform if transform is not None else self.page_transform(page_index)
        r = fitz.Rect(rect)
        return t.mapRect(QRectF(r.x0, r.y0, r.width, r.height))

    def scroll_to_rect(self, page_index: int, rect) -> None:
        """Cuộn để vùng `rect` (toạ độ trang chưa xoay) của trang `page_index` nằm giữa vùng nhìn."""
        if not 0 <= page_index < self.reader.page_count:
            return
        if not self._continuous or page_index != self._current_page:
            self.go_to_page(page_index)
        r = self.page_rect_to_widget(page_index, rect)
        self.ensureVisible(int(r.center().x()), int(r.center().y()), 60, int(self.viewport().height() * 0.3))
        self._surface.update()

    def _interaction_press(self, event: QMouseEvent) -> None:
        pos = event.position()
        pno = self.page_at(pos)
        if pno is None:
            return
        if pno != self._current_page:
            self._current_page = pno
            self.pageChanged.emit(pno)
        self._drag_page = pno
        self._interaction.press(self, pno, self.widget_to_page(pno, pos), event)
        self._surface.update()

    def _interaction_move(self, event: QMouseEvent) -> None:
        pos = event.position()
        dragging = self._drag_page is not None and bool(event.buttons() & Qt.MouseButton.LeftButton)
        pno = self._drag_page if dragging else self.page_at(pos)
        pt = self.widget_to_page(pno, pos) if pno is not None else None
        self._interaction.move(self, pno, pt, event, dragging)
        if dragging:
            self._autoscroll(pos)
            self._surface.update()

    def _interaction_release(self, event: QMouseEvent) -> None:
        pno = self._drag_page
        self._drag_page = None
        if pno is None:
            return
        self._interaction.release(self, pno, self.widget_to_page(pno, event.position()), event)
        self._surface.update()

    def _interaction_double_click(self, event: QMouseEvent) -> None:
        pos = event.position()
        pno = self.page_at(pos)
        if pno is not None:
            self._interaction.double_click(self, pno, self.widget_to_page(pno, pos), event)
            self._surface.update()

    def _autoscroll(self, pos: QPointF) -> None:
        """Kéo chuột sát mép vùng nhìn khi đang vẽ/chọn thì tự cuộn theo."""
        vp = self.viewport()
        local = vp.mapFromGlobal(self._surface.mapToGlobal(pos.toPoint()))
        margin, step = 24, 18
        bar = self.verticalScrollBar()
        if local.y() < margin:
            bar.setValue(bar.value() - step)
        elif local.y() > vp.height() - margin:
            bar.setValue(bar.value() + step)

    def set_canvas_theme(self, theme: str) -> None:
        """Cập nhật màu nền vùng vẽ PDF theo giao diện `'light'` hoặc `'dark'`."""
        self._canvas_theme = "light" if theme == "light" else "dark"
        self._surface.update()

    def set_continuous_mode(self, enabled: bool) -> None:
        """Chuyển đổi giữa chế độ Cuộn liên tục và Từng trang."""
        if self._continuous == enabled:
            return
        target_page = self._current_page
        self._continuous = enabled
        self._recompute_layout()
        self.go_to_page(target_page)

    def set_show_layout_overlay(self, enabled: bool) -> None:
        """Bật/tắt hiển thị khung soi bố cục (Văn bản, Bảng, Ảnh, Chữ ký, Vector) trên trang PDF."""
        self._show_layout_overlay = bool(enabled)
        self._surface.update()

    def set_zoom_mode(self, mode: str, percent: Optional[int] = None) -> None:
        """Đặt chế độ thu phóng: `'fit_width'`, `'fit_page'`, hoặc `'percent'`."""
        self._zoom_mode = mode
        if percent is not None:
            self._zoom_percent = max(25, min(400, int(percent)))
        self._recompute_layout()
        self.zoomChanged.emit(self._zoom_percent)

    def zoom_in(self, step: int = 20) -> None:
        self.set_zoom_mode("percent", self._zoom_percent + step)

    def zoom_out(self, step: int = 20) -> None:
        self.set_zoom_mode("percent", self._zoom_percent - step)

    def rotate_current_page(self, delta_degrees: int = 90) -> None:
        self.reader.rotate_page(self._current_page, delta_degrees)
        self._recompute_layout()
        self._surface.update()

    def set_search_hits(
        self, hits: List[SearchHit], active_hit: Optional[SearchHit] = None
    ) -> None:
        """Cập nhật danh sách vị trí tìm kiếm để tô sáng trên trang PDF."""
        grouped: Dict[int, List[SearchHit]] = {}
        for h in hits:
            grouped.setdefault(h.page_index, []).append(h)
        self._search_hits_by_page = grouped
        self._active_hit = active_hit
        if active_hit is not None:
            self.scroll_to_hit(active_hit)
        self._surface.update()

    def scroll_to_hit(self, hit: SearchHit) -> None:
        """Cuộn tới đúng trang và toạ độ của kết quả tìm kiếm."""
        self._active_hit = hit
        if not self._continuous and self._current_page != hit.page_index:
            self._current_page = hit.page_index
            self._recompute_layout()
            self.pageChanged.emit(self._current_page)
        elif self._continuous:
            if 0 <= hit.page_index < len(self._page_rects_px):
                hit_y = self.page_rect_to_widget(hit.page_index, hit.bbox).top()
                vh = self.viewport().height()
                self.verticalScrollBar().setValue(max(0, int(hit_y - vh * 0.35)))
        self._surface.update()

    def go_to_page(self, page_index: int) -> None:
        """Di chuyển tới trang `page_index` (0-based)."""
        if self.reader.page_count == 0:
            return
        clamped = max(0, min(self.reader.page_count - 1, int(page_index)))
        self._current_page = clamped
        if self._continuous:
            if clamped < len(self._page_rects_px):
                top_y = int(self._page_rects_px[clamped].top()) - 10
                self.verticalScrollBar().blockSignals(True)
                self.verticalScrollBar().setValue(max(0, top_y))
                self.verticalScrollBar().blockSignals(False)
        else:
            self._recompute_layout()
            self.verticalScrollBar().setValue(0)
        self._surface.update()
        self.pageChanged.emit(self._current_page)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._zoom_mode in ("fit_width", "fit_page"):
            self._recompute_layout()
            self.zoomChanged.emit(self._zoom_percent)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in(15)
            elif delta < 0:
                self.zoom_out(15)
            event.accept()
            return
        super().wheelEvent(event)

    def _recompute_layout(self) -> None:
        """Tính toán kích thước và vị trí của từng trang trên bề mặt vẽ."""
        if self.reader.page_count == 0:
            self._surface.resize(400, 400)
            return

        vw = max(320, self.viewport().width() - 2 * self.MARGIN_X)
        vh = max(240, self.viewport().height() - 2 * self.MARGIN_Y)

        ref_w, ref_h = self.reader.get_page_size(self._current_page)
        base_dpi_scale = 96.0 / 72.0  # 100% tương ứng 96 DPI trên màn hình Windows

        if self._zoom_mode == "fit_width":
            self._effective_scale = max(0.25, vw / max(1.0, ref_w))
            self._zoom_percent = max(25, min(400, int(round((self._effective_scale / base_dpi_scale) * 100))))
        elif self._zoom_mode == "fit_page":
            scale_w = vw / max(1.0, ref_w)
            scale_h = vh / max(1.0, ref_h)
            self._effective_scale = max(0.25, min(scale_w, scale_h))
            self._zoom_percent = max(25, min(400, int(round((self._effective_scale / base_dpi_scale) * 100))))
        else:
            self._effective_scale = base_dpi_scale * (self._zoom_percent / 100.0)

        self._page_rects_px.clear()
        pages_to_layout = (
            range(self.reader.page_count) if self._continuous else [self._current_page]
        )

        max_page_w = 0.0
        page_sizes_px: List[Tuple[int, float, float]] = []
        for pno in pages_to_layout:
            pw_pt, ph_pt = self.reader.get_page_size(pno)
            pw_px = pw_pt * self._effective_scale
            ph_px = ph_pt * self._effective_scale
            max_page_w = max(max_page_w, pw_px)
            page_sizes_px.append((pno, pw_px, ph_px))

        canvas_w = max(int(vw + 2 * self.MARGIN_X), int(max_page_w + 2 * self.MARGIN_X))
        y_cursor = float(self.MARGIN_Y)

        if self._continuous:
            for _pno, pw_px, ph_px in page_sizes_px:
                x = (canvas_w - pw_px) / 2.0
                self._page_rects_px.append(QRectF(x, y_cursor, pw_px, ph_px))
                y_cursor += ph_px + self.PAGE_GAP
        else:
            # Trong chế độ từng trang, điền rect cho tất cả chỉ số trang để truy cập thống nhất
            _, pw_px, ph_px = page_sizes_px[0]
            x = (canvas_w - pw_px) / 2.0
            single_rect = QRectF(x, y_cursor, pw_px, ph_px)
            for _ in range(self.reader.page_count):
                self._page_rects_px.append(single_rect)
            y_cursor += ph_px + self.MARGIN_Y

        canvas_h = max(int(vh + 2 * self.MARGIN_Y), int(y_cursor))
        self._surface.resize(canvas_w, canvas_h)
        self._surface.update()

    def _on_scroll_changed(self, value: int) -> None:
        if not self._continuous or not self._page_rects_px:
            self._surface.update()
            return
        viewport_mid = value + self.viewport().height() * 0.35
        best_page = self._current_page
        for idx, r in enumerate(self._page_rects_px):
            if r.top() <= viewport_mid <= r.bottom() + self.PAGE_GAP:
                best_page = idx
                break
        if best_page != self._current_page:
            self._current_page = best_page
            self.pageChanged.emit(self._current_page)
        self._surface.update()

    def _start_pan(self, global_pos: QPoint, surface_pos: QPoint) -> None:
        self._panning = True
        self._pan_start_global = global_pos
        self._pan_start_scroll = QPoint(
            self.horizontalScrollBar().value(),
            self.verticalScrollBar().value(),
        )
        self._surface.setCursor(Qt.CursorShape.ClosedHandCursor)
        # Cập nhật trang hiện tại nếu người dùng bấm vào một trang cụ thể
        if self._continuous:
            for idx, r in enumerate(self._page_rects_px):
                if r.contains(surface_pos):
                    if idx != self._current_page:
                        self._current_page = idx
                        self.pageChanged.emit(self._current_page)
                    break

    def _update_pan(self, global_pos: QPoint) -> None:
        if not self._panning:
            return
        delta = global_pos - self._pan_start_global
        self.horizontalScrollBar().setValue(self._pan_start_scroll.x() - delta.x())
        self.verticalScrollBar().setValue(self._pan_start_scroll.y() - delta.y())

    def _end_pan(self) -> None:
        self._panning = False
        self.refresh_cursor()

    def _paint_surface(self, surface: QWidget, event: QPaintEvent) -> None:
        painter = QPainter(surface)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Nền vùng làm việc (Sáng: xám nhạt PdfCraft #E2E8F0, Tối: đen than #111318)
        bg_color = QColor("#E2E8F0") if self._canvas_theme == "light" else QColor("#111318")
        painter.fillRect(event.rect(), bg_color)

        if not self._page_rects_px:
            painter.end()
            return

        vis_rect = QRectF(event.rect()).adjusted(-80, -300, 80, 300)
        dpr = max(1.0, surface.devicePixelRatioF())

        pages_to_draw = (
            range(self.reader.page_count) if self._continuous else [self._current_page]
        )

        for pno in pages_to_draw:
            prect = self._page_rects_px[pno]
            if not prect.intersects(vis_rect):
                continue

            # Bóng đổ trang
            shadow_rect = prect.translated(4.0, 5.0)
            shadow_alpha = 45 if self._canvas_theme == "light" else 110
            painter.fillRect(shadow_rect, QColor(15, 23, 42, shadow_alpha))

            # Kết xuất trang từ PyMuPDF ở độ phân giải màn hình thật (High-DPI)
            buf = self.reader.render_page(pno, scale=self._effective_scale * dpr)
            qimg = QImage(
                buf.rgb_bytes,
                buf.width,
                buf.height,
                buf.stride,
                QImage.Format.Format_RGB888,
            )
            painter.drawImage(prect, qimg)

            # Viền trang (nổi bật trang đang chọn)
            inactive_border = QColor("#CBD5E1") if self._canvas_theme == "light" else QColor("#374151")
            border_color = QColor("#2563EB") if pno == self._current_page else inactive_border
            painter.setPen(QPen(border_color, 1.6 if pno == self._current_page else 1.0))
            painter.drawRect(prect)

            # Lớp phủ 1: Tô sáng kết quả tìm kiếm trên trang này
            hits = self._search_hits_by_page.get(pno, [])
            transform = self.page_transform(pno) if (hits or self._show_layout_overlay) else None
            for h in hits:
                hrect = self.page_rect_to_widget(pno, h.bbox, transform).adjusted(-2, -2, 2, 2)
                is_active = self._active_hit is not None and (
                    self._active_hit.page_index == h.page_index
                    and self._active_hit.bbox == h.bbox
                )
                if is_active:
                    painter.fillRect(hrect, QColor(249, 115, 22, 115))
                    painter.setPen(QPen(QColor("#EA580C"), 2.0))
                else:
                    painter.fillRect(hrect, QColor(250, 204, 21, 95))
                    painter.setPen(QPen(QColor("#EAB308"), 1.2))
                painter.drawRect(hrect)

            # Lớp phủ 2: Soi bố cục (Layout Inspector Overlay)
            if self._show_layout_overlay:
                self._draw_layout_overlay(painter, pno, prect, transform)

            # Lớp phủ 3: Xem trước của công cụ chú thích (vùng chọn chữ, nét đang vẽ, chú thích đang chọn)
            if self._interaction is not None:
                painter.save()
                painter.setClipRect(prect.adjusted(-40, -40, 40, 40))
                self._interaction.paint(self, painter, pno)
                painter.restore()

        painter.end()

    def _draw_layout_overlay(
        self, painter: QPainter, page_index: int, prect: QRectF, transform: Optional[QTransform] = None
    ) -> None:
        """Vẽ các khung nhận diện Văn bản / Bảng biểu / Hình ảnh / Chữ ký / Vector lên trang PDF."""
        summary = self.reader.get_page_layout(page_index)
        color_map = {
            "text": (QColor("#2563EB"), QColor(37, 99, 235, 28)),       # Xanh dương
            "table": (QColor("#16A34A"), QColor(22, 163, 74, 42)),      # Xanh lá
            "image": (QColor("#EA580C"), QColor(234, 88, 12, 38)),      # Cam
            "signature": (QColor("#E11D48"), QColor(225, 29, 72, 42)),  # Đỏ hồng (Chữ ký số / Con dấu)
            "vector": (QColor("#9333EA"), QColor(147, 51, 234, 20)),    # Tím
        }
        font = QFont("Segoe UI", 8)
        font.setBold(True)
        painter.setFont(font)

        for el in summary.elements:
            border_c, fill_c = color_map.get(el.kind, (QColor("#2563EB"), QColor(37, 99, 235, 25)))
            erect = self.page_rect_to_widget(page_index, el.bbox, transform)
            painter.fillRect(erect, fill_c)
            pen_width = 2.0 if el.kind in ("table", "signature") else 1.1
            painter.setPen(QPen(border_c, pen_width, Qt.PenStyle.SolidLine))
            painter.drawRect(erect)

            if el.kind in ("table", "image", "signature") and el.label:
                tag_rect = QRectF(erect.left(), max(prect.top(), erect.top() - 16), min(230.0, erect.width() + 90), 16)
                painter.fillRect(tag_rect, border_c)
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(tag_rect.adjusted(4, 0, -2, 0), Qt.AlignmentFlag.AlignVCenter, el.label)
