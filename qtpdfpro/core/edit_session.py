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
        self._words: Dict[int, List[tuple]] = {}

    # ─── Trạng thái ───────────────────────────────────────────────────────

    @property
    def modified(self) -> bool:
        top = self._undo[-1].action_id if self._undo else None
        return self._unsaved_purge or top != self._saved_top

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
        self._words.clear()

    def prepare_save(self) -> int:
        """Xoá hẳn chú thích đã xoá mềm trước khi ghi tệp; trả về số chú thích đã xoá."""
        was_modified = self.modified
        removed = an.purge_deleted(self.doc)
        self._undo.clear()
        self._redo.clear()
        self._saved_top = None
        self._unsaved_purge = was_modified
        return removed

    def mark_saved(self) -> None:
        self._saved_top = self._undo[-1].action_id if self._undo else None
        self._unsaved_purge = False

    # ─── Tiện ích nội bộ ──────────────────────────────────────────────────

    def _push(self, label: str, page_index: int, undo: Callable[[], None], redo: Callable[[], None]) -> None:
        self._undo.append(EditAction(label, page_index, undo, redo, next(_ids)))
        if len(self._undo) > self.MAX_HISTORY:
            del self._undo[0]
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
        else:
            self.doc.xref_set_key(xref, "Contents", fitz.get_pdf_str(an._nfc(text)))
        self.doc.xref_set_key(xref, "M", fitz.get_pdf_str(fitz.get_pdf_now()))
        after = _snapshot(self.doc, xref, keys)

        def apply(snap: Dict[str, str]) -> None:
            _restore(self.doc, xref, snap)

        self._push("Sửa nội dung chú thích", page_index, undo=lambda: apply(before), redo=lambda: apply(after))
        return True

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
