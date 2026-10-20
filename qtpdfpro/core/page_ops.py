"""Tổ chức trang PDF: sắp xếp, xoay, xoá, nhân bản, chèn trang trắng, ghép nhiều tệp, tách và trích trang.

Không phụ thuộc `PySide6` — dùng chung cho hộp thoại «Sắp xếp & cắt ghép trang», dòng lệnh và `pytest`.

Mô hình dữ liệu: một tài liệu đích là danh sách `PageRef` (tham chiếu tới trang `page_index` của tài liệu
nguồn `source`, kèm góc xoay thêm; `page_index=None` là trang trắng). `assemble_pdf` dựng tài liệu mới từ
danh sách đó, giữ chú thích, liên kết và mục lục (bookmark) của các trang còn lại.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import fitz  # PyMuPDF

A4_SIZE = (595.28, 841.89)
_ROTATIONS = (0, 90, 180, 270)
_BLANK_WORDS = ("blank", "trang", "trangtrang", "trang_trang", "b")
_ODD_WORDS = ("odd", "le")
_EVEN_WORDS = ("even", "chan")
_TOKEN_RE = re.compile(
    r"^(?P<a>\d+|end|n)(?:-(?P<b>\d+|end|n))?(?:r(?P<rot>-?\d+))?$",
    re.IGNORECASE,
)
_WORD_TOKEN_RE = re.compile(r"^(?P<w>[a-z_]+)(?:r(?P<rot>-?\d+))?$", re.IGNORECASE)
_INPUT_SPEC_RE = re.compile(r"^(?P<path>.+\.pdf):(?P<spec>[0-9a-z,;\-\s]+)$", re.IGNORECASE)


class PageOpsError(ValueError):
    """Lỗi cú pháp phạm vi trang hoặc thao tác trang không hợp lệ (thông báo tiếng Việt)."""


@dataclass(frozen=True)
class PageRef:
    """Một trang của tài liệu đích."""

    source: str = ""  # khoá tài liệu nguồn (thường là đường dẫn tệp); "" với trang trắng
    page_index: Optional[int] = None  # 0-based; None = trang trắng
    rotation: int = 0  # góc xoay thêm (bội số 90), cộng vào /Rotate gốc của trang
    width: float = 0.0  # cỡ trang trắng (pt); 0 = lấy theo trang liền trước (hoặc A4)
    height: float = 0.0

    @property
    def is_blank(self) -> bool:
        return self.page_index is None

    def rotated(self, delta: int) -> "PageRef":
        return replace(self, rotation=normalize_rotation(self.rotation + delta))


@dataclass
class OrganizeResult:
    """Kết quả ghi một (hoặc nhiều) tệp PDF sau khi tổ chức trang."""

    output_paths: List[str]
    page_counts: List[int]

    @property
    def total_pages(self) -> int:
        return sum(self.page_counts)

    def to_dict(self) -> dict:
        return {
            "outputs": [
                {"path": p, "pages": n} for p, n in zip(self.output_paths, self.page_counts)
            ],
            "total_pages": self.total_pages,
        }


def normalize_rotation(degrees: int) -> int:
    """Đưa góc về 0/90/180/270; báo lỗi nếu không phải bội số 90."""
    value = int(degrees)
    if value % 90:
        raise PageOpsError(f"Góc xoay phải là bội số của 90°: {degrees}")
    return value % 360


def blank_page(width: float = 0.0, height: float = 0.0) -> PageRef:
    return PageRef(source="", page_index=None, width=float(width), height=float(height))


def refs_for_document(source: str, page_count: int) -> List[PageRef]:
    """Danh sách tham chiếu toàn bộ trang của một tài liệu theo thứ tự gốc."""
    return [PageRef(source=source, page_index=i) for i in range(page_count)]


# ─── Cú pháp phạm vi trang ────────────────────────────────────────────────


def _page_number(token: str, total: int) -> int:
    t = token.lower()
    n = total if t in ("end", "n") else int(t)
    if not 1 <= n <= total:
        raise PageOpsError(f"Trang {n} nằm ngoài tài liệu (1..{total}).")
    return n


def _tokens(spec: str) -> List[str]:
    return [t.replace(" ", "") for t in re.split(r"[,;]", spec or "") if t.strip()]


def parse_order_spec(spec: str, total: int, source: str = "") -> List[PageRef]:
    """Phân tích chuỗi thứ tự trang thành danh sách `PageRef` (giữ đúng thứ tự, cho phép lặp/đảo).

    Cú pháp (phân tách bằng dấu phẩy, số trang tính từ 1):
    - `5` — trang 5; `1-3` — trang 1→3; `8-6` — trang 8, 7, 6 (đảo); `end` (hoặc `n`) — trang cuối.
    - `le` / `odd`, `chan` / `even` — mọi trang lẻ / chẵn.
    - Hậu tố xoay `r90`, `r180`, `r270`, `r-90` (vd `2r90`, `1-3r180`, `ler90`).
    - `blank` / `trang` — chèn một trang trắng (cỡ theo trang liền trước).
    """
    if total <= 0:
        raise PageOpsError("Tài liệu không có trang nào.")
    tokens = _tokens(spec)
    if not tokens:
        raise PageOpsError("Chưa nhập thứ tự trang.")
    refs: List[PageRef] = []
    for token in tokens:
        m = _TOKEN_RE.match(token)
        if m:
            rot = normalize_rotation(int(m.group("rot") or 0))
            a = _page_number(m.group("a"), total)
            b = _page_number(m.group("b"), total) if m.group("b") else a
            step = 1 if b >= a else -1
            refs.extend(PageRef(source, p - 1, rot) for p in range(a, b + step, step))
            continue
        w = _WORD_TOKEN_RE.match(token)
        word = w.group("w").lower() if w else ""
        rot = normalize_rotation(int(w.group("rot") or 0)) if w else 0
        if word in _BLANK_WORDS:
            refs.append(blank_page())
        elif word in _ODD_WORDS:
            refs.extend(PageRef(source, i, rot) for i in range(0, total, 2))
        elif word in _EVEN_WORDS:
            refs.extend(PageRef(source, i, rot) for i in range(1, total, 2))
        else:
            raise PageOpsError(f"Không hiểu phần thứ tự trang '{token}'.")
    return refs


def parse_page_selection(spec: str, total: int) -> List[int]:
    """Chuỗi chọn trang (`'1-3,5,end'`, `'le'`) → chỉ số 0-based, giữ thứ tự & bỏ trùng; bỏ trống = tất cả."""
    if not (spec or "").strip():
        return list(range(total))
    seen: Dict[int, None] = {}
    for ref in parse_order_spec(spec, total):
        if ref.page_index is not None:
            seen.setdefault(ref.page_index, None)
    return list(seen)


def parse_split_ranges(spec: str, total: int) -> List[List[int]]:
    """`'1-3,4-6,7'` → mỗi phần tử phân tách bằng dấu phẩy là một tệp con (chỉ số 0-based)."""
    parts = []
    for token in _tokens(spec):
        pages = [r.page_index for r in parse_order_spec(token, total) if r.page_index is not None]
        if pages:
            parts.append(pages)
    if not parts:
        raise PageOpsError("Chưa nhập khoảng trang cần tách.")
    return parts


def split_input_spec(arg: str) -> Tuple[str, Optional[str]]:
    """`'a.pdf:1-3'` → (`'a.pdf'`, `'1-3'`); không có hậu tố trang → (`arg`, None). Chịu ổ đĩa `C:\\`."""
    m = _INPUT_SPEC_RE.match(arg.strip())
    if m:
        return m.group("path"), m.group("spec")
    return arg, None


# ─── Chia danh sách trang thành nhiều phần ────────────────────────────────


def split_refs(
    refs: Sequence[PageRef],
    *,
    every: Optional[int] = None,
    after: Optional[Iterable[int]] = None,
) -> List[List[PageRef]]:
    """Chia danh sách trang: `every=N` (mỗi phần N trang) hoặc `after` (cắt sau các vị trí 1-based)."""
    items = list(refs)
    if not items:
        return []
    if every is not None:
        n = int(every)
        if n < 1:
            raise PageOpsError("Số trang mỗi phần phải ≥ 1.")
        return [items[i : i + n] for i in range(0, len(items), n)]
    cuts = sorted({int(c) for c in (after or []) if 0 < int(c) < len(items)})
    parts: List[List[PageRef]] = []
    start = 0
    for c in cuts:
        parts.append(items[start:c])
        start = c
    parts.append(items[start:])
    return [p for p in parts if p]


# ─── Dựng tài liệu ────────────────────────────────────────────────────────


def _runs(refs: Sequence[PageRef]) -> List[List[PageRef]]:
    """Gom các trang liên tiếp cùng nguồn (tăng dần, không trùng) để chép bằng 1 lệnh `insert_pdf`."""
    runs: List[List[PageRef]] = []
    for ref in refs:
        last = runs[-1][-1] if runs else None
        if (
            last is not None
            and not ref.is_blank
            and not last.is_blank
            and ref.source == last.source
            and ref.page_index == last.page_index + 1
        ):
            runs[-1].append(ref)
        else:
            runs.append([ref])
    return runs


def _normalized_toc(entries: List[list]) -> List[list]:
    """Sửa cấp mục lục sau khi lọc: bắt đầu từ cấp 1, mỗi mục không sâu hơn mục trước quá 1 cấp."""
    fixed: List[list] = []
    prev = 0
    for lvl, title, page in entries:
        lvl = max(1, min(int(lvl), prev + 1))
        fixed.append([lvl, title, page])
        prev = lvl
    return fixed


def _remap_toc(doc: fitz.Document, source: str, first_new: Dict[Tuple[str, int], int], shift: int) -> List[list]:
    out = []
    for item in doc.get_toc(simple=True) or []:
        if len(item) < 3:
            continue
        lvl, title, page_1 = int(item[0]), str(item[1]), int(item[2])
        new_idx = first_new.get((source, page_1 - 1))
        if new_idx is None:
            continue
        out.append([lvl + shift, title, new_idx + 1])
    return out


def assemble_pdf(
    refs: Sequence[PageRef],
    sources: Mapping[str, fitz.Document],
    *,
    keep_bookmarks: bool = True,
    bookmark_titles: Optional[Mapping[str, str]] = None,
) -> fitz.Document:
    """Dựng tài liệu PDF mới (trong bộ nhớ) từ danh sách trang.

    - Chú thích, liên kết và trường biểu mẫu của trang được chép theo trang.
    - `keep_bookmarks`: giữ mục lục của các trang còn lại (trỏ tới lần xuất hiện đầu tiên của trang).
    - `bookmark_titles` (khi ghép nhiều tệp): thêm 1 mục cấp 1 cho mỗi tệp nguồn, mục lục gốc lùi vào 1 cấp.
    """
    if not refs:
        raise PageOpsError("Tài liệu kết quả không có trang nào.")
    out = fitz.open()
    first_new: Dict[Tuple[str, int], int] = {}
    source_order: List[str] = []
    last_size = A4_SIZE

    for run in _runs(refs):
        head = run[0]
        if head.is_blank:
            w = head.width or last_size[0]
            h = head.height or last_size[1]
            out.new_page(width=w, height=h)
            last_size = (w, h)
            continue
        src = sources.get(head.source)
        if src is None:
            raise PageOpsError(f"Thiếu tài liệu nguồn: {head.source}")
        for r in run:
            if not 0 <= r.page_index < src.page_count:
                raise PageOpsError(f"Trang {r.page_index + 1} không có trong {Path(head.source).name}.")
        start = out.page_count
        out.insert_pdf(src, from_page=run[0].page_index, to_page=run[-1].page_index)
        for offset, r in enumerate(run):
            new_idx = start + offset
            first_new.setdefault((r.source, r.page_index), new_idx)
            page = out[new_idx]
            if r.rotation:
                page.set_rotation((page.rotation + r.rotation) % 360)
            last_size = (page.rect.width, page.rect.height)
        if head.source not in source_order:
            source_order.append(head.source)

    # Chú thích đã xoá trong phiên chỉnh sửa (đang ẩn) không được mang sang tệp mới
    from qtpdfpro.core.annotations import purge_deleted

    purge_deleted(out)

    if source_order:
        meta = dict(sources[source_order[0]].metadata or {})
        meta = {k: v for k, v in meta.items() if k in ("title", "author", "subject", "keywords", "creator")}
        meta["producer"] = "QT PDF Pro"
        try:
            out.set_metadata(meta)
        except Exception:
            pass

    if keep_bookmarks and source_order:
        toc: List[list] = []
        if bookmark_titles:
            for key in source_order:
                firsts = [i for (s, _p), i in first_new.items() if s == key]
                if not firsts:
                    continue
                toc.append([1, bookmark_titles.get(key) or Path(key).stem, min(firsts) + 1])
                toc.extend(_remap_toc(sources[key], key, first_new, shift=1))
        else:
            for key in source_order:
                toc.extend(_remap_toc(sources[key], key, first_new, shift=0))
        if toc:
            try:
                out.set_toc(_normalized_toc(toc))
            except Exception:
                pass
    return out


def save_pdf(doc: fitz.Document, path: Union[str, Path]) -> Path:
    """Ghi tài liệu ra tệp (nén, dọn đối tượng thừa) qua tệp tạm rồi đổi tên — không để lại tệp hỏng."""
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.stem}.qtpdfpro-tmp.pdf")
    doc.save(str(tmp), garbage=3, deflate=True)
    try:
        os.replace(tmp, target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return target


# ─── Mở tài liệu nguồn theo đường dẫn ─────────────────────────────────────


class SourceSet:
    """Mở và giữ các tệp PDF nguồn theo đường dẫn (khoá = đường dẫn tuyệt đối); đóng hết khi thoát `with`."""

    def __init__(self) -> None:
        self.docs: Dict[str, fitz.Document] = {}

    def open(self, path: Union[str, Path], password: Optional[str] = None) -> str:
        p = Path(path).resolve()
        key = str(p)
        if key in self.docs:
            return key
        if not p.exists():
            raise FileNotFoundError(f"Không tìm thấy tệp PDF: {p}")
        doc = fitz.open(key)
        if not doc.is_pdf:
            doc.close()
            raise PageOpsError(f"Không phải tệp PDF: {p.name}")
        if doc.needs_pass and not (password and doc.authenticate(password)):
            doc.close()
            raise PermissionError(f"Tệp PDF được bảo vệ bằng mật khẩu: {p.name}")
        self.docs[key] = doc
        return key

    def close(self) -> None:
        for doc in self.docs.values():
            if not doc.is_closed:
                doc.close()
        self.docs.clear()

    def __enter__(self) -> "SourceSet":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def _check_not_source(output: Path, sources: SourceSet) -> None:
    if str(output.resolve()) in sources.docs:
        raise PageOpsError(f"Tệp kết quả trùng tệp nguồn — hãy chọn tên khác: {output.name}")


def _write(refs: Sequence[PageRef], sources: SourceSet, output: Union[str, Path], **kwargs) -> Tuple[Path, int]:
    out_path = Path(output)
    _check_not_source(out_path, sources)
    doc = assemble_pdf(refs, sources.docs, **kwargs)
    try:
        saved = save_pdf(doc, out_path)
        return saved, doc.page_count
    finally:
        doc.close()


def organize_pdf(src: Union[str, Path], order_spec: str, output: Union[str, Path]) -> OrganizeResult:
    """Sắp xếp / xoá / xoay / nhân bản / chèn trang trắng theo chuỗi thứ tự (xem `parse_order_spec`)."""
    with SourceSet() as sources:
        key = sources.open(src)
        refs = parse_order_spec(order_spec, sources.docs[key].page_count, key)
        saved, n = _write(refs, sources, output)
    return OrganizeResult([str(saved)], [n])


def extract_pages(src: Union[str, Path], pages_spec: str, output: Union[str, Path]) -> OrganizeResult:
    """Trích các trang chọn (`'1-3,5'`) thành tệp mới, giữ thứ tự gốc của tài liệu."""
    with SourceSet() as sources:
        key = sources.open(src)
        total = sources.docs[key].page_count
        pages = sorted(parse_page_selection(pages_spec, total))
        refs = [PageRef(key, i) for i in pages]
        saved, n = _write(refs, sources, output)
    return OrganizeResult([str(saved)], [n])


def merge_pdfs(
    inputs: Sequence[Union[str, Path]],
    output: Union[str, Path],
    *,
    bookmarks: bool = True,
) -> OrganizeResult:
    """Ghép nhiều tệp PDF (mỗi phần tử có thể kèm phạm vi trang: `'a.pdf:1-3'`) thành một tệp."""
    if not inputs:
        raise PageOpsError("Chưa chọn tệp PDF cần ghép.")
    with SourceSet() as sources:
        refs: List[PageRef] = []
        titles: Dict[str, str] = {}
        for item in inputs:
            path, spec = split_input_spec(str(item))
            key = sources.open(path)
            total = sources.docs[key].page_count
            titles.setdefault(key, Path(key).stem)
            if spec:
                refs.extend(parse_order_spec(spec, total, key))
            else:
                refs.extend(refs_for_document(key, total))
        saved, n = _write(refs, sources, output, bookmark_titles=titles if bookmarks else None,
                          keep_bookmarks=bookmarks)
    return OrganizeResult([str(saved)], [n])


def part_file_names(stem: str, count: int) -> List[str]:
    width = max(2, len(str(count)))
    return [f"{stem}_phan_{i + 1:0{width}d}.pdf" for i in range(count)]


def write_parts(
    parts: Sequence[Sequence[PageRef]],
    sources: Mapping[str, fitz.Document],
    output_dir: Union[str, Path],
    stem: str,
) -> OrganizeResult:
    """Ghi từng phần (danh sách trang) thành một tệp `<stem>_phan_01.pdf`, `<stem>_phan_02.pdf`, …"""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[str] = []
    counts: List[int] = []
    source_paths = {str(Path(k).resolve()) for k in sources if k}
    for name, part in zip(part_file_names(stem, len(parts)), parts):
        target = out_dir / name
        if str(target.resolve()) in source_paths:
            raise PageOpsError(f"Tệp kết quả trùng tệp nguồn: {target.name}")
        doc = assemble_pdf(part, sources)
        try:
            paths.append(str(save_pdf(doc, target)))
            counts.append(doc.page_count)
        finally:
            doc.close()
    return OrganizeResult(paths, counts)


def split_pdf(
    src: Union[str, Path],
    output_dir: Union[str, Path],
    *,
    every: Optional[int] = None,
    ranges: Optional[str] = None,
    after: Optional[Iterable[int]] = None,
) -> OrganizeResult:
    """Tách tệp PDF thành nhiều tệp: mỗi `every` trang, theo `ranges` (`'1-3,4-6'`) hoặc cắt `after` các trang."""
    if sum(x is not None for x in (every, ranges, after)) != 1:
        raise PageOpsError("Chọn đúng một cách tách: mỗi N trang, theo khoảng trang, hoặc cắt sau các trang.")
    with SourceSet() as sources:
        key = sources.open(src)
        total = sources.docs[key].page_count
        refs = refs_for_document(key, total)
        if ranges is not None:
            parts = [[PageRef(key, i) for i in part] for part in parse_split_ranges(ranges, total)]
        else:
            parts = split_refs(refs, every=every, after=after)
        return write_parts(parts, sources.docs, output_dir, Path(key).stem)
