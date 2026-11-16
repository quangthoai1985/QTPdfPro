"""Lõi scan tài liệu (tích hợp từ quangthoai1985/PDFScanner): cấu hình, xử lý ảnh, xuất PDF/ảnh, phiên quét & mẫu giả lập.

Hoàn toàn không import `PySide6` để dùng chung cho giao diện GUI, dòng lệnh CLI và bộ kiểm thử `pytest`.
"""

from __future__ import annotations

import ctypes
import itertools
import json
import logging
import os
import shutil
import struct
import threading
import time
import uuid
import zlib
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np

from qtpdfpro import __app_name__, __version__
from qtpdfpro.core.settings import get_data_dir

log = logging.getLogger(__name__)


# ─── Hằng số, khổ giấy và mẫu có sẵn (presets) ───────────────────────────────


@dataclass(frozen=True)
class Preset:
    name: str
    scan_mode: str  # "gray" | "color"
    output: str  # "gray" | "bw" | "color"
    overrides: dict = field(default_factory=dict)
    description: str = ""


PRESETS: Tuple[Preset, ...] = (
    Preset(
        "Văn bản (xám)",
        "gray",
        "gray",
        {},
        "Nền trắng, chữ đen rõ, nét mềm. Hợp với đa số văn bản.",
    ),
    Preset(
        "Văn bản đen trắng (file nhỏ nhất)",
        "gray",
        "bw",
        {},
        "Chỉ đen và trắng, dung lượng nhỏ nhất. Hợp với văn bản chỉ có chữ.",
    ),
    Preset(
        "Có dấu đỏ / chữ ký màu",
        "color",
        "color",
        {},
        "Scan màu, tẩy nền về trắng nhưng giữ màu con dấu đỏ và chữ ký.",
    ),
    Preset(
        "Chữ mờ / giấy cũ",
        "gray",
        "gray",
        {"gamma": 1.6, "white_point": 0.84, "sharpen": 0.8},
        "Làm đậm chữ in mờ, tẩy mạnh nền giấy ố vàng.",
    ),
)

CUSTOM = "Tuỳ chỉnh"

PAPER_SIZES: Dict[str, Tuple[str, Optional[Tuple[float, float]]]] = {
    "full": ("Toàn mặt kính", None),
    "a4": ("A4 (210 × 297 mm)", (210.0, 297.0)),
    "letter": ("Letter (216 × 279 mm)", (215.9, 279.4)),
    "b5": ("B5 (176 × 250 mm)", (176.0, 250.0)),
    "a5": ("A5 dọc (148 × 210 mm)", (148.0, 210.0)),
    "a5l": ("A5 ngang (210 × 148 mm)", (210.0, 148.0)),
    "a6": ("A6 (105 × 148 mm)", (105.0, 148.0)),
    "card": ("Thẻ CCCD / thẻ ngân hàng (86 × 54 mm)", (85.6, 54.0)),
    "custom": ("Tuỳ chỉnh (kéo khung trên ảnh xem trước)", None),
}

SCAN_SOURCES: Tuple[Tuple[str, str], ...] = (
    ("auto", "Tự động (Mặt kính / ADF)"),
    ("flatbed", "Mặt kính (Flatbed)"),
    ("adf", "Khay nạp giấy (ADF)"),
)

DPI_CHOICES: Tuple[int, ...] = (150, 200, 300, 400, 600)
PREVIEW_DPI = 100
DEFAULT_BED_IN: Tuple[float, float] = (8.5, 11.7)
OUTPUT_KINDS = ("gray", "bw", "color")


def paper_area(
    key: str,
    origin: Tuple[float, float] = (0.0, 0.0),
    bed: Tuple[float, float] = DEFAULT_BED_IN,
) -> Tuple[float, float, float, float]:
    """Vùng scan `(x, y, w, h)` inch cho khổ giấy `key`, đặt tại `origin`, không vượt mặt kính."""
    size = PAPER_SIZES[key][1]
    if size is None:
        return (0.0, 0.0, bed[0], bed[1])
    w, h = min(size[0] / 25.4, bed[0]), min(size[1] / 25.4, bed[1])
    x = min(max(origin[0], 0.0), max(0.0, bed[0] - w))
    y = min(max(origin[1], 0.0), max(0.0, bed[1] - h))
    return (x, y, w, h)


# ─── Pipeline xử lý ảnh scan ─────────────────────────────────────────────────


@dataclass
class Settings:
    dpi: int = 300
    bg_floor: float = 0.5
    deskew: bool = True
    max_skew: float = 5.0
    sharpen: float = 0.5
    white_point: float = 0.88
    black_point: Optional[float] = None
    gamma: float = 1.2
    sauvola_k: float = 0.2
    bw_bg_guard: float = 0.85
    bw_ink_guard: Optional[float] = None
    despeckle_px: int = 2
    speck_max_mm: float = 1.0
    speck_isolation_mm: float = 1.5
    edge_margin_mm: float = 4.0

    def prepare_key(self) -> tuple:
        return (self.dpi, self.bg_floor, self.deskew, self.max_skew)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "Settings":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in names})


@dataclass
class Prepared:
    gray: np.ndarray
    color: Optional[np.ndarray]
    skew_angle: float


@dataclass
class Result:
    gray: np.ndarray
    bw: np.ndarray
    color: Optional[np.ndarray]
    skew_angle: float


def _to_u8(img: np.ndarray) -> np.ndarray:
    return np.clip(img + 0.5, 0, 255).astype(np.uint8)


def _odd(n: float) -> int:
    val = max(3, int(round(n)))
    return val if val % 2 else val + 1


def estimate_background(channel: np.ndarray, dpi: int) -> np.ndarray:
    """Ảnh nền giấy cùng kích thước, đã xoá chữ."""
    h, w = channel.shape
    scale = min(1.0, 50.0 / max(1, dpi))
    small = cv2.resize(
        channel,
        (max(1, round(w * scale)), max(1, round(h * scale))),
        interpolation=cv2.INTER_AREA,
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, kernel)
    bg = cv2.medianBlur(bg, 5)
    bg = cv2.GaussianBlur(bg, (0, 0), 2)
    return cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)


def normalize(channel: np.ndarray, bg: np.ndarray, floor_ratio: float) -> np.ndarray:
    """Chia ảnh cho nền để giấy thành 255. Trả về float32."""
    paper = float(np.percentile(bg, 90))
    bg_f = np.maximum(bg.astype(np.float32), max(paper * floor_ratio, 1.0))
    return np.clip(channel.astype(np.float32) * (255.0 / bg_f), 0, 255)


def estimate_skew(gray_u8: np.ndarray, dpi: int, max_angle: float) -> float:
    """Góc (độ) cần xoay để các dòng chữ nằm ngang."""
    scale = min(1.0, 100.0 / max(1, dpi))
    small = cv2.resize(gray_u8, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    _, ink = cv2.threshold(small, 0, 1, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if ink.sum() < 0.002 * ink.size:
        return 0.0
    h, w = ink.shape
    center = (w / 2, h / 2)
    ink_f = ink.astype(np.float32)

    def score(angle: float) -> float:
        m = cv2.getRotationMatrix2D(center, float(angle), 1.0)
        rows = cv2.warpAffine(ink_f, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=0).sum(axis=1)
        return float(np.dot(rows, rows))

    best = max(np.arange(-max_angle, max_angle + 1e-6, 0.5), key=score)
    best = max(np.arange(best - 0.5, best + 0.5 + 1e-6, 0.05), key=score)
    return float(best)


def rotate(img: np.ndarray, angle: float, border) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        img,
        m,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border,
    )


def unsharp(img: np.ndarray, amount: float, sigma: float) -> np.ndarray:
    if amount <= 0:
        return img
    blur = cv2.GaussianBlur(img, (0, 0), sigma)
    return img + amount * (img - blur)


def auto_black_point(gray: np.ndarray) -> float:
    ink = gray[gray < 160]
    if ink.size < 100:
        return 0.0
    return float(min(np.percentile(ink, 25), 100))


def levels_lut(black: float, white: float, gamma: float) -> np.ndarray:
    v = np.clip((np.arange(256, dtype=np.float32) - black) / max(white - black, 1.0), 0, 1)
    return _to_u8(255 * v ** gamma)


def sauvola_ink(
    gray: np.ndarray,
    dpi: int,
    k: float,
    bg_guard: float,
    ink_guard: Optional[float],
) -> np.ndarray:
    """Mặt nạ True = mực. Giữ chữ mờ, nét mảnh và mảng tô đặc (con dấu)."""
    if ink_guard is None:
        otsu, _ = cv2.threshold(_to_u8(gray), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        ink_guard = min(otsu, 0.6 * 255) / 255
    win = _odd(dpi / 10)
    mean = cv2.boxFilter(gray, cv2.CV_32F, (win, win), borderType=cv2.BORDER_REPLICATE)
    sq_mean = cv2.boxFilter(gray * gray, cv2.CV_32F, (win, win), borderType=cv2.BORDER_REPLICATE)
    std = np.sqrt(np.maximum(sq_mean - mean * mean, 0))
    thresh = mean * (1 + k * (std / 128.0 - 1))
    return ((gray < thresh) & (gray < bg_guard * 255)) | (gray <= ink_guard * 255)


def despeckle(ink: np.ndarray, max_area: int) -> np.ndarray:
    if max_area <= 0:
        return ink
    _, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    small = stats[:, cv2.CC_STAT_AREA] <= max_area
    small[0] = False
    return ink & ~small[labels]


def debris_mask(ink: np.ndarray, s: Settings) -> np.ndarray:
    """Mặt nạ chấm bụi cô lập và vệt tối sát mép ảnh (giữ nguyên dấu tiếng Việt gần chữ)."""
    px_per_mm = s.dpi / 25.4
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    x, y, w, h = (stats[:, i] for i in range(4))
    remove = np.zeros(n, bool)

    if s.speck_isolation_mm > 0:
        max_side = s.speck_max_mm * px_per_mm
        small = (w <= max_side) & (h <= max_side)
        small[0] = False
        content = ~small
        content[0] = False
        r = max(1, round(s.speck_isolation_mm * px_per_mm))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        near = cv2.dilate(content[labels].astype(np.uint8), kernel) > 0
        near_content = np.zeros(n, bool)
        near_content[labels[near]] = True
        remove |= small & ~near_content

    if s.edge_margin_mm > 0:
        band = s.edge_margin_mm * px_per_mm
        hgt, wid = ink.shape
        remove |= (
            ((x == 0) & (x + w <= band))
            | ((y == 0) & (y + h <= band))
            | ((x + w >= wid) & (x >= wid - band))
            | ((y + h >= hgt) & (y >= hgt - band))
        )

    remove[0] = False
    return remove[labels]


def prepare(raw: np.ndarray, s: Settings) -> Prepared:
    """Làm phẳng nền + chỉnh nghiêng. `raw`: ảnh xám 2 chiều hoặc BGR."""
    is_color = raw.ndim == 3
    gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY) if is_color else raw
    norm = normalize(gray, estimate_background(gray, s.dpi), s.bg_floor)

    angle = 0.0
    if s.deskew:
        angle = estimate_skew(_to_u8(norm), s.dpi, s.max_skew)
        if abs(angle) < 0.05:
            angle = 0.0
    if angle:
        norm = rotate(norm, angle, 255)

    color = None
    if is_color:
        chans = [normalize(c, estimate_background(c, s.dpi), s.bg_floor) for c in cv2.split(raw)]
        color = cv2.merge(chans)
        if angle:
            color = rotate(color, angle, (255, 255, 255))
        color = _to_u8(color)
    return Prepared(_to_u8(norm), color, angle)


def render(prep: Prepared, s: Settings, kind: str) -> np.ndarray:
    """Tạo ảnh kết quả: `'gray' | 'bw' | 'color'`."""
    norm = prep.gray.astype(np.float32)

    if kind == "bw":
        ink = sauvola_ink(norm, s.dpi, s.sauvola_k, s.bw_bg_guard, s.bw_ink_guard)
        ink = despeckle(ink, round(s.despeckle_px * (s.dpi / 300) ** 2))
        ink &= ~debris_mask(ink, s)
        return np.where(ink, 0, 255).astype(np.uint8)

    sigma = s.dpi / 300
    black = s.black_point * 255 if s.black_point is not None else auto_black_point(norm)
    lut = levels_lut(black, s.white_point * 255, s.gamma)
    gray_out = cv2.LUT(_to_u8(unsharp(norm, s.sharpen, sigma)), lut)

    debris = debris_mask(gray_out < 200, s)
    debris = cv2.dilate(debris.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0

    if kind == "color" and prep.color is not None:
        out = cv2.LUT(_to_u8(unsharp(prep.color.astype(np.float32), s.sharpen, sigma)), lut)
    else:
        out = gray_out
    out[debris] = 255
    return out


def process(raw: np.ndarray, s: Settings) -> Result:
    """Chạy toàn bộ pipeline xử lý ảnh, trả về cả 3 bản xám, đen trắng và màu."""
    prep = prepare(raw, s)
    color = render(prep, s, "color") if prep.color is not None else None
    return Result(render(prep, s, "gray"), render(prep, s, "bw"), color, prep.skew_angle)


# ─── Mô hình trang đang scan & bộ đệm LRU ───────────────────────────────────

MAX_CACHED_PAGES = 4
_ids = itertools.count(1)
_cache_lock = threading.Lock()
_cache_order: "OrderedDict[int, Page]" = OrderedDict()


@dataclass(eq=False)
class Page:
    raw: np.ndarray
    settings: Settings
    output: str = "gray"
    rotation: int = 0
    source: str = "scan"
    id: int = field(default_factory=lambda: next(_ids))

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._prepared: Optional[Prepared] = None
        self._prepared_key: Optional[tuple] = None

    @property
    def dpi(self) -> int:
        return self.settings.dpi

    @property
    def is_color(self) -> bool:
        return self.raw.ndim == 3

    def apply(self, settings: Settings, output: str) -> None:
        self.settings = replace(settings, dpi=self.dpi)
        self.output = output if (output != "color" or self.is_color) else "gray"

    def oriented_raw(self) -> np.ndarray:
        return (
            np.ascontiguousarray(np.rot90(self.raw, k=-(self.rotation // 90)))
            if self.rotation
            else self.raw
        )

    def rotate(self, degrees: int) -> None:
        self.rotation = (self.rotation + degrees) % 360
        self.drop_cache()

    def prepared(self, settings: Optional[Settings] = None) -> Prepared:
        s = settings or self.settings
        key = (s.prepare_key(), self.rotation)
        with self._lock:
            if self._prepared is None or self._prepared_key != key:
                self._prepared = prepare(self.oriented_raw(), s)
                self._prepared_key = key
        _touch(self)
        return self._prepared

    def render(self, settings: Optional[Settings] = None, output: Optional[str] = None) -> np.ndarray:
        s = settings or self.settings
        return render(self.prepared(s), s, output or self.output)

    def drop_cache(self) -> None:
        with self._lock:
            self._prepared = None
            self._prepared_key = None


def _touch(page: Page) -> None:
    with _cache_lock:
        _cache_order.pop(page.id, None)
        _cache_order[page.id] = page
        while len(_cache_order) > MAX_CACHED_PAGES:
            _, old = _cache_order.popitem(last=False)
            old.drop_cache()


# ─── Đọc/ghi ảnh an toàn đường dẫn tiếng Việt & Xuất PDF/Ảnh chuẩn DPI ───────

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")
IMAGE_FILTER = "Ảnh (" + " ".join(f"*{e}" for e in IMAGE_EXTS) + ")"
IMAGE_FORMATS = ("jpg", "png", "tif")
EXTENSIONS = {"pdf": ".pdf", "jpg": ".jpg", "png": ".png", "tif": ".tif"}


def _is_gray(img: np.ndarray) -> bool:
    small = img[::8, ::8].astype(np.int16)
    return (
        int(np.abs(small[..., 0] - small[..., 1]).max()) <= 2
        and int(np.abs(small[..., 1] - small[..., 2]).max()) <= 2
    )


def _read_explicit_dpi(raw_bytes: bytes) -> Optional[int]:
    """Đọc DPI thật từ header PNG (`pHYs`), JPEG (`JFIF APP0`) hoặc TIFF (Tag 282)."""
    # PNG pHYs
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        pos = 8
        while pos + 12 <= len(raw_bytes):
            length = struct.unpack_from(">I", raw_bytes, pos)[0]
            ctype = raw_bytes[pos + 4 : pos + 8]
            if ctype == b"pHYs" and length == 9 and pos + 21 <= len(raw_bytes):
                x_ppm, _y_ppm, unit = struct.unpack_from(">IIB", raw_bytes, pos + 8)
                if unit == 1 and x_ppm > 0:
                    return max(1, round(x_ppm * 0.0254))
                return None
            if ctype == b"IDAT" or ctype == b"IEND":
                break
            pos += 12 + length
        return None

    # JPEG JFIF APP0
    if raw_bytes.startswith(b"\xff\xd8"):
        pos = 2
        while pos + 4 <= len(raw_bytes):
            if raw_bytes[pos] != 0xFF:
                break
            marker = raw_bytes[pos + 1]
            if marker in (0xD8, 0xD9, 0x00) or (0xD0 <= marker <= 0xD7):
                pos += 2
                continue
            if marker == 0xDA:  # Start of Scan
                break
            seg_len = struct.unpack_from(">H", raw_bytes, pos + 2)[0]
            if marker == 0xE0 and seg_len >= 16 and raw_bytes[pos + 4 : pos + 9] == b"JFIF\x00":
                units = raw_bytes[pos + 11]
                xd, _yd = struct.unpack_from(">HH", raw_bytes, pos + 12)
                if units == 1 and xd > 0:
                    return int(xd)
                if units == 2 and xd > 0:
                    return max(1, round(xd * 2.54))
                return None
            pos += 2 + seg_len
        return None

    # TIFF: PyMuPDF đọc chuẩn tag XResolution
    if raw_bytes.startswith((b"II*\x00", b"MM\x00*")):
        try:
            pix = fitz.Pixmap(raw_bytes)
            if pix.xres > 0:
                return int(pix.xres)
        except Exception:
            pass
    return None


def imread(path: str | Path) -> Tuple[np.ndarray, Optional[int]]:
    """Đọc ảnh an toàn đường dẫn tiếng Việt → `(ảnh uint8 xám/BGR, dpi hoặc None)`."""
    raw_bytes = Path(path).read_bytes()
    arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Không đọc được ảnh: {path}")
    if img.dtype == np.uint16:
        img = (img >> 8).astype(np.uint8)
    if img.ndim == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    if img.ndim == 3 and _is_gray(img):
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dpi = _read_explicit_dpi(raw_bytes)
    return np.ascontiguousarray(img), dpi


def imwrite(path: str | Path, img: np.ndarray) -> None:
    p = Path(path)
    ok, buf = cv2.imencode(p.suffix, img)
    if not ok:
        raise ValueError(f"Không ghi được {p}")
    buf.tofile(str(p))


def _inject_jpeg_dpi(jpeg_bytes: bytes, dpi: int) -> bytes:
    jb = bytearray(jpeg_bytes)
    if len(jb) >= 18 and jb[0:2] == b"\xff\xd8" and jb[2:4] == b"\xff\xe0" and jb[6:10] == b"JFIF":
        jb[13] = 1  # DPI (dots per inch)
        struct.pack_into(">HH", jb, 14, int(dpi), int(dpi))
        return bytes(jb)
    # Chèn mới APP0 JFIF ngay sau SOI nếu thiếu
    app0 = bytearray(b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00\x00\x00\x00\x00\x00")
    struct.pack_into(">HH", app0, 13, int(dpi), int(dpi))
    return bytes(jb[:2] + app0 + jb[2:])


def _inject_png_dpi(png_bytes: bytes, dpi: int) -> bytes:
    if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n") or len(png_bytes) < 33:
        return png_bytes
    ppm = max(1, round(dpi / 0.0254))
    body = b"pHYs" + struct.pack(">IIB", ppm, ppm, 1)
    chunk = struct.pack(">I", 9) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    # IHDR dài 25 byte (kết thúc ở offset 33)
    return png_bytes[:33] + chunk + png_bytes[33:]


def encode_page(img: np.ndarray, kind: str, dpi: int, jpeg_quality: int = 82) -> bytes:
    """Mã hoá một trang thành bytes ảnh có nhúng DPI để dựng PDF (`bw` → PNG 1-bit, `gray/color` → JPEG)."""
    if kind == "bw":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        bw = np.where(gray < 128, 0, 255).astype(np.uint8)
        ok, buf = cv2.imencode(".png", bw, [cv2.IMWRITE_PNG_BILEVEL, 1])
        if not ok:
            raise ValueError("Không mã hoá được trang đen trắng.")
        return _inject_png_dpi(buf.tobytes(), dpi)

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)])
    if not ok:
        raise ValueError("Không mã hoá được trang JPEG.")
    return _inject_jpeg_dpi(buf.tobytes(), dpi)


def build_pdf_bytes(
    pages: Sequence[bytes],
    title: Optional[str] = None,
    dpis: Optional[Sequence[int]] = None,
) -> bytes:
    """Dựng tệp PDF chuẩn kích thước vật lý (pt theo DPI thật của từng ảnh) từ danh sách bytes `encode_page`."""
    doc = fitz.open()
    try:
        for idx, blob in enumerate(pages):
            pix = fitz.Pixmap(blob)
            dpi_x = float(dpis[idx]) if dpis and idx < len(dpis) else float(pix.xres or 300)
            dpi_y = float(dpis[idx]) if dpis and idx < len(dpis) else float(pix.yres or dpi_x or 300)
            dpi_x = max(36.0, dpi_x)
            dpi_y = max(36.0, dpi_y)
            w_pt = pix.width * 72.0 / dpi_x
            h_pt = pix.height * 72.0 / dpi_y
            page = doc.new_page(width=w_pt, height=h_pt)
            page.insert_image(page.rect, stream=blob)
        meta = {
            "creator": f"{__app_name__} {__version__}",
            "producer": f"{__app_name__} {__version__}",
        }
        if title:
            meta["title"] = str(title)
        doc.set_metadata(meta)
        return doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()


def save_pdf(
    path: str | Path,
    pages: Sequence[bytes],
    title: Optional[str] = None,
    dpis: Optional[Sequence[int]] = None,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = build_pdf_bytes(pages, title=title or target.stem, dpis=dpis)
    target.write_bytes(data)
    return target


def encode_image(img: np.ndarray, kind: str, dpi: int, fmt: str, jpeg_quality: int = 88) -> bytes:
    """Mã hoá một trang thành ảnh (`'jpg' | 'png' | 'tif'`) kèm DPI."""
    if kind == "bw":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        work = np.where(gray < 128, 0, 255).astype(np.uint8)
    else:
        work = img

    if fmt == "jpg":
        ok, buf = cv2.imencode(".jpg", work, [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)])
        if not ok:
            raise ValueError("Không mã hoá được ảnh JPG.")
        return _inject_jpeg_dpi(buf.tobytes(), dpi)

    if fmt == "png":
        params = [cv2.IMWRITE_PNG_BILEVEL, 1] if kind == "bw" else []
        ok, buf = cv2.imencode(".png", work, params)
        if not ok:
            raise ValueError("Không mã hoá được ảnh PNG.")
        return _inject_png_dpi(buf.tobytes(), dpi)

    if fmt == "tif":
        params = [
            cv2.IMWRITE_TIFF_COMPRESSION,
            5,  # LZW
            cv2.IMWRITE_TIFF_XDPI,
            int(dpi),
            cv2.IMWRITE_TIFF_YDPI,
            int(dpi),
        ]
        ok, buf = cv2.imencode(".tif", work, params)
        if not ok:
            raise ValueError("Không mã hoá được ảnh TIFF.")
        return buf.tobytes()

    raise ValueError(f"Định dạng ảnh không hỗ trợ: {fmt}")


def save_image(path: str | Path, img: np.ndarray, kind: str, dpi: int, fmt: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encode_image(img, kind, dpi, fmt))
    return target


# ─── Phiên scan nhiều trang lưu tạm trên đĩa (hỗ trợ khôi phục khi tắt đột ngột) ─

MANIFEST = "session.json"
PREFIX = "phien_"
VERSION = 1
_SESSION_LOCK = threading.Lock()
_ACTIVE_LOCKS: set[Path] = set()


def default_cache_dir() -> Path:
    return get_data_dir() / "scan_cache"


def _write_png(path: Path, img: np.ndarray) -> None:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise OSError(f"Không mã hoá được ảnh {path}")
    buf.tofile(str(path))


def _read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED) if data.size else None
    if img is None:
        raise ValueError(f"Ảnh tạm hỏng hoặc chưa ghi xong: {path}")
    return img


def _replace(src: Path, dst: Path, tries: int = 5) -> None:
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05 * (i + 1))


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if not handle:
            return ctypes.windll.kernel32.GetLastError() == 5
        try:
            code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok and code.value == 259)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _try_acquire_lock(folder: Path) -> Optional[Path]:
    lock_path = (folder / "lock.pid").resolve()
    with _SESSION_LOCK:
        if lock_path in _ACTIVE_LOCKS:
            return None
        if lock_path.exists():
            try:
                pid = int(lock_path.read_text(encoding="utf-8").strip())
                if pid != os.getpid() and _is_pid_alive(pid):
                    return None
            except Exception:
                pass
        lock_path.write_text(str(os.getpid()), encoding="utf-8")
        _ACTIVE_LOCKS.add(lock_path)
        return lock_path


def _release_lock(lock_path: Optional[Path]) -> None:
    if lock_path is None:
        return
    with _SESSION_LOCK:
        _ACTIVE_LOCKS.discard(lock_path)
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def _log_failure(future) -> None:
    if future.exception() is not None:
        log.warning("Không ghi được ảnh tạm: %s", future.exception())


class ScanSession:
    """Lưu tạm các trang chưa hoàn tất của tài liệu scan nhiều trang."""

    def __init__(
        self,
        folder: Path,
        lock_path: Path,
        entries: Optional[list] = None,
        created: Optional[datetime] = None,
    ) -> None:
        self.folder = Path(folder)
        self.created = created or datetime.now()
        self._lock_path: Optional[Path] = lock_path
        self._entries = entries or []
        self._files: Dict[int, str] = {}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qtpdfpro-scan-cache")
        self._pending: list = []

    @classmethod
    def create(cls, cache_dir: Optional[Path] = None) -> "ScanSession":
        base = Path(cache_dir) if cache_dir else default_cache_dir()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = base / f"{PREFIX}{stamp}_{os.getpid()}"
        i = 2
        while folder.exists():
            folder = base / f"{PREFIX}{stamp}_{os.getpid()}_{i}"
            i += 1
        folder.mkdir(parents=True)
        lock_path = _try_acquire_lock(folder)
        if lock_path is None:
            raise OSError(f"Không khoá được thư mục tạm {folder}")
        session = cls(folder, lock_path)
        session.update([])
        return session

    @classmethod
    def open(cls, folder: str | Path) -> Optional["ScanSession"]:
        folder_p = Path(folder)
        lock_path = _try_acquire_lock(folder_p)
        if lock_path is None:
            return None
        try:
            data = json.loads((folder_p / MANIFEST).read_text(encoding="utf-8"))
            entries = [e for e in data.get("pages", []) if (folder_p / e["file"]).exists()]
            created = datetime.fromisoformat(data["created"]) if data.get("created") else None
        except Exception as exc:
            log.info("Bỏ thư mục tạm không dùng được %s: %s", folder_p, exc)
            _release_lock(lock_path)
            shutil.rmtree(folder_p, ignore_errors=True)
            return None
        return cls(folder_p, lock_path, entries, created)

    def page_count(self) -> int:
        return len(self._files) or len(self._entries)

    def load_pages(self) -> List[Page]:
        pages: List[Page] = []
        for e in self._entries:
            try:
                raw = _read_image(self.folder / e["file"])
                page = Page(
                    raw,
                    Settings.from_dict(e.get("settings")),
                    output=e.get("output", "gray"),
                    rotation=int(e.get("rotation", 0)) % 360,
                    source=e.get("source", "scan"),
                )
            except Exception as ex:
                log.warning("Bỏ qua trang tạm %s: %s", e.get("file"), ex)
                continue
            self._files[page.id] = e["file"]
            pages.append(page)
        self._entries = []
        return pages

    def add(self, page: Page) -> None:
        name = f"{uuid.uuid4().hex[:12]}.png"
        self._files[page.id] = name
        self._pending = [f for f in self._pending if not f.done()]
        future = self._pool.submit(_write_png, self.folder / name, page.raw)
        future.add_done_callback(_log_failure)
        self._pending.append(future)

    def remove(self, page: Page) -> None:
        name = self._files.pop(page.id, None)
        if name:
            self.flush()
            try:
                (self.folder / name).unlink(missing_ok=True)
            except OSError as exc:
                log.warning("Không xoá được ảnh tạm %s: %s", name, exc)

    def update(self, pages: Sequence[Page]) -> None:
        data = {
            "version": VERSION,
            "app": f"{__app_name__} {__version__}",
            "created": self.created.isoformat(),
            "pages": [
                {
                    "file": self._files[p.id],
                    "settings": p.settings.to_dict(),
                    "output": p.output,
                    "rotation": p.rotation,
                    "source": p.source,
                }
                for p in pages
                if p.id in self._files
            ],
        }
        tmp = self.folder / (MANIFEST + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        _replace(tmp, self.folder / MANIFEST)

    def flush(self) -> None:
        for f in self._pending:
            try:
                f.result()
            except Exception:
                pass
        self._pending = []

    def release(self) -> None:
        self.flush()
        self._pool.shutdown(wait=True)
        _release_lock(self._lock_path)
        self._lock_path = None

    def discard(self) -> None:
        self.flush()
        self._pool.shutdown(wait=True)
        try:
            (self.folder / MANIFEST).unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Không xoá được %s: %s", self.folder / MANIFEST, exc)
        _release_lock(self._lock_path)
        self._lock_path = None
        shutil.rmtree(self.folder, ignore_errors=True)


def find_orphan_sessions(cache_dir: Optional[Path] = None) -> List[Path]:
    base = Path(cache_dir) if cache_dir else default_cache_dir()
    if not base.is_dir():
        return []
    return sorted(
        (d for d in base.iterdir() if d.is_dir() and d.name.startswith(PREFIX)),
        key=lambda d: d.name,
        reverse=True,
    )


# ─── Trang văn bản giả lập để kiểm thử không cần máy scan thật ────────────────

DIACRITICS_LINE = "Những chữ nhỏ: ặ ẫ ỡ ự ỹ ị ọ ụ ạ ệ ộ ợ - kiểm tra dấu nặng và dấu mũ."
BODY = [
    "Căn cứ Nghị định số 30/2020/NĐ-CP ngày 05 tháng 3 năm 2020 của Chính phủ",
    "về công tác văn thư; xét đề nghị của Trưởng phòng Tổ chức - Hành chính,",
    "Điều 1. Ban hành kèm theo Quyết định này Quy chế quản lý hồ sơ, tài liệu.",
    "Điều 2. Quyết định có hiệu lực kể từ ngày ký. Các ông (bà) Trưởng phòng,",
    "Thủ trưởng các đơn vị trực thuộc chịu trách nhiệm thi hành Quyết định này.",
    DIACRITICS_LINE,
]
STAMP_CENTER = (1800, 3000)


def _pick_font(names: Sequence[str]) -> Optional[str]:
    font_dir = Path("C:/Windows/Fonts")
    for name in names:
        p = font_dir / name
        if p.exists():
            return str(p)
    return None


def clean_page(width: int = 2480, height: int = 3508) -> np.ndarray:
    """Trang sạch (RGB uint8) vẽ bằng PyMuPDF, có chữ tiếng Việt nhiều dấu và con dấu đỏ."""
    scale = 300.0 / 72.0
    w_pt, h_pt = width / scale, height / scale
    doc = fitz.open()
    try:
        page = doc.new_page(width=w_pt, height=h_pt)
        bold_font = _pick_font(["timesbd.ttf", "arialbd.ttf"])
        reg_font = _pick_font(["times.ttf", "arial.ttf"])
        bname = "tbold" if bold_font else "helv"
        rname = "treg" if reg_font else "helv"
        if bold_font:
            page.insert_font(fontname=bname, fontfile=bold_font)
        if reg_font:
            page.insert_font(fontname=rname, fontfile=reg_font)

        t1 = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
        t2 = "Độc lập - Tự do - Hạnh phúc"
        page.insert_text((w_pt * 0.14, 250 / scale), t1, fontname=bname, fontsize=56 / scale, color=(0, 0, 0))
        page.insert_text((w_pt * 0.28, 330 / scale), t2, fontname=rname, fontsize=42 / scale, color=(0, 0, 0))

        y = 600.0
        for _ in range(4):
            for line in BODY:
                page.insert_text((250 / scale, y / scale), line, fontname=rname, fontsize=42 / scale, color=(0, 0, 0))
                y += 70.0
            y += 40.0

        cx, cy = STAMP_CENTER[0] / scale, STAMP_CENTER[1] / scale
        red = (200 / 255.0, 30 / 255.0, 40 / 255.0)
        page.draw_circle((cx, cy), 200 / scale, color=red, width=10 / scale)
        page.draw_circle((cx, cy), 150 / scale, color=red, width=5 / scale)
        star_pts = [
            (
                cx + (r / scale) * float(np.cos(a)),
                cy - (r / scale) * float(np.sin(a)),
            )
            for i, a in enumerate(np.linspace(np.pi / 2, np.pi / 2 + 4 * np.pi, 10, endpoint=False))
            for r in [70 if i % 2 == 0 else 28]
        ]
        page.draw_polyline(star_pts + [star_pts[0]], color=red, fill=red, closePath=True, width=1.0)
        sig_pts = [(x / scale, y_s / scale) for x, y_s in ((1550, 2950), (1700, 2880), (1800, 3050), (1950, 2900))]
        page.draw_polyline(sig_pts, color=(30 / 255.0, 50 / 255.0, 170 / 255.0), width=6 / scale)

        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        if arr.shape[0] != height or arr.shape[1] != width:
            arr = cv2.resize(arr, (width, height), interpolation=cv2.INTER_AREA)
        return np.ascontiguousarray(arr)
    finally:
        doc.close()


def degraded_page(angle: float = 1.5, color: bool = True, seed: int = 1) -> np.ndarray:
    """Trang giả lập đã scan: BGR (`color=True`) hoặc xám, nghiêng `angle` độ."""
    clean = clean_page().astype(np.float32)
    h, w = clean.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    light = 0.80 + 0.12 * (xx / w) + 0.05 * np.sin(yy / h * 3.1)
    light *= 1 - 0.45 * np.exp(-xx / 180)
    paper = np.array([0.97, 0.92, 0.78], np.float32)
    ink = clean.mean(axis=2, keepdims=True) < 128
    img = clean * light[..., None] * paper + 35 * ink
    img = cv2.GaussianBlur(img, (0, 0), 1.1)
    img += np.random.default_rng(seed).normal(0, 4, img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    img = cv2.warpAffine(img, m, (w, h), borderValue=(215, 225, 230))
    return img if color else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
