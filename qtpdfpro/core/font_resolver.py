"""Chuẩn hoá phông chữ PDF sang phông chuẩn Windows/Word và xử lý bảng mã tiếng Việt.

Giải quyết triệt để lỗi Microsoft Word không nhận diện được tên phông PostScript/Subset
trong PDF (ví dụ `BCDEFG+TimesNewRomanPS-BoldMT`, `Arial-ItalicMT`, `CIDFont+F1`) dẫn tới
việc Word tự thay bằng phông khác làm giãn dòng, vỡ khung, hoặc lỗi chữ tiếng Việt.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Biểu thức gỡ tiền tố subset 6 chữ cái hoa (vd: ABCDEF+TimesNewRomanPSMT)
_SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")

# Biểu thức loại bỏ ký tự điều khiển không hợp lệ trong XML 1.0
_INVALID_XML_CHARS_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]"
)

# Bảng ánh xạ từ khoá tên phông PDF sang tên phông chuẩn trên Windows / Microsoft Word
_FONT_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        (
            "timesnewroman",
            "times-roman",
            "times-bold",
            "times-italic",
            "timesroman",
            "tinos",
            "nimbusrom",
            "liberationserif",
            "vn-time",
            ".vntime",
            "vni-times",
            "times",
        ),
        "Times New Roman",
    ),
    (
        (
            "arial",
            "helvetica",
            "nimbussan",
            "liberationsans",
            "arimo",
            ".vnarial",
            "vni-helve",
            "vni-aptima",
            ".vnavant",
            "helv",
            "sans-serif",
            "swiss",
        ),
        "Arial",
    ),
    (("calibri", "carlito"), "Calibri"),
    (("cambria", "caladea"), "Cambria"),
    (("tahoma", ".vntahoma"), "Tahoma"),
    (("verdana", ".vnvogue"), "Verdana"),
    (("segoeui", "segoe ui"), "Segoe UI"),
    (
        (
            "courier",
            "consolas",
            "liberationmono",
            "dejavusansmono",
            ".vncourier",
            "vni-cour",
            "monospace",
        ),
        "Courier New",
    ),
    (("georgia",), "Georgia"),
    (("palatino", "bookantiqua", "urwpalladio"), "Palatino Linotype"),
    (("trebuchet",), "Trebuchet MS"),
    (("garamond",), "Garamond"),
    (("centurygothic", "century gothic"), "Century Gothic"),
    (("bookman",), "Bookman Old Style"),
    (("impact",), "Impact"),
    (("comicsans", "comic sans"), "Comic Sans MS"),
    (("symbol",), "Symbol"),
    (("wingdings",), "Wingdings"),
    (
        (
            "roboto",
            "notosans",
            "opensans",
            "inter",
            "dejavusans",
            "aptos",
            "lato",
            "montserrat",
        ),
        "Arial",
    ),
    (("notoserif", "dejavuserif", "merriweather", "ptserif"), "Times New Roman"),
]

# Bảng chuyển đổi dấu rời (Spacing Modifier / Combining) sang ký tự kết hợp chuẩn trước khi NFC
_SPACING_ACCENT_FIXES: dict[str, str] = {
    "\u02c6": "\u0302",  # ˆ -> combining circumflex
    "\u02dc": "\u0303",  # ˜ -> combining tilde
    "\u00b4": "\u0301",  # ´ -> combining acute (khi đứng ngay sau nguyên âm)
    "\u02d8": "\u0306",  # ˘ -> combining breve
}

# Bảng chuyển mã TCVN3 (ABC - phông .Vn*) sang Unicode dựng sẵn
_TCVN3_TO_UNICODE: dict[str, str] = {
    "¸": "á", "µ": "à", "¶": "ả", "·": "ã", "¹": "ạ",
    "¨": "ă", "¾": "ắ", "»": "ằ", "¼": "ẳ", "½": "ẵ", "Æ": "ặ",
    "©": "â", "Ê": "ấ", "Ç": "ầ", "È": "ẩ", "É": "ẫ", "Ë": "ậ",
    "®": "đ",
    "Ð": "é", "Ì": "è", "Î": "ẻ", "Ï": "ẽ", "Ñ": "ẹ",
    "ª": "ê", "Õ": "ế", "Ò": "ề", "Ó": "ể", "Ô": "ễ", "Ö": "ệ",
    "Ý": "í", "×": "ì", "Ø": "ỉ", "Ü": "ĩ", "Þ": "ị",
    "ã": "ó", "ß": "ò", "á": "ỏ", "â": "õ", "ä": "ọ",
    "«": "ô", "è": "ố", "å": "ồ", "æ": "ổ", "ç": "ỗ", "é": "ộ",
    "¬": "ơ", "í": "ớ", "ê": "ờ", "ë": "ở", "ì": "ỡ", "î": "ợ",
    "ó": "ú", "ï": "ù", "ñ": "ủ", "ò": "ũ", "ô": "ụ",
    "­": "ư", "ø": "ứ", "õ": "ừ", "ö": "ử", "÷": "ữ", "ù": "ự",
    "ý": "ý", "ú": "ỳ", "û": "ỷ", "ü": "ỹ", "þ": "ỵ",
    "¡": "Ă", "¢": "Â", "§": "Đ", "£": "Ê", "¤": "Ô", "¥": "Ơ", "¦": "Ư",
}


@dataclass(frozen=True)
class ResolvedFont:
    """Thông tin phông chữ sau khi chuẩn hoá."""

    raw_name: str
    clean_name: str
    family: str
    is_bold: bool
    is_italic: bool
    encoding_hint: str  # "unicode" | "tcvn3" | "vni"


def strip_subset_prefix(font_name: str) -> str:
    """Gỡ bỏ tiền tố subset `ABCDEF+` khỏi tên phông PDF."""
    if not font_name:
        return ""
    return _SUBSET_PREFIX_RE.sub("", font_name.strip())


def detect_font_encoding(font_name: str) -> str:
    """Phát hiện phông chữ dùng bảng mã cũ TCVN3 (.Vn*) hoặc VNI (VNI-*)."""
    clean = strip_subset_prefix(font_name).lower()
    if clean.startswith(".vn") or "tcvn" in clean:
        return "tcvn3"
    if clean.startswith("vni-") or clean.startswith("vni_"):
        return "vni"
    return "unicode"


def resolve_pdf_font(
    font_name: str | None,
    flags: int = 0,
    default_family: str = "Times New Roman",
) -> ResolvedFont:
    """Chuẩn hoá tên phông từ PDF sang tên phông chuẩn của Microsoft Word."""
    raw = (font_name or "").strip()
    clean = strip_subset_prefix(raw)
    lower = clean.lower()

    # Phát hiện kiểu đậm / nghiêng từ tên phông và cờ PDF (bit 1 = italic, bit 4 = bold)
    is_bold = bool(flags & (1 << 4)) or any(
        k in lower for k in ("bold", "black", "heavy", "demi", "semibold", "-bd", "bdmt")
    )
    is_italic = bool(flags & (1 << 1)) or any(
        k in lower for k in ("italic", "oblique", "slanted", "-it", "itmt")
    )

    encoding_hint = detect_font_encoding(clean)

    # Trong TCVN3, phông tên kết thúc bằng 'H' (vd .VnTimeH, .VnArialH) là chữ IN HOA
    normalized_key = re.sub(r"[^a-z0-9.\-]", "", lower)
    family = ""
    for keywords, target_family in _FONT_RULES:
        if any(kw in normalized_key or kw in lower for kw in keywords):
            family = target_family
            break

    if not family:
        # Nếu tên phông sau khi bỏ hậu tố -Bold/-Italic/PSMT đã là tên hợp lệ thì giữ lại
        base = re.sub(
            r"[-,]?(psmt|mt|ps|regular|bolditalic|bold|italic|oblique|reg|light|medium)$",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()
        if base and not base.lower().startswith(("cidfont", "f0", "f1", "f2", "f3", "tt")):
            family = base
        else:
            family = default_family

    return ResolvedFont(
        raw_name=raw,
        clean_name=clean,
        family=family,
        is_bold=is_bold,
        is_italic=is_italic,
        encoding_hint=encoding_hint,
    )


def convert_tcvn3_to_unicode(text: str, is_upper_font: bool = False) -> str:
    """Chuyển chuỗi văn bản bảng mã TCVN3 (.VnTime) sang Unicode dựng sẵn."""
    if not text:
        return ""
    out = []
    for ch in text:
        mapped = _TCVN3_TO_UNICODE.get(ch, ch)
        if is_upper_font:
            mapped = mapped.upper()
        out.append(mapped)
    return unicodedata.normalize("NFC", "".join(out))


_VNI_TWO_CHAR_MAP: dict[str, str] = {
    "a8": "ă", "a6": "â", "e6": "ê", "o6": "ô", "o7": "ơ", "u7": "ư", "d9": "đ",
    "A8": "Ă", "A6": "Â", "E6": "Ê", "O6": "Ô", "O7": "Ơ", "U7": "Ư", "D9": "Đ",
    "a1": "á", "a2": "à", "a3": "ả", "a4": "ã", "a5": "ạ",
    "e1": "é", "e2": "è", "e3": "ẻ", "e4": "ẽ", "e5": "ẹ",
    "i1": "í", "i2": "ì", "i3": "ỉ", "i4": "ĩ", "i5": "ị",
    "o1": "ó", "o2": "ò", "o3": "ỏ", "o4": "õ", "o5": "ọ",
    "u1": "ú", "u2": "ù", "u3": "ủ", "u4": "ũ", "u5": "ụ",
    "y1": "ý", "y2": "ỳ", "y3": "ỷ", "y4": "ỹ", "y5": "ỵ",
}


def normalize_vietnamese_text(
    text: str,
    font_name: str | None = None,
    convert_legacy: bool = True,
) -> str:
    """Chuẩn hoá văn bản tiếng Việt sang Unicode NFC hợp lệ cho OpenXML."""
    if not text:
        return ""

    # Loại bỏ ký tự điều khiển làm hỏng XML của Word và chuẩn hoá khoảng trắng/gạch ngang PDF
    cleaned = _INVALID_XML_CHARS_RE.sub("", text)
    cleaned = cleaned.replace("\u00a0", " ").replace("\u00ad", "-")

    if convert_legacy and font_name:
        enc = detect_font_encoding(font_name)
        if enc == "tcvn3":
            is_upper = strip_subset_prefix(font_name).lower().endswith("h")
            return convert_tcvn3_to_unicode(cleaned, is_upper_font=is_upper)

    # Sửa lỗi nguyên âm + dấu rời dạng Spacing Modifier trong một số PDF xuất từ Mac/LaTeX
    cleaned = re.sub(
        r"([A-Za-zÀ-ỹ])([\u02c6\u02dc\u02d8])",
        lambda m: m.group(1) + _SPACING_ACCENT_FIXES[m.group(2)],
        cleaned,
    )

    return unicodedata.normalize("NFC", cleaned)
