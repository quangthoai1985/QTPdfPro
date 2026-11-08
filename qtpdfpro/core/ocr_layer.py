"""Lớp chữ nhận dạng tạm cho trang ảnh quét (Đợt 2 của công cụ «Chọn chữ») — không phụ thuộc Qt.

- `prepare_page_image` (luồng giao diện — dùng PyMuPDF) kết xuất cả trang đúng chiều đang xem;
  `recognize_page` (luồng nền — chỉ numpy + ONNX Runtime) nhận dạng thành `PageOcr`:
  * `words`: từ theo thứ tự đọc (cắt XY: hai cột → hết cột trái rồi cột phải), toạ độ **trang chưa xoay**, cùng
    dạng tuple với `text_select.page_words` → công cụ Chọn dùng như chữ thật (kéo theo dòng, nhấp đúp, Ctrl+A).
    Khung từng từ ước lượng theo tỷ lệ số ký tự trong dòng.
  * `lines`: `OcrLine` theo toạ độ trang hiển thị như `OcrEngine.ocr_page` (chỉ khi không xoay xem thêm) → dùng
    lại khi lưu PDF tìm kiếm được (`CachedOcrEngine` cho `ocr.ocr_pdf`), không phải nhận dạng lại.
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
    lines: list = field(default_factory=list)  # List[ocr.OcrLine] — hệ trang hiển thị (pt); [] nếu xoay xem thêm
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


def split_line_words(text: str, rect: fitz.Rect) -> List[tuple]:
    """Chia một dòng chữ nhận dạng thành từ; khung từng từ theo tỷ lệ vị trí ký tự trong dòng."""
    text = text.strip()
    if not text:
        return []
    n = len(text)
    w = rect.width
    out = []
    i = 0
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        j = i
        while j < n and not text[j].isspace():
            j += 1
        out.append((fitz.Rect(rect.x0 + w * i / n, rect.y0, rect.x0 + w * j / n, rect.y1), text[i:j]))
        i = j
    return out


def recognize_page(engine, region: ts.RegionImage, view_rotation: int = 0, clean_ink: bool = True) -> PageOcr:
    """Nhận dạng ảnh cả trang (gọi được ở luồng nền: chỉ numpy + ONNX Runtime qua `engine.ocr_image`)."""
    t0 = time.perf_counter()
    raw = [ln for ln in engine.ocr_image(region.rgb, region.zoom, clean_ink) if (ln.text or "").strip()]
    px_rects = [fitz.Rect(*(v * region.zoom for v in ln.bbox)) for ln in raw]
    out = PageOcr(region.page_index, int(view_rotation) % 360)
    for li, i in enumerate(ts.order_by_columns(px_rects)):
        text = normalize_vietnamese_text(raw[i].text).strip()
        for wi, (wr, word) in enumerate(split_line_words(text, px_rects[i])):
            pr = region.rect_to_page(wr)
            out.words.append((pr.x0, pr.y0, pr.x1, pr.y1, word, 0, li, wi))
    if out.view_rotation == 0:
        # hệ trang hiển thị (pt) như OcrEngine.ocr_page: bỏ lề trắng đã đệm, gốc vùng = gốc trang
        off = region.margin / region.zoom
        for ln in raw:
            x0, y0, x1, y1 = ln.bbox
            out.lines.append(replace(ln, text=normalize_vietnamese_text(ln.text).strip(),
                                     bbox=(x0 - off, y0 - off, x1 - off, y1 - off),
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
    """Bộ máy cho `ocr.ocr_pdf` / `recognize_document`: trang đã nhận dạng (không xoay xem thêm) lấy lại từ lớp chữ,
    trang khác mới nạp bộ máy thật (lần đầu cần) để nhận dạng."""

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
        if hit is not None and hit.lines and hit.view_rotation == 0 and not keep_ink_images:
            from qtpdfpro.core.ocr import OcrPage

            self.reused.append(page.number)
            return OcrPage(page.number, page.rect.width, page.rect.height, [replace(ln) for ln in hit.lines])
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
