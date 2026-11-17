"""Các thao tác chỉnh sửa trực tiếp trang và nội dung trên `fitz.Document` đang mở.

Không phụ thuộc `PySide6` — dùng chung cho thanh công cụ «Chỉnh sửa», `EditSession` (Hoàn tác / Làm lại)
và kiểm thử tự động `pytest`.
"""

from __future__ import annotations

import base64
import re
import zlib
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF

from qtpdfpro.core import annotations as an
from qtpdfpro.core import fill_sign as fs
from qtpdfpro.core.page_ops import parse_page_selection
from qtpdfpro.core.page_stamp import MM, _TextStamps

APP_IMAGE_NAME = "QTPdfProImage"
APP_PDF_PAGE_NAME = "QTPdfProPdfPage"
_NUM_RE = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_MAX_EMBED_PDF_Z64_BYTES = 2_000_000

# Các khổ giấy chuẩn: (mã, tên hiển thị tiếng Việt, rộng mm dọc, cao mm dọc)
PAGE_SIZE_SPECS: List[Tuple[str, str, float, float]] = [
    ("A4", "A4 (210 × 297 mm)", 210.0, 297.0),
    ("A5", "A5 (148 × 210 mm)", 148.0, 210.0),
    ("A3", "A3 (297 × 420 mm)", 297.0, 420.0),
    ("B5", "B5 (176 × 250 mm)", 176.0, 250.0),
    ("LETTER", "Letter (215,9 × 279,4 mm)", 215.9, 279.4),
    ("LEGAL", "Legal (215,9 × 355,6 mm)", 215.9, 355.6),
]
_PAGE_SIZE_MAP: Dict[str, Tuple[float, float]] = {code: (w, h) for code, _label, w, h in PAGE_SIZE_SPECS}

RESIZABLE_APP_KINDS = ("image", "pdfpage", "textbox", "stamp", "signature", "fillmark")
RESIZABLE_SUBTYPES = ("Square", "Circle", "Redact", "FreeText", "Stamp")


class PageEditError(ValueError):
    """Lỗi thao tác chỉnh sửa trang / nội dung không hợp lệ (thông báo tiếng Việt)."""


def _check_page(doc: fitz.Document, page_index: int) -> fitz.Page:
    if not 0 <= page_index < doc.page_count:
        raise PageEditError(f"Trang {page_index + 1} không tồn tại (tài liệu có {doc.page_count} trang).")
    return doc[page_index]


def _mirror_pdf_array(text: str, axis_sum: float, mirror_x: bool, normalize_pairs: bool = False) -> str:
    """Đảo toạ độ X (chỉ số chẵn) hoặc Y (chỉ số lẻ) trong mảng PDF `[x0 y0 ...]` qua `axis_sum - v`."""

    def repl(m: re.Match) -> str:
        nums = [float(n) for n in _NUM_RE.findall(m.group(1))]
        out = [
            (axis_sum - v) if ((i % 2 == 0) == mirror_x) else v
            for i, v in enumerate(nums)
        ]
        if normalize_pairs and len(out) == 4:
            x0, y0, x1, y1 = out
            out = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
        return "[" + " ".join(f"{v:.4f}".rstrip("0").rstrip(".") for v in out) + "]"

    return re.sub(r"\[([^\[\]]*)\]", repl, text)


def _flip_page_annotations(page: fitz.Page, axis_sum: float, flip_x: bool) -> None:
    """Lật toạ độ các chú thích & liên kết trên `page` khớp với phép lật nội dung trang."""
    doc = page.parent
    for annot in list(page.annots() or ()):
        xref = annot.xref
        for key in ("Rect", "QuadPoints", "InkList", "L", "Vertices", "CL"):
            kind, value = doc.xref_get_key(xref, key)
            if kind == "array":
                doc.xref_set_key(
                    xref,
                    key,
                    _mirror_pdf_array(value, axis_sum, mirror_x=flip_x, normalize_pairs=(key == "Rect")),
                )
        doc.xref_set_key(xref, "M", fitz.get_pdf_str(an._pdf_now()))


def flip_page_contents(
    doc: fitz.Document,
    page_index: int,
    horizontal: bool = True,
    extra_rot: int = 0,
) -> None:
    """Lật toàn bộ nội dung trang hiện tại theo chiều ngang (`horizontal=True`) hoặc chiều dọc (`False`).

    Tính đến `/Rotate` sẵn có của trang và góc xoay xem thêm `extra_rot` để phép lật khớp đúng hướng
    người dùng đang nhìn thấy trên màn hình (kể cả khi trang đang bị cắt CropBox).
    """
    page = _check_page(doc, page_index)
    mb = fitz.Rect(page.mediabox)
    cb = fitz.Rect(page.cropbox)
    pdf_xsum = cb.x0 + cb.x1
    pdf_ysum = (mb.y0 + mb.y1 - cb.y1) + (mb.y0 + mb.y1 - cb.y0)
    total_rot = (page.rotation + extra_rot) % 360
    # Trang đang xoay 90°/270°: trục ngang màn hình chính là trục Y gốc của trang PDF (và ngược lại)
    flip_x = (not horizontal) if total_rot in (90, 270) else horizontal

    page.wrap_contents()
    contents = page.get_contents()
    if contents:
        if flip_x:
            prefix = f"q -1 0 0 1 {pdf_xsum:.6g} 0 cm\n".encode("ascii")
        else:
            prefix = f"q 1 0 0 -1 0 {pdf_ysum:.6g} cm\n".encode("ascii")
        first_bytes = doc.xref_stream(contents[0]) or b""
        if len(contents) == 1:
            doc.update_stream(contents[0], prefix + first_bytes + b"\nQ\n")
        else:
            last_bytes = doc.xref_stream(contents[-1]) or b""
            doc.update_stream(contents[0], prefix + first_bytes)
            doc.update_stream(contents[-1], last_bytes + b"\nQ\n")

    _flip_page_annotations(page, pdf_xsum if flip_x else pdf_ysum, flip_x=flip_x)


def crop_page_rect(
    doc: fitz.Document,
    page_index: int,
    rect: fitz.Rect,
    *,
    view_coords: bool = True,
) -> fitz.Rect:
    """Đặt `CropBox` mới cho trang; trả về `CropBox` cũ để Hoàn tác.

    Nếu `view_coords=True`, `rect` là toạ độ trang chưa xoay tính từ góc trên-trái của `CropBox` hiện hành
    (cùng hệ với `AnnotationController`).
    """
    page = _check_page(doc, page_index)
    old_crop = fitz.Rect(page.cropbox)
    target = fitz.Rect(rect).normalize()
    if view_coords:
        pos = page.cropbox_position
        target = target + (pos.x, pos.y, pos.x, pos.y)
    mb = fitz.Rect(page.mediabox)
    clamped = target & mb
    if clamped.is_empty or clamped.width < 12.0 or clamped.height < 12.0:
        raise PageEditError("Vùng cắt trang quá nhỏ (tối thiểu 12 × 12 pt).")
    page.set_cropbox(clamped)
    return old_crop


def crop_page_margins(
    doc: fitz.Document,
    page_index: int,
    *,
    top_pt: float = 0.0,
    bottom_pt: float = 0.0,
    left_pt: float = 0.0,
    right_pt: float = 0.0,
    reset: bool = False,
) -> fitz.Rect:
    """Cắt lề theo 4 cạnh nhìn thấy trên màn hình (tính bằng pt), hoặc khôi phục nguyên khổ `MediaBox`."""
    page = _check_page(doc, page_index)
    old_crop = fitz.Rect(page.cropbox)
    if reset:
        page.set_cropbox(fitz.Rect(page.mediabox))
        return old_crop
    pr = fitz.Rect(page.rect)  # toạ độ đang hiển thị
    new_disp = fitz.Rect(
        pr.x0 + max(0.0, left_pt),
        pr.y0 + max(0.0, top_pt),
        pr.x1 - max(0.0, right_pt),
        pr.y1 - max(0.0, bottom_pt),
    )
    if new_disp.width < 12.0 or new_disp.height < 12.0:
        raise PageEditError("Lề cắt quá lớn — phần trang còn lại phải tối thiểu 12 × 12 pt.")
    unrot = (new_disp * page.derotation_matrix).normalize()
    crop_page_rect(doc, page_index, unrot, view_coords=True)
    return old_crop


# ─── Chèn ảnh (chú thích Stamp có /AP /N Form XObject, hỗ trợ xoay/lật) ────


def image_aspect(image_bytes: bytes) -> float:
    """Tỷ lệ cao / rộng của ảnh nguồn."""
    pix = fitz.Pixmap(image_bytes)
    return max(0.05, float(pix.height) / max(1, pix.width))


def build_image_appearance(
    image_bytes: bytes,
    width: float,
    height: float,
    *,
    rotation: int = 0,
    flip_h: bool = False,
    flip_v: bool = False,
) -> Tuple[fitz.Document, float, float]:
    """Tạo trang tạm chứa ảnh theo kích thước, góc xoay và trạng thái lật ngang/dọc."""
    w, h = max(8.0, float(width)), max(8.0, float(height))
    tmp = fitz.open()
    page = tmp.new_page(width=w, height=h)
    page.insert_image(fitz.Rect(0, 0, w, h), stream=image_bytes, rotate=int(rotation) % 360, keep_proportion=False)
    if flip_h or flip_v:
        page.wrap_contents()
        contents = page.get_contents()
        if contents:
            prefix = b""
            suffix = b""
            if flip_h:
                prefix += f"q -1 0 0 1 {w:g} 0 cm\n".encode("ascii")
                suffix = b"\nQ\n" + suffix
            if flip_v:
                prefix += f"q 1 0 0 -1 0 {h:g} cm\n".encode("ascii")
                suffix = b"\nQ\n" + suffix
            if len(contents) == 1:
                tmp.update_stream(contents[0], prefix + (tmp.xref_stream(contents[0]) or b"") + suffix)
            else:
                tmp.update_stream(contents[0], prefix + (tmp.xref_stream(contents[0]) or b""))
                tmp.update_stream(contents[-1], (tmp.xref_stream(contents[-1]) or b"") + suffix)
    return tmp, w, h


def add_image_annotation(
    page: fitz.Page,
    rect: fitz.Rect,
    image_bytes: bytes,
    *,
    rotation: int = 0,
    flip_h: bool = False,
    flip_v: bool = False,
    opacity: float = 1.0,
    author: str = "",
) -> fitz.Annot:
    """Chèn ảnh lên trang dạng chú thích Stamp có `/AP /N` riêng (di chuyển, xoay, lật, xoá, Hoàn tác được)."""
    if not image_bytes:
        raise PageEditError("Dữ liệu ảnh trống.")
    box = an._display_rect(page, fitz.Rect(rect).normalize())
    if box.width < 8 or box.height < 8:
        aspect = image_aspect(image_bytes)
        w = 180.0
        h = w * aspect
        if rotation % 180 == 90:
            w, h = h, w
        box = fitz.Rect(box.x0, box.y0, box.x0 + w, box.y0 + h)
    else:
        w, h = box.width, box.height
    disp = an._fit_in_page(page, box)
    unrot = (disp * page.derotation_matrix).normalize()
    tmp, w, h = build_image_appearance(
        image_bytes, disp.width, disp.height, rotation=rotation, flip_h=flip_h, flip_v=flip_v,
    )
    annot = page.add_stamp_annot(unrot, stamp=0)
    page.parent.xref_set_key(annot.xref, "Name", f"/{APP_IMAGE_NAME}")
    style = an.AnnotStyle(color="#3B82F6", opacity=max(0.1, min(1.0, float(opacity))))
    data = {
        "kind": "image",
        "rotation": int(rotation) % 360,
        "flip_h": bool(flip_h),
        "flip_v": bool(flip_v),
        "style": {"color": style.color, "opacity": style.opacity},
    }
    an._custom_annot_finish(page, annot, tmp, unrot, style, data, "Hình ảnh", author)
    return annot


def rebuild_image_annotation(
    page: fitz.Page,
    xref: int,
    image_bytes: bytes,
    *,
    rotate_delta: int = 0,
    toggle_flip_h: bool = False,
    toggle_flip_v: bool = False,
) -> Tuple[int, bool, bool]:
    """Xoay hoặc lật ảnh đã chèn (`xref`) và dựng lại `/AP /N` giữ tâm khung."""
    doc = page.parent
    data = an.qt_data(doc, xref)
    if data.get("kind") != "image":
        raise PageEditError("Đối tượng đang chọn không phải hình ảnh do QT PDF Pro chèn.")
    annot = page.load_annot(xref)
    disp = an._display_rect(page, annot.rect)
    cx = (disp.x0 + disp.x1) / 2.0
    cy = (disp.y0 + disp.y1) / 2.0
    w, h = disp.width, disp.height

    rot = (int(data.get("rotation", 0)) + rotate_delta) % 360
    flip_h = bool(data.get("flip_h", False)) ^ bool(toggle_flip_h)
    flip_v = bool(data.get("flip_v", False)) ^ bool(toggle_flip_v)
    if rotate_delta % 180 == 90:
        w, h = h, w

    new_disp = an._fit_in_page(page, fitz.Rect(cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0))
    unrot = (new_disp * page.derotation_matrix).normalize()
    tmp, _, _ = build_image_appearance(
        image_bytes, new_disp.width, new_disp.height, rotation=rot, flip_h=flip_h, flip_v=flip_v,
    )
    style_dict = data.get("style") or {}
    style = an.AnnotStyle(
        color=str(style_dict.get("color") or "#3B82F6"),
        opacity=float(style_dict.get("opacity", 1.0)),
    )
    new_data = {
        "kind": "image",
        "rotation": rot,
        "flip_h": flip_h,
        "flip_v": flip_v,
        "style": style_dict,
    }
    an._custom_annot_finish(page, annot, tmp, unrot, style, new_data, "Hình ảnh", None)
    return rot, flip_h, flip_v


def render_annot_png(page: fitz.Page, xref: int, scale: float = 2.0) -> bytes:
    """Kết xuất ảnh PNG từ vùng `/Rect` của annotation trên trang tạm sạch (dự phòng khi thiếu bytes gốc)."""
    annot = page.load_annot(xref)
    r = an._display_rect(page, annot.rect)
    tmp = fitz.open()
    try:
        tp = tmp.new_page(width=max(8.0, r.width), height=max(8.0, r.height))
        kind, ap = page.parent.xref_get_key(xref, "AP")
        if kind == "dict":
            pix = annot.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=True)
            return pix.tobytes("png")
        tp.show_pdf_page(tp.rect, page.parent, page.number, clip=annot.rect)
        return tp.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=True).tobytes("png")
    finally:
        tmp.close()


# ─── Liên kết & Che thông tin nhạy cảm ───────────────────────────────────


def add_link_on_page(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    uri: str = "",
    target_page: Optional[int] = None,
) -> dict:
    """Chèn liên kết (URL web hoặc nhảy tới trang 0-based) vào vùng `rect` trên trang."""
    box = fitz.Rect(rect).normalize()
    if box.width < 4 or box.height < 4:
        box = fitz.Rect(box.x0, box.y0, box.x0 + 120, box.y0 + 24)
    if uri.strip():
        link = {"kind": fitz.LINK_URI, "from": box, "uri": uri.strip()}
    elif target_page is not None:
        max_p = max(0, page.parent.page_count - 1)
        pno = max(0, min(max_p, int(target_page)))
        link = {"kind": fitz.LINK_GOTO, "from": box, "page": pno, "to": fitz.Point(0, 0)}
    else:
        raise PageEditError("Hãy nhập địa chỉ liên kết (URL) hoặc trang đích.")
    page.insert_link(link)
    return link


def add_redaction_on_page(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    text: str = "",
    fill: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> fitz.Annot:
    """Đánh dấu vùng cần che vĩnh viễn trên trang."""
    box = fitz.Rect(rect).normalize()
    if box.width < 4 or box.height < 4:
        raise PageEditError("Vùng đánh dấu che quá nhỏ.")
    annot = page.add_redact_annot(box, text=text, fill=fill)
    annot.update()
    return annot


def mark_redactions_for_text(doc: fitz.Document, needle: str, pages: Optional[Sequence[int]] = None) -> int:
    """Tìm cụm từ và đánh dấu che đỏ trên các trang được chọn."""
    q = an._nfc(needle).strip()
    if not q:
        raise PageEditError("Hãy nhập từ khoá cần che.")
    targets = list(pages) if pages is not None else list(range(doc.page_count))
    count = 0
    for pno in targets:
        page = _check_page(doc, pno)
        rects = list(page.search_for(q))
        if not rects and " " in q:
            rects = list(page.search_for(q.replace(" ", "\u00a0")))
        for r in rects:
            page.add_redact_annot(r, fill=(0.0, 0.0, 0.0))
            count += 1
    return count


def apply_document_redactions(doc: fitz.Document, pages: Optional[Sequence[int]] = None) -> int:
    """Áp dụng xoá vĩnh viễn mọi vùng đã đánh dấu Redact trên tài liệu."""
    targets = list(pages) if pages is not None else list(range(doc.page_count))
    applied = 0
    for pno in targets:
        page = _check_page(doc, pno)
        has_redact = any(a.type[1] == "Redact" for a in (page.annots() or ()))
        if has_redact:
            page.apply_redactions()
            applied += 1
    return applied


# ─── Đầu trang & Chân trang, Bates, Nền trang, Đính kèm, Làm sạch ─────────


def _format_hf_text(template: str, page_num: int, total_pages: int) -> str:
    if not template:
        return ""
    today_str = date.today().strftime("%d/%m/%Y")
    text = (
        template.replace("{trang}", "{page}")
        .replace("{n}", "{page}")
        .replace("{tong}", "{total}")
        .replace("{ngay}", "{date}")
    )
    return an._nfc(
        text.replace("{page}", str(page_num))
        .replace("{total}", str(total_pages))
        .replace("{date}", today_str)
    )


def apply_header_footer_in_doc(
    doc: fitz.Document,
    *,
    header_left: str = "",
    header_center: str = "",
    header_right: str = "",
    footer_left: str = "",
    footer_center: str = "",
    footer_right: str = "",
    font_size: float = 10.0,
    font_family: str = "serif",
    color: str = "#111827",
    margin_mm: float = 12.0,
    skip_first: bool = False,
    pages_spec: str = "",
) -> int:
    """Đóng đầu trang && chân trang trực tiếp vào các trang của `doc`."""
    slots: List[Tuple[str, str]] = [
        ("top-left", header_left),
        ("top-center", header_center),
        ("top-right", header_right),
        ("bottom-left", footer_left),
        ("bottom-center", footer_center),
        ("bottom-right", footer_right),
    ]
    active = [(pos, tmpl.strip()) for pos, tmpl in slots if tmpl and tmpl.strip()]
    if not active:
        raise PageEditError("Hãy nhập ít nhất một nội dung cho Đầu trang hoặc Chân trang.")
    targets = parse_page_selection(pages_spec, doc.page_count)
    total = doc.page_count
    stamps = _TextStamps(font_family, False, font_size, color, 1.0)
    applied = 0
    try:
        placed_jobs = []
        for idx, pno in enumerate(targets):
            if skip_first and idx == 0:
                continue
            for pos, tmpl in active:
                txt = _format_hf_text(tmpl, pno + 1, total)
                if txt:
                    placed_jobs.append((pno, pos, stamps.add(txt)))
        if not placed_jobs:
            return 0
        stamps.finish()
        margin = float(margin_mm) * MM
        side = 18.0 * MM
        seen_pages = set()
        for pno, pos, lbl in placed_jobs:
            page = doc[pno]
            r = page.rect
            hw, hh = (lbl.width + 2 * lbl.pad_x) / 2.0, (lbl.height + 2 * lbl.pad_y) / 2.0
            cx = (
                max(side + hw, r.width * 0.12)
                if pos.endswith("left")
                else min(r.width - side - hw, r.width * 0.88)
                if pos.endswith("right")
                else r.width / 2.0
            )
            cy = max(margin + hh, hh + 4) if pos.startswith("top") else min(r.height - margin - hh, r.height - hh - 4)
            stamps.place(page, lbl, fitz.Point(cx, cy), angle=0.0, behind=False)
            seen_pages.add(pno)
        applied = len(seen_pages)
    finally:
        stamps.close()
    return applied


def apply_bates_in_doc(
    doc: fitz.Document,
    *,
    prefix: str = "BATES-",
    suffix: str = "",
    start: int = 1,
    digits: int = 6,
    position: str = "top-right",
    font_size: float = 10.0,
    color: str = "#111827",
    margin_mm: float = 10.0,
    pages_spec: str = "",
) -> int:
    """Đánh số Bates tuần tự trên các trang của `doc`."""
    targets = parse_page_selection(pages_spec, doc.page_count)
    d = max(1, min(12, int(digits)))
    stamps = _TextStamps("sans", True, font_size, color, 1.0)
    try:
        items = []
        num = int(start)
        for pno in targets:
            txt = f"{prefix}{num:0{d}d}{suffix}"
            items.append((pno, stamps.add(txt)))
            num += 1
        if not items:
            return 0
        stamps.finish()
        margin = float(margin_mm) * MM
        side = 16.0 * MM
        for pno, lbl in items:
            page = doc[pno]
            r = page.rect
            hw, hh = (lbl.width + 2 * lbl.pad_x) / 2.0, (lbl.height + 2 * lbl.pad_y) / 2.0
            cx = (
                max(side + hw, r.width * 0.12)
                if position.endswith("left")
                else min(r.width - side - hw, r.width * 0.88)
                if position.endswith("right")
                else r.width / 2.0
            )
            cy = max(margin + hh, hh + 4) if position.startswith("top") else min(r.height - margin - hh, r.height - hh - 4)
            stamps.place(page, lbl, fitz.Point(cx, cy), angle=0.0, behind=False)
        return len(items)
    finally:
        stamps.close()


def apply_background_in_doc(
    doc: fitz.Document,
    *,
    color: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    opacity: float = 1.0,
    pages_spec: str = "",
) -> int:
    """Thêm màu nền hoặc ảnh nền phía sau nội dung (`overlay=False`) trên các trang chọn."""
    if not color and not image_bytes:
        raise PageEditError("Hãy chọn màu nền hoặc tệp ảnh nền.")
    targets = parse_page_selection(pages_spec, doc.page_count)
    op = max(0.05, min(1.0, float(opacity)))
    rgb = an.parse_color(color) if color else None
    for pno in targets:
        page = _check_page(doc, pno)
        if image_bytes:
            page.insert_image(page.rect, stream=image_bytes, keep_proportion=False, overlay=False)
        if rgb is not None:
            shape = page.new_shape()
            shape.draw_rect(page.rect)
            shape.finish(color=None, fill=rgb, fill_opacity=op, width=0)
            shape.commit(overlay=False)
    return len(targets)


def attach_file_to_doc(doc: fitz.Document, file_path: str | Path, description: str = "") -> str:
    """Nhúng một tệp đính kèm vào PDF (EmbeddedFiles)."""
    path = Path(file_path)
    if not path.is_file():
        raise PageEditError(f"Không tìm thấy tệp để đính kèm: {path}")
    data = path.read_bytes()
    name = path.name
    existing = set(doc.embfile_names() or [])
    candidate = name
    idx = 1
    while candidate in existing:
        candidate = f"{path.stem}_{idx}{path.suffix}"
        idx += 1
    doc.embfile_add(candidate, data, filename=candidate, ufilename=candidate, desc=description or candidate)
    return candidate


def sanitize_doc_in_place(doc: fitz.Document) -> None:
    """Làm sạch siêu dữ liệu, JavaScript, tệp ẩn và thông tin nhạy cảm trên tài liệu."""
    scrub_opts = dict(
        metadata=True,
        xml_metadata=True,
        attached_files=False,
        embedded_files=False,
        thumbnails=True,
        reset_responses=True,
        reset_fields=False,
        hidden_text=True,
        javascript=True,
        remove_links=False,
    )
    try:
        doc.scrub(**scrub_opts)
    except Exception:
        # Một số phiên bản PyMuPDF báo lỗi xref sau thao tác liên kết/redact chưa ghi —
        # nén dọn rác sang tài liệu sạch tạm để scrub trang, rồi nạp lại trang và làm sạch siêu dữ liệu trên doc.
        clean_bytes = doc.tobytes(garbage=3, deflate=False)
        src = fitz.open("pdf", clean_bytes)
        try:
            src.scrub(**scrub_opts)
            old_n = doc.page_count
            doc.insert_pdf(src)
            if old_n > 0:
                doc.delete_pages(list(range(old_n)))
        finally:
            src.close()
        try:
            cat_xref = doc.pdf_catalog()
            if cat_xref > 0:
                for key in ("OpenAction", "AA"):
                    if doc.xref_get_key(cat_xref, key)[0] != "null":
                        doc.xref_set_key(cat_xref, key, "null")
                names_ref = doc.xref_get_key(cat_xref, "Names")
                if names_ref[0] == "xref":
                    nx = int(names_ref[1].split()[0])
                    if doc.xref_get_key(nx, "JavaScript")[0] != "null":
                        doc.xref_set_key(nx, "JavaScript", "null")
        except Exception:
            pass
    doc.set_metadata({})
    try:
        doc.del_xml_metadata()
    except Exception:
        pass


# ─── Khổ giấy, Tạo trang trắng, Đổi khổ trang ─────────────────────────────


def resolve_page_size_pt(
    preset: str = "A4",
    *,
    orientation: str = "portrait",
    width_mm: Optional[float] = None,
    height_mm: Optional[float] = None,
) -> Tuple[float, float]:
    """Quy đổi tên khổ giấy chuẩn (`A4`, `A5`, `A3`, `B5`, `LETTER`, `LEGAL`, `custom`) + hướng sang `(w_pt, h_pt)`."""
    key = (preset or "A4").strip()
    if key.lower() == "custom":
        if width_mm is None or height_mm is None:
            raise PageEditError("Hãy nhập đầy đủ chiều rộng và chiều cao (mm) cho khổ giấy tuỳ chỉnh.")
        w_mm = float(width_mm)
        h_mm = float(height_mm)
        if not (20.0 <= w_mm <= 2000.0 and 20.0 <= h_mm <= 2000.0):
            raise PageEditError("Kích thước khổ giấy tuỳ chỉnh phải nằm trong khoảng 20 – 2000 mm.")
    else:
        spec = _PAGE_SIZE_MAP.get(key.upper())
        if spec is None:
            raise PageEditError(f"Khổ giấy không được hỗ trợ: {preset}")
        w_mm, h_mm = spec
    w_pt, h_pt = w_mm * MM, h_mm * MM
    ori = (orientation or "portrait").strip().lower()
    if ori == "landscape" and w_pt < h_pt:
        w_pt, h_pt = h_pt, w_pt
    elif ori == "portrait" and w_pt > h_pt:
        w_pt, h_pt = h_pt, w_pt
    return float(w_pt), float(h_pt)


def create_blank_pdf_bytes(
    preset: str = "A4",
    *,
    orientation: str = "portrait",
    width_mm: Optional[float] = None,
    height_mm: Optional[float] = None,
    page_count: int = 1,
) -> bytes:
    """Tạo tài liệu PDF trắng mới với khổ giấy và số trang chọn sẵn."""
    w_pt, h_pt = resolve_page_size_pt(
        preset, orientation=orientation, width_mm=width_mm, height_mm=height_mm
    )
    n = max(1, min(200, int(page_count)))
    doc = fitz.open()
    try:
        for _ in range(n):
            doc.new_page(width=w_pt, height=h_pt)
        return doc.tobytes(deflate=True)
    finally:
        doc.close()


def insert_sized_blank_page(
    doc: fitz.Document,
    after_index: int = -1,
    *,
    preset: str = "same",
    orientation: str = "portrait",
    width_mm: Optional[float] = None,
    height_mm: Optional[float] = None,
    count: int = 1,
    before: bool = False,
) -> int:
    """Chèn 1 hoặc nhiều trang trắng theo khổ chọn (hoặc cùng kích thước trang hiện tại) vào `doc`.

    Trả về chỉ số 0-based của trang đầu tiên vừa chèn.
    """
    key = (preset or "same").strip()
    if key.lower() == "same" and doc.page_count > 0:
        ref_idx = max(0, min(doc.page_count - 1, int(after_index)))
        r = doc[ref_idx].rect
        w_pt, h_pt = float(r.width), float(r.height)
    else:
        eff_preset = "A4" if key.lower() == "same" else key
        w_pt, h_pt = resolve_page_size_pt(
            eff_preset, orientation=orientation, width_mm=width_mm, height_mm=height_mm
        )
    if doc.page_count == 0:
        insert_at = 0
    else:
        ref_idx = max(0, min(doc.page_count - 1, int(after_index)))
        insert_at = ref_idx if before else ref_idx + 1
    n = max(1, min(200, int(count)))
    for i in range(n):
        doc.new_page(pno=insert_at + i, width=w_pt, height=h_pt)
    return insert_at


def _copy_annot_ap_xobject(
    src: fitz.Document, src_annot_xref: int, dst: fitz.Document, *, strip_matrix: bool
) -> Optional[int]:
    """Sao chép `/AP /N` Form XObject từ chú thích nguồn sang tài liệu đích."""
    kind, val = src.xref_get_key(src_annot_xref, "AP/N")
    if kind != "xref":
        return None
    src_xo = int(val.split()[0])
    mapping: Dict[int, int] = {}

    def copy(xref: int) -> int:
        if xref in mapping:
            return mapping[xref]
        new = dst.get_new_xref()
        mapping[xref] = new
        obj = src.xref_object(xref, compressed=True)
        obj = an._REF_RE.sub(lambda m: f"{copy(int(m.group(1)))} 0 R", obj)
        dst.update_object(new, obj)
        if src.xref_is_stream(xref):
            for k in ("Filter", "DecodeParms"):
                dst.xref_set_key(new, k, "null")
            dst.update_stream(new, src.xref_stream(xref))
        return new

    new_xo = copy(src_xo)
    if strip_matrix:
        dst.xref_set_key(new_xo, "Matrix", "null")
    return new_xo


def _copy_scaled_annotations_and_links(
    src: fitz.Document,
    src_page: fitz.Page,
    dst: fitz.Document,
    new_pg: fitz.Page,
    old_rect: fitz.Rect,
    dest_rect: fitz.Rect,
) -> None:
    """Chép & quy đổi toạ độ các liên kết và chú thích từ `src_page` sang `new_pg`."""
    ow = max(1e-6, old_rect.width)
    oh = max(1e-6, old_rect.height)
    sx = dest_rect.width / ow
    sy = dest_rect.height / oh

    def map_pt(p: fitz.Point) -> fitz.Point:
        return fitz.Point(
            dest_rect.x0 + (p.x - old_rect.x0) * sx,
            dest_rect.y0 + (p.y - old_rect.y0) * sy,
        )

    def map_disp_rect(r: fitz.Rect) -> fitz.Rect:
        p0 = map_pt(fitz.Point(r.x0, r.y0))
        p1 = map_pt(fitz.Point(r.x1, r.y1))
        return fitz.Rect(p0, p1).normalize()

    rot_mat = src_page.rotation_matrix
    src_rot = src_page.rotation % 360

    for lk in list(src_page.get_links() or ()):
        fr = lk.get("from")
        if fr is None:
            continue
        mapped = map_disp_rect(fitz.Rect(fr)) & new_pg.rect
        if mapped.is_empty or mapped.width < 1.0 or mapped.height < 1.0:
            continue
        nlk = dict(lk)
        nlk.pop("xref", None)
        nlk.pop("id", None)
        nlk["from"] = mapped
        try:
            new_pg.insert_link(nlk)
        except Exception:
            pass

    for annot in list(src_page.annots() or ()):
        if an.is_marked_deleted(src, annot.xref):
            continue
        subtype = annot.type[1]
        if subtype == "Popup":
            continue
        disp = (fitz.Rect(annot.rect) * rot_mat).normalize()
        mapped_disp = map_disp_rect(disp)
        if not mapped_disp.intersects(new_pg.rect):
            continue
        target_rect = (mapped_disp & new_pg.rect).normalize()
        if target_rect.width < 1.0 or target_rect.height < 1.0:
            continue

        data = an.qt_data(src, annot.xref)
        if data:
            new_annot = None
            kind = data.get("kind")
            if kind in ("textbox", "filltext"):
                new_annot = new_pg.add_freetext_annot(target_rect, "Text", fontsize=12)
            elif kind in ("stamp", "fillmark", "signature", "image", "pdfpage"):
                new_annot = new_pg.add_stamp_annot(target_rect, stamp=0)
            if new_annot is not None:
                xo = _copy_annot_ap_xobject(src, annot.xref, dst, strip_matrix=(src_rot != 0))
                if xo is not None:
                    an._set_rect_key(new_pg, new_annot.xref, target_rect)
                    dst.xref_set_key(new_annot.xref, "AP", f"<</N {xo} 0 R>>")
                    for key in ("Name", "Contents", "T", "CA", "M", "CreationDate", "IT", an.QT_KEY):
                        k_kind, k_val = src.xref_get_key(annot.xref, key)
                        if k_kind != "null":
                            dst.xref_set_key(
                                new_annot.xref,
                                key,
                                fitz.get_pdf_str(k_val) if k_kind == "string" else k_val,
                            )
                continue

        info = annot.info or {}
        colors = annot.colors or {}
        stroke = colors.get("stroke")
        fill = colors.get("fill")
        opacity = float(annot.opacity if annot.opacity is not None else 1.0)
        bw = float((annot.border or {}).get("width") or 1.5)
        try:
            new_a = None
            if subtype in an.MARKUP_SUBTYPES:
                quads = [
                    map_disp_rect((r * rot_mat).normalize()).quad
                    for r in (an._quad_rects(annot.vertices) or [annot.rect])
                ]
                creators = {
                    "Highlight": new_pg.add_highlight_annot,
                    "Underline": new_pg.add_underline_annot,
                    "StrikeOut": new_pg.add_strikeout_annot,
                    "Squiggly": new_pg.add_squiggly_annot,
                }
                new_a = creators[subtype](quads)
            elif subtype in ("Square", "Circle"):
                new_a = new_pg.add_rect_annot(target_rect) if subtype == "Square" else new_pg.add_circle_annot(target_rect)
                new_a.set_border(width=max(0.25, bw * min(sx, sy)))
            elif subtype == "Redact":
                new_a = new_pg.add_redact_annot(target_rect, fill=fill or (0.0, 0.0, 0.0))
            elif subtype == "Ink":
                verts = annot.vertices or []
                strokes = verts if verts and isinstance(verts[0], list) else [verts]
                mapped_strokes = [
                    [(mp.x, mp.y) for mp in (map_pt(fitz.Point(v) * rot_mat) for v in s)]
                    for s in strokes
                    if s
                ]
                if mapped_strokes:
                    new_a = new_pg.add_ink_annot(mapped_strokes)
                    new_a.set_border(width=max(0.25, bw * min(sx, sy)))
            elif subtype == "Line" and annot.vertices and len(annot.vertices) >= 2:
                p0 = map_pt(fitz.Point(annot.vertices[0]) * rot_mat)
                p1 = map_pt(fitz.Point(annot.vertices[1]) * rot_mat)
                new_a = new_pg.add_line_annot(p0, p1)
                new_a.set_border(width=max(0.25, bw * min(sx, sy)))
            elif subtype == "Text":
                new_a = new_pg.add_text_annot(fitz.Point(target_rect.x0, target_rect.y0), info.get("content") or "")
            if new_a is not None:
                if stroke or fill:
                    kw = {}
                    if stroke:
                        kw["stroke"] = stroke
                    if fill and subtype not in an.MARKUP_SUBTYPES:
                        kw["fill"] = fill
                    if kw:
                        new_a.set_colors(**kw)
                if opacity < 1.0:
                    new_a.set_opacity(opacity)
                if info.get("title") or info.get("content"):
                    new_a.set_info(title=info.get("title") or "", content=info.get("content") or "")
                new_a.update()
        except Exception:
            pass


def resize_pages_in_doc(
    doc: fitz.Document,
    *,
    preset: str = "A4",
    orientation: str = "portrait",
    width_mm: Optional[float] = None,
    height_mm: Optional[float] = None,
    scale_mode: str = "fit",
    pages_spec: str = "",
) -> int:
    """Đổi khổ giấy (A4, A5, A3, B5, Letter, Legal hoặc tuỳ chỉnh mm) cho các trang được chọn.

    `scale_mode`:
      - `"fit"`: co giãn đều nội dung cho vừa khổ giấy mới (giữ tỷ lệ, căn giữa).
      - `"center"`: chỉ đổi kích thước tờ giấy, giữ nguyên tỷ lệ 1:1 của nội dung và đặt ở giữa.
      - `"stretch"`: kéo giãn nội dung vừa khít 100% cả chiều ngang và chiều dọc của khổ mới.
    `orientation`: `"portrait"` | `"landscape"` | `"auto"` (giữ nguyên hướng dọc/ngang của từng trang).
    """
    if scale_mode not in ("fit", "center", "stretch"):
        raise PageEditError(f"Chế độ co giãn không hợp lệ: {scale_mode}")
    targets = parse_page_selection(pages_spec, doc.page_count)
    if not targets:
        return 0
    ori = (orientation or "portrait").strip().lower()
    base_ori = "portrait" if ori == "auto" else ori
    base_w, base_h = resolve_page_size_pt(
        preset, orientation=base_ori, width_mm=width_mm, height_mm=height_mm
    )

    src = fitz.open("pdf", doc.tobytes(deflate=False))
    try:
        for pno in targets:
            src_page = src[pno]
            old_rect = fitz.Rect(src_page.rect)
            old_w, old_h = max(1.0, float(old_rect.width)), max(1.0, float(old_rect.height))
            w_new, h_new = base_w, base_h
            if ori == "auto" and (old_w > old_h) != (w_new > h_new):
                w_new, h_new = h_new, w_new

            if scale_mode == "fit":
                s = min(w_new / old_w, h_new / old_h)
                dw, dh = old_w * s, old_h * s
                dest_rect = fitz.Rect((w_new - dw) / 2.0, (h_new - dh) / 2.0, (w_new + dw) / 2.0, (h_new + dh) / 2.0)
            elif scale_mode == "center":
                dw, dh = old_w, old_h
                dest_rect = fitz.Rect((w_new - dw) / 2.0, (h_new - dh) / 2.0, (w_new + dw) / 2.0, (h_new + dh) / 2.0)
            else:
                dest_rect = fitz.Rect(0.0, 0.0, w_new, h_new)

            new_pg = doc.new_page(pno=pno, width=w_new, height=h_new)
            has_content = bool(
                src_page.read_contents().strip()
                or src_page.get_images()
                or src_page.get_drawings()
                or src_page.get_xobjects()
            )
            if has_content:
                vis = dest_rect & new_pg.rect
                if not vis.is_empty and vis.width >= 0.5 and vis.height >= 0.5:
                    try:
                        if abs(vis.x0 - dest_rect.x0) < 0.01 and abs(vis.y0 - dest_rect.y0) < 0.01 and abs(vis.x1 - dest_rect.x1) < 0.01 and abs(vis.y1 - dest_rect.y1) < 0.01:
                            new_pg.show_pdf_page(dest_rect, src, pno, keep_proportion=(scale_mode != "stretch"))
                        else:
                            sx_inv = old_w / max(1e-6, dest_rect.width)
                            sy_inv = old_h / max(1e-6, dest_rect.height)
                            clip = fitz.Rect(
                                old_rect.x0 + (vis.x0 - dest_rect.x0) * sx_inv,
                                old_rect.y0 + (vis.y0 - dest_rect.y0) * sy_inv,
                                old_rect.x0 + (vis.x1 - dest_rect.x0) * sx_inv,
                                old_rect.y0 + (vis.y1 - dest_rect.y0) * sy_inv,
                            ) & old_rect
                            if not clip.is_empty and clip.width >= 0.5 and clip.height >= 0.5:
                                new_pg.show_pdf_page(vis, src, pno, clip=clip, keep_proportion=False)
                    except ValueError:
                        pass

            _copy_scaled_annotations_and_links(src, src_page, doc, new_pg, old_rect, dest_rect)
            doc.delete_page(pno + 1)
    finally:
        src.close()
    return len(targets)


# ─── Nhúng trang PDF khác vào mặt trang (Form XObject vector sắc nét) ─────


def _pack_pdf_z64(data: bytes) -> Optional[str]:
    if not data:
        return None
    comp = zlib.compress(data, level=6)
    if len(comp) > _MAX_EMBED_PDF_Z64_BYTES:
        return None
    return base64.b64encode(comp).decode("ascii")


def _unpack_pdf_z64(data_dict: dict) -> Optional[bytes]:
    raw = data_dict.get("pdf_z64")
    if isinstance(raw, str) and raw:
        try:
            return zlib.decompress(base64.b64decode(raw.encode("ascii")))
        except Exception:
            return None
    return None


def extract_single_page_pdf_bytes(src_doc: fitz.Document, page_index: int) -> Tuple[bytes, float, float]:
    """Tách 1 trang từ `src_doc` thành PDF 1 trang (làm phẳng chú thích) và trả về `(bytes, rộng_pt, cao_pt)`."""
    if not 0 <= page_index < src_doc.page_count:
        raise PageEditError(f"Trang nguồn {page_index + 1} không tồn tại.")
    one = fitz.open()
    try:
        one.insert_pdf(src_doc, from_page=page_index, to_page=page_index)
        if any(True for _ in (one[0].annots() or ())):
            an.flatten_annotations(one)
        r = one[0].rect
        w, h = float(r.width), float(r.height)
        return one.tobytes(garbage=3, deflate=True), w, h
    finally:
        one.close()


def build_pdf_page_appearance(
    page_pdf_bytes: bytes,
    width: float,
    height: float,
    *,
    rotation: int = 0,
    flip_h: bool = False,
    flip_v: bool = False,
    border_color: Optional[str] = "#CBD5E1",
    border_width: float = 0.6,
) -> Tuple[fitz.Document, float, float]:
    """Dựng trang tạm chứa trang PDF được nhúng (giữ nguyên vector, hỗ trợ xoay/lật và khung viền mảnh)."""
    if not page_pdf_bytes:
        raise PageEditError("Dữ liệu trang PDF cần nhúng bị trống.")
    w, h = max(8.0, float(width)), max(8.0, float(height))
    src = fitz.open("pdf", page_pdf_bytes)
    tmp = fitz.open()
    try:
        if src.page_count == 0:
            raise PageEditError("Tài liệu PDF nguồn không có trang nào.")
        page = tmp.new_page(width=w, height=h)
        src_pg = src[0]
        has_content = bool(
            src_pg.read_contents().strip()
            or src_pg.get_images()
            or src_pg.get_drawings()
            or src_pg.get_xobjects()
        )
        if has_content:
            try:
                page.show_pdf_page(
                    fitz.Rect(0, 0, w, h),
                    src,
                    0,
                    rotate=int(rotation) % 360,
                    keep_proportion=False,
                )
            except ValueError:
                pass
        if flip_h or flip_v:
            page.wrap_contents()
            contents = page.get_contents()
            if contents:
                prefix = b""
                suffix = b""
                if flip_h:
                    prefix += f"q -1 0 0 1 {w:g} 0 cm\n".encode("ascii")
                    suffix = b"\nQ\n" + suffix
                if flip_v:
                    prefix += f"q 1 0 0 -1 0 {h:g} cm\n".encode("ascii")
                    suffix = b"\nQ\n" + suffix
                if len(contents) == 1:
                    tmp.update_stream(contents[0], prefix + (tmp.xref_stream(contents[0]) or b"") + suffix)
                else:
                    tmp.update_stream(contents[0], prefix + (tmp.xref_stream(contents[0]) or b""))
                    tmp.update_stream(contents[-1], (tmp.xref_stream(contents[-1]) or b"") + suffix)
        if border_color and border_width > 0:
            inset = float(border_width) / 2.0
            shape = page.new_shape()
            shape.draw_rect(fitz.Rect(inset, inset, max(inset + 1.0, w - inset), max(inset + 1.0, h - inset)))
            shape.finish(color=an.parse_color(border_color), width=float(border_width))
            shape.commit()
        return tmp, w, h
    except Exception:
        tmp.close()
        raise
    finally:
        src.close()


def add_pdf_page_annotation(
    page: fitz.Page,
    rect: fitz.Rect,
    page_pdf_bytes: bytes,
    *,
    source_name: str = "",
    source_page_1based: int = 1,
    rotation: int = 0,
    flip_h: bool = False,
    flip_v: bool = False,
    opacity: float = 1.0,
    border_color: Optional[str] = "#CBD5E1",
    border_width: float = 0.6,
    author: str = "",
) -> fitz.Annot:
    """Chèn 1 trang PDF khác lên trang hiện tại dưới dạng đối tượng độc lập sắc nét vector (kéo thả, đổi cỡ được)."""
    if not page_pdf_bytes:
        raise PageEditError("Dữ liệu trang PDF nguồn trống.")
    box = an._display_rect(page, fitz.Rect(rect).normalize())
    if box.width < 8 or box.height < 8:
        box = fitz.Rect(box.x0, box.y0, box.x0 + 220.0, box.y0 + 310.0)
    disp = an._fit_in_page(page, box)
    unrot = (disp * page.derotation_matrix).normalize()
    tmp, w, h = build_pdf_page_appearance(
        page_pdf_bytes,
        disp.width,
        disp.height,
        rotation=rotation,
        flip_h=flip_h,
        flip_v=flip_v,
        border_color=border_color,
        border_width=border_width,
    )
    annot = page.add_stamp_annot(unrot, stamp=0)
    page.parent.xref_set_key(annot.xref, "Name", f"/{APP_PDF_PAGE_NAME}")
    style = an.AnnotStyle(color=border_color or "#3B82F6", opacity=max(0.1, min(1.0, float(opacity))))
    data: dict = {
        "kind": "pdfpage",
        "source_name": source_name,
        "source_page": int(source_page_1based),
        "rotation": int(rotation) % 360,
        "flip_h": bool(flip_h),
        "flip_v": bool(flip_v),
        "border_color": border_color or "",
        "border_width": float(border_width),
        "aspect": float(h / max(1.0, w)),
        "style": {"color": style.color, "opacity": style.opacity},
    }
    z64 = _pack_pdf_z64(page_pdf_bytes)
    if z64:
        data["pdf_z64"] = z64
    label = (
        f"Trang {source_page_1based} ({source_name})"
        if source_name
        else f"Trang PDF #{source_page_1based}"
    )
    an._custom_annot_finish(page, annot, tmp, unrot, style, data, label, author)
    return annot


def rebuild_pdf_page_annotation(
    page: fitz.Page,
    xref: int,
    page_pdf_bytes: Optional[bytes] = None,
    *,
    new_unrot_rect: Optional[fitz.Rect] = None,
    rotate_delta: int = 0,
    toggle_flip_h: bool = False,
    toggle_flip_v: bool = False,
) -> Tuple[int, bool, bool]:
    """Dựng lại hình hiển thị của trang PDF nhúng (`xref`) khi đổi cỡ, xoay 90° hoặc lật."""
    doc = page.parent
    data = an.qt_data(doc, xref)
    if data.get("kind") != "pdfpage":
        raise PageEditError("Đối tượng đang chọn không phải trang PDF nhúng.")
    raw_pdf = page_pdf_bytes or _unpack_pdf_z64(data)
    annot = page.load_annot(xref)
    rot = (int(data.get("rotation", 0)) + rotate_delta) % 360
    flip_h = bool(data.get("flip_h", False)) ^ bool(toggle_flip_h)
    flip_v = bool(data.get("flip_v", False)) ^ bool(toggle_flip_v)

    if new_unrot_rect is not None:
        disp = an._fit_in_page(page, an._display_rect(page, fitz.Rect(new_unrot_rect).normalize()))
        if disp.width < 12.0 or disp.height < 12.0:
            disp = fitz.Rect(disp.x0, disp.y0, disp.x0 + max(12.0, disp.width), disp.y0 + max(12.0, disp.height))
    else:
        disp = an._display_rect(page, annot.rect)
        cx = (disp.x0 + disp.x1) / 2.0
        cy = (disp.y0 + disp.y1) / 2.0
        w, h = disp.width, disp.height
        if rotate_delta % 180 == 90:
            w, h = h, w
        disp = an._fit_in_page(page, fitz.Rect(cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0))

    unrot = (disp * page.derotation_matrix).normalize()
    border_color = data.get("border_color") or None
    border_width = float(data.get("border_width", 0.0))
    if raw_pdf:
        tmp, _, _ = build_pdf_page_appearance(
            raw_pdf,
            disp.width,
            disp.height,
            rotation=rot,
            flip_h=flip_h,
            flip_v=flip_v,
            border_color=border_color,
            border_width=border_width,
        )
    else:
        fallback_png = render_annot_png(page, xref, scale=3.0)
        tmp, _, _ = build_image_appearance(
            fallback_png,
            disp.width,
            disp.height,
            rotation=rotate_delta % 360,
            flip_h=toggle_flip_h,
            flip_v=toggle_flip_v,
        )
    style_dict = data.get("style") or {}
    style = an.AnnotStyle(
        color=str(style_dict.get("color") or "#3B82F6"),
        opacity=float(style_dict.get("opacity", 1.0)),
    )
    new_data = dict(data)
    new_data.update(
        {
            "kind": "pdfpage",
            "rotation": rot,
            "flip_h": flip_h,
            "flip_v": flip_v,
            "aspect": float(disp.height / max(1.0, disp.width)),
            "style": style_dict,
        }
    )
    content = str((annot.info or {}).get("content") or "Trang PDF nhúng")
    an._custom_annot_finish(page, annot, tmp, unrot, style, new_data, content, None)
    return rot, flip_h, flip_v


def layout_embedded_pages_rects(
    page_rect: fitz.Rect,
    aspects: Sequence[float],
    *,
    layout_mode: str = "auto_grid",
    margin_pt: float = 12.0 * MM,
    gap_pt: float = 5.0 * MM,
) -> List[fitz.Rect]:
    """Tính toạ độ (hệ hiển thị của trang đích) đặt `N` trang PDF theo kiểu chia lưới hoặc xếp tự do."""
    n = len(aspects)
    if n == 0:
        return []
    pr = fitz.Rect(page_rect)
    margin = max(0.0, min(float(margin_pt), min(pr.width, pr.height) * 0.25))
    gap = max(2.0, float(gap_pt))
    inner = fitz.Rect(pr.x0 + margin, pr.y0 + margin, pr.x1 - margin, pr.y1 - margin)
    iw, ih = max(40.0, inner.width), max(40.0, inner.height)

    if layout_mode == "cascade":
        rects: List[fitz.Rect] = []
        frac = 0.85 if n == 1 else 0.55
        max_w, max_h = iw * frac, ih * frac
        for idx, asp in enumerate(aspects):
            a = max(0.1, float(asp))
            w = max_w
            h = w * a
            if h > max_h:
                h = max_h
                w = h / a
            ox = inner.x0 + (idx % 6) * 20.0
            oy = inner.y0 + (idx % 6) * 20.0
            r = fitz.Rect(ox, oy, ox + w, oy + h)
            # Đẩy nhẹ vào trong nếu tràn mép
            dx = max(0.0, pr.x0 - r.x0) - max(0.0, r.x1 - pr.x1)
            dy = max(0.0, pr.y0 - r.y0) - max(0.0, r.y1 - pr.y1)
            rects.append(r + (dx, dy, dx, dy))
        return rects

    if layout_mode == "grid_2":
        cols = 2 if iw >= ih else 1
        rows = 1 if cols == 2 else 2
    elif layout_mode == "grid_4":
        cols, rows = 2, 2
    elif layout_mode == "grid_6":
        cols, rows = (3, 2) if iw >= ih else (2, 3)
    else:
        if n == 1:
            cols, rows = 1, 1
        elif n == 2:
            cols, rows = (2, 1) if iw >= ih else (1, 2)
        elif n <= 4:
            cols, rows = 2, 2
        elif n <= 6:
            cols, rows = (3, 2) if iw >= ih else (2, 3)
        elif n <= 9:
            cols, rows = 3, 3
        else:
            cols = max(2, int(round(n ** 0.5)))
            rows = max(1, (n + cols - 1) // cols)

    per_page = max(1, cols * rows)
    cell_w = max(20.0, (iw - gap * max(0, cols - 1)) / cols)
    cell_h = max(20.0, (ih - gap * max(0, rows - 1)) / rows)
    out: List[fitz.Rect] = []
    for idx, asp in enumerate(aspects):
        slot = idx % per_page
        layer = idx // per_page
        row, col = divmod(slot, cols)
        cx = inner.x0 + col * (cell_w + gap) + cell_w / 2.0 + layer * 10.0
        cy = inner.y0 + row * (cell_h + gap) + cell_h / 2.0 + layer * 10.0
        a = max(0.1, float(asp))
        w = cell_w
        h = w * a
        if h > cell_h:
            h = cell_h
            w = h / a
        r = fitz.Rect(cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)
        dx = max(0.0, pr.x0 - r.x0) - max(0.0, r.x1 - pr.x1)
        dy = max(0.0, pr.y0 - r.y0) - max(0.0, r.y1 - pr.y1)
        out.append(r + (dx, dy, dx, dy))
    return out


# ─── Đổi kích thước chú thích / đối tượng đã chọn bằng 8 tay nắm ───────────


def is_resizable_annotation(info: Optional[an.AnnotationInfo]) -> bool:
    if info is None or not info.movable:
        return False
    if info.app_kind in RESIZABLE_APP_KINDS:
        return True
    return info.subtype in ("Square", "Circle", "Redact")


def resize_annotation_in_page(
    page: fitz.Page,
    xref: int,
    new_unrot_rect: fitz.Rect,
    *,
    image_bytes: Optional[bytes] = None,
    pdf_bytes: Optional[bytes] = None,
    sig_library: Optional[object] = None,
) -> fitz.Rect:
    """Đổi kích thước chú thích / ảnh / trang PDF nhúng / hộp chữ / khung về `new_unrot_rect` (toạ độ trang chưa xoay)."""
    doc = page.parent
    annot = page.load_annot(xref)
    data = an.qt_data(doc, xref)
    kind = data.get("kind")
    subtype = annot.type[1]

    disp = an._fit_in_page(page, an._display_rect(page, fitz.Rect(new_unrot_rect).normalize()))
    if disp.width < 12.0 or disp.height < 12.0:
        disp = an._fit_in_page(
            page,
            fitz.Rect(disp.x0, disp.y0, disp.x0 + max(12.0, disp.width), disp.y0 + max(12.0, disp.height)),
        )
    unrot = (disp * page.derotation_matrix).normalize()

    if kind == "pdfpage":
        rebuild_pdf_page_annotation(page, xref, pdf_bytes, new_unrot_rect=unrot)
        return unrot

    if kind == "image":
        raw = image_bytes or render_annot_png(page, xref, scale=3.0)
        rot = int(data.get("rotation", 0))
        flip_h = bool(data.get("flip_h", False))
        flip_v = bool(data.get("flip_v", False))
        style_dict = data.get("style") or {}
        style = an.AnnotStyle(
            color=str(style_dict.get("color") or "#3B82F6"),
            opacity=float(style_dict.get("opacity", 1.0)),
        )
        tmp, _, _ = build_image_appearance(
            raw, disp.width, disp.height, rotation=rot, flip_h=flip_h, flip_v=flip_v
        )
        an._custom_annot_finish(page, annot, tmp, unrot, style, dict(data), "Hình ảnh", None)
        return unrot

    if kind == "textbox":
        style_dict = data.get("style") or {}
        style = an.AnnotStyle(**{k: v for k, v in style_dict.items() if k in an.AnnotStyle.__dataclass_fields__})
        text = str(data.get("text") or (annot.info or {}).get("content") or "")
        tmp, w, h = an.build_text_box_appearance(text, disp.width, style, min_height=disp.height)
        final_disp = an._fit_in_page(page, fitz.Rect(disp.x0, disp.y0, disp.x0 + w, disp.y0 + h))
        final_unrot = (final_disp * page.derotation_matrix).normalize()
        new_data = dict(data)
        new_data["width"] = w
        an._custom_annot_finish(page, annot, tmp, final_unrot, style, new_data, text, None)
        return final_unrot

    if kind == "stamp":
        old_disp = an._display_rect(page, annot.rect)
        style_dict = data.get("style") or {}
        style = an.AnnotStyle(**{k: v for k, v in style_dict.items() if k in an.AnnotStyle.__dataclass_fields__})
        ratio = (disp.width / max(8.0, old_disp.width) + disp.height / max(8.0, old_disp.height)) / 2.0
        style.font_size = max(6.0, min(144.0, float(style.font_size or 18.0) * ratio))
        label = str(data.get("label") or "ĐÃ DUYỆT")
        date_text = str(data.get("date") or "") or None
        tmp, sw, sh = an.build_stamp_appearance(label, style, date_text)
        final_disp = an._fit_in_page(page, fitz.Rect(disp.x0, disp.y0, disp.x0 + sw, disp.y0 + sh))
        final_unrot = (final_disp * page.derotation_matrix).normalize()
        new_data = dict(data)
        new_data["style"] = asdict(style)
        content = label + (f" — {date_text}" if date_text else "")
        an._custom_annot_finish(page, annot, tmp, final_unrot, style, new_data, content, None)
        return final_unrot

    if kind == "signature":
        style_dict = data.get("style") or {}
        style = an.AnnotStyle(**{k: v for k, v in style_dict.items() if k in an.AnnotStyle.__dataclass_fields__})
        sig = None
        if sig_library is not None and data.get("id"):
            try:
                sig = sig_library.get(data["id"])
            except Exception:
                sig = None
        if sig is not None:
            tmp, _, _ = fs.build_signature_appearance(sig, disp.width, disp.height)
            content = sig.label
        else:
            raw = render_annot_png(page, xref, scale=3.0)
            tmp, _, _ = build_image_appearance(raw, disp.width, disp.height)
            content = str((annot.info or {}).get("content") or "Chữ ký")
        an._custom_annot_finish(page, annot, tmp, unrot, style, dict(data), content, None)
        return unrot

    if kind == "fillmark":
        mark = str(data.get("mark") or "check")
        style_dict = data.get("style") or {}
        style = an.AnnotStyle(**{k: v for k, v in style_dict.items() if k in an.AnnotStyle.__dataclass_fields__})
        size = max(5.0, disp.width / 1.6 if mark == "line" else min(disp.width, disp.height))
        tmp, mw, mh = fs.build_mark_appearance(mark, size, style.color)
        final_disp = an._fit_in_page(page, fitz.Rect(disp.x0, disp.y0, disp.x0 + mw, disp.y0 + mh))
        final_unrot = (final_disp * page.derotation_matrix).normalize()
        new_data = dict(data)
        new_data["size"] = size
        symbol, name = fs.MARKS.get(mark, ("✓", "Dấu tích"))
        an._custom_annot_finish(page, annot, tmp, final_unrot, style, new_data, f"{symbol} {name}", None)
        return final_unrot

    if subtype in ("Square", "Circle", "Redact"):
        annot.set_rect(unrot)
        annot.update()
        doc.xref_set_key(xref, "M", fitz.get_pdf_str(an._pdf_now()))
        return unrot

    raise PageEditError("Đối tượng này chưa hỗ trợ kéo đổi kích thước.")
