"""Phiên chỉnh sửa chú thích trên một tài liệu đang mở: thêm / xoá / di chuyển / sửa nội dung kèm Hoàn tác – Làm lại.

Không dùng journal của MuPDF: khi bật journal, PyMuPDF 1.28 chặn các hàm cần để dựng hình hiển thị hộp chữ /
dấu đóng (`ENSURE_OPERATION` báo lỗi «Can't undo/redo during an operation»). Thay vào đó mỗi thao tác ghi lại
cách làm ngược:
- Thêm chú thích → hoàn tác bằng **ẩn** (xoá mềm, cờ `/F Hidden` + khoá `QTPdfProDeleted`), làm lại bằng hiện lại.
- Xoá → ẩn; hoàn tác → hiện lại. Chú thích bị ẩn được xoá hẳn khi lưu (`prepare_save`).
- Di chuyển → dịch các khoá hình học; hoàn tác → dịch ngược.
- Sửa nội dung → lưu giá trị cũ của các khoá (`Contents`, `AP`, `Rect`, …) để khôi phục.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF

from qtpdfpro.core import annotations as an
from qtpdfpro.core import fill_sign as fs
from qtpdfpro.core import page_edit as pe

_ids = count(1)


@dataclass
class EditAction:
    label: str
    page_index: int
    undo: Callable[[], None]
    redo: Callable[[], None]
    action_id: int = 0


def _snapshot(doc: fitz.Document, xref: int, keys: Sequence[str]) -> Dict[str, str]:
    snap = {}
    for key in keys:
        kind, value = doc.xref_get_key(xref, key)
        if kind == "null":
            snap[key] = "null"
        elif kind == "string":
            snap[key] = fitz.get_pdf_str(value)
        else:
            snap[key] = value
    return snap


def _restore(doc: fitz.Document, xref: int, snap: Dict[str, str]) -> None:
    for key, value in snap.items():
        doc.xref_set_key(xref, key, value)


class EditSession:
    """Quản lý chú thích & lịch sử hoàn tác của một `fitz.Document` đang mở."""

    MAX_HISTORY = 200

    def __init__(self, doc: fitz.Document, author: Optional[str] = None) -> None:
        self.doc = doc
        self.author = author if author is not None else an.default_author()
        self._undo: List[EditAction] = []
        self._redo: List[EditAction] = []
        self._saved_top: Optional[int] = None
        self._unsaved_purge = False  # đã xoá hẳn chú thích ẩn nhưng chưa ghi tệp xong
        self._full_save_ids: set[int] = set()
        self._prepared_full_save = False
        self._annot_images: Dict[int, bytes] = {}
        self._annot_pdfs: Dict[int, bytes] = {}
        self._words: Dict[int, List[tuple]] = {}
        self._leaders: Dict[int, List[fs.Leader]] = {}
        self._boxes: Dict[int, List[fitz.Rect]] = {}

    # ─── Trạng thái ───────────────────────────────────────────────────────

    @property
    def modified(self) -> bool:
        top = self._undo[-1].action_id if self._undo else None
        return self._unsaved_purge or top != self._saved_top

    @property
    def needs_full_save(self) -> bool:
        """True nếu phiên có thao tác xoay/lật/cắt/sửa luồng nội dung hoặc tổ chức trang."""
        return self._prepared_full_save or any(a.action_id in self._full_save_ids for a in self._undo)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""

    def rebind(self, doc: fitz.Document) -> None:
        """Gắn phiên vào tài liệu mới mở lại (sau khi lưu đè / lưu thành); lịch sử được làm mới."""
        self.doc = doc
        self._undo.clear()
        self._redo.clear()
        self._saved_top = None
        self._unsaved_purge = False
        self._full_save_ids.clear()
        self._prepared_full_save = False
        self._annot_images.clear()
        self._annot_pdfs.clear()
        self._words.clear()
        self._leaders.clear()
        self._boxes.clear()

    def prepare_save(self) -> int:
        """Xoá hẳn chú thích đã xoá mềm trước khi ghi tệp; trả về số chú thích đã xoá."""
        was_modified = self.modified
        was_full = self.needs_full_save
        removed = an.purge_deleted(self.doc)
        self._undo.clear()
        self._redo.clear()
        self._saved_top = None
        self._unsaved_purge = was_modified
        self._full_save_ids.clear()
        self._prepared_full_save = was_full
        return removed

    def mark_saved(self) -> None:
        self._saved_top = self._undo[-1].action_id if self._undo else None
        self._unsaved_purge = False
        self._prepared_full_save = False

    # ─── Tiện ích nội bộ ──────────────────────────────────────────────────

    def _invalidate_page_cache(self, page_index: Optional[int] = None) -> None:
        if page_index is None:
            self._words.clear()
            self._leaders.clear()
            self._boxes.clear()
        else:
            self._words.pop(page_index, None)
            self._leaders.pop(page_index, None)
            self._boxes.pop(page_index, None)

    def _push(
        self,
        label: str,
        page_index: int,
        undo: Callable[[], None],
        redo: Callable[[], None],
        *,
        full_save: bool = False,
    ) -> None:
        aid = next(_ids)
        self._undo.append(EditAction(label, page_index, undo, redo, aid))
        if full_save:
            self._full_save_ids.add(aid)
        if len(self._undo) > self.MAX_HISTORY:
            dropped = self._undo.pop(0)
            self._full_save_ids.discard(dropped.action_id)
        self._redo.clear()

    def _set_hidden(self, page_index: int, xref: int, hidden: bool) -> None:
        # MuPDF đọc lại /F, /Rect, /AP khi kết xuất nên không cần nạp lại trang sau khi sửa qua xref
        an.set_annotation_hidden(self.doc, xref, hidden)

    def _add(self, label: str, page_index: int, create: Callable[[fitz.Page], fitz.Annot]) -> int:
        page = self.doc[page_index]
        annot = create(page)
        xref = annot.xref
        self._push(
            label,
            page_index,
            undo=lambda: self._set_hidden(page_index, xref, True),
            redo=lambda: self._set_hidden(page_index, xref, False),
        )
        return xref

    # ─── Chọn chữ ─────────────────────────────────────────────────────────

    def words(self, page_index: int) -> List[tuple]:
        if page_index not in self._words:
            self._words[page_index] = an.page_words(self.doc[page_index])
        return self._words[page_index]

    def page_has_text(self, page_index: int) -> bool:
        return bool(self.words(page_index))

    def select_text(self, page_index: int, p0, p1, area: bool = False) -> List[fitz.Rect]:
        words = self.words(page_index)
        if area:
            return an.words_in_rect(words, fitz.Rect(fitz.Point(p0), fitz.Point(p1)))
        return an.select_text_rects(words, p0, p1)

    # ─── Thêm chú thích ───────────────────────────────────────────────────

    def add_markup(self, page_index: int, kind: str, rects: Sequence[fitz.Rect], style: an.AnnotStyle) -> int:
        label = {"highlight": "Tô sáng", "underline": "Gạch chân", "strikeout": "Gạch ngang",
                 "squiggly": "Gạch sóng"}.get(kind, "Đánh dấu chữ")
        return self._add(label, page_index, lambda p: an.add_text_markup(p, kind, rects, style, self.author))

    def add_ink(self, page_index: int, strokes, style: an.AnnotStyle, marker: bool = False) -> int:
        label = "Bút dạ quang" if marker else "Vẽ tay"
        return self._add(label, page_index, lambda p: an.add_ink(p, strokes, style, self.author, marker=marker))

    def add_shape(self, page_index: int, kind: str, p0, p1, style: an.AnnotStyle) -> int:
        label = {"rect": "Khung chữ nhật", "ellipse": "Hình elip", "line": "Đường thẳng",
                 "arrow": "Mũi tên"}.get(kind, "Hình")
        return self._add(label, page_index, lambda p: an.add_shape(p, kind, p0, p1, style, self.author))

    def add_note(self, page_index: int, point, text: str, style: an.AnnotStyle) -> int:
        return self._add("Ghi chú", page_index, lambda p: an.add_note(p, point, text, style, self.author))

    def add_text_box(self, page_index: int, rect: fitz.Rect, text: str, style: an.AnnotStyle) -> int:
        return self._add("Hộp chữ", page_index, lambda p: an.add_text_box(p, rect, text, style, self.author))

    def add_stamp(self, page_index: int, center, label: str, style: an.AnnotStyle,
                  date_text: Optional[str] = None) -> int:
        return self._add(
            f"Dấu «{label}»", page_index, lambda p: an.add_stamp(p, center, label, style, self.author, date_text)
        )

    # ─── Điền & Ký (core/fill_sign.py) ────────────────────────────────────

    def leaders(self, page_index: int, font_size: float = 12.0) -> List[fs.Leader]:
        """Dòng chấm / gạch dưới / đường kẻ để điền trên trang (đệm theo trang — nội dung trang không đổi khi
        thêm chú thích)."""
        if page_index not in self._leaders:
            self._leaders[page_index] = fs.find_leaders(self.doc[page_index], font_size)
        return self._leaders[page_index]

    def boxes(self, page_index: int) -> List[fitz.Rect]:
        if page_index not in self._boxes:
            self._boxes[page_index] = fs.find_boxes(self.doc[page_index])
        return self._boxes[page_index]

    def fill_target(self, page_index: int, point, style: an.AnnotStyle, snap: bool = True) -> fs.FillTarget:
        page = self.doc[page_index]
        return fs.snap_text_target(page, point, style.font_size, self.leaders(page_index, style.font_size), snap)

    def add_fill_text(self, page_index: int, point, text: str, style: an.AnnotStyle, snap: bool = True,
                      kind: str = "text") -> int:
        label = "Ghi ngày" if kind == "date" else "Gõ chữ"
        leaders = self.leaders(page_index, style.font_size)
        return self._add(label, page_index, lambda p: fs.add_fill_text(
            p, point, text, style, self.author, snap, leaders, kind=kind))

    def add_fill_mark(self, page_index: int, point, mark: str, style: an.AnnotStyle, snap: bool = True) -> int:
        boxes = self.boxes(page_index)
        return self._add(fs.MARKS.get(mark, ("", "Dấu"))[1], page_index,
                         lambda p: fs.add_mark(p, point, mark, style, self.author, snap, boxes))

    def add_signature(self, page_index: int, sig: fs.Signature, center=None, rect=None) -> int:
        label = "Ký nháy" if sig.initials else "Ký"
        return self._add(label, page_index, lambda p: fs.add_signature(p, sig, center, rect, self.author))

    # ─── Sửa chú thích ────────────────────────────────────────────────────

    def annotation_at(self, page_index: int, point, tolerance: float = 4.0) -> Optional[int]:
        return an.annotation_at(self.doc[page_index], point, tolerance)

    def info(self, page_index: int, xref: int) -> Optional[an.AnnotationInfo]:
        page = self.doc[page_index]
        for annot in page.annots():
            if annot.xref == xref:
                return an.annotation_info(page, annot)
        return None

    def annotation_rect(self, page_index: int, xref: int) -> Optional[fitz.Rect]:
        page = self.doc[page_index]
        for annot in page.annots():
            if annot.xref == xref:
                return fitz.Rect(annot.rect)
        return None

    def list_annotations(self) -> List[an.AnnotationInfo]:
        return an.list_annotations(self.doc)

    def delete(self, page_index: int, xref: int) -> bool:
        info = self.info(page_index, xref)
        if info is None:
            return False
        self._set_hidden(page_index, xref, True)
        self._push(
            f"Xoá {info.label.lower()}",
            page_index,
            undo=lambda: self._set_hidden(page_index, xref, False),
            redo=lambda: self._set_hidden(page_index, xref, True),
        )
        return True

    def move(self, page_index: int, xref: int, dx: float, dy: float) -> bool:
        info = self.info(page_index, xref)
        if info is None or not info.movable or (abs(dx) < 0.01 and abs(dy) < 0.01):
            return False

        def shift(sx: float, sy: float) -> None:
            an.translate_annotation(self.doc[page_index], xref, sx, sy)

        shift(dx, dy)
        self._push(f"Di chuyển {info.label.lower()}", page_index,
                   undo=lambda: shift(-dx, -dy), redo=lambda: shift(dx, dy))
        return True

    def set_content(self, page_index: int, xref: int, text: str) -> bool:
        """Sửa nội dung ghi chú / chú thích; hộp chữ của QT PDF Pro được dựng lại hình hiển thị."""
        info = self.info(page_index, xref)
        if info is None:
            return False
        keys = ("Contents", "M", "AP", "Rect", an.QT_KEY)
        before = _snapshot(self.doc, xref, keys)
        page = self.doc[page_index]
        if info.app_kind == "textbox":
            an.rebuild_text_box(page, xref, text)
        elif info.app_kind == "filltext":
            fs.rebuild_fill_text(page, xref, text)
        else:
            self.doc.xref_set_key(xref, "Contents", fitz.get_pdf_str(an._nfc(text)))
        self.doc.xref_set_key(xref, "M", fitz.get_pdf_str(fitz.get_pdf_now()))
        after = _snapshot(self.doc, xref, keys)

        def apply(snap: Dict[str, str]) -> None:
            _restore(self.doc, xref, snap)

        self._push("Sửa nội dung chú thích", page_index, undo=lambda: apply(before), redo=lambda: apply(after))
        return True

    # ─── Xoay / lật / cắt trang & thêm ảnh / liên kết / che thông tin ────

    def rotate_page(self, page_index: int, delta: int) -> int:
        """Xoay trang trong tài liệu (thay đổi `/Rotate` của trang, Hoàn tác & Lưu được)."""
        page = self.doc[page_index]
        old_rot = page.rotation % 360
        new_rot = (old_rot + int(delta)) % 360
        if new_rot == old_rot:
            return old_rot

        def apply(rot: int) -> None:
            self.doc[page_index].set_rotation(rot)
            self._invalidate_page_cache(page_index)

        apply(new_rot)
        label = "Xoay trang trái 90°" if delta % 360 == 270 else "Xoay trang phải 90°"
        self._push(label, page_index, undo=lambda: apply(old_rot), redo=lambda: apply(new_rot), full_save=True)
        return new_rot

    def flip_page(self, page_index: int, horizontal: bool = True, extra_rot: int = 0) -> None:
        """Lật trang ngang (`horizontal=True`) hoặc dọc (`False`), hỗ trợ Hoàn tác / Làm lại."""
        geom_keys = ("Rect", "QuadPoints", "InkList", "L", "Vertices", "CL", "M")

        def snap_page() -> Tuple[Tuple[str, str], List[Tuple[int, bytes]], List[Tuple[int, Dict[str, str]]]]:
            p = self.doc[page_index]
            ckey = self.doc.xref_get_key(p.xref, "Contents")
            streams = [(x, bytes(self.doc.xref_stream(x) or b"")) for x in p.get_contents()]
            annots = [(a.xref, _snapshot(self.doc, a.xref, geom_keys)) for a in (p.annots() or ())]
            return ckey, streams, annots

        def restore_page(state: Tuple[Tuple[str, str], List[Tuple[int, bytes]], List[Tuple[int, Dict[str, str]]]]) -> None:
            ckey, streams, annots = state
            p = self.doc[page_index]
            self.doc.xref_set_key(p.xref, "Contents", "null" if ckey[0] == "null" else ckey[1])
            for xref, raw in streams:
                self.doc.update_stream(xref, raw)
            for axref, snap in annots:
                _restore(self.doc, axref, snap)
            self._invalidate_page_cache(page_index)

        before = snap_page()
        pe.flip_page_contents(self.doc, page_index, horizontal=horizontal, extra_rot=extra_rot)
        after = snap_page()
        self._invalidate_page_cache(page_index)
        label = "Lật trang ngang" if horizontal else "Lật trang dọc"
        self._push(
            label,
            page_index,
            undo=lambda: restore_page(before),
            redo=lambda: restore_page(after),
            full_save=True,
        )

    def crop_page(self, page_index: int, rect: fitz.Rect, *, view_coords: bool = True) -> fitz.Rect:
        """Cắt vùng hiển thị (`CropBox`) của trang, trả về CropBox mới."""
        old_crop = pe.crop_page_rect(self.doc, page_index, rect, view_coords=view_coords)
        new_crop = fitz.Rect(self.doc[page_index].cropbox)
        self._invalidate_page_cache(page_index)

        def apply(box: fitz.Rect) -> None:
            self.doc[page_index].set_cropbox(box)
            self._invalidate_page_cache(page_index)

        self._push(
            "Cắt lề trang",
            page_index,
            undo=lambda: apply(old_crop),
            redo=lambda: apply(new_crop),
            full_save=True,
        )
        return new_crop

    def crop_margins(
        self,
        page_index: int,
        *,
        top_pt: float = 0.0,
        bottom_pt: float = 0.0,
        left_pt: float = 0.0,
        right_pt: float = 0.0,
        reset: bool = False,
    ) -> fitz.Rect:
        """Cắt lề trang theo 4 cạnh hoặc khôi phục khổ gốc."""
        old_crop = pe.crop_page_margins(
            self.doc, page_index, top_pt=top_pt, bottom_pt=bottom_pt, left_pt=left_pt, right_pt=right_pt, reset=reset
        )
        new_crop = fitz.Rect(self.doc[page_index].cropbox)
        self._invalidate_page_cache(page_index)

        def apply(box: fitz.Rect) -> None:
            self.doc[page_index].set_cropbox(box)
            self._invalidate_page_cache(page_index)

        self._push(
            "Khôi phục khổ trang" if reset else "Cắt lề trang",
            page_index,
            undo=lambda: apply(old_crop),
            redo=lambda: apply(new_crop),
            full_save=True,
        )
        return new_crop

    def add_image(
        self,
        page_index: int,
        rect: fitz.Rect,
        image_bytes: bytes,
        *,
        rotation: int = 0,
        flip_h: bool = False,
        flip_v: bool = False,
        opacity: float = 1.0,
    ) -> int:
        """Chèn hình ảnh lên trang (di chuyển, xoay 90°, lật ngang/dọc, xoá và Hoàn tác được)."""
        xref = self._add(
            "Chèn ảnh",
            page_index,
            lambda p: pe.add_image_annotation(
                p, rect, image_bytes, rotation=rotation, flip_h=flip_h, flip_v=flip_v, opacity=opacity,
                author=self.author,
            ),
        )
        self._annot_images[xref] = image_bytes
        return xref

    def add_pdf_page_overlay(
        self,
        page_index: int,
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
    ) -> int:
        """Nhúng một trang PDF khác lên trang hiện tại như đối tượng kéo thả, đổi cỡ sắc nét."""
        xref = self._add(
            "Chèn trang PDF",
            page_index,
            lambda p: pe.add_pdf_page_annotation(
                p,
                rect,
                page_pdf_bytes,
                source_name=source_name,
                source_page_1based=source_page_1based,
                rotation=rotation,
                flip_h=flip_h,
                flip_v=flip_v,
                opacity=opacity,
                border_color=border_color,
                border_width=border_width,
                author=self.author,
            ),
        )
        self._annot_pdfs[xref] = page_pdf_bytes
        return xref

    def embed_pdf_pages(
        self,
        page_index: int,
        src_doc: fitz.Document,
        page_indices: Sequence[int],
        *,
        source_name: str = "",
        layout_mode: str = "auto_grid",
        margin_mm: float = 12.0,
        gap_mm: float = 5.0,
        border_color: Optional[str] = "#CBD5E1",
        border_width: float = 0.6,
    ) -> List[int]:
        """Import nhiều trang từ `src_doc` lên cùng một trang `page_index` (1 bước Hoàn tác chung)."""
        indices = [int(i) for i in page_indices if 0 <= int(i) < src_doc.page_count]
        if not indices:
            raise pe.PageEditError("Không có trang hợp lệ nào được chọn từ tệp PDF nguồn.")
        target_page = self.doc[page_index]
        extracted = [(pno, *pe.extract_single_page_pdf_bytes(src_doc, pno)) for pno in indices]
        aspects = [h / max(1.0, w) for _pno, _raw, w, h in extracted]
        disp_rects = pe.layout_embedded_pages_rects(
            target_page.rect,
            aspects,
            layout_mode=layout_mode,
            margin_pt=float(margin_mm) * pe.MM,
            gap_pt=float(gap_mm) * pe.MM,
        )
        derot = target_page.derotation_matrix
        xrefs: List[int] = []
        for (pno, raw_pdf, _w, _h), disp_rect in zip(extracted, disp_rects):
            unrot = (disp_rect * derot).normalize()
            annot = pe.add_pdf_page_annotation(
                target_page,
                unrot,
                raw_pdf,
                source_name=source_name,
                source_page_1based=pno + 1,
                border_color=border_color,
                border_width=border_width,
                author=self.author,
            )
            xrefs.append(annot.xref)
            self._annot_pdfs[annot.xref] = raw_pdf

        def _hide_all(hidden: bool) -> None:
            for x in xrefs:
                self._set_hidden(page_index, x, hidden)

        label = f"Chèn {len(xrefs)} trang PDF" if len(xrefs) > 1 else "Chèn trang PDF"
        self._push(label, page_index, undo=lambda: _hide_all(True), redo=lambda: _hide_all(False))
        return xrefs

    def transform_image_annot(
        self,
        page_index: int,
        xref: int,
        *,
        rotate_delta: int = 0,
        toggle_flip_h: bool = False,
        toggle_flip_v: bool = False,
    ) -> bool:
        """Xoay 90° hoặc lật ngang/dọc một hình ảnh hoặc trang PDF nhúng đã chèn trên trang."""
        info = self.info(page_index, xref)
        if info is None or info.app_kind not in ("image", "pdfpage"):
            return False
        page = self.doc[page_index]
        keys = ("AP", "Rect", "M", an.QT_KEY)
        before = _snapshot(self.doc, xref, keys)
        if info.app_kind == "pdfpage":
            pe.rebuild_pdf_page_annotation(
                page,
                xref,
                self._annot_pdfs.get(xref),
                rotate_delta=rotate_delta,
                toggle_flip_h=toggle_flip_h,
                toggle_flip_v=toggle_flip_v,
            )
        else:
            raw = self._annot_images.get(xref)
            if not raw:
                raw = pe.render_annot_png(page, xref, scale=3.0)
                self._annot_images[xref] = raw
            pe.rebuild_image_annotation(
                page,
                xref,
                raw,
                rotate_delta=rotate_delta,
                toggle_flip_h=toggle_flip_h,
                toggle_flip_v=toggle_flip_v,
            )
        after = _snapshot(self.doc, xref, keys)

        def apply(snap: Dict[str, str]) -> None:
            _restore(self.doc, xref, snap)

        kind_txt = "trang PDF" if info.app_kind == "pdfpage" else "ảnh"
        label = (
            f"Lật {kind_txt} ngang" if toggle_flip_h
            else f"Lật {kind_txt} dọc" if toggle_flip_v
            else f"Xoay {kind_txt}"
        )
        self._push(label, page_index, undo=lambda: apply(before), redo=lambda: apply(after))
        return True

    def resize(
        self,
        page_index: int,
        xref: int,
        new_rect: fitz.Rect,
        sig_library: Optional[fs.SignatureLibrary] = None,
    ) -> bool:
        """Đổi kích thước chú thích / ảnh / trang PDF nhúng / hộp chữ sang `new_rect` (Hoàn tác được)."""
        info = self.info(page_index, xref)
        if not pe.is_resizable_annotation(info):
            return False
        assert info is not None
        page = self.doc[page_index]
        if info.app_kind == "image" and xref not in self._annot_images:
            self._annot_images[xref] = pe.render_annot_png(page, xref, scale=3.0)
        keys = ("Rect", "AP", "M", "Border", an.QT_KEY)
        before = _snapshot(self.doc, xref, keys)
        pe.resize_annotation_in_page(
            page,
            xref,
            new_rect,
            image_bytes=self._annot_images.get(xref),
            pdf_bytes=self._annot_pdfs.get(xref),
            sig_library=sig_library,
        )
        after = _snapshot(self.doc, xref, keys)

        def apply(snap: Dict[str, str]) -> None:
            _restore(self.doc, xref, snap)

        self._push(
            f"Đổi cỡ {info.label.lower()}",
            page_index,
            undo=lambda: apply(before),
            redo=lambda: apply(after),
        )
        return True

    def add_link(
        self,
        page_index: int,
        rect: fitz.Rect,
        *,
        uri: str = "",
        target_page: Optional[int] = None,
    ) -> None:
        """Chèn liên kết URL hoặc nhảy tới trang đích lên trang `page_index`."""
        page = self.doc[page_index]
        before_links = [dict(lk) for lk in (page.get_links() or ())]
        pe.add_link_on_page(page, rect, uri=uri, target_page=target_page)
        page = self.doc.reload_page(page)
        after_links = [dict(lk) for lk in (page.get_links() or ())]

        def apply_links(links: List[dict]) -> None:
            pg = self.doc.reload_page(self.doc[page_index])
            for existing in list(pg.get_links() or ()):
                pg.delete_link(existing)
            for lk in links:
                pg.insert_link(dict(lk))
            self.doc.reload_page(pg)

        self._push(
            "Thêm liên kết",
            page_index,
            undo=lambda: apply_links(before_links),
            redo=lambda: apply_links(after_links),
            full_save=True,
        )

    def add_redaction(
        self,
        page_index: int,
        rect: fitz.Rect,
        *,
        text: str = "",
        fill: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> int:
        """Đánh dấu vùng che thông tin nhạy cảm trên trang."""
        return self._add(
            "Đánh dấu che thông tin",
            page_index,
            lambda p: pe.add_redaction_on_page(p, rect, text=text, fill=fill),
        )

    def run_doc_operation(
        self,
        label: str,
        page_index: int,
        mutate_fn: Callable[[fitz.Document], None],
    ) -> None:
        """Chạy thao tác biến đổi cấp tài liệu (chèn/xoá trang, đóng dấu nước, đầu/chân trang, Bates, áp dụng che…)
        kèm chụp bản sao trước/sau để Hoàn tác và Làm lại toàn vẹn."""
        an.purge_deleted(self.doc)
        before_bytes = self.doc.tobytes(deflate=False)
        before_meta = dict(self.doc.metadata or {})
        before_toc = list(self.doc.get_toc(simple=False) or ())

        mutate_fn(self.doc)

        after_bytes = self.doc.tobytes(deflate=False)
        after_meta = dict(self.doc.metadata or {})
        after_toc = list(self.doc.get_toc(simple=False) or ())
        self._invalidate_page_cache(None)

        def restore_snapshot(data: bytes, meta: dict, toc: list) -> None:
            old_n = self.doc.page_count
            src = fitz.open("pdf", data)
            try:
                self.doc.insert_pdf(src)
            finally:
                src.close()
            if old_n > 0:
                self.doc.delete_pages(list(range(old_n)))
            self.doc.set_metadata(meta)
            try:
                self.doc.set_toc(toc)
            except Exception:
                pass
            self._invalidate_page_cache(None)

        self._push(
            label,
            max(0, min(page_index, max(0, self.doc.page_count - 1))),
            undo=lambda: restore_snapshot(before_bytes, before_meta, before_toc),
            redo=lambda: restore_snapshot(after_bytes, after_meta, after_toc),
            full_save=True,
        )

    # ─── Hoàn tác / Làm lại ───────────────────────────────────────────────

    def undo(self) -> Optional[Tuple[str, int]]:
        """Hoàn tác thao tác gần nhất; trả về (tên thao tác, trang) hoặc None."""
        if not self._undo:
            return None
        action = self._undo.pop()
        action.undo()
        self._redo.append(action)
        return action.label, action.page_index

    def redo(self) -> Optional[Tuple[str, int]]:
        if not self._redo:
            return None
        action = self._redo.pop()
        action.redo()
        self._undo.append(action)
        return action.label, action.page_index
