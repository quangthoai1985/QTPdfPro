"""Phân tích cấu trúc bố cục trang PDF (Văn bản, Bảng biểu, Hình ảnh, Vector, Cột).

Cung cấp dữ liệu cho:
1. Lớp phủ trực quan "Soi bố cục (Layout Inspector)" trên giao diện đọc PDF.
2. Bộ chọn chế độ chuyển đổi thông minh (`Smart Auto`) và báo cáo kiểm định (`Fidelity`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import fitz  # PyMuPDF

from qtpdfpro.core.font_resolver import normalize_vietnamese_text, resolve_pdf_font

BBox = Tuple[float, float, float, float]


@dataclass
class LayoutElement:
    """Một thành phần bố cục được phát hiện trên trang PDF."""

    kind: str  # "text" | "table" | "image" | "vector"
    bbox: BBox
    label: str = ""
    text_preview: str = ""
    font_family: str = ""
    font_size: float = 0.0


@dataclass
class PageLayoutSummary:
    """Tóm tắt cấu trúc bố cục của một trang PDF."""

    page_index: int
    width: float
    height: float
    rotation: int
    text_block_count: int = 0
    table_count: int = 0
    image_count: int = 0
    vector_count: int = 0
    char_count: int = 0
    is_scanned: bool = False
    fonts_used: List[str] = field(default_factory=list)
    elements: List[LayoutElement] = field(default_factory=list)

    @property
    def recommended_mode(self) -> str:
        """Gợi ý chế độ chuyển đổi tối ưu cho trang này."""
        if self.vector_count > 120 and self.table_count == 0 and self.text_block_count > 15:
            return "exact"
        return "hybrid"


def analyze_page_layout(page: fitz.Page, include_vectors: bool = True) -> PageLayoutSummary:
    """Phân tích toàn bộ thành phần trên một trang PDF."""
    rect = page.rect
    summary = PageLayoutSummary(
        page_index=page.number,
        width=float(rect.width),
        height=float(rect.height),
        rotation=int(page.rotation),
    )

    fonts_set: set[str] = set()
    raw = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)

    # 1. Phân tích khối văn bản & hình ảnh từ get_text("dict")
    for block in raw.get("blocks", []):
        btype = block.get("type", 0)
        bbox: BBox = tuple(float(v) for v in block.get("bbox", (0, 0, 0, 0)))  # type: ignore[assignment]
        if btype == 0:  # Khối văn bản
            lines_text: list[str] = []
            first_font = ""
            first_size = 0.0
            for line in block.get("lines", []):
                spans_text: list[str] = []
                for span in line.get("spans", []):
                    raw_font = span.get("font", "")
                    flags = int(span.get("flags", 0))
                    resolved = resolve_pdf_font(raw_font, flags=flags)
                    fonts_set.add(resolved.family)
                    if not first_font:
                        first_font = resolved.family
                        first_size = float(span.get("size", 11.0))
                    txt = normalize_vietnamese_text(span.get("text", ""), raw_font)
                    spans_text.append(txt)
                line_str = "".join(spans_text).strip()
                if line_str:
                    lines_text.append(line_str)

            full_block_text = "\n".join(lines_text).strip()
            if full_block_text:
                summary.text_block_count += 1
                summary.char_count += len(full_block_text)
                preview = full_block_text.replace("\n", " ")[:60]
                summary.elements.append(
                    LayoutElement(
                        kind="text",
                        bbox=bbox,
                        label=f"Văn bản ({first_font}, {first_size:.1f}pt)",
                        text_preview=preview,
                        font_family=first_font,
                        font_size=first_size,
                    )
                )
        elif btype == 1:  # Khối hình ảnh trong luồng
            summary.image_count += 1
            summary.elements.append(
                LayoutElement(
                    kind="image",
                    bbox=bbox,
                    label=f"Hình ảnh ({int(bbox[2]-bbox[0])}×{int(bbox[3]-bbox[1])}pt)",
                )
            )

    # Kiểm tra thêm ảnh nhúng qua get_images nếu chưa nằm trong dict blocks
    page_images = page.get_images(full=True)
    if len(page_images) > summary.image_count:
        for img_info in page_images:
            xref = img_info[0]
            try:
                rects = page.get_image_rects(xref)
                for r in rects:
                    ibbox: BBox = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
                    if not any(
                        el.kind == "image" and _bbox_close(el.bbox, ibbox)
                        for el in summary.elements
                    ):
                        summary.image_count += 1
                        summary.elements.append(
                            LayoutElement(
                                kind="image",
                                bbox=ibbox,
                                label=f"Ảnh XRef #{xref}",
                            )
                        )
            except Exception:
                pass

    # 2. Phát hiện bảng biểu bằng PyMuPDF find_tables (ẩn thông báo quảng cáo pymupdf_layout ra stdout)
    try:
        import contextlib
        import io as _io

        with contextlib.redirect_stdout(_io.StringIO()):
            finder = page.find_tables()
        for idx, tbl in enumerate(finder.tables, start=1):
            tbbox: BBox = tuple(float(v) for v in tbl.bbox)  # type: ignore[assignment]
            summary.table_count += 1
            summary.elements.append(
                LayoutElement(
                    kind="table",
                    bbox=tbbox,
                    label=f"Bảng #{idx} ({tbl.row_count} hàng × {tbl.col_count} cột)",
                )
            )
    except Exception:
        pass

    # 3. Phân tích các nét vẽ vector (đường kẻ, khung hộp)
    try:
        drawings = page.get_drawings()
        summary.vector_count = len(drawings)
        if include_vectors:
            for d in drawings[:80]:  # Giới hạn số khung vector hiển thị trên overlay để không rối mắt
                r = d.get("rect")
                if r is not None:
                    vbbox: BBox = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
                    if (vbbox[2] - vbbox[0]) > 2.0 or (vbbox[3] - vbbox[1]) > 2.0:
                        summary.elements.append(
                            LayoutElement(
                                kind="vector",
                                bbox=vbbox,
                                label="Đường kẻ / Khung vector",
                            )
                        )
    except Exception:
        pass

    summary.fonts_used = sorted(fonts_set)
    summary.is_scanned = summary.char_count == 0 and summary.image_count > 0
    return summary


def _bbox_close(a: BBox, b: BBox, tol: float = 3.0) -> bool:
    return (
        abs(a[0] - b[0]) <= tol
        and abs(a[1] - b[1]) <= tol
        and abs(a[2] - b[2]) <= tol
        and abs(a[3] - b[3]) <= tol
    )
