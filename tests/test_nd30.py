"""Kiểm thử engine chuẩn thể thức Nghị định 30/2020/NĐ-CP (đo lề, đối chiếu, dựng DOCX giữ đúng PDF).

Dữ liệu: `samples/nd30/*.pdf` — văn bản mẫu (nội dung hư cấu) tạo bằng bộ sinh văn bản chuẩn NĐ30
rồi xuất PDF bằng Microsoft Word, nên biết trước thông số gốc:
- `quyet_dinh_mau.pdf`: lề 20/20/30/20 mm, cỡ 14, giãn dòng 1,5 lines, cách đoạn 6 pt, thụt 1 cm.
- `ke_hoach_mau.pdf`: lề 25/20/35/15 mm, cỡ 13, giãn dòng Exactly 18 pt, cách đoạn 0 pt, thụt 1,27 cm,
  có bảng dữ liệu có viền và ảnh con dấu đè lên chữ ký.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import fitz  # PyMuPDF
import pytest
from lxml import etree

from qtpdfpro.core.admin_layout import (
    ParaBlock,
    RuleBlock,
    TableBlock,
    analyze_admin_document,
    extract_rules,
    resolve_line_spacing,
)
from qtpdfpro.core.converter import ConversionOptions, convert_pdf_to_docx
from qtpdfpro.core.layout_verify import compare_pdf_layouts, verify_docx_layout
from qtpdfpro.core.nd30_standard import build_docx_plan, check_nd30_compliance, snap_margin_mm
from qtpdfpro.core.word_com_bridge import is_ms_word_available

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "nd30"
QD_PDF = SAMPLES / "quyet_dinh_mau.pdf"
KH_PDF = SAMPLES / "ke_hoach_mau.pdf"
CV_PDF = SAMPLES / "cong_van_mau.pdf"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def _analyze(pdf: Path):
    with fitz.open(str(pdf)) as doc:
        return analyze_admin_document(doc)


def _docx_xml(path: Path, part: str) -> etree._Element:
    with zipfile.ZipFile(path) as zf:
        return etree.fromstring(zf.read(part))


def test_resolve_line_spacing_prefers_exact_word_values() -> None:
    assert resolve_line_spacing(24.13, 14.0, 1.149) == ("auto", 1.5)
    assert resolve_line_spacing(16.09, 14.0, 1.149) == ("auto", 1.0)
    rule, value = resolve_line_spacing(18.0, 13.0, 1.149)
    assert (rule, value) == ("exact", 18.0)
    # Chính sách NĐ30 kẹp giãn dòng phần nội dung vào 1,0–1,5 lines
    assert resolve_line_spacing(40.0, 14.0, 1.149, policy="nd30") == ("auto", 1.5)


def test_snap_margin_faithful_vs_nd30() -> None:
    assert snap_margin_mm(29.98, (30, 35), "faithful") == 30.0
    assert snap_margin_mm(19.4, (30, 35), "faithful") == 19.4  # không ép lệch bố cục
    assert snap_margin_mm(19.4, (30, 35), "nd30") == 30.0


def test_extract_rules_detects_word_thin_rectangles() -> None:
    with fitz.open(str(QD_PDF)) as doc:
        rules = extract_rules(doc[0])
    widths = sorted(round(r.width) for r in rules)
    # Kẻ dưới tên cơ quan 35 mm, dưới Tiêu ngữ 50 mm, dưới trích yếu 30 mm
    assert widths == [85, 99, 142]


def test_measure_quyet_dinh_margins_spacing_and_components() -> None:
    ad = _analyze(QD_PDF)
    ml = ad.measured
    assert ad.is_admin and ad.header is not None and ad.sign is not None
    assert abs(ml.margin_top_mm - 20.0) <= 0.3
    assert abs(ml.margin_left_mm - 30.0) <= 0.3
    assert abs(ml.margin_right_mm - 20.0) <= 0.3
    assert ml.body_size == 14.0
    assert abs(ml.line_multiple - 1.5) <= 0.01
    assert ml.para_spacing_pt == pytest.approx(6.0, abs=0.3)
    assert abs((ml.first_indent_mm or 0) - 10.0) <= 0.3
    assert 1 in ml.page_number_pages and 0 not in ml.page_number_pages

    # Phần đầu: 2 hàng (Cơ quan | Quốc hiệu; Số | Địa danh), mỗi cột có đường kẻ riêng
    assert len(ad.header.rows) == 2
    left0, right0 = ad.header.rows[0]
    assert any(isinstance(it, RuleBlock) for it in left0)
    assert any(isinstance(it, RuleBlock) for it in right0)
    assert all(it.align == "center" for it in left0 + right0 if isinstance(it, ParaBlock))

    # Các đoạn "Căn cứ ..." liền nhau không bị gộp; đoạn văn bản căn đều 2 lề
    texts = [b.text for b in ad.blocks if isinstance(b, ParaBlock)]
    assert any(t.startswith("Căn cứ Luật") and "Nghị định" not in t for t in texts)
    assert any(b.align == "both" for b in ad.blocks if isinstance(b, ParaBlock))

    rep = check_nd30_compliance(ad)
    assert rep.is_admin_document
    assert rep.score >= 99.0
    assert rep.fail_count == 0


def test_plan_faithful_keeps_pdf_values_and_nd30_policy_standardizes() -> None:
    ad = _analyze(KH_PDF)
    faithful = build_docx_plan(ad, "faithful")
    assert (faithful.margin_top_mm, faithful.margin_left_mm, faithful.margin_right_mm) == (25.0, 35.0, 15.0)
    assert faithful.line_exact_pt == 18.0
    assert faithful.para_spacing_pt == 0.0
    assert faithful.first_indent_mm == 12.7

    rep = check_nd30_compliance(ad)
    spacing = next(c for c in rep.checks if c.code == "para_spacing")
    assert spacing.status == "fail"  # 0 pt < 6 pt theo NĐ30

    forced = build_docx_plan(ad, "nd30")
    assert forced.para_spacing_pt == 6.0
    assert any("cách đoạn" in n for n in forced.notes)


def test_convert_nd30_builds_standard_word_structure(tmp_path: Path) -> None:
    out = tmp_path / "quyet_dinh_nd30.docx"
    res = convert_pdf_to_docx(QD_PDF, out, ConversionOptions(mode="nd30"))
    assert res.mode_used == "nd30"
    assert res.fidelity.word_retention_ratio >= 0.99
    assert res.nd30_report is not None and res.nd30_report.score >= 99.0
    assert res.nd30_plan is not None and res.nd30_plan.margin_left_mm == 30.0

    root = _docx_xml(out, "word/document.xml")
    body = root.find(f"{W}body")
    # Lề trang đúng giá trị gốc (twips): trên 20 mm, trái 30 mm, phải 20 mm
    pg_mar = root.find(f".//{W}sectPr/{W}pgMar")
    assert abs(int(pg_mar.get(f"{W}top")) - 1134) <= 2
    assert abs(int(pg_mar.get(f"{W}left")) - 1701) <= 2
    assert abs(int(pg_mar.get(f"{W}right")) - 1134) <= 2
    assert root.find(f".//{W}sectPr/{W}titlePg") is not None  # không đánh số trang 1

    # Phần đầu là bảng 2 cột KHÔNG viền chứa Quốc hiệu
    first = body[0]
    assert first.tag == f"{W}tbl"
    borders = first.find(f"{W}tblPr/{W}tblBorders")
    assert borders is not None and all(b.get(f"{W}val") == "nil" for b in borders)
    head_text = "".join(t.text or "" for t in first.iter(f"{W}t"))
    assert "CỘNG HÒA XÃ HỘI CHỦ NGHĨA" in head_text and "Số: 125/QĐ-SGDĐT" in head_text
    # Không dựng phần đầu bằng nhiều section chia cột như pdf2docx
    assert len(list(root.iter(f"{W}sectPr"))) == 1

    # Đường kẻ là viền dưới đoạn văn (không phải ảnh) — 3 đường như PDF
    rule_paras = [p for p in root.iter(f"{W}p") if p.find(f"{W}pPr/{W}pBdr/{W}bottom") is not None]
    assert len(rule_paras) == 3

    # Đoạn văn: căn đều, thụt đầu dòng 1 cm (567 twips), giãn dòng 1,5 lines (360)
    dieu1 = next(p for p in root.iter(f"{W}p") if "".join(t.text or "" for t in p.iter(f"{W}t")).startswith("Điều 1."))
    ppr = dieu1.find(f"{W}pPr")
    assert ppr.find(f"{W}jc").get(f"{W}val") == "both"
    assert abs(int(ppr.find(f"{W}ind").get(f"{W}firstLine")) - 567) <= 2
    assert ppr.find(f"{W}spacing").get(f"{W}line") == "360"

    # Chế độ bố cục Word 2013+ & số trang là trường PAGE ở đầu trang
    settings = _docx_xml(out, "word/settings.xml")
    modes = [cs.get(f"{W}val") for cs in settings.iter(f"{W}compatSetting") if cs.get(f"{W}name") == "compatibilityMode"]
    assert modes == ["15"]
    with zipfile.ZipFile(out) as zf:
        headers = [n for n in zf.namelist() if n.startswith("word/header")]
        assert any("PAGE" in zf.read(n).decode("utf-8") for n in headers)


def test_convert_nd30_data_table_and_stamp(tmp_path: Path) -> None:
    out = tmp_path / "ke_hoach_nd30.docx"
    res = convert_pdf_to_docx(KH_PDF, out, ConversionOptions(mode="nd30"))
    assert res.mode_used == "nd30"
    root = _docx_xml(out, "word/document.xml")
    tables = list(root.iter(f"{W}tbl"))
    bordered = [
        t for t in tables
        if any(b.get(f"{W}val") == "single" for b in t.iter() if b.getparent() is not None and b.getparent().tag == f"{W}tblBorders")
    ]
    assert len(bordered) == 1
    cell_text = "".join(t.text or "" for t in bordered[0].iter(f"{W}t"))
    assert "Nội dung công việc" in cell_text and "Thanh tra Sở" in cell_text
    # Con dấu giữ nguyên dạng ảnh nổi neo theo đoạn
    anchors = list(root.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}anchor"))
    assert len(anchors) == 1
    # Giữ đúng giãn dòng "Exactly 18 pt" (360 twips) của văn bản gốc
    assert any(
        sp.get(f"{W}lineRule") == "exact" and sp.get(f"{W}line") == "360" for sp in root.iter(f"{W}spacing")
    )


def test_auto_mode_picks_nd30_for_admin_document(tmp_path: Path) -> None:
    res = convert_pdf_to_docx(CV_PDF, tmp_path / "cv.docx", ConversionOptions(mode="auto"))
    assert res.mode_used == "nd30"
    assert res.fidelity.overall_score >= 99.0


def test_compare_identical_pdfs_is_match() -> None:
    rep = compare_pdf_layouts(QD_PDF, QD_PDF)
    assert rep.verdict == "match"
    assert rep.matched_lines == rep.pdf_lines and rep.max_dy_pt == 0.0


@pytest.mark.skipif(not is_ms_word_available(), reason="Cần Microsoft Word để dựng lại DOCX")
def test_nd30_docx_matches_pdf_when_rendered_by_word(tmp_path: Path) -> None:
    out = tmp_path / "cv_verify.docx"
    convert_pdf_to_docx(CV_PDF, out, ConversionOptions(mode="nd30"))
    rep = verify_docx_layout(CV_PDF, out)
    assert rep.available
    assert rep.verdict == "match", rep.samples
    assert rep.pdf_pages == rep.docx_pages
    assert rep.max_dy_pt <= 1.5 and rep.max_dx_pt <= 1.5


def test_table_block_detected_in_ke_hoach() -> None:
    ad = _analyze(KH_PDF)
    assert any(isinstance(b, TableBlock) for b in ad.blocks)
    assert len(ad.floating_images) == 1
