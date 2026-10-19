"""Bộ Kiểm định Độ chính xác sau chuyển đổi (Fidelity Inspector).

Đối chiếu tệp PDF gốc và tệp DOCX đầu ra để đo lường mức độ bảo toàn nội dung và bố cục:
- Tỷ lệ bảo toàn từ vựng & ký tự (Text Retention %)
- Tỷ lệ khớp kích thước trang / phân đoạn
- Số lượng bảng biểu, hình ảnh, đoạn văn, khung định vị
- Danh sách phông chữ chuẩn hoá trong DOCX
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Counter as CounterType, List, Optional
from collections import Counter

from lxml import etree
import fitz  # PyMuPDF

from qtpdfpro.core.font_resolver import normalize_vietnamese_text

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
W = f"{{{W_NS}}}"
A = f"{{{A_NS}}}"

_WORD_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


@dataclass
class FidelityReport:
    """Báo cáo định lượng độ chính xác giữa PDF gốc và DOCX đầu ra."""

    pdf_pages_converted: int = 0
    docx_sections: int = 0
    pdf_char_count: int = 0
    docx_char_count: int = 0
    pdf_word_count: int = 0
    docx_word_count: int = 0
    word_retention_ratio: float = 1.0  # 0.0 -> 1.0
    char_retention_ratio: float = 1.0  # 0.0 -> 1.0
    page_size_match: bool = True
    docx_paragraphs: int = 0
    docx_tables: int = 0
    docx_frames: int = 0
    docx_images: int = 0
    docx_fonts: List[str] = field(default_factory=list)
    overall_score: float = 100.0  # Thang điểm 0.0 -> 100.0
    notes: List[str] = field(default_factory=list)


def evaluate_conversion_fidelity(
    pdf_path: str | Path,
    docx_path: str | Path,
    pages: Optional[List[int]] = None,
) -> FidelityReport:
    """So sánh tệp PDF nguồn và tệp DOCX đích để tạo báo cáo độ chính xác."""
    report = FidelityReport()
    src_path = Path(pdf_path).resolve()
    out_path = Path(docx_path).resolve()

    if not src_path.exists() or not out_path.exists():
        report.overall_score = 0.0
        report.notes.append("Không tìm thấy tệp nguồn hoặc tệp đích.")
        return report

    # 1. Trích xuất thông tin từ PDF nguồn
    pdf_texts: list[str] = []
    first_page_size_pt: tuple[float, float] = (595.0, 842.0)
    with fitz.open(str(src_path)) as pdf_doc:
        total = len(pdf_doc)
        target_pages = (
            [p for p in pages if 0 <= p < total]
            if pages is not None
            else list(range(total))
        )
        if not target_pages:
            target_pages = list(range(total))
        report.pdf_pages_converted = len(target_pages)
        first_rect = pdf_doc[target_pages[0]].rect
        first_page_size_pt = (float(first_rect.width), float(first_rect.height))

        for pno in target_pages:
            raw_txt = pdf_doc[pno].get_text("text")
            pdf_texts.append(normalize_vietnamese_text(raw_txt))

    full_pdf_text = "\n".join(pdf_texts)
    pdf_tokens = [t.lower() for t in _WORD_TOKEN_RE.findall(full_pdf_text)]
    pdf_non_ws_chars = re.sub(r"\s+", "", full_pdf_text)
    report.pdf_word_count = len(pdf_tokens)
    report.pdf_char_count = len(pdf_non_ws_chars)

    # 2. Phân tích cấu trúc XML bên trong tệp .docx
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    docx_texts: list[str] = []
    fonts_found: set[str] = set()

    with zipfile.ZipFile(out_path, "r") as zf:
        media_files = [n for n in zf.namelist() if n.startswith("word/media/")]
        report.docx_images = len(media_files)

        if "word/document.xml" in zf.namelist():
            xml_bytes = zf.read("word/document.xml")
            root = etree.fromstring(xml_bytes, parser)

            report.docx_paragraphs = len(list(root.iter(f"{W}p")))
            report.docx_tables = len(list(root.iter(f"{W}tbl")))
            report.docx_frames = len(list(root.iter(f"{W}framePr")))
            sect_prs = list(root.iter(f"{W}sectPr"))
            report.docx_sections = max(1, len(sect_prs))

            for t_el in root.iter(f"{W}t"):
                if t_el.text:
                    docx_texts.append(normalize_vietnamese_text(t_el.text))

            for rfonts in root.iter(f"{W}rFonts"):
                fname = rfonts.get(f"{W}ascii") or rfonts.get(f"{W}hAnsi")
                if fname:
                    fonts_found.add(fname)

            # Kiểm tra khớp kích thước trang đầu tiên (sai số <= 5pt = 100 twips)
            if sect_prs:
                pg_sz = sect_prs[0].find(f"{W}pgSz")
                if pg_sz is not None:
                    try:
                        w_pt = int(pg_sz.get(f"{W}w", "0")) / 20.0
                        h_pt = int(pg_sz.get(f"{W}h", "0")) / 20.0
                        if (
                            abs(w_pt - first_page_size_pt[0]) <= 6.0
                            and abs(h_pt - first_page_size_pt[1]) <= 6.0
                        ):
                            report.page_size_match = True
                        else:
                            report.page_size_match = False
                    except ValueError:
                        pass

    report.docx_fonts = sorted(fonts_found)
    full_docx_text = " ".join(docx_texts)
    docx_tokens = [t.lower() for t in _WORD_TOKEN_RE.findall(full_docx_text)]
    docx_non_ws_chars = re.sub(r"\s+", "", full_docx_text)
    report.docx_word_count = len(docx_tokens)
    report.docx_char_count = len(docx_non_ws_chars)

    # 3. Tính tỷ lệ bảo toàn từ vựng (Multiset Bag-of-Words overlap)
    if report.pdf_word_count == 0:
        report.word_retention_ratio = 1.0
        report.char_retention_ratio = 1.0
        if report.docx_images > 0:
            report.notes.append("Tài liệu dạng ảnh/scan (đã giữ nguyên hình ảnh).")
    else:
        pdf_counter: CounterType[str] = Counter(pdf_tokens)
        docx_counter: CounterType[str] = Counter(docx_tokens)
        matched_words = sum((pdf_counter & docx_counter).values())
        report.word_retention_ratio = min(1.0, matched_words / max(1, report.pdf_word_count))

        pdf_char_counter: CounterType[str] = Counter(pdf_non_ws_chars.lower())
        docx_char_counter: CounterType[str] = Counter(docx_non_ws_chars.lower())
        matched_chars = sum((pdf_char_counter & docx_char_counter).values())
        report.char_retention_ratio = min(1.0, matched_chars / max(1, report.pdf_char_count))

    # 4. Chấm điểm tổng hợp (thang 100)
    text_score = (0.65 * report.word_retention_ratio + 0.35 * report.char_retention_ratio) * 85.0
    layout_score = 10.0 if report.page_size_match else 5.0
    font_score = 5.0 if all("+" not in f for f in report.docx_fonts) else 1.0
    report.overall_score = round(min(100.0, text_score + layout_score + font_score), 1)

    if report.overall_score >= 95.0:
        report.notes.append("Độ chính xác xuất sắc: Bảo toàn đầy đủ văn bản, phông chữ và kích thước trang.")
    elif report.overall_score >= 85.0:
        report.notes.append("Độ chính xác tốt: Hầu hết các thành phần được giữ nguyên.")
    else:
        report.notes.append(
            "Lưu ý: Một số thành phần phức tạp có thể khác biệt; thử chuyển bằng chế độ 'Giữ vị trí tuyệt đối 1:1'."
        )

    return report
