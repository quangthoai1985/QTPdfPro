"""Bộ Điều phối Chuyển đổi PDF sang DOCX Đa Chế độ (Multi-Engine PDF-to-DOCX Orchestrator).

Hỗ trợ 4 chế độ chuyển đổi:
- `hybrid` (Mặc định khuyên dùng): Kết hợp `pdf2docx` tái tạo cấu trúc (đoạn văn, bảng biểu,
  cột, hình ảnh, màu sắc) + Bộ Hậu xử lý Chuẩn xác OpenXML (`openxml_fixer.py`).
- `exact` (Giữ nguyên vị trí 1:1): Đặt từng dòng chữ vào khung toạ độ tuyệt đối `<w:framePr>`
  kết hợp lớp đồ hoạ nền vector/ảnh phía sau (`exact_layout_engine.py`).
- `word_com` (Microsoft Word Reflow): Gọi engine chuyển đổi gốc của MS Word qua COM rồi
  chạy Bộ Hậu xử lý Chuẩn xác OpenXML (`word_com_bridge.py`).
- `auto` (Tự động thông minh): Phân tích bố cục trang PDF trước, tự chọn `hybrid` hoặc `exact`
  tuỳ theo độ phức tạp đồ hoạ vector của tài liệu.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import fitz  # PyMuPDF
from pdf2docx import Converter as Pdf2DocxConverter

from qtpdfpro.core.exact_layout_engine import convert_pdf_exact_layout
from qtpdfpro.core.fidelity import FidelityReport, evaluate_conversion_fidelity
from qtpdfpro.core.layout_analyzer import analyze_page_layout
from qtpdfpro.core.openxml_fixer import OpenXMLFixReport, fix_docx_package
from qtpdfpro.core.word_com_bridge import convert_via_ms_word_com, is_ms_word_available

ProgressCallback = Optional[Callable[[int, int, str], None]]


class ConversionError(Exception):
    """Lỗi tường minh bằng tiếng Việt khi chuyển đổi PDF sang DOCX."""


@dataclass
class ConversionOptions:
    """Tuỳ chọn cấu hình cho một lượt chuyển đổi PDF sang DOCX."""

    mode: str = "hybrid"  # "auto" | "hybrid" | "exact" | "word_com"
    pages: Optional[List[int]] = None  # Danh sách trang 0-based; None = tất cả trang
    default_font: str = "Times New Roman"
    normalize_vietnamese: bool = True
    fix_table_padding: bool = True
    prevent_line_overflow: bool = True
    exact_background_dpi: int = 180
    password: Optional[str] = None


@dataclass
class ConversionResult:
    """Kết quả trả về sau khi hoàn tất chuyển đổi PDF sang DOCX."""

    pdf_path: str
    docx_path: str
    mode_used: str
    pages_converted: int
    elapsed_seconds: float
    fix_report: OpenXMLFixReport = field(default_factory=OpenXMLFixReport)
    fidelity: FidelityReport = field(default_factory=FidelityReport)


def parse_page_range(spec: str, total_pages: int) -> List[int]:
    """Phân tích chuỗi phạm vi trang (1-based, vd `'1-3, 5, 8-10'`) thành danh sách chỉ số 0-based."""
    if total_pages <= 0:
        return []
    cleaned = (spec or "").strip()
    if not cleaned or cleaned.lower() in ("all", "tatca", "tất cả", "*"):
        return list(range(total_pages))

    indices: set[int] = set()
    for part in cleaned.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            pieces = token.split("-", 1)
            try:
                start_1 = int(pieces[0].strip())
                end_1 = int(pieces[1].strip())
            except ValueError as exc:
                raise ConversionError(f"Phạm vi trang không hợp lệ: '{token}'") from exc
            if start_1 > end_1:
                start_1, end_1 = end_1, start_1
            for p1 in range(start_1, end_1 + 1):
                if 1 <= p1 <= total_pages:
                    indices.add(p1 - 1)
        else:
            try:
                p1 = int(token)
            except ValueError as exc:
                raise ConversionError(f"Số trang không hợp lệ: '{token}'") from exc
            if 1 <= p1 <= total_pages:
                indices.add(p1 - 1)

    if not indices:
        raise ConversionError(
            f"Không có trang nào trong phạm vi '{spec}' thuộc tài liệu (1..{total_pages})."
        )
    return sorted(indices)


def convert_pdf_to_docx(
    pdf_path: str | Path,
    docx_path: str | Path,
    options: Optional[ConversionOptions] = None,
    progress_cb: ProgressCallback = None,
) -> ConversionResult:
    """Thực hiện chuyển đổi tệp PDF sang DOCX kèm hậu xử lý chuẩn xác và kiểm định chất lượng."""
    t0 = time.perf_counter()
    opts = options or ConversionOptions()
    src = Path(pdf_path).resolve()
    dst = Path(docx_path).resolve()

    if not src.exists():
        raise ConversionError(f"Không tìm thấy tệp PDF đầu vào: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    # 1. Kiểm tra tệp PDF và xác định danh sách trang cần chuyển
    with fitz.open(str(src)) as doc:
        if doc.needs_pass:
            if not opts.password or not doc.authenticate(opts.password):
                raise ConversionError("Tệp PDF có mật khẩu bảo vệ. Vui lòng nhập đúng mật khẩu.")
        total_pages = len(doc)
        if total_pages == 0:
            raise ConversionError("Tệp PDF không có trang nào.")

        target_pages = (
            [p for p in opts.pages if 0 <= p < total_pages]
            if opts.pages is not None
            else list(range(total_pages))
        )
        if not target_pages:
            target_pages = list(range(total_pages))

        # Xác định chế độ thực tế nếu người dùng chọn "auto"
        actual_mode = opts.mode.lower().strip()
        if actual_mode == "auto":
            sample_pages = target_pages[: min(3, len(target_pages))]
            summaries = [analyze_page_layout(doc[p], include_vectors=False) for p in sample_pages]
            if any(s.recommended_mode == "exact" for s in summaries):
                actual_mode = "exact"
            else:
                actual_mode = "hybrid"

    total_target = len(target_pages)
    if progress_cb:
        progress_cb(0, total_target, f"Khởi động engine chuyển đổi ({actual_mode})...")

    # 2. Chạy Engine chuyển đổi chính
    if actual_mode == "word_com":
        if is_ms_word_available():
            if progress_cb:
                progress_cb(1, total_target, "Đang chuyển đổi qua Microsoft Word Reflow...")
            ok = convert_via_ms_word_com(src, dst, pages=target_pages)
            if not ok:
                actual_mode = "hybrid"
        else:
            actual_mode = "hybrid"

    if actual_mode == "hybrid":
        try:
            _run_hybrid_pdf2docx(
                src=src,
                dst=dst,
                target_pages=target_pages,
                total_doc_pages=total_pages,
                progress_cb=progress_cb,
            )
        except Exception:
            # Nếu pdf2docx gặp cấu trúc vector dị biệt, tự động chuyển sang chế độ khung tuyệt đối 1:1
            actual_mode = "exact"

    if actual_mode == "exact":
        convert_pdf_exact_layout(
            pdf_path=src,
            docx_path=dst,
            pages=target_pages,
            background_dpi=opts.exact_background_dpi,
            default_font=opts.default_font,
            normalize_vietnamese=opts.normalize_vietnamese,
            progress_cb=progress_cb,
        )

    # 3. Chạy Bộ Hậu xử lý Chuẩn xác OpenXML (QT OpenXML Precision Fixer)
    if progress_cb:
        progress_cb(
            total_target,
            total_target,
            "Đang chuẩn hoá phông chữ, tiếng Việt & tinh chỉnh lề OpenXML...",
        )

    fix_report = fix_docx_package(
        docx_path=dst,
        default_font=opts.default_font,
        normalize_vietnamese=opts.normalize_vietnamese,
        fix_table_padding=(opts.fix_table_padding and actual_mode != "exact"),
        prevent_line_overflow=(opts.prevent_line_overflow and actual_mode != "exact"),
    )

    # 4. Đánh giá độ chính xác (Fidelity Inspector)
    if progress_cb:
        progress_cb(total_target, total_target, "Đang kiểm định độ chính xác tài liệu...")

    fidelity = evaluate_conversion_fidelity(src, dst, pages=target_pages)
    elapsed = round(time.perf_counter() - t0, 3)

    return ConversionResult(
        pdf_path=str(src),
        docx_path=str(dst),
        mode_used=actual_mode,
        pages_converted=total_target,
        elapsed_seconds=elapsed,
        fix_report=fix_report,
        fidelity=fidelity,
    )


_PDF2DOCX_PATCHED = False


def _install_pdf2docx_patches() -> None:
    """Sửa lỗi nội bộ của thư viện `pdf2docx` (`RawPage._create_section`):

    Mặc định khi `elements.group_by_columns()` tách ra >2 nhóm cột hoặc 2 cột lệch toạ độ Y
    (như Quốc hiệu - Tiêu ngữ có tiêu đề 'QUYẾT ĐỊNH' ở giữa bên dưới), `pdf2docx` chỉ lấy
    `cols[0].bbox` và `cols[1].bbox` dẫn tới việc bỏ sót các khối văn bản ở `cols[2]` hoặc
    ngoài dải Y của `cols[1]`. Bản vá này gộp toàn bộ chiều cao Y (`y_top..y_bot`) để
    không một dòng văn bản nào bị rơi rớt.
    """
    global _PDF2DOCX_PATCHED
    if _PDF2DOCX_PATCHED:
        return
    try:
        from pdf2docx.layout.Column import Column
        from pdf2docx.layout.Section import Section
        from pdf2docx.page.RawPage import RawPage

        def _safe_create_section(num_col: int, elements, h_range: tuple, y_ref: float):
            if not elements:
                return None
            X0, X1 = h_range
            if num_col == 1:
                x0, y0, x1, y1 = elements.bbox
                column = Column().update_bbox((X0, y0, X1, y1))
                column.add_elements(elements)
                section = Section(space=0, columns=[column])
                before_space = y0 - y_ref
            else:
                cols = elements.group_by_columns()
                u0, v0, u1, v1 = cols[0].bbox
                m0, n0, m1, n1 = cols[1].bbox
                u = (u1 + m0) / 2.0
                y_top = min(c.bbox[1] for c in cols)
                y_bot = max(c.bbox[3] for c in cols)

                column_1 = Column().update_bbox((X0, v0, u, y_bot))
                column_1.add_elements(elements)

                column_2 = Column().update_bbox((u, y_top, X1, y_bot))
                column_2.add_elements(elements)

                section = Section(space=0, columns=[column_1, column_2])
                before_space = y_top - y_ref

            section.before_space = round(before_space, 1)
            return section

        RawPage._create_section = staticmethod(_safe_create_section)
        _PDF2DOCX_PATCHED = True
    except Exception:
        pass


def _run_hybrid_pdf2docx(
    src: Path,
    dst: Path,
    target_pages: List[int],
    total_doc_pages: int,
    progress_cb: ProgressCallback = None,
) -> None:
    """Chạy `pdf2docx` để phân tích cấu trúc đoạn văn, cột và bảng biểu."""
    import contextlib
    import io as _io
    import logging

    _install_pdf2docx_patches()

    total_target = len(target_pages)
    if progress_cb:
        progress_cb(
            0,
            total_target,
            f"Đang phân tích cấu trúc đoạn văn & bảng biểu ({total_target} trang)...",
        )

    logging.getLogger("pdf2docx").setLevel(logging.WARNING)
    with contextlib.redirect_stdout(_io.StringIO()), contextlib.redirect_stderr(_io.StringIO()):
        cv = Pdf2DocxConverter(str(src))
        try:
            is_all = len(target_pages) == total_doc_pages
            if is_all:
                cv.convert(str(dst))
            else:
                cv.convert(str(dst), pages=target_pages)
        finally:
            cv.close()

    if progress_cb:
        progress_cb(total_target, total_target, "Đã dựng xong cấu trúc DOCX cơ bản.")
