"""Nén PDF: giảm độ phân giải & nén lại ảnh, nhúng tập con phông chữ, dọn đối tượng thừa.

Chỉ dùng PyMuPDF (không cần Ghostscript). Ba mức nén:

| Mức | Ảnh trên ngưỡng → đưa về | Chất lượng JPEG | Dùng khi |
|---|---|---|---|
| Nhẹ | > 250 dpi → 200 dpi | 85 | Cần in lại đẹp |
| Vừa | > 180 dpi → 150 dpi | 75 | Đọc trên màn hình, in văn phòng |
| Mạnh | > 120 dpi → 96 dpi | 60 | Gửi thư điện tử, tải lên cổng dịch vụ công |

Không ghi tệp nếu kết quả không nhỏ hơn tệp gốc. Tệp có mật khẩu giữ nguyên mật khẩu sau khi nén.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import fitz  # PyMuPDF

from qtpdfpro.core.pdf_io import (
    PathLike,
    PdfToolError,
    ToolResult,
    check_signature,
    format_size,
    is_protected,
    open_pdf,
    resolve_output,
    write_pdf_bytes,
)


@dataclass(frozen=True)
class CompressLevel:
    key: str
    label: str
    description: str
    dpi_threshold: int  # chỉ xử lý ảnh có độ phân giải hiệu dụng trên ngưỡng này
    dpi_target: int
    quality: int  # chất lượng JPEG 0–100


COMPRESS_LEVELS: Dict[str, CompressLevel] = {
    "light": CompressLevel("light", "Nhẹ", "Giữ chất lượng in — ảnh trên 250 dpi đưa về 200 dpi, JPEG 85", 250, 200, 85),
    "medium": CompressLevel("medium", "Vừa", "Cân bằng đọc màn hình & in văn phòng — 150 dpi, JPEG 75", 180, 150, 75),
    "strong": CompressLevel("strong", "Mạnh", "Nhỏ nhất để gửi thư điện tử — 96 dpi, JPEG 60", 120, 96, 60),
}

_LEVEL_ALIASES = {"nhe": "light", "low": "light", "vua": "medium", "trung_binh": "medium", "manh": "strong", "high": "strong"}

SUFFIX = "_nen"


def resolve_level(level: str) -> CompressLevel:
    key = (level or "medium").strip().lower()
    key = _LEVEL_ALIASES.get(key, key)
    if key not in COMPRESS_LEVELS:
        raise PdfToolError(f"Mức nén không hợp lệ: «{level}» (chọn nhe / vua / manh).")
    return COMPRESS_LEVELS[key]


def compress_document(doc: fitz.Document, level: str = "medium") -> bytes:
    """Nén tài liệu đang mở (thay đổi `doc`) → dữ liệu PDF đã nén (giữ nguyên mã hoá nếu có)."""
    lv = resolve_level(level)
    doc.rewrite_images(dpi_threshold=lv.dpi_threshold, dpi_target=lv.dpi_target, quality=lv.quality)
    try:
        doc.subset_fonts()
    except Exception:
        pass  # phông không nhúng tập con được (Type3, CFF lỗi…) thì giữ nguyên
    return doc.tobytes(
        garbage=4, deflate=True, clean=True, use_objstms=1, encryption=fitz.PDF_ENCRYPT_KEEP,
    )


def compress_pdf(
    src: PathLike,
    output: Optional[PathLike] = None,
    level: str = "medium",
    password: Optional[str] = None,
    allow_signed: bool = False,
) -> ToolResult:
    """Nén tệp `src` → `output` (mặc định `<tên>_nen.pdf`).

    Kết quả không nhỏ hơn tệp gốc thì **không ghi** (`written=False`).
    """
    lv = resolve_level(level)
    src_path = Path(src).resolve()
    out = resolve_output(src_path, output, SUFFIX)
    in_size = src_path.stat().st_size if src_path.exists() else 0
    doc = open_pdf(src_path, password, need=fitz.PDF_PERM_MODIFY).doc
    try:
        check_signature(doc, allow_signed)
        pages = doc.page_count
        protected = is_protected(doc)
        data = compress_document(doc, lv.key)
    finally:
        doc.close()
    res = ToolResult("compress", str(src_path), "", False, pages, in_size, len(data), encrypted=protected)
    if len(data) >= in_size:
        res.note = (
            f"Tệp đã tối ưu — nén mức «{lv.label}» không nhỏ hơn ({format_size(len(data))} ≥ "
            f"{format_size(in_size)}), không ghi tệp."
        )
        return res
    res.output_path = str(write_pdf_bytes(data, out))
    res.written = True
    percent = f"{res.saved_ratio * 100:.1f}".replace(".", ",")
    res.note = f"Mức «{lv.label}»: {format_size(in_size)} → {format_size(len(data))} (giảm {percent}%)"
    return res
