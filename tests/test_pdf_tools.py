"""Kiểm thử công cụ văn phòng: nén (`core/compress.py`), dấu nước & đánh số trang (`core/page_stamp.py`),
đặt / gỡ mật khẩu (`core/pdf_security.py`) và các lệnh CLI compress / watermark / number / protect / unlock."""

from __future__ import annotations

import json
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytest

from qtpdfpro.cli import main as cli_main
from qtpdfpro.core import compress, page_stamp as ps, pdf_io, pdf_security as sec


def _make_pdf(path: Path, pages: int = 3, rotations=None, signed: bool = False) -> Path:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"Noi dung trang {i + 1}", fontsize=14)
        if rotations:
            page.set_rotation(rotations[i])
    if signed:  # cờ /SigFlags của AcroForm như tệp đã ký số
        doc.xref_set_key(doc.pdf_catalog(), "AcroForm", "<</Fields[]/SigFlags 3>>")
    doc.save(str(path))
    doc.close()
    return path


def _make_image_pdf(path: Path) -> Path:
    """PDF 1 trang chứa ảnh RGB lớn (~260 dpi trên trang A4) — nén phải nhỏ đi rõ rệt."""
    h, w = 1600, 1200
    y, x = np.mgrid[0:h, 0:w]
    img = np.stack([x * 255 // w, y * 255 // h, (x + y) * 255 // (w + h)], axis=-1)
    img = np.clip(img + np.random.default_rng(1).integers(-24, 24, img.shape), 0, 255).astype(np.uint8)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(72, 72, 402, 512), pixmap=fitz.Pixmap(fitz.csRGB, w, h, img.tobytes(), False))
    page.insert_text((72, 560), "Anh minh hoa", fontsize=12)
    doc.save(str(path), deflate=True)
    doc.close()
    return path


def _lines(page: fitz.Page) -> list[tuple[str, fitz.Rect, tuple, dict]]:
    """(chữ, khung theo trang đang hiển thị, hướng chữ theo trang hiển thị, span đầu) của từng dòng."""
    out = []
    m = page.rotation_matrix
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"])
            d = fitz.Point(line["dir"]) * m - fitz.Point(0, 0) * m
            out.append((text, fitz.Rect(line["bbox"]) * m, (round(d.x, 3), round(d.y, 3)), line["spans"][0]))
    return out


# ─── Nén ──────────────────────────────────────────────────────────────────


def test_compress_reduces_large_image(tmp_path: Path) -> None:
    src = _make_image_pdf(tmp_path / "anh.pdf")
    res = compress.compress_pdf(src, level="vua")
    out = Path(res.output_path)
    assert res.written and out.name == "anh_nen.pdf"
    assert res.output_size == out.stat().st_size < res.input_size * 0.5
    assert res.saved_ratio > 0.5 and "Vừa" in res.note
    with fitz.open(str(out)) as doc:
        assert "Anh minh hoa" in doc[0].get_text()
        assert len(doc[0].get_images()) == 1
    strong = compress.compress_pdf(src, tmp_path / "manh.pdf", level="manh")
    assert strong.output_size < res.output_size
    with pytest.raises(pdf_io.PdfToolError):
        compress.resolve_level("cuc_manh")


def test_compress_not_written_when_not_smaller(tmp_path: Path, monkeypatch) -> None:
    src = _make_pdf(tmp_path / "nho.pdf", 1)
    monkeypatch.setattr(compress, "compress_document", lambda doc, level="medium": b"%PDF" + b"0" * 100000)
    res = compress.compress_pdf(src, tmp_path / "kq.pdf")
    assert not res.written and res.output_path == ""
    assert not (tmp_path / "kq.pdf").exists()
    assert "không ghi tệp" in res.note


def test_tools_refuse_signed_without_force_and_source_overwrite(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path / "da_ky.pdf", 1, signed=True)
    with pytest.raises(pdf_io.SignedDocumentError):
        compress.compress_pdf(src, tmp_path / "a.pdf")
    with pytest.raises(pdf_io.SignedDocumentError):
        ps.watermark_pdf(src, tmp_path / "b.pdf")
    with pytest.raises(pdf_io.SignedDocumentError):
        sec.protect_pdf(src, tmp_path / "c.pdf", sec.ProtectOptions("1"))
    assert ps.number_pages(src, tmp_path / "d.pdf", allow_signed=True).written
    # Không ghi đè tệp nguồn (kể cả khác hoa/thường trên Windows)
    with pytest.raises(pdf_io.PdfToolError):
        ps.watermark_pdf(src, src, allow_signed=True)
    with pytest.raises(pdf_io.PdfToolError):
        pdf_io.resolve_output(src, tmp_path / "DA_KY.PDF", "_x")
    assert pdf_io.resolve_output(src, None, "_nen").name == "da_ky_nen.pdf"
    assert pdf_io.format_size(1536) == "1,50 KB" and pdf_io.format_size(800) == "800 B"


# ─── Dấu nước ─────────────────────────────────────────────────────────────


def test_watermark_vietnamese_text_pages_and_rotation(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path / "goc.pdf", 4, rotations=[0, 90, 0, 270])
    opts = ps.WatermarkOptions(text="BẢN SAO\nLƯU HÀNH NỘI BỘ Ỷ", font_size=40, opacity=0.25, angle=45,
                               color="#DC2626", pages="1-2,4")
    res = ps.watermark_pdf(src, options=opts)
    assert res.written and res.pages_changed == 3 and Path(res.output_path).name == "goc_dau_nuoc.pdf"
    with fitz.open(res.output_path) as doc:
        for pno in (0, 1, 3):
            page = doc[pno]
            text = page.get_text()
            assert "BẢN SAO" in text and "LƯU HÀNH NỘI BỘ Ỷ" in text  # đúng dấu, dấu cách thường
            marks = [ln for ln in _lines(page) if ln[0] == "BẢN SAO"]
            assert len(marks) == 1
            _t, bbox, direction, span = marks[0]
            assert direction == (0.707, -0.707)  # chữ chéo lên 45° như người đọc nhìn thấy
            assert abs(span["size"] - 40) < 0.1 and "Arial" in span["font"]
            assert abs((bbox.x0 + bbox.x1) / 2 - page.rect.width / 2) < 60
        assert "BẢN SAO" not in doc[2].get_text()
        fonts = {f[3] for f in doc.get_page_fonts(0, full=True)}
        assert any("+Arial" in name for name in fonts)  # phông Windows nhúng tập con
    assert res.output_size < res.input_size + 60_000


def test_watermark_tile_and_validation(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path / "goc.pdf", 1)
    res = ps.watermark_pdf(src, tmp_path / "lat.pdf",
                           ps.WatermarkOptions(text="MẬT", font_size=30, layout="tile", angle=30, behind=True))
    with fitz.open(res.output_path) as doc:
        assert doc[0].get_text().count("MẬT") >= 6
    with pytest.raises(pdf_io.PdfToolError):
        ps.watermark_pdf(src, tmp_path / "x.pdf", ps.WatermarkOptions(text="  "))
    with pytest.raises(pdf_io.PdfToolError):
        ps.watermark_pdf(src, tmp_path / "x.pdf", ps.WatermarkOptions(layout="cheo"))


# ─── Đánh số trang ────────────────────────────────────────────────────────


def test_page_numbers_template_start_skip_and_position(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path / "goc.pdf", 4, rotations=[0, 90, 180, 270])
    opts = ps.PageNumberOptions(template="Trang {n} / {total}", position="bottom-right", start=5,
                                skip_first=True, font_size=11, margin_mm=12, side_margin_mm=15)
    res = ps.number_pages(src, options=opts)
    assert res.pages_changed == 3 and Path(res.output_path).name == "goc_danh_so.pdf"
    with fitz.open(res.output_path) as doc:
        assert "Trang" not in doc[0].get_text()
        for pno, label in ((1, "Trang 6 / 8"), (2, "Trang 7 / 8"), (3, "Trang 8 / 8")):
            page = doc[pno]
            hits = [ln for ln in _lines(page) if ln[0] == label]
            assert len(hits) == 1, page.get_text()
            _t, bbox, direction, span = hits[0]
            assert direction == (1.0, 0.0)  # chữ nằm ngang đúng chiều đọc dù trang xoay
            assert "Times New Roman" in span["font"] and abs(span["size"] - 11) < 0.1
            w, h = page.rect.width, page.rect.height
            assert abs((w - bbox.x1) - 15 * ps.MM) < 3  # cách mép phải 15 mm
            assert abs((h - bbox.y1) - 12 * ps.MM) < 4  # cách mép dưới 12 mm
            assert bbox.y0 > h - 30 * ps.MM


def test_page_numbers_nd30_preset_and_pages(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path / "goc.pdf", 3)
    res = ps.number_pages(src, tmp_path / "nd30.pdf", ps.nd30_page_number_options())
    with fitz.open(res.output_path) as doc:
        assert [ln[0] for ln in _lines(doc[0])] == ["Noi dung trang 1"]  # không hiện số trang 1
        for pno in (1, 2):
            hits = [ln for ln in _lines(doc[pno]) if ln[0] == str(pno + 1)]
            assert len(hits) == 1
            bbox, span = hits[0][1], hits[0][3]
            assert abs((bbox.x0 + bbox.x1) / 2 - 297.5) < 2 and bbox.y1 < 25 * ps.MM  # giữa lề trên
            assert "Times New Roman" in span["font"] and abs(span["size"] - 13) < 0.1
    part = ps.number_pages(src, tmp_path / "phan.pdf", ps.PageNumberOptions(template="- {n} -", pages="2-3"))
    with fitz.open(part.output_path) as doc:
        assert "- 1 -" in doc[1].get_text() and "- 2 -" in doc[2].get_text()
        assert "-" not in doc[0].get_text()
    assert ps.format_page_label("Trang {trang}/{tong}", 2, 9) == "Trang 2/9"
    assert ps.normalize_position("duoi-phai") == "bottom-right"
    for bad in (ps.PageNumberOptions(template="Trang"), ps.PageNumberOptions(position="giua"),
                ps.PageNumberOptions(margin_mm=500)):
        with pytest.raises(pdf_io.PdfToolError):
            ps.number_pages(src, tmp_path / "x.pdf", bad)


# ─── Mật khẩu ─────────────────────────────────────────────────────────────


def test_protect_and_unlock(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path / "goc.pdf", 2)
    opts = sec.ProtectOptions("mo123", "chu456", allow_copy=False, allow_modify=False)
    res = sec.protect_pdf(src, options=opts)
    out = Path(res.output_path)
    assert res.encrypted and out.name == "goc_bao_ve.pdf" and "cấm sao chép" in res.note
    info = sec.security_info(out)
    assert info.needs_password and info.encrypted
    with fitz.open(str(out)) as doc:
        assert doc.needs_pass
        assert doc.authenticate("sai") == 0
        assert doc.authenticate("mo123") == 2
        assert sec.permissions_dict(doc.permissions) == {"print": True, "copy": False, "modify": False,
                                                          "annotate": True}
        assert doc.metadata["encryption"].endswith("256-bit AES")
        assert "Noi dung trang 2" in doc[1].get_text()
    with fitz.open(str(out)) as doc:
        assert doc.authenticate("chu456") & 4

    # Gỡ: mật khẩu mở không đủ khi tệp hạn chế quyền; mật khẩu chủ thì được
    with pytest.raises(PermissionError):
        sec.unlock_pdf(out, tmp_path / "u.pdf", "mo123")
    with pytest.raises(PermissionError):
        sec.unlock_pdf(out, tmp_path / "u.pdf", "sai")
    un = sec.unlock_pdf(out, password="chu456")
    assert Path(un.output_path).name == "goc_bao_ve_mo_khoa.pdf"
    with fitz.open(un.output_path) as doc:
        assert not doc.needs_pass and not doc.metadata.get("encryption")
        assert [p.get_text().strip() for p in doc] == ["Noi dung trang 1", "Noi dung trang 2"]
    with pytest.raises(pdf_io.PdfToolError):
        sec.unlock_pdf(un.output_path, tmp_path / "v.pdf", "x")

    # Chỉ mật khẩu mở, đủ quyền → mật khẩu mở gỡ được
    only = sec.protect_pdf(src, tmp_path / "chi_mo.pdf", sec.ProtectOptions("abc"))
    assert sec.unlock_pdf(only.output_path, tmp_path / "chi_mo_u.pdf", "abc").written
    # Chỉ mật khẩu chủ: mở không cần mật khẩu nhưng cấm in
    own = sec.protect_pdf(src, tmp_path / "chi_chu.pdf", sec.ProtectOptions("", "chu", allow_print=False))
    info = sec.security_info(own.output_path)
    assert not info.needs_password and info.encrypted and info.permissions["print"] is False

    for bad in (sec.ProtectOptions(), sec.ProtectOptions("a", allow_print=False),
                sec.ProtectOptions("a", "a", allow_copy=False)):
        with pytest.raises(pdf_io.PdfToolError):
            sec.protect_pdf(src, tmp_path / "x.pdf", bad)


def test_tools_on_protected_source_keep_encryption(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path / "goc.pdf", 2)
    prot = Path(sec.protect_pdf(src, tmp_path / "bv.pdf",
                                sec.ProtectOptions("mo", "chu", allow_modify=False)).output_path)
    with pytest.raises(PermissionError):
        ps.watermark_pdf(prot, tmp_path / "w.pdf")  # chưa nhập mật khẩu
    with pytest.raises(PermissionError):
        ps.watermark_pdf(prot, tmp_path / "w.pdf", password="mo")  # mật khẩu mở không có quyền sửa
    res = ps.number_pages(prot, tmp_path / "n.pdf", password="chu")
    assert res.encrypted
    with fitz.open(res.output_path) as doc:
        assert doc.needs_pass and doc.authenticate("mo") == 2
        assert "2" in doc[1].get_text() and "Noi dung trang 2" in doc[1].get_text()


# ─── Dòng lệnh ────────────────────────────────────────────────────────────


def test_cli_office_commands(tmp_path: Path, capsys) -> None:
    src = _make_pdf(tmp_path / "goc.pdf", 3)

    def run(*argv) -> tuple[int, dict | str]:
        code = cli_main([str(a) for a in argv])
        out = capsys.readouterr().out
        try:
            return code, json.loads(out)
        except ValueError:
            return code, out

    code, data = run("watermark", src, "--text", r"BẢN SAO\nNỘI BỘ", "--tile", "--size", "24", "--json")
    assert code == 0 and data["pages_changed"] == 3
    with fitz.open(data["output_path"]) as doc:
        assert "NỘI BỘ" in doc[0].get_text()

    code, data = run("number", src, "--preset", "nd30", "--format", "Trang {n}", "-o", tmp_path / "so.pdf", "--json")
    assert code == 0 and data["pages_changed"] == 2
    with fitz.open(str(tmp_path / "so.pdf")) as doc:
        assert "Trang 3" in doc[2].get_text() and "Trang" not in doc[0].get_text()

    code, data = run("protect", src, "-u", "111", "-O", "222", "--no-print", "--json")
    assert code == 0 and data["encrypted"]
    code, _ = run("unlock", data["output_path"], "--password", "111")
    assert code == 1  # hạn chế quyền: cần mật khẩu chủ
    code, data2 = run("unlock", data["output_path"], "--password", "222", "--json")
    assert code == 0 and not data2["encrypted"]

    code, data = run("compress", _make_image_pdf(tmp_path / "anh.pdf"), "--level", "manh", "--json")
    assert code == 0 and data["written"] and data["saved_percent"] > 50

    signed = _make_pdf(tmp_path / "ky.pdf", 1, signed=True)
    assert run("compress", signed)[0] == 1
    assert run("number", signed, "--force")[0] == 0
    code, text = run("watermark", src, "--text", "X", "-o", src)
    assert code == 1
