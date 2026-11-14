"""Các thao tác chỉnh sửa trực tiếp trang và nội dung trên `fitz.Document` đang mở.

Không phụ thuộc `PySide6` — dùng chung cho thanh công cụ «Chỉnh sửa», `EditSession` (Hoàn tác / Làm lại)
và kiểm thử tự động `pytest`.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF

from qtpdfpro.core import annotations as an
from qtpdfpro.core.page_ops import parse_page_selection
from qtpdfpro.core.page_stamp import MM, _TextStamps

APP_IMAGE_NAME = "QTPdfProImage"
_NUM_RE = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


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
