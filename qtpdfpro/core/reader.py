"""Engine đọc, kết xuất, tìm kiếm và trích xuất thông tin tài liệu PDF.

Dựa trên `PyMuPDF` (`fitz`), thiết kế hoàn toàn tách biệt với `PySide6` để dùng chung
cho cả giao diện đồ hoạ, dòng lệnh CLI và bộ kiểm thử tự động `pytest`.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

from qtpdfpro.core.font_resolver import normalize_vietnamese_text
from qtpdfpro.core.layout_analyzer import BBox, PageLayoutSummary, analyze_page_layout


@dataclass
class RenderedPageBuffer:
    """Bộ đệm hình ảnh RGB của một trang PDF sau khi kết xuất."""

    page_index: int
    width: int
    height: int
    stride: int
    scale: float
    rotation: int
    rgb_bytes: bytes


@dataclass
class BookmarkNode:
    """Một mục trong cây Mục lục (Table of Contents / Outline) của PDF."""

    level: int
    title: str
    page_index: int  # 0-based


@dataclass
class SearchHit:
    """Một kết quả tìm kiếm văn bản trên trang PDF."""

    page_index: int  # 0-based
    bbox: BBox
    snippet: str


@dataclass
class DocumentInfo:
    """Thông tin tổng quan của tệp PDF."""

    file_path: str
    file_name: str
    file_size_bytes: int
    page_count: int
    title: str = ""
    author: str = ""
    subject: str = ""
    creator: str = ""
    producer: str = ""
    creation_date: str = ""
    is_encrypted: bool = False
    pdf_version: str = ""


class PDFDocumentReader:
    """Quản lý một tài liệu PDF đang mở: kết xuất trang, tìm kiếm, mục lục, phân tích bố cục."""

    def __init__(self, pdf_path: str | Path, password: Optional[str] = None, cache_size: int = 24) -> None:
        self.path = Path(pdf_path).resolve()
        if not self.path.exists():
            raise FileNotFoundError(f"Không tìm thấy tệp PDF: {self.path}")

        self._doc: fitz.Document = fitz.open(str(self.path))
        if self._doc.needs_pass:
            if not password or not self._doc.authenticate(password):
                self._doc.close()
                raise PermissionError("Tệp PDF được bảo vệ bằng mật khẩu.")

        self._cache_size = max(4, cache_size)
        self._render_cache: "OrderedDict[Tuple[int, int, int], RenderedPageBuffer]" = OrderedDict()
        self._page_rotations: Dict[int, int] = {}
        self._layout_cache: Dict[int, PageLayoutSummary] = {}

    def __enter__(self) -> "PDFDocumentReader":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @property
    def page_count(self) -> int:
        return len(self._doc)

    @property
    def doc(self) -> fitz.Document:
        return self._doc

    def close(self) -> None:
        """Đóng tài liệu PDF và giải phóng bộ nhớ đệm."""
        self._render_cache.clear()
        self._layout_cache.clear()
        if getattr(self, "_doc", None) is not None and not self._doc.is_closed:
            self._doc.close()

    def get_info(self) -> DocumentInfo:
        """Trả về thông tin metadata của tài liệu PDF."""
        meta = self._doc.metadata or {}
        size_bytes = self.path.stat().st_size if self.path.exists() else 0
        return DocumentInfo(
            file_path=str(self.path),
            file_name=self.path.name,
            file_size_bytes=size_bytes,
            page_count=len(self._doc),
            title=normalize_vietnamese_text(meta.get("title") or ""),
            author=normalize_vietnamese_text(meta.get("author") or ""),
            subject=normalize_vietnamese_text(meta.get("subject") or ""),
            creator=normalize_vietnamese_text(meta.get("creator") or ""),
            producer=normalize_vietnamese_text(meta.get("producer") or ""),
            creation_date=meta.get("creationDate") or "",
            is_encrypted=bool(self._doc.is_encrypted),
            pdf_version=meta.get("format") or "PDF",
        )

    def get_page_size(self, page_index: int) -> Tuple[float, float]:
        """Trả về `(width_pt, height_pt)` của trang sau khi tính góc xoay."""
        self._check_page_index(page_index)
        page = self._doc[page_index]
        rect = page.rect
        extra_rot = self._page_rotations.get(page_index, 0) % 360
        if extra_rot in (90, 270):
            return float(rect.height), float(rect.width)
        return float(rect.width), float(rect.height)

    def rotate_page(self, page_index: int, delta_degrees: int = 90) -> int:
        """Xoay hiển thị của một trang thêm `delta_degrees` (bội số của 90)."""
        self._check_page_index(page_index)
        current = self._page_rotations.get(page_index, 0)
        new_rot = (current + delta_degrees) % 360
        self._page_rotations[page_index] = new_rot
        # Xoá cache của trang này
        keys_to_remove = [k for k in self._render_cache if k[0] == page_index]
        for k in keys_to_remove:
            self._render_cache.pop(k, None)
        return new_rot

    def get_page_rotation(self, page_index: int) -> int:
        return self._page_rotations.get(page_index, 0)

    def render_page(self, page_index: int, scale: float = 1.0) -> RenderedPageBuffer:
        """Kết xuất trang `page_index` ở tỷ lệ `scale` (1.0 = 72 DPI, 2.0 = 144 DPI) sang RGB."""
        self._check_page_index(page_index)
        clamped_scale = max(0.15, min(6.0, float(scale)))
        scale_key = int(round(clamped_scale * 1000))
        extra_rot = self._page_rotations.get(page_index, 0) % 360
        cache_key = (page_index, scale_key, extra_rot)

        if cache_key in self._render_cache:
            self._render_cache.move_to_end(cache_key)
            return self._render_cache[cache_key]

        page = self._doc[page_index]
        mat = fitz.Matrix(clamped_scale, clamped_scale)
        if extra_rot:
            mat = mat.prerotate(extra_rot)

        pix = page.get_pixmap(matrix=mat, alpha=False)
        buf = RenderedPageBuffer(
            page_index=page_index,
            width=pix.width,
            height=pix.height,
            stride=pix.stride,
            scale=clamped_scale,
            rotation=extra_rot,
            rgb_bytes=bytes(pix.samples),
        )

        self._render_cache[cache_key] = buf
        while len(self._render_cache) > self._cache_size:
            self._render_cache.popitem(last=False)
        return buf

    def get_bookmarks(self) -> List[BookmarkNode]:
        """Trả về danh sách mục lục (Table of Contents) của tài liệu."""
        toc = self._doc.get_toc(simple=True) or []
        nodes: List[BookmarkNode] = []
        for item in toc:
            if len(item) >= 3:
                level, title, page_1based = int(item[0]), str(item[1]), int(item[2])
                page_idx = max(0, min(self.page_count - 1, page_1based - 1))
                nodes.append(
                    BookmarkNode(
                        level=max(1, level),
                        title=normalize_vietnamese_text(title.strip()) or f"Trang {page_idx + 1}",
                        page_index=page_idx,
                    )
                )
        return nodes

    def get_page_text(self, page_index: int) -> str:
        """Trích xuất văn bản thuần trên trang `page_index` (đã chuẩn hoá NFC)."""
        self._check_page_index(page_index)
        raw_text = self._doc[page_index].get_text("text")
        return normalize_vietnamese_text(raw_text)

    def search(self, query: str, max_hits: int = 500) -> List[SearchHit]:
        """Tìm kiếm văn bản trên toàn bộ tài liệu, trả về toạ độ bbox và ngữ cảnh."""
        q = normalize_vietnamese_text(query.strip())
        if not q:
            return []

        hits: List[SearchHit] = []
        q_lower = q.lower()
        q_nbsp = q.replace(" ", "\u00a0").replace("-", "\u00ad")

        for page_idx in range(self.page_count):
            page = self._doc[page_idx]
            rects = list(page.search_for(q))
            if not rects and q_nbsp != q:
                rects = list(page.search_for(q_nbsp))

            page_text = normalize_vietnamese_text(page.get_text("text"))
            lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
            matching_lines = [ln for ln in lines if q_lower in ln.lower()]

            if rects:
                for idx, r in enumerate(rects):
                    snippet = (
                        matching_lines[idx]
                        if idx < len(matching_lines)
                        else (matching_lines[0] if matching_lines else q)
                    )
                    if len(snippet) > 90:
                        snippet = snippet[:87] + "..."
                    hits.append(
                        SearchHit(
                            page_index=page_idx,
                            bbox=(float(r.x0), float(r.y0), float(r.x1), float(r.y1)),
                            snippet=snippet,
                        )
                    )
                    if len(hits) >= max_hits:
                        return hits
            elif matching_lines:
                # Dự phòng quét từng dòng trong dict khi phông chữ PDF dùng CMap đặc biệt
                raw_dict = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
                for block in raw_dict.get("blocks", []):
                    if block.get("type", 0) != 0:
                        continue
                    for line in block.get("lines", []):
                        line_txt = normalize_vietnamese_text(
                            "".join(s.get("text", "") for s in line.get("spans", []))
                        ).strip()
                        if q_lower in line_txt.lower():
                            lb = line.get("bbox", (0, 0, 0, 0))
                            snippet = line_txt[:87] + "..." if len(line_txt) > 90 else line_txt
                            hits.append(
                                SearchHit(
                                    page_index=page_idx,
                                    bbox=(float(lb[0]), float(lb[1]), float(lb[2]), float(lb[3])),
                                    snippet=snippet,
                                )
                            )
                            if len(hits) >= max_hits:
                                return hits
        return hits

    def get_page_layout(self, page_index: int) -> PageLayoutSummary:
        """Phân tích và trả về cấu trúc bố cục của trang `page_index` (có cache)."""
        self._check_page_index(page_index)
        if page_index not in self._layout_cache:
            self._layout_cache[page_index] = analyze_page_layout(self._doc[page_index])
        return self._layout_cache[page_index]

    def _check_page_index(self, page_index: int) -> None:
        if page_index < 0 or page_index >= self.page_count:
            raise IndexError(f"Chỉ số trang {page_index} nằm ngoài phạm vi (0..{self.page_count - 1}).")
