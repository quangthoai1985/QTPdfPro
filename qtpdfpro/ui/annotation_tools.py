"""Chế độ «Chỉnh sửa PDF» trên khung đọc: thanh công cụ chú thích, bộ xử lý chuột và ngăn danh sách chú thích.

- `AnnotationController` — nhận thao tác chuột từ `PDFScrollViewer` (toạ độ trang chưa xoay), vẽ xem trước,
  gọi `EditSession` (core) để thêm / chọn / di chuyển / xoá chú thích, có Hoàn tác – Làm lại.
- `EditToolbar` — 2 tầng: công cụ (tô sáng, gạch chân, gạch ngang, gạch sóng, bút, bút dạ quang, khung, elip,
  đường, mũi tên, hộp chữ, ghi chú, dấu đóng, tẩy) và kiểu dáng theo công cụ (màu, nét, độ đậm, phông, mẫu dấu).
- `AnnotationListPanel` — ngăn «Chú thích» bên phải: liệt kê, đi tới, sửa nội dung, xoá.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLayout,
    QLayoutItem,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from qtpdfpro.core import annotations as an
from qtpdfpro.core.edit_session import EditSession
from qtpdfpro.core.reader import PDFDocumentReader

MARKUP_TOOLS = ("highlight", "underline", "strikeout", "squiggly")
INK_TOOLS = ("pen", "marker")
SHAPE_TOOLS = ("rect", "ellipse", "line", "arrow")
CREATE_TOOLS = MARKUP_TOOLS + INK_TOOLS + SHAPE_TOOLS + ("text", "note", "stamp")


@dataclass(frozen=True)
class ToolDef:
    key: str
    label: str
    tip: str
    shortcut: str
    hint: str


TOOL_DEFS: List[ToolDef] = [
    ToolDef("pan", "✋", "Cuộn trang", "Esc", "Kéo để cuộn trang. Chọn một công cụ để tô màu, đánh dấu, vẽ hoặc chèn chữ."),
    ToolDef("select", "↖", "Chọn / di chuyển chú thích", "V",
            "Nhấp chọn chú thích · kéo để di chuyển · Delete để xoá · nhấp đúp để sửa nội dung."),
    ToolDef("highlight", "🖍", "Tô sáng chữ", "H",
            "Kéo chuột qua chữ để tô sáng · giữ Alt để chọn theo vùng · trang ảnh quét: kéo một vùng."),
    ToolDef("underline", "U", "Gạch chân chữ", "U", "Kéo chuột qua chữ cần gạch chân · giữ Alt để chọn theo vùng."),
    ToolDef("strikeout", "S", "Gạch ngang chữ", "K", "Kéo chuột qua chữ cần gạch ngang (đánh dấu xoá)."),
    ToolDef("squiggly", "〰", "Gạch sóng chữ", "G", "Kéo chuột qua chữ cần gạch sóng (lưu ý / cần sửa)."),
    ToolDef("pen", "✏️", "Bút vẽ tay", "P", "Giữ chuột trái và vẽ tự do lên trang."),
    ToolDef("marker", "🖌️", "Bút dạ quang", "M", "Vẽ đè lên chữ — nét to, trong suốt, không che chữ."),
    ToolDef("rect", "▭", "Khung chữ nhật", "R", "Kéo để vẽ khung · giữ Shift để vẽ hình vuông."),
    ToolDef("ellipse", "◯", "Hình elip", "O", "Kéo để vẽ elip · giữ Shift để vẽ hình tròn."),
    ToolDef("line", "╱", "Đường thẳng", "L", "Kéo từ điểm đầu tới điểm cuối · giữ Shift để bắt góc 45°."),
    ToolDef("arrow", "➜", "Mũi tên", "A", "Kéo từ gốc tới đầu mũi tên · giữ Shift để bắt góc 45°."),
    ToolDef("text", "T", "Hộp chữ", "T", "Nhấp (hoặc kéo để đặt độ rộng) rồi nhập nội dung hộp chữ."),
    ToolDef("note", "💬", "Ghi chú dán", "N", "Nhấp vào vị trí cần ghi chú rồi nhập nội dung."),
    ToolDef("stamp", "🔖", "Đóng dấu", "D", "Chọn mẫu dấu rồi nhấp vào trang để đóng dấu."),
    ToolDef("eraser", "⌫", "Tẩy chú thích", "X", "Nhấp hoặc kéo qua chú thích để xoá (Ctrl+Z để khôi phục)."),
]
TOOL_BY_KEY = {t.key: t for t in TOOL_DEFS}

_DEFAULT_STYLES: Dict[str, an.AnnotStyle] = {
    "highlight": an.AnnotStyle(color="#FACC15"),
    "underline": an.AnnotStyle(color="#16A34A"),
    "strikeout": an.AnnotStyle(color="#DC2626"),
    "squiggly": an.AnnotStyle(color="#F97316"),
    "pen": an.AnnotStyle(color="#DC2626", width=2.0),
    "marker": an.AnnotStyle(color="#FACC15", width=12.0, opacity=0.4),
    "rect": an.AnnotStyle(color="#DC2626", width=2.0),
    "ellipse": an.AnnotStyle(color="#DC2626", width=2.0),
    "line": an.AnnotStyle(color="#DC2626", width=2.0),
    "arrow": an.AnnotStyle(color="#DC2626", width=2.0),
    "text": an.AnnotStyle(color="#111827", text_color="#111827", font_size=12.0),
    "note": an.AnnotStyle(color="#FACC15"),
    "stamp": an.AnnotStyle(color="#16A34A", font_size=18.0, opacity=0.9),
}

_CURSORS = {
    "pan": Qt.CursorShape.OpenHandCursor,
    "select": Qt.CursorShape.ArrowCursor,
    "eraser": Qt.CursorShape.PointingHandCursor,
    **{k: Qt.CursorShape.IBeamCursor for k in MARKUP_TOOLS},
}


@dataclass
class _Drag:
    page: int
    start: fitz.Point
    current: fitz.Point
    points: List[Tuple[float, float]] = field(default_factory=list)
    rects: List[fitz.Rect] = field(default_factory=list)
    xref: Optional[int] = None  # chú thích đang kéo di chuyển (công cụ Chọn)
    area: bool = False


def _qcolor(hex_color: str, alpha: Optional[int] = None) -> QColor:
    c = QColor(hex_color or "#000000")
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def _snap_45(p0: fitz.Point, p1: fitz.Point) -> fitz.Point:
    dx, dy = p1.x - p0.x, p1.y - p0.y
    length = math.hypot(dx, dy)
    angle = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
    return fitz.Point(p0.x + length * math.cos(angle), p0.y + length * math.sin(angle))


def _square(p0: fitz.Point, p1: fitz.Point) -> fitz.Point:
    side = max(abs(p1.x - p0.x), abs(p1.y - p0.y))
    return fitz.Point(p0.x + math.copysign(side, p1.x - p0.x or 1), p0.y + math.copysign(side, p1.y - p0.y or 1))


class AnnotationController(QObject):
    """Bộ xử lý chuột của chế độ chỉnh sửa (gắn vào `PDFScrollViewer.set_interaction`)."""

    documentChanged = Signal(int)  # trang vừa thay đổi chú thích
    toolChanged = Signal(str)
    styleChanged = Signal()
    selectionChanged = Signal()
    message = Signal(str)

    def __init__(self, reader: PDFDocumentReader, author: Optional[str] = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.reader = reader
        self.author = author or None
        self._tool = "highlight"
        self._styles: Dict[str, an.AnnotStyle] = {k: v.copy() for k, v in _DEFAULT_STYLES.items()}
        self.stamp_label = an.STAMP_PRESETS[0][0]
        self.stamp_with_date = False
        self._drag: Optional[_Drag] = None
        self._selected: Optional[Tuple[int, int]] = None
        self._hover: Optional[Tuple[int, int]] = None
        self._erased: set[Tuple[int, int]] = set()

    # ─── Trạng thái công cụ & kiểu dáng ───────────────────────────────────

    @property
    def session(self) -> EditSession:
        return self.reader.edit_session(self.author)

    @property
    def tool(self) -> str:
        return self._tool

    @property
    def selected(self) -> Optional[Tuple[int, int]]:
        return self._selected

    def set_tool(self, key: str) -> None:
        if key not in TOOL_BY_KEY:
            return
        self._tool = key
        self._drag = None
        self._hover = None
        if key not in ("select",):
            self._set_selected(None)
        self.toolChanged.emit(key)

    def style(self, tool: Optional[str] = None) -> an.AnnotStyle:
        return self._styles.get(tool or self._tool, an.AnnotStyle())

    def update_style(self, **changes) -> None:
        if self._tool not in self._styles:
            return
        style = self._styles[self._tool]
        for key, value in changes.items():
            setattr(style, key, value)
        if self._tool == "text" and "color" in changes:
            style.text_color = changes["color"]
        self.styleChanged.emit()

    def set_stamp_preset(self, label: str, color: Optional[str] = None) -> None:
        self.stamp_label = an._nfc(label).strip().upper() or self.stamp_label
        if color:
            self._styles["stamp"].color = color
        self.styleChanged.emit()

    def cursor(self) -> Qt.CursorShape:
        return _CURSORS.get(self._tool, Qt.CursorShape.CrossCursor)

    # ─── Hoàn tác / chọn / xoá / sửa ──────────────────────────────────────

    def _set_selected(self, value: Optional[Tuple[int, int]]) -> None:
        if value != self._selected:
            self._selected = value
            self.selectionChanged.emit()

    def undo(self) -> bool:
        res = self.session.undo()
        if res is None:
            self.message.emit("Không còn thao tác để hoàn tác.")
            return False
        self._set_selected(None)
        self.documentChanged.emit(res[1])
        self.message.emit(f"Đã hoàn tác: {res[0]}")
        return True

    def redo(self) -> bool:
        res = self.session.redo()
        if res is None:
            self.message.emit("Không còn thao tác để làm lại.")
            return False
        self._set_selected(None)
        self.documentChanged.emit(res[1])
        self.message.emit(f"Đã làm lại: {res[0]}")
        return True

    def select(self, page_index: int, xref: int) -> None:
        self._set_selected((page_index, xref))

    def delete_annotation(self, page_index: int, xref: int) -> bool:
        if self.session.delete(page_index, xref):
            if self._selected == (page_index, xref):
                self._set_selected(None)
            self.documentChanged.emit(page_index)
            self.message.emit("Đã xoá chú thích — Ctrl+Z để khôi phục.")
            return True
        return False

    def edit_annotation(self, page_index: int, xref: int, parent: QWidget | None = None) -> bool:
        info = self.session.info(page_index, xref)
        if info is None:
            return False
        title = "Sửa hộp chữ" if info.app_kind == "textbox" else f"Nội dung — {info.label}"
        current = an.qt_data(self.reader.doc, xref).get("text", info.content) if info.app_kind == "textbox" \
            else info.content
        text, ok = QInputDialog.getMultiLineText(parent, title, "Nội dung:", current)
        if not ok or text == current:
            return False
        if info.app_kind == "textbox" and not text.strip():
            return self.delete_annotation(page_index, xref)
        try:
            self.session.set_content(page_index, xref, text)
        except an.AnnotationError as exc:
            self.message.emit(str(exc))
            return False
        self.documentChanged.emit(page_index)
        return True

    # ─── Giao diện CanvasInteraction ─────────────────────────────────────

    def press(self, viewer, page_index: int, pt: fitz.Point, event: QMouseEvent) -> None:
        tool = self._tool
        self._drag = _Drag(page_index, pt, pt, area=bool(event.modifiers() & Qt.KeyboardModifier.AltModifier))
        if tool in INK_TOOLS:
            self._drag.points.append((pt.x, pt.y))
        elif tool == "select":
            xref = self.session.annotation_at(page_index, pt)
            self._set_selected((page_index, xref) if xref else None)
            info = self.session.info(page_index, xref) if xref else None
            self._drag.xref = xref if info is not None and info.movable else None
        elif tool == "eraser":
            self._erased.clear()
            self._erase_at(page_index, pt)

    def move(self, viewer, page_index: Optional[int], pt: Optional[fitz.Point], event: QMouseEvent,
             dragging: bool) -> None:
        if not dragging or self._drag is None:
            self._update_hover(viewer, page_index, pt)
            return
        d = self._drag
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        tool = self._tool
        if tool in ("rect", "ellipse") and shift:
            pt = _square(d.start, pt)
        elif tool in ("line", "arrow") and shift:
            pt = _snap_45(d.start, pt)
        d.current = pt
        if tool in INK_TOOLS:
            last = d.points[-1]
            if math.hypot(pt.x - last[0], pt.y - last[1]) >= 0.6:
                d.points.append((pt.x, pt.y))
        elif tool in MARKUP_TOOLS:
            d.area = d.area or bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            d.rects = self.session.select_text(d.page, d.start, pt, area=d.area)
        elif tool == "eraser":
            self._erase_at(d.page, pt)

    def release(self, viewer, page_index: int, pt: fitz.Point, event: QMouseEvent) -> None:
        d, self._drag = self._drag, None
        if d is None:
            return
        tool = self._tool
        end = d.current if tool in SHAPE_TOOLS else pt
        moved = math.hypot(end.x - d.start.x, end.y - d.start.y)
        style = self.style().copy()
        session = self.session
        try:
            if tool in MARKUP_TOOLS:
                rects = d.rects or session.select_text(page_index, d.start, end, area=d.area)
                if moved < 1.5:
                    rects = [r for r in session.select_text(page_index, end, end) if r.contains(end)]
                if not rects and tool == "highlight" and moved >= 4 and (d.area or not session.page_has_text(page_index)):
                    rects = [fitz.Rect(d.start, end).normalize()]  # tô sáng vùng (trang ảnh quét)
                if not rects:
                    self.message.emit(TOOL_BY_KEY[tool].hint)
                    return
                session.add_markup(page_index, tool, rects, style)
                verb = {"highlight": "tô sáng", "underline": "gạch chân", "strikeout": "gạch ngang",
                        "squiggly": "gạch sóng"}[tool]
                self._done(page_index, f"Đã {verb} {len(rects)} dòng chữ.")
            elif tool in INK_TOOLS:
                if len(d.points) >= 1:
                    session.add_ink(page_index, [d.points], style, marker=tool == "marker")
                    self._done(page_index, "Đã thêm nét vẽ.")
            elif tool in SHAPE_TOOLS:
                if moved < 3:
                    self.message.emit(TOOL_BY_KEY[tool].hint)
                    return
                session.add_shape(page_index, tool, d.start, end, style)
                self._done(page_index, f"Đã vẽ {TOOL_BY_KEY[tool].tip.lower()}.")
            elif tool == "text":
                self._create_text_box(viewer, page_index, d.start, end, moved, style)
            elif tool == "note":
                text, ok = QInputDialog.getMultiLineText(viewer, "Ghi chú dán", "Nội dung ghi chú:", "")
                if ok and text.strip():
                    session.add_note(page_index, end, text, style)
                    self._done(page_index, "Đã thêm ghi chú.")
            elif tool == "stamp":
                date_text = an.stamp_date_text() if self.stamp_with_date else None
                session.add_stamp(page_index, end, self.stamp_label, style, date_text)
                self._done(page_index, f"Đã đóng dấu «{self.stamp_label}».")
            elif tool == "select" and d.xref is not None and moved >= 0.5:
                if session.move(page_index, d.xref, end.x - d.start.x, end.y - d.start.y):
                    self._done(page_index, "Đã di chuyển chú thích.")
        except an.AnnotationError as exc:
            self.message.emit(str(exc))
        except Exception as exc:  # lỗi bất ngờ từ PyMuPDF — báo, không làm hỏng giao diện
            self.message.emit(f"Không thêm được chú thích: {exc}")

    def double_click(self, viewer, page_index: int, pt: fitz.Point, event: QMouseEvent) -> None:
        if self._tool not in ("select", "pan"):
            return
        xref = self.session.annotation_at(page_index, pt)
        if xref:
            self._set_selected((page_index, xref))
            self.edit_annotation(page_index, xref, viewer)

    def key_press(self, viewer, event: QKeyEvent) -> bool:
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self._selected is not None:
            return self.delete_annotation(*self._selected) or True
        if key == Qt.Key.Key_Escape:
            if self._drag is not None:
                self._drag = None
                viewer.widget().update()
                return True
            if self._selected is not None:
                self._set_selected(None)
                viewer.widget().update()
                return True
        return False

    def paint(self, viewer, painter: QPainter, page_index: int) -> None:
        t = viewer.page_transform(page_index)
        scale = viewer.effective_scale
        if self._hover is not None and self._hover[0] == page_index and self._hover != self._selected:
            r = self.session.annotation_rect(*self._hover)
            if r is not None:
                color = "#DC2626" if self._tool == "eraser" else "#2563EB"
                painter.setPen(QPen(_qcolor(color, 200), 1.2, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(viewer.page_rect_to_widget(page_index, r, t).adjusted(-2, -2, 2, 2))
        if self._selected is not None and self._selected[0] == page_index:
            r = self.session.annotation_rect(*self._selected)
            if r is not None:
                d = self._drag
                if d is not None and d.xref == self._selected[1]:
                    dx, dy = d.current.x - d.start.x, d.current.y - d.start.y
                    r = r + (dx, dy, dx, dy)
                wr = viewer.page_rect_to_widget(page_index, r, t).adjusted(-3, -3, 3, 3)
                painter.setPen(QPen(_qcolor("#2563EB"), 1.5, Qt.PenStyle.DashLine))
                painter.setBrush(QBrush(_qcolor("#2563EB", 22)))
                painter.drawRect(wr)
        d = self._drag
        if d is None or d.page != page_index:
            return
        style = self.style()
        tool = self._tool
        color = _qcolor(style.color)
        if tool in MARKUP_TOOLS:
            for r in d.rects:
                if tool == "highlight":
                    painter.fillRect(viewer.page_rect_to_widget(page_index, r, t), _qcolor(style.color, 110))
                    continue
                y = r.y1 - 0.5 if tool in ("underline", "squiggly") else (r.y0 + r.y1) / 2
                pen = QPen(color, max(1.2, scale), Qt.PenStyle.DotLine if tool == "squiggly" else Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.drawLine(t.map(QPointF(r.x0, y)), t.map(QPointF(r.x1, y)))
            if not d.rects and (d.area or tool == "highlight"):
                painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
                painter.setBrush(QBrush(_qcolor(style.color, 40)))
                painter.drawRect(viewer.page_rect_to_widget(page_index, fitz.Rect(d.start, d.current).normalize(), t))
        elif tool in INK_TOOLS and len(d.points) >= 1:
            path = QPainterPath(t.map(QPointF(*d.points[0])))
            for x, y in d.points[1:]:
                path.lineTo(t.map(QPointF(x, y)))
            c = _qcolor(style.color, int(255 * style.opacity))
            painter.setPen(QPen(c, max(1.0, style.width * scale), Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        elif tool in SHAPE_TOOLS:
            pen = QPen(_qcolor(style.color, int(255 * style.opacity)), max(1.0, style.width * scale))
            painter.setPen(pen)
            painter.setBrush(QBrush(_qcolor(style.fill)) if style.fill and tool in ("rect", "ellipse")
                             else Qt.BrushStyle.NoBrush)
            if tool in ("rect", "ellipse"):
                wr = viewer.page_rect_to_widget(page_index, fitz.Rect(d.start, d.current).normalize(), t)
                painter.drawRect(wr) if tool == "rect" else painter.drawEllipse(wr)
            else:
                a, b = t.map(QPointF(d.start.x, d.start.y)), t.map(QPointF(d.current.x, d.current.y))
                painter.drawLine(a, b)
                if tool == "arrow":
                    self._paint_arrow_head(painter, a, b, max(6.0, style.width * scale * 3.5), pen.color())
        elif tool == "text":
            painter.setPen(QPen(_qcolor("#2563EB"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(viewer.page_rect_to_widget(page_index, fitz.Rect(d.start, d.current).normalize(), t))

    # ─── Nội bộ ───────────────────────────────────────────────────────────

    @staticmethod
    def _paint_arrow_head(painter: QPainter, a: QPointF, b: QPointF, size: float, color: QColor) -> None:
        ang = math.atan2(b.y() - a.y(), b.x() - a.x())
        left = QPointF(b.x() - size * math.cos(ang - 0.45), b.y() - size * math.sin(ang - 0.45))
        right = QPointF(b.x() - size * math.cos(ang + 0.45), b.y() - size * math.sin(ang + 0.45))
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygonF([b, left, right]))

    def _done(self, page_index: int, text: str) -> None:
        self.documentChanged.emit(page_index)
        self.message.emit(text + " (Ctrl+Z để hoàn tác)")

    def _create_text_box(self, viewer, page_index: int, p0: fitz.Point, p1: fitz.Point, moved: float,
                         style: an.AnnotStyle) -> None:
        text, ok = QInputDialog.getMultiLineText(viewer, "Hộp chữ", "Nội dung hộp chữ:", "")
        if not ok or not text.strip():
            return
        if moved >= 12:
            rect = fitz.Rect(p0, p1).normalize()
        else:
            page = self.reader.doc[page_index]
            disp = fitz.Point(p0) * page.rotation_matrix
            rect = (fitz.Rect(disp.x, disp.y, disp.x + 220, disp.y + 10) * page.derotation_matrix).normalize()
        self.session.add_text_box(page_index, rect, text, style)
        self._done(page_index, "Đã thêm hộp chữ.")

    def _erase_at(self, page_index: int, pt: fitz.Point) -> None:
        xref = self.session.annotation_at(page_index, pt)
        if xref and (page_index, xref) not in self._erased:
            self._erased.add((page_index, xref))
            self.delete_annotation(page_index, xref)

    def _update_hover(self, viewer, page_index: Optional[int], pt: Optional[fitz.Point]) -> None:
        if self._tool not in ("select", "eraser"):
            return
        hover = None
        if page_index is not None and pt is not None:
            xref = self.session.annotation_at(page_index, pt)
            hover = (page_index, xref) if xref else None
        if hover != self._hover:
            self._hover = hover
            if self._tool == "select":
                viewer.refresh_cursor(Qt.CursorShape.SizeAllCursor if hover else Qt.CursorShape.ArrowCursor)
            viewer.widget().update()


# ─── Thanh công cụ ────────────────────────────────────────────────────────


def _swatch_style(color: str) -> str:
    return (
        f"QPushButton {{ background-color: {color}; border: 2px solid rgba(127,127,127,0.45); border-radius: 10px;"
        " min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px; padding: 0px; }"
        " QPushButton:checked { border: 3px solid #2563EB; }"
        " QPushButton:hover { border-color: #60A5FA; }"
    )


class FlowLayout(QLayout):
    """Bố cục xếp hàng ngang, tự xuống dòng khi hết chỗ (thanh công cụ không ép cửa sổ rộng ra)."""

    def __init__(self, parent: QWidget | None = None, hspacing: int = 4, vspacing: int = 4) -> None:
        super().__init__(parent)
        self._items: List[QLayoutItem] = []
        self._h = hspacing
        self._v = vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 - API Qt
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802 - API Qt
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802 - API Qt
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802 - API Qt
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - API Qt
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - API Qt
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - API Qt
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - API Qt
        """Kích thước mong muốn = xếp tất cả trên một hàng."""
        visible = [it.sizeHint() for it in self._items if not it.isEmpty()]
        m = self.contentsMargins()
        w = sum(sz.width() for sz in visible) + self._h * max(0, len(visible) - 1)
        h = max((sz.height() for sz in visible), default=0)
        return QSize(w + m.left() + m.right(), h + m.top() + m.bottom())

    def minimumSize(self) -> QSize:  # noqa: N802 - API Qt
        size = QSize()
        for it in self._items:
            if not it.isEmpty():
                size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect: QRect, apply: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        lines: List[List[Tuple[QLayoutItem, QSize]]] = [[]]
        x = 0
        for it in self._items:
            if it.isEmpty():
                continue
            hint = it.sizeHint()
            if lines[-1] and x + hint.width() > area.width():
                lines.append([])
                x = 0
            lines[-1].append((it, hint))
            x += hint.width() + self._h
        y = area.y()
        for line in lines:
            if not line:
                continue
            line_h = max(h.height() for _it, h in line)
            if apply:
                lx = area.x()
                for it, hint in line:
                    it.setGeometry(QRect(QPoint(lx, y + (line_h - hint.height()) // 2), hint))
                    lx += hint.width() + self._h
            y += line_h + self._v
        return max(0, y - self._v - rect.y()) + m.bottom()


class EditToolbar(QFrame):
    """Thanh công cụ chế độ chỉnh sửa (2 tầng) đặt phía trên khung đọc PDF; các nút tự xuống dòng khi hẹp."""

    saveRequested = Signal()
    organizeRequested = Signal()
    exitRequested = Signal()

    def __init__(self, controller: AnnotationController, shortcut_parent: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("editToolbar")
        self.controller = controller
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 5, 8, 5)
        root.setSpacing(4)

        # Tầng 1: công cụ (tự xuống dòng) + hoàn tác + lưu
        row1 = QHBoxLayout()
        row1.setSpacing(3)
        self.tools_box = QWidget()
        tools_flow = FlowLayout(self.tools_box, hspacing=3, vspacing=3)
        title = QLabel("✏️ <b>Chỉnh sửa</b>")
        title.setObjectName("editToolbarTitle")
        tools_flow.addWidget(title)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_buttons: Dict[str, QPushButton] = {}
        for i, td in enumerate(TOOL_DEFS):
            if td.key in ("highlight", "pen", "rect", "text", "eraser"):
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setObjectName("editToolbarSep")
                sep.setFixedHeight(22)
                tools_flow.addWidget(sep)
            btn = QPushButton(td.label)
            btn.setObjectName("annotToolBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"<b>{td.tip}</b> ({td.shortcut})<br/>{td.hint}")
            if td.key == "underline":
                f = btn.font(); f.setUnderline(True); f.setBold(True); btn.setFont(f)
            elif td.key == "strikeout":
                f = btn.font(); f.setStrikeOut(True); f.setBold(True); btn.setFont(f)
            elif td.key == "text":
                f = btn.font(); f.setBold(True); btn.setFont(f)
            btn.clicked.connect(lambda _c=False, k=td.key: self.controller.set_tool(k))
            self.tool_group.addButton(btn, i)
            self.tool_buttons[td.key] = btn
            tools_flow.addWidget(btn)
        row1.addWidget(self.tools_box, 1)

        self.btn_undo = QPushButton("↶")
        self.btn_undo.setObjectName("annotToolBtn")
        self.btn_undo.setToolTip("Hoàn tác (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.controller.undo)
        self.btn_redo = QPushButton("↷")
        self.btn_redo.setObjectName("annotToolBtn")
        self.btn_redo.setToolTip("Làm lại (Ctrl+Y)")
        self.btn_redo.clicked.connect(self.controller.redo)
        self.btn_organize = QPushButton("🧩 Trang")
        self.btn_organize.setObjectName("ghostBtn")
        self.btn_organize.setToolTip("Sắp xếp & cắt ghép trang: kéo thả, xoay, xoá, chèn, ghép tệp, tách tệp")
        self.btn_organize.clicked.connect(self.organizeRequested)
        self.btn_save = QPushButton("💾 Lưu")
        self.btn_save.setObjectName("primaryConvertBtn")
        self.btn_save.setToolTip("Lưu chú thích vào tệp PDF (Ctrl+S) — ghi bổ sung, giữ nguyên chữ ký số đã có")
        self.btn_save.clicked.connect(self.saveRequested)
        self.btn_exit = QPushButton("✕")
        self.btn_exit.setObjectName("ghostIconBtn")
        self.btn_exit.setToolTip("Thoát chế độ chỉnh sửa (thay đổi chưa lưu vẫn được giữ)")
        self.btn_exit.clicked.connect(self.exitRequested)
        for w in (self.btn_undo, self.btn_redo, self.btn_organize, self.btn_save, self.btn_exit):
            row1.addWidget(w, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(row1)

        # Tầng 2: kiểu dáng theo công cụ
        row2 = QHBoxLayout()
        row2.setSpacing(5)
        self.style_box = QWidget()
        sb = FlowLayout(self.style_box, hspacing=8, vspacing=3)
        self.color_box = QWidget()
        cl = QHBoxLayout(self.color_box)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(5)
        self.lbl_color = QLabel("Màu")
        cl.addWidget(self.lbl_color)
        self.swatch_group = QButtonGroup(self)
        self.swatch_group.setExclusive(True)
        self.swatches: Dict[str, QPushButton] = {}
        for hex_color, name in an.COLOR_PRESETS:
            sw = QPushButton()
            sw.setCheckable(True)
            sw.setToolTip(name)
            sw.setStyleSheet(_swatch_style(hex_color))
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.clicked.connect(lambda _c=False, c=hex_color: self._on_color(c))
            self.swatch_group.addButton(sw)
            self.swatches[hex_color] = sw
            cl.addWidget(sw)
        self.btn_custom_color = QPushButton("＋")
        self.btn_custom_color.setObjectName("ghostIconBtn")
        self.btn_custom_color.setToolTip("Chọn màu khác…")
        self.btn_custom_color.clicked.connect(self._pick_color)
        cl.addWidget(self.btn_custom_color)
        sb.addWidget(self.color_box)

        self.width_box = QWidget()
        wl = QHBoxLayout(self.width_box)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(QLabel("Nét"))
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.5, 40.0)
        self.width_spin.setSingleStep(0.5)
        self.width_spin.setSuffix(" pt")
        self.width_spin.valueChanged.connect(lambda v: self._set_style(width=float(v)))
        wl.addWidget(self.width_spin)
        sb.addWidget(self.width_box)

        self.opacity_box = QWidget()
        ol = QHBoxLayout(self.opacity_box)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.addWidget(QLabel("Độ đậm"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setFixedWidth(90)
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        self.opacity_lbl = QLabel("100%")
        self.opacity_lbl.setMinimumWidth(34)
        ol.addWidget(self.opacity_slider)
        ol.addWidget(self.opacity_lbl)
        sb.addWidget(self.opacity_box)

        self.font_box = QWidget()
        fl = QHBoxLayout(self.font_box)
        fl.setContentsMargins(0, 0, 0, 0)
        self.font_combo = QComboBox()
        for key, name in an.FONT_FAMILIES:
            self.font_combo.addItem(name, key)
        self.font_combo.currentIndexChanged.connect(
            lambda _i: self._set_style(font_family=self.font_combo.currentData())
        )
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(6, 96)
        self.size_spin.setDecimals(0)
        self.size_spin.setSuffix(" pt")
        self.size_spin.valueChanged.connect(lambda v: self._set_style(font_size=float(v)))
        self.bold_btn = QPushButton("B")
        self.bold_btn.setObjectName("annotToolBtn")
        self.bold_btn.setCheckable(True)
        f = self.bold_btn.font(); f.setBold(True); self.bold_btn.setFont(f)
        self.bold_btn.setToolTip("Chữ đậm")
        self.bold_btn.toggled.connect(lambda v: self._set_style(bold=bool(v)))
        fl.addWidget(self.font_combo)
        fl.addWidget(self.size_spin)
        fl.addWidget(self.bold_btn)
        sb.addWidget(self.font_box)

        self.fill_chk = QCheckBox("Tô nền")
        self.fill_chk.setToolTip("Tô nền nhạt cùng màu cho khung / elip / hộp chữ")
        self.fill_chk.toggled.connect(self._on_fill)
        sb.addWidget(self.fill_chk)

        self.stamp_box = QWidget()
        stl = QHBoxLayout(self.stamp_box)
        stl.setContentsMargins(0, 0, 0, 0)
        stl.addWidget(QLabel("Mẫu dấu"))
        self.stamp_combo = QComboBox()
        for label, color in an.STAMP_PRESETS:
            self.stamp_combo.addItem(label, (label, color))
        self.stamp_combo.addItem("Tuỳ chỉnh…", None)
        self.stamp_combo.activated.connect(self._on_stamp_preset)
        self.stamp_date_chk = QCheckBox("Kèm ngày")
        self.stamp_date_chk.setToolTip("Thêm dòng «Ngày dd/mm/yyyy» dưới nhãn dấu")
        self.stamp_date_chk.toggled.connect(lambda v: setattr(self.controller, "stamp_with_date", bool(v)))
        stl.addWidget(self.stamp_combo)
        stl.addWidget(self.stamp_date_chk)
        sb.addWidget(self.stamp_box)

        # Hàng kiểu dáng lấy đủ chỗ cho một hàng trước; gợi ý chỉ dùng phần còn trống
        self.style_box.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        row2.addWidget(self.style_box, 0)
        self.hint_lbl = QLabel()
        self.hint_lbl.setObjectName("mutedLabel")
        # Gợi ý dài không được ép chiều rộng tối thiểu của cửa sổ: thiếu chỗ thì bị cắt, xem đủ ở tooltip
        self.hint_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row2.addWidget(self.hint_lbl, 1)
        root.addLayout(row2)

        # Phím tắt chọn công cụ — chỉ khi con trỏ đang ở khung đọc
        self._shortcuts: List[QShortcut] = []
        for td in TOOL_DEFS:
            sc = QShortcut(QKeySequence(td.shortcut), shortcut_parent)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda k=td.key: self.controller.set_tool(k))
            sc.setEnabled(False)
            self._shortcuts.append(sc)

        for box in (self.tools_box, self.style_box, self.color_box, self.width_box, self.opacity_box,
                    self.font_box, self.stamp_box):
            box.setObjectName("editToolbarBox")  # nền trong suốt (theme.py), không lệch màu với thanh công cụ

        controller.toolChanged.connect(lambda _k: self.sync_from_controller())
        controller.styleChanged.connect(self.sync_from_controller)
        self.sync_from_controller()

    def set_shortcuts_enabled(self, enabled: bool) -> None:
        for sc in self._shortcuts:
            sc.setEnabled(enabled)

    def update_history(self, can_undo: bool, can_redo: bool, undo_label: str = "", redo_label: str = "") -> None:
        self.btn_undo.setEnabled(can_undo)
        self.btn_redo.setEnabled(can_redo)
        self.btn_undo.setToolTip(f"Hoàn tác: {undo_label} (Ctrl+Z)" if undo_label else "Hoàn tác (Ctrl+Z)")
        self.btn_redo.setToolTip(f"Làm lại: {redo_label} (Ctrl+Y)" if redo_label else "Làm lại (Ctrl+Y)")

    # ─── Đồng bộ giao diện ↔ bộ điều khiển ───────────────────────────────

    def sync_from_controller(self) -> None:
        self._syncing = True
        try:
            tool = self.controller.tool
            btn = self.tool_buttons.get(tool)
            if btn is not None and not btn.isChecked():
                btn.setChecked(True)
            td = TOOL_BY_KEY[tool]
            hint = td.hint
            if tool == "stamp":
                hint = f"Nhấp vào trang để đóng dấu «{self.controller.stamp_label}»."
            self.hint_lbl.setText(hint)
            self.hint_lbl.setToolTip(hint)
            creating = tool in CREATE_TOOLS
            self.style_box.setVisible(creating)
            if not creating:
                return
            style = self.controller.style()
            color = (style.text_color if tool == "text" else style.color).upper()
            matched = self.swatches.get(color)
            if matched is not None:
                matched.setChecked(True)
            else:
                checked = self.swatch_group.checkedButton()
                if checked is not None:
                    self.swatch_group.setExclusive(False)
                    checked.setChecked(False)
                    self.swatch_group.setExclusive(True)
            self.btn_custom_color.setStyleSheet(
                "" if matched is not None else f"QPushButton {{ color: {color}; font-weight: 700; }}"
            )
            self.width_box.setVisible(tool in INK_TOOLS + SHAPE_TOOLS)
            self.width_spin.setValue(style.width)
            self.opacity_slider.setValue(int(round(style.opacity * 100)))
            self.opacity_lbl.setText(f"{int(round(style.opacity * 100))}%")
            self.font_box.setVisible(tool in ("text", "stamp"))
            self.font_combo.setVisible(tool == "text")
            self.bold_btn.setVisible(tool == "text")
            idx = self.font_combo.findData(style.font_family)
            self.font_combo.setCurrentIndex(max(0, idx))
            self.size_spin.setValue(style.font_size)
            self.bold_btn.setChecked(style.bold)
            self.fill_chk.setVisible(tool in ("rect", "ellipse", "text"))
            self.fill_chk.setChecked(bool(style.fill))
            self.stamp_box.setVisible(tool == "stamp")
            for i in range(self.stamp_combo.count()):
                data = self.stamp_combo.itemData(i)
                if data and data[0] == self.controller.stamp_label:
                    self.stamp_combo.setCurrentIndex(i)
                    break
            self.stamp_date_chk.setChecked(self.controller.stamp_with_date)
        finally:
            self._syncing = False

    def _set_style(self, **changes) -> None:
        if not self._syncing:
            self.controller.update_style(**changes)

    def _on_color(self, color: str) -> None:
        if self._syncing:
            return
        changes = {"color": color}
        style = self.controller.style()
        if style.fill and self.controller.tool in ("rect", "ellipse"):
            changes["fill"] = an.tint(color)
        self.controller.update_style(**changes)

    def _pick_color(self) -> None:
        style = self.controller.style()
        current = style.text_color if self.controller.tool == "text" else style.color
        c = QColorDialog.getColor(QColor(current), self, "Chọn màu")
        if c.isValid():
            self._on_color(c.name().upper())

    def _on_opacity(self, value: int) -> None:
        self.opacity_lbl.setText(f"{value}%")
        self._set_style(opacity=value / 100.0)

    def _on_fill(self, checked: bool) -> None:
        if self._syncing:
            return
        tool = self.controller.tool
        style = self.controller.style()
        if not checked:
            self.controller.update_style(fill=None, border=None)
        elif tool == "text":
            self.controller.update_style(fill="#FEF9C3", border="#CA8A04")
        else:
            self.controller.update_style(fill=an.tint(style.color))

    def _on_stamp_preset(self, index: int) -> None:
        data = self.stamp_combo.itemData(index)
        if data is None:
            text, ok = QInputDialog.getText(self, "Dấu tuỳ chỉnh", "Nhãn dấu (vd: ĐÃ KIỂM TRA):",
                                            text=self.controller.stamp_label)
            if ok and text.strip():
                self.controller.set_stamp_preset(text)
                label = an._nfc(text).strip().upper()
                if self.stamp_combo.findText(label) < 0:
                    self.stamp_combo.insertItem(self.stamp_combo.count() - 1, label,
                                                (label, self.controller.style("stamp").color))
            self.sync_from_controller()
            return
        label, color = data
        self.controller.set_stamp_preset(label, color)
        if self.controller.tool != "stamp":
            self.controller.set_tool("stamp")


# ─── Ngăn danh sách chú thích ─────────────────────────────────────────────


def _color_icon(color: str) -> QIcon:
    pix = QPixmap(14, 14)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setBrush(QBrush(QColor(color or "#94A3B8")))
    p.setPen(QPen(QColor(0, 0, 0, 60), 1))
    p.drawRoundedRect(QRectF(1, 1, 12, 12), 3, 3)
    p.end()
    return QIcon(pix)


class AnnotationListPanel(QWidget):
    """Ngăn «Chú thích»: danh sách mọi chú thích của tài liệu."""

    activated = Signal(int, int)  # trang, xref
    editRequested = Signal(int, int)
    deleteRequested = Signal(int, int)
    startEditingRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        self.count_lbl = QLabel()
        self.count_lbl.setWordWrap(True)
        lay.addWidget(self.count_lbl)
        self.list = QListWidget()
        self.list.setIconSize(QSize(14, 14))
        self.list.setWordWrap(True)
        self.list.itemClicked.connect(self._on_clicked)
        self.list.itemDoubleClicked.connect(self._on_double)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.btn_edit = QPushButton("✏ Sửa nội dung")
        self.btn_edit.clicked.connect(lambda: self._emit_current(self.editRequested))
        self.btn_delete = QPushButton("🗑 Xoá")
        self.btn_delete.clicked.connect(lambda: self._emit_current(self.deleteRequested))
        row.addWidget(self.btn_edit)
        row.addWidget(self.btn_delete)
        lay.addLayout(row)
        self.btn_start = QPushButton("✏️ Bật chế độ chỉnh sửa (Ctrl+E)")
        self.btn_start.setObjectName("primaryConvertBtn")
        self.btn_start.clicked.connect(self.startEditingRequested)
        lay.addWidget(self.btn_start)
        self.set_items([])

    def set_items(self, items: List[an.AnnotationInfo]) -> None:
        current = self._current()
        self.list.clear()
        for info in items:
            head = f"Tr. {info.page_index + 1} · {info.icon} {info.label}"
            meta = " · ".join(x for x in (info.author, info.modified) if x)
            body = info.content if len(info.content) <= 90 else info.content[:89] + "…"
            text = head + (f"\n{body}" if body else "") + (f"\n{meta}" if meta else "")
            item = QListWidgetItem(_color_icon(info.color), text)
            item.setData(Qt.ItemDataRole.UserRole, (info.page_index, info.xref))
            item.setToolTip(info.content or info.label)
            self.list.addItem(item)
            if current == (info.page_index, info.xref):
                self.list.setCurrentItem(item)
        n = len(items)
        self.count_lbl.setText(
            f"<b>{n} chú thích</b> trong tài liệu — nhấp để đi tới, nhấp đúp để sửa nội dung." if n else
            "Tài liệu chưa có chú thích. Bật chế độ chỉnh sửa để tô sáng, gạch chân, vẽ, chèn chữ, "
            "ghi chú hoặc đóng dấu."
        )
        self.btn_edit.setEnabled(n > 0)
        self.btn_delete.setEnabled(n > 0)

    def select(self, page_index: int, xref: int) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == (page_index, xref):
                self.list.setCurrentItem(item)
                return

    def _current(self) -> Optional[Tuple[int, int]]:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _emit_current(self, signal) -> None:
        cur = self._current()
        if cur is not None:
            signal.emit(*cur)

    def _on_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.activated.emit(*data)

    def _on_double(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.editRequested.emit(*data)
