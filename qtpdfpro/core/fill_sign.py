"""Điền & Ký (Fill & Sign): gõ chữ vào chỗ trống của văn bản in sẵn, đánh dấu ✓ ✕ ● ─, ghi ngày tháng và ký bằng
chữ ký hình ảnh (vẽ tay, gõ tên, ảnh có sẵn hoặc ảnh chụp chữ ký trên giấy).

Không phụ thuộc `PySide6`. Mọi thứ đặt lên trang đều là **chú thích có hình hiển thị tự dựng** (như hộp chữ / dấu đóng
ở `annotations.py`) nên di chuyển, xoá, hoàn tác, liệt kê được; «Xuất bản làm phẳng» mới vẽ hẳn vào trang. Lưu cùng
tệp là ghi bổ sung nên chữ ký số đã có trên văn bản vẫn còn hiệu lực.

- **Chữ tự bắt dòng chấm**: `find_leaders` tìm các dòng chấm «……», «.....», gạch dưới «____» trong chữ của trang và
  các đường kẻ ngang mảnh; `snap_text_target` đặt chân chữ (baseline) đúng lên dòng đó, cỡ chữ theo chữ in quanh đó.
- **Dấu ✓ ✕ ● ─** (`add_mark`) tự căn giữa ô vuông (☐ hoặc khung vẽ) khi nhấp gần ô.
- **Ngày tháng** theo kiểu Việt Nam (`DATE_FORMATS`, có mẫu NĐ30 «ngày 23 tháng 10 năm 2026»).
- **Chữ ký / chữ ký nháy** (`Signature`, `add_signature`) lưu trong `SignatureLibrary` — mỗi chữ ký một tệp được
  mã hoá bằng Windows DPAPI (chỉ tài khoản Windows đã tạo mới giải mã được).
- **Tách nền ảnh chụp** (`clean_signature_photo`, OpenCV): ước lượng màu giấy bằng phép đóng hình thái học, tính độ
  đậm của nét so với giấy, giữ nét bằng ngưỡng kép, bỏ đốm bụi, **giữ màu mực từng điểm** (con dấu đỏ vẫn đỏ).

Lưu ý pháp lý (hiển thị trên giao diện): chữ ký hình ảnh **không** phải chữ ký số.
"""

from __future__ import annotations

import base64
import ctypes
import json
import math
import sys
import time
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import fitz  # PyMuPDF

from qtpdfpro.core import annotations as an
from qtpdfpro.core.page_stamp import _TextStamps
from qtpdfpro.core.settings import get_data_dir

Point = Union[fitz.Point, Tuple[float, float]]

APP_SIGNATURE_NAME = "QTChuKy"
APP_MARK_NAME = "QTDauDien"

MARKS: Dict[str, Tuple[str, str]] = {  # khoá → (ký hiệu, tên tiếng Việt)
    "check": ("✓", "Dấu tích"),
    "cross": ("✕", "Dấu nhân"),
    "dot": ("●", "Chấm tròn"),
    "line": ("─", "Gạch ngang"),
}

DATE_FORMATS: List[Tuple[str, str]] = [  # khoá → mẫu strftime (ngày/tháng có số 0 đứng trước)
    ("dmy", "%d/%m/%Y"),
    ("nd30", "ngày %d tháng %m năm %Y"),
    ("nd30_cap", "Ngày %d tháng %m năm %Y"),
    ("dmy_dash", "%d-%m-%Y"),
    ("dmy_dot", "%d.%m.%Y"),
]

_LEADER_CHARS = {".": 1, "…": 3, "_": 1, "‥": 2, "·": 1}
_BOX_GLYPHS = set("☐□❑❒▢◻⬜")
_MIN_LEADER_WIDTH = 14.0
_FILL_PAD = 0.0  # lề trong của khung chữ điền (đã có lề của `_TextStamps`)

SIGNATURE_WIDTH = 150.0  # chiều rộng mặc định khi đặt chữ ký (pt)
INITIALS_WIDTH = 60.0
SIGNATURE_MAX_HEIGHT = 70.0
INITIALS_MAX_HEIGHT = 34.0
MAX_IMAGE_SIDE = 1600  # ảnh chữ ký lưu tối đa (điểm ảnh mỗi cạnh)
MAX_IMAGE_BYTES = 16 * 1024 * 1024

INK_COLORS: List[Tuple[str, str]] = [("#111827", "Đen"), ("#1E3A8A", "Xanh mực"), ("#B91C1C", "Đỏ")]


class FillSignError(an.AnnotationError):
    """Lỗi Điền & Ký (thông báo tiếng Việt)."""


# ─── Ngày tháng ───────────────────────────────────────────────────────────


def format_date(fmt: str = "dmy", today: Optional[date] = None) -> str:
    """Ngày hôm nay theo mẫu `fmt` (khoá trong `DATE_FORMATS`, hoặc chính mẫu strftime)."""
    pattern = dict(DATE_FORMATS).get(fmt, fmt or "%d/%m/%Y")
    return (today or date.today()).strftime(pattern)


# ─── Tìm chỗ điền: dòng chấm, gạch dưới, đường kẻ, ô vuông ────────────────


@dataclass
class Leader:
    """Một chỗ trống để điền, toạ độ **trang đang hiển thị** (gốc trên-trái)."""

    x0: float
    x1: float
    baseline: float  # chân chữ sẽ đặt lên
    font_size: float  # cỡ chữ của dòng in quanh đó
    source: str  # "text" (dòng chấm / gạch dưới) | "rule" (đường kẻ ngang)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    def to_dict(self) -> dict:
        return {k: round(v, 2) if isinstance(v, float) else v for k, v in asdict(self).items()}


@dataclass
class FillTarget:
    """Vị trí đặt chữ điền (toạ độ trang đang hiển thị)."""

    x: float
    baseline: float
    font_size: float
    leader: Optional[Leader] = None


def _is_display_horizontal(page: fitz.Page, direction: Sequence[float]) -> bool:
    d = fitz.Point(direction) * page.rotation_matrix - fitz.Point(0, 0) * page.rotation_matrix
    return d.x > 0.9 and abs(d.y) < 0.1


def _text_leaders(page: fitz.Page) -> List[Leader]:
    out: List[Leader] = []
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    rot = page.rotation_matrix
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            if not _is_display_horizontal(page, line.get("dir", (1, 0))):
                continue
            for span in line.get("spans", []):
                size = float(span.get("size") or 12.0)
                chars = span.get("chars", [])
                run: List[dict] = []
                count = 0

                def flush() -> None:
                    nonlocal run, count
                    while run and run[-1]["c"] == " ":
                        run.pop()
                    if run and count >= 3:
                        rects = [fitz.Rect(c["bbox"]) * rot for c in run]
                        x0 = min(r.x0 for r in rects)
                        x1 = max(r.x1 for r in rects)
                        base = (fitz.Point(run[0]["origin"]) * rot).y
                        if x1 - x0 >= _MIN_LEADER_WIDTH:
                            out.append(Leader(x0, x1, base, size, "text"))
                    run, count = [], 0

                for ch in chars:
                    c = ch.get("c", "")
                    if c in _LEADER_CHARS:
                        run.append(ch)
                        count += _LEADER_CHARS[c]
                    elif c == " " and run:
                        run.append(ch)
                    else:
                        flush()
                flush()
    return out


def _rule_leaders(page: fitz.Page, words: Sequence[fitz.Rect], default_size: float) -> List[Leader]:
    out: List[Leader] = []
    rot = page.rotation_matrix
    try:
        drawings = page.get_drawings()
    except Exception:
        return out
    for d in drawings:
        for item in d.get("items", []):
            seg: Optional[Tuple[float, float, float]] = None
            if item[0] == "l":
                a, b = fitz.Point(item[1]) * rot, fitz.Point(item[2]) * rot
                if abs(a.y - b.y) <= 0.6:
                    seg = (min(a.x, b.x), max(a.x, b.x), (a.y + b.y) / 2)
            elif item[0] == "re":
                r = (fitz.Rect(item[1]) * rot).normalize()
                if r.height <= 1.6:
                    seg = (r.x0, r.x1, (r.y0 + r.y1) / 2)
            if seg is None or seg[1] - seg[0] < 24:
                continue
            x0, x1, y = seg
            # Gạch chân của chữ in sẵn (chữ nằm sát ngay trên đường kẻ) không phải chỗ điền
            underlines_text = any(
                y - 5 <= w.y1 <= y + 1 and min(w.x1, x1) - max(w.x0, x0) > 0.4 * min(w.width, x1 - x0)
                for w in words
            )
            if not underlines_text:
                out.append(Leader(x0, x1, y - 1.5, default_size, "rule"))
    return out


def find_leaders(page: fitz.Page, default_size: float = 12.0) -> List[Leader]:
    """Mọi chỗ trống để điền trên trang: dòng chấm / gạch dưới trong chữ + đường kẻ ngang mảnh không gạch chân chữ."""
    rot = page.rotation_matrix
    words = [(fitz.Rect(w[:4]) * rot).normalize() for w in page.get_text("words")
             if not set(w[4]) <= set(_LEADER_CHARS) | {" "}]
    leaders = _text_leaders(page) + _rule_leaders(page, words, default_size)
    leaders.sort(key=lambda ld: (round(ld.baseline, 1), ld.x0))
    return leaders


def find_boxes(page: fitz.Page) -> List[fitz.Rect]:
    """Ô vuông để đánh dấu (ký tự ☐ □ … hoặc khung vuông vẽ cạnh 5–24 pt), toạ độ trang đang hiển thị."""
    rot = page.rotation_matrix
    boxes: List[fitz.Rect] = []
    raw = page.get_text("rawdict")
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    if ch.get("c") in _BOX_GLYPHS:
                        r = (fitz.Rect(ch["bbox"]) * rot).normalize()
                        side = min(r.width, r.height)
                        boxes.append(fitz.Rect(r.x0, r.y1 - side, r.x0 + side, r.y1))
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []
    for d in drawings:
        for item in d.get("items", []):
            if item[0] == "re":
                r = (fitz.Rect(item[1]) * rot).normalize()
                if 5 <= r.width <= 24 and abs(r.width - r.height) <= 2:
                    boxes.append(r)
            elif item[0] == "qu":
                r = (item[1].rect * rot).normalize()
                if 5 <= r.width <= 24 and abs(r.width - r.height) <= 2:
                    boxes.append(r)
    return boxes


def _display_point(page: fitz.Page, point: Point) -> fitz.Point:
    return fitz.Point(point) * page.rotation_matrix


def snap_text_target(
    page: fitz.Page,
    point: Point,
    font_size: float = 12.0,
    leaders: Optional[Sequence[Leader]] = None,
    snap: bool = True,
) -> FillTarget:
    """Chỗ đặt chữ khi nhấp tại `point` (toạ độ trang chưa xoay): bắt vào dòng chấm / đường kẻ gần nhất nếu có.

    Nhấp ở đầu dòng chấm (¼ đầu) thì chữ bắt đầu ngay đầu dòng; nhấp giữa dòng thì bắt đầu tại chỗ nhấp.
    Không bắt được thì chân chữ nằm hơi dưới điểm nhấp (điểm nhấp ở giữa chiều cao chữ).
    """
    p = _display_point(page, point)
    if snap:
        if leaders is None:
            leaders = find_leaders(page, font_size)
        best: Optional[Leader] = None
        best_d = 1e9
        for ld in leaders:
            fs = ld.font_size if ld.source == "text" else font_size
            if not ld.x0 - 8 <= p.x <= ld.x1 + 8:
                continue
            if not ld.baseline - fs * 1.9 - 4 <= p.y <= ld.baseline + 8:
                continue
            dist = abs(p.y - (ld.baseline - fs * 0.4))
            if dist < best_d:
                best, best_d = ld, dist
        if best is not None:
            fs = best.font_size if best.source == "text" else font_size
            fs = max(8.0, min(16.0, fs))
            x = best.x0 + 1.0 if p.x <= best.x0 + 0.25 * best.width else p.x
            # Dòng chấm nằm ở chân chữ: nâng chữ điền lên một chút để dấu dưới (ạ, ị, ụ) không lẫn vào chấm
            lift = max(1.2, fs * 0.14) if best.source == "text" else 0.4
            return FillTarget(x, best.baseline - lift, fs, best)
    return FillTarget(p.x, p.y + font_size * 0.35, font_size, None)


def snap_mark_box(page: fitz.Page, point: Point, boxes: Optional[Sequence[fitz.Rect]] = None,
                  tolerance: float = 6.0) -> Optional[fitz.Rect]:
    """Ô vuông (toạ độ hiển thị) chứa / gần điểm nhấp nhất, hoặc None."""
    p = _display_point(page, point)
    if boxes is None:
        boxes = find_boxes(page)
    best, best_d = None, 1e9
    for b in boxes:
        if fitz.Rect(b.x0 - tolerance, b.y0 - tolerance, b.x1 + tolerance, b.y1 + tolerance).contains(p):
            c = fitz.Point((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2)
            dist = math.hypot(c.x - p.x, c.y - p.y)
            if dist < best_d:
                best, best_d = fitz.Rect(b), dist
    return best


# ─── Chữ điền & ngày tháng ────────────────────────────────────────────────


def _one_line(text: str) -> str:
    return " ".join(an._nfc(text).split())


def _text_stamps(style: an.AnnotStyle, size: float) -> _TextStamps:
    return _TextStamps(style.font_family, style.bold, size, style.text_color or style.color, 1.0)


def fill_text_rect(page: fitz.Page, target: FillTarget, text: str, style: an.AnnotStyle) -> fitz.Rect:
    """Khung (toạ độ hiển thị) mà chữ điền sẽ chiếm — dùng cho xem trước."""
    font = an._measure_font(style.font_family, style.bold)
    fs = target.font_size
    w = font.text_length(_one_line(text) or "M", fontsize=fs)
    return fitz.Rect(target.x, target.baseline - font.ascender * fs, target.x + w, target.baseline - font.descender * fs)


def _place_fill_text(page: fitz.Page, target: FillTarget, text: str, style: an.AnnotStyle,
                     annot: Optional[fitz.Annot], author: Optional[str], extra: Optional[dict] = None) -> fitz.Annot:
    text = _one_line(text)
    if not text:
        raise FillSignError("Chưa nhập nội dung cần điền.")
    stamps = _text_stamps(style, target.font_size)
    label = stamps.add(text)
    stamps.finish()
    asc = stamps.font.ascender * target.font_size
    w = label.width + 2 * label.pad_x
    h = label.height + 2 * label.pad_y
    top = target.baseline - asc - label.pad_y
    disp = an._fit_in_page(page, fitz.Rect(target.x - label.pad_x, top, target.x - label.pad_x + w, top + h))
    unrot = (disp * page.derotation_matrix).normalize()
    if annot is None:
        annot = page.add_freetext_annot(unrot, "Text", fontsize=target.font_size,
                                        text_color=an.parse_color(style.text_color))
        page.parent.xref_set_key(annot.xref, "IT", "/FreeTextTypeWriter")
    data = {"kind": "filltext", "text": text, "font_size": target.font_size, "style": asdict(style)}
    data.update(extra or {})
    an._custom_annot_finish(page, annot, stamps.doc, unrot, style, data, text, author)
    return annot


def add_fill_text(
    page: fitz.Page,
    point: Point,
    text: str,
    style: an.AnnotStyle,
    author: str = "",
    snap: bool = True,
    leaders: Optional[Sequence[Leader]] = None,
    font_size: Optional[float] = None,
    kind: str = "text",
) -> fitz.Annot:
    """Gõ chữ tại `point` (toạ độ trang chưa xoay), tự bắt dòng chấm khi `snap`. `font_size` ép cỡ chữ cố định."""
    target = snap_text_target(page, point, style.font_size, leaders, snap)
    if font_size:
        target.font_size = float(font_size)
    return _place_fill_text(page, target, text, style, None, author, {"fill": kind})


def add_date(page: fitz.Page, point: Point, style: an.AnnotStyle, fmt: str = "dmy", author: str = "",
             snap: bool = True, leaders: Optional[Sequence[Leader]] = None, today: Optional[date] = None) -> fitz.Annot:
    """Ghi ngày hôm nay theo mẫu `fmt` như chữ điền."""
    return add_fill_text(page, point, format_date(fmt, today), style, author, snap, leaders, kind="date")


def rebuild_fill_text(page: fitz.Page, xref: int, text: str) -> None:
    """Sửa nội dung chữ điền (giữ đầu dòng & chân chữ)."""
    doc = page.parent
    data = an.qt_data(doc, xref)
    if data.get("kind") != "filltext":
        raise FillSignError("Chú thích không phải chữ điền của QT PDF Pro.")
    style = an.AnnotStyle(**{k: v for k, v in data.get("style", {}).items() if k in an.AnnotStyle.__dataclass_fields__})
    fs = float(data.get("font_size") or style.font_size)
    annot = page.load_annot(xref)
    disp = an._display_rect(page, annot.rect)
    stamps = _text_stamps(style, fs)
    pad_x, pad_y = stamps.add("M").pad_x, stamps.add("M").pad_y
    asc = stamps.font.ascender * fs
    stamps.close()
    target = FillTarget(disp.x0 + pad_x, disp.y0 + pad_y + asc, fs)
    _place_fill_text(page, target, text, style, annot, None, {"fill": data.get("fill", "text")})


# ─── Dấu ✓ ✕ ● ─ ─────────────────────────────────────────────────────────


def build_mark_appearance(mark: str, size: float, color: str) -> Tuple[fitz.Document, float, float]:
    """Dấu vẽ bằng nét vector (không cần phông có ký hiệu) → (tài liệu tạm, rộng, cao)."""
    if mark not in MARKS:
        raise FillSignError(f"Dấu không hợp lệ: {mark}")
    s = max(4.0, float(size))
    rgb = an.parse_color(color, "#111827")
    w, h = (s * 1.6, s * 0.5) if mark == "line" else (s, s)

    def draw(page: fitz.Page) -> None:
        shape = page.new_shape()
        lw = max(0.8, s * 0.12)
        if mark == "check":
            shape.draw_polyline([(s * 0.14, s * 0.55), (s * 0.4, s * 0.8), (s * 0.88, s * 0.18)])
            shape.finish(color=rgb, width=lw, lineCap=1, lineJoin=1, closePath=False)
        elif mark == "cross":
            shape.draw_line((s * 0.2, s * 0.2), (s * 0.8, s * 0.8))
            shape.draw_line((s * 0.8, s * 0.2), (s * 0.2, s * 0.8))
            shape.finish(color=rgb, width=lw, lineCap=1, closePath=False)
        elif mark == "dot":
            shape.draw_circle((s / 2, s / 2), s * 0.28)
            shape.finish(color=rgb, fill=rgb, width=0)
        else:
            shape.draw_line((s * 0.08, h / 2), (w - s * 0.08, h / 2))
            shape.finish(color=rgb, width=max(0.8, s * 0.1), lineCap=1, closePath=False)
        shape.commit()

    return an._new_appearance_doc(w, h, draw), w, h


def add_mark(
    page: fitz.Page,
    point: Point,
    mark: str,
    style: an.AnnotStyle,
    author: str = "",
    snap: bool = True,
    boxes: Optional[Sequence[fitz.Rect]] = None,
) -> fitz.Annot:
    """Đặt dấu ✓ ✕ ● ─ có tâm tại `point`; nhấp gần ô vuông thì căn giữa ô, cỡ dấu theo ô."""
    size = float(style.font_size or 12.0)
    center = _display_point(page, point)
    box = snap_mark_box(page, point, boxes) if snap and mark != "line" else None
    if box is not None:
        size = max(5.0, min(box.width, box.height) * 0.86)
        center = fitz.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
    tmp, w, h = build_mark_appearance(mark, size, style.color)
    disp = an._fit_in_page(page, fitz.Rect(center.x - w / 2, center.y - h / 2, center.x + w / 2, center.y + h / 2))
    unrot = (disp * page.derotation_matrix).normalize()
    annot = page.add_stamp_annot(unrot, stamp=0)
    page.parent.xref_set_key(annot.xref, "Name", f"/{APP_MARK_NAME}")
    symbol, name = MARKS[mark]
    data = {"kind": "fillmark", "mark": mark, "size": size, "style": asdict(style)}
    an._custom_annot_finish(page, annot, tmp, unrot, style, data, f"{symbol} {name}", author)
    return annot


# ─── Chữ ký hình ảnh ──────────────────────────────────────────────────────


@dataclass
class Signature:
    """Chữ ký hoặc chữ ký nháy đã lưu.

    - `drawn`: `strokes` = các nét, mỗi nét là dãy điểm (x, y) bất kỳ đơn vị, y hướng xuống; `pen` = độ dày nét so
      với chiều rộng chữ ký (vd 0,016 × 150 pt ≈ 2,4 pt).
    - `typed`: `text` vẽ bằng phông `font` (khoá trong `SCRIPT_FONTS`).
    - `image`: `png` = ảnh PNG có kênh trong suốt (đã tách nền).
    """

    kind: str
    initials: bool = False
    name: str = ""
    color: str = "#1E3A8A"
    strokes: List[List[Tuple[float, float]]] = field(default_factory=list)
    pen: float = 0.016
    text: str = ""
    font: str = "times_italic"
    png: bytes = b""
    id: str = ""
    created: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in ("drawn", "typed", "image"):
            raise FillSignError(f"Kiểu chữ ký không hợp lệ: {self.kind}")
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.created:
            self.created = time.time()

    @property
    def label(self) -> str:
        what = "Chữ ký nháy" if self.initials else "Chữ ký"
        how = {"drawn": "vẽ tay", "typed": "gõ tên", "image": "ảnh"}[self.kind]
        return f"{what} ({how})" + (f" — {self.name}" if self.name else "")

    def is_empty(self) -> bool:
        if self.kind == "drawn":
            return not any(len(s) >= 2 for s in self.strokes)
        if self.kind == "typed":
            return not self.text.strip()
        return not self.png

    def to_payload(self) -> dict:
        d = asdict(self)
        d["png"] = base64.b64encode(self.png).decode("ascii") if self.png else ""
        return d

    @classmethod
    def from_payload(cls, data: dict) -> "Signature":
        data = dict(data)
        png = data.pop("png", "") or ""
        strokes = [[(float(x), float(y)) for x, y in s] for s in data.pop("strokes", []) or []]
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(png=base64.b64decode(png) if png else b"", strokes=strokes, **known)


# Phông cho chữ ký gõ tên: (khoá, tên hiển thị, tệp trong thư mục phông Windows). Phông viết tay của Windows thiếu
# chữ tiếng Việt có dấu (Segoe Script không có «ễ», «ư»…) → chỉ dùng khi đủ chữ, không thì lùi về Times nghiêng.
SCRIPT_FONTS: List[Tuple[str, str, str]] = [
    ("times_italic", "Times New Roman nghiêng", "timesi.ttf"),
    ("times_bold_italic", "Times New Roman đậm nghiêng", "timesbi.ttf"),
    ("segoe_script", "Segoe Script", "segoesc.ttf"),
    ("segoe_print", "Segoe Print", "segoepr.ttf"),
    ("ink_free", "Ink Free", "Inkfree.ttf"),
    ("gabriola", "Gabriola", "Gabriola.ttf"),
]


def _script_font_file(key: str) -> Optional[Path]:
    d = an.system_font_dir()
    if d is None:
        return None
    for k, _name, fname in SCRIPT_FONTS:
        if k == key and (d / fname).exists():
            return d / fname
    return None


def font_supports(key: str, text: str) -> bool:
    """Phông `key` có đủ mọi chữ của `text` (kể cả tiếng Việt có dấu) không."""
    path = _script_font_file(key)
    if path is None:
        return False
    font = fitz.Font(fontfile=str(path))
    return all(c.isspace() or font.has_glyph(ord(c)) for c in an._nfc(text))


def available_script_fonts(text: str = "") -> List[Tuple[str, str, bool]]:
    """(khoá, tên, đủ chữ cho `text`) của các phông có trên máy."""
    return [(k, name, font_supports(k, text or "Aa")) for k, name, _f in SCRIPT_FONTS if _script_font_file(k)]


def resolve_script_font(key: str, text: str) -> Tuple[Optional[Path], str]:
    """Tệp phông dùng thật cho chữ ký gõ tên (lùi về Times nghiêng nếu phông chọn thiếu chữ)."""
    for k in (key, "times_italic", "times_bold_italic"):
        if font_supports(k, text):
            return _script_font_file(k), k
    return None, "tiit"


def _strokes_bounds(strokes: Sequence[Sequence[Tuple[float, float]]]) -> Optional[fitz.Rect]:
    pts = [p for s in strokes for p in s]
    if not pts:
        return None
    return fitz.Rect(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _image_size(png: bytes) -> Tuple[int, int]:
    pix = fitz.Pixmap(png)
    return pix.width, pix.height


def signature_aspect(sig: Signature) -> float:
    """Tỷ lệ cao / rộng tự nhiên của chữ ký."""
    if sig.kind == "drawn":
        b = _strokes_bounds(sig.strokes)
        if b is None or b.width <= 0:
            return 0.4
        return max(0.08, b.height / b.width)
    if sig.kind == "image":
        w, h = _image_size(sig.png)
        return max(0.05, h / max(1, w))
    path, key = resolve_script_font(sig.font, sig.text)
    font = fitz.Font(fontfile=str(path)) if path else fitz.Font(key)
    width = font.text_length(an._nfc(sig.text), fontsize=1.0)
    return max(0.12, (font.ascender - font.descender) / max(0.01, width))


def default_signature_size(sig: Signature) -> Tuple[float, float]:
    """Kích thước đặt mặc định (rộng, cao) pt: chữ ký rộng 150 pt, chữ ký nháy 60 pt, giới hạn chiều cao."""
    width = INITIALS_WIDTH if sig.initials else SIGNATURE_WIDTH
    max_h = INITIALS_MAX_HEIGHT if sig.initials else SIGNATURE_MAX_HEIGHT
    aspect = signature_aspect(sig)
    height = width * aspect
    if height > max_h:
        height = max_h
        width = height / aspect
    return width, height


def _smooth_path(shape: "fitz.Shape", pts: Sequence[fitz.Point]) -> None:
    """Đường cong mượt qua các điểm (Bézier bậc 2 qua trung điểm, đổi sang bậc 3)."""
    if len(pts) == 1:
        p = pts[0]
        shape.draw_line(p, fitz.Point(p.x + 0.01, p.y + 0.01))
        return
    if len(pts) == 2:
        shape.draw_line(pts[0], pts[1])
        return
    start = pts[0]
    for i in range(1, len(pts) - 1):
        ctrl = pts[i]
        end = pts[-1] if i == len(pts) - 2 else fitz.Point((pts[i].x + pts[i + 1].x) / 2, (pts[i].y + pts[i + 1].y) / 2)
        c1 = start + (ctrl - start) * (2 / 3)
        c2 = end + (ctrl - end) * (2 / 3)
        shape.draw_bezier(start, c1, c2, end)
        start = end


def build_signature_appearance(sig: Signature, width: float, height: float) -> Tuple[fitz.Document, float, float]:
    """Trang tạm `width × height` pt vẽ chữ ký (nét vector, chữ nhúng phông, hoặc ảnh có kênh trong suốt)."""
    if sig.is_empty():
        raise FillSignError("Chữ ký trống.")
    w, h = max(4.0, float(width)), max(4.0, float(height))
    rgb = an.parse_color(sig.color, "#1E3A8A")

    def draw(page: fitz.Page) -> None:
        if sig.kind == "drawn":
            b = _strokes_bounds(sig.strokes)
            assert b is not None
            lw = max(0.6, sig.pen * w)
            inner = fitz.Rect(lw / 2, lw / 2, w - lw / 2, h - lw / 2)
            k = min(inner.width / max(b.width, 1e-6), inner.height / max(b.height, 1e-6))
            ox = inner.x0 + (inner.width - b.width * k) / 2
            oy = inner.y0 + (inner.height - b.height * k) / 2
            shape = page.new_shape()
            for stroke in sig.strokes:
                pts = [fitz.Point(ox + (x - b.x0) * k, oy + (y - b.y0) * k) for x, y in stroke]
                if pts:
                    _smooth_path(shape, pts)
                    shape.finish(color=rgb, width=lw, lineCap=1, lineJoin=1, closePath=False)
            shape.commit()
        elif sig.kind == "image":
            page.insert_image(fitz.Rect(0, 0, w, h), stream=sig.png, keep_proportion=True)
        else:
            text = an._nfc(sig.text).strip()
            path, key = resolve_script_font(sig.font, text)
            font = fitz.Font(fontfile=str(path)) if path else fitz.Font(key)
            span = font.ascender - font.descender
            fs = min(h / span, w / max(0.01, font.text_length(text, fontsize=1.0)))
            tw = font.text_length(text, fontsize=fs)
            x = (w - tw) / 2
            y = (h - span * fs) / 2 + font.ascender * fs
            page.insert_text((x, y), text, fontsize=fs, fontname="QTSig" if path else key,
                             fontfile=str(path) if path else None, color=rgb)

    return an._new_appearance_doc(w, h, draw), w, h


def render_signature_png(sig: Signature, height_px: int = 64, max_width_px: int = 360) -> bytes:
    """Ảnh xem trước PNG (nền trong suốt) — dùng cho danh sách chữ ký trên giao diện."""
    aspect = signature_aspect(sig)
    hp = max(8, int(height_px))
    wp = int(hp / aspect)
    if wp > max_width_px:
        wp = max_width_px
        hp = max(8, int(wp * aspect))
    tmp, w, h = build_signature_appearance(sig, 100.0, 100.0 * aspect)
    try:
        pix = tmp[0].get_pixmap(matrix=fitz.Matrix(wp / w, hp / h), alpha=True)
        return pix.tobytes("png")
    finally:
        tmp.close()


def add_signature(
    page: fitz.Page,
    sig: Signature,
    center: Optional[Point] = None,
    rect: Optional[fitz.Rect] = None,
    author: str = "",
    width: Optional[float] = None,
) -> fitz.Annot:
    """Đặt chữ ký: `rect` (toạ độ trang chưa xoay, kéo chuột) → vừa khung giữ tỷ lệ; không thì tâm tại `center`."""
    aspect = signature_aspect(sig)
    if rect is not None and fitz.Rect(rect).width >= 8 and fitz.Rect(rect).height >= 4:
        box = an._display_rect(page, fitz.Rect(rect))
        w = box.width
        h = w * aspect
        if h > box.height:
            h = box.height
            w = h / aspect
        c = fitz.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
    else:
        if center is None:
            raise FillSignError("Chưa chọn chỗ đặt chữ ký.")
        w, h = default_signature_size(sig)
        if width:
            w, h = float(width), float(width) * aspect
        c = _display_point(page, center)
    tmp, w, h = build_signature_appearance(sig, w, h)
    disp = an._fit_in_page(page, fitz.Rect(c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2))
    unrot = (disp * page.derotation_matrix).normalize()
    annot = page.add_stamp_annot(unrot, stamp=0)
    page.parent.xref_set_key(annot.xref, "Name", f"/{APP_SIGNATURE_NAME}")
    data = {"kind": "signature", "initials": sig.initials, "sig_kind": sig.kind, "sig_id": sig.id}
    style = an.AnnotStyle(color=sig.color)
    content = ("Chữ ký nháy" if sig.initials else "Chữ ký") + (f" — {sig.name}" if sig.name else "")
    an._custom_annot_finish(page, annot, tmp, unrot, style, data, content, author)
    return annot


# ─── Ảnh chữ ký: chuẩn hoá & tách nền ảnh chụp ────────────────────────────


def _cv():
    try:
        import cv2  # noqa: PLC0415 - chỉ nạp OpenCV khi cần
        import numpy as np  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - requirements.txt đã có opencv
        raise FillSignError("Thiếu thư viện OpenCV (opencv-python) để xử lý ảnh chữ ký.") from exc
    return cv2, np


def _decode(data: bytes, unchanged: bool):
    cv2, np = _cv()
    if not data:
        raise FillSignError("Tệp ảnh trống.")
    if len(data) > MAX_IMAGE_BYTES:
        raise FillSignError("Ảnh quá lớn (tối đa 16 MB).")
    flag = cv2.IMREAD_UNCHANGED if unchanged else cv2.IMREAD_COLOR  # IMREAD_COLOR xoay theo EXIF ảnh điện thoại
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flag)
    if img is None:
        raise FillSignError("Không đọc được ảnh (hãy dùng PNG, JPG, BMP hoặc WEBP).")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.dtype != np.uint8:
        img = cv2.convertScaleAbs(img, alpha=255.0 / max(1.0, float(img.max())))
    return img


def _downscale(img, max_side: int):
    cv2, _np = _cv()
    h, w = img.shape[:2]
    k = max_side / max(h, w)
    if k < 1:
        img = cv2.resize(img, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA)
    return img


def _trim_encode(bgra, pad: int = 8) -> bytes:
    cv2, np = _cv()
    alpha = bgra[:, :, 3]
    ys, xs = np.nonzero(alpha > 8)
    if len(xs) == 0:
        raise FillSignError("Không tìm thấy nét chữ ký trong ảnh — thử tăng «độ nhạy mực» hoặc chụp gần hơn.")
    y0, y1 = max(0, ys.min() - pad), min(bgra.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(bgra.shape[1], xs.max() + pad + 1)
    out = _downscale(bgra[y0:y1, x0:x1], MAX_IMAGE_SIDE)
    ok, buf = cv2.imencode(".png", out)
    if not ok:
        raise FillSignError("Không ghi được ảnh chữ ký.")
    return buf.tobytes()


def clean_signature_photo(data: bytes, sensitivity: int = 50, keep_color: bool = True) -> bytes:
    """Ảnh chụp / ảnh quét chữ ký (con dấu) trên giấy → PNG nền trong suốt, cắt sát nét.

    1. **Màu giấy**: phép đóng hình thái học (giãn rồi co) trên từng kênh xoá nét bút mảnh hơn cửa sổ, giữ lại độ
       sáng của giấy kể cả chỗ tối do bóng tay / ánh sáng không đều.
    2. **Độ đậm** của mỗi điểm so với giấy, làm mượt nhẹ để nét bút bi có lõi sáng vẫn liền.
    3. **Ngưỡng kép**: điểm đậm hơn ngưỡng là mực; điểm mờ hơn (tới ½ ngưỡng) chỉ giữ khi dính với vùng có mực thật
       → giữ được đầu nét mờ, bỏ đốm bụi. `sensitivity` 0–100: càng cao càng nhận nét mờ.
    4. **Màu mực**: `keep_color` khôi phục màu thật của từng điểm (mực xanh, con dấu đỏ) từ màu ảnh chia cho màu giấy;
       tắt thì tô một màu trung bình. Độ trong suốt theo độ đậm (mép nét mềm).
    """
    cv2, np = _cv()
    img = _downscale(_decode(data, unchanged=False), 2400)
    h, w = img.shape[:2]
    radius = max(4, int(round(max(h, w) * 0.012)))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * radius + 1, 2 * radius + 1))
    imgf = img.astype(np.float32)
    # Kênh tối nhất: mực màu nào cũng tối ở ít nhất một kênh (mực đỏ tối ở kênh xanh), còn giấy sáng ở mọi kênh —
    # đóng từng kênh riêng sẽ coi con dấu đỏ là «giấy» ở kênh đỏ. Phép đóng bám theo cả mép bóng sắc nét — không
    # làm mờ thêm, kẻo dải sáng tràn qua mép bóng thành «mực».
    value = img.min(axis=2)
    gray_paper = cv2.morphologyEx(value, cv2.MORPH_CLOSE, kernel, borderType=cv2.BORDER_REPLICATE).astype(np.float32)
    gray_paper = np.maximum(gray_paper, value.astype(np.float32))
    darkness = np.clip(gray_paper - value, 0, 255)
    darkness = cv2.GaussianBlur(darkness, (0, 0), max(0.6, radius / 8))
    # Vùng tối lớn (mặt bàn ngoài tờ giấy) không phải mực — xoá cả dải mép giáp giấy
    dark_area = (gray_paper < 0.45 * float(np.percentile(gray_paper, 95))).astype(np.uint8)
    dark_area = cv2.dilate(dark_area, kernel, iterations=1).astype(bool)
    darkness[dark_area] = 0

    s = max(0, min(100, int(sensitivity))) / 100.0
    thr = 100.0 + (12.0 - 100.0) * s
    strong = darkness >= thr
    weak = (darkness >= thr * 0.5).astype(np.uint8)
    n, labels, stats, _c = cv2.connectedComponentsWithStats(weak, connectivity=8)
    if n <= 1 or not strong.any():
        raise FillSignError("Không tìm thấy nét chữ ký trong ảnh — thử tăng «độ nhạy mực» hoặc chụp gần hơn.")
    has_ink = np.zeros(n, dtype=bool)
    has_ink[np.unique(labels[strong])] = True
    min_area = max(6, int(h * w * 0.00002))
    has_ink &= stats[:, cv2.CC_STAT_AREA] >= min_area
    has_ink[0] = False
    keep = has_ink[labels]

    alpha = np.clip((darkness - thr * 0.5) / (thr * 0.5), 0.0, 1.0)
    alpha[~keep] = 0.0
    if keep_color:
        # Màu giấy = độ sáng giấy × sắc giấy chung của ảnh (đo trên các điểm chắc chắn là giấy)
        paper_px = (darkness < thr * 0.15) & ~dark_area
        tint = np.ones(3, dtype=np.float32)
        if paper_px.sum() > 100:
            tint = np.median(imgf[paper_px] / np.maximum(gray_paper[paper_px], 1.0)[:, None], axis=0)
        paper = gray_paper[:, :, None] * tint[None, None, :]
        a = np.maximum(alpha, 0.25)[:, :, None]
        norm = np.clip(imgf / np.maximum(paper, 1.0) * 255.0, 0, 255)
        ink = np.clip(255.0 - (255.0 - norm) / a, 0, 255)
    else:
        sel = alpha > 0.6
        mean = imgf[sel].mean(axis=0) if sel.any() else np.array([40.0, 40.0, 40.0])
        ink = np.broadcast_to(mean, imgf.shape)
    bgra = np.dstack([ink, alpha * 255.0]).astype(np.uint8)
    bgra[bgra[:, :, 3] == 0] = 0  # điểm trong suốt không mang màu nhiễu → PNG nhỏ hơn nhiều
    return _trim_encode(bgra)


def prepare_signature_image(data: bytes, clean: Optional[bool] = None, sensitivity: int = 50,
                            keep_color: bool = True) -> bytes:
    """Ảnh chữ ký có sẵn → PNG RGBA cắt sát nét. Ảnh đã có nền trong suốt giữ nguyên; ảnh nền trắng/giấy thì tách
    nền (`clean` None = tự quyết theo việc ảnh có kênh trong suốt hay không)."""
    cv2, np = _cv()
    img = _decode(data, unchanged=True)
    has_alpha = img.ndim == 3 and img.shape[2] == 4 and int(img[:, :, 3].min()) < 250
    if clean is None:
        clean = not has_alpha
    if clean:
        if has_alpha:  # ghép lên nền trắng trước khi tách nền
            a = img[:, :, 3:4].astype(np.float32) / 255.0
            img = (img[:, :, :3].astype(np.float32) * a + 255.0 * (1 - a)).astype(np.uint8)
            ok, buf = cv2.imencode(".png", img)
            data = buf.tobytes()
        return clean_signature_photo(data, sensitivity, keep_color)
    if img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    return _trim_encode(_downscale(img, 4096))


# ─── Thư viện chữ ký (mã hoá DPAPI) ───────────────────────────────────────


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


_DPAPI_ENTROPY = b"QTPdfPro.SignatureLibrary.v1"


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    buf_in = ctypes.create_string_buffer(data, len(data))
    ent = ctypes.create_string_buffer(_DPAPI_ENTROPY, len(_DPAPI_ENTROPY))
    blob_in = _Blob(len(data), ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_char)))
    blob_ent = _Blob(len(_DPAPI_ENTROPY), ctypes.cast(ent, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN
    if protect:
        ok = fn(ctypes.byref(blob_in), "QT PDF Pro", ctypes.byref(blob_ent), None, None, flags, ctypes.byref(blob_out))
    else:
        ok = fn(ctypes.byref(blob_in), None, ctypes.byref(blob_ent), None, None, flags, ctypes.byref(blob_out))
    if not ok:
        raise FillSignError("Không mã hoá / giải mã được thư viện chữ ký (DPAPI).")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


_MAGIC_DPAPI = b"QTSIG1D"
_MAGIC_PLAIN = b"QTSIG1P"


def encode_signature_file(sig: Signature) -> bytes:
    raw = json.dumps(sig.to_payload(), ensure_ascii=False).encode("utf-8")
    if sys.platform == "win32":
        return _MAGIC_DPAPI + _dpapi(raw, protect=True)
    return _MAGIC_PLAIN + raw  # ngoài Windows không có DPAPI — chỉ dùng khi phát triển


def decode_signature_file(data: bytes) -> Signature:
    if data.startswith(_MAGIC_DPAPI):
        raw = _dpapi(data[len(_MAGIC_DPAPI):], protect=False)
    elif data.startswith(_MAGIC_PLAIN):
        raw = data[len(_MAGIC_PLAIN):]
    else:
        raise FillSignError("Tệp chữ ký không hợp lệ.")
    return Signature.from_payload(json.loads(raw.decode("utf-8")))


class SignatureLibrary:
    """Chữ ký đã lưu ở `<thư mục dữ liệu>/signatures/<id>.qtsig` (mã hoá DPAPI theo tài khoản Windows)."""

    SUFFIX = ".qtsig"

    def __init__(self, folder: Optional[Path] = None) -> None:
        self.folder = Path(folder) if folder is not None else get_data_dir() / "signatures"

    def _path(self, sig_id: str) -> Path:
        safe = "".join(c for c in sig_id if c.isalnum())
        if not safe:
            raise FillSignError("Mã chữ ký không hợp lệ.")
        return self.folder / f"{safe}{self.SUFFIX}"

    def list(self, initials: Optional[bool] = None) -> List[Signature]:
        """Chữ ký đã lưu (cũ trước); tệp hỏng / của tài khoản khác bị bỏ qua."""
        if not self.folder.is_dir():
            return []
        result = []
        for path in self.folder.glob(f"*{self.SUFFIX}"):
            try:
                sig = decode_signature_file(path.read_bytes())
            except Exception:
                continue
            if initials is None or sig.initials == initials:
                result.append(sig)
        return sorted(result, key=lambda s: s.created)

    def get(self, sig_id: str) -> Optional[Signature]:
        path = self._path(sig_id)
        if not path.exists():
            return None
        try:
            return decode_signature_file(path.read_bytes())
        except Exception:
            return None

    def save(self, sig: Signature) -> Signature:
        if sig.is_empty():
            raise FillSignError("Chữ ký trống — hãy vẽ, gõ tên hoặc chọn ảnh trước khi lưu.")
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self._path(sig.id)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(encode_signature_file(sig))
        tmp.replace(path)
        return sig

    def delete(self, sig_id: str) -> bool:
        path = self._path(sig_id)
        if path.exists():
            path.unlink()
            return True
        return False


# ─── Thao tác hàng loạt (CLI) ─────────────────────────────────────────────


def _normalize_key(text: str) -> str:
    t = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def apply_fill_operations(doc: fitz.Document, ops: Sequence[dict], author: str = "",
                          library: Optional[SignatureLibrary] = None) -> int:
    """Điền & ký theo danh sách thao tác. Toạ độ là pt trên trang **đang hiển thị** (gốc trên-trái).

    `{"type": "text", "page": 1, "at": [150, 210], "text": "Nguyễn Văn A"}` (tự bắt dòng chấm, `"snap": false` để tắt),
    `{"type": "check" | "cross" | "dot" | "line", "page": 1, "at": [72, 400]}`,
    `{"type": "date", "page": 1, "at": [380, 120], "format": "nd30"}`,
    `{"type": "signature", "page": 1, "at": [420, 700], "image": "chu_ky.png", "clean": true, "width": 140}`
    (hoặc `"id"` của chữ ký trong thư viện, `"text"` để ký bằng tên gõ, `"initials": true` cho chữ ký nháy).
    """
    count = 0
    leaders_cache: Dict[int, List[Leader]] = {}
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise FillSignError(f"Thao tác thứ {i + 1} không hợp lệ.")
        kind = _normalize_key(str(op.get("type", "")))
        pno = int(op.get("page", 1)) - 1
        if not 0 <= pno < doc.page_count:
            raise FillSignError(f"Thao tác thứ {i + 1}: trang {pno + 1} không tồn tại.")
        page = doc[pno]
        at = op.get("at")
        if not isinstance(at, (list, tuple)) or len(at) < 2:
            raise FillSignError(f"Thao tác thứ {i + 1}: thiếu toạ độ «at»: [x, y].")
        point = fitz.Point(float(at[0]), float(at[1])) * page.derotation_matrix
        style = an.style_from_dict(op, an.AnnotStyle(color="#111827", text_color="#111827", font_family="serif",
                                                     font_size=float(op.get("font_size", 12))))
        if "color" in op:
            style.text_color = style.color
        snap = bool(op.get("snap", True))
        if kind in ("text", "chu", "go"):
            leaders = leaders_cache.setdefault(pno, find_leaders(page, style.font_size))
            add_fill_text(page, point, str(op.get("text", "")), style, author, snap, leaders,
                          font_size=op.get("font_size"))
        elif kind in ("date", "ngay"):
            leaders = leaders_cache.setdefault(pno, find_leaders(page, style.font_size))
            text = str(op["text"]) if op.get("text") else format_date(str(op.get("format", "dmy")))
            add_fill_text(page, point, text, style, author, snap, leaders, font_size=op.get("font_size"), kind="date")
        elif kind in MARKS:
            add_mark(page, point, kind, style, author, snap)
        elif kind in ("signature", "sign", "initials", "chuky"):
            initials = bool(op.get("initials")) or kind == "initials"
            sig: Optional[Signature] = None
            if op.get("id"):
                sig = (library or SignatureLibrary()).get(str(op["id"]))
                if sig is None:
                    raise FillSignError(f"Không có chữ ký mã «{op['id']}» trong thư viện.")
            elif op.get("image"):
                png = prepare_signature_image(Path(str(op["image"])).read_bytes(), op.get("clean"),
                                              int(op.get("sensitivity", 50)), bool(op.get("keep_color", True)))
                sig = Signature("image", initials, png=png)
            elif op.get("text"):
                sig = Signature("typed", initials, text=str(op["text"]), color=str(op.get("color") or "#1E3A8A"),
                                font=str(op.get("font", "times_italic")))
            else:
                raise FillSignError(f"Thao tác thứ {i + 1}: chữ ký cần «id», «image» hoặc «text».")
            add_signature(page, sig, center=point, author=author, width=op.get("width"))
        else:
            raise FillSignError(f"Thao tác thứ {i + 1}: kiểu '{op.get('type')}' không được hỗ trợ.")
        count += 1
    return count
