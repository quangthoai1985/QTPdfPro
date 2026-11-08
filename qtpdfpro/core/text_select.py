"""Chọn & sao chép chữ trên trang PDF — lõi của công cụ «Chọn» trên khung đọc và lệnh `cli text`.

- **Trang có lớp chữ**: danh sách từ theo thứ tự đọc (`page_words`; chữ đã chuẩn hoá Unicode NFC, phông TCVN3
  `.Vn*` chuyển sang Unicode), chọn theo khoảng (kéo bắt đầu trên chữ), theo vùng (kéo từ chỗ trống / giữ Alt),
  một từ (nhấp đúp), một dòng (nhấp ba lần).
- **Ghép chữ để sao chép** (`lines_to_text`): giữ nguyên ngắt dòng, hoặc nối các dòng bị ngắt thành đoạn liền
  (tách đoạn theo khoảng cách đoạn, thụt đầu dòng, dòng kết thúc sớm, gạch đầu dòng / đánh số).
- **Trang ảnh quét** (`is_scanned_page`): kết xuất đúng vùng chọn (`render_region`, ở luồng giao diện vì dùng
  PyMuPDF) rồi nhận dạng bằng `OcrEngine.ocr_image` (`recognize_region`, chỉ numpy + ONNX Runtime → chạy được ở
  luồng nền). Chữ thật nằm trong vùng (số hiệu / ngày phần mềm cấp số chèn sau khi quét) hiện trên ảnh kết xuất
  nên được đọc cùng luôn.

Toạ độ vào / ra: trang **chưa xoay** (hệ của `page.get_text` và chú thích), như khung đọc truyền cho công cụ chuột.
Không phụ thuộc Qt.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import fitz  # PyMuPDF
import numpy as np

from qtpdfpro.core.annotations import _line_rects, _nearest_word
from qtpdfpro.core.annotations import page_words as _raw_page_words
from qtpdfpro.core.font_resolver import detect_font_encoding, normalize_vietnamese_text

Word = tuple  # (x0, y0, x1, y1, chữ, khối, dòng, số_thứ_tự_từ) — như page.get_text("words")

SCANNED_PAGE_CHARS = 100  # = ocr.TEXT_PAGE_CHARS: ít ký tự chữ thật hơn thế + có ảnh → trang ảnh quét
REGION_MIN_SIDE_PX = 736  # = limit_side_len của bộ dò dòng: đệm ảnh vùng tới cỡ này để nó không phóng to dải hẹp
REGION_MARGIN_PX = 24  # lề trắng quanh ảnh vùng (dòng chữ sát mép vẫn dò được)
MAX_REGION_PIXELS = 30_000_000  # vùng quá lớn → giảm độ phân giải kết xuất
MIN_OCR_SIDE_PT = 6.0  # vùng nhỏ hơn thế (pt) coi như nhấp chuột, không nhận dạng

_LIST_ITEM_RE = re.compile(r"^\s*(?:[-–—•+*▪●○]|\d{1,3}[.)]|[a-zđ][.)]|[IVXLC]{1,5}\.)\s")


# ─── Từ trên trang ─────────────────────────────────────────────────────────


def _legacy_spans(page: fitz.Page) -> List[Tuple[fitz.Rect, str]]:
    """Các đoạn chữ dùng phông TCVN3 (`.VnTime`…) — rỗng (nhanh) khi trang không có phông như vậy."""
    try:
        fonts = page.get_fonts(full=False)
    except Exception:
        return []
    if not any(detect_font_encoding(str(f[3])) == "tcvn3" for f in fonts):
        return []
    spans: List[Tuple[fitz.Rect, str]] = []
    for block in page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT).get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                font = span.get("font", "")
                if detect_font_encoding(font) == "tcvn3":
                    spans.append((fitz.Rect(span["bbox"]), font))
    return spans


def page_words(page: fitz.Page) -> List[Word]:
    """Từ trên trang theo thứ tự đọc; chữ đã chuẩn hoá để sao chép (NFC, TCVN3 → Unicode, bỏ ký tự rác)."""
    legacy = _legacy_spans(page)
    out: List[Word] = []
    for w in _raw_page_words(page):
        font = None
        if legacy:
            c = fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
            font = next((f for r, f in legacy if c in r), None)
        text = normalize_vietnamese_text(w[4], font).strip()
        if text:
            out.append((w[0], w[1], w[2], w[3], text, w[5], w[6], w[7]))
    return out


def page_text_chars(page: fitz.Page) -> int:
    return sum(1 for ch in page.get_text("text") if not ch.isspace())


def is_scanned_page(page: fitz.Page) -> bool:
    """Trang ảnh quét chưa có lớp chữ: rất ít chữ thật và có ảnh → chọn chữ phải nhận dạng (OCR)."""
    if page_text_chars(page) >= SCANNED_PAGE_CHARS:
        return False
    try:
        return bool(page.get_images(full=True))
    except Exception:
        return False


# ─── Chọn ──────────────────────────────────────────────────────────────────


def _word_rect(w: Word, pad: float = 0.0) -> fitz.Rect:
    h = (w[3] - w[1]) * pad
    return fitz.Rect(w[0] - h, w[1] - h * 0.3, w[2] + h, w[3] + h * 0.3)


def word_index_at(words: Sequence[Word], pt, pad: float = 0.15) -> Optional[int]:
    """Chỉ số từ nằm dưới điểm `pt` (khung từ nới `pad` × chiều cao); None nếu không trúng từ nào."""
    p = fitz.Point(pt)
    for i, w in enumerate(words):
        if p in _word_rect(w, pad):
            return i
    return None


def near_text(words: Sequence[Word], pt) -> bool:
    """Điểm nằm trên / sát chữ → kéo chuột từ đây là chọn theo dòng chữ (con trỏ chữ I); không thì kéo khung."""
    return word_index_at(words, pt, pad=0.45) is not None


def select_range(words: Sequence[Word], p0, p1) -> List[Word]:
    """Mọi từ từ vị trí `p0` tới `p1` theo thứ tự đọc (như kéo chuột trong trình đọc)."""
    if not words:
        return []
    i0, i1 = _nearest_word(words, fitz.Point(p0)), _nearest_word(words, fitz.Point(p1))
    if i0 > i1:
        i0, i1 = i1, i0
    return list(words[i0:i1 + 1])


def select_area(words: Sequence[Word], rect) -> List[Word]:
    """Từ có tâm nằm trong khung chữ nhật (chọn một cột / một ô bảng mà không lẫn dòng bên cạnh)."""
    area = fitz.Rect(rect).normalize()
    out = []
    for w in words:
        if fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2) in area:
            out.append(w)
    return out


def select_word(words: Sequence[Word], pt) -> List[Word]:
    i = word_index_at(words, pt)
    return [words[i]] if i is not None else []


def select_line(words: Sequence[Word], pt) -> List[Word]:
    """Cả dòng chứa điểm `pt` (nhấp ba lần)."""
    i = word_index_at(words, pt, pad=0.45)
    if i is None:
        return []
    key = (words[i][5], words[i][6])
    return [w for w in words if (w[5], w[6]) == key]


def selection_rects(words: Sequence[Word]) -> List[fitz.Rect]:
    """Khung tô của vùng chọn, gộp theo dòng."""
    return _line_rects(words)


# ─── Ghép chữ để sao chép ──────────────────────────────────────────────────


@dataclass
class TextLine:
    rect: fitz.Rect  # khung dòng (chỉ cần cùng một hệ toạ độ trong một lần ghép)
    text: str


def word_lines(words: Sequence[Word]) -> List[TextLine]:
    """Gom từ thành dòng (theo khối + dòng của PyMuPDF), giữ thứ tự."""
    lines: List[TextLine] = []
    keys: List[Tuple[int, int]] = []
    for w in words:
        key = (w[5], w[6])
        r = fitz.Rect(w[:4])
        if keys and keys[-1] == key:
            lines[-1].rect |= r
            lines[-1].text += " " + w[4]
        else:
            lines.append(TextLine(r, w[4]))
            keys.append(key)
    return lines


def _starts_paragraph(prev: TextLine, cur: TextLine, left: float, right: float, normal_gap: float) -> bool:
    h = max(1.0, min(prev.rect.height, cur.rect.height))
    gap = cur.rect.y0 - prev.rect.y1
    return (
        gap > normal_gap + 0.4 * h  # khoảng cách đoạn
        or gap < -0.5 * h  # quay lên trên → cột khác
        or cur.rect.x0 > prev.rect.x0 + 1.2 * h  # thụt đầu dòng so với dòng trước
        or cur.rect.x0 > left + 1.2 * h  # thụt so với lề trái (các đoạn «Căn cứ…» liên tiếp đều thụt)
        or prev.rect.x1 < right - 4.0 * h  # dòng trước kết thúc sớm → cuối đoạn
        or bool(_LIST_ITEM_RE.match(cur.text))  # gạch đầu dòng / đánh số
    )


def lines_to_text(lines: Sequence[TextLine], join_lines: bool = False) -> str:
    """Ghép dòng thành văn bản: giữ ngắt dòng, hoặc (`join_lines`) nối dòng trong cùng đoạn bằng dấu cách."""
    texts = [ln.text.strip() for ln in lines]
    if not join_lines or len(lines) < 2:
        return "\n".join(t for t in texts if t)
    right = max(ln.rect.x1 for ln in lines)
    left = min(ln.rect.x0 for ln in lines)
    gaps = sorted(b.rect.y0 - a.rect.y1 for a, b in zip(lines, lines[1:]) if b.rect.y0 >= a.rect.y1 - 1.0)
    normal_gap = gaps[len(gaps) // 2] if gaps else 0.0
    parts = [texts[0]]
    for prev, cur, text in zip(lines, lines[1:], texts[1:]):
        if not text:
            continue
        sep = "\n" if _starts_paragraph(prev, cur, left, right, normal_gap) else " "
        parts.append(sep + text)
    return "".join(parts).strip()


def selection_text(words: Sequence[Word], join_lines: bool = False) -> str:
    return lines_to_text(word_lines(words), join_lines)


# ─── Nhận dạng vùng trên trang ảnh quét ────────────────────────────────────


@dataclass
class RegionImage:
    """Ảnh RGB của một vùng trang (đã đệm lề trắng) + phép đổi điểm ảnh ↔ toạ độ trang chưa xoay."""

    page_index: int
    rgb: np.ndarray
    zoom: float  # điểm ảnh / pt
    margin: int  # lề trắng đã thêm ở trái / trên (px)
    origin: Tuple[int, int]  # góc trên-trái của ảnh kết xuất trong không gian đã nhân `matrix`
    matrix: fitz.Matrix  # ma trận kết xuất (thu phóng × góc xoay xem)
    derotation: fitz.Matrix  # trang hiển thị → trang chưa xoay
    page_rect: fitz.Rect  # vùng đã kết xuất (toạ độ trang chưa xoay)
    size: Tuple[int, int] = (0, 0)  # (rộng, cao) px của phần kết xuất thật, chưa tính lề đệm

    def to_page(self, x_px: float, y_px: float) -> fitz.Point:
        p = fitz.Point(x_px - self.margin + self.origin[0], y_px - self.margin + self.origin[1])
        return p * ~self.matrix * self.derotation

    def rect_to_page(self, rect_px) -> fitz.Rect:
        r = fitz.Rect(rect_px)
        pts = [self.to_page(x, y) for x, y in ((r.x0, r.y0), (r.x1, r.y0), (r.x0, r.y1), (r.x1, r.y1))]
        return fitz.Rect(min(p.x for p in pts), min(p.y for p in pts), max(p.x for p in pts), max(p.y for p in pts))


def render_region(page: fitz.Page, rect, dpi: int = 0, view_rotation: int = 0) -> RegionImage:
    """Kết xuất vùng `rect` (trang chưa xoay) thành ảnh đúng chiều đang xem (gồm /Rotate và góc xoay xem thêm).

    `dpi=0`: theo độ phân giải ảnh quét của trang (200–300, như OCR cả tệp). Ảnh được đệm lề trắng và tối thiểu
    `REGION_MIN_SIDE_PX` để bộ dò dòng không phóng một dải chữ hẹp lên hàng chục nghìn điểm ảnh.
    """
    if not dpi:
        from qtpdfpro.core.ocr import auto_dpi

        dpi = auto_dpi(page)
    clip = (fitz.Rect(rect).normalize() * page.rotation_matrix) & page.rect  # hệ trang hiển thị (pt)
    if clip.is_empty or clip.width < 1 or clip.height < 1:
        raise ValueError("Vùng chọn nằm ngoài trang.")
    zoom = dpi / 72.0
    pixels = clip.width * clip.height * zoom * zoom
    if pixels > MAX_REGION_PIXELS:
        zoom *= math.sqrt(MAX_REGION_PIXELS / pixels)
    mat = fitz.Matrix(zoom, zoom).prerotate(int(view_rotation) % 360)
    pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False, colorspace=fitz.csRGB)
    samples = pix.samples  # giữ bytes sống tới khi chép xong
    arr = np.frombuffer(samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, : pix.width * 3]
    arr = arr.reshape(pix.height, pix.width, 3)
    m = REGION_MARGIN_PX
    h = max(pix.height + 2 * m, REGION_MIN_SIDE_PX)
    w = max(pix.width + 2 * m, REGION_MIN_SIDE_PX)
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    canvas[m:m + pix.height, m:m + pix.width] = arr
    return RegionImage(
        page_index=page.number,
        rgb=canvas,
        zoom=zoom,
        margin=m,
        origin=(pix.x, pix.y),
        matrix=mat,
        derotation=page.derotation_matrix,
        page_rect=clip * page.derotation_matrix,
        size=(pix.width, pix.height),
    )


@dataclass
class RegionText:
    """Kết quả nhận dạng một vùng: dòng chữ (khung theo điểm ảnh — để ghép đoạn) + khung trên trang."""

    page_index: int
    lines: List[TextLine] = field(default_factory=list)
    page_rects: List[fitz.Rect] = field(default_factory=list)  # khung từng dòng, toạ độ trang chưa xoay
    seconds: float = 0.0

    def text(self, join_lines: bool = False) -> str:
        return lines_to_text(self.lines, join_lines)


def recognize_region(engine, region: RegionImage, clean_ink: bool = True) -> RegionText:
    """Nhận dạng ảnh vùng bằng `engine.ocr_image` (OcrEngine — chỉ numpy + ONNX Runtime, gọi ở luồng nền được).

    `clean_ink`: xoá nét đỏ / xanh (con dấu, chữ ký) trước khi đọc như OCR cả tệp.
    """
    t0 = time.perf_counter()
    lines = engine.ocr_image(region.rgb, region.zoom, clean_ink)
    out = RegionText(region.page_index)
    for ln in lines:
        text = (ln.text or "").strip()
        if not text:
            continue
        px = fitz.Rect(*(v * region.zoom for v in ln.bbox))
        out.lines.append(TextLine(px, normalize_vietnamese_text(text)))
        out.page_rects.append(region.rect_to_page(px))
    out.seconds = time.perf_counter() - t0
    return out


def region_png(region: RegionImage) -> bytes:
    """Ảnh PNG của vùng (bỏ lề trắng đã đệm) — cho «Sao chép ảnh vùng chọn» / lệnh CLI."""
    m = region.margin
    w, h = region.size
    crop = np.ascontiguousarray(region.rgb[m:m + h, m:m + w])
    pix = fitz.Pixmap(fitz.csRGB, crop.shape[1], crop.shape[0], crop.tobytes(), False)
    return pix.tobytes("png")
