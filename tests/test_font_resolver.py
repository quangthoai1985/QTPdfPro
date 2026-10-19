"""Kiểm thử mô-đun chuẩn hoá phông chữ và bảng mã tiếng Việt (`font_resolver.py`)."""

from __future__ import annotations

from qtpdfpro.core.font_resolver import (
    convert_tcvn3_to_unicode,
    normalize_vietnamese_text,
    resolve_pdf_font,
    strip_subset_prefix,
)


def test_strip_subset_prefix() -> None:
    assert strip_subset_prefix("BCDEFG+TimesNewRomanPS-BoldMT") == "TimesNewRomanPS-BoldMT"
    assert strip_subset_prefix("XYZABC+ArialMT") == "ArialMT"
    assert strip_subset_prefix("Times New Roman") == "Times New Roman"


def test_resolve_pdf_font_families_and_styles() -> None:
    r1 = resolve_pdf_font("ABCDEF+TimesNewRomanPS-BoldItalicMT")
    assert r1.family == "Times New Roman"
    assert r1.is_bold is True
    assert r1.is_italic is True

    r2 = resolve_pdf_font("Arial-BoldMT")
    assert r2.family == "Arial"
    assert r2.is_bold is True
    assert r2.is_italic is False

    r3 = resolve_pdf_font("Helvetica-Oblique")
    assert r3.family == "Arial"
    assert r3.is_italic is True

    r4 = resolve_pdf_font("CIDFont+F1", default_family="Times New Roman")
    assert r4.family == "Times New Roman"

    r5 = resolve_pdf_font(".VnTimeH")
    assert r5.family == "Times New Roman"
    assert r5.encoding_hint == "tcvn3"


def test_normalize_vietnamese_nfd_and_spacing_accents() -> None:
    # Chuỗi NFD tách rời chữ cái và dấu thanh
    decomposed = "C\u004f\u0302\u0323NG HO\u0041\u0300 XA\u0303 H\u004f\u0302\u0323I"
    normalized = normalize_vietnamese_text(decomposed)
    assert normalized == "CỘNG HOÀ XÃ HỘI"

    # Ký tự điều khiển XML không hợp lệ phải bị loại bỏ
    dirty = "Văn\x00 bản\x07 hợp\x1f lệ"
    assert normalize_vietnamese_text(dirty) == "Văn bản hợp lệ"


def test_convert_tcvn3_to_unicode() -> None:
    # "ééc lËp" trong TCVN3 -> "độc lập" (với ® = đ, é = ộ)
    sample_tcvn = "®éc lËp - tù do"
    assert convert_tcvn3_to_unicode(sample_tcvn) == "độc lập - tự do"
    assert normalize_vietnamese_text(sample_tcvn, font_name=".VnTime") == "độc lập - tự do"
    assert normalize_vietnamese_text(sample_tcvn, font_name=".VnTimeH") == "ĐỘC LẬP - TỰ DO"
