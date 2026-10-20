"""In tài liệu PDF: khoảng trang, kế hoạch in (khổ giấy, hướng, tỷ lệ, tự xoay) và kết xuất trang ở DPI máy in.

Không phụ thuộc `PySide6` — dùng chung cho hộp thoại «In» (`ui/print_dialog.py`), lớp gửi lệnh in qua `QPrinter`
(`ui/print_job.py`), dòng lệnh `cli print` và `pytest`. `print_to_pdf` dựng «bản in» thành tệp PDF chỉ bằng PyMuPDF
(đúng ảnh trang mà máy in nhận được) để kiểm tra mà không cần máy in.

Quy ước toạ độ: điểm (pt = 1/72 inch), gốc ở góc trên-trái tờ giấy theo hướng in. Mỗi trang PDF in thành một
**tờ** (`PrintSheet`): ảnh trang (đã tính `/Rotate`) xoay thêm `rotate` độ theo chiều kim đồng hồ rồi đặt vào
khung `target` trên tờ. Trang khác hướng giấy được xoay 90° như Acrobat «Tự động dọc/ngang»: trang ngang trên giấy
dọc xoay ngược chiều kim đồng hồ (đầu trang về mép trái — mép đóng gáy), trang dọc trên giấy ngang xoay thuận chiều.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import fitz  # PyMuPDF

from qtpdfpro.core import page_ops

# Khổ giấy dọc (rộng × cao, pt)
PAPER_SIZES: Dict[str, Tuple[float, float]] = {
    "A4": (595.28, 841.89),
    "A5": (419.53, 595.28),
    "A3": (841.89, 1190.55),
    "Letter": (612.0, 792.0),
    "Legal": (612.0, 1008.0),
}
PAPER_LABELS: Dict[str, str] = {
    "A4": "A4 (210 × 297 mm)",
    "A5": "A5 (148 × 210 mm)",
    "A3": "A3 (297 × 420 mm)",
    "Letter": "Letter (216 × 279 mm)",
    "Legal": "Legal (216 × 356 mm)",
}
ORIENTATIONS: Dict[str, str] = {"auto": "Tự động theo trang", "portrait": "Dọc", "landscape": "Ngang"}
SCALE_MODES: Dict[str, str] = {
    "fit": "Vừa khổ giấy",
    "actual": "Cỡ thật (100%)",
    "shrink": "Chỉ thu nhỏ trang quá khổ",
}
DUPLEX_MODES: Dict[str, str] = {
    "none": "In 1 mặt",
    "long": "2 mặt — lật theo cạnh dài",
    "short": "2 mặt — lật theo cạnh ngắn",
}
SUBSETS: Dict[str, str] = {
    "all": "Mọi trang trong phạm vi",
    "odd": "Chỉ trang lẻ (1, 3, 5…)",
    "even": "Chỉ trang chẵn (2, 4, 6…)",
}
PAGE_SCOPES = ("all", "current", "custom")

MIN_PRINT_DPI = 300
MAX_PRINT_DPI = 600
MIN_FALLBACK_DPI = 150  # trang quá khổ (A0…) hạ DPI để ảnh một trang không vượt MAX_RENDER_PIXELS
MAX_RENDER_PIXELS = 48_000_000  # ≈ A3 ở 480 dpi; A4 ở 600 dpi là 34,8 triệu điểm ảnh

# Thiết lập được nhớ cho lần in sau (số bản, khoảng trang, lẻ/chẵn, in ngược là theo từng lần in)
REMEMBERED_KEYS = (
    "printer", "collate", "paper", "orientation", "scale", "auto_rotate",
    "duplex", "grayscale", "annotations", "max_dpi",
)


class PrintError(ValueError):
    """Lỗi thiết lập in / khoảng trang không hợp lệ (thông báo tiếng Việt)."""


@dataclass
class PrintOptions:
    """Thiết lập một lần in."""

    printer: str = ""  # tên máy in; trống = máy in mặc định của Windows
    copies: int = 1
    collate: bool = True  # in trọn từng bộ (1-2-3, 1-2-3) thay vì 1-1, 2-2, 3-3
    paper: str = "A4"
    orientation: str = "auto"  # auto | portrait | landscape
    scale: str = "fit"  # fit | actual | shrink
    auto_rotate: bool = True  # xoay 90° trang khác hướng giấy cho vừa tờ
    duplex: str = "none"  # none | long | short
    grayscale: bool = False
    annotations: bool = True  # in kèm chú thích, con dấu & chữ ký (widget)
    subset: str = "all"  # all | odd | even (theo số trang)
    reverse: bool = False  # in ngược thứ tự (tờ cuối ra trước)
    max_dpi: int = MAX_PRINT_DPI  # trần DPI kết xuất (300 = in nhanh, 600 = theo máy in)

    def normalized(self) -> "PrintOptions":
        """Bản sao đã đưa mọi giá trị về miền hợp lệ (giá trị lạ → mặc định)."""
        base = PrintOptions()
        try:
            copies = int(self.copies)
        except (TypeError, ValueError):
            copies = 1
        try:
            max_dpi = int(self.max_dpi)
        except (TypeError, ValueError):
            max_dpi = MAX_PRINT_DPI
        return replace(
            self,
            printer=str(self.printer or ""),
            copies=max(1, min(999, copies)),
            collate=bool(self.collate),
            paper=self.paper if self.paper in PAPER_SIZES else base.paper,
            orientation=self.orientation if self.orientation in ORIENTATIONS else base.orientation,
            scale=self.scale if self.scale in SCALE_MODES else base.scale,
            auto_rotate=bool(self.auto_rotate),
            duplex=self.duplex if self.duplex in DUPLEX_MODES else base.duplex,
            grayscale=bool(self.grayscale),
            annotations=bool(self.annotations),
            subset=self.subset if self.subset in SUBSETS else base.subset,
            reverse=bool(self.reverse),
            max_dpi=max(MIN_PRINT_DPI, min(MAX_PRINT_DPI, max_dpi)),
        )

    def to_settings(self) -> Dict[str, object]:
        """Phần thiết lập lưu vào `settings.json` (không gồm số bản, khoảng trang)."""
        data = asdict(self.normalized())
        return {k: data[k] for k in REMEMBERED_KEYS}

    @classmethod
    def from_settings(cls, data: Optional[Mapping[str, object]]) -> "PrintOptions":
        """Đọc thiết lập đã nhớ (chịu khoá lạ / kiểu sai)."""
        if not isinstance(data, Mapping):
            return cls()
        valid = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in valid and k in REMEMBERED_KEYS}
        try:
            return cls(**kwargs).normalized()
        except TypeError:
            return cls()


@dataclass(frozen=True)
class PrintSheet:
    """Một mặt giấy in ra."""

    page_index: Optional[int]  # 0-based; None = tờ trắng (chèn giữa các bộ khi in 2 mặt)
    paper_width: float  # cỡ tờ theo hướng in (pt)
    paper_height: float
    rotate: int = 0  # 0 | 90 | 270 — xoay thêm ảnh trang theo chiều kim đồng hồ
    target: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # khung đặt ảnh trang (pt)
    scale: float = 1.0  # tỷ lệ trang → giấy (1 = cỡ thật)
    clipped: bool = False  # «Cỡ thật» mà trang lớn hơn vùng in được → mất phần mép

    @property
    def is_blank(self) -> bool:
        return self.page_index is None

    def to_dict(self) -> dict:
        return {
            "page": None if self.page_index is None else self.page_index + 1,
            "rotate": self.rotate,
            "scale": round(self.scale, 4),
            "target": [round(v, 2) for v in self.target],
            "clipped": self.clipped,
        }


@dataclass
class PrintPlan:
    """Kế hoạch in: các tờ của **một bộ** + thiết lập chung."""

    sheets: List[PrintSheet]
    options: PrintOptions
    landscape: bool
    paper_size: Tuple[float, float]  # theo hướng in
    margins: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # trái, trên, phải, dưới (pt)

    @property
    def sheet_count(self) -> int:
        return len(self.sheets)

    @property
    def page_indices(self) -> List[int]:
        return [s.page_index for s in self.sheets if s.page_index is not None]

    def job_sheets(self, manual_copies: bool = True) -> List[PrintSheet]:
        """Danh sách tờ gửi tới máy in. `manual_copies=False` khi trình điều khiển máy in tự nhân bản."""
        copies = self.options.copies
        if not manual_copies or copies <= 1 or not self.sheets:
            return list(self.sheets)
        blank = PrintSheet(None, *self.paper_size)
        duplex = self.options.duplex != "none"
        if self.options.collate:
            one = list(self.sheets)
            if duplex and len(one) % 2:
                one.append(blank)  # mỗi bộ bắt đầu ở mặt trước của tờ mới
            out = one * copies
            if duplex and len(self.sheets) % 2:
                out.pop()
            return out
        step = 2 if duplex else 1
        out: List[PrintSheet] = []
        for i in range(0, len(self.sheets), step):
            group = list(self.sheets[i:i + step])
            if len(group) < step:
                group.append(blank)
            out.extend(group * copies)
        if duplex and len(self.sheets) % 2:
            out.pop()
        return out

    def summary(self) -> str:
        """Mô tả ngắn: «3 tờ × 2 bản · A4 dọc · Vừa khổ giấy · Đen trắng»."""
        o = self.options
        parts = [f"{self.sheet_count} trang" + (f" × {o.copies} bản" if o.copies > 1 else "")]
        parts.append(f"{o.paper} {'ngang' if self.landscape else 'dọc'}")
        parts.append(SCALE_MODES[o.scale])
        if o.duplex != "none":
            parts.append("2 mặt")
        parts.append("Đen trắng" if o.grayscale else "Màu")
        return " · ".join(parts)

    def to_dict(self) -> dict:
        o = self.options
        return {
            "paper": o.paper,
            "orientation": "landscape" if self.landscape else "portrait",
            "paper_size_pt": [round(v, 2) for v in self.paper_size],
            "scale_mode": o.scale,
            "copies": o.copies,
            "collate": o.collate,
            "duplex": o.duplex,
            "grayscale": o.grayscale,
            "annotations": o.annotations,
            "sheets": [s.to_dict() for s in self.sheets],
        }


@dataclass
class PrintImage:
    """Ảnh một trang đã kết xuất để in (RGB 3 kênh hoặc xám 1 kênh, không kênh alpha)."""

    width: int
    height: int
    stride: int
    grayscale: bool
    samples: bytes
    dpi: float


@dataclass
class PrintResult:
    """Kết quả một lần in."""

    sheets_printed: int = 0
    total_sheets: int = 0
    cancelled: bool = False
    output_path: str = ""  # khi in ra tệp
    dpi: int = 0
    printer: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


ProgressCallback = Callable[[int, int], None]  # (số tờ đã gửi, tổng số tờ)


# ─── Khoảng trang ─────────────────────────────────────────────────────────


def parse_print_range(spec: str, total: int) -> List[int]:
    """Chuỗi khoảng trang (1-based) → chỉ số 0-based theo thứ tự nhập, bỏ trùng.

    Cú pháp như `cli extract` (`page_ops.parse_order_spec`) cộng thêm khoảng mở: `'8-'` = trang 8 tới hết,
    `'-3'` = trang 1 tới 3. Ví dụ `'1-3, 5, 8-'`, `'end'`, `'le'`/`'chan'`. Bỏ trống hoặc `'all'` = tất cả.
    """
    if total <= 0:
        raise PrintError("Tài liệu không có trang nào để in.")
    text = (spec or "").strip()
    if not text or text.lower() in ("all", "*", "tất cả", "tat ca", "tatca"):
        return list(range(total))
    tokens: List[str] = []
    for raw in re.split(r"[,;]", text):
        token = raw.strip().replace(" ", "").replace("–", "-").replace("—", "-")
        if not token:
            continue
        if token.endswith("-"):
            token += "end"
        elif token.startswith("-"):
            token = "1" + token
        tokens.append(token)
    if not tokens:
        raise PrintError("Chưa nhập khoảng trang cần in.")
    try:
        pages = page_ops.parse_page_selection(",".join(tokens), total)
    except page_ops.PageOpsError as exc:
        raise PrintError(str(exc)) from exc
    if not pages:
        raise PrintError(f"Khoảng trang «{spec}» không có trang nào của tài liệu (1..{total}).")
    return pages


def resolve_print_pages(scope: str, spec: str, total: int, current: int = 0) -> List[int]:
    """Trang cần in theo lựa chọn «Tất cả» / «Trang hiện tại» / «Tuỳ chọn» (chỉ số 0-based)."""
    if total <= 0:
        raise PrintError("Tài liệu không có trang nào để in.")
    if scope == "current":
        return [max(0, min(total - 1, int(current)))]
    if scope == "custom":
        if not (spec or "").strip():
            raise PrintError("Hãy nhập khoảng trang cần in, ví dụ 1-3, 5, 8-")
        return parse_print_range(spec, total)
    return list(range(total))


def apply_subset(indices: Sequence[int], subset: str = "all", reverse: bool = False) -> List[int]:
    """Lọc trang lẻ / chẵn (theo số trang 1-based) và đảo thứ tự nếu cần."""
    if subset == "odd":
        out = [i for i in indices if i % 2 == 0]
    elif subset == "even":
        out = [i for i in indices if i % 2 == 1]
    else:
        out = list(indices)
    if reverse:
        out.reverse()
    return out


# ─── Kế hoạch in ──────────────────────────────────────────────────────────


def page_sizes(doc: fitz.Document) -> List[Tuple[float, float]]:
    """Cỡ hiển thị (đã tính `/Rotate`) của mọi trang, pt."""
    return [(float(p.rect.width), float(p.rect.height)) for p in doc]


def paper_size(paper: str, landscape: bool = False) -> Tuple[float, float]:
    w, h = PAPER_SIZES.get(paper, PAPER_SIZES["A4"])
    return (h, w) if landscape else (w, h)


def _is_landscape(size: Tuple[float, float]) -> bool:
    return size[0] > size[1] + 0.5


def choose_landscape(sizes: Sequence[Tuple[float, float]], indices: Sequence[int], options: PrintOptions) -> bool:
    """Hướng giấy của cả lần in: theo lựa chọn, hoặc «Tự động» = hướng của đa số trang được in (hoà → dọc)."""
    if options.orientation == "landscape":
        return True
    if options.orientation == "portrait":
        return False
    wide = sum(1 for i in indices if _is_landscape(sizes[i]))
    return wide * 2 > len(indices)


def plan_print(
    sizes: Sequence[Tuple[float, float]],
    indices: Sequence[int],
    options: PrintOptions,
    margins: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
) -> PrintPlan:
    """Lập kế hoạch in cho các trang `indices` (đã lọc lẻ/chẵn, đảo thứ tự).

    `sizes` là cỡ hiển thị của mọi trang (`page_sizes`); `margins` là lề không in được của máy in (pt, theo
    hướng giấy). «Vừa khổ giấy» / «Chỉ thu nhỏ» căn giữa trong vùng in được; «Cỡ thật» căn giữa tờ giấy.
    """
    opts = options.normalized()
    if not indices:
        raise PrintError("Không có trang nào để in.")
    for i in indices:
        if not 0 <= i < len(sizes):
            raise PrintError(f"Trang {i + 1} nằm ngoài tài liệu (1..{len(sizes)}).")
    landscape = choose_landscape(sizes, indices, opts)
    pw, ph = paper_size(opts.paper, landscape)
    ml, mt, mr, mb = (max(0.0, float(m)) for m in margins)
    if ml + mr >= pw - 36 or mt + mb >= ph - 36:
        ml = mt = mr = mb = 0.0  # lề máy in vô lý → bỏ qua
    area_w, area_h = pw - ml - mr, ph - mt - mb

    sheets: List[PrintSheet] = []
    for idx in indices:
        w, h = sizes[idx]
        w, h = max(w, 1.0), max(h, 1.0)
        rotate = 0
        if opts.auto_rotate and _is_landscape((w, h)) != landscape and abs(w - h) > 0.5:
            rotate = 90 if landscape else 270
        cw, ch = (h, w) if rotate else (w, h)
        fit = min(area_w / cw, area_h / ch)
        if opts.scale == "fit":
            s = fit
        elif opts.scale == "shrink":
            s = min(1.0, fit)
        else:
            s = 1.0
        tw, th = cw * s, ch * s
        if opts.scale == "actual":
            x0, y0 = (pw - tw) / 2, (ph - th) / 2
        else:
            x0, y0 = ml + (area_w - tw) / 2, mt + (area_h - th) / 2
        clipped = opts.scale == "actual" and (tw > area_w + 0.5 or th > area_h + 0.5)
        sheets.append(PrintSheet(idx, pw, ph, rotate, (x0, y0, x0 + tw, y0 + th), s, clipped))
    return PrintPlan(sheets, opts, landscape, (pw, ph), (ml, mt, mr, mb))


def plan_document(
    doc: fitz.Document,
    indices: Sequence[int],
    options: PrintOptions,
    margins: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
) -> PrintPlan:
    """`plan_print` cho tài liệu đang mở (áp dụng lọc lẻ/chẵn & in ngược của `options`)."""
    opts = options.normalized()
    pages = apply_subset(indices, opts.subset, opts.reverse)
    if not pages:
        raise PrintError("Không có trang nào sau khi lọc trang lẻ/chẵn.")
    return plan_print(page_sizes(doc), pages, opts, margins)


# ─── Kết xuất ảnh trang ───────────────────────────────────────────────────


def clamp_print_dpi(printer_dpi: Optional[float], max_dpi: int = MAX_PRINT_DPI) -> int:
    """DPI kết xuất trang khi in: theo máy in nhưng trong khoảng 300–600 (và không quá `max_dpi`)."""
    upper = max(MIN_PRINT_DPI, min(MAX_PRINT_DPI, int(max_dpi or MAX_PRINT_DPI)))
    try:
        dpi = int(round(float(printer_dpi or 0)))
    except (TypeError, ValueError):
        dpi = 0
    if dpi <= 0:
        dpi = MIN_PRINT_DPI
    return max(MIN_PRINT_DPI, min(upper, dpi))


def effective_dpi(sheet: PrintSheet, dpi: float, max_pixels: int = MAX_RENDER_PIXELS) -> float:
    """Hạ DPI cho trang quá khổ để ảnh không vượt `max_pixels` điểm ảnh (không thấp hơn 150 dpi)."""
    x0, y0, x1, y1 = sheet.target
    area_in2 = max(1e-6, (x1 - x0) * (y1 - y0)) / (72.0 * 72.0)
    limit = math.sqrt(max_pixels / area_in2)
    if dpi <= limit:
        return float(dpi)
    return max(min(MIN_FALLBACK_DPI, float(dpi)), limit)


def render_page_pixmap(
    doc: fitz.Document,
    page_index: int,
    zoom: float,
    rotate: int = 0,
    grayscale: bool = False,
    annotations: bool = True,
) -> fitz.Pixmap:
    """Kết xuất trang ở tỷ lệ `zoom` (1 = 72 dpi), xoay thêm `rotate` độ, ảnh xám hoặc RGB, không alpha."""
    page = doc[page_index]
    mat = fitz.Matrix(zoom, zoom)
    if rotate % 360:
        mat = mat.prerotate(rotate % 360)
    colorspace = fitz.csGRAY if grayscale else fitz.csRGB
    return page.get_pixmap(matrix=mat, colorspace=colorspace, alpha=False, annots=annotations)


def render_sheet_pixmap(
    doc: fitz.Document,
    sheet: PrintSheet,
    dpi: float,
    grayscale: bool = False,
    annotations: bool = True,
) -> Optional[fitz.Pixmap]:
    """Ảnh trang cho một tờ, đúng cỡ khung `target` ở `dpi` (None với tờ trắng)."""
    if sheet.page_index is None:
        return None
    zoom = sheet.scale * effective_dpi(sheet, dpi) / 72.0
    return render_page_pixmap(doc, sheet.page_index, zoom, sheet.rotate, grayscale, annotations)


def render_sheet(
    doc: fitz.Document,
    sheet: PrintSheet,
    dpi: float,
    grayscale: bool = False,
    annotations: bool = True,
) -> Optional[PrintImage]:
    """Như `render_sheet_pixmap` nhưng trả về bytes thô (dựng `QImage` ở giao diện)."""
    pix = render_sheet_pixmap(doc, sheet, dpi, grayscale, annotations)
    if pix is None:
        return None
    zoom_dpi = effective_dpi(sheet, dpi)
    return PrintImage(pix.width, pix.height, pix.stride, pix.n == 1, bytes(pix.samples), zoom_dpi)


# ─── Tài liệu ─────────────────────────────────────────────────────────────


def printing_allowed(doc: fitz.Document) -> bool:
    """Tài liệu có cho phép in không (cờ quyền in của PDF mã hoá)."""
    try:
        perms = int(doc.permissions)
    except Exception:
        return True
    return bool(perms & fitz.PDF_PERM_PRINT)


def snapshot_pdf_bytes(doc: fitz.Document) -> bytes:
    """Bản chụp tài liệu (gồm chú thích chưa lưu) để luồng in mở `fitz.Document` riêng.

    PyMuPDF không an toàn khi hai luồng dùng chung một tài liệu, nên luồng in không đọc thẳng tài liệu của tab.
    """
    if doc.is_pdf:
        return doc.tobytes(garbage=0, deflate=False)
    return doc.convert_to_pdf()


def print_to_pdf(
    doc: fitz.Document,
    plan: PrintPlan,
    output: Union[str, Path],
    dpi: int = MIN_PRINT_DPI,
    progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> PrintResult:
    """Dựng «bản in» thành tệp PDF: mỗi tờ là một trang cỡ giấy chứa ảnh trang ở `dpi` (đúng như gửi máy in).

    Số bản được nhân trong tệp (theo `collate`, chèn tờ trắng giữa các bộ khi in 2 mặt).
    """
    sheets = plan.job_sheets(manual_copies=True)
    o = plan.options
    dpi = max(72, int(dpi))
    out = fitz.open()
    result = PrintResult(total_sheets=len(sheets), dpi=dpi, printer="PDF")
    try:
        for i, sheet in enumerate(sheets):
            if should_cancel is not None and should_cancel():
                result.cancelled = True
                break
            page = out.new_page(width=sheet.paper_width, height=sheet.paper_height)
            pix = render_sheet_pixmap(doc, sheet, dpi, o.grayscale, o.annotations)
            if pix is not None:
                page.insert_image(fitz.Rect(sheet.target), pixmap=pix)
            result.sheets_printed = i + 1
            if progress is not None:
                progress(i + 1, len(sheets))
        if result.cancelled:
            return result
        result.output_path = str(page_ops.save_pdf(out, output))
    finally:
        out.close()
    return result


__all__ = [
    "PAPER_SIZES", "PAPER_LABELS", "ORIENTATIONS", "SCALE_MODES", "DUPLEX_MODES", "SUBSETS", "PAGE_SCOPES",
    "MIN_PRINT_DPI", "MAX_PRINT_DPI", "PrintError", "PrintOptions", "PrintSheet", "PrintPlan", "PrintImage",
    "PrintResult", "parse_print_range", "resolve_print_pages", "apply_subset", "page_sizes", "paper_size",
    "choose_landscape", "plan_print", "plan_document", "clamp_print_dpi", "effective_dpi", "render_page_pixmap",
    "render_sheet_pixmap", "render_sheet", "printing_allowed", "snapshot_pdf_bytes", "print_to_pdf",
]
