"""Chú thích & đánh dấu trên PDF: tô sáng, gạch chân, gạch ngang, gạch sóng, vẽ tay, bút dạ quang,
khung / elip / đường thẳng / mũi tên, hộp chữ, ghi chú dán và dấu đóng («ĐÃ DUYỆT», «BẢN SAO», …).

Không phụ thuộc `PySide6`. Mọi toạ độ nhận vào là **toạ độ trang chưa xoay** của PyMuPDF (cùng hệ với
`page.get_text("words")` và các hàm `page.add_*_annot`); đổi từ toạ độ hiển thị bằng `page.derotation_matrix`.

Hộp chữ và dấu đóng không dùng hình hiển thị (appearance) do MuPDF tự sinh — phông Helvetica dựng sẵn thiếu
nhiều chữ tiếng Việt có dấu (vd «Ỷ» thành «Ý»), còn chế độ rich-text thì lệch lề và lẫn phông. Thay vào đó, hình
hiển thị được dựng bằng `insert_htmlbox` với phông TrueType của Windows (Arial / Times New Roman, nhúng tập con)
trên một trang tạm, rồi ghép thành Form XObject đặt làm `/AP /N` của chú thích — hiển thị đúng ở mọi trình đọc PDF
mà chú thích vẫn di chuyển, xoá, liệt kê được như chú thích thường.
"""

from __future__ import annotations

import getpass
import html
import json
import math
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import fitz  # PyMuPDF

Point = Union[fitz.Point, Tuple[float, float]]
RGB = Tuple[float, float, float]

QT_KEY = "QTPdfPro"  # JSON kiểu dáng hộp chữ / dấu đóng → dựng lại hình hiển thị khi sửa nội dung
QT_DELETED_KEY = "QTPdfProDeleted"  # chú thích đã xoá trong phiên (đang ẩn) → xoá hẳn khi lưu
APP_STAMP_NAME = "QTDauDong"

MARKUP_KINDS = ("highlight", "underline", "strikeout", "squiggly")
SHAPE_KINDS = ("rect", "ellipse", "line", "arrow")
MARKUP_SUBTYPES = ("Highlight", "Underline", "StrikeOut", "Squiggly")
MOVABLE_EXCLUDED = MARKUP_SUBTYPES + ("Link", "Widget", "Popup")

# Bảng màu nhanh (mã màu, tên tiếng Việt)
COLOR_PRESETS: List[Tuple[str, str]] = [
    ("#FACC15", "Vàng"),
    ("#4ADE80", "Xanh lá"),
    ("#38BDF8", "Xanh trời"),
    ("#F472B6", "Hồng"),
    ("#F97316", "Cam"),
    ("#DC2626", "Đỏ"),
    ("#2563EB", "Xanh dương"),
    ("#7C3AED", "Tím"),
    ("#111827", "Đen"),
]
_COLOR_NAMES = {
    "vang": "#FACC15", "yellow": "#FACC15",
    "xanhla": "#4ADE80", "green": "#4ADE80",
    "xanhtroi": "#38BDF8", "cyan": "#38BDF8",
    "hong": "#F472B6", "pink": "#F472B6",
    "cam": "#F97316", "orange": "#F97316",
    "do": "#DC2626", "red": "#DC2626",
    "xanh": "#2563EB", "xanhduong": "#2563EB", "blue": "#2563EB",
    "tim": "#7C3AED", "purple": "#7C3AED",
    "den": "#111827", "black": "#111827",
}

# Dấu đóng soạn sẵn (nhãn, màu)
STAMP_PRESETS: List[Tuple[str, str]] = [
    ("ĐÃ DUYỆT", "#16A34A"),
    ("BẢN SAO", "#DC2626"),
    ("MẬT", "#DC2626"),
    ("KHẨN", "#DC2626"),
    ("HỎA TỐC", "#DC2626"),
    ("ĐÃ XEM", "#2563EB"),
    ("ĐÃ KÝ", "#2563EB"),
    ("KHÔNG DUYỆT", "#DC2626"),
    ("BẢN NHÁP", "#64748B"),
]

KIND_LABELS = {
    "Highlight": ("🖍", "Tô sáng"),
    "Underline": ("U̲", "Gạch chân"),
    "StrikeOut": ("S̶", "Gạch ngang"),
    "Squiggly": ("〰", "Gạch sóng"),
    "Ink": ("✏", "Nét vẽ tay"),
    "Square": ("▭", "Khung chữ nhật"),
    "Circle": ("◯", "Hình elip"),
    "Line": ("╱", "Đường thẳng / mũi tên"),
    "PolyLine": ("╱", "Đường gấp khúc"),
    "Polygon": ("⬠", "Đa giác"),
    "FreeText": ("T", "Hộp chữ"),
    "Text": ("💬", "Ghi chú"),
    "Stamp": ("🔖", "Dấu đóng"),
    "Caret": ("‸", "Dấu chèn"),
    "FileAttachment": ("📎", "Tệp đính kèm"),
    "Redact": ("⬛", "Vùng che"),
    "Sound": ("🔊", "Âm thanh"),
}

FONT_FAMILIES: List[Tuple[str, str]] = [
    ("sans", "Arial"),
    ("serif", "Times New Roman"),
    ("mono", "Courier New"),
]
_FONT_FILES = {
    "sans": {"": "arial.ttf", "b": "arialbd.ttf", "i": "ariali.ttf", "bi": "arialbi.ttf"},
    "serif": {"": "times.ttf", "b": "timesbd.ttf", "i": "timesi.ttf", "bi": "timesbi.ttf"},
    "mono": {"": "cour.ttf", "b": "courbd.ttf", "i": "couri.ttf", "bi": "courbi.ttf"},
}
_CSS_GENERIC = {"sans": "sans-serif", "serif": "serif", "mono": "monospace"}
_BUILTIN_MEASURE_FONT = {"sans": ("helv", "hebo"), "serif": ("tiro", "tibo"), "mono": ("cour", "cobo")}

# Ma trận xoay hình hiển thị để dấu/hộp chữ luôn đứng thẳng trên trang có /Rotate
_AP_MATRIX = {0: None, 90: (0, 1, -1, 0, 0, 0), 180: (-1, 0, 0, -1, 0, 0), 270: (0, -1, 1, 0, 0, 0)}
_REF_RE = re.compile(r"(\d+) 0 R")
_NUM_RE = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


class AnnotationError(ValueError):
    """Thao tác chú thích không hợp lệ (thông báo tiếng Việt)."""


@dataclass
class AnnotStyle:
    """Kiểu dáng chú thích."""

    color: str = "#FACC15"  # màu nét / màu tô sáng / màu chữ của dấu đóng
    opacity: float = 1.0
    width: float = 1.5  # độ dày nét (pt)
    fill: Optional[str] = None  # màu nền khung / elip / hộp chữ
    font_size: float = 12.0
    font_family: str = "sans"  # "sans" | "serif" | "mono"
    bold: bool = False
    italic: bool = False
    text_color: str = "#111827"  # màu chữ hộp chữ
    border: Optional[str] = None  # màu viền hộp chữ

    def copy(self, **changes) -> "AnnotStyle":
        data = asdict(self)
        data.update(changes)
        return AnnotStyle(**data)


@dataclass
class AnnotationInfo:
    """Thông tin một chú thích để liệt kê trong ngăn «Chú thích»."""

    page_index: int
    xref: int
    subtype: str
    icon: str
    label: str
    rect: Tuple[float, float, float, float]
    color: str
    content: str
    author: str
    modified: str
    movable: bool
    app_kind: str = ""  # "textbox" | "stamp" nếu do QT PDF Pro dựng hình hiển thị

    def to_dict(self) -> dict:
        d = asdict(self)
        d["page"] = self.page_index + 1
        return d


# ─── Màu sắc ──────────────────────────────────────────────────────────────


def parse_color(value: Union[str, Sequence[float], None], default: str = "#FACC15") -> RGB:
    """`'#RRGGBB'`, `'RRGGBB'`, tên màu (`'vang'`, `'do'`, `'red'`…) hoặc bộ 3 số 0..1 / 0..255 → RGB 0..1."""
    if value is None or value == "":
        value = default
    if isinstance(value, (tuple, list)):
        nums = [float(v) for v in value[:3]]
        if any(n > 1.0 for n in nums):
            nums = [n / 255.0 for n in nums]
        return (nums[0], nums[1], nums[2])
    text = str(value).strip()
    key = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    key = "".join(c for c in key if unicodedata.category(c) != "Mn").replace(" ", "").replace("_", "")
    text = _COLOR_NAMES.get(key, text)
    hexv = text.lstrip("#")
    if len(hexv) == 3:
        hexv = "".join(c * 2 for c in hexv)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", hexv):
        raise AnnotationError(f"Màu không hợp lệ: {value}")
    return tuple(int(hexv[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def color_hex(rgb: Optional[Sequence[float]]) -> str:
    if not rgb:
        return ""
    vals = [max(0, min(255, int(round(float(c) * 255)))) for c in list(rgb)[:3]]
    if len(vals) == 1:
        vals = vals * 3
    return "#{:02X}{:02X}{:02X}".format(*vals)


def tint(color: str, amount: float = 0.75) -> str:
    """Pha màu với trắng (`amount` = tỉ lệ trắng) — dùng làm nền nhạt cho khung / hộp chữ."""
    r, g, b = parse_color(color)
    return color_hex((r + (1 - r) * amount, g + (1 - g) * amount, b + (1 - b) * amount))


def default_author() -> str:
    for key in ("QT_PDF_PRO_AUTHOR", "USERNAME", "USER"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    try:
        return getpass.getuser()
    except Exception:
        return "QT PDF Pro"


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", (text or "").replace("\r\n", "\n").replace("\r", "\n"))


def _pdf_now() -> str:
    return fitz.get_pdf_now()


def _pdf_date_text(raw: str) -> str:
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?", raw or "")
    if not m:
        return ""
    y, mo, d, hh, mm = m.groups()
    return f"{d}/{mo}/{y}" + (f" {hh}:{mm}" if hh and mm else "")


# ─── Chọn chữ trên trang ──────────────────────────────────────────────────


def page_words(page: fitz.Page) -> List[tuple]:
    """Danh sách từ `(x0, y0, x1, y1, chữ, khối, dòng, từ)` theo thứ tự đọc (toạ độ trang chưa xoay)."""
    words = page.get_text("words", sort=False)
    return sorted(words, key=lambda w: (w[5], w[6], w[7]))


def _point_rect_distance(p: fitz.Point, r: fitz.Rect) -> Tuple[float, float]:
    dx = max(r.x0 - p.x, 0.0, p.x - r.x1)
    dy = max(r.y0 - p.y, 0.0, p.y - r.y1)
    return dx, dy


def _nearest_word(words: Sequence[tuple], p: fitz.Point) -> int:
    best, best_score = 0, float("inf")
    for i, w in enumerate(words):
        dx, dy = _point_rect_distance(p, fitz.Rect(w[:4]))
        score = dy * 3.0 + dx  # ưu tiên từ cùng dòng
        if score < best_score:
            best, best_score = i, score
            if score == 0:
                break
    return best


def _line_rects(words: Iterable[tuple]) -> List[fitz.Rect]:
    rects: List[fitz.Rect] = []
    keys: List[Tuple[int, int]] = []
    for w in words:
        key = (w[5], w[6])
        r = fitz.Rect(w[:4])
        if keys and keys[-1] == key:
            rects[-1] |= r
        else:
            rects.append(r)
            keys.append(key)
    return rects


def select_text_rects(words: Sequence[tuple], p0: Point, p1: Point) -> List[fitz.Rect]:
    """Chọn chữ như kéo chuột trong trình đọc: mọi từ từ vị trí `p0` tới `p1` theo thứ tự đọc, gộp theo dòng."""
    if not words:
        return []
    i0 = _nearest_word(words, fitz.Point(p0))
    i1 = _nearest_word(words, fitz.Point(p1))
    if i0 > i1:
        i0, i1 = i1, i0
    return _line_rects(words[i0 : i1 + 1])


def words_in_rect(words: Sequence[tuple], rect: fitz.Rect) -> List[fitz.Rect]:
    """Chọn chữ theo vùng chữ nhật (giữ Alt): mọi từ giao với vùng, gộp theo dòng."""
    area = fitz.Rect(rect).normalize()
    return _line_rects(w for w in words if fitz.Rect(w[:4]).intersects(area))


def text_under_rects(page: fitz.Page, rects: Iterable[fitz.Rect], limit: int = 200) -> str:
    parts = []
    for r in rects:
        txt = page.get_textbox(fitz.Rect(r)).strip()
        if txt:
            parts.append(" ".join(txt.split()))
    text = _nfc(" ".join(parts))
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ─── Phông chữ & dựng hình hiển thị cho hộp chữ / dấu đóng ────────────────


@lru_cache(maxsize=1)
def system_font_dir() -> Optional[Path]:
    """Thư mục phông Windows có Arial/Times New Roman (hoặc `QT_PDF_PRO_FONT_DIR`); None nếu không có."""
    candidates = [os.environ.get("QT_PDF_PRO_FONT_DIR", "")]
    candidates.append(str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"))
    for c in candidates:
        if c and (Path(c) / "arial.ttf").exists():
            return Path(c)
    return None


@lru_cache(maxsize=1)
def _font_archive() -> Optional[fitz.Archive]:
    d = system_font_dir()
    return fitz.Archive(str(d)) if d else None


def _face_key(bold: bool, italic: bool) -> str:
    return ("b" if bold else "") + ("i" if italic else "")


def _font_css(family: str) -> str:
    family = family if family in _FONT_FILES else "sans"
    d = system_font_dir()
    if d is None:
        return f"body {{font-family: {_CSS_GENERIC[family]};}} "
    rules = []
    for face, fname in _FONT_FILES[family].items():
        if (d / fname).exists():
            weight = "bold" if "b" in face else "normal"
            style = "italic" if "i" in face else "normal"
            rules.append(
                f"@font-face {{font-family: QTVN; src: url({fname}); font-weight: {weight}; font-style: {style};}}"
            )
    return " ".join(rules) + " body {font-family: QTVN;} "


@lru_cache(maxsize=16)
def _measure_font(family: str, bold: bool) -> fitz.Font:
    family = family if family in _FONT_FILES else "sans"
    d = system_font_dir()
    if d is not None:
        fname = _FONT_FILES[family]["b" if bold else ""]
        if (d / fname).exists():
            return fitz.Font(fontfile=str(d / fname))
    return fitz.Font(_BUILTIN_MEASURE_FONT[family][1 if bold else 0])


def _html_paragraphs(text: str, cls: str = "") -> str:
    attr = f' class="{cls}"' if cls else ""
    lines = _nfc(text).split("\n")
    return "".join(f"<p{attr}>{html.escape(line) or '&#160;'}</p>" for line in lines)


def _story_height(html_text: str, css: str, width: float) -> float:
    story = fitz.Story(html_text, user_css=css, archive=_font_archive())
    _more, filled = story.place(fitz.Rect(0, 0, max(10.0, width), 100000))
    return float(fitz.Rect(filled).y1)


def _new_appearance_doc(width: float, height: float, draw: Callable[[fitz.Page], None]) -> fitz.Document:
    tmp = fitz.open()
    page = tmp.new_page(width=width, height=height)
    draw(page)
    try:
        tmp.subset_fonts()
    except Exception:
        pass  # không nhúng tập con được thì giữ phông đầy đủ
    return tmp


def _text_box_css(style: AnnotStyle) -> str:
    return _font_css(style.font_family) + (
        f"body {{margin:0; padding:0; color:{style.text_color}; font-size:{style.font_size:g}pt; "
        f"line-height:1.25; font-weight:{'bold' if style.bold else 'normal'}; "
        f"font-style:{'italic' if style.italic else 'normal'};}} p {{margin:0; padding:0;}}"
    )


def build_text_box_appearance(
    text: str, width: float, style: AnnotStyle, min_height: float = 0.0
) -> Tuple[fitz.Document, float, float]:
    """Trang tạm vẽ hộp chữ rộng `width` pt (cao tự khớp nội dung) → (tài liệu tạm, rộng, cao)."""
    border = style.border
    bw = 1.0 if border else 0.0
    pad = 4.0 + bw
    width = max(24.0, float(width))
    css = _text_box_css(style)
    body = _html_paragraphs(text)
    content_h = _story_height(body, css, width - 2 * pad)
    height = max(float(min_height), content_h + 2 * pad + 1.0, style.font_size * 1.25 + 2 * pad)

    def draw(page: fitz.Page) -> None:
        if style.fill or border:
            shape = page.new_shape()
            inset = bw / 2 if bw else 0.0
            shape.draw_rect(fitz.Rect(inset, inset, width - inset, height - inset))
            shape.finish(
                color=parse_color(border) if border else None,
                fill=parse_color(style.fill) if style.fill else None,
                width=bw or 0,
            )
            shape.commit()
        page.insert_htmlbox(
            fitz.Rect(pad, pad, width - pad, height - pad + 1.0), body, css=css,
            archive=_font_archive(), scale_low=1,
        )

    return _new_appearance_doc(width, height, draw), width, height


def build_stamp_appearance(
    label: str, style: AnnotStyle, date_text: Optional[str] = None
) -> Tuple[fitz.Document, float, float]:
    """Dấu đóng viền đôi bo góc, chữ in đậm (dòng ngày tuỳ chọn) → (tài liệu tạm, rộng, cao)."""
    label = _nfc(label).strip().upper() or "ĐÃ DUYỆT"
    fs = max(8.0, float(style.font_size or 18.0))
    color = style.color
    font = _measure_font(style.font_family, True)
    text_w = font.text_length(label, fontsize=fs)
    date_fs = max(6.0, fs * 0.42)
    if date_text:
        text_w = max(text_w, _measure_font(style.font_family, False).text_length(date_text, fontsize=date_fs))
    pad_x = max(10.0, fs * 0.65)
    width = text_w + 2 * pad_x + 4.0
    css = _font_css(style.font_family) + (
        f"body {{margin:0; padding:0; color:{color}; text-align:center;}} "
        f"p {{margin:0; padding:0;}} p.l {{font-size:{fs:g}pt; font-weight:bold; line-height:1.15;}} "
        f"p.d {{font-size:{date_fs:g}pt; line-height:1.2;}}"
    )
    body = _html_paragraphs(label, "l") + (_html_paragraphs(date_text, "d") if date_text else "")
    content_h = _story_height(body, css, width - 12.0)
    height = content_h + max(12.0, fs * 0.55) + 4.0
    rgb = parse_color(color)

    def draw(page: fitz.Page) -> None:
        shape = page.new_shape()
        outer = fitz.Rect(1.4, 1.4, width - 1.4, height - 1.4)
        shape.draw_rect(outer, radius=(min(0.5, 7 / outer.width), min(0.5, 7 / outer.height)))
        shape.finish(color=rgb, width=2.4)
        inner = fitz.Rect(4.6, 4.6, width - 4.6, height - 4.6)
        shape.draw_rect(inner, radius=(min(0.5, 4.5 / inner.width), min(0.5, 4.5 / inner.height)))
        shape.finish(color=rgb, width=0.8)
        shape.commit()
        top = (height - content_h) / 2.0
        page.insert_htmlbox(
            fitz.Rect(6.0, top, width - 6.0, height), body, css=css, archive=_font_archive(), scale_low=1
        )

    return _new_appearance_doc(width, height, draw), width, height


def _graft_form_xobject(dst: fitz.Document, src: fitz.Document, matrix: Optional[tuple]) -> int:
    """Chép trang 0 của `src` (nội dung + tài nguyên, kể cả phông nhúng) vào `dst` thành Form XObject."""
    page = src[0]
    width, height = page.rect.width, page.rect.height
    contents = page.read_contents()
    mapping: Dict[int, int] = {}

    def copy(xref: int) -> int:
        if xref in mapping:
            return mapping[xref]
        new = dst.get_new_xref()
        mapping[xref] = new
        obj = src.xref_object(xref, compressed=True)
        obj = _REF_RE.sub(lambda m: f"{copy(int(m.group(1)))} 0 R", obj)
        dst.update_object(new, obj)
        if src.xref_is_stream(xref):
            for key in ("Filter", "DecodeParms"):
                dst.xref_set_key(new, key, "null")
            dst.update_stream(new, src.xref_stream(xref))
        return new

    kind, res = src.xref_get_key(page.xref, "Resources")
    if kind == "xref":
        res = src.xref_object(int(res.split()[0]), compressed=True)
    elif kind != "dict":
        res = "<<>>"
    res = _REF_RE.sub(lambda m: f"{copy(int(m.group(1)))} 0 R", res)
    xo = dst.get_new_xref()
    mat = "/Matrix[%g %g %g %g %g %g]" % matrix if matrix else ""
    dst.update_object(xo, f"<</Type/XObject/Subtype/Form/BBox[0 0 {width:g} {height:g}]{mat}/Resources {res}>>")
    dst.update_stream(xo, contents)
    return xo


def _apply_custom_appearance(page: fitz.Page, annot: fitz.Annot, tmp: fitz.Document) -> int:
    doc = page.parent
    try:
        xo = _graft_form_xobject(doc, tmp, _AP_MATRIX.get(page.rotation % 360))
    finally:
        tmp.close()
    doc.xref_set_key(annot.xref, "AP", f"<</N {xo} 0 R>>")
    return xo


def _set_qt_data(doc: fitz.Document, xref: int, data: dict) -> None:
    doc.xref_set_key(xref, QT_KEY, fitz.get_pdf_str(json.dumps(data, ensure_ascii=False)))


def qt_data(doc: fitz.Document, xref: int) -> dict:
    kind, value = doc.xref_get_key(xref, QT_KEY)
    if kind != "string" or not value:
        return {}
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _display_rect(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    return (fitz.Rect(rect) * page.rotation_matrix).normalize()


def _fit_in_page(page: fitz.Page, disp: fitz.Rect) -> fitz.Rect:
    """Đẩy khung (toạ độ hiển thị) vào trong trang nếu bị tràn mép."""
    pr = page.rect
    dx = max(pr.x0 - disp.x0, 0.0) - max(disp.x1 - pr.x1, 0.0)
    dy = max(pr.y0 - disp.y0, 0.0) - max(disp.y1 - pr.y1, 0.0)
    return disp + (dx, dy, dx, dy)


# ─── Tạo chú thích ────────────────────────────────────────────────────────


def _finish_info(annot: fitz.Annot, author: str, content: Optional[str] = None) -> None:
    info = {"title": author or "", "modDate": _pdf_now()}
    if content is not None:
        info["content"] = _nfc(content)
    try:
        annot.set_info(**info)
    except Exception:
        pass


def add_text_markup(
    page: fitz.Page, kind: str, rects: Sequence[fitz.Rect], style: AnnotStyle, author: str = ""
) -> fitz.Annot:
    """Tô sáng / gạch chân / gạch ngang / gạch sóng các vùng chữ (mỗi vùng thường là một dòng)."""
    creators = {
        "highlight": page.add_highlight_annot,
        "underline": page.add_underline_annot,
        "strikeout": page.add_strikeout_annot,
        "squiggly": page.add_squiggly_annot,
    }
    if kind not in creators:
        raise AnnotationError(f"Kiểu đánh dấu chữ không hợp lệ: {kind}")
    quads = [fitz.Rect(r).quad for r in rects if not fitz.Rect(r).is_empty]
    if not quads:
        raise AnnotationError("Chưa chọn được chữ nào để đánh dấu.")
    annot = creators[kind](quads)
    annot.set_colors(stroke=parse_color(style.color))
    if style.opacity < 1:
        annot.set_opacity(style.opacity)
    _finish_info(annot, author)
    annot.update()
    return annot


def _simplify(points: Sequence[Point], min_step: float = 0.6, max_points: int = 4000) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for pt in points:
        x, y = float(pt[0]), float(pt[1])
        if not out or math.hypot(x - out[-1][0], y - out[-1][1]) >= min_step:
            out.append((x, y))
    if len(out) == 1:
        out.append((out[0][0] + 0.3, out[0][1] + 0.3))  # chấm một điểm vẫn hiện được
    if len(out) > max_points:
        step = math.ceil(len(out) / max_points)
        out = out[::step] + [out[-1]]
    return out


def add_ink(
    page: fitz.Page,
    strokes: Sequence[Sequence[Point]],
    style: AnnotStyle,
    author: str = "",
    marker: bool = False,
) -> fitz.Annot:
    """Nét vẽ tay (`marker=True`: bút dạ quang — nét to, trong suốt, hoà trộn Multiply không che chữ)."""
    clean = [_simplify(s) for s in strokes if len(s) >= 1]
    if not clean:
        raise AnnotationError("Nét vẽ trống.")
    annot = page.add_ink_annot(clean)
    annot.set_border(width=max(0.25, float(style.width)))
    annot.set_colors(stroke=parse_color(style.color))
    if style.opacity < 1:
        annot.set_opacity(style.opacity)
    if marker:
        annot.set_blendmode(fitz.PDF_BM_Multiply)
    _finish_info(annot, author)
    annot.update()
    return annot


def add_shape(
    page: fitz.Page, kind: str, p0: Point, p1: Point, style: AnnotStyle, author: str = ""
) -> fitz.Annot:
    """Khung chữ nhật, elip, đường thẳng hoặc mũi tên (mũi tên ở đầu `p1`)."""
    a, b = fitz.Point(p0), fitz.Point(p1)
    rgb = parse_color(style.color)
    if kind in ("rect", "ellipse"):
        r = fitz.Rect(a, b).normalize()
        if r.width < 2 or r.height < 2:
            raise AnnotationError("Hình quá nhỏ.")
        annot = page.add_rect_annot(r) if kind == "rect" else page.add_circle_annot(r)
        annot.set_border(width=max(0.25, float(style.width)))
        if style.fill:
            annot.set_colors(stroke=rgb, fill=parse_color(style.fill))
        else:
            annot.set_colors(stroke=rgb)
    elif kind in ("line", "arrow"):
        if math.hypot(b.x - a.x, b.y - a.y) < 2:
            raise AnnotationError("Đường quá ngắn.")
        annot = page.add_line_annot(a, b)
        annot.set_border(width=max(0.25, float(style.width)))
        if kind == "arrow":
            annot.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
            annot.set_colors(stroke=rgb, fill=rgb)
        else:
            annot.set_colors(stroke=rgb)
    else:
        raise AnnotationError(f"Kiểu hình không hợp lệ: {kind}")
    if style.opacity < 1:
        annot.set_opacity(style.opacity)
    _finish_info(annot, author)
    annot.update()
    return annot


def add_note(
    page: fitz.Page, point: Point, text: str, style: AnnotStyle, author: str = "", icon: str = "Comment"
) -> fitz.Annot:
    """Ghi chú dán (biểu tượng bong bóng, nội dung hiện khi mở ghi chú)."""
    annot = page.add_text_annot(fitz.Point(point), _nfc(text), icon=icon)
    annot.set_colors(stroke=parse_color(style.color))
    if style.opacity < 1:
        annot.set_opacity(style.opacity)
    _finish_info(annot, author, text)
    annot.update()
    return annot


def _set_rect_key(page: fitz.Page, xref: int, rect: fitz.Rect) -> None:
    """Ghi `/Rect` trực tiếp (đổi toạ độ trang chưa xoay → không gian PDF) — không làm MuPDF vẽ lại hình hiển thị."""
    r = (fitz.Rect(rect) * ~page.transformation_matrix).normalize()
    page.parent.xref_set_key(xref, "Rect", f"[{r.x0:.4f} {r.y0:.4f} {r.x1:.4f} {r.y1:.4f}]")


def _custom_annot_finish(page: fitz.Page, annot: fitz.Annot, tmp: fitz.Document, rect: fitz.Rect,
                         style: AnnotStyle, data: dict, content: str, author: Optional[str]) -> None:
    """Gắn hình hiển thị tự dựng + các khoá thông tin.

    Chỉ ghi qua xref: gọi `set_info` / `set_rect` sau bước này sẽ đánh dấu chú thích «cần vẽ lại» và MuPDF
    tự sinh lại hình hiển thị bằng Helvetica (mất dấu tiếng Việt).
    """
    doc = page.parent
    _set_rect_key(page, annot.xref, rect)
    _apply_custom_appearance(page, annot, tmp)
    doc.xref_set_key(annot.xref, "Contents", fitz.get_pdf_str(_nfc(content)))
    doc.xref_set_key(annot.xref, "CA", f"{max(0.05, min(1.0, style.opacity)):g}")
    now = fitz.get_pdf_str(_pdf_now())
    doc.xref_set_key(annot.xref, "M", now)
    if author is not None:
        doc.xref_set_key(annot.xref, "T", fitz.get_pdf_str(author))
        doc.xref_set_key(annot.xref, "CreationDate", now)
    _set_qt_data(doc, annot.xref, data)


def add_text_box(
    page: fitz.Page, rect: fitz.Rect, text: str, style: AnnotStyle, author: str = ""
) -> fitz.Annot:
    """Hộp chữ (FreeText) tại `rect`; chiều rộng theo `rect`, chiều cao tự khớp nội dung."""
    text = _nfc(text).strip("\n")
    if not text.strip():
        raise AnnotationError("Hộp chữ chưa có nội dung.")
    disp = _display_rect(page, rect)
    width = disp.width if disp.width >= 24 else 220.0
    tmp, w, h = build_text_box_appearance(text, width, style, min_height=disp.height if disp.height > 8 else 0)
    disp = _fit_in_page(page, fitz.Rect(disp.x0, disp.y0, disp.x0 + w, disp.y0 + h))
    unrot = (disp * page.derotation_matrix).normalize()
    annot = page.add_freetext_annot(unrot, "Text", fontsize=style.font_size, text_color=parse_color(style.text_color))
    data = {"kind": "textbox", "text": text, "width": w, "style": asdict(style)}
    _custom_annot_finish(page, annot, tmp, unrot, style, data, text, author)
    return annot


def add_stamp(
    page: fitz.Page,
    center: Point,
    label: str,
    style: AnnotStyle,
    author: str = "",
    date_text: Optional[str] = None,
) -> fitz.Annot:
    """Dấu đóng (Stamp) có tâm tại `center`, nhãn tiếng Việt in đậm, viền đôi bo góc."""
    tmp, w, h = build_stamp_appearance(label, style, date_text)
    c = fitz.Point(center) * page.rotation_matrix
    disp = _fit_in_page(page, fitz.Rect(c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2))
    unrot = (disp * page.derotation_matrix).normalize()
    annot = page.add_stamp_annot(unrot, stamp=0)  # MuPDF ép /Rect theo tỉ lệ dấu chuẩn → ghi lại bên dưới
    page.parent.xref_set_key(annot.xref, "Name", f"/{APP_STAMP_NAME}")
    label = _nfc(label).strip().upper()
    data = {"kind": "stamp", "label": label, "date": date_text or "", "style": asdict(style)}
    content = label + (f" — {date_text}" if date_text else "")
    _custom_annot_finish(page, annot, tmp, unrot, style, data, content, author)
    return annot


def rebuild_text_box(page: fitz.Page, xref: int, text: str) -> None:
    """Dựng lại hình hiển thị hộp chữ của QT PDF Pro với nội dung mới (giữ góc trên-trái và chiều rộng)."""
    doc = page.parent
    data = qt_data(doc, xref)
    if data.get("kind") != "textbox":
        raise AnnotationError("Chú thích không phải hộp chữ của QT PDF Pro.")
    style = AnnotStyle(**{k: v for k, v in data.get("style", {}).items() if k in AnnotStyle.__dataclass_fields__})
    annot = page.load_annot(xref)
    disp = _display_rect(page, annot.rect)
    tmp, w, h = build_text_box_appearance(_nfc(text), float(data.get("width") or disp.width), style)
    disp = _fit_in_page(page, fitz.Rect(disp.x0, disp.y0, disp.x0 + w, disp.y0 + h))
    data["text"] = _nfc(text)
    _custom_annot_finish(page, annot, tmp, (disp * page.derotation_matrix).normalize(), style, data, text, None)


# ─── Liệt kê, chọn, ẩn/xoá, di chuyển ─────────────────────────────────────


def is_marked_deleted(doc: fitz.Document, xref: int) -> bool:
    kind, value = doc.xref_get_key(xref, QT_DELETED_KEY)
    return kind == "bool" and value == "true"


def annotation_flags(doc: fitz.Document, xref: int) -> int:
    kind, value = doc.xref_get_key(xref, "F")
    try:
        return int(float(value)) if kind in ("int", "float") else 0
    except ValueError:
        return 0


def set_annotation_hidden(doc: fitz.Document, xref: int, hidden: bool) -> None:
    """Ẩn (xoá mềm, có thể hoàn tác) hoặc hiện lại một chú thích."""
    flags = annotation_flags(doc, xref)
    if hidden:
        doc.xref_set_key(xref, "F", str(flags | fitz.PDF_ANNOT_IS_HIDDEN))
        doc.xref_set_key(xref, QT_DELETED_KEY, "true")
    else:
        doc.xref_set_key(xref, "F", str(flags & ~fitz.PDF_ANNOT_IS_HIDDEN))
        doc.xref_set_key(xref, QT_DELETED_KEY, "null")


def purge_deleted(doc: fitz.Document) -> int:
    """Xoá hẳn các chú thích đã xoá mềm trong phiên (trước khi lưu tệp)."""
    count = 0
    for page in doc:
        for annot in list(page.annots()):
            if is_marked_deleted(doc, annot.xref):
                page.delete_annot(annot)
                count += 1
    return count


def is_movable_subtype(subtype: str) -> bool:
    return subtype not in MOVABLE_EXCLUDED


def _dist_point_segment(p: fitz.Point, a: fitz.Point, b: fitz.Point) -> float:
    vx, vy = b.x - a.x, b.y - a.y
    seg2 = vx * vx + vy * vy
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((p.x - a.x) * vx + (p.y - a.y) * vy) / seg2))
    return math.hypot(p.x - (a.x + t * vx), p.y - (a.y + t * vy))


def _quad_rects(points: Sequence) -> List[fitz.Rect]:
    pts = [fitz.Point(p) for p in points or []]
    rects = []
    for i in range(0, len(pts) - 3, 4):
        group = pts[i : i + 4]
        rects.append(fitz.Rect(min(p.x for p in group), min(p.y for p in group),
                               max(p.x for p in group), max(p.y for p in group)))
    return rects


def annotation_at(page: fitz.Page, point: Point, tolerance: float = 4.0) -> Optional[int]:
    """Chú thích (xref) nằm trên cùng tại điểm `point`; nét vẽ / đường thẳng xét theo khoảng cách tới nét."""
    p = fitz.Point(point)
    hit: Optional[int] = None
    for annot in page.annots():
        if annot.flags & fitz.PDF_ANNOT_IS_HIDDEN:
            continue
        r = annot.rect
        if not fitz.Rect(r.x0 - tolerance, r.y0 - tolerance, r.x1 + tolerance, r.y1 + tolerance).contains(p):
            continue
        subtype = annot.type[1]
        if subtype in ("Ink", "Line", "PolyLine"):
            verts = annot.vertices or []
            strokes = verts if verts and isinstance(verts[0], list) else [verts]
            width = float((annot.border or {}).get("width") or 1.0)
            limit = max(tolerance, width / 2 + 2.5)
            near = False
            for stroke in strokes:
                pts = [fitz.Point(v) for v in stroke]
                if len(pts) == 1 and math.hypot(p.x - pts[0].x, p.y - pts[0].y) <= limit:
                    near = True
                if any(_dist_point_segment(p, pts[i], pts[i + 1]) <= limit for i in range(len(pts) - 1)):
                    near = True
                if near:
                    break
            if not near:
                continue
        elif subtype in MARKUP_SUBTYPES:
            rects = _quad_rects(annot.vertices) or [r]
            if not any(fitz.Rect(q.x0 - 1, q.y0 - 1, q.x1 + 1, q.y1 + 1).contains(p) for q in rects):
                continue
        hit = annot.xref
    return hit


def _shift_array(text: str, dx: float, dy: float) -> str:
    def shift(m: re.Match) -> str:
        nums = [float(n) for n in _NUM_RE.findall(m.group(1))]
        out = [n + (dx if i % 2 == 0 else dy) for i, n in enumerate(nums)]
        return "[" + " ".join(f"{v:.4f}".rstrip("0").rstrip(".") for v in out) + "]"

    return re.sub(r"\[([^\[\]]*)\]", shift, text)


def translate_annotation(page: fitz.Page, xref: int, dx: float, dy: float) -> None:
    """Dời chú thích `(dx, dy)` (toạ độ trang chưa xoay) bằng cách dịch mọi khoá hình học trong không gian PDF.

    Không gọi `annot.update()` nên hình hiển thị giữ nguyên (kể cả hộp chữ / dấu đóng tự dựng) và không phình
    viền như khi dùng `set_rect` + `update` cho khung chữ nhật.
    """
    doc = page.parent
    inv = ~page.transformation_matrix
    v = fitz.Point(dx, dy) * inv - fitz.Point(0, 0) * inv
    for key in ("Rect", "QuadPoints", "InkList", "L", "Vertices", "CL"):
        kind, value = doc.xref_get_key(xref, key)
        if kind == "array":
            doc.xref_set_key(xref, key, _shift_array(value, v.x, v.y))
    doc.xref_set_key(xref, "M", fitz.get_pdf_str(_pdf_now()))


def _annot_color(annot: fitz.Annot, data: dict) -> str:
    style = data.get("style") or {}
    if data.get("kind") == "stamp" and style.get("color"):
        return str(style["color"])
    if data.get("kind") == "textbox":
        return str(style.get("fill") or style.get("text_color") or "")
    colors = annot.colors or {}
    rgb = colors.get("stroke") or colors.get("fill")
    return color_hex(rgb) if rgb else ""


def annotation_info(page: fitz.Page, annot: fitz.Annot) -> AnnotationInfo:
    doc = page.parent
    subtype = annot.type[1]
    icon, label = KIND_LABELS.get(subtype, ("•", subtype))
    info = annot.info or {}
    data = qt_data(doc, annot.xref)
    content = _nfc(info.get("content") or "")
    if subtype in MARKUP_SUBTYPES and not content:
        content = text_under_rects(page, _quad_rects(annot.vertices) or [annot.rect], limit=120)
    if data.get("kind") == "stamp":
        label = "Dấu đóng"
    return AnnotationInfo(
        page_index=page.number,
        xref=annot.xref,
        subtype=subtype,
        icon=icon,
        label=label,
        rect=tuple(round(v, 2) for v in annot.rect),  # type: ignore[arg-type]
        color=_annot_color(annot, data),
        content=content,
        author=_nfc(info.get("title") or ""),
        modified=_pdf_date_text(info.get("modDate") or info.get("creationDate") or ""),
        movable=is_movable_subtype(subtype),
        app_kind=str(data.get("kind") or ""),
    )


def list_annotations(doc: fitz.Document, pages: Optional[Iterable[int]] = None) -> List[AnnotationInfo]:
    """Mọi chú thích đang hiển thị (bỏ liên kết, trường biểu mẫu, popup và chú thích đã xoá mềm)."""
    result: List[AnnotationInfo] = []
    for pno in (pages if pages is not None else range(doc.page_count)):
        page = doc[pno]
        for annot in page.annots():
            if annot.flags & fitz.PDF_ANNOT_IS_HIDDEN:
                continue
            result.append(annotation_info(page, annot))
    return result


# ─── Đánh dấu theo nội dung chữ & thao tác hàng loạt (CLI) ────────────────


def mark_text(
    doc: fitz.Document,
    needle: str,
    kind: str,
    style: AnnotStyle,
    pages: Optional[Iterable[int]] = None,
    author: str = "",
) -> int:
    """Tô sáng / gạch chân / gạch ngang mọi chỗ xuất hiện cụm từ `needle`; trả về số chỗ đã đánh dấu."""
    q = _nfc(needle).strip()
    if not q:
        raise AnnotationError("Chưa nhập cụm từ cần đánh dấu.")
    count = 0
    for pno in (pages if pages is not None else range(doc.page_count)):
        page = doc[pno]
        quads = page.search_for(q, quads=True)
        if not quads and " " in q:
            quads = page.search_for(q.replace(" ", "\u00a0"), quads=True)
        for quad in quads:
            add_text_markup(page, kind, [quad.rect], style, author)
            count += 1
    return count


def _op_point(page: fitz.Page, value) -> fitz.Point:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise AnnotationError(f"Toạ độ điểm không hợp lệ: {value}")
    return fitz.Point(float(value[0]), float(value[1])) * page.derotation_matrix


def _op_rect(page: fitz.Page, value) -> fitz.Rect:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        raise AnnotationError(f"Toạ độ khung không hợp lệ: {value}")
    return (fitz.Rect([float(v) for v in value[:4]]) * page.derotation_matrix).normalize()


def style_from_dict(data: dict, base: Optional[AnnotStyle] = None) -> AnnotStyle:
    style = base.copy() if base else AnnotStyle()
    for key in AnnotStyle.__dataclass_fields__:
        if key in data:
            setattr(style, key, data[key])
    for key in ("color", "fill", "text_color", "border"):
        val = getattr(style, key)
        if val:
            setattr(style, key, color_hex(parse_color(val)))
    return style


def apply_operations(doc: fitz.Document, ops: Sequence[dict], author: str = "") -> int:
    """Thêm chú thích theo danh sách thao tác (JSON). Toạ độ là pt theo trang **đang hiển thị** (gốc trên-trái).

    Ví dụ: `{"type": "highlight", "text": "Độc lập", "color": "vang"}`,
    `{"type": "stamp", "page": 1, "at": [450, 90], "label": "ĐÃ DUYỆT", "date": true}`,
    `{"type": "note", "page": 2, "at": [60, 80], "text": "Bổ sung số liệu"}`,
    `{"type": "arrow", "page": 1, "from": [100, 300], "to": [200, 260], "color": "do", "width": 2}`.
    """
    count = 0
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise AnnotationError(f"Thao tác thứ {i + 1} không hợp lệ.")
        kind = str(op.get("type", "")).lower()
        style = style_from_dict(op)
        pno = int(op.get("page", 1)) - 1
        if kind in MARKUP_KINDS and op.get("text"):
            spec = op.get("pages")
            pages = None if spec in (None, "", "all") else [int(p) - 1 for p in str(spec).split(",") if p.strip()]
            if spec is None and "page" in op:
                pages = [pno]
            count += mark_text(doc, str(op["text"]), kind, style, pages, author)
            continue
        if not 0 <= pno < doc.page_count:
            raise AnnotationError(f"Thao tác thứ {i + 1}: trang {pno + 1} không tồn tại.")
        page = doc[pno]
        if kind in MARKUP_KINDS:
            area = _op_rect(page, op.get("rect"))
            rects = words_in_rect(page_words(page), area) or ([area] if kind == "highlight" else [])
            add_text_markup(page, kind, rects, style, author)
        elif kind in ("ink", "pen", "marker"):
            strokes = op.get("strokes") or [op.get("points") or []]
            pts = [[_op_point(page, p) for p in s] for s in strokes]
            if kind == "marker" and "opacity" not in op:
                style.opacity = 0.4
            add_ink(page, pts, style, author, marker=kind == "marker")
        elif kind in SHAPE_KINDS:
            add_shape(page, kind, _op_point(page, op.get("from")), _op_point(page, op.get("to")), style, author)
        elif kind in ("text", "textbox", "freetext"):
            add_text_box(page, _op_rect(page, op.get("rect")), str(op.get("text", "")), style, author)
        elif kind == "note":
            add_note(page, _op_point(page, op.get("at")), str(op.get("text", "")), style, author)
        elif kind == "stamp":
            date = op.get("date")
            date_text: Optional[str] = None
            if date is True:
                date_text = stamp_date_text()
            elif isinstance(date, str) and date:
                date_text = date
            if "color" not in op:
                style.color = dict(STAMP_PRESETS).get(_nfc(str(op.get("label", ""))).upper(), "#DC2626")
            if "font_size" not in op:
                style.font_size = 18
            add_stamp(page, _op_point(page, op.get("at")), str(op.get("label", "ĐÃ DUYỆT")), style, author, date_text)
        else:
            raise AnnotationError(f"Thao tác thứ {i + 1}: kiểu '{kind}' không được hỗ trợ.")
        count += 1
    return count


def flatten_annotations(doc: fitz.Document) -> None:
    """Làm phẳng: vẽ chú thích vào nội dung trang (không còn sửa/xoá được như chú thích)."""
    purge_deleted(doc)
    doc.bake(annots=True, widgets=False)


def stamp_date_text(today: Optional[date] = None) -> str:
    """Dòng ngày cho dấu đóng, vd «Ngày 20/10/2026»."""
    return (today or date.today()).strftime("Ngày %d/%m/%Y")
