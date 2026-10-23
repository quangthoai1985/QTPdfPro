"""Đóng dấu nước chữ & đánh số trang lên tệp PDF.

Không phụ thuộc `PySide6`. Cách dựng (tránh lỗi «Ỷ» → «Ý» của phông Helvetica dựng sẵn trong PDF):

1. Vẽ chữ lên **tài liệu tạm** bằng phông TrueType của Windows (Arial / Times New Roman — cùng thư mục phông với
   hộp chữ của `annotations.py`), mỗi nhãn một trang vừa khít chữ; mọi trang dùng chung một phông →
   `subset_fonts()` chỉ nhúng các ký tự đã dùng (vài chục KB).
2. Thu gọn bảng độ rộng `/W` và `ToUnicode` của phông về đúng các ký tự đã dùng (MuPDF ghi cho cả phông, ~25 KB),
   đồng thời dấu cách chép ra là U+0020 (MuPDF ghi U+00A0 vì Arial/Times dùng chung một glyph cho hai mã).
3. Đặt trang tạm lên từng trang đích bằng `show_pdf_page` (Form XObject dùng lại, chữ vẫn tìm kiếm / chép được).
   Toạ độ tính theo **trang đang hiển thị** rồi nhân `page.derotation_matrix`, góc xoay cộng thêm `/Rotate`
   của trang → chữ luôn đứng đúng chiều người đọc, kể cả trang xoay 90° / 180° / 270°.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # PyMuPDF

from qtpdfpro.core.annotations import _FONT_FILES, _measure_font, _nfc, parse_color, system_font_dir
from qtpdfpro.core.page_ops import parse_page_selection, save_pdf
from qtpdfpro.core.pdf_io import (
    PathLike,
    PdfToolError,
    ToolResult,
    check_signature,
    is_protected,
    open_pdf,
    resolve_output,
)

MM = 72.0 / 25.4

POSITIONS: List[Tuple[str, str]] = [
    ("top-left", "Đầu trang — trái"),
    ("top-center", "Đầu trang — giữa"),
    ("top-right", "Đầu trang — phải"),
    ("bottom-left", "Chân trang — trái"),
    ("bottom-center", "Chân trang — giữa"),
    ("bottom-right", "Chân trang — phải"),
]
_POSITION_ALIASES = {
    "tren-trai": "top-left", "tren-giua": "top-center", "tren-phai": "top-right",
    "duoi-trai": "bottom-left", "duoi-giua": "bottom-center", "duoi-phai": "bottom-right",
    "dau-trai": "top-left", "dau-giua": "top-center", "dau-phai": "top-right",
    "chan-trai": "bottom-left", "chan-giua": "bottom-center", "chan-phai": "bottom-right",
    "top": "top-center", "bottom": "bottom-center",
}

NUMBER_FORMATS: List[Tuple[str, str]] = [
    ("{n}", "1"),
    ("Trang {n}", "Trang 1"),
    ("{n} / {total}", "1 / 10"),
    ("Trang {n} / {total}", "Trang 1 / 10"),
    ("- {n} -", "- 1 -"),
]

WATERMARK_LAYOUTS: List[Tuple[str, str]] = [("center", "Giữa trang"), ("tile", "Lát gạch kín trang")]

WATERMARK_SUFFIX = "_dau_nuoc"
NUMBER_SUFFIX = "_danh_so"

_BUILTIN_FONTS = {("sans", False): "helv", ("sans", True): "hebo", ("serif", False): "tiro",
                  ("serif", True): "tibo", ("mono", False): "cour", ("mono", True): "cobo"}
_PAD_X = 0.15  # lề trong của trang tạm theo cỡ chữ: chừa chỗ cho nét nghiêng / đậm tràn
_PAD_Y = 0.32  # … và dấu chồng của chữ hoa tiếng Việt («Ẫ», «Ỗ») cao hơn ascender của phông
_REF_RE = re.compile(r"(\d+) 0 R")


@dataclass
class WatermarkOptions:
    """Tuỳ chọn dấu nước chữ."""

    text: str = "BẢN SAO"
    font_size: float = 56.0
    opacity: float = 0.2  # 0.02–1
    angle: float = 45.0  # độ, ngược chiều kim đồng hồ như người đọc nhìn thấy
    color: str = "#DC2626"
    font_family: str = "sans"  # "sans" (Arial) | "serif" (Times New Roman)
    bold: bool = True
    layout: str = "center"  # "center" | "tile"
    pages: str = ""  # chuỗi chọn trang ('1-3,5', 'le', …); "" = tất cả
    behind: bool = False  # nằm dưới nội dung trang (ảnh quét nền trắng sẽ che mất)


@dataclass
class PageNumberOptions:
    """Tuỳ chọn đánh số trang."""

    template: str = "{n}"  # {n} = số trang, {total} = tổng số
    position: str = "bottom-center"
    start: int = 1  # số của trang đầu tiên trong phạm vi
    skip_first: bool = False  # không in số lên trang đầu (vẫn tính số)
    font_size: float = 12.0
    font_family: str = "serif"
    bold: bool = False
    color: str = "#000000"
    margin_mm: float = 10.0  # khoảng cách mép trên / dưới trang tới chữ
    side_margin_mm: float = 20.0  # khoảng cách mép trái / phải (vị trí trái / phải)
    pages: str = ""  # phạm vi trang được đánh số; "" = tất cả


# Mẫu «Chuẩn NĐ30» (Nghị định 30/2020/NĐ-CP): số Ả Rập, giữa lề trên, Times New Roman 13, không hiện trang 1
ND30_PAGE_NUMBERS = PageNumberOptions(
    template="{n}", position="top-center", start=1, skip_first=True, font_size=13.0, font_family="serif",
    bold=False, color="#000000", margin_mm=10.0,
)


def nd30_page_number_options() -> PageNumberOptions:
    return replace(ND30_PAGE_NUMBERS)


def normalize_position(position: str) -> str:
    key = (position or "bottom-center").strip().lower().replace("_", "-").replace(" ", "-")
    key = _POSITION_ALIASES.get(key, key)
    if key not in dict(POSITIONS):
        raise PdfToolError(
            f"Vị trí số trang không hợp lệ: «{position}» (chọn {', '.join(k for k, _ in POSITIONS)})."
        )
    return key


def format_page_label(template: str, n: int, total: int) -> str:
    """`'Trang {n} / {total}'` → `'Trang 3 / 10'` (nhận cả `{trang}` / `{tong}`)."""
    text = template.replace("{trang}", "{n}").replace("{tong}", "{total}")
    return _nfc(text.replace("{n}", str(n)).replace("{total}", str(total)))


# ─── Trang tạm chứa chữ (nguồn cho show_pdf_page) ─────────────────────────


@dataclass
class _Label:
    pno: int
    width: float  # khung chữ (không gồm lề trong)
    height: float
    pad_x: float
    pad_y: float


class _TextStamps:
    """Tài liệu tạm: mỗi nhãn một trang vừa khít chữ, mọi trang dùng chung một phông Windows."""

    def __init__(self, family: str, bold: bool, size: float, color: str, opacity: float = 1.0) -> None:
        family = family if family in _FONT_FILES else "sans"
        self.font = _measure_font(family, bold)
        self.fontfile: Optional[str] = None
        self.fontname = _BUILTIN_FONTS[(family, bold)]
        d = system_font_dir()
        fname = _FONT_FILES[family]["b" if bold else ""]
        if d is not None and (d / fname).exists():
            self.fontfile = str(d / fname)
            self.fontname = "QTVN" + family.capitalize() + ("B" if bold else "")
        self.size = float(size)
        self.rgb = parse_color(color, "#000000")
        self.opacity = max(0.02, min(1.0, float(opacity)))
        self.doc = fitz.open()
        self._cache: dict = {}

    def add(self, text: str) -> _Label:
        if text in self._cache:
            return self._cache[text]
        fs = self.size
        lines = _nfc(text).replace("\r", "").split("\n")
        widths = [self.font.text_length(line, fontsize=fs) for line in lines]
        asc, desc = self.font.ascender, self.font.descender
        step = fs * 1.2
        width = max(widths + [fs * 0.5])
        height = (asc - desc) * fs + step * (len(lines) - 1)
        pad_x, pad_y = fs * _PAD_X, fs * _PAD_Y
        page = self.doc.new_page(width=width + 2 * pad_x, height=height + 2 * pad_y)
        for i, (line, lw) in enumerate(zip(lines, widths)):
            if not line.strip():
                continue
            page.insert_text(
                (pad_x + (width - lw) / 2.0, pad_y + asc * fs + i * step), line,
                fontsize=fs, fontname=self.fontname, fontfile=self.fontfile, color=self.rgb,
                fill_opacity=self.opacity,
            )
        label = _Label(page.number, width, height, pad_x, pad_y)
        self._cache[text] = label
        return label

    def finish(self) -> None:
        """Nhúng tập con phông, thu gọn `/W` & `ToUnicode` (gọi sau khi thêm hết nhãn)."""
        try:
            self.doc.subset_fonts()
        except Exception:
            pass  # không nhúng tập con được thì giữ phông đầy đủ
        if self.fontfile:
            self._shrink_font_tables()

    def _shrink_font_tables(self) -> None:
        shrink_font_tables(self.doc, self.font, "".join(self._cache))

    def place(self, page: fitz.Page, label: _Label, center: fitz.Point, angle: float = 0.0,
              behind: bool = False) -> None:
        """Đặt nhãn sao cho tâm khung chữ ở `center` (toạ độ trang đang hiển thị), xoay `angle` độ."""
        w = label.width + 2 * label.pad_x
        h = label.height + 2 * label.pad_y
        t = math.radians(angle)
        bw = abs(w * math.cos(t)) + abs(h * math.sin(t))
        bh = abs(w * math.sin(t)) + abs(h * math.cos(t))
        disp = fitz.Rect(center.x - bw / 2, center.y - bh / 2, center.x + bw / 2, center.y + bh / 2)
        page.show_pdf_page(
            disp * page.derotation_matrix, self.doc, label.pno,
            overlay=not behind, rotate=angle + page.rotation,
        )

    def close(self) -> None:
        if not self.doc.is_closed:
            self.doc.close()


def shrink_font_tables(doc: fitz.Document, font: fitz.Font, used_text: str) -> None:
    """Viết lại `/W` và `ToUnicode` của MỌI phông Type0 trong `doc` (tài liệu tạm chỉ có một phông Windows nhúng
    qua `insert_text`) chỉ gồm các ký tự của `used_text`; dấu cách chép ra U+0020 thay vì U+00A0."""
    glyphs: dict = {}  # gid → (mã Unicode, độ rộng /1000 em); dấu cách (32) đứng trước U+00A0
    for ch in sorted(set(used_text)):
        gid = font.has_glyph(ord(ch))
        if gid and gid not in glyphs and ord(ch) <= 0xFFFF:
            glyphs[gid] = (ord(ch), round(font.glyph_advance(ord(ch)) * 1000))
    if not glyphs:
        return
    items = sorted(glyphs.items())
    widths = "[" + " ".join(f"{g}[{w}]" for g, (_u, w) in items) + "]"
    blocks = []
    for i in range(0, len(items), 100):  # mỗi khối bfchar tối đa 100 mục
        chunk = items[i:i + 100]
        body = "\n".join(f"<{g:04X}> <{u:04X}>" for g, (u, _w) in chunk)
        blocks.append(f"{len(chunk)} beginbfchar\n{body}\nendbfchar")
    cmap = (
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        "/CIDSystemInfo <</Registry(Adobe)/Ordering(UCS)/Supplement 0>> def\n"
        "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        + "\n".join(blocks)
        + "\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    ).encode("ascii")
    for xref in range(1, doc.xref_length()):
        if doc.xref_get_key(xref, "Subtype") != ("name", "/Type0"):
            continue
        kind, tu = doc.xref_get_key(xref, "ToUnicode")
        if kind == "xref":
            doc.update_stream(int(tu.split()[0]), cmap)
        kind, desc = doc.xref_get_key(xref, "DescendantFonts")
        ref = _REF_RE.search(desc) if kind in ("array", "xref") else None
        if ref:
            doc.xref_set_key(int(ref.group(1)), "W", widths)


# ─── Dấu nước ─────────────────────────────────────────────────────────────


def _validate_watermark(opts: WatermarkOptions) -> None:
    if not _nfc(opts.text).strip():
        raise PdfToolError("Hãy nhập nội dung dấu nước.")
    if not 4 <= float(opts.font_size) <= 400:
        raise PdfToolError("Cỡ chữ dấu nước phải từ 4 đến 400 pt.")
    if opts.layout not in dict(WATERMARK_LAYOUTS):
        raise PdfToolError(f"Kiểu đặt dấu nước không hợp lệ: «{opts.layout}» (center / tile).")


def _tile_centers(rect: fitz.Rect, bw: float, bh: float, gap: float) -> List[fitz.Point]:
    """Tâm các ô lát gạch (so le từng hàng) phủ kín trang, đối xứng quanh tâm trang."""
    sx, sy = bw + gap, bh + gap
    cx, cy = rect.width / 2.0, rect.height / 2.0
    nx = int(rect.width / (2 * sx)) + 2
    ny = int(rect.height / (2 * sy)) + 2
    pts = []
    for j in range(-ny, ny + 1):
        shift = sx / 2.0 if j % 2 else 0.0
        for i in range(-nx, nx + 1):
            x, y = cx + i * sx + shift, cy + j * sy
            if -bw / 2 < x < rect.width + bw / 2 and -bh / 2 < y < rect.height + bh / 2:
                pts.append(fitz.Point(x, y))
    return pts


def apply_watermark(doc: fitz.Document, opts: WatermarkOptions) -> int:
    """Đóng dấu nước lên tài liệu đang mở (thay đổi `doc`) → số trang đã đóng dấu."""
    _validate_watermark(opts)
    targets = parse_page_selection(opts.pages, doc.page_count)
    stamps = _TextStamps(opts.font_family, opts.bold, opts.font_size, opts.color, opts.opacity)
    try:
        label = stamps.add(opts.text.strip("\n"))
        stamps.finish()
        w = label.width + 2 * label.pad_x
        h = label.height + 2 * label.pad_y
        t = math.radians(opts.angle)
        bw = abs(w * math.cos(t)) + abs(h * math.sin(t))
        bh = abs(w * math.sin(t)) + abs(h * math.cos(t))
        gap = max(24.0, opts.font_size * 1.2)
        for pno in targets:
            page = doc[pno]
            rect = page.rect
            if opts.layout == "tile":
                centers = _tile_centers(rect, bw, bh, gap)
            else:
                centers = [fitz.Point(rect.width / 2.0, rect.height / 2.0)]
            for c in centers:
                stamps.place(page, label, c, opts.angle, opts.behind)
    finally:
        stamps.close()
    return len(targets)


def watermark_pdf(
    src: PathLike,
    output: Optional[PathLike] = None,
    options: Optional[WatermarkOptions] = None,
    password: Optional[str] = None,
    allow_signed: bool = False,
) -> ToolResult:
    """Đóng dấu nước chữ lên `src` → `output` (mặc định `<tên>_dau_nuoc.pdf`)."""
    opts = options or WatermarkOptions()
    _validate_watermark(opts)
    return _run_on_file("watermark", src, output, WATERMARK_SUFFIX, password, allow_signed,
                        lambda doc: apply_watermark(doc, opts))


# ─── Đánh số trang ────────────────────────────────────────────────────────


def _validate_numbers(opts: PageNumberOptions) -> str:
    position = normalize_position(opts.position)
    if "{n}" not in opts.template.replace("{trang}", "{n}"):
        raise PdfToolError("Mẫu số trang phải có {n} (vd «Trang {n}», «{n} / {total}»).")
    if not 4 <= float(opts.font_size) <= 72:
        raise PdfToolError("Cỡ chữ số trang phải từ 4 đến 72 pt.")
    if int(opts.start) < 0:
        raise PdfToolError("Số bắt đầu phải ≥ 0.")
    if not 0 <= float(opts.margin_mm) <= 100 or not 0 <= float(opts.side_margin_mm) <= 100:
        raise PdfToolError("Lề phải từ 0 đến 100 mm.")
    return position


def _number_center(rect: fitz.Rect, label: _Label, position: str, margin: float, side: float) -> fitz.Point:
    vert, horiz = position.split("-")
    y = margin + label.height / 2.0 if vert == "top" else rect.height - margin - label.height / 2.0
    if horiz == "left":
        x = side + label.width / 2.0
    elif horiz == "right":
        x = rect.width - side - label.width / 2.0
    else:
        x = rect.width / 2.0
    return fitz.Point(x, y)


def apply_page_numbers(doc: fitz.Document, opts: PageNumberOptions) -> int:
    """Đánh số trang lên tài liệu đang mở (thay đổi `doc`) → số trang đã in số."""
    position = _validate_numbers(opts)
    targets = sorted(parse_page_selection(opts.pages, doc.page_count))
    if not targets:
        return 0
    start = int(opts.start)
    total = start + len(targets) - 1
    stamps = _TextStamps(opts.font_family, opts.bold, opts.font_size, opts.color)
    try:
        jobs = []
        for k, pno in enumerate(targets):
            if k == 0 and opts.skip_first:
                continue
            jobs.append((pno, stamps.add(format_page_label(opts.template, start + k, total))))
        stamps.finish()
        margin, side = float(opts.margin_mm) * MM, float(opts.side_margin_mm) * MM
        for pno, label in jobs:
            page = doc[pno]
            stamps.place(page, label, _number_center(page.rect, label, position, margin, side))
    finally:
        stamps.close()
    return len(jobs)


def number_pages(
    src: PathLike,
    output: Optional[PathLike] = None,
    options: Optional[PageNumberOptions] = None,
    password: Optional[str] = None,
    allow_signed: bool = False,
) -> ToolResult:
    """Đánh số trang `src` → `output` (mặc định `<tên>_danh_so.pdf`)."""
    opts = options or PageNumberOptions()
    _validate_numbers(opts)
    return _run_on_file("number", src, output, NUMBER_SUFFIX, password, allow_signed,
                        lambda doc: apply_page_numbers(doc, opts))


# ─── Chạy trên tệp ────────────────────────────────────────────────────────


def _run_on_file(tool: str, src: PathLike, output: Optional[PathLike], suffix: str, password: Optional[str],
                 allow_signed: bool, apply) -> ToolResult:
    src_path = Path(src).resolve()
    out = resolve_output(src_path, output, suffix)
    doc = open_pdf(src_path, password, need=fitz.PDF_PERM_MODIFY).doc
    try:
        check_signature(doc, allow_signed)
        changed = apply(doc)
        protected = is_protected(doc)
        saved = save_pdf(doc, out, encryption=fitz.PDF_ENCRYPT_KEEP)
        pages = doc.page_count
    finally:
        doc.close()
    return ToolResult(
        tool, str(src_path), str(saved), True, pages, src_path.stat().st_size, saved.stat().st_size,
        pages_changed=changed, encrypted=protected,
    )
