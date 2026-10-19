"""Kiểm thử chuyên sâu chuyển đổi PDF sang DOCX đa chế độ và kiểm định độ chính xác (Fidelity)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from lxml import etree
import pytest

from qtpdfpro.cli import main as cli_main
from qtpdfpro.core.converter import (
    ConversionError,
    ConversionOptions,
    convert_pdf_to_docx,
    parse_page_range,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def test_parse_page_range() -> None:
    assert parse_page_range("", 5) == [0, 1, 2, 3, 4]
    assert parse_page_range("all", 3) == [0, 1, 2]
    assert parse_page_range("1-2, 4", 5) == [0, 1, 3]
    assert parse_page_range("3-1", 4) == [0, 1, 2]
    with pytest.raises(ConversionError):
        parse_page_range("abc", 5)
    with pytest.raises(ConversionError):
        parse_page_range("9-10", 3)


def test_convert_hybrid_mode_preserves_vietnamese_tables_and_openxml_rules(
    sample_vietnamese_pdf: Path, tmp_path: Path
) -> None:
    out_docx = tmp_path / "output_hybrid.docx"
    opts = ConversionOptions(mode="hybrid")
    res = convert_pdf_to_docx(sample_vietnamese_pdf, out_docx, options=opts)

    assert out_docx.exists()
    assert res.mode_used == "hybrid"
    assert res.pages_converted == 2
    assert res.fidelity.overall_score >= 92.0
    assert res.fidelity.word_retention_ratio >= 0.95
    assert res.fidelity.page_size_match is True
    assert res.fidelity.docx_tables >= 1
    assert res.fidelity.docx_images >= 1

    # Kiểm tra cấu trúc XML bên trong tệp DOCX sau khi qua OpenXML Precision Fixer
    with zipfile.ZipFile(out_docx, "r") as zf:
        xml_bytes = zf.read("word/document.xml")
    root = etree.fromstring(xml_bytes)

    all_text = " ".join(t.text for t in root.iter(f"{W}t") if t.text)
    assert "CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM" in all_text
    assert "Độc lập - Tự do - Hạnh phúc" in all_text
    assert "Bảo toàn phông chữ tiếng Việt" in all_text

    # Mọi thẻ w:rFonts không còn tiền tố subset '+' và phải có đủ 4 thuộc tính phông
    rfonts_list = list(root.iter(f"{W}rFonts"))
    assert len(rfonts_list) > 0
    for rf in rfonts_list:
        ascii_f = rf.get(f"{W}ascii", "")
        assert "+" not in ascii_f
        assert rf.get(f"{W}hAnsi") == ascii_f
        assert rf.get(f"{W}cs") == ascii_f
        assert rf.get(f"{W}eastAsia") == ascii_f

    # Bảng biểu phải có w:tblLayout w:type="fixed"
    tbl_layouts = list(root.iter(f"{W}tblLayout"))
    assert any(tl.get(f"{W}type") == "fixed" for tl in tbl_layouts)


def test_convert_exact_frame_mode_preserves_1to1_positions(
    sample_vietnamese_pdf: Path, tmp_path: Path
) -> None:
    out_docx = tmp_path / "output_exact.docx"
    opts = ConversionOptions(mode="exact", pages=[0], exact_background_dpi=144)
    res = convert_pdf_to_docx(sample_vietnamese_pdf, out_docx, options=opts)

    assert out_docx.exists()
    assert res.mode_used == "exact"
    assert res.pages_converted == 1
    assert res.fidelity.overall_score >= 95.0
    assert res.fidelity.word_retention_ratio >= 0.98
    assert res.fidelity.docx_frames >= 5
    assert res.fidelity.docx_images >= 1  # Lớp nền đồ hoạ vector/ảnh phía sau chữ


def test_cli_convert_inspect_and_verify(
    sample_vietnamese_pdf: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_docx = tmp_path / "cli_out.docx"

    rc1 = cli_main(["convert", str(sample_vietnamese_pdf), "-o", str(out_docx), "--mode", "auto", "--json"])
    assert rc1 == 0
    conv_json = json.loads(capsys.readouterr().out)
    assert conv_json["pages_converted"] == 2
    assert conv_json["overall_score"] >= 90.0

    rc2 = cli_main(["inspect", str(sample_vietnamese_pdf), "--json"])
    assert rc2 == 0
    insp_json = json.loads(capsys.readouterr().out)
    assert insp_json["page_count"] == 2
    assert insp_json["bookmarks"] == 3

    rc3 = cli_main(["verify", str(sample_vietnamese_pdf), str(out_docx), "--json"])
    assert rc3 == 0
    ver_json = json.loads(capsys.readouterr().out)
    assert ver_json["overall_score"] >= 90.0
