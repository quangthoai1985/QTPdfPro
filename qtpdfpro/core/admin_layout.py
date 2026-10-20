"""Phân tích bố cục văn bản hành chính Việt Nam từ PDF (phục vụ engine chuẩn NĐ30).

Khác với `layout_analyzer.py` (chỉ đếm thành phần để soi bố cục), module này dựng lại
**cấu trúc ngữ nghĩa** của văn bản để tái tạo DOCX đúng thể thức Nghị định 30/2020/NĐ-CP:

1. Trích từng **dòng chữ trực quan** (`TextLine`) kèm đường cơ sở (baseline), mép phải tính theo
   ký tự thật cuối dòng (bỏ khoảng trắng thừa của dòng căn đều), các đoạn định dạng (`TextRun`).
2. Trích **đường kẻ ngang** (`RuleLine`) — gồm cả nét `l` lẫn hình chữ nhật mảnh `re` mà
   Microsoft Word xuất ra khi vẽ đường kẻ dưới Quốc hiệu / tên cơ quan.
3. Trích **ảnh** (con dấu, chữ ký số từ widget; ảnh nhúng) và **bảng có viền** (`find_tables`).
4. Nhận diện vùng **tiêu đề 2 cột** (Tên cơ quan | Quốc hiệu – Tiêu ngữ; Số | Địa danh, ngày)
   và **khối ký** (Nơi nhận | Quyền hạn, chức vụ, họ tên) để dựng thành bảng không viền.
5. Gom dòng thành **đoạn văn** và **đo** lề trang, cỡ chữ, khoảng cách dòng, khoảng cách đoạn,
   thụt đầu dòng — đầu vào cho bộ đối chiếu `nd30_standard.py` và bộ dựng `nd30_engine.py`.
"""

from __future__ import annotations

import contextlib
import io as _io
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import fitz  # PyMuPDF

from qtpdfpro.core.font_resolver import normalize_vietnamese_text, resolve_pdf_font
from qtpdfpro.core.pdf_primitives import extract_widget_overlays, splice_overlapping_stamped_text

PT_PER_MM = 72.0 / 25.4

# Hệ số chiều cao dòng đơn (single) của Word theo phông = (winAscent + winDescent + lineGap) / em,
# và hệ số phần chân chữ (descent). Word đặt khoảng giãn dòng thêm (1,5 lines...) ở PHÍA DƯỚI dòng.
_FONT_LINE_METRICS: dict[str, tuple[float, float]] = {
    "Times New Roman": (1.149, 0.216),
    "Arial": (1.149, 0.212),
    "Calibri": (1.221, 0.25),
    "Cambria": (1.172, 0.222),
    "Tahoma": (1.207, 0.207),
    "Verdana": (1.215, 0.21),
    "Segoe UI": (1.33, 0.25),
}

_QUOC_HIEU_RE = re.compile(r"C[ỘO]NG\s+H(?:[ÒÓO]A|O[ÀÁA])\s+X[ÃA]\s+H[ỘO]I\s+CH[ỦU]\s+NGH[ĨI]A\s+VI[ỆE]T\s+NAM", re.I)
_TIEU_NGU_RE = re.compile(r"Đ[ộo]c\s+l[ậa]p\s*[-–]\s*T[ựu]\s+do\s*[-–]\s*H[ạa]nh\s+ph[úu]c", re.I)
_SO_KY_HIEU_RE = re.compile(r"^\s*S[ốo]\s*[:.]", re.I)
_NGAY_THANG_RE = re.compile(r"ng[àa]y\s+\S+\s+th[áa]ng\s+\S+\s+n[ăa]m", re.I)
_NOI_NHAN_RE = re.compile(r"^\s*N[ơo]i\s+nh[ậa]n\s*:?", re.I)
_PAGE_NUMBER_RE = re.compile(r"^[\s\-–—]*\d{1,3}[\s\-–—]*$")
_BULLET_START_RE = re.compile(r"^\s*[-–•+*]\s")


# Bội số giãn dòng chuẩn trong hộp thoại Paragraph của Word
STANDARD_MULTIPLES = (1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.4, 1.5, 2.0)
# Word đặt baseline ở 0,8 × chiều cao dòng khi giãn dòng "Exactly" (đo thực nghiệm 0,796–0,802)
EXACT_BASELINE_RATIO = 0.8


def resolve_line_spacing(
    pitch: float,
    size: float,
    line_factor: float,
    policy: str = "faithful",
    is_body: bool = True,
    tol: float = 0.04,
) -> tuple[str, float]:
    """Chọn cách ghi giãn dòng tái tạo đúng khoảng cách baseline đo được.

    Trả về `("auto", bội số)` nếu bội số chuẩn của Word (1,0 / 1,15 / 1,5...) cho ra đúng khoảng
    cách dòng (sai lệch ≤ `tol` pt/dòng — không cộng dồn lệch trang); ngược lại `("exact", pt)`
    như người soạn đặt "Exactly 18 pt". Chính sách `nd30` cho phép bắt rộng hơn (2,5%) và kẹp
    phần nội dung vào 1,0–1,5 lines.
    """
    single = line_factor * size
    if single <= 0:
        return "auto", 1.0
    multiple = pitch / single
    best = min(STANDARD_MULTIPLES, key=lambda m: abs(m * single - pitch))
    if abs(best * single - pitch) <= tol:
        return "auto", best
    if policy == "nd30":
        m = best if abs(best - multiple) <= 0.025 * best else round(multiple, 2)
        if is_body:
            m = min(max(m, 1.0), 1.5)
        return "auto", m
    if pitch < single - 0.05:
        return "exact", round(pitch * 20) / 20
    exact = round(pitch * 2) / 2
    if abs(exact - pitch) > max(0.04, tol):
        exact = round(pitch * 20) / 20  # Word lưu theo 1/20 pt
    return "exact", exact


def font_line_metrics(family: str) -> tuple[float, float]:
    """Trả về (hệ số chiều cao dòng đơn, hệ số descent) của phông trong Microsoft Word."""
    return _FONT_LINE_METRICS.get(family, (1.15, 0.216))


# ─── Thành phần cơ bản ─────────────────────────────────────────────────────


@dataclass
class TextRun:
    """Một đoạn chữ cùng định dạng trong dòng."""

    text: str
    font: str = "Times New Roman"
    size: float = 14.0
    bold: bool = False
    italic: bool = False
    color: int = 0  # sRGB 0xRRGGBB


@dataclass
class TextLine:
    """Một dòng chữ trực quan trên trang PDF."""

    page: int
    x0: float
    y0: float
    x1: float  # mép phải của ký tự thật cuối cùng (không tính khoảng trắng)
    y1: float
    baseline: float
    size: float
    runs: List[TextRun] = field(default_factory=list)
    first_word_w: float = 0.0
    role: str = ""  # "" | "page_number"

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)

    @property
    def center(self) -> float:
        return 0.5 * (self.x0 + self.x1)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def font(self) -> str:
        weights: Counter[str] = Counter()
        for r in self.runs:
            weights[r.font] += len(r.text.strip()) or 1
        return weights.most_common(1)[0][0] if weights else "Times New Roman"

    def _ratio(self, attr: str) -> float:
        total = sum(len(r.text.strip()) for r in self.runs)
        if total == 0:
            return 0.0
        return sum(len(r.text.strip()) for r in self.runs if getattr(r, attr)) / total

    @property
    def is_bold(self) -> bool:
        return self._ratio("bold") >= 0.8

    @property
    def is_italic(self) -> bool:
        return self._ratio("italic") >= 0.8

    @property
    def is_upper(self) -> bool:
        letters = [c for c in self.text if c.isalpha()]
        return bool(letters) and sum(c.isupper() for c in letters) / len(letters) >= 0.9

    def style_key(self) -> tuple:
        return (round(self.size * 2) / 2, self.is_bold, self.is_italic)

    def box_top(self) -> float:
        """Đỉnh hộp dòng theo mô hình Word (baseline − (single − descent) × cỡ chữ)."""
        lh, desc = font_line_metrics(self.font)
        return self.baseline - (lh - desc) * self.size


@dataclass
class RuleLine:
    """Đường kẻ ngang độc lập (dưới tên cơ quan, Tiêu ngữ, trích yếu...)."""

    page: int
    x0: float
    x1: float
    y: float
    thickness: float = 0.6
    color: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def center(self) -> float:
        return 0.5 * (self.x0 + self.x1)


@dataclass
class ImageItem:
    """Ảnh trên trang: con dấu / chữ ký số (widget) hoặc ảnh nhúng."""

    page: int
    bbox: Tuple[float, float, float, float]
    png: bytes
    is_widget: bool = False


@dataclass
class TableCellModel:
    bbox: Tuple[float, float, float, float]
    lines: List[TextLine] = field(default_factory=list)


@dataclass
class TableModel:
    """Bảng có đường viền phát hiện bằng `page.find_tables()`."""

    page: int
    bbox: Tuple[float, float, float, float]
    rows: List[List[Optional[TableCellModel]]] = field(default_factory=list)
    col_edges: List[float] = field(default_factory=list)


@dataclass
class PageModel:
    index: int
    width: float
    height: float
    lines: List[TextLine] = field(default_factory=list)
    rules: List[RuleLine] = field(default_factory=list)
    images: List[ImageItem] = field(default_factory=list)
    tables: List[TableModel] = field(default_factory=list)


# ─── Khối bố cục sau khi phân tích ──────────────────────────────────────────


@dataclass
class ParaBlock:
    """Đoạn văn đã gom dòng, kèm hình học trong vùng [left, right]."""

    page: int
    lines: List[TextLine]
    align: str = "left"  # "left" | "center" | "right" | "both"
    ind_left: float = 0.0
    ind_right: float = 0.0
    first_line: float = 0.0
    pitch: float = 0.0  # khoảng cách baseline giữa các dòng (pt)
    joiner: str = "space"  # "space" (nối dòng tự chảy) | "break" (giữ ngắt dòng)
    before: float = 0.0  # khoảng cách trước đoạn (pt)
    role: str = "body"  # "body" | "title" | "header" | "sign" | "cell"
    line_rule: str = "auto"  # "auto" (bội số) | "exact" (Exactly)
    line_value: float = 1.0  # bội số hoặc pt

    @property
    def end_page(self) -> int:
        """Trang chứa dòng cuối (đoạn có thể tràn sang trang sau)."""
        return self.lines[-1].page if self.lines else self.page

    @property
    def size(self) -> float:
        sizes = Counter(round(l.size * 2) / 2 for l in self.lines)
        return sizes.most_common(1)[0][0] if sizes else 14.0

    @property
    def font(self) -> str:
        return self.lines[0].font if self.lines else "Times New Roman"

    def line_height(self) -> float:
        """Chiều cao một dòng mà Word sẽ dựng theo giãn dòng đã chọn."""
        if self.line_rule == "exact":
            return self.line_value
        return self.line_value * font_line_metrics(self.font)[0] * self.size

    def _baseline_offset(self, line: TextLine) -> float:
        if self.line_rule == "exact":
            return EXACT_BASELINE_RATIO * self.line_value
        lh, desc = font_line_metrics(line.font)
        return (lh - desc) * line.size

    @property
    def top(self) -> float:
        return self.lines[0].baseline - self._baseline_offset(self.lines[0])

    @property
    def bottom(self) -> float:
        last = self.lines[-1]
        return last.baseline - self._baseline_offset(last) + self.line_height()

    def resolve_spacing(self, doc_pitch: Optional[float] = None) -> None:
        """Quy khoảng cách baseline đo được về giãn dòng Word (bội số chuẩn hoặc Exactly)."""
        lh = font_line_metrics(self.font)[0]
        n_gaps = max(0, len(self.lines) - 1)
        pitch = self.pitch or lh * self.size
        if doc_pitch and abs(pitch - doc_pitch) <= 0.35:
            pitch, tol = doc_pitch, 0.04  # cùng kiểu đoạn với phần thân → dùng giá trị đo toàn văn bản
        else:
            tol = 0.04 if n_gaps >= 8 else (0.15 if n_gaps >= 2 else 0.25)
        self.pitch = pitch
        self.line_rule, self.line_value = resolve_line_spacing(pitch, self.size, lh, tol=tol)

    @property
    def text(self) -> str:
        sep = " " if self.joiner == "space" else "\n"
        return sep.join(l.text.strip() for l in self.lines)


@dataclass
class RuleBlock:
    page: int
    rule: RuleLine
    before: float = 0.0
    height: float = 2.0  # chiều cao đoạn mang đường viền dưới (pt)

    @property
    def top(self) -> float:
        return self.rule.y - self.height

    @property
    def bottom(self) -> float:
        return self.rule.y + 0.5 * self.rule.thickness


CellItem = Union[ParaBlock, RuleBlock]


@dataclass
class TwoColBlock:
    """Khối 2 cột trình bày bằng bảng không viền (tiêu đề hoặc khối ký)."""

    kind: str  # "header" | "sign"
    page: int
    x_start: float
    x_mid: float
    x_end: float
    rows: List[Tuple[List[CellItem], List[CellItem]]] = field(default_factory=list)
    before: float = 0.0
    top: float = 0.0
    bottom: float = 0.0


@dataclass
class TableBlock:
    page: int
    table: TableModel
    before: float = 0.0

    @property
    def top(self) -> float:
        return self.table.bbox[1]

    @property
    def bottom(self) -> float:
        return self.table.bbox[3]


@dataclass
class ImageBlock:
    page: int
    image: ImageItem
    inline: bool = False
    before: float = 0.0

    @property
    def top(self) -> float:
        return self.image.bbox[1]

    @property
    def bottom(self) -> float:
        return self.image.bbox[3]


Block = Union[ParaBlock, RuleBlock, TwoColBlock, TableBlock, ImageBlock]


@dataclass
class MeasuredLayout:
    """Các thông số đo được trên PDF (đơn vị gốc: pt; lề quy ra mm)."""

    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    margin_top_mm: float = 0.0
    margin_left_mm: float = 0.0
    margin_right_mm: float = 0.0
    margin_bottom_lo_mm: Optional[float] = None  # cận dưới ước lượng
    margin_bottom_hi_mm: Optional[float] = None  # cận trên ước lượng
    body_font: str = "Times New Roman"
    body_size: float = 14.0
    body_align: str = "both"
    line_pitch_pt: float = 0.0
    line_multiple: float = 1.0
    para_spacing_pt: Optional[float] = None
    first_indent_mm: Optional[float] = None
    font_share: float = 1.0  # tỷ lệ ký tự dùng phông chủ đạo
    header_distance_pt: Optional[float] = None
    page_number_pages: List[int] = field(default_factory=list)


@dataclass
class AdminDocument:
    """Kết quả phân tích toàn văn bản."""

    pages: List[PageModel]
    text_left: float
    text_right: float
    measured: MeasuredLayout
    blocks: List[Block] = field(default_factory=list)
    header: Optional[TwoColBlock] = None
    sign: Optional[TwoColBlock] = None
    floating_images: List[ImageItem] = field(default_factory=list)
    is_admin: bool = False
    is_scanned: bool = False


# ─── 1. Trích xuất nguyên liệu từ trang ─────────────────────────────────────


def _span_runs_and_chars(line: dict) -> tuple[list[TextRun], list[tuple[str, tuple, float, float]]]:
    runs: list[TextRun] = []
    chars: list[tuple[str, tuple, float, float]] = []
    for sp in line.get("spans", []):
        raw_font = sp.get("font", "")
        flags = int(sp.get("flags", 0))
        size = float(sp.get("size", 0.0))
        sp_chars = sp.get("chars", [])
        txt = "".join(c.get("c", "") for c in sp_chars)
        if not txt:
            continue
        resolved = resolve_pdf_font(raw_font, flags=flags)
        txt = normalize_vietnamese_text(txt, raw_font)
        runs.append(
            TextRun(
                text=txt,
                font=resolved.family,
                size=size,
                bold=resolved.is_bold,
                italic=resolved.is_italic,
                color=int(sp.get("color", 0) or 0),
            )
        )
        for c in sp_chars:
            origin = c.get("origin") or (c["bbox"][0], c["bbox"][3])
            chars.append((c.get("c", ""), tuple(c["bbox"]), float(origin[1]), size))
    return runs, chars


def _merge_runs(runs: list[TextRun]) -> list[TextRun]:
    out: list[TextRun] = []
    for r in runs:
        if (
            out
            and out[-1].font == r.font
            and abs(out[-1].size - r.size) < 0.25
            and out[-1].bold == r.bold
            and out[-1].italic == r.italic
            and out[-1].color == r.color
        ):
            out[-1].text += r.text
        else:
            out.append(TextRun(r.text, r.font, r.size, r.bold, r.italic, r.color))
    return out


def extract_text_lines(page: fitz.Page) -> list[TextLine]:
    """Trích các dòng chữ trực quan (đã ghép số đóng dấu đè, gộp mảnh cùng dòng)."""
    raw = page.get_text("rawdict", flags=fitz.TEXTFLAGS_TEXT)
    blocks = [b for b in raw.get("blocks", []) if b.get("type", 0) == 0]
    try:
        blocks = splice_overlapping_stamped_text(blocks)
    except Exception:
        pass

    pieces: list[TextLine] = []
    for blk in blocks:
        for ln in blk.get("lines", []):
            direction = ln.get("dir", (1.0, 0.0))
            if abs(direction[0]) < 0.95:
                continue  # bỏ chữ xoay dọc (lề, dấu giáp lai...)
            runs, chars = _span_runs_and_chars(ln)
            visible = [c for c in chars if c[0].strip()]
            if not visible:
                continue
            sizes = Counter(round(c[3] * 2) / 2 for c in visible)
            size = sizes.most_common(1)[0][0]
            if size < 2.0:
                continue
            x0 = min(c[1][0] for c in visible)
            x1 = max(c[1][2] for c in visible)
            baseline = statistics.median(c[2] for c in visible if abs(c[3] - size) < 1.0) if any(
                abs(c[3] - size) < 1.0 for c in visible
            ) else statistics.median(c[2] for c in visible)
            # Độ rộng từ đầu tiên (dùng để biết dòng trước có "kết thúc sớm" hay không)
            first_word_end = x1
            started = False
            for ch, bbox, _o, _s in chars:
                if ch.strip():
                    started = True
                    first_word_end = bbox[2]
                elif started:
                    break
            lb = ln.get("bbox", (x0, baseline - size, x1, baseline + 0.25 * size))
            merged = _merge_runs(runs)
            if merged:
                merged[0].text = merged[0].text.lstrip()
                merged[-1].text = merged[-1].text.rstrip()
                merged = [r for r in merged if r.text]
            if not merged:
                continue
            pieces.append(
                TextLine(
                    page=page.number,
                    x0=float(x0),
                    y0=float(lb[1]),
                    x1=float(x1),
                    y1=float(lb[3]),
                    baseline=float(baseline),
                    size=float(size),
                    runs=merged,
                    first_word_w=float(first_word_end - x0),
                )
            )

    # Gộp các mảnh nằm trên cùng đường cơ sở và sát nhau thành một dòng trực quan
    pieces.sort(key=lambda l: (round(l.baseline / 2.0), l.x0))
    lines: list[TextLine] = []
    for pc in sorted(pieces, key=lambda l: (l.baseline, l.x0)):
        target = None
        for cand in reversed(lines[-6:]):
            tol = 0.3 * max(cand.size, pc.size)
            gap = pc.x0 - cand.x1
            if abs(cand.baseline - pc.baseline) <= tol and -1.5 <= gap <= 1.2 * max(cand.size, pc.size):
                target = cand
                break
        if target is None:
            lines.append(pc)
            continue
        gap = pc.x0 - target.x1
        if gap > 0.15 * target.size and not target.text.endswith(" ") and not pc.text.startswith(" "):
            target.runs[-1].text += " "
        target.runs = _merge_runs(target.runs + pc.runs)
        target.x1 = max(target.x1, pc.x1)
        target.y0 = min(target.y0, pc.y0)
        target.y1 = max(target.y1, pc.y1)
        if pc.size > target.size:
            target.size = pc.size
    lines.sort(key=lambda l: (l.baseline, l.x0))
    return lines


def extract_rules(page: fitz.Page, table_rects: Sequence[fitz.Rect] = ()) -> list[RuleLine]:
    """Trích các đường kẻ ngang độc lập (nét `l` hoặc hình chữ nhật mảnh `re` / `qu`)."""
    try:
        drawings = page.get_drawings() or []
    except Exception:
        return []

    candidates: list[RuleLine] = []
    blockers: list[fitz.Rect] = []
    for d in drawings:
        color = d.get("color") or d.get("fill") or (0.0, 0.0, 0.0)
        if not isinstance(color, (tuple, list)) or len(color) < 3:
            color = (0.0, 0.0, 0.0)
        stroke_w = float(d.get("width") or 0.6)
        for item in d.get("items") or []:
            kind = item[0]
            if kind == "l":
                p0, p1 = item[1], item[2]
                dx, dy = abs(p1.x - p0.x), abs(p1.y - p0.y)
                if dy <= 1.0 and dx >= 12.0:
                    candidates.append(
                        RuleLine(page.number, min(p0.x, p1.x), max(p0.x, p1.x), 0.5 * (p0.y + p1.y), stroke_w, tuple(color[:3]))
                    )
                else:
                    blockers.append(
                        fitz.Rect(min(p0.x, p1.x) - 0.5, min(p0.y, p1.y) - 0.5, max(p0.x, p1.x) + 0.5, max(p0.y, p1.y) + 0.5)
                    )
            elif kind in ("re", "qu"):
                r = fitz.Rect(item[1]) if kind == "re" else item[1].rect
                if r.height <= 2.2 and r.width >= 12.0:
                    candidates.append(
                        RuleLine(page.number, r.x0, r.x1, 0.5 * (r.y0 + r.y1), max(0.25, r.height), tuple(color[:3]))
                    )
                elif r.width <= 2.2 and r.height <= 2.2:
                    continue  # chấm nhỏ
                else:
                    blockers.append(fitz.Rect(r))
            elif kind == "c":
                blockers.append(fitz.Rect(d.get("rect", (0, 0, 0, 0))))

    rules: list[RuleLine] = []
    for rl in candidates:
        probe = fitz.Rect(rl.x0 - 3.0, rl.y - 3.0, rl.x1 + 3.0, rl.y + 3.0)
        if any(probe.intersects(b) for b in blockers):
            continue
        if any(
            fitz.Rect(t.x0 - 2.5, t.y0 - 2.5, t.x1 + 2.5, t.y1 + 2.5).contains(fitz.Point(rl.center, rl.y))
            for t in table_rects
        ):
            continue
        # Gộp các đoạn thẳng hàng nối tiếp nhau
        merged = False
        for ex in rules:
            if abs(ex.y - rl.y) <= 0.8 and rl.x0 <= ex.x1 + 1.5 and rl.x1 >= ex.x0 - 1.5:
                ex.x0 = min(ex.x0, rl.x0)
                ex.x1 = max(ex.x1, rl.x1)
                merged = True
                break
        if not merged:
            rules.append(rl)
    rules.sort(key=lambda r: (r.y, r.x0))
    return rules


def _pixmap_png(doc: fitz.Document, xref: int) -> Optional[bytes]:
    try:
        info = doc.extract_image(xref)
        smask = int(info.get("smask") or 0) if info else 0
        base = fitz.Pixmap(doc, xref)
        if base.alpha:
            base = fitz.Pixmap(base, 0)
        if base.colorspace is None or base.colorspace.n not in (1, 3):
            base = fitz.Pixmap(fitz.csRGB, base)
        if smask:
            mask = fitz.Pixmap(doc, smask)
            if base.colorspace.n == 1:
                base = fitz.Pixmap(fitz.csRGB, base)
            base = fitz.Pixmap(base, mask)
        return base.tobytes("png")
    except Exception:
        return None


def extract_images(page: fitz.Page) -> list[ImageItem]:
    """Trích ảnh nhúng và ảnh con dấu / chữ ký số (widget) của trang."""
    items: list[ImageItem] = []
    doc = page.parent
    try:
        for png, width_pt, pos_x, pos_y, _behind in extract_widget_overlays(page):
            pix = fitz.Pixmap(png)
            height_pt = width_pt * pix.height / max(1, pix.width)
            items.append(ImageItem(page.number, (pos_x, pos_y, pos_x + width_pt, pos_y + height_pt), png, True))
    except Exception:
        pass

    try:
        infos = page.get_image_info(xrefs=True)
    except Exception:
        infos = []
    seen: set[tuple] = set()
    for info in infos:
        bbox = tuple(float(v) for v in info.get("bbox", (0, 0, 0, 0)))
        if bbox[2] - bbox[0] < 4.0 or bbox[3] - bbox[1] < 4.0:
            continue
        key = tuple(round(v) for v in bbox)
        if key in seen:
            continue
        seen.add(key)
        xref = int(info.get("xref") or 0)
        png = _pixmap_png(doc, xref) if (doc is not None and xref > 0) else None
        if png is None:
            try:
                png = page.get_pixmap(clip=fitz.Rect(bbox), dpi=200, alpha=False).tobytes("png")
            except Exception:
                continue
        items.append(ImageItem(page.number, bbox, png, False))  # type: ignore[arg-type]
    return items


def extract_tables(page: fitz.Page, lines: Sequence[TextLine]) -> list[TableModel]:
    """Trích bảng có đường viền và gán dòng chữ vào từng ô."""
    try:
        with contextlib.redirect_stdout(_io.StringIO()):
            finder = page.find_tables()
    except Exception:
        return []

    tables: list[TableModel] = []
    for tbl in finder.tables:
        try:
            bbox = tuple(float(v) for v in tbl.bbox)
            rows_raw = [list(r.cells) for r in tbl.rows]
        except Exception:
            continue
        if not rows_raw or (bbox[2] - bbox[0]) < 20 or (bbox[3] - bbox[1]) < 8:
            continue
        xs: list[float] = []
        for row in rows_raw:
            for c in row:
                if c is not None:
                    xs.extend([float(c[0]), float(c[2])])
        edges: list[float] = []
        for x in sorted(xs):
            if not edges or x - edges[-1] > 2.0:
                edges.append(x)
        model = TableModel(page=page.number, bbox=bbox, col_edges=edges)  # type: ignore[arg-type]
        for row in rows_raw:
            out_row: list[Optional[TableCellModel]] = []
            for c in row:
                if c is None:
                    out_row.append(None)
                    continue
                cb = tuple(float(v) for v in c)
                cell = TableCellModel(bbox=cb)  # type: ignore[arg-type]
                cell.lines = [
                    l for l in lines
                    if cb[0] - 1 <= l.center <= cb[2] + 1 and cb[1] - 1 <= l.baseline - 0.3 * l.size <= cb[3] + 1
                ]
                out_row.append(cell)
            model.rows.append(out_row)
        tables.append(model)
    return tables


def extract_page_model(page: fitz.Page) -> PageModel:
    lines = extract_text_lines(page)
    tables = extract_tables(page, lines)
    table_rects = [fitz.Rect(t.bbox) for t in tables]
    model = PageModel(
        index=page.number,
        width=float(page.rect.width),
        height=float(page.rect.height),
        lines=lines,
        rules=extract_rules(page, table_rects),
        images=extract_images(page),
        tables=tables,
    )
    return model


# ─── 2. Tiện ích hình học ──────────────────────────────────────────────────


def _mode(values: Iterable[float], step: float = 0.5) -> Optional[float]:
    vals = [round(v / step) * step for v in values]
    if not vals:
        return None
    cnt = Counter(vals)
    best, _ = cnt.most_common(1)[0]
    # trung bình có trọng số của nhóm lân cận để giảm sai số làm tròn
    near = [v for v in values if abs(v - best) <= step]
    return statistics.fmean(near) if near else best


def _is_full(line: TextLine, right: float, next_line: Optional[TextLine] = None) -> bool:
    """Dòng có chạm lề phải (hoặc không đủ chỗ cho từ đầu của dòng sau) hay không."""
    free = right - line.x1
    if free <= max(1.2, 0.18 * line.size):
        return True
    if next_line is not None:
        return free < next_line.first_word_w + 0.25 * line.size
    return False


def _is_centered(line: TextLine, left: float, right: float) -> bool:
    mid = 0.5 * (left + right)
    width = right - left
    if line.x0 - left < 0.5 * line.size:
        return False
    if line.x1 >= right - 1.0 and line.x0 <= left + 1.0:
        return False
    return abs(line.center - mid) <= max(3.0, 0.012 * width)


# ─── 3. Phân tích toàn văn bản ─────────────────────────────────────────────


def analyze_admin_document(doc: fitz.Document, pages: Optional[Sequence[int]] = None) -> AdminDocument:
    """Phân tích văn bản (danh sách trang 0-based) và trả về mô hình bố cục ngữ nghĩa."""
    page_ids = list(pages) if pages is not None else list(range(len(doc)))
    models = [extract_page_model(doc[p]) for p in page_ids]
    total_chars = sum(len(l.text) for m in models for l in m.lines)
    is_scanned = total_chars < 20 and any(m.images for m in models)

    pw = models[0].width if models else 595.0

    _mark_page_numbers(models)
    content_lines = [l for m in models for l in m.lines if not l.role]

    # 3.1 Ước lượng lề trái / phải thô
    left, right = _estimate_text_bounds(content_lines, pw)

    # 3.2 Nhận diện vùng tiêu đề 2 cột & khối ký
    header = _detect_header(models[0], left, right) if models else None
    sign = _detect_sign_block(models, left, right)
    is_admin = bool(header) or any(_QUOC_HIEU_RE.search(l.text) for l in (models[0].lines if models else []))

    claimed: set[int] = set()
    claimed_rules: set[int] = set()
    for blk in (header, sign):
        if blk is None:
            continue
        for lcol, rcol in blk.rows:
            for it in lcol + rcol:
                if isinstance(it, ParaBlock):
                    claimed.update(id(l) for l in it.lines)
                else:
                    claimed_rules.add(id(it.rule))

    # 3.3 Dòng thuộc bảng có viền
    table_line_ids: set[int] = set()
    for m in models:
        for t in m.tables:
            for row in t.rows:
                for c in row:
                    if c is not None:
                        table_line_ids.update(id(l) for l in c.lines)

    flow_lines = [
        l for l in content_lines if id(l) not in claimed and id(l) not in table_line_ids
    ]
    pitch_by_size = _line_pitch_by_size(flow_lines)
    first_indent = _estimate_first_indent(flow_lines, left, pitch_by_size)

    # 3.4 Tinh chỉnh lề phải theo các dòng căn đều thực sự
    right = _refine_right_edge(flow_lines, left, right, pitch_by_size)

    # 3.5 Dựng luồng khối (đoạn văn, đường kẻ, bảng, ảnh) theo thứ tự đọc
    blocks: list[Block] = []
    floating: list[ImageItem] = []
    for m in models:
        items: list[tuple[float, float, object]] = []
        for l in m.lines:
            if not l.role and id(l) not in claimed and id(l) not in table_line_ids:
                items.append((l.baseline - 0.7 * l.size, l.x0, l))
        for r in m.rules:
            if id(r) not in claimed_rules:
                items.append((r.y - 1.0, r.x0, RuleBlock(m.index, r)))
        for t in m.tables:
            items.append((t.bbox[1], t.bbox[0], TableBlock(m.index, t)))
        text_on_page = [l for l in m.lines if not l.role]
        for img in m.images:
            if _image_is_inline(img, text_on_page, left, right):
                items.append((img.bbox[1], img.bbox[0], ImageBlock(m.index, img, inline=True)))
            else:
                floating.append(img)
        for blk in (header, sign):
            if blk is not None and blk.page == m.index:
                items.append((blk.top, 0.0, blk))
        items.sort(key=lambda t: (t[0], t[1]))

        pending: list[TextLine] = []
        for _y, _x, obj in items:
            if isinstance(obj, TextLine):
                pending.append(obj)
                continue
            if pending:
                blocks.extend(_build_flow_paragraphs(pending, left, right, pitch_by_size, first_indent))
                pending = []
            blocks.append(obj)  # type: ignore[arg-type]
        if pending:
            blocks.extend(_build_flow_paragraphs(pending, left, right, pitch_by_size, first_indent))

    blocks = _merge_cross_page_paragraphs(blocks, left, right)
    _resolve_all_spacing(blocks, header, sign, pitch_by_size)
    measured = _measure(models, blocks, left, right, pitch_by_size, header, first_indent)
    _normalize_single_line_indents(blocks, measured)
    _assign_flow_spacing(blocks, models, measured, left)

    return AdminDocument(
        pages=models,
        text_left=left,
        text_right=right,
        measured=measured,
        blocks=blocks,
        header=header,
        sign=sign,
        floating_images=floating,
        is_admin=is_admin,
        is_scanned=is_scanned,
    )


def _mark_page_numbers(models: Sequence[PageModel]) -> None:
    """Đánh dấu dòng số trang (chỉ gồm chữ số, nằm sát mép trên/dưới, tách biệt nội dung)."""
    for m in models:
        if not m.lines:
            continue
        ordered = sorted(m.lines, key=lambda l: l.baseline)
        for idx in (0, len(ordered) - 1):
            ln = ordered[idx]
            if not _PAGE_NUMBER_RE.match(ln.text):
                continue
            if abs(ln.center - 0.5 * m.width) > 60.0:
                continue
            neighbor = ordered[1] if idx == 0 and len(ordered) > 1 else (ordered[-2] if len(ordered) > 1 else None)
            in_margin = ln.baseline < 0.12 * m.height or ln.baseline > 0.9 * m.height
            separated = neighbor is None or abs(neighbor.baseline - ln.baseline) > 1.2 * ln.size
            if in_margin and separated:
                ln.role = "page_number"


def _estimate_text_bounds(lines: Sequence[TextLine], page_width: float) -> tuple[float, float]:
    if not lines:
        return 85.0, page_width - 56.7
    x0_counts = Counter(round(l.x0) for l in lines)
    # Lề trái = giá trị x0 phổ biến nhất trong nửa trái trang
    left_cands = [(c, x) for x, c in x0_counts.items() if x < 0.45 * page_width]
    left = float(max(left_cands)[1]) if left_cands else min(l.x0 for l in lines)
    near_left = [l.x0 for l in lines if abs(l.x0 - left) <= 1.5]
    if near_left:
        left = statistics.fmean(near_left)
    wide = sorted(l.x1 for l in lines if l.x1 - left > 0.55 * (page_width - left - 30))
    if wide:
        top_half = wide[len(wide) // 2 :]
        right = statistics.median(top_half)
    else:
        right = max(l.x1 for l in lines)
    return left, right


def _refine_right_edge(lines: Sequence[TextLine], left: float, right: float, pitch_by_size: dict) -> float:
    full = [l.x1 for l in lines if abs(l.x1 - right) <= max(4.0, 0.3 * l.size) and l.x0 <= left + 60]
    if len(full) >= 2:
        return float(statistics.median(full))
    return right


def _line_pitch_by_size(lines: Sequence[TextLine]) -> dict[float, float]:
    gaps: dict[float, list[float]] = {}
    ordered = sorted(lines, key=lambda l: (l.page, l.baseline))
    for a, b in zip(ordered, ordered[1:]):
        if a.page != b.page or abs(a.size - b.size) > 0.3:
            continue
        g = b.baseline - a.baseline
        if 0.95 * a.size <= g <= 2.0 * a.size:
            gaps.setdefault(round(a.size * 2) / 2, []).append(g)
    out: dict[float, float] = {}
    for sz, vals in gaps.items():
        m = _mode(vals, step=0.25)
        if m:
            out[sz] = m
    return out


def _estimate_first_indent(lines: Sequence[TextLine], left: float, pitch_by_size: dict) -> Optional[float]:
    """Thụt đầu dòng chủ đạo: độ lùi phổ biến của dòng mà dòng kế tiếp bắt đầu sát lề trái."""
    offsets: list[float] = []
    ordered = sorted(lines, key=lambda l: (l.page, l.baseline))
    for a, b in zip(ordered, ordered[1:]):
        if a.page != b.page or abs(a.size - b.size) > 0.6:
            continue
        off = a.x0 - left
        if 4.0 <= off <= 80.0 and abs(b.x0 - left) <= 1.5 and b.baseline - a.baseline <= 2.2 * a.size:
            offsets.append(off)
    return _mode(offsets, step=0.5) if len(offsets) >= 2 else None


def _pitch_for(size: float, font: str, pitch_by_size: dict) -> float:
    key = round(size * 2) / 2
    if key in pitch_by_size:
        return pitch_by_size[key]
    return font_line_metrics(font)[0] * size


def _image_is_inline(img: ImageItem, lines: Sequence[TextLine], left: float, right: float) -> bool:
    if img.is_widget:
        return False
    x0, y0, x1, y1 = img.bbox
    if (x1 - x0) < 0.35 * (right - left):
        return False
    for l in lines:
        if l.baseline > y0 + 2 and l.baseline - l.size < y1 - 2:
            return False  # có chữ chạy song song → ảnh nổi
    return True


# ─── 3a. Vùng tiêu đề 2 cột (Quốc hiệu – Tiêu ngữ) ─────────────────────────


def _same_row(a: TextLine, b: TextLine) -> bool:
    return abs(a.baseline - b.baseline) <= 0.5 * max(a.size, b.size)


def _detect_header(page: PageModel, left: float, right: float) -> Optional[TwoColBlock]:
    lines = [l for l in page.lines if not l.role]
    if len(lines) < 3:
        return None
    mid = 0.5 * (left + right)
    anchor_idx = None
    for i, l in enumerate(lines):
        if i == 0:
            continue
        if _QUOC_HIEU_RE.search(l.text) or _TIEU_NGU_RE.search(l.text):
            continue
        if _SO_KY_HIEU_RE.match(l.text) or _NGAY_THANG_RE.search(l.text):
            continue
        others_same_row = [o for o in lines if o is not l and _same_row(o, l)]
        is_body_like = l.x0 <= left + 2.0 and l.x1 >= right - 3.0
        if others_same_row and not is_body_like:
            continue
        crosses_mid = l.x0 < mid - 15.0 and l.x1 > mid + 15.0
        if is_body_like or _is_centered(l, left, right) or crosses_mid:
            anchor_idx = i
            break
    if anchor_idx is None:
        return None
    head = lines[:anchor_idx]
    left_lines = [l for l in head if l.center < mid]
    right_lines = [l for l in head if l.center >= mid]
    has_marker = any(_QUOC_HIEU_RE.search(l.text) or _TIEU_NGU_RE.search(l.text) for l in right_lines)
    if not right_lines or not has_marker:
        return None

    anchor = lines[anchor_idx]
    head_top = min(l.y0 for l in head)
    rules = [r for r in page.rules if head_top - 2 <= r.y <= anchor.box_top() + 2]

    # Chia 2 hàng: hàng 2 bắt đầu tại dòng "Số:" hoặc dòng "…, ngày … tháng … năm …"
    split_candidates = [l.box_top() for l in left_lines if _SO_KY_HIEU_RE.match(l.text)]
    split_candidates += [l.box_top() for l in right_lines if _NGAY_THANG_RE.search(l.text)]
    split_y = min(split_candidates) - 1.0 if split_candidates else None

    def row_of(y: float) -> int:
        return 1 if (split_y is not None and y >= split_y) else 0

    x_start = min([left] + [l.x0 for l in head] + [r.x0 for r in rules])
    x_end = max([right] + [l.x1 for l in head] + [r.x1 for r in rules])
    l_x1 = max((l.x1 for l in left_lines), default=x_start)
    r_x0 = min(l.x0 for l in right_lines)
    x_mid = 0.5 * (l_x1 + r_x0) if left_lines else max(x_start + 1.0, r_x0 - 2.0)

    rows: list[tuple[list[CellItem], list[CellItem]]] = []
    for row in (0, 1) if split_y is not None else (0,):
        cells: list[list[CellItem]] = []
        for col_lines, side in ((left_lines, "L"), (right_lines, "R")):
            items_src: list[tuple[float, object]] = [(l.baseline, l) for l in col_lines if row_of(l.box_top()) == row]
            for r in rules:
                in_side = (r.center < x_mid) if side == "L" else (r.center >= x_mid)
                if in_side and row_of(r.y) == row:
                    items_src.append((r.y, r))
            items_src.sort(key=lambda t: t[0])
            cells.append(_cell_items([o for _, o in items_src], page.index, "header"))
        rows.append((cells[0], cells[1]))
    for side in (0, 1):
        _classify_column_alignment([it for r in rows for it in r[side]], "header")

    blk = TwoColBlock(kind="header", page=page.index, x_start=x_start, x_mid=x_mid, x_end=x_end, rows=rows)
    blk.top = min(l.box_top() for l in head)
    blk.bottom = max([_item_bottom(it) for lc, rc in rows for it in lc + rc] or [blk.top])
    return blk


def _item_bottom(it: CellItem) -> float:
    return it.bottom


def _classify_column_alignment(items: Sequence[CellItem], kind: str) -> None:
    """Xác định căn lề cho các đoạn của một cột (gộp mọi hàng của bảng không viền).

    Các dòng có cùng tâm nhưng khác mép trái → căn giữa; cùng mép trái → căn trái. Khi chỉ có
    1 dòng thì theo quy ước NĐ30: phần đầu văn bản và khối chức vụ / họ tên căn giữa, «Nơi nhận»
    và danh sách nơi nhận căn trái.
    """
    paras = [it for it in items if isinstance(it, ParaBlock)]
    lines = [l for p in paras for l in p.lines]
    if not lines:
        return
    centers = [l.center for l in lines]
    x0s = [l.x0 for l in lines]
    same_center = max(centers) - min(centers) <= 4.0
    same_x0 = max(x0s) - min(x0s) <= 2.0
    for p in paras:
        first_txt = p.lines[0].text
        listy = bool(_NOI_NHAN_RE.match(first_txt) or _BULLET_START_RE.match(first_txt))
        if listy:
            p.align = "left"
        elif len(lines) >= 2 and same_x0 and not same_center:
            p.align = "left"
        elif len(lines) >= 2 and same_center and not same_x0:
            p.align = "center"
        elif len(lines) >= 2 and not same_center and not same_x0:
            # Cột lẫn: dòng nào thẳng tâm với đa số thì căn giữa, còn lại căn trái
            med_c = statistics.median(centers)
            p.align = "center" if all(abs(l.center - med_c) <= 4.0 for l in p.lines) else "left"
        else:
            p.align = "center"


def _cell_items(objs: Sequence[object], page_idx: int, kind: str = "header") -> list[CellItem]:
    """Gom dòng trong một ô thành đoạn (giữ nguyên ngắt dòng) và chèn đường kẻ.

    Căn lề: các dòng có cùng tâm nhưng khác mép trái → căn giữa; cùng mép trái → căn trái.
    Ô chỉ có 1 dòng thì theo quy ước NĐ30: phần đầu văn bản và khối chức vụ / họ tên căn giữa,
    «Nơi nhận» và danh sách nơi nhận căn trái.
    """
    out: list[CellItem] = []
    run: list[TextLine] = []

    def flush() -> None:
        if not run:
            return
        groups: list[list[TextLine]] = [[run[0]]]
        for ln in run[1:]:
            prev = groups[-1][-1]
            same_style = prev.style_key() == ln.style_key() and prev.is_upper == ln.is_upper
            close = ln.baseline - prev.baseline <= 1.45 * max(prev.size, ln.size)
            aligned = abs(prev.center - ln.center) <= 4.0 or abs(prev.x0 - ln.x0) <= 2.0
            starts_item = bool(_BULLET_START_RE.match(ln.text)) or bool(_NOI_NHAN_RE.match(ln.text))
            if same_style and close and aligned and not starts_item:
                groups[-1].append(ln)
            else:
                groups.append([ln])
        for g in groups:
            pitch = (
                statistics.median(b.baseline - a.baseline for a, b in zip(g, g[1:]))
                if len(g) >= 2
                else font_line_metrics(g[0].font)[0] * g[0].size
            )
            out.append(ParaBlock(page=page_idx, lines=g, pitch=pitch, joiner="break", role="cell"))
        run.clear()

    for o in objs:
        if isinstance(o, TextLine):
            run.append(o)
        else:
            flush()
            out.append(RuleBlock(page_idx, o))  # type: ignore[arg-type]
    flush()

    return out


# ─── 3b. Khối ký (Nơi nhận | Chức vụ, họ tên) ──────────────────────────────


def _detect_sign_block(models: Sequence[PageModel], left: float, right: float) -> Optional[TwoColBlock]:
    mid = 0.5 * (left + right)
    target_page: Optional[PageModel] = None
    noi_nhan: Optional[TextLine] = None
    for m in reversed(models):
        for l in m.lines:
            if not l.role and _NOI_NHAN_RE.match(l.text) and l.center < mid:
                target_page, noi_nhan = m, l
                break
        if noi_nhan:
            break

    if target_page is None or noi_nhan is None:
        return _detect_trailing_signature(models, left, right)

    lines = [l for l in target_page.lines if not l.role]
    right_same = [
        l for l in lines if l.center > mid + 0.05 * (right - left) and abs(l.baseline - noi_nhan.baseline) <= 1.6 * l.size
    ]
    top = min([noi_nhan.box_top()] + [l.box_top() for l in right_same])
    region = [l for l in lines if l.box_top() >= top - 1.0]
    return _make_sign_block(target_page, region, left, right, top)


def _detect_trailing_signature(models: Sequence[PageModel], left: float, right: float) -> Optional[TwoColBlock]:
    if not models:
        return None
    page = models[-1]
    lines = sorted([l for l in page.lines if not l.role], key=lambda l: l.baseline)
    if len(lines) < 3:
        return None
    mid = 0.5 * (left + right)
    region: list[TextLine] = []
    for l in reversed(lines):
        in_right = l.x0 > mid - 0.08 * (right - left)
        if in_right:
            region.append(l)
        else:
            break
    if len(region) < 2:
        return None
    region.reverse()
    top = region[0].box_top()
    return _make_sign_block(page, region, left, right, top)


def _make_sign_block(page: PageModel, region: list[TextLine], left: float, right: float, top: float) -> Optional[TwoColBlock]:
    mid = 0.5 * (left + right)
    left_lines = [l for l in region if l.center < mid and l.x1 < mid + 0.15 * (right - left)]
    right_lines = [l for l in region if l not in left_lines]
    if not right_lines:
        return None
    rules = [r for r in page.rules if r.y >= top - 1.0]
    x_start = min([left] + [l.x0 for l in region])
    x_end = max([right] + [l.x1 for l in region])
    l_x1 = max((l.x1 for l in left_lines), default=x_start)
    r_x0 = min(l.x0 for l in right_lines)
    x_mid = 0.5 * (l_x1 + r_x0) if left_lines else max(x_start + 1.0, r_x0 - 2.0)

    cells: list[list[CellItem]] = []
    for col_lines, side in ((left_lines, "L"), (right_lines, "R")):
        src: list[tuple[float, object]] = [(l.baseline, l) for l in col_lines]
        for r in rules:
            if (r.center < x_mid) == (side == "L"):
                src.append((r.y, r))
        src.sort(key=lambda t: t[0])
        cells.append(_cell_items([o for _, o in src], page.index, "sign"))
    for col in cells:
        _classify_column_alignment(col, "sign")

    blk = TwoColBlock(kind="sign", page=page.index, x_start=x_start, x_mid=x_mid, x_end=x_end, rows=[(cells[0], cells[1])])
    blk.top = top
    blk.bottom = max([it.bottom for it in cells[0] + cells[1]] or [top])
    return blk


# ─── 3c. Gom dòng thành đoạn văn trong luồng chính ─────────────────────────


def _starts_new_paragraph(
    prev: TextLine,
    ln: TextLine,
    cur: list[TextLine],
    left: float,
    right: float,
    pitch_by_size: dict,
    first_indent: Optional[float] = None,
) -> bool:
    size = max(prev.size, ln.size)
    if abs(prev.size - ln.size) > 0.6:
        return True
    gap = ln.baseline - prev.baseline
    if gap <= 0.5 * size:
        return True
    ref_pitch = (
        statistics.median(b.baseline - a.baseline for a, b in zip(cur, cur[1:]))
        if len(cur) >= 2
        else _pitch_for(prev.size, prev.font, pitch_by_size)
    )
    if gap > ref_pitch + max(1.8, 0.2 * size):
        return True
    c_prev, c_ln = _is_centered(prev, left, right), _is_centered(ln, left, right)
    if c_prev or c_ln:
        if c_prev and c_ln and prev.style_key() == ln.style_key() and prev.is_upper == ln.is_upper:
            return False
        return True
    if _BULLET_START_RE.match(ln.text):
        return True
    cont_x0 = cur[1].x0 if len(cur) >= 2 else None
    if cont_x0 is not None and ln.x0 > cont_x0 + 3.0:
        return True
    if cont_x0 is None and ln.x0 > prev.x0 + 3.0:
        return True  # dòng sau thụt vào hơn dòng đầu → đoạn mới
    if (
        cont_x0 is None
        and first_indent
        and abs(prev.x0 - (left + first_indent)) <= 2.0
        and abs(ln.x0 - (left + first_indent)) <= 2.0
    ):
        return True  # hai dòng liên tiếp cùng thụt đầu dòng → hai đoạn riêng
    if not _is_full(prev, right, ln):
        return True
    return False


def _build_flow_paragraphs(
    lines: Sequence[TextLine],
    left: float,
    right: float,
    pitch_by_size: dict,
    first_indent: Optional[float] = None,
) -> list[ParaBlock]:
    paras: list[list[TextLine]] = []
    cur: list[TextLine] = []
    for ln in sorted(lines, key=lambda l: (l.page, l.baseline, l.x0)):
        if cur and _same_row(cur[-1], ln) and ln.x0 > cur[-1].x1:
            # Hai mảnh cùng hàng nhưng cách xa (vd: chữ trái + chữ phải) → đoạn riêng
            paras.append(cur)
            cur = [ln]
            continue
        if not cur or not _starts_new_paragraph(cur[-1], ln, cur, left, right, pitch_by_size, first_indent):
            cur.append(ln)
        else:
            paras.append(cur)
            cur = [ln]
    if cur:
        paras.append(cur)
    return [_make_para(p, left, right, pitch_by_size) for p in paras]


def _make_para(lines: list[TextLine], left: float, right: float, pitch_by_size: dict) -> ParaBlock:
    first = lines[0]
    pitch = (
        statistics.median(b.baseline - a.baseline for a, b in zip(lines, lines[1:]))
        if len(lines) >= 2
        else _pitch_for(first.size, first.font, pitch_by_size)
    )
    para = ParaBlock(page=first.page, lines=lines, pitch=pitch)
    centered = all(_is_centered(l, left, right) for l in lines)
    if centered:
        para.align = "center"
        para.joiner = "break" if len(lines) > 1 else "space"
        para.role = "title"
        if len(lines) == 1:
            para.pitch = font_line_metrics(first.font)[0] * first.size
        return para

    justified = len(lines) >= 2 and all(_is_full(a, right, b) for a, b in zip(lines, lines[1:])) and all(
        right - a.x1 <= max(1.5, 0.25 * a.size) for a in lines[:-1]
    )
    rest_x0 = statistics.median(l.x0 for l in lines[1:]) if len(lines) >= 2 else None
    if (
        len(lines) == 1
        and right - first.x1 <= 1.5
        and first.x0 > left + 0.25 * (right - left)
    ):
        para.align = "right"
        return para

    base_x0 = rest_x0 if rest_x0 is not None else first.x0
    para.ind_left = max(0.0, base_x0 - left)
    para.first_line = first.x0 - base_x0 if rest_x0 is not None else 0.0
    if len(lines) >= 2 and not justified:
        para.align = "left"
    else:
        para.align = "both"
    if len(lines) >= 2 and not justified:
        # Đoạn căn trái nhiều dòng: giữ đúng ngắt dòng gốc
        para.joiner = "break"
    return para


def _merge_cross_page_paragraphs(blocks: list[Block], left: float, right: float) -> list[Block]:
    """Nối đoạn văn bị ngắt trang (dòng cuối trang trước tràn lề phải, dòng đầu trang sau sát lề)."""
    out: list[Block] = []
    for blk in blocks:
        if (
            out
            and isinstance(blk, ParaBlock)
            and isinstance(out[-1], ParaBlock)
            and blk.page == out[-1].page + 1
            and blk.align in ("both", "left")
            and out[-1].align in ("both", "left")
        ):
            prev = out[-1]
            last = prev.lines[-1]
            first = blk.lines[0]
            if (
                _is_full(last, right, first)
                and abs(first.x0 - (left + prev.ind_left)) <= 2.5
                and abs(first.size - last.size) < 0.6
                and not _BULLET_START_RE.match(first.text)
            ):
                prev.lines.extend(blk.lines)
                if prev.align == "left" and blk.align == "both":
                    prev.align = "both"
                continue
        out.append(blk)
    return out


# ─── 3d. Đo thông số & khoảng cách đoạn ────────────────────────────────────


def _measure(
    models: Sequence[PageModel],
    blocks: Sequence[Block],
    left: float,
    right: float,
    pitch_by_size: dict,
    header: Optional[TwoColBlock],
    first_indent: Optional[float] = None,
) -> MeasuredLayout:
    ml = MeasuredLayout()
    if not models:
        return ml
    pw, ph = models[0].width, models[0].height
    ml.page_width_mm = pw / PT_PER_MM
    ml.page_height_mm = ph / PT_PER_MM
    ml.margin_left_mm = left / PT_PER_MM
    ml.margin_right_mm = (pw - right) / PT_PER_MM

    body = [b for b in blocks if isinstance(b, ParaBlock) and b.role == "body"]
    all_lines = [l for m in models for l in m.lines if not l.role]

    # Phông & cỡ chữ chủ đạo của phần nội dung
    font_w: Counter[str] = Counter()
    size_w: Counter[float] = Counter()
    for b in body:
        for l in b.lines:
            for r in l.runs:
                n = len(r.text.strip())
                font_w[r.font] += n
                size_w[round(r.size * 2) / 2] += n
    if not font_w:
        for l in all_lines:
            for r in l.runs:
                font_w[r.font] += len(r.text.strip())
                size_w[round(r.size * 2) / 2] += len(r.text.strip())
    if font_w:
        ml.body_font = font_w.most_common(1)[0][0]
        ml.font_share = font_w.most_common(1)[0][1] / max(1, sum(font_w.values()))
    if size_w:
        ml.body_size = size_w.most_common(1)[0][0]

    # Căn lề chủ đạo
    aligns = Counter(b.align for b in body if len(b.lines) >= 2)
    ml.body_align = aligns.most_common(1)[0][0] if aligns else "both"

    # Khoảng cách dòng
    lh, _desc = font_line_metrics(ml.body_font)
    ml.line_pitch_pt = pitch_by_size.get(ml.body_size, lh * ml.body_size)
    ml.line_multiple = ml.line_pitch_pt / (lh * ml.body_size)

    # Thụt đầu dòng
    indents = [
        b.first_line + b.ind_left
        for b in body
        if b.align == "both" and 4.0 <= (b.first_line + b.ind_left) <= 80.0
    ]
    fi = first_indent if first_indent else (_mode(indents, step=0.5) if indents else None)
    ml.first_indent_mm = fi / PT_PER_MM if fi else None

    # Khoảng cách đoạn (đo giữa hai đoạn nội dung liên tiếp cùng trang)
    gaps: list[float] = []
    for a, b in zip(blocks, blocks[1:]):
        if isinstance(a, ParaBlock) and isinstance(b, ParaBlock) and a.role == "body" and b.role == "body" and a.page == b.page:
            if abs(a.size - ml.body_size) < 0.6 and abs(b.size - ml.body_size) < 0.6:
                gaps.append(b.top - a.bottom)
    gaps = [g for g in gaps if -2.0 <= g <= 3.0 * ml.body_size]
    if gaps:
        g = _mode(gaps, step=0.5)
        ml.para_spacing_pt = max(0.0, round(g or 0.0, 1))

    # Lề trên: đỉnh dòng nội dung đầu tiên (không tính số trang)
    tops = []
    for m in models:
        first_lines = sorted([l for l in m.lines if not l.role], key=lambda l: l.baseline)
        if first_lines:
            tops.append(first_lines[0].box_top())
    if tops:
        ml.margin_top_mm = max(0.0, min(tops)) / PT_PER_MM

    # Lề dưới: chỉ ước lượng được khoảng [lo, hi] từ các trang đầy
    lows: list[float] = []
    highs: list[float] = []
    for i, m in enumerate(models[:-1]):
        lines_m = sorted([l for l in m.lines if not l.role], key=lambda l: l.baseline)
        nxt = sorted([l for l in models[i + 1].lines if not l.role], key=lambda l: l.baseline)
        if not lines_m:
            continue
        last = lines_m[-1]
        last_bottom = last.box_top() + _pitch_for(last.size, last.font, pitch_by_size)
        if last_bottom < 0.7 * ph:
            continue  # trang chưa đầy (ngắt trang chủ động) → không suy ra được lề dưới
        highs.append(ph - last_bottom)
        if nxt:
            need = 2 * _pitch_for(nxt[0].size, nxt[0].font, pitch_by_size) + (ml.para_spacing_pt or 0.0)
            lows.append(ph - (last_bottom + need))
    if highs:
        ml.margin_bottom_hi_mm = max(0.0, min(highs)) / PT_PER_MM
    if lows:
        ml.margin_bottom_lo_mm = max(0.0, max(lows)) / PT_PER_MM

    # Số trang
    for m in models:
        for l in m.lines:
            if l.role == "page_number":
                ml.page_number_pages.append(m.index)
                if l.baseline < 0.5 * m.height:
                    top = l.box_top()
                    ml.header_distance_pt = top if ml.header_distance_pt is None else min(ml.header_distance_pt, top)
    return ml


def _resolve_all_spacing(
    blocks: Sequence[Block],
    header: Optional[TwoColBlock],
    sign: Optional[TwoColBlock],
    pitch_by_size: dict,
) -> None:
    for b in blocks:
        if isinstance(b, ParaBlock):
            b.resolve_spacing(pitch_by_size.get(round(b.size * 2) / 2) if b.role == "body" else None)
    for tc in (header, sign):
        if tc is None:
            continue
        for lcol, rcol in tc.rows:
            for it in lcol + rcol:
                if isinstance(it, ParaBlock):
                    it.resolve_spacing(None)
        tc.bottom = max([it.bottom for lc, rc in tc.rows for it in lc + rc] or [tc.top])


def _normalize_single_line_indents(blocks: Sequence[Block], ml: MeasuredLayout) -> None:
    """Đoạn 1 dòng lùi vào đúng bằng thụt đầu dòng chủ đạo → ghi là thụt đầu dòng (first line)."""
    if ml.first_indent_mm is None:
        return
    fi = ml.first_indent_mm * PT_PER_MM
    for b in blocks:
        if isinstance(b, ParaBlock) and b.role == "body" and len(b.lines) == 1 and b.align in ("both", "left"):
            if abs(b.ind_left - fi) <= 2.0 and abs(b.first_line) < 0.5:
                b.first_line, b.ind_left = b.ind_left, 0.0


def _assign_flow_spacing(blocks: Sequence[Block], models: Sequence[PageModel], ml: MeasuredLayout, left: float) -> None:
    """Tính khoảng cách trước (before) của từng khối theo vị trí thật trên PDF."""
    top_margin_pt = ml.margin_top_mm * PT_PER_MM
    # Đoạn 1 dòng: không đo được giãn dòng riêng → suy ra từ vị trí khối kế tiếp cùng trang
    for blk, nxt in zip(blocks, list(blocks[1:]) + [None]):
        if not isinstance(blk, ParaBlock) or len(blk.lines) != 1 or nxt is None or nxt.page != blk.page:
            continue
        single = font_line_metrics(blk.font)[0] * blk.size
        if isinstance(nxt, RuleBlock):
            room = nxt.rule.y - blk.top - 1.0
        else:
            room = nxt.top - blk.top
        if room < blk.line_height() - 0.3:
            blk.pitch = max(single, room)
            blk.resolve_spacing(None)
    prev_bottom: dict[int, float] = {}
    for blk in blocks:
        page = blk.page
        ref = prev_bottom.get(page, top_margin_pt)
        if isinstance(blk, TwoColBlock):
            blk.before = max(0.0, blk.top - ref)
            _assign_cell_spacing(blk, ref)
            prev_bottom[page] = blk.bottom
            continue
        if isinstance(blk, RuleBlock):
            blk.height = max(1.0, min(14.0, blk.rule.y - ref))
            blk.before = 0.0
            prev_bottom[page] = blk.bottom
            continue
        blk.before = max(0.0, blk.top - ref)
        prev_bottom[getattr(blk, "end_page", page)] = blk.bottom


def _assign_cell_spacing(blk: TwoColBlock, ref: float) -> None:
    row_ref = blk.top
    for li, (lcol, rcol) in enumerate(blk.rows):
        row_bottom = row_ref
        row_top = min([it.top for it in lcol + rcol if isinstance(it, ParaBlock)] or [row_ref])
        if li == 0:
            row_top = blk.top
        for col in (lcol, rcol):
            cref = row_top if li == 0 else row_ref
            for it in col:
                if isinstance(it, RuleBlock):
                    it.height = max(1.0, min(14.0, it.rule.y - cref))
                    it.before = 0.0
                else:
                    it.before = max(0.0, it.top - cref)
                cref = it.bottom
                row_bottom = max(row_bottom, cref)
        row_ref = row_bottom
