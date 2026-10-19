"""Engine Chuyển đổi Giữ nguyên Vị trí Tuyệt đối 1:1 (Exact Visual Frame Engine).

Cơ chế hoạt động:
1. Tách riêng lớp đồ hoạ nền (đường kẻ vector, khung biểu mẫu, hình ảnh, con dấu) của từng trang PDF
   bằng cách xoá lớp văn bản trên bản sao trong bộ nhớ (`apply_redactions` giữ nguyên ảnh & vector),
   sau đó kết xuất thành lớp nền sắc nét neo cố định phía sau chữ (`wp:anchor behindDoc="1"`).
2. Trích xuất toàn bộ các dòng văn bản (`get_text("dict")`) kèm toạ độ `bbox`, phông chữ, cỡ chữ,
   màu RGB, kiểu đậm/nghiêng.
3. Đặt từng dòng văn bản vào khung định vị tuyệt đối OpenXML (`<w:framePr>`) theo đúng toạ độ
   `(x, y, width, height)` tính bằng `twips` (`1 pt = 20 twips`) so với góc trên-trái của trang.
4. Kết quả: Khi mở trong Microsoft Word, bố cục giống bản PDF 100% tới từng milimet mà toàn bộ
   chữ vẫn là văn bản thật có thể bôi đen và chỉnh sửa.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Callable, List, Optional

import docx
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Emu, Pt, RGBColor
import fitz  # PyMuPDF

from qtpdfpro.core.font_resolver import normalize_vietnamese_text, resolve_pdf_font

ProgressCallback = Optional[Callable[[int, int, str], None]]


def convert_pdf_exact_layout(
    pdf_path: str | Path,
    docx_path: str | Path,
    pages: Optional[List[int]] = None,
    background_dpi: int = 180,
    default_font: str = "Times New Roman",
    normalize_vietnamese: bool = True,
    progress_cb: ProgressCallback = None,
) -> int:
    """Chuyển đổi PDF sang DOCX theo chế độ giữ nguyên vị trí tuyệt đối 1:1."""
    src_path = Path(pdf_path).resolve()
    out_path = Path(docx_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with fitz.open(str(src_path)) as pdf_doc:
        total_doc_pages = len(pdf_doc)
        target_pages = (
            [p for p in pages if 0 <= p < total_doc_pages]
            if pages is not None
            else list(range(total_doc_pages))
        )
        if not target_pages:
            target_pages = list(range(total_doc_pages))

        word_doc = docx.Document()
        # Xoá đoạn văn trống mặc định đầu tiên của python-docx
        if word_doc.paragraphs:
            p0 = word_doc.paragraphs[0]._element
            p0.getparent().remove(p0)

        total_target = len(target_pages)
        for idx, page_no in enumerate(target_pages):
            if progress_cb:
                progress_cb(
                    idx,
                    total_target,
                    f"Đang dựng bố cục 1:1 trang {page_no + 1}/{total_doc_pages}...",
                )

            page = pdf_doc[page_no]
            rect = page.rect
            w_pt = float(rect.width)
            h_pt = float(rect.height)

            if idx == 0:
                section = word_doc.sections[0]
            else:
                section = word_doc.add_section(WD_SECTION.NEW_PAGE)

            section.page_width = Pt(w_pt)
            section.page_height = Pt(h_pt)
            section.top_margin = Pt(12)
            section.bottom_margin = Pt(12)
            section.left_margin = Pt(12)
            section.right_margin = Pt(12)
            section.header_distance = Pt(0)
            section.footer_distance = Pt(0)

            # 1. Nếu trang có hình vẽ vector hoặc hình ảnh, tạo lớp nền phía sau chữ
            bg_png = _render_graphics_only_png(pdf_doc, page_no, dpi=background_dpi)
            anchor_para = word_doc.add_paragraph()
            _zero_paragraph_spacing(anchor_para)
            if bg_png is not None:
                _add_background_image_behind_text(
                    paragraph=anchor_para,
                    image_bytes=bg_png,
                    width_pt=w_pt,
                    height_pt=h_pt,
                    doc_id=idx + 1,
                )

            # 2. Trích xuất và đặt từng dòng văn bản vào khung toạ độ tuyệt đối <w:framePr>
            raw_dict = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
            for block in raw_dict.get("blocks", []):
                if block.get("type", 0) != 0:
                    continue
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    # Kiểm tra xem dòng có ký tự thực không
                    line_raw_text = "".join(s.get("text", "") for s in spans)
                    if not line_raw_text.strip():
                        continue

                    lbbox = line.get("bbox", (0, 0, 0, 0))
                    x0, y0, x1, y1 = (
                        float(lbbox[0]),
                        float(lbbox[1]),
                        float(lbbox[2]),
                        float(lbbox[3]),
                    )
                    box_w_pt = max(18.0, (x1 - x0) + 8.0)  # Cộng thêm 8pt đệm phải để không bị rớt chữ cuối
                    box_h_pt = max(10.0, (y1 - y0) + 3.0)

                    p = word_doc.add_paragraph()
                    _zero_paragraph_spacing(p)
                    _apply_frame_pr(
                        paragraph=p,
                        x_pt=max(0.0, x0),
                        y_pt=max(0.0, y0),
                        w_pt=min(w_pt - max(0.0, x0), box_w_pt),
                        h_pt=box_h_pt,
                    )

                    for span in spans:
                        raw_txt = span.get("text", "")
                        if not raw_txt:
                            continue
                        raw_font = span.get("font", "")
                        flags = int(span.get("flags", 0))
                        size_pt = max(5.0, float(span.get("size", 11.0)))
                        color_int = int(span.get("color", 0))

                        resolved = resolve_pdf_font(
                            raw_font, flags=flags, default_family=default_font
                        )
                        txt = (
                            normalize_vietnamese_text(raw_txt, raw_font, convert_legacy=True)
                            if normalize_vietnamese
                            else raw_txt
                        )
                        if not txt:
                            continue

                        run = p.add_run(txt)
                        run.font.name = resolved.family
                        run.font.size = Pt(round(size_pt * 2) / 2.0)
                        run.bold = resolved.is_bold
                        run.italic = resolved.is_italic

                        r = (color_int >> 16) & 0xFF
                        g = (color_int >> 8) & 0xFF
                        b = color_int & 0xFF
                        run.font.color.rgb = RGBColor(r, g, b)

                        # Gán đủ 4 thuộc tính phông chữ trong XML
                        rpr = run._r.get_or_add_rPr()
                        rfonts = rpr.find(qn("w:rFonts"))
                        if rfonts is None:
                            rfonts = OxmlElement("w:rFonts")
                            rpr.insert(0, rfonts)
                        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                            rfonts.set(qn(attr), resolved.family)

        if progress_cb:
            progress_cb(total_target, total_target, "Đang lưu tệp Word (.docx)...")
        word_doc.save(str(out_path))
        return total_target


def _render_graphics_only_png(
    src_doc: fitz.Document, page_no: int, dpi: int = 180
) -> Optional[bytes]:
    """Tạo ảnh PNG chỉ chứa đồ hoạ vector, khung bảng và hình ảnh (đã xoá chữ)."""
    page = src_doc[page_no]
    has_drawings = len(page.get_drawings()) > 0
    has_images = len(page.get_images()) > 0
    if not has_drawings and not has_images:
        return None

    with fitz.open() as temp_doc:
        temp_doc.insert_pdf(src_doc, from_page=page_no, to_page=page_no)
        tpage = temp_doc[0]
        tpage.add_redact_annot(tpage.rect, fill=False)
        tpage.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
        )
        scale = max(1.0, min(4.0, float(dpi) / 72.0))
        pix = tpage.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")


def _zero_paragraph_spacing(paragraph: docx.text.paragraph.Paragraph) -> None:
    pf = paragraph.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    ppr = paragraph._p.get_or_add_pPr()
    snap = OxmlElement("w:snapToGrid")
    snap.set(qn("w:val"), "0")
    ppr.append(snap)


def _apply_frame_pr(
    paragraph: docx.text.paragraph.Paragraph,
    x_pt: float,
    y_pt: float,
    w_pt: float,
    h_pt: float,
) -> None:
    """Định vị đoạn văn bằng `<w:framePr>` theo toạ độ tuyệt đối trên trang (đơn vị twips)."""
    ppr = paragraph._p.get_or_add_pPr()
    frame_pr = OxmlElement("w:framePr")
    frame_pr.set(qn("w:w"), str(max(200, int(round(w_pt * 20)))))
    frame_pr.set(qn("w:h"), str(max(120, int(round(h_pt * 20)))))
    frame_pr.set(qn("w:hRule"), "atLeast")
    frame_pr.set(qn("w:hSpace"), "0")
    frame_pr.set(qn("w:vSpace"), "0")
    frame_pr.set(qn("w:wrap"), "notBeside")
    frame_pr.set(qn("w:hAnchor"), "page")
    frame_pr.set(qn("w:vAnchor"), "page")
    frame_pr.set(qn("w:x"), str(max(0, int(round(x_pt * 20)))))
    frame_pr.set(qn("w:y"), str(max(0, int(round(y_pt * 20)))))
    ppr.insert(0, frame_pr)


def _add_background_image_behind_text(
    paragraph: docx.text.paragraph.Paragraph,
    image_bytes: bytes,
    width_pt: float,
    height_pt: float,
    doc_id: int,
) -> None:
    """Chèn ảnh đồ hoạ nền neo cố định tại góc (0, 0) của trang và nằm dưới lớp văn bản."""
    run = paragraph.add_run()
    inline_shape = run.add_picture(
        io.BytesIO(image_bytes),
        width=Pt(width_pt),
        height=Pt(height_pt),
    )

    # Chuyển wp:inline thành wp:anchor có behindDoc="1" tại toạ độ (0, 0) của trang
    drawing = run._r.find(qn("w:drawing"))
    if drawing is None:
        return
    inline = drawing.find(qn("wp:inline"))
    if inline is None:
        return

    cx = int(Emu(Pt(width_pt)))
    cy = int(Emu(Pt(height_pt)))
    graphic = inline.find(qn("a:graphic"))
    if graphic is None:
        return

    anchor_xml = (
        f'<wp:anchor {nsdecls("wp", "a")} '
        f'distT="0" distB="0" distL="0" distR="0" '
        f'simplePos="0" relativeHeight="1" behindDoc="1" '
        f'locked="0" layoutInCell="1" allowOverlap="1">'
        f'<wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionH>'
        f'<wp:positionV relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionV>'
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        f'<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:wrapNone/>'
        f'<wp:docPr id="{doc_id}" name="PageBackground_{doc_id}"/>'
        f'<wp:cNvGraphicFramePr/>'
        f"</wp:anchor>"
    )
    anchor_el = parse_xml(anchor_xml)
    anchor_el.append(graphic)
    drawing.remove(inline)
    drawing.append(anchor_el)
