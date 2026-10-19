"""Bộ Hậu xử lý Chuẩn xác OpenXML (QT OpenXML Precision Fixer).

Can thiệp trực tiếp vào cấu trúc XML của tệp `.docx` (`word/document.xml`, `word/styles.xml`)
bằng `lxml` để khắc phục triệt để các nguyên nhân làm lệch bố cục khi mở trong Microsoft Word:
1. Chuẩn hoá tên phông PDF/PostScript/Subset sang phông chuẩn Windows trên cả 4 thuộc tính
   (`w:ascii`, `w:hAnsi`, `w:cs`, `w:eastAsia`) và khôi phục cờ Đậm/Nghiêng từ tên phông.
2. Chuẩn hoá văn bản tiếng Việt sang Unicode dựng sẵn (NFC) và chuyển mã TCVN3 (.Vn*) nếu có.
3. Tắt `w:snapToGrid` trên đoạn văn và lưới trang (`w:docGrid`) để chống giãn dòng tự động.
4. Tinh chỉnh khoảng đệm ô bảng (`w:tcMar` / `w:tblCellMar`) và khoá `w:tblLayout="fixed"`
   để chữ trong ô bảng không bị ép rớt dòng.
5. Tinh chỉnh khoảng cách ký tự vi mô (`w:spacing`) và lề phân đoạn (`w:pgMar`) chống tràn trang.
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Set

from lxml import etree

from qtpdfpro.core.font_resolver import normalize_vietnamese_text, resolve_pdf_font

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W = f"{{{W_NS}}}"
XML_SPACE = f"{{{XML_NS}}}space"


@dataclass
class OpenXMLFixReport:
    """Thống kê kết quả tinh chỉnh OpenXML trên tệp DOCX."""

    fonts_normalized: int = 0
    text_nodes_normalized: int = 0
    paragraphs_tuned: int = 0
    tables_tuned: int = 0
    sections_tuned: int = 0
    font_mapping: Dict[str, str] = field(default_factory=dict)


def fix_docx_package(
    docx_path: str | Path,
    default_font: str = "Times New Roman",
    normalize_vietnamese: bool = True,
    fix_table_padding: bool = True,
    prevent_line_overflow: bool = True,
) -> OpenXMLFixReport:
    """Tinh chỉnh gói `.docx` tại chỗ để đạt độ chính xác bố cục cao nhất trong Word."""
    path = Path(docx_path).resolve()
    report = OpenXMLFixReport()

    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    tmp_dir = Path(tempfile.mkdtemp(prefix="qtpdf_docx_"))
    try:
        with zipfile.ZipFile(path, "r") as zin:
            zin.extractall(tmp_dir)

        for rel_xml in ("word/document.xml", "word/styles.xml"):
            xml_file = tmp_dir / rel_xml
            if not xml_file.exists():
                continue

            tree = etree.parse(str(xml_file), parser)
            root = tree.getroot()

            if rel_xml == "word/document.xml":
                _tune_document_xml(
                    root=root,
                    report=report,
                    default_font=default_font,
                    normalize_vietnamese=normalize_vietnamese,
                    fix_table_padding=fix_table_padding,
                    prevent_line_overflow=prevent_line_overflow,
                )
            else:
                _tune_styles_xml(root=root, report=report, default_font=default_font)

            tree.write(
                str(xml_file),
                xml_declaration=True,
                encoding="UTF-8",
                standalone="yes",
            )

        # Đóng gói lại thành tệp .docx
        tmp_out = tmp_dir / "fixed_out.docx"
        with zipfile.ZipFile(tmp_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in sorted(tmp_dir.rglob("*")):
                if item == tmp_out or item.is_dir():
                    continue
                arcname = item.relative_to(tmp_dir).as_posix()
                zout.write(item, arcname)

        shutil.move(str(tmp_out), str(path))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return report


def _tune_styles_xml(root: etree._Element, report: OpenXMLFixReport, default_font: str) -> None:
    """Chuẩn hoá các khai báo phông mặc định trong `word/styles.xml`."""
    for rfonts in root.iter(f"{W}rFonts"):
        raw = (
            rfonts.get(f"{W}ascii")
            or rfonts.get(f"{W}hAnsi")
            or rfonts.get(f"{W}eastAsia")
            or rfonts.get(f"{W}cs")
            or default_font
        )
        resolved = resolve_pdf_font(raw, default_family=default_font)
        for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
            rfonts.set(f"{W}{attr}", resolved.family)
        for theme_attr in ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme"):
            rfonts.attrib.pop(f"{W}{theme_attr}", None)


def _tune_document_xml(
    root: etree._Element,
    report: OpenXMLFixReport,
    default_font: str,
    normalize_vietnamese: bool,
    fix_table_padding: bool,
    prevent_line_overflow: bool,
) -> None:
    """Tinh chỉnh toàn diện `word/document.xml`: phông chữ, đoạn văn, bảng biểu và phân đoạn."""
    # 1. Xử lý tất cả các Run (<w:r>)
    for run in root.iter(f"{W}r"):
        rpr = run.find(f"{W}rPr")
        if rpr is None:
            rpr = etree.Element(f"{W}rPr")
            run.insert(0, rpr)

        rfonts = rpr.find(f"{W}rFonts")
        raw_font_name = ""
        if rfonts is not None:
            raw_font_name = (
                rfonts.get(f"{W}ascii")
                or rfonts.get(f"{W}hAnsi")
                or rfonts.get(f"{W}eastAsia")
                or rfonts.get(f"{W}cs")
                or ""
            )
        else:
            rfonts = etree.SubElement(rpr, f"{W}rFonts")

        resolved = resolve_pdf_font(raw_font_name, default_family=default_font)
        if raw_font_name and raw_font_name != resolved.family:
            report.font_mapping[raw_font_name] = resolved.family
        report.fonts_normalized += 1

        for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
            rfonts.set(f"{W}{attr}", resolved.family)
        for theme_attr in ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme"):
            rfonts.attrib.pop(f"{W}{theme_attr}", None)

        # Khôi phục Bold / Italic nếu tên phông gốc có chỉ định nhưng thẻ XML bị thiếu
        if resolved.is_bold and rpr.find(f"{W}b") is None:
            etree.SubElement(rpr, f"{W}b")
        if resolved.is_italic and rpr.find(f"{W}i") is None:
            etree.SubElement(rpr, f"{W}i")

        # Chuẩn hoá văn bản tiếng Việt trong các nút <w:t> của Run này
        total_run_chars = 0
        for t_node in run.findall(f"{W}t"):
            txt = t_node.text or ""
            if txt:
                if normalize_vietnamese:
                    new_txt = normalize_vietnamese_text(
                        txt, font_name=raw_font_name, convert_legacy=True
                    )
                    if new_txt != txt:
                        t_node.text = new_txt
                        txt = new_txt
                report.text_nodes_normalized += 1
                total_run_chars += len(txt)
                if txt.startswith(" ") or txt.endswith(" "):
                    t_node.set(XML_SPACE, "preserve")

        # Tinh chỉnh khoảng cách ký tự vi mô (-1 twip = -0.05pt) cho chuỗi dài để chống rớt từ cuối dòng
        if prevent_line_overflow and total_run_chars >= 28:
            char_spacing = rpr.find(f"{W}spacing")
            if char_spacing is None:
                char_spacing = etree.SubElement(rpr, f"{W}spacing")
                char_spacing.set(f"{W}val", "-2")
            else:
                try:
                    cur_val = int(char_spacing.get(f"{W}val", "0"))
                    if cur_val > 0 and cur_spacing_is_excessive(cur_val):
                        char_spacing.set(f"{W}val", "0")
                except ValueError:
                    pass

    # 2. Tinh chỉnh các Đoạn văn (<w:p>)
    for para in root.iter(f"{W}p"):
        ppr = para.find(f"{W}pPr")
        if ppr is None:
            ppr = etree.Element(f"{W}pPr")
            para.insert(0, ppr)

        # Tắt bắt dính lưới dòng để Word không tự kéo giãn chiều cao dòng
        snap = ppr.find(f"{W}snapToGrid")
        if snap is None:
            snap = etree.SubElement(ppr, f"{W}snapToGrid")
        snap.set(f"{W}val", "0")

        # Kiểm tra khoảng cách dòng <w:spacing> để không cắt dấu mũ tiếng Việt mà vẫn gọn trang
        spacing = ppr.find(f"{W}spacing")
        if spacing is not None and prevent_line_overflow:
            line_rule = spacing.get(f"{W}lineRule", "")
            line_val_str = spacing.get(f"{W}line", "")
            max_sz_half_pt = _get_max_font_size_half_pt(para)
            if line_val_str and max_sz_half_pt > 0:
                try:
                    line_twips = int(line_val_str)
                    font_twips = max_sz_half_pt * 10  # 1 half-pt = 10 twips
                    # Nếu exact line nhỏ hơn 1.05 lần cỡ chữ thì đổi sang atLeast để không mất dấu tiếng Việt
                    if line_rule == "exact" and line_twips < int(font_twips * 1.05):
                        spacing.set(f"{W}line", str(int(font_twips * 1.08)))
                    # Nếu khoảng cách sau đoạn (after) quá lớn bất thường (> 24pt = 480 twips), kẹp nhẹ lại
                    after_str = spacing.get(f"{W}after", "")
                    if after_str and int(after_str) > 360:
                        spacing.set(f"{W}after", str(int(int(after_str) * 0.92)))
                except ValueError:
                    pass

        report.paragraphs_tuned += 1

    # 3. Tinh chỉnh Bảng biểu (<w:tbl>)
    if fix_table_padding:
        for tbl in root.iter(f"{W}tbl"):
            tbl_pr = tbl.find(f"{W}tblPr")
            if tbl_pr is None:
                tbl_pr = etree.Element(f"{W}tblPr")
                tbl.insert(0, tbl_pr)

            # Khoá bố cục bảng cố định theo độ rộng cột của PDF
            tbl_layout = tbl_pr.find(f"{W}tblLayout")
            if tbl_layout is None:
                tbl_layout = etree.SubElement(tbl_pr, f"{W}tblLayout")
            tbl_layout.set(f"{W}type", "fixed")

            # Giảm khoảng đệm mặc định của bảng (từ 108 dxa xuống 36 dxa ≈ 1.8pt)
            cell_mar = tbl_pr.find(f"{W}tblCellMar")
            if cell_mar is None:
                cell_mar = etree.SubElement(tbl_pr, f"{W}tblCellMar")
            _set_cell_margins(cell_mar, top=20, bottom=20, left=36, right=36)

            # Tinh chỉnh từng ô <w:tc>
            for tc in tbl.iter(f"{W}tc"):
                tc_pr = tc.find(f"{W}tcPr")
                if tc_pr is None:
                    tc_pr = etree.Element(f"{W}tcPr")
                    tc.insert(0, tc_pr)
                tc_mar = tc_pr.find(f"{W}tcMar")
                if tc_mar is not None:
                    _clamp_existing_cell_margins(tc_mar, max_lr=40, max_tb=30)

            report.tables_tuned += 1

    # 4. Tinh chỉnh Phân đoạn & Lề trang (<w:sectPr>)
    for sect_pr in root.iter(f"{W}sectPr"):
        pg_mar = sect_pr.find(f"{W}pgMar")
        if pg_mar is not None:
            # Đặt khoảng cách header/footer = 0 để không đẩy lề trên/dưới của trang
            pg_mar.set(f"{W}header", "0")
            pg_mar.set(f"{W}footer", "0")
            if prevent_line_overflow:
                # Giảm nhẹ lề dưới (tối đa 80 twips = 4pt) để bù sai số chiều cao dòng giữa PDF và Word
                try:
                    bot = int(pg_mar.get(f"{W}bottom", "720"))
                    if bot > 160:
                        pg_mar.set(f"{W}bottom", str(max(120, bot - 80)))
                except ValueError:
                    pass

        doc_grid = sect_pr.find(f"{W}docGrid")
        if doc_grid is None:
            doc_grid = etree.SubElement(sect_pr, f"{W}docGrid")
        doc_grid.set(f"{W}type", "default")
        report.sections_tuned += 1


def cur_spacing_is_excessive(val_twips: int) -> bool:
    """Kiểm tra nếu khoảng giãn chữ cái quá lớn (> 2pt = 40 twips) gây rớt dòng."""
    return val_twips > 40


def _get_max_font_size_half_pt(para: etree._Element) -> int:
    max_sz = 0
    for sz in para.iter(f"{W}sz"):
        val = sz.get(f"{W}val", "")
        try:
            v = int(val)
            if v > max_sz:
                max_sz = v
        except ValueError:
            pass
    return max_sz


def _set_cell_margins(mar_elem: etree._Element, top: int, bottom: int, left: int, right: int) -> None:
    for side, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        node = mar_elem.find(f"{W}{side}")
        if node is None:
            node = etree.SubElement(mar_elem, f"{W}{side}")
        node.set(f"{W}w", str(val))
        node.set(f"{W}type", "dxa")


def _clamp_existing_cell_margins(mar_elem: etree._Element, max_lr: int, max_tb: int) -> None:
    for side, limit in (("left", max_lr), ("right", max_lr), ("top", max_tb), ("bottom", max_tb)):
        node = mar_elem.find(f"{W}{side}")
        if node is not None:
            try:
                cur = int(node.get(f"{W}w", "0"))
                if cur > limit:
                    node.set(f"{W}w", str(limit))
            except ValueError:
                pass
