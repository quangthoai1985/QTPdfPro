"""Tìm kiếm thông minh (Smart Search) tiếng Việt cho cả PDF có lớp chữ và PDF ảnh scan (OCR).

Tính năng:
- Tìm chính xác có dấu (ưu tiên) và tìm thông minh không cần gõ dấu tiếng Việt (`quyet dinh` → `Quyết định`).
- Tìm được cụm từ vắt qua ngắt dòng (trả về đủ `rects` trên từng dòng) và chữ phông TCVN3 (`.Vn*`).
- Hợp nhất liền mạch lớp chữ PDF thật và lớp chữ nhận dạng OCR (`ocr_words`) trên các trang ảnh scan.
- Trích xuất `snippet` ngữ cảnh căn giữa đúng vị trí từ khoá khớp (kể cả khi một dòng có nhiều kết quả).
- Không phụ thuộc PySide6.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF

from qtpdfpro.core import text_select as ts
from qtpdfpro.core.font_resolver import detect_font_encoding, normalize_vietnamese_text
from qtpdfpro.core.layout_analyzer import BBox


@dataclass(frozen=True)
class SearchOptions:
    """Tuỳ chọn tìm kiếm thông minh."""

    case_sensitive: bool = False
    whole_word: bool = False
    smart_accents: bool = True
    max_hits: int = 500


@dataclass
class SearchHit:
    """Một kết quả tìm kiếm văn bản trên trang PDF."""

    page_index: int  # 0-based
    bbox: BBox
    snippet: str
    rects: Tuple[BBox, ...] = ()
    exact: bool = True
    source: str = "text"  # "text" | "ocr"


def fold_char(ch: str) -> str:
    """Bỏ dấu tiếng Việt của một ký tự (giữ nguyên hoa/thường)."""
    if ch == "đ":
        return "d"
    if ch == "Đ":
        return "D"
    nfkd = unicodedata.normalize("NFD", ch)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def fold_text(text: str) -> str:
    """Bỏ dấu tiếng Việt toàn chuỗi (giữ nguyên hoa/thường)."""
    return "".join(fold_char(c) for c in text)


def has_vietnamese_diacritics(text: str) -> bool:
    """True nếu chuỗi có ít nhất một dấu thanh / dấu mũ / chữ đ-Đ."""
    nfc = normalize_vietnamese_text(text)
    return fold_text(nfc) != nfc


def _is_word_char(ch: str) -> bool:
    return bool(ch) and (ch.isalnum() or ch == "_")


def _rect_overlap_ratio(a: BBox, b: BBox) -> float:
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
    return inter / area_a


def _merge_pdf_and_ocr_words(
    pdf_words: Sequence[ts.Word],
    ocr_words: Sequence[ts.Word],
    page_text_chars: int,
) -> List[Tuple[ts.Word, str]]:
    """Hợp nhất từ trên lớp chữ PDF và từ OCR (không trùng lặp trên trang scan)."""
    if not ocr_words:
        return [(w, "text") for w in pdf_words]
    if not pdf_words:
        return [(w, "ocr") for w in ocr_words]
    if page_text_chars >= ts.SCANNED_PAGE_CHARS:
        return [(w, "text") for w in pdf_words]

    # Trang scan: ưu tiên chữ OCR và giữ các chữ PDF đóng dấu (như số hiệu/ngày) không chồng lên chữ OCR
    ocr_boxes = [(float(w[0]), float(w[1]), float(w[2]), float(w[3])) for w in ocr_words]
    combined: List[Tuple[ts.Word, str]] = [(w, "ocr") for w in ocr_words]
    for pw in pdf_words:
        pbox = (float(pw[0]), float(pw[1]), float(pw[2]), float(pw[3]))
        if not any(_rect_overlap_ratio(pbox, ob) > 0.45 for ob in ocr_boxes):
            combined.append((pw, "text"))
    return combined


def _assign_visual_lines(items: Sequence[Tuple[ts.Word, str]]) -> List[int]:
    """Gán chỉ số dòng trực quan cho mỗi từ theo thứ tự đọc."""
    if not items:
        return []
    line_ids = [0]
    cur_line = 0
    for idx in range(1, len(items)):
        prev_w, prev_src = items[idx - 1]
        cur_w, cur_src = items[idx]
        same_key = prev_src == cur_src and (prev_w[5], prev_w[6]) == (cur_w[5], cur_w[6])
        if same_key:
            line_ids.append(cur_line)
            continue
        # Kiểm tra chồng lấn theo trục dọc nếu khác nguồn
        if prev_src != cur_src:
            y_ov = min(prev_w[3], cur_w[3]) - max(prev_w[1], cur_w[1])
            min_h = max(1.0, min(prev_w[3] - prev_w[1], cur_w[3] - cur_w[1]))
            if y_ov > 0.4 * min_h and cur_w[0] >= prev_w[0] - 0.5 * min_h:
                line_ids.append(cur_line)
                continue
        cur_line += 1
        line_ids.append(cur_line)
    return line_ids


def _build_stream(
    items: Sequence[Tuple[ts.Word, str]],
) -> Tuple[str, List[int], List[Tuple[int, int]], List[int]]:
    """Dựng chuỗi văn bản liên tục kèm ánh xạ ký tự ↔ từ ↔ dòng trực quan."""
    line_ids = _assign_visual_lines(items)
    chars: List[str] = []
    char_word: List[int] = []
    char_sub: List[Tuple[int, int]] = []  # (vị trí trong từ, tổng độ dài từ)

    for w_idx, (w, _src) in enumerate(items):
        wtext = normalize_vietnamese_text(str(w[4])).strip()
        if not wtext:
            continue
        if chars:
            chars.append(" ")
            char_word.append(-1)
            char_sub.append((0, 0))
        wlen = len(wtext)
        for pos, ch in enumerate(wtext):
            chars.append(ch)
            char_word.append(w_idx)
            char_sub.append((pos, wlen))

    return "".join(chars), char_word, char_sub, line_ids


def _build_search_haystack(
    page_str: str,
    *,
    fold: bool,
    case_sensitive: bool,
) -> Tuple[str, List[int]]:
    """Tạo chuỗi tìm kiếm kèm ánh xạ 1-n từ vị trí `haystack` về vị trí gốc trong `page_str`."""
    out_chars: List[str] = []
    to_orig: List[int] = []
    for orig_idx, ch in enumerate(page_str):
        mapped = fold_char(ch) if fold else ch
        if not case_sensitive:
            mapped = mapped.lower()
        for mc in mapped:
            out_chars.append(mc)
            to_orig.append(orig_idx)
    return "".join(out_chars), to_orig


def _make_snippet(
    page_str: str,
    char_word: Sequence[int],
    line_ids: Sequence[int],
    orig_start: int,
    orig_end: int,
    max_len: int = 90,
) -> str:
    """Trích ngữ cảnh ngay tại dòng chứa kết quả; cắt đều hai đầu nếu dòng quá dài."""
    # Tìm phạm vi dòng trực quan đầu tiên của đoạn khớp
    start_w = next((char_word[i] for i in range(orig_start, orig_end + 1) if char_word[i] >= 0), -1)
    if start_w < 0:
        snippet = page_str[orig_start : orig_end + 1].strip()
        return snippet[: max_len - 3] + "..." if len(snippet) > max_len else snippet

    target_line = line_ids[start_w]
    line_char_start = orig_start
    while line_char_start > 0:
        pw = char_word[line_char_start - 1]
        if pw >= 0 and line_ids[pw] != target_line:
            break
        if pw == -1 and line_char_start >= 2:
            ppw = char_word[line_char_start - 2]
            if ppw >= 0 and line_ids[ppw] != target_line:
                break
        line_char_start -= 1

    line_char_end = orig_end
    n = len(page_str)
    while line_char_end + 1 < n:
        nw = char_word[line_char_end + 1]
        if nw >= 0 and line_ids[nw] != target_line:
            break
        if nw == -1 and line_char_end + 2 < n:
            nnw = char_word[line_char_end + 2]
            if nnw >= 0 and line_ids[nnw] != target_line:
                break
        line_char_end += 1

    line_text = page_str[line_char_start : line_char_end + 1].strip()
    if len(line_text) <= max_len:
        return line_text

    # Căn cửa sổ ngữ cảnh quanh vị trí từ khoá trong dòng
    rel_start = max(0, orig_start - line_char_start)
    rel_end = max(rel_start, orig_end - line_char_start)
    match_mid = (rel_start + rel_end) // 2
    half = max_len // 2
    win_start = max(0, match_mid - half)
    win_end = min(len(line_text), win_start + max_len)
    if win_end - win_start < max_len:
        win_start = max(0, win_end - max_len)
    piece = line_text[win_start:win_end].strip()
    if win_start > 0:
        piece = "..." + piece.lstrip()
    if win_end < len(line_text):
        piece = piece.rstrip() + "..."
    return piece[:max_len]


def _match_rects(
    items: Sequence[Tuple[ts.Word, str]],
    char_word: Sequence[int],
    char_sub: Sequence[Tuple[int, int]],
    line_ids: Sequence[int],
    orig_start: int,
    orig_end: int,
) -> Tuple[Tuple[BBox, ...], str]:
    """Tính khung tô sáng gộp theo từng dòng trực quan và nguồn chữ (`'text'` hoặc `'ocr'`)."""
    word_ranges: Dict[int, List[int]] = {}
    word_order: List[int] = []
    hit_sources: set[str] = set()

    for c_idx in range(orig_start, orig_end + 1):
        w_idx = char_word[c_idx]
        if w_idx < 0:
            continue
        sub_pos, wlen = char_sub[c_idx]
        if w_idx not in word_ranges:
            word_ranges[w_idx] = [sub_pos, sub_pos + 1, wlen]
            word_order.append(w_idx)
        else:
            word_ranges[w_idx][0] = min(word_ranges[w_idx][0], sub_pos)
            word_ranges[w_idx][1] = max(word_ranges[w_idx][1], sub_pos + 1)
        hit_sources.add(items[w_idx][1])

    line_boxes: Dict[int, BBox] = {}
    line_order: List[int] = []
    for w_idx in word_order:
        w = items[w_idx][0]
        s0, s1, wlen = word_ranges[w_idx]
        wlen = max(1, wlen)
        x0, y0, x1, y1 = float(w[0]), float(w[1]), float(w[2]), float(w[3])
        if s0 == 0 and s1 >= wlen:
            wb = (x0, y0, x1, y1)
        else:
            fx0 = x0 + (x1 - x0) * (s0 / wlen)
            fx1 = x0 + (x1 - x0) * (s1 / wlen)
            wb = (fx0, y0, max(fx0 + 1.0, fx1), y1)
        lid = line_ids[w_idx]
        if lid not in line_boxes:
            line_boxes[lid] = wb
            line_order.append(lid)
        else:
            prev = line_boxes[lid]
            line_boxes[lid] = (min(prev[0], wb[0]), min(prev[1], wb[1]), max(prev[2], wb[2]), max(prev[3], wb[3]))

    rects = tuple(line_boxes[lid] for lid in line_order)
    src = "ocr" if "ocr" in hit_sources else "text"
    return rects, src


def _snap_glyph_rect(
    page: Optional[fitz.Page],
    exact_slice: str,
    approx_rect: BBox,
    cache: Dict[str, List[BBox]],
) -> BBox:
    """Nếu là lớp chữ PDF thật và `page.search_for` khớp khít được, ưu tiên dùng khung glyph chính xác."""
    if page is None or not exact_slice:
        return approx_rect
    if exact_slice not in cache:
        try:
            cache[exact_slice] = [
                (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
                for r in page.search_for(exact_slice)
            ]
        except Exception:
            cache[exact_slice] = []
    best = None
    best_ov = 0.2
    for gr in cache[exact_slice]:
        ov = _rect_overlap_ratio(approx_rect, gr)
        if ov > best_ov:
            best_ov = ov
            best = gr
    return best if best is not None else approx_rect


def search_page_items(
    page_index: int,
    items: Sequence[Tuple[ts.Word, str]],
    query: str,
    options: SearchOptions,
    *,
    page: Optional[fitz.Page] = None,
    force_fold: Optional[bool] = None,
    only_source: Optional[str] = None,
) -> List[SearchHit]:
    """Tìm kiếm trên danh sách từ của một trang đã hợp nhất."""
    q_norm = " ".join(normalize_vietnamese_text(query).split())
    if not q_norm or not items:
        return []

    page_str, char_word, char_sub, line_ids = _build_stream(items)
    if not page_str:
        return []

    q_has_acc = has_vietnamese_diacritics(q_norm)
    use_fold = force_fold if force_fold is not None else (options.smart_accents and not q_has_acc)
    haystack, to_orig = _build_search_haystack(page_str, fold=use_fold, case_sensitive=options.case_sensitive)
    needle = fold_text(q_norm) if use_fold else q_norm
    if not options.case_sensitive:
        needle = needle.lower()
    if not needle:
        return []

    q_cmp = q_norm if options.case_sensitive else q_norm.lower()
    glyph_cache: Dict[str, List[BBox]] = {}
    hits: List[SearchHit] = []
    pos = 0
    n_len = len(needle)

    while True:
        idx = haystack.find(needle, pos)
        if idx < 0:
            break
        pos = idx + max(1, n_len)
        orig_start = to_orig[idx]
        orig_end = to_orig[idx + n_len - 1]

        if options.whole_word:
            if orig_start > 0 and _is_word_char(page_str[orig_start - 1]):
                continue
            if orig_end + 1 < len(page_str) and _is_word_char(page_str[orig_end + 1]):
                continue

        rects, src = _match_rects(items, char_word, char_sub, line_ids, orig_start, orig_end)
        if not rects:
            continue
        if only_source is not None and src != only_source:
            continue

        orig_slice = page_str[orig_start : orig_end + 1]
        is_exact = (orig_slice if options.case_sensitive else orig_slice.lower()) == q_cmp
        if src == "text" and len(rects) == 1 and page is not None:
            snapped = _snap_glyph_rect(page, orig_slice, rects[0], glyph_cache)
            rects = (snapped,)

        snippet = _make_snippet(page_str, char_word, line_ids, orig_start, orig_end)
        hits.append(
            SearchHit(
                page_index=page_index,
                bbox=rects[0],
                snippet=snippet,
                rects=rects,
                exact=is_exact,
                source=src,
            )
        )
        if len(hits) >= options.max_hits:
            break

    return hits


def _page_has_tcvn3(page: fitz.Page) -> bool:
    try:
        return any(detect_font_encoding(str(f[3])) == "tcvn3" for f in page.get_fonts(full=False))
    except Exception:
        return False


def search_document(
    doc: fitz.Document,
    query: str,
    options: Optional[SearchOptions] = None,
    *,
    ocr_words: Optional[Dict[int, Sequence[ts.Word]]] = None,
) -> List[SearchHit]:
    """Tìm kiếm thông minh trên toàn bộ `fitz.Document`, kết hợp chữ PDF gốc và `ocr_words`."""
    opts = options or SearchOptions()
    q_norm = " ".join(normalize_vietnamese_text(query).split())
    if not q_norm:
        return []

    q_has_acc = has_vietnamese_diacritics(q_norm)
    q_folded_lower = fold_text(q_norm).lower()
    q_lower = q_norm.lower()

    hits: List[SearchHit] = []
    ocr_pages_items: List[Tuple[int, fitz.Page, List[Tuple[ts.Word, str]]]] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        p_ocr = ocr_words.get(page_idx) if ocr_words else None

        # Lọc nhanh trang thường khi chắc chắn không chứa từ khoá
        if not p_ocr and not _page_has_tcvn3(page):
            raw_txt = " ".join(normalize_vietnamese_text(page.get_text("text")).split())
            if opts.smart_accents and not q_has_acc:
                if q_folded_lower not in fold_text(raw_txt).lower():
                    continue
            elif not opts.case_sensitive:
                if q_lower not in raw_txt.lower():
                    continue
            else:
                if q_norm not in raw_txt:
                    continue

        pdf_words = ts.page_words(page)
        text_chars = sum(len(str(w[4])) for w in pdf_words)
        items = _merge_pdf_and_ocr_words(pdf_words, p_ocr or (), text_chars)
        if p_ocr:
            ocr_pages_items.append((page_idx, page, items))

        remaining = opts.max_hits - len(hits)
        if remaining <= 0:
            break
        page_opts = SearchOptions(
            case_sensitive=opts.case_sensitive,
            whole_word=opts.whole_word,
            smart_accents=opts.smart_accents,
            max_hits=remaining,
        )
        hits.extend(search_page_items(page_idx, items, q_norm, page_opts, page=page))
        if len(hits) >= opts.max_hits:
            break

    # Lượt 2 (thông minh cho trang scan): nếu người dùng gõ có dấu mà trang scan OCR sai dấu nhẹ (0 kết quả),
    # tự động tìm lại trên lớp chữ OCR theo chế độ bỏ dấu để không bỏ sót tài liệu scan.
    if not hits and opts.smart_accents and q_has_acc and ocr_pages_items:
        for page_idx, page, items in ocr_pages_items:
            remaining = opts.max_hits - len(hits)
            if remaining <= 0:
                break
            page_opts = SearchOptions(
                case_sensitive=opts.case_sensitive,
                whole_word=opts.whole_word,
                smart_accents=True,
                max_hits=remaining,
            )
            hits.extend(
                search_page_items(
                    page_idx,
                    items,
                    q_norm,
                    page_opts,
                    page=page,
                    force_fold=True,
                    only_source="ocr",
                )
            )

    return hits
