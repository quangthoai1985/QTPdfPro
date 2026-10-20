"""Chuẩn thể thức văn bản hành chính theo Nghị định 30/2020/NĐ-CP (Phụ lục I).

Module gồm 3 phần:
1. `ND30_SPEC` — các thông số quy định (khổ giấy, lề, phông, cỡ chữ, giãn dòng, cách đoạn...).
2. `check_nd30_compliance()` — **đối chiếu** bố cục đo được trên PDF với quy định, trả về
   danh sách hạng mục Đạt / Cần xem lại / Không đạt kèm số đo và gợi ý.
3. `build_docx_plan()` — **ước lượng về chuẩn**: từ số đo trên PDF suy ra giá trị chuẩn mà người
   soạn đã đặt trong Word (vd lề trái đo 29,8 mm → 30 mm; giãn dòng đo 1,49 → 1,5 lines), rồi
   kẹp vào khoảng NĐ30 cho phép khi chọn chính sách `"nd30"`.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence

from qtpdfpro.core.admin_layout import (
    PT_PER_MM,
    STANDARD_MULTIPLES,
    resolve_line_spacing,
    AdminDocument,
    ParaBlock,
    RuleBlock,
    _NGAY_THANG_RE,
    _NOI_NHAN_RE,
    _QUOC_HIEU_RE,
    _SO_KY_HIEU_RE,
    _TIEU_NGU_RE,
)


@dataclass(frozen=True)
class ND30Spec:
    """Thông số quy định của Phụ lục I Nghị định 30/2020/NĐ-CP."""

    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    margin_top: tuple[float, float] = (20.0, 25.0)
    margin_bottom: tuple[float, float] = (20.0, 25.0)
    margin_left: tuple[float, float] = (30.0, 35.0)
    margin_right: tuple[float, float] = (15.0, 20.0)
    default_margins: tuple[float, float, float, float] = (20.0, 20.0, 30.0, 20.0)  # trên, dưới, trái, phải
    font: str = "Times New Roman"
    body_size: tuple[float, float] = (13.0, 14.0)
    line_multiple: tuple[float, float] = (1.0, 1.5)
    para_spacing_min_pt: float = 6.0
    first_indents_mm: tuple[float, ...] = (10.0, 12.7)
    quoc_hieu_size: tuple[float, float] = (12.0, 13.0)
    tieu_ngu_size: tuple[float, float] = (13.0, 14.0)
    co_quan_size: tuple[float, float] = (12.0, 13.0)
    so_ky_hieu_size: tuple[float, float] = (13.0, 13.0)
    dia_danh_size: tuple[float, float] = (13.0, 14.0)
    ten_loai_size: tuple[float, float] = (13.0, 14.0)
    noi_nhan_title_size: float = 12.0
    noi_nhan_item_size: float = 11.0


ND30_SPEC = ND30Spec()

_STANDARD_MULTIPLES = STANDARD_MULTIPLES
_NICE_MARGINS_MM = (15.0, 20.0, 25.0, 30.0, 35.0)


@dataclass
class ND30Check:
    """Một hạng mục đối chiếu thể thức."""

    code: str
    name: str
    measured: str
    expected: str
    status: str  # "ok" | "warn" | "fail" | "na"
    note: str = ""


@dataclass
class ND30Report:
    """Báo cáo đối chiếu thể thức NĐ30 của một tệp PDF."""

    is_admin_document: bool = False
    score: float = 0.0  # 0..100
    checks: List[ND30Check] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "ok")

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    def to_dict(self) -> dict:
        return {
            "is_admin_document": self.is_admin_document,
            "score": self.score,
            "ok": self.ok_count,
            "warn": self.warn_count,
            "fail": self.fail_count,
            "checks": [asdict(c) for c in self.checks],
        }


@dataclass
class DocxLayoutPlan:
    """Thông số trình bày sẽ ghi vào DOCX (sau khi ước lượng / chuẩn hoá)."""

    # "faithful" (mặc định): giữ đúng bố cục PDF — chỉ làm tròn về giá trị chuẩn khi sai số đo nhỏ,
    #                        không ép đổi thông số làm DOCX lệch khỏi PDF.
    # "nd30": chuẩn hoá cưỡng bức về khoảng NĐ30 (có thể làm thay đổi dàn trang so với PDF).
    policy: str = "faithful"
    margin_top_mm: float = 20.0
    margin_bottom_mm: float = 20.0
    margin_left_mm: float = 30.0
    margin_right_mm: float = 20.0
    body_font: str = "Times New Roman"
    body_size_src: float = 14.0  # cỡ chữ nội dung đo trên PDF
    body_size: float = 14.0  # cỡ chữ nội dung ghi vào DOCX
    line_multiple: float = 1.0
    line_exact_pt: Optional[float] = None  # đặt khi giãn dòng không khớp bội số chuẩn
    para_spacing_pt: float = 6.0
    para_spacing_src_pt: Optional[float] = None
    first_indent_mm: float = 10.0
    first_indent_src_mm: Optional[float] = None
    add_page_numbers: bool = True
    header_distance_mm: float = 10.0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Tiện ích ────────────────────────────────────────────────────────────


def _fmt_mm(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.1f} mm".replace(".", ",")


def _fmt_range(lo: float, hi: float, unit: str) -> str:
    a = f"{lo:g}".replace(".", ",")
    b = f"{hi:g}".replace(".", ",")
    return f"{a}–{b} {unit}" if lo != hi else f"{a} {unit}"


def _in_range(v: float, rng: tuple[float, float], tol: float) -> str:
    lo, hi = rng
    if lo - tol <= v <= hi + tol:
        return "ok"
    if lo - 3 * tol <= v <= hi + 3 * tol:
        return "warn"
    return "fail"


def snap_margin_mm(value: float, rng: tuple[float, float], policy: str) -> float:
    """Ước lượng giá trị lề người soạn đã đặt.

    - `faithful`: chỉ bắt về số tròn (15/20/25/30/35 mm) khi sai số đo ≤ 0,3 mm (vd 29,98 → 30),
      còn lại làm tròn 0,1 mm để không làm lệch độ rộng dòng chữ so với PDF.
    - `nd30`: bắt rộng hơn (≤ 0,8 mm), làm tròn 0,5 mm rồi kẹp vào khoảng NĐ30 cho phép.
    """
    if policy == "nd30":
        snapped, tol = round(value * 2) / 2, 0.8
    else:
        snapped, tol = round(value, 1), 0.3
    for nice in _NICE_MARGINS_MM:
        if abs(value - nice) <= tol:
            snapped = nice
            break
    if policy == "nd30":
        snapped = min(max(snapped, rng[0]), rng[1])
    return snapped


def snap_line_multiple(multiple: float) -> Optional[float]:
    """Bắt giãn dòng về bội số chuẩn của Word (1,0 / 1,15 / 1,5 ...) nếu sai lệch ≤ 2,5%."""
    for m in _STANDARD_MULTIPLES:
        if abs(multiple - m) <= 0.025 * m:
            return m
    return None


def snap_first_indent_mm(value: Optional[float], policy: str) -> float:
    if value is None:
        return ND30_SPEC.first_indents_mm[0]
    for cand in ND30_SPEC.first_indents_mm:
        if abs(value - cand) <= 1.5:
            return cand
    if policy == "nd30":
        return min(ND30_SPEC.first_indents_mm, key=lambda c: abs(c - value))
    return round(value, 1)


# ─── Nhận diện các thành phần thể thức ─────────────────────────────────────


@dataclass
class _Components:
    co_quan_chu_quan: Optional[ParaBlock] = None
    co_quan_ban_hanh: Optional[ParaBlock] = None
    rule_co_quan: Optional[RuleBlock] = None
    so_ky_hieu: Optional[ParaBlock] = None
    trich_yeu_cv: Optional[ParaBlock] = None
    quoc_hieu: Optional[ParaBlock] = None
    tieu_ngu: Optional[ParaBlock] = None
    rule_tieu_ngu: Optional[RuleBlock] = None
    dia_danh: Optional[ParaBlock] = None
    ten_loai: Optional[ParaBlock] = None
    trich_yeu: Optional[ParaBlock] = None
    noi_nhan: Optional[ParaBlock] = None
    noi_nhan_items: List[ParaBlock] = field(default_factory=list)
    chuc_vu: List[ParaBlock] = field(default_factory=list)
    ho_ten: Optional[ParaBlock] = None


_TEN_LOAI = (
    "QUYẾT ĐỊNH", "BÁO CÁO", "KẾ HOẠCH", "TỜ TRÌNH", "THÔNG BÁO", "CHỈ THỊ", "QUY CHẾ", "QUY ĐỊNH",
    "HƯỚNG DẪN", "CHƯƠNG TRÌNH", "PHƯƠNG ÁN", "ĐỀ ÁN", "DỰ ÁN", "BIÊN BẢN", "GIẤY MỜI", "GIẤY GIỚI THIỆU",
    "GIẤY NGHỈ PHÉP", "PHIẾU GỬI", "PHIẾU CHUYỂN", "PHIẾU BÁO", "THƯ CÔNG", "NGHỊ QUYẾT", "CÔNG ĐIỆN",
    "BẢN GHI NHỚ", "BẢN THỎA THUẬN", "GIẤY ỦY QUYỀN", "HỢP ĐỒNG", "THÔNG CÁO", "BẢN SAO",
)


def _paras(items: Sequence[object]) -> list[ParaBlock]:
    return [it for it in items if isinstance(it, ParaBlock)]


def identify_components(doc: AdminDocument) -> _Components:
    comp = _Components()
    hdr = doc.header
    if hdr is not None:
        left_all = [it for lc, _rc in hdr.rows for it in lc]
        right_all = [it for _lc, rc in hdr.rows for it in rc]
        for p in _paras(right_all):
            t = p.text
            if comp.quoc_hieu is None and _QUOC_HIEU_RE.search(t.replace("\n", " ")):
                comp.quoc_hieu = p
            elif comp.tieu_ngu is None and _TIEU_NGU_RE.search(t):
                comp.tieu_ngu = p
            elif comp.dia_danh is None and _NGAY_THANG_RE.search(t):
                comp.dia_danh = p
        rules_r = [it for it in right_all if isinstance(it, RuleBlock)]
        if rules_r:
            comp.rule_tieu_ngu = rules_r[0]
        agency: list[ParaBlock] = []
        for p in _paras(left_all):
            t = p.text.strip()
            if _SO_KY_HIEU_RE.match(t):
                comp.so_ky_hieu = p
            elif t.lower().startswith("v/v"):
                comp.trich_yeu_cv = p
            elif comp.so_ky_hieu is None:
                agency.append(p)
        if agency:
            bold = [p for p in agency if all(l.is_bold for l in p.lines)]
            comp.co_quan_ban_hanh = bold[-1] if bold else agency[-1]
            regular = [p for p in agency if p is not comp.co_quan_ban_hanh]
            comp.co_quan_chu_quan = regular[0] if regular else None
        rules_l = [it for it in left_all if isinstance(it, RuleBlock)]
        if rules_l:
            comp.rule_co_quan = rules_l[0]

    # Tên loại + trích yếu: các đoạn căn giữa ngay sau phần tiêu đề
    started = hdr is None
    for blk in doc.blocks:
        if blk is hdr:
            started = True
            continue
        if not started:
            continue
        if isinstance(blk, RuleBlock):
            if comp.ten_loai is not None:
                break
            continue
        if not isinstance(blk, ParaBlock):
            break
        if blk.align != "center":
            break
        t = blk.text.replace("\n", " ").strip()
        if comp.ten_loai is None and blk.lines[0].is_upper and any(t.upper().startswith(k) for k in _TEN_LOAI):
            comp.ten_loai = blk
            continue
        if comp.ten_loai is not None and comp.trich_yeu is None and not blk.lines[0].is_upper:
            comp.trich_yeu = blk
            continue
        break

    sign = doc.sign
    if sign is not None:
        lcol, rcol = sign.rows[0]
        for p in _paras(lcol):
            if comp.noi_nhan is None and _NOI_NHAN_RE.match(p.text):
                comp.noi_nhan = p
            elif comp.noi_nhan is not None:
                comp.noi_nhan_items.append(p)
        rparas = _paras(rcol)
        if rparas:
            comp.ho_ten = rparas[-1]
            comp.chuc_vu = rparas[:-1]
    return comp


# ─── Đối chiếu ───────────────────────────────────────────────────────────


def _size_of(p: Optional[ParaBlock]) -> Optional[float]:
    return p.size if p is not None else None


def _check_component(
    code: str,
    name: str,
    para: Optional[ParaBlock],
    size_rng: tuple[float, float],
    *,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    upper: Optional[bool] = None,
    required: bool = True,
) -> ND30Check:
    expected_bits = [_fmt_range(size_rng[0], size_rng[1], "pt")]
    if upper is True:
        expected_bits.append("in hoa")
    if bold is True:
        expected_bits.append("đậm")
    if bold is False:
        expected_bits.append("không đậm")
    if italic is True:
        expected_bits.append("nghiêng")
    if italic is False:
        expected_bits.append("đứng")
    expected = ", ".join(expected_bits)
    if para is None:
        return ND30Check(code, name, "Không tìm thấy", expected, "fail" if required else "na")
    first = para.lines[0]
    measured_bits = [f"{para.size:g} pt".replace(".", ",")]
    problems: list[str] = []
    if not (size_rng[0] - 0.3 <= para.size <= size_rng[1] + 0.3):
        problems.append("cỡ chữ")
    is_bold = all(l.is_bold for l in para.lines)
    is_italic = all(l.is_italic for l in para.lines)
    is_upper = all(l.is_upper for l in para.lines)
    measured_bits.append("in hoa" if is_upper else "in thường")
    measured_bits.append("đậm" if is_bold else "không đậm")
    measured_bits.append("nghiêng" if is_italic else "đứng")
    if bold is not None and bold != is_bold:
        problems.append("đậm")
    if italic is not None and italic != is_italic:
        problems.append("nghiêng")
    if upper is not None and upper != is_upper:
        problems.append("in hoa")
    status = "ok" if not problems else ("warn" if problems == ["cỡ chữ"] else "fail")
    note = f"Sai: {', '.join(problems)}" if problems else ""
    _ = first
    return ND30Check(code, name, ", ".join(measured_bits), expected, status, note)


def check_nd30_compliance(doc: AdminDocument, spec: ND30Spec = ND30_SPEC) -> ND30Report:
    """Đối chiếu bố cục văn bản PDF đã phân tích với quy định thể thức NĐ30."""
    ml = doc.measured
    rep = ND30Report(is_admin_document=doc.is_admin)
    add = rep.checks.append

    # 1. Khổ giấy
    is_a4 = abs(ml.page_width_mm - spec.page_width_mm) <= 2.0 and abs(ml.page_height_mm - spec.page_height_mm) <= 2.0
    add(ND30Check("page_size", "Khổ giấy", f"{ml.page_width_mm:.0f} × {ml.page_height_mm:.0f} mm", "A4 (210 × 297 mm), khổ dọc", "ok" if is_a4 else "fail"))

    # 2. Lề trang
    add(ND30Check("margin_top", "Lề trên", _fmt_mm(ml.margin_top_mm), _fmt_range(*spec.margin_top, "mm"), _in_range(ml.margin_top_mm, spec.margin_top, 0.8)))
    lo, hi = ml.margin_bottom_lo_mm, ml.margin_bottom_hi_mm
    if hi is None:
        add(ND30Check("margin_bottom", "Lề dưới", "Không đo được (văn bản 1 trang)", _fmt_range(*spec.margin_bottom, "mm"), "na", "Cần ít nhất 1 trang đầy chữ để ước lượng."))
    else:
        lo_v = lo if lo is not None else 0.0
        meas = f"{_fmt_mm(lo_v)} – {_fmt_mm(hi)}" if lo is not None else f"≤ {_fmt_mm(hi)}"
        inter = max(lo_v, spec.margin_bottom[0]) <= min(hi, spec.margin_bottom[1]) + 0.8
        status = "ok" if inter else ("fail" if hi < spec.margin_bottom[0] - 0.8 else "warn")
        add(ND30Check("margin_bottom", "Lề dưới (ước lượng)", meas, _fmt_range(*spec.margin_bottom, "mm"), status, "Ước lượng từ vị trí dòng cuối các trang đầy."))
    add(ND30Check("margin_left", "Lề trái", _fmt_mm(ml.margin_left_mm), _fmt_range(*spec.margin_left, "mm"), _in_range(ml.margin_left_mm, spec.margin_left, 0.8)))
    add(ND30Check("margin_right", "Lề phải", _fmt_mm(ml.margin_right_mm), _fmt_range(*spec.margin_right, "mm"), _in_range(ml.margin_right_mm, spec.margin_right, 0.8)))

    # 3. Phông, cỡ chữ, căn lề, giãn dòng, cách đoạn, thụt đầu dòng
    font_ok = ml.body_font == spec.font and ml.font_share >= 0.9
    add(ND30Check("font", "Phông chữ", f"{ml.body_font} ({ml.font_share * 100:.0f}% ký tự)", f"{spec.font} (Unicode TCVN 6909:2001)", "ok" if font_ok else ("warn" if ml.body_font == spec.font else "fail")))
    add(ND30Check("body_size", "Cỡ chữ phần nội dung", f"{ml.body_size:g} pt".replace(".", ","), _fmt_range(*spec.body_size, "pt"), _in_range(ml.body_size, spec.body_size, 0.3)))
    align_name = {"both": "Căn đều 2 lề", "left": "Căn trái", "center": "Căn giữa", "right": "Căn phải"}.get(ml.body_align, ml.body_align)
    add(ND30Check("body_align", "Căn lề phần nội dung", align_name, "Căn đều 2 lề", "ok" if ml.body_align == "both" else "warn"))
    from qtpdfpro.core.admin_layout import font_line_metrics

    rule, value = resolve_line_spacing(ml.line_pitch_pt, ml.body_size, font_line_metrics(ml.body_font)[0])
    if rule == "auto":
        lm_txt = f"{value:g} lines ({ml.line_pitch_pt:.1f} pt)".replace(".", ",")
    else:
        lm_txt = f"Exactly {value:g} pt (≈ {ml.line_multiple:.2f} lines)".replace(".", ",")
    add(ND30Check("line_spacing", "Khoảng cách dòng", lm_txt, "Từ 1 dòng (single) đến 1,5 lines", _in_range(ml.line_multiple, spec.line_multiple, 0.03)))
    if ml.para_spacing_pt is None:
        add(ND30Check("para_spacing", "Khoảng cách đoạn", "Không đo được", f"Tối thiểu {spec.para_spacing_min_pt:g} pt", "na"))
    else:
        ps = ml.para_spacing_pt
        status = "ok" if ps >= spec.para_spacing_min_pt - 0.6 else ("warn" if ps >= spec.para_spacing_min_pt - 2.5 else "fail")
        add(ND30Check("para_spacing", "Khoảng cách đoạn", f"{ps:.1f} pt".replace(".", ","), f"Tối thiểu {spec.para_spacing_min_pt:g} pt", status))
    if ml.first_indent_mm is None:
        add(ND30Check("first_indent", "Thụt đầu dòng", "Không có", "1 cm hoặc 1,27 cm", "warn"))
    else:
        fi = ml.first_indent_mm
        ok = any(abs(fi - c) <= 1.0 for c in spec.first_indents_mm)
        near = any(abs(fi - c) <= 2.5 for c in spec.first_indents_mm)
        add(ND30Check("first_indent", "Thụt đầu dòng", _fmt_mm(fi), "1 cm hoặc 1,27 cm", "ok" if ok else ("warn" if near else "fail")))

    if not doc.is_admin:
        rep.checks.append(ND30Check("header", "Phần đầu văn bản hành chính", "Không phát hiện Quốc hiệu – Tiêu ngữ", "Có Quốc hiệu, Tiêu ngữ, tên cơ quan, số ký hiệu", "fail", "Tệp có thể không phải văn bản hành chính."))
        _finalize_score(rep)
        return rep

    comp = identify_components(doc)

    # 4. Quốc hiệu & Tiêu ngữ (ô 1)
    add(_check_component("quoc_hieu", "Quốc hiệu", comp.quoc_hieu, spec.quoc_hieu_size, bold=True, italic=False, upper=True))
    tn = _check_component("tieu_ngu", "Tiêu ngữ", comp.tieu_ngu, spec.tieu_ngu_size, bold=True, italic=False)
    if comp.tieu_ngu is not None and not re.search(r"\S\s+-\s+\S.*\S\s+-\s+\S", comp.tieu_ngu.text):
        tn.status = "warn" if tn.status == "ok" else tn.status
        tn.note = (tn.note + "; " if tn.note else "") + "Gạch nối giữa các cụm từ phải có cách chữ (Độc lập - Tự do - Hạnh phúc)"
    add(tn)
    if comp.tieu_ngu is not None:
        tn_w = max(l.width for l in comp.tieu_ngu.lines)
        if comp.rule_tieu_ngu is None:
            add(ND30Check("rule_tieu_ngu", "Đường kẻ dưới Tiêu ngữ", "Không có", "Nét liền, dài bằng dòng Tiêu ngữ", "fail"))
        else:
            ratio = comp.rule_tieu_ngu.rule.width / max(1.0, tn_w)
            add(ND30Check("rule_tieu_ngu", "Đường kẻ dưới Tiêu ngữ", f"{comp.rule_tieu_ngu.rule.width / PT_PER_MM:.1f} mm ({ratio * 100:.0f}% dòng chữ)".replace(".", ","), "Nét liền, dài bằng dòng Tiêu ngữ", "ok" if 0.8 <= ratio <= 1.2 else "warn"))

    # 5. Tên cơ quan (ô 2)
    if comp.co_quan_chu_quan is not None:
        add(_check_component("co_quan_chu_quan", "Tên cơ quan chủ quản", comp.co_quan_chu_quan, spec.co_quan_size, bold=False, upper=True))
    add(_check_component("co_quan_ban_hanh", "Tên cơ quan ban hành", comp.co_quan_ban_hanh, spec.co_quan_size, bold=True, upper=True))
    if comp.co_quan_ban_hanh is not None:
        cq_w = max(l.width for l in comp.co_quan_ban_hanh.lines)
        if comp.rule_co_quan is None:
            add(ND30Check("rule_co_quan", "Đường kẻ dưới tên cơ quan", "Không có", "Nét liền, dài 1/3 – 1/2 dòng chữ", "fail"))
        else:
            ratio = comp.rule_co_quan.rule.width / max(1.0, cq_w)
            add(ND30Check("rule_co_quan", "Đường kẻ dưới tên cơ quan", f"{comp.rule_co_quan.rule.width / PT_PER_MM:.1f} mm ({ratio * 100:.0f}% dòng chữ)".replace(".", ","), "Nét liền, dài 1/3 – 1/2 dòng chữ", "ok" if 0.28 <= ratio <= 0.6 else "warn"))

    # 6. Số, ký hiệu (ô 3)
    so = _check_component("so_ky_hieu", "Số, ký hiệu", comp.so_ky_hieu, spec.so_ky_hieu_size, bold=False, italic=False)
    if comp.so_ky_hieu is not None:
        t = comp.so_ky_hieu.text.replace(" ", "")
        m = re.match(r"S[ốo]:(\d+)/([A-ZĐ0-9\-]+)", t, re.I)
        if not m:
            so.status = "warn" if so.status == "ok" else so.status
            so.note = (so.note + "; " if so.note else "") + "Định dạng chuẩn: «Số: 05/QĐ-UBND»"
        elif len(m.group(1)) == 1:
            so.status = "warn" if so.status == "ok" else so.status
            so.note = (so.note + "; " if so.note else "") + "Số nhỏ hơn 10 phải thêm số 0 phía trước"
    add(so)

    # 7. Địa danh, ngày tháng (ô 4)
    dd = _check_component("dia_danh", "Địa danh, ngày tháng năm", comp.dia_danh, spec.dia_danh_size, italic=True, bold=False)
    if comp.dia_danh is not None:
        mt = re.search(r"ng[àa]y\s+(\d+)\s+th[áa]ng\s+(\d+)", comp.dia_danh.text, re.I)
        if mt:
            day, month = mt.group(1), mt.group(2)
            if (int(day) < 10 and len(day) == 1) or (int(month) in (1, 2) and len(month) == 1):
                dd.status = "warn" if dd.status == "ok" else dd.status
                dd.note = (dd.note + "; " if dd.note else "") + "Ngày < 10 và tháng 1, 2 phải thêm số 0"
    add(dd)

    # 8. Tên loại & trích yếu (ô 5)
    if comp.trich_yeu_cv is not None:
        add(_check_component("trich_yeu", "Trích yếu công văn (V/v)", comp.trich_yeu_cv, (12.0, 13.0), bold=False, italic=False))
    else:
        add(_check_component("ten_loai", "Tên loại văn bản", comp.ten_loai, spec.ten_loai_size, bold=True, upper=True))
        add(_check_component("trich_yeu", "Trích yếu nội dung", comp.trich_yeu, spec.ten_loai_size, bold=True, required=comp.ten_loai is not None))

    # 9. Nơi nhận & chữ ký (ô 7, ô 9b)
    nn = _check_component("noi_nhan", "«Nơi nhận:»", comp.noi_nhan, (spec.noi_nhan_title_size, spec.noi_nhan_title_size), bold=True, italic=True, required=doc.sign is not None)
    add(nn)
    if comp.noi_nhan_items:
        sizes = {round(p.size * 2) / 2 for p in comp.noi_nhan_items}
        last_txt = comp.noi_nhan_items[-1].text.strip().lstrip("-–• ").strip()
        ok_size = all(abs(s - spec.noi_nhan_item_size) <= 0.3 for s in sizes)
        ok_luu = last_txt.lower().startswith("lưu")
        status = "ok" if ok_size and ok_luu else "warn"
        note = []
        if not ok_size:
            note.append("Danh sách nơi nhận cỡ 11 pt")
        if not ok_luu:
            note.append("Dòng cuối phải là «Lưu: VT, …»")
        add(ND30Check("noi_nhan_items", "Danh sách nơi nhận", f"{len(comp.noi_nhan_items)} dòng, cỡ {', '.join(f'{s:g}' for s in sorted(sizes))} pt", "Mỗi nơi 1 dòng, cỡ 11 pt, dòng cuối «Lưu: VT, …»", status, "; ".join(note)))
    if comp.chuc_vu:
        add(_check_component("chuc_vu", "Quyền hạn, chức vụ người ký", comp.chuc_vu[0], (13.0, 14.0), bold=True, upper=True))
    if comp.ho_ten is not None:
        add(_check_component("ho_ten", "Họ tên người ký", comp.ho_ten, (13.0, 14.0), bold=True))

    # 10. Số trang
    n_pages = len(doc.pages)
    if n_pages >= 2:
        numbered = sorted(set(ml.page_number_pages))
        first_idx = doc.pages[0].index
        has_first = first_idx in numbered
        others = [m.index for m in doc.pages[1:]]
        covered = sum(1 for p in others if p in numbered)
        if covered == len(others) and not has_first:
            rng = "Trang 2" if n_pages == 2 else f"Trang 2–{n_pages}"
            st, meas = "ok", f"{rng} có số trang, trang 1 không"
        elif covered == 0:
            st, meas = "fail", "Không đánh số trang"
        else:
            st, meas = "warn", f"{covered}/{len(others)} trang sau có số" + ("; trang 1 có số" if has_first else "")
        add(ND30Check("page_numbers", "Đánh số trang", meas, "Từ trang 2, canh giữa lề trên; không hiển thị trang 1", st))

    _finalize_score(rep)
    return rep


def _finalize_score(rep: ND30Report) -> None:
    graded = [c for c in rep.checks if c.status != "na"]
    if not graded:
        rep.score = 0.0
        return
    pts = sum(1.0 if c.status == "ok" else (0.5 if c.status == "warn" else 0.0) for c in graded)
    rep.score = round(100.0 * pts / len(graded), 1)


# ─── Ước lượng thông số DOCX chuẩn ─────────────────────────────────────────


def normalize_policy(policy: Optional[str]) -> str:
    """Chuẩn hoá tên chính sách: `faithful` (giữ đúng PDF, mặc định) hoặc `nd30` (ép chuẩn)."""
    p = (policy or "").strip().lower()
    return "nd30" if p in ("nd30", "standard", "chuan", "chuẩn") else "faithful"


def build_docx_plan(doc: AdminDocument, policy: str = "faithful", spec: ND30Spec = ND30_SPEC) -> DocxLayoutPlan:
    """Suy ra thông số trình bày DOCX từ số đo PDF theo chính sách đã chọn.

    - `faithful`: ước lượng giá trị gốc người soạn đã đặt (bắt về số tròn khi sai số ≤ ngưỡng đo),
      tuyệt đối không kẹp vào khoảng NĐ30 → DOCX dàn trang trùng khớp PDF.
    - `nd30`: như trên rồi kẹp vào khoảng NĐ30 (lề, cỡ chữ, giãn dòng, cách đoạn ≥ 6pt...).
    """
    policy = normalize_policy(policy)
    ml = doc.measured
    plan = DocxLayoutPlan(policy=policy)

    plan.margin_top_mm = snap_margin_mm(ml.margin_top_mm or spec.default_margins[0], spec.margin_top, policy)
    plan.margin_left_mm = snap_margin_mm(ml.margin_left_mm or spec.default_margins[2], spec.margin_left, policy)
    plan.margin_right_mm = snap_margin_mm(ml.margin_right_mm or spec.default_margins[3], spec.margin_right, policy)

    lo, hi = ml.margin_bottom_lo_mm, ml.margin_bottom_hi_mm
    if hi is None:
        plan.margin_bottom_mm = spec.default_margins[1]
        plan.notes.append("Lề dưới không đo được trực tiếp — dùng giá trị chuẩn 20 mm.")
    else:
        lo_v = lo if lo is not None else 0.0
        a, b = max(lo_v, spec.margin_bottom[0]), min(hi, spec.margin_bottom[1])
        if a <= b:
            plan.margin_bottom_mm = snap_margin_mm(a, spec.margin_bottom, policy)
        elif policy == "nd30":
            plan.margin_bottom_mm = spec.margin_bottom[0] if hi < spec.margin_bottom[0] else spec.margin_bottom[1]
        else:
            plan.margin_bottom_mm = snap_margin_mm(min(hi, max(lo_v, 10.0)), (0, 99), "faithful")

    plan.body_font = spec.font if policy == "nd30" else ml.body_font
    plan.body_size_src = ml.body_size
    plan.body_size = ml.body_size
    if policy == "nd30":
        plan.body_size = min(max(round(ml.body_size), spec.body_size[0]), spec.body_size[1])

    from qtpdfpro.core.admin_layout import font_line_metrics

    rule, value = resolve_line_spacing(
        ml.line_pitch_pt, ml.body_size, font_line_metrics(ml.body_font)[0], policy, is_body=True
    )
    if rule == "auto":
        plan.line_multiple = value
    else:
        plan.line_multiple = round(ml.line_multiple, 2)
        plan.line_exact_pt = value

    plan.para_spacing_src_pt = ml.para_spacing_pt
    ps = ml.para_spacing_pt if ml.para_spacing_pt is not None else spec.para_spacing_min_pt
    ps = round(ps * 2) / 2
    if abs(ps - round(ps)) <= 0.5:
        ps = float(round(ps))
    if policy == "nd30":
        ps = max(ps, spec.para_spacing_min_pt)
    plan.para_spacing_pt = ps

    plan.first_indent_src_mm = ml.first_indent_mm
    plan.first_indent_mm = snap_first_indent_mm(ml.first_indent_mm, policy)

    n_pages = len(doc.pages)
    plan.add_page_numbers = (n_pages >= 2) if policy == "nd30" else bool(ml.page_number_pages)
    if ml.header_distance_pt is not None:
        plan.header_distance_mm = max(5.0, round(ml.header_distance_pt / PT_PER_MM, 1))

    if policy == "nd30":
        changes = []
        if abs(plan.margin_left_mm - ml.margin_left_mm) > 0.8:
            changes.append(f"lề trái {ml.margin_left_mm:.1f} → {plan.margin_left_mm:g} mm")
        if abs(plan.margin_right_mm - ml.margin_right_mm) > 0.8:
            changes.append(f"lề phải {ml.margin_right_mm:.1f} → {plan.margin_right_mm:g} mm")
        if abs(plan.margin_top_mm - ml.margin_top_mm) > 0.8:
            changes.append(f"lề trên {ml.margin_top_mm:.1f} → {plan.margin_top_mm:g} mm")
        if abs(plan.body_size - ml.body_size) > 0.3:
            changes.append(f"cỡ chữ nội dung {ml.body_size:g} → {plan.body_size:g} pt")
        if ml.para_spacing_pt is not None and plan.para_spacing_pt - ml.para_spacing_pt > 0.6:
            changes.append(f"cách đoạn {ml.para_spacing_pt:g} → {plan.para_spacing_pt:g} pt")
        if changes:
            plan.notes.append("Đã chuẩn hoá theo NĐ30: " + "; ".join(changes).replace(".", ",") + ".")
    return plan
