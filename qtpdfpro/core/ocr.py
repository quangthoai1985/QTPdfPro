"""OCR tiếng Việt cho PDF ảnh quét (mục B3) — không phụ thuộc PySide6, chỉ ONNX Runtime + OpenCV + numpy.

Dây chuyền chốt bằng thử nghiệm trên bản scan thật (2026-10-23, `docs/DE_XUAT_TINH_NANG.md` «Giai đoạn 2»):

1. Kết xuất trang ở `dpi` **gồm cả lớp chữ sẵn có** — số hiệu / ngày do phần mềm cấp số chèn sau khi scan
   không có trong ảnh nhúng. Trang đã có chữ thật (≥ `TEXT_PAGE_CHARS` ký tự) thì bỏ qua.
2. `remove_color_ink`: xoá nét đỏ (con dấu) và xanh (chữ ký), giữ chữ đen nằm dưới con dấu.
3. `TextDetector`: PP-OCRv6 det small (ONNX) tìm dòng chữ; hậu xử lý DB viết lại bằng OpenCV (nới khung chữ
   nhật theo khoảng cách `diện tích × unclip_ratio / chu vi` — đúng như pyclipper rồi minAreaRect).
4. `TextRecognizer`: cắt dòng dài > 14:1 tại cột ít mực nhất (`split_long_line` — VietOCR huấn luyện tới 512×32),
   VietOCR vgg_seq2seq (ONNX: bộ mã hoá ảnh + một bước giải mã GRU) giải mã tham lam bằng numpy.
5. Kết quả `OcrPage` (dòng có toạ độ trang hiển thị, cỡ chữ, đậm / nghiêng ước lượng từ nét chữ) →
   `ocr_pdf()` ghi PDF tìm kiếm được (lớp chữ ẩn Times New Roman nhúng tập con, dấu cách chép ra U+0020) hoặc
   văn bản `.txt`; `ocr_to_docx()` dựng lại trang chỉ có chữ thật + ảnh con dấu / chữ ký rồi chuyển bằng
   `converter.convert_pdf_to_docx` (văn bản hành chính tự đi đường NĐ30).

Mô hình tải lần đầu qua `core/ocr_models.py` (không nằm trong bộ cài).
"""

from __future__ import annotations

import math
import tempfile
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF
import numpy as np

from qtpdfpro.core import ocr_models
from qtpdfpro.core.annotations import _FONT_FILES, system_font_dir
from qtpdfpro.core.ocr_models import ModelBundle, OcrModelError
from qtpdfpro.core.page_ops import parse_page_selection, save_pdf
from qtpdfpro.core.page_stamp import shrink_font_tables
from qtpdfpro.core.pdf_io import PathLike, PdfToolError, default_output, open_pdf, same_file

DEFAULT_DPI = 0  # 0 = tự chọn theo độ phân giải ảnh quét của trang, kẹp trong [MIN_DPI, MAX_DPI]
MIN_DPI, MAX_DPI = 200, 300
TEXT_PAGE_CHARS = 100  # trang có từ chừng này ký tự chữ thật trở lên coi là đã có lớp chữ
SPLIT_RATIO = 14.0  # VietOCR: ảnh cao 32, rộng tối đa 512 (16:1) — cắt sớm hơn một chút
LINE_PAD_X, LINE_PAD_Y = 0.020, 0.015  # lề cắt quanh khung dòng, theo inch (4 px / 3 px ở 200 dpi)
# Cỡ chữ (pt) ≈ chiều cao khung dòng (pt) × hệ số — đo trên văn bản hành chính Times New Roman 14 pt
SIZE_PER_BOX_HEIGHT = 0.75
SIZE_SNAP = 0.25  # cỡ ước lượng lệch ≤ 25% so với trung vị trang → cỡ thân bài (chiều cao khung dao động theo dấu / nét xuống)
COLUMN_GAP = 0.9  # khoảng trống trong khung dòng ≥ 0,9 × chiều cao khung (cách từ ~0,2–0,5) → tách thành hai cột
BOLD_STROKE_RATIO = 1.22  # nét dày hơn trung vị trang chừng này lần → chữ đậm
ITALIC_SHEAR = 0.21  # tan(~12°): độ nghiêng của chữ nghiêng Times New Roman
ITALIC_GAIN = 1.06  # độ sắc của hình chiếu cột tăng chừng này khi «dựng thẳng» → chữ nghiêng

ProgressCallback = Optional[Callable[[int, int, str], None]]
CancelCheck = Optional[Callable[[], bool]]


class OcrError(PdfToolError):
    """Lỗi OCR (thông điệp tiếng Việt hiển thị được cho người dùng)."""


class OcrCancelled(OcrError):
    """Người dùng dừng giữa chừng."""


class OcrModelsMissing(OcrError):
    """Chưa cài bộ mô hình OCR (giao diện sẽ tải ngầm; dòng lệnh: `ocr --install`)."""


# ─── Kết quả ───────────────────────────────────────────────────────────────


@dataclass
class OcrLine:
    """Một dòng chữ đọc được; `bbox` theo trang ĐANG HIỂN THỊ (pt, gốc trên-trái)."""

    text: str
    bbox: Tuple[float, float, float, float]
    size: float = 0.0  # cỡ chữ ước lượng (pt)
    bold: bool = False
    italic: bool = False
    baseline: float = 0.0  # chân chữ (pt, trang hiển thị); 0 = chưa đo → lấy 78% chiều cao khung

    @property
    def base_y(self) -> float:
        return self.baseline or self.bbox[1] + (self.bbox[3] - self.bbox[1]) * 0.78


@dataclass
class OcrPage:
    number: int  # chỉ số trang 0-based
    width: float  # khổ trang đang hiển thị (pt)
    height: float
    lines: List[OcrLine] = field(default_factory=list)
    skipped: bool = False  # trang đã có lớp chữ → không OCR
    seconds: float = 0.0
    ink_images: List[Tuple[Tuple[float, float, float, float], bytes]] = field(default_factory=list)  # con dấu, chữ ký

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass
class OcrResult:
    input_path: str
    output_path: str
    output_kind: str  # "pdf" | "txt" | "docx"
    pages_total: int
    pages_ocr: int
    pages_skipped: int
    lines: int
    chars: int
    seconds: float
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Tiền xử lý ảnh ────────────────────────────────────────────────────────


def _cv2():
    import cv2  # noqa: PLC0415 - OpenCV đã có trong requirements (dùng chung với fill_sign)

    return cv2


def color_ink_mask(rgb: np.ndarray) -> np.ndarray:
    """Mặt nạ nét đỏ (con dấu) / xanh (chữ ký), nới 1 px; không gồm điểm tối trung tính (chữ in dưới con dấu)."""
    cv2 = _cv2()
    a = rgb.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mask = ((r - np.maximum(g, b)) > 50) | (((b - np.maximum(r, g)) > 35) & (b > 80))
    mask = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    spread = a.max(axis=2) - a.min(axis=2)
    return mask & ~((a.mean(axis=2) < 110) & (spread < 40))


def remove_color_ink(rgb: np.ndarray) -> np.ndarray:
    """Bản sao ảnh RGB đã tô trắng nét đỏ / xanh. Đừng lọc theo độ bão hoà HSV: nhiễu màu JPEG quanh chữ đen
    sẽ bị xoá theo, chữ mòn."""
    out = rgb.copy()
    out[color_ink_mask(rgb)] = 255
    return out


def split_long_line(gray: np.ndarray, max_ratio: float = SPLIT_RATIO) -> List[Tuple[np.ndarray, str]]:
    """Cắt ảnh dòng (xám) có tỷ lệ > `max_ratio` thành các đoạn → [(đoạn, chuỗi nối với đoạn trước)].

    Ưu tiên cắt giữa khoảng trắng rộng nhất gần điểm chia (nối bằng dấu cách); không có khoảng trắng thì cắt
    ở cột ít mực nhất và nối liền (tránh «2008» → «200 8»)."""
    h, w = gray.shape[:2]
    if h == 0 or w / h <= max_ratio:
        return [(gray, "")]
    k = math.ceil(w / h / max_ratio)
    ink = (gray < 140).sum(axis=0)
    smooth = np.convolve(ink.astype(float), np.ones(7), "same")
    cuts, joins = [0], [""]
    for i in range(1, k):
        target = int(w * i / k)
        lo, hi = max(cuts[-1] + h, target - 2 * h), min(w - h, target + 2 * h)
        if hi <= lo:
            cuts.append(target)
            joins.append("")
            continue
        best, x = None, lo
        while x < hi:  # các đoạn cột không có mực trong cửa sổ
            if ink[x] == 0:
                end = x
                while end < hi and ink[end] == 0:
                    end += 1
                run = (end - x, -abs((x + end) // 2 - target), (x + end) // 2)
                best = max(best, run) if best else run
                x = end
            else:
                x += 1
        if best is not None and best[0] >= max(2, int(0.15 * h)):
            cuts.append(best[2])
            joins.append(" ")
        else:
            cuts.append(lo + int(np.argmin(smooth[lo:hi])))
            joins.append("")
    cuts.append(w)
    return [(gray[:, a:b], j) for a, b, j in zip(cuts, cuts[1:], joins) if b > a]


def has_leading_dash(gray: np.ndarray) -> bool:
    """Dòng mở đầu bằng gạch đầu dòng «-» (nét ngang mảnh ở giữa chiều cao, tách khỏi chữ sau) — VietOCR hay bỏ
    sót ký tự này ở dòng ngắn (danh sách «Nơi nhận»)."""
    cv2 = _cv2()
    h = gray.shape[0]
    if h < 8 or gray.size == 0:
        return False
    _t, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    n, _lab, stats, _c = cv2.connectedComponentsWithStats(ink, connectivity=8)
    comps = sorted((s for s in stats[1:] if s[4] >= 3), key=lambda s: s[0])
    if len(comps) < 2:
        return False
    x, y, w, ch, _area = comps[0]
    mid = (y + ch / 2) / h
    gap = comps[1][0] - (x + w)
    # ở 200 dpi gạch «-» cỡ 13 pt chỉ ~8 × 3–4 px trong dòng cao ~50 px
    return ch <= 0.12 * h and w >= 1.6 * ch and w <= 0.5 * h and 0.35 <= mid <= 0.75 and gap >= 0.08 * h


def prepare_line_image(gray: np.ndarray, height: int = 32, min_width: int = 32, max_width: int = 512) -> np.ndarray:
    """Ảnh dòng → tensor `(1, 3, 32, W)` float32 0..1 như `vietocr.tool.translate.process_image`
    (rộng làm tròn lên bội 10, kẹp 32–512)."""
    cv2 = _cv2()
    h, w = gray.shape[:2]
    new_w = int(height * w / max(1, h))
    new_w = max(min_width, min(max_width, math.ceil(new_w / 10) * 10))
    interp = cv2.INTER_AREA if h > height else cv2.INTER_CUBIC
    img = cv2.resize(gray, (new_w, height), interpolation=interp).astype(np.float32) / 255.0
    return np.repeat(img[None, None, :, :], 3, axis=1)


# ─── Tìm dòng: PP-OCRv6 det + hậu xử lý DB ─────────────────────────────────


def _box_score(pred: np.ndarray, pts: np.ndarray) -> float:
    cv2 = _cv2()
    h, w = pred.shape
    xmin = int(np.clip(np.floor(pts[:, 0].min()), 0, w - 1))
    xmax = int(np.clip(np.ceil(pts[:, 0].max()), 0, w - 1))
    ymin = int(np.clip(np.floor(pts[:, 1].min()), 0, h - 1))
    ymax = int(np.clip(np.ceil(pts[:, 1].max()), 0, h - 1))
    mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
    shifted = (pts - [xmin, ymin]).reshape(1, -1, 2).astype(np.int32)
    cv2.fillPoly(mask, shifted, 1)
    return float(cv2.mean(pred[ymin:ymax + 1, xmin:xmax + 1], mask)[0])


def db_boxes(pred: np.ndarray, dest_h: int, dest_w: int, thresh: float = 0.3, box_thresh: float = 0.5,
             unclip_ratio: float = 1.6, max_candidates: int = 1000) -> List[np.ndarray]:
    """Bản đồ xác suất `pred` (H×W) → các khung 4 đỉnh (trên-trái, trên-phải, dưới-phải, dưới-trái) theo ảnh
    `dest_h × dest_w`. Giống `DBPostProcess` của PaddleOCR / RapidOCR (dilation 2×2, score «fast»)."""
    cv2 = _cv2()
    h, w = pred.shape
    bitmap = cv2.dilate((pred > thresh).astype(np.uint8), np.ones((2, 2), np.uint8))
    contours, _ = cv2.findContours(bitmap * 255, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    boxes: List[np.ndarray] = []
    for contour in contours[:max_candidates]:
        (cx, cy), (rw, rh), angle = cv2.minAreaRect(contour)
        if min(rw, rh) < 3:
            continue
        if _box_score(pred, cv2.boxPoints(((cx, cy), (rw, rh), angle))) < box_thresh:
            continue
        # nới khung chữ nhật: pyclipper.offset(d) rồi minAreaRect cho đúng (w + 2d) × (h + 2d)
        d = rw * rh * unclip_ratio / (2.0 * (rw + rh))
        rw, rh = rw + 2 * d, rh + 2 * d
        if min(rw, rh) < 5:
            continue
        pts = cv2.boxPoints(((cx, cy), (rw, rh), angle))
        pts[:, 0] = np.clip(np.round(pts[:, 0] / w * dest_w), 0, dest_w - 1)
        pts[:, 1] = np.clip(np.round(pts[:, 1] / h * dest_h), 0, dest_h - 1)
        xs = pts[np.argsort(pts[:, 0])]
        left, right = xs[:2][np.argsort(xs[:2, 1])], xs[2:][np.argsort(xs[2:, 1])]
        box = np.array([left[0], right[0], right[1], left[1]], dtype=np.float32)
        if np.linalg.norm(box[0] - box[1]) <= 3 or np.linalg.norm(box[0] - box[3]) <= 3:
            continue
        boxes.append(box)
    return boxes


class TextDetector:
    def __init__(self, session, cfg: dict) -> None:
        self.session = session
        self.input_name = session.get_inputs()[0].name
        self.max_side = int(cfg.get("max_side_len", 2000))
        self.limit_side = int(cfg.get("limit_side_len", 736))
        self.mean = np.array(cfg.get("mean", [0.5, 0.5, 0.5]), dtype=np.float32)
        self.std = np.array(cfg.get("std", [0.5, 0.5, 0.5]), dtype=np.float32)
        self.thresh = float(cfg.get("thresh", 0.3))
        self.box_thresh = float(cfg.get("box_thresh", 0.5))
        self.unclip_ratio = float(cfg.get("unclip_ratio", 1.6))
        self.max_candidates = int(cfg.get("max_candidates", 1000))

    def __call__(self, bgr: np.ndarray) -> List[np.ndarray]:
        """Ảnh BGR uint8 → khung dòng chữ theo toạ độ ảnh đó."""
        cv2 = _cv2()
        h0, w0 = bgr.shape[:2]
        scale = min(1.0, self.max_side / max(h0, w0))  # RapidOCR: thu cạnh dài về ≤ 2000 px trước
        img = cv2.resize(bgr, (int(w0 * scale), int(h0 * scale))) if scale < 1.0 else bgr
        h, w = img.shape[:2]
        ratio = self.limit_side / min(h, w) if min(h, w) < self.limit_side else 1.0
        rh = max(32, int(round(int(h * ratio) / 32) * 32))
        rw = max(32, int(round(int(w * ratio) / 32) * 32))
        x = (cv2.resize(img, (rw, rh)).astype(np.float32) / 255.0 - self.mean) / self.std
        pred = self.session.run(None, {self.input_name: x.transpose(2, 0, 1)[None].astype(np.float32)})[0]
        boxes = db_boxes(pred[0, 0], h, w, self.thresh, self.box_thresh, self.unclip_ratio, self.max_candidates)
        return [b / scale for b in boxes]


# ─── Đọc chữ: VietOCR seq2seq ──────────────────────────────────────────────


class Vocab:
    """Bảng ký tự VietOCR: chỉ số = vị trí + 4 (0 pad, 1 bắt đầu, 2 kết thúc, 3 mask)."""

    SOS, EOS = 1, 2

    def __init__(self, chars: str) -> None:
        self.i2c = {i + 4: c for i, c in enumerate(chars)}

    def decode(self, ids: Sequence[int]) -> str:
        ids = list(ids)
        first = 1 if ids[:1] == [self.SOS] else 0
        last = ids.index(self.EOS) if self.EOS in ids else len(ids)
        return "".join(self.i2c.get(i, "") for i in ids[first:last])


class TextRecognizer:
    def __init__(self, encoder, decoder, vocab: Vocab, cfg: dict) -> None:
        self.encoder, self.decoder, self.vocab = encoder, decoder, vocab
        self.height = int(cfg.get("image_height", 32))
        self.min_width = int(cfg.get("image_min_width", 32))
        self.max_width = int(cfg.get("image_max_width", 512))
        self.max_length = int(cfg.get("max_length", 128))

    def read_segment(self, gray: np.ndarray) -> str:
        x = prepare_line_image(gray, self.height, self.min_width, self.max_width)
        hidden, enc_out = self.encoder.run(None, {"img": x})
        tokens = [Vocab.SOS]
        for _ in range(self.max_length):
            logits, hidden = self.decoder.run(
                None, {"token": np.array([tokens[-1]], dtype=np.int64), "hidden": hidden, "enc_out": enc_out}
            )
            tokens.append(int(np.argmax(logits[0])))
            if tokens[-1] == Vocab.EOS:
                break
        return self.vocab.decode(tokens)

    def __call__(self, gray: np.ndarray) -> str:
        text = ""
        for seg, join in split_long_line(gray):
            part = self.read_segment(seg).strip()
            if part:
                text = f"{text}{join}{part}" if text else part
        text = fix_stray_caps(text)
        if text and text[0] not in "-–—•" and has_leading_dash(gray):
            text = "- " + text
        return unicodedata.normalize("NFC", text)


_TONED_UPPER = frozenset("ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ")


def fix_stray_caps(line: str) -> str:
    """VietOCR đôi khi đọc một từ thường thành chữ hoa ở chỗ cắt đoạn / sau chữ viết tắt («BGDĐT NGÀY 31»).
    Từ viết hoa toàn bộ CÓ DẤU THANH (chữ viết tắt như UBND, BGDĐT không có) trong dòng mà phần còn lại chủ yếu
    là chữ thường (≥ 60%) → đổi về chữ thường. Dòng tiêu đề viết hoa không bị đụng tới."""
    words = line.split(" ")
    fixed = False
    for i, word in enumerate(words):
        core = word.strip(",;.:()\"'")
        if len(core) < 2 or not core.isupper() or not any(c in _TONED_UPPER for c in core):
            continue
        rest = [c for k, w in enumerate(words) if k != i for c in w if c.isalpha()]
        if rest and sum(c.islower() for c in rest) / len(rest) >= 0.6:
            words[i] = word.lower()
            fixed = True
    return " ".join(words) if fixed else line


# ─── Kiểu chữ: cỡ, đậm, nghiêng ────────────────────────────────────────────


def column_spans(gray: np.ndarray, min_gap: float = COLUMN_GAP) -> List[Tuple[int, int]]:
    """Khung dòng có khoảng trống rộng ≥ `min_gap` × chiều cao (hai cột cùng hàng: «BỘ GIÁO DỤC…  CỘNG HOÀ…»,
    «Nơi nhận:  BỘ TRƯỞNG») → các đoạn [x0, x1) có mực; khoảng trống giữa các từ không bị tách."""
    h, w = gray.shape[:2]
    cols = (gray < 140).any(axis=0)
    if not cols.any():
        return []
    gap = max(3, int(min_gap * h))
    spans, start, blank = [], None, 0
    for x in range(w):
        if cols[x]:
            if start is None:
                start = x
            elif blank >= gap:
                spans.append((start, x - blank))
                start = x
            blank = 0
        elif start is not None:
            blank += 1
    if start is not None:
        spans.append((start, w - blank))
    return spans


def baseline_row(gray: np.ndarray) -> int:
    """Hàng chân chữ trong ảnh dòng: nơi lượng mực theo hàng GIẢM MẠNH NHẤT khi đi xuống (đáy thân chữ) trong
    nửa dưới khung — không bị dấu chồng phía trên, nét xuống (g, p, y) phía dưới hay dòng ngắn làm lệch."""
    cv2 = _cv2()
    h = gray.shape[0]
    if gray.size == 0:
        return 0
    _t, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    rows = np.convolve((ink > 0).sum(axis=1).astype(float), np.ones(3) / 3, "same")
    if not rows.any():
        return h
    drop = rows[:-1] - rows[1:]
    lo, hi = int(0.35 * h), max(int(0.35 * h) + 1, int(0.97 * h))
    return lo + int(np.argmax(drop[lo:hi])) + 1


def stroke_metrics(gray: np.ndarray) -> Tuple[float, float]:
    """(độ dày nét trung bình px, độ «nghiêng» = độ sắc hình chiếu cột khi dựng thẳng / khi để nguyên)."""
    cv2 = _cv2()
    if gray.size == 0:
        return 0.0, 1.0
    _t, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    if not ink.any():
        return 0.0, 1.0
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    stroke = float(2.0 * dist[ink > 0].mean())

    def sharpness(img: np.ndarray) -> float:
        cols = img.sum(axis=0).astype(np.float64)
        total = cols.sum()
        return float((cols ** 2).sum() / (total * total)) if total else 0.0

    h, w = ink.shape
    pad = int(h * ITALIC_SHEAR) + 2
    m = np.float32([[1, ITALIC_SHEAR, 0], [0, 1, 0]])  # kéo phần trên sang phải → dựng thẳng chữ nghiêng
    upright = cv2.warpAffine(ink, m, (w + pad, h))
    base = sharpness(ink)
    return stroke, (sharpness(upright) / base) if base else 1.0


def assign_styles(lines: List[OcrLine], metrics: List[Tuple[float, float, float]]) -> None:
    """Đậm theo độ dày nét so với trung vị trang, nghiêng theo độ sắc khi dựng thẳng; cỡ chữ thô (gom về cỡ thân
    bài ở `harmonize_sizes`). `metrics` = (cỡ chữ ước lượng pt, nét px / cỡ chữ px, độ nghiêng)."""
    if not lines:
        return
    strokes = [k for _s, k, _i in metrics if k > 0]
    base_stroke = float(np.median(strokes)) if strokes else 0.0
    for line, (size, stroke, slant) in zip(lines, metrics):
        line.size = max(4.0, size)
        line.bold = bool(base_stroke and stroke > base_stroke * BOLD_STROKE_RATIO)
        line.italic = slant > ITALIC_GAIN


def harmonize_sizes(lines: Sequence[OcrLine]) -> None:
    """Chiều cao khung dao động theo dấu chồng / nét xuống: cỡ lệch ≤ `SIZE_SNAP` so với trung vị (cả tài liệu khi
    gọi từ `recognize_document`) coi là cỡ thân bài; làm tròn 0,5 pt."""
    sizes = [ln.size for ln in lines if ln.size > 0]
    if not sizes:
        return
    body = float(np.median(sizes))
    for ln in lines:
        size = body if abs(ln.size - body) <= SIZE_SNAP * body else ln.size
        ln.size = round(size * 2) / 2


def order_lines(lines: List[OcrLine]) -> List[OcrLine]:
    """Thứ tự đọc: gom dòng chồng lấn theo chiều dọc thành hàng, trong hàng trái → phải."""
    rows: List[List[OcrLine]] = []
    for line in sorted(lines, key=lambda ln: (ln.bbox[1] + ln.bbox[3]) / 2):
        mid = (line.bbox[1] + line.bbox[3]) / 2
        if rows:
            last = rows[-1][0]
            if abs(mid - (last.bbox[1] + last.bbox[3]) / 2) < 0.5 * (line.bbox[3] - line.bbox[1]):
                rows[-1].append(line)
                continue
        rows.append([line])
    return [ln for row in rows for ln in sorted(row, key=lambda ln: ln.bbox[0])]


# ─── Bộ máy OCR ────────────────────────────────────────────────────────────


def _import_onnxruntime():
    try:
        import onnxruntime  # noqa: PLC0415 - chỉ nạp khi dùng OCR
    except ImportError as exc:  # pragma: no cover - requirements.txt đã có onnxruntime
        raise OcrError("Thiếu thư viện ONNX Runtime (onnxruntime) để chạy OCR.") from exc
    return onnxruntime


def page_text_chars(page: fitz.Page) -> int:
    return sum(1 for ch in page.get_text("text") if not ch.isspace())


def auto_dpi(page: fitz.Page) -> int:
    """Độ phân giải để kết xuất: theo ảnh quét lớn nhất của trang (không phóng ảnh 200 dpi lên 300 vô ích),
    kẹp trong [MIN_DPI, MAX_DPI]; trang không có ảnh lớn → MAX_DPI."""
    best = 0.0
    for img in page.get_images(full=True):
        try:
            rect = page.get_image_bbox(img)
        except Exception:
            continue
        if rect.is_empty or rect.width * rect.height < 0.25 * page.rect.width * page.rect.height:
            continue
        best = max(best, math.sqrt(img[2] * img[3] / (rect.width * rect.height)) * 72.0)
    return int(min(MAX_DPI, max(MIN_DPI, round(best)))) if best else MAX_DPI


def _render_rgb(page: fitz.Page, dpi: int) -> np.ndarray:
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, colorspace=fitz.csRGB)
    samples = pix.samples  # giữ tham chiếu: bytes mới, dùng xong mới được giải phóng
    arr = np.frombuffer(samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, : pix.width * 3]
    return arr.reshape(pix.height, pix.width, 3).copy()


def ink_images(rgb: np.ndarray, zoom: float, min_area_pt: float = 400.0) -> List[Tuple[Tuple[float, float, float, float], bytes]]:
    """Cụm nét đỏ / xanh đủ lớn (con dấu, chữ ký) → [(khung pt, PNG nền trong suốt)] để neo lại vào DOCX."""
    cv2 = _cv2()
    mask = color_ink_mask(rgb).astype(np.uint8)
    if not mask.any():
        return []
    grown = cv2.dilate(mask, np.ones((25, 25), np.uint8))
    n, _labels, stats, _c = cv2.connectedComponentsWithStats(grown)
    out = []
    for i in range(1, n):
        x, y, w, h, _area = stats[i]
        if (w / zoom) * (h / zoom) < min_area_pt:
            continue
        sub = rgb[y:y + h, x:x + w]
        alpha = (mask[y:y + h, x:x + w] * 255).astype(np.uint8)
        ok, png = cv2.imencode(".png", np.dstack([sub[..., ::-1], alpha]))
        if ok:
            out.append(((x / zoom, y / zoom, (x + w) / zoom, (y + h) / zoom), png.tobytes()))
    return out


class OcrEngine:
    """Nạp 3 mô hình ONNX một lần, dùng lại cho mọi trang (mỗi trang ~5 giây trên CPU 4 nhân)."""

    def __init__(self, detector: TextDetector, recognizer: TextRecognizer) -> None:
        self.detector = detector
        self.recognizer = recognizer

    @classmethod
    def from_bundle(cls, bundle: ModelBundle, threads: int = 0) -> "OcrEngine":
        ort = _import_onnxruntime()
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        if threads:
            opts.intra_op_num_threads = threads

        def session(name: str):
            # đọc bytes: đường dẫn hồ sơ người dùng có dấu tiếng Việt không làm hỏng việc nạp
            return ort.InferenceSession(bundle.path(name).read_bytes(), opts, providers=["CPUExecutionProvider"])

        det, rec = bundle.detector, bundle.recognizer
        try:
            vocab = Vocab(bundle.path(rec["vocab"]).read_text(encoding="utf-8"))
            return cls(TextDetector(session(det["file"]), det),
                       TextRecognizer(session(rec["encoder"]), session(rec["decoder"]), vocab, rec))
        except (KeyError, OSError) as exc:
            raise OcrModelError("Bộ mô hình OCR thiếu cấu hình — hãy tải lại bộ mô hình.") from exc
        except Exception as exc:  # lỗi ONNX Runtime khi nạp mô hình hỏng
            raise OcrModelError(f"Không nạp được mô hình OCR: {exc}") from exc

    @classmethod
    def load(cls, threads: int = 0) -> "OcrEngine":
        bundle = ocr_models.find_bundle()
        if bundle is None:
            raise OcrModelsMissing(
                "Chưa cài bộ mô hình OCR tiếng Việt (~88 MB, tải một lần). "
                "Mở «OCR tiếng Việt» trong ứng dụng để tự tải, hoặc chạy: python -m qtpdfpro.cli ocr --install"
            )
        return cls.from_bundle(bundle, threads)

    def ocr_image(self, rgb: np.ndarray, zoom: float = 1.0, clean_ink: bool = True) -> List[OcrLine]:
        """Ảnh RGB → dòng chữ (toạ độ = điểm ảnh / `zoom`)."""
        work = remove_color_ink(rgb) if clean_ink else rgb
        gray = np.ascontiguousarray(work.mean(axis=2).astype(np.uint8))
        boxes = self.detector(np.ascontiguousarray(work[:, :, ::-1]))
        h, w = gray.shape
        pad_x, pad_y = max(2, int(LINE_PAD_X * zoom * 72)), max(2, int(LINE_PAD_Y * zoom * 72))
        lines: List[OcrLine] = []
        metrics: List[Tuple[float, float, float]] = []
        for box in boxes:
            bx0, y0 = np.maximum(0, np.floor(box.min(axis=0)).astype(int))
            bx1, y1 = np.ceil(box.max(axis=0)).astype(int)
            y1, bx1 = min(h, y1), min(w, bx1)
            region = gray[y0:y1, bx0:bx1]
            if region.size == 0:
                continue
            for cx0, cx1 in column_spans(region):  # hai cột cùng hàng → hai dòng
                x0, x1 = bx0 + cx0, bx0 + cx1
                crop = gray[max(0, y0 - pad_y):min(h, y1 + pad_y), max(0, x0 - pad_x):min(w, x1 + pad_x)]
                text = self.recognizer(crop) if crop.size else ""
                if not text:
                    continue
                size = (y1 - y0) / zoom * SIZE_PER_BOX_HEIGHT
                stroke, slant = stroke_metrics(gray[y0:y1, x0:x1])
                base = (y0 + baseline_row(gray[y0:y1, x0:x1])) / zoom
                lines.append(OcrLine(text, (x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom), baseline=base))
                metrics.append((size, stroke / max(1.0, size * zoom), slant))
        assign_styles(lines, metrics)
        return order_lines(lines)

    def ocr_page(self, page: fitz.Page, dpi: int = DEFAULT_DPI, clean_ink: bool = True,
                 keep_ink_images: bool = False) -> OcrPage:
        t0 = time.perf_counter()
        dpi = int(dpi) if dpi else auto_dpi(page)
        rgb = _render_rgb(page, dpi)
        zoom = dpi / 72.0
        result = OcrPage(page.number, page.rect.width, page.rect.height, self.ocr_image(rgb, zoom, clean_ink))
        if keep_ink_images:
            result.ink_images = ink_images(rgb, zoom)
        result.seconds = time.perf_counter() - t0
        return result


# ─── Lớp chữ ẩn (PDF tìm kiếm được) ────────────────────────────────────────


def _ocr_font_file(bold: bool = False, italic: bool = False) -> Optional[str]:
    d = system_font_dir()
    if d is None:
        return None
    key = ("b" if bold else "") + ("i" if italic else "")
    path = d / _FONT_FILES["serif"][key]
    return str(path) if path.exists() else None


class _TextLayer:
    """Tài liệu tạm: mỗi trang đích một trang cùng khổ (chưa xoay) chứa chữ ẩn, một phông Times New Roman chung
    → `subset_fonts` + thu gọn `/W`/`ToUnicode`, rồi `show_pdf_page` lên trang đích (không đụng phông của tệp gốc)."""

    def __init__(self) -> None:
        self.fontfile = _ocr_font_file()
        self.font = fitz.Font(fontfile=self.fontfile) if self.fontfile else fitz.Font("tiro")
        self.doc = fitz.open()
        self.used: List[str] = []

    def add(self, page: fitz.Page, ocr_page: OcrPage) -> int:
        """Trang tạm cho `page` (khổ chưa xoay); trả về số trang trong tài liệu tạm."""
        box = page.cropbox
        tmp = self.doc.new_page(width=box.width, height=box.height)
        derot = page.derotation_matrix
        for line in ocr_page.lines:
            text = line.text
            x0, y0, x1, y1 = line.bbox
            height = max(1.0, y1 - y0)
            size = line.size or height * SIZE_PER_BOX_HEIGHT
            width = self.font.text_length(text, fontsize=size)
            if width <= 0:
                continue
            # chân chữ đo từ ảnh; kéo giãn theo chiều dòng cho khớp bề rộng → tô chọn / tìm kiếm đúng chỗ.
            # Trang /Rotate 90° / 270°: trong toạ độ chưa xoay dòng chữ chạy theo trục dọc
            origin = fitz.Point(x0, line.base_y) * derot
            sx = max(0.3, min(3.0, (x1 - x0) / width))
            stretch = fitz.Matrix(1, sx) if page.rotation % 180 else fitz.Matrix(sx, 1)
            tmp.insert_text(origin, text, fontsize=size, fontname="QTOCR", fontfile=self.fontfile,
                            render_mode=3, rotate=page.rotation, morph=(origin, stretch))
            self.used.append(text)
        return tmp.number

    def finish(self) -> None:
        if not self.used:
            return
        try:
            self.doc.subset_fonts()
        except Exception:
            pass  # không nhúng tập con được thì giữ phông đầy đủ
        if self.fontfile:
            shrink_font_tables(self.doc, self.font, "".join(self.used))

    def place(self, page: fitz.Page, pno: int) -> None:
        box = page.cropbox
        page.show_pdf_page(fitz.Rect(0, 0, box.width, box.height), self.doc, pno, overlay=True)

    def close(self) -> None:
        if not self.doc.is_closed:
            self.doc.close()


# ─── Chạy trên tệp ─────────────────────────────────────────────────────────


def _resolve_output(src: Path, output: Optional[PathLike], kind: str) -> Path:
    ext = {"pdf": ".pdf", "txt": ".txt", "docx": ".docx"}[kind]
    out = Path(output).resolve() if output else default_output(src, "_ocr").with_suffix(ext)
    if out.suffix.lower() != ext:
        out = out.with_name(out.name + ext)
    if same_file(src, out):
        raise OcrError(f"Tệp kết quả trùng tệp nguồn — hãy chọn tên khác: {out.name}")
    return out


def recognize_document(
    doc: fitz.Document,
    pages: Optional[str] = None,
    dpi: int = DEFAULT_DPI,
    skip_text_pages: bool = True,
    clean_ink: bool = True,
    keep_ink_images: bool = False,
    engine: Optional[OcrEngine] = None,
    progress_cb: ProgressCallback = None,
    should_cancel: CancelCheck = None,
) -> List[OcrPage]:
    """OCR các trang chọn của `doc` (đang mở) → `OcrPage` theo thứ tự trang."""
    try:
        indices = parse_page_selection(pages or "", doc.page_count)
    except ValueError as exc:
        raise OcrError(str(exc)) from exc
    if not indices:
        raise OcrError("Không có trang nào để nhận dạng.")
    engine = engine or OcrEngine.load()
    results: List[OcrPage] = []
    for k, i in enumerate(indices):
        if should_cancel is not None and should_cancel():
            raise OcrCancelled("Đã dừng nhận dạng chữ.")
        page = doc[i]
        if progress_cb:
            progress_cb(k, len(indices), f"Đang nhận dạng trang {i + 1} ({k + 1}/{len(indices)})...")
        if skip_text_pages and page_text_chars(page) >= TEXT_PAGE_CHARS:
            results.append(OcrPage(i, page.rect.width, page.rect.height, skipped=True))
            continue
        results.append(engine.ocr_page(page, dpi, clean_ink, keep_ink_images))
    harmonize_sizes([ln for r in results for ln in r.lines])
    if progress_cb:
        progress_cb(len(indices), len(indices), "Đã nhận dạng xong.")
    return results


def _summary(src: Path, out: Path, kind: str, total: int, pages: List[OcrPage], t0: float, note: str = "") -> OcrResult:
    done = [p for p in pages if not p.skipped]
    return OcrResult(
        input_path=str(src), output_path=str(out), output_kind=kind, pages_total=total,
        pages_ocr=len(done), pages_skipped=len(pages) - len(done),
        lines=sum(len(p.lines) for p in done), chars=sum(len(p.text) for p in done),
        seconds=round(time.perf_counter() - t0, 2), note=note,
    )


def ocr_pdf(
    src: PathLike,
    output: Optional[PathLike] = None,
    pages: Optional[str] = None,
    dpi: int = DEFAULT_DPI,
    password: Optional[str] = None,
    skip_text_pages: bool = True,
    clean_ink: bool = True,
    engine: Optional[OcrEngine] = None,
    progress_cb: ProgressCallback = None,
    should_cancel: CancelCheck = None,
) -> OcrResult:
    """PDF ảnh quét → PDF tìm kiếm được (ảnh giữ nguyên, thêm lớp chữ ẩn chọn / chép / tìm được)."""
    t0 = time.perf_counter()
    src_path = Path(src).resolve()
    out = _resolve_output(src_path, output, "pdf")
    opened = open_pdf(src_path, password)
    doc = opened.doc
    layer = _TextLayer()
    try:
        results = recognize_document(doc, pages, dpi, skip_text_pages, clean_ink, False, engine, progress_cb, should_cancel)
        placed = [(doc[r.number], layer.add(doc[r.number], r)) for r in results if not r.skipped and r.lines]
        layer.finish()
        for page, pno in placed:
            layer.place(page, pno)
        save_kwargs = {"garbage": 3, "deflate": True}
        if opened.locked:  # giữ mật khẩu / mã hoá của tệp gốc
            save_kwargs["encryption"] = fitz.PDF_ENCRYPT_KEEP
        save_pdf(doc, out, **save_kwargs)
        total = doc.page_count
    finally:
        layer.close()
        doc.close()
    note = "" if any(not r.skipped for r in results) else "Mọi trang đã có lớp chữ — không cần OCR."
    return _summary(src_path, out, "pdf", total, results, t0, note)


def ocr_to_text(
    src: PathLike,
    output: Optional[PathLike] = None,
    pages: Optional[str] = None,
    dpi: int = DEFAULT_DPI,
    password: Optional[str] = None,
    engine: Optional[OcrEngine] = None,
    progress_cb: ProgressCallback = None,
    should_cancel: CancelCheck = None,
) -> OcrResult:
    """Nhận dạng → tệp văn bản UTF-8 (trang có lớp chữ thì lấy chữ sẵn có), các trang cách nhau bằng dấu ngắt trang."""
    t0 = time.perf_counter()
    src_path = Path(src).resolve()
    out = _resolve_output(src_path, output, "txt")
    doc = open_pdf(src_path, password).doc
    try:
        results = recognize_document(doc, pages, dpi, True, True, False, engine, progress_cb, should_cancel)
        chunks = [doc[r.number].get_text("text").strip() if r.skipped else r.text for r in results]
        total = doc.page_count
    finally:
        doc.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n\f\n".join(chunks) + "\n", encoding="utf-8", newline="\n")
    return _summary(src_path, out, "txt", total, results, t0)


def build_text_pdf(pages: List[OcrPage], src_doc: fitz.Document) -> fitz.Document:
    """Trang dựng lại chỉ có CHỮ THẬT (Times New Roman, cỡ / đậm / nghiêng ước lượng) đặt đúng toạ độ + ảnh con
    dấu / chữ ký — đầu vào cho `converter.convert_pdf_to_docx` (trang đã có chữ thì chép nguyên trang gốc)."""
    out = fitz.open()
    fonts = {}
    for p in pages:
        if p.skipped:
            out.insert_pdf(src_doc, from_page=p.number, to_page=p.number)
            continue
        page = out.new_page(width=p.width, height=p.height)
        for rect, png in p.ink_images:
            page.insert_image(fitz.Rect(rect), stream=png, overlay=False)
        for line in p.lines:
            key = (line.bold, line.italic)
            if key not in fonts:
                path = _ocr_font_file(*key)
                fonts[key] = (path, fitz.Font(fontfile=path) if path else fitz.Font("tiro"))
            fontfile, font = fonts[key]
            name = "QTOCR" + ("B" if line.bold else "") + ("I" if line.italic else "")
            x0, y0, x1, y1 = line.bbox
            size = line.size or 13.0
            box_w = x1 - x0
            width = font.text_length(line.text, fontsize=size)
            if width > box_w * 1.02:  # tràn khung gốc (ví dụ phần đầu 13 pt ước lượng thành 14) → thu vừa khung
                size = max(6.0, math.floor(size * box_w / width * 2) / 2)
                width = font.text_length(line.text, fontsize=size)
            origin = fitz.Point(x0, line.base_y)
            morph = None
            if " " in line.text and 0.85 * box_w <= width < box_w:
                # dòng căn đều: kéo giãn ngang cho kín khung như bản gốc (bộ chuyển đo đúng lề phải), ép dọc
                # cùng tỷ lệ để định thức = 1 → cỡ chữ đọc lại vẫn đúng (MuPDF tính cỡ = √|định thức|)
                sx = box_w / width
                morph = (origin, fitz.Matrix(sx, 1.0 / sx))
            page.insert_text(origin, line.text, fontsize=size, fontname=name if fontfile else "tiro",
                             fontfile=fontfile, morph=morph)
    if fonts:
        try:
            out.subset_fonts()
        except Exception:
            pass
    return out


def ocr_to_docx(
    src: PathLike,
    output: Optional[PathLike] = None,
    pages: Optional[str] = None,
    dpi: int = DEFAULT_DPI,
    password: Optional[str] = None,
    mode: str = "auto",
    nd30_policy: str = "faithful",
    engine: Optional[OcrEngine] = None,
    progress_cb: ProgressCallback = None,
    should_cancel: CancelCheck = None,
) -> OcrResult:
    """PDF ảnh quét → DOCX: nhận dạng, dựng trang chữ thật rồi chuyển như PDF thường (văn bản hành chính → NĐ30)."""
    from qtpdfpro.core.converter import ConversionOptions, convert_pdf_to_docx  # noqa: PLC0415 - tránh vòng import

    t0 = time.perf_counter()
    src_path = Path(src).resolve()
    out = _resolve_output(src_path, output, "docx")
    doc = open_pdf(src_path, password).doc
    try:
        results = recognize_document(doc, pages, dpi, True, True, True, engine, progress_cb, should_cancel)
        text_doc = build_text_pdf(results, doc)
        total = doc.page_count
    finally:
        doc.close()
    if progress_cb:
        progress_cb(len(results), len(results), "Đang dựng tệp Word...")
    with tempfile.TemporaryDirectory(prefix="qtpdfpro-ocr-") as tmp:
        tmp_pdf = Path(tmp) / "ocr_text.pdf"
        text_doc.save(str(tmp_pdf), garbage=3, deflate=True)
        text_doc.close()
        opts = ConversionOptions(mode=mode, nd30_policy=nd30_policy, verify_layout=False)
        conv = convert_pdf_to_docx(tmp_pdf, out, opts)
    note = f"Chế độ chuyển: {getattr(conv, 'mode_used', mode)}"
    return _summary(src_path, out, "docx", total, results, t0, note)
