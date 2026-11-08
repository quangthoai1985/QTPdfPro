"""Lớp chữ nhận dạng tạm cho trang ảnh quét (Đợt 2 của công cụ «Chọn chữ») — không phụ thuộc Qt.

- `prepare_page_image` (luồng giao diện — dùng PyMuPDF) kết xuất cả trang đúng chiều đang xem;
  `recognize_page` (luồng nền — chỉ numpy + ONNX Runtime) nhận dạng thành `PageOcr`:
  * `words`: từ theo thứ tự đọc (cắt XY: hai cột → hết cột trái rồi cột phải), toạ độ **trang chưa xoay**, cùng
    dạng tuple với `text_select.page_words` → công cụ Chọn dùng như chữ thật (kéo theo dòng, nhấp đúp, Ctrl+A).
    Khung từng từ: ước lượng theo tỷ lệ số ký tự trong dòng rồi kéo về khe trắng thật giữa hai từ (`column_ink`).
  * `lines`: `OcrLine` theo toạ độ khung nhìn (= trang hiển thị như `OcrEngine.ocr_page` khi không xoay xem thêm;
    trang xoay xem thì là trang đã xoay thêm `view_rotation`) → dùng lại khi lưu PDF tìm kiếm được
    (`CachedOcrEngine` cho `ocr.ocr_pdf`, lớp chữ đặt theo tổng góc xoay), không phải nhận dạng lại.
- `OcrLayerCache`: lưu đệm theo SHA-256 nội dung tệp ở `<thư mục dữ liệu>/ocr_cache/<sha>.json` (mở lại tệp là có
  chữ ngay); bộ mô hình đổi phiên bản thì bỏ. Chỉ nằm trên máy người dùng.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Dict, List, Optional

import fitz  # PyMuPDF
import numpy as np

from qtpdfpro.core import text_select as ts
from qtpdfpro.core.font_resolver import normalize_vietnamese_text
from qtpdfpro.core.settings import get_data_dir

CACHE_FORMAT = 1
CACHE_DIR_NAME = "ocr_cache"
MAX_CACHE_FILES = 300  # giữ chừng này tệp gần nhất


@dataclass
class PageOcr:
    """Chữ nhận dạng của một trang."""

    page_index: int
    view_rotation: int = 0
    words: List[ts.Word] = field(default_factory=list)
    lines: list = field(default_factory=list)  # List[ocr.OcrLine] — hệ khung nhìn (pt), xem `view_rotation`
    seconds: float = 0.0

    @property
    def text(self) -> str:
        return ts.selection_text(self.words)


def _bundle_version() -> int:
    from qtpdfpro.core.ocr_models import BUNDLE_VERSION

    return BUNDLE_VERSION


def page_rect_unrotated(page: fitz.Page) -> fitz.Rect:
    return page.rect * page.derotation_matrix


def prepare_page_image(page: fitz.Page, view_rotation: int = 0, dpi: int = 0) -> ts.RegionImage:
    """Ảnh cả trang để nhận dạng (gọi ở luồng giao diện: dùng PyMuPDF). `dpi=0` theo ảnh quét (200–300)."""
    return ts.render_region(page, page_rect_unrotated(page), dpi=dpi, view_rotation=view_rotation)


def column_ink(gray: np.ndarray) -> np.ndarray:
    """Cột nào của ảnh dòng chữ (xám) có mực: ngưỡng giữa nền giấy và nét chữ, cột có ≥ 1 điểm mực."""
    if gray.size == 0:
        return np.zeros(gray.shape[1] if gray.ndim == 2 else 0, dtype=bool)
    lo, hi = np.percentile(gray, 2), np.percentile(gray, 90)
    if hi - lo < 40:  # gần như trơn: không đủ tương phản để tìm khe
        return np.ones(gray.shape[1], dtype=bool)
    return ((gray < (lo + hi) / 2).sum(axis=0)) >= 1


def _ink_gaps(ink: np.ndarray, min_width: float) -> List[tuple]:
    """Khoảng trắng giữa hai vùng mực (không tính hai mép ngoài), rộng ≥ `min_width` cột: [(đầu, cuối), …]."""
    gaps = []
    n = len(ink)
    i = 0
    while i < n:
        if ink[i]:
            i += 1
            continue
        j = i
        while j < n and not ink[j]:
            j += 1
        if i > 0 and j < n and j - i >= min_width:
            gaps.append((i, j))
        i = j
    return gaps


def split_line_words(text: str, rect: fitz.Rect, ink: Optional[np.ndarray] = None) -> List[tuple]:
    """Chia một dòng chữ nhận dạng thành từ. Khung từng từ ước lượng theo tỷ lệ vị trí ký tự trong dòng; có `ink`
    (cột có mực của ảnh dòng, rộng = `rect.width` điểm ảnh) thì mép từ được kéo về khe trắng thật gần nhất giữa hai
    từ và hai đầu dòng về mép mực — tô chọn / nhấp đúp trên bản scan trúng đúng chữ."""
    text = text.strip()
    if not text:
        return []
    n = len(text)
    w = rect.width
    spans = []  # (ký tự đầu, ký tự cuối) của từng từ
    i = 0
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        j = i
        while j < n and not text[j].isspace():
            j += 1
        spans.append((i, j))
        i = j
    edges = [[w * a / n, w * b / n] for a, b in spans]  # [trái, phải] tính từ rect.x0
    if ink is not None and len(ink) >= 2 and ink.any():
        cols = np.flatnonzero(ink)
        scale = len(ink) / max(1e-6, w)
        edges[0][0] = cols[0] / scale
        edges[-1][1] = (cols[-1] + 1) / scale
        h_px = rect.height * scale
        gaps = _ink_gaps(ink, max(2.0, 0.12 * h_px))
        tol = max(2.5 * len(ink) / n, 0.6 * h_px)
        used = -1
        for k in range(len(spans) - 1):
            want = (edges[k][1] + edges[k + 1][0]) / 2 * scale  # ranh giới ước lượng (cột)
            best, best_d = None, tol
            for g in range(used + 1, len(gaps)):
                d = abs((gaps[g][0] + gaps[g][1]) / 2 - want)
                if d <= best_d:
                    best, best_d = g, d
            if best is not None:
                used = best
                edges[k][1] = gaps[best][0] / scale
                edges[k + 1][0] = gaps[best][1] / scale
    out = []
    for (a, b), (x0, x1) in zip(spans, edges):
        x1 = max(x1, x0 + 0.5)
        out.append((fitz.Rect(rect.x0 + x0, rect.y0, rect.x0 + x1, rect.y1), text[a:b]))
    return out


def recognize_page(engine, region: ts.RegionImage, view_rotation: int = 0, clean_ink: bool = True) -> PageOcr:
    """Nhận dạng ảnh cả trang (gọi được ở luồng nền: chỉ numpy + ONNX Runtime qua `engine.ocr_image`)."""
    t0 = time.perf_counter()
    raw = [ln for ln in engine.ocr_image(region.rgb, region.zoom, clean_ink) if (ln.text or "").strip()]
    px_rects = [fitz.Rect(*(v * region.zoom for v in ln.bbox)) for ln in raw]
    gray = region.rgb.min(axis=2) if region.rgb.ndim == 3 else region.rgb
    out = PageOcr(region.page_index, int(view_rotation) % 360)
    for li, i in enumerate(ts.order_by_columns(px_rects)):
        text = normalize_vietnamese_text(raw[i].text).strip()
        r = px_rects[i]
        x0, y0 = max(0, int(round(r.x0))), max(0, int(round(r.y0)))
        x1, y1 = min(gray.shape[1], int(round(r.x1))), min(gray.shape[0], int(round(r.y1)))
        ink = column_ink(gray[y0:y1, x0:x1]) if x1 - x0 >= 2 and y1 - y0 >= 2 else None
        line_rect = fitz.Rect(x0, r.y0, x1, r.y1) if ink is not None else r
        for wi, (wr, word) in enumerate(split_line_words(text, line_rect, ink)):
            pr = region.rect_to_page(wr)
            out.words.append((pr.x0, pr.y0, pr.x1, pr.y1, word, 0, li, wi))
    # Dòng theo hệ của khung nhìn (pt, gốc trên-trái — trang hiển thị khi không xoay xem thêm) như
    # OcrEngine.ocr_page: bỏ lề trắng đã đệm, gốc vùng = gốc trang. Trang xoay xem thêm: `_TextLayer` đặt chữ theo
    # tổng góc /Rotate + góc xoay xem (`PageOcr.view_rotation` → `OcrPage.view_rotation`).
    off = region.margin / region.zoom
    for ln in raw:
        bx0, by0, bx1, by1 = ln.bbox
        out.lines.append(replace(ln, text=normalize_vietnamese_text(ln.text).strip(),
                                 bbox=(bx0 - off, by0 - off, bx1 - off, by1 - off),
                                 baseline=(ln.baseline - off) if ln.baseline else 0.0))
    out.seconds = time.perf_counter() - t0
    return out


# ─── Lưu đệm ───────────────────────────────────────────────────────────────


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _line_to_dict(ln) -> dict:
    return {"text": ln.text, "bbox": [round(v, 2) for v in ln.bbox], "size": round(ln.size, 2),
            "bold": bool(ln.bold), "italic": bool(ln.italic), "baseline": round(ln.baseline, 2)}


def _line_from_dict(d: dict):
    from qtpdfpro.core.ocr import OcrLine

    return OcrLine(str(d["text"]), tuple(float(v) for v in d["bbox"]), float(d.get("size", 0.0)),
                   bool(d.get("bold", False)), bool(d.get("italic", False)), float(d.get("baseline", 0.0)))


class OcrLayerCache:
    """`<thư mục dữ liệu>/ocr_cache/<sha256 tệp>.json` — chữ nhận dạng của từng trang."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else get_data_dir() / CACHE_DIR_NAME

    def path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def load(self, key: str) -> Dict[int, PageOcr]:
        try:
            data = json.loads(self.path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict) or data.get("format") != CACHE_FORMAT or data.get("bundle") != _bundle_version():
            return {}
        pages: Dict[int, PageOcr] = {}
        for k, p in (data.get("pages") or {}).items():
            try:
                words = [(float(w[0]), float(w[1]), float(w[2]), float(w[3]), str(w[4]), int(w[5]), int(w[6]), int(w[7]))
                         for w in p.get("words", [])]
                pages[int(k)] = PageOcr(int(k), int(p.get("rotation", 0)), words,
                                        [_line_from_dict(d) for d in p.get("lines", [])], float(p.get("seconds", 0.0)))
            except (KeyError, TypeError, ValueError, IndexError):
                continue
        try:
            os.utime(self.path(key))  # đánh dấu vừa dùng (dọn tệp cũ theo thời điểm sửa)
        except OSError:
            pass
        return pages

    def save(self, key: str, pages: Dict[int, PageOcr]) -> None:
        data = {
            "format": CACHE_FORMAT,
            "bundle": _bundle_version(),
            "pages": {
                str(i): {
                    "rotation": p.view_rotation,
                    "seconds": round(p.seconds, 2),
                    "words": [[round(w[0], 2), round(w[1], 2), round(w[2], 2), round(w[3], 2), w[4], w[5], w[6], w[7]]
                              for w in p.words],
                    "lines": [_line_to_dict(ln) for ln in p.lines],
                }
                for i, p in sorted(pages.items())
            },
        }
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.path(key)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
        self.prune()

    def prune(self, max_files: int = MAX_CACHE_FILES) -> None:
        try:
            files = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return
        for old in files[max_files:]:
            try:
                old.unlink()
            except OSError:
                pass


# ─── Dùng lại khi lưu PDF tìm kiếm được ────────────────────────────────────


class CachedOcrEngine:
    """Bộ máy cho `ocr.ocr_pdf` / `recognize_document`: trang đã nhận dạng khi xem (kể cả trang đang xoay xem — lớp
    chữ đặt theo đúng chiều người dùng đã đọc) lấy lại từ lớp chữ, trang khác mới nạp bộ máy thật để nhận dạng.
    Xuất Word (`keep_ink_images`) luôn nhận dạng lại theo chiều trang hiển thị."""

    def __init__(self, pages: Dict[int, PageOcr], factory: Optional[Callable[[], object]] = None) -> None:
        self.pages = dict(pages)
        self._factory = factory
        self._engine = None
        self.reused: List[int] = []

    def _real(self):
        if self._engine is None:
            if self._factory is not None:
                self._engine = self._factory()
            else:
                from qtpdfpro.core.ocr import OcrEngine

                self._engine = OcrEngine.load()
        return self._engine

    def ocr_page(self, page: fitz.Page, dpi: int = 0, clean_ink: bool = True, keep_ink_images: bool = False):
        hit = self.pages.get(page.number)
        if hit is not None and hit.lines and not keep_ink_images:
            from qtpdfpro.core.ocr import OcrPage

            self.reused.append(page.number)
            return OcrPage(page.number, page.rect.width, page.rect.height, [replace(ln) for ln in hit.lines],
                           view_rotation=hit.view_rotation)
        return self._real().ocr_page(page, dpi, clean_ink, keep_ink_images)

    def ocr_image(self, rgb, zoom: float = 1.0, clean_ink: bool = True):
        return self._real().ocr_image(rgb, zoom, clean_ink)


def page_layer(doc_path: str | Path, page: fitz.Page, engine=None, cache: Optional[OcrLayerCache] = None,
               view_rotation: int = 0) -> PageOcr:
    """Lớp chữ của một trang (dùng lưu đệm nếu có, không thì nhận dạng rồi lưu) — cho lệnh `cli text --layer`."""
    cache = cache or OcrLayerCache()
    key = file_sha256(doc_path)
    pages = cache.load(key)
    hit = pages.get(page.number)
    if hit is not None and hit.view_rotation == view_rotation:
        return hit
    if engine is None:
        from qtpdfpro.core.ocr import OcrEngine

        engine = OcrEngine.load()
    res = recognize_page(engine, prepare_page_image(page, view_rotation), view_rotation)
    pages[page.number] = res
    cache.save(key, pages)
    return res
