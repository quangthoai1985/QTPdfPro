"""Kiểm chứng bố cục DOCX so với PDF gốc bằng chính Microsoft Word (Render Verify).

Bộ kiểm định `fidelity.py` chỉ đếm chữ / bảng / ảnh nên không phát hiện được DOCX bị lệch dòng,
tràn trang. Module này xuất DOCX trở lại PDF **bằng Microsoft Word** (đúng như người dùng sẽ thấy
khi mở tệp), rồi so khớp từng dòng chữ với PDF gốc:

- Số trang, số dòng khớp nội dung, số dòng bị đẩy sang trang khác.
- Độ lệch đường cơ sở (dọc) và mép trái/phải (ngang) của từng dòng, tính bằng pt.

Chỉ chạy được trên Windows có cài Microsoft Word; nếu không, báo `available = False`.
"""

from __future__ import annotations

import difflib
import re
import shutil
import statistics
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

import fitz  # PyMuPDF

from qtpdfpro.core.admin_layout import extract_text_lines
from qtpdfpro.core.word_com_bridge import is_ms_word_available

_PS_DOCX_TO_PDF = """param([string]$DocxFile, [string]$PdfFile)
$ErrorActionPreference = 'Stop'
$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $doc = $word.Documents.Open($DocxFile, $false, $true, $false)
    $doc.ExportAsFixedFormat($PdfFile, 17)
    $doc.Close($false)
    $word.Quit()
    exit 0
} catch {
    if ($doc -ne $null) { try { $doc.Close($false) } catch {} }
    if ($word -ne $null) { try { $word.Quit() } catch {} }
    exit 1
}
"""


@dataclass
class LayoutVerifyReport:
    """Kết quả so khớp vị trí từng dòng giữa PDF gốc và DOCX (do Word dàn trang)."""

    available: bool = False
    pdf_pages: int = 0
    docx_pages: int = 0
    pdf_lines: int = 0
    docx_lines: int = 0
    matched_lines: int = 0
    moved_page_lines: int = 0
    max_dy_pt: float = 0.0
    mean_dy_pt: float = 0.0
    max_dx_pt: float = 0.0
    mean_dx_pt: float = 0.0
    verdict: str = ""  # "match" | "minor" | "deviated" | "unavailable"
    score: float = 0.0
    samples: List[str] = field(default_factory=list)
    note: str = ""

    @property
    def verdict_text(self) -> str:
        return {
            "match": "Trùng khớp PDF gốc",
            "minor": "Lệch nhỏ (cần xem lại vài dòng)",
            "deviated": "Lệch đáng kể so với PDF gốc",
        }.get(self.verdict, "Không kiểm chứng được (máy chưa cài Microsoft Word)")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict_text"] = self.verdict_text
        return d


def export_docx_to_pdf_via_word(docx_path: str | Path, pdf_path: str | Path, timeout_sec: int = 120) -> bool:
    """Xuất DOCX sang PDF bằng Microsoft Word chạy nền (COM qua PowerShell)."""
    src = Path(docx_path).resolve()
    dst = Path(pdf_path).resolve()
    tmp_dir = Path(tempfile.mkdtemp(prefix="qtpdf_verify_"))
    try:
        script = tmp_dir / "docx_to_pdf.ps1"
        script.write_text(_PS_DOCX_TO_PDF, encoding="utf-8-sig")
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), str(src), str(dst)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        return proc.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    except Exception:
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _collect_lines(pdf: fitz.Document, pages: Optional[Sequence[int]]) -> list[tuple[int, str, float, float, float]]:
    out: list[tuple[int, str, float, float, float]] = []
    page_ids = list(pages) if pages is not None else list(range(len(pdf)))
    for order, pno in enumerate(page_ids):
        for ln in extract_text_lines(pdf[pno]):
            txt = re.sub(r"\s+", " ", ln.text).strip()
            if txt:
                out.append((order, txt, ln.x0, ln.x1, ln.baseline))
    return out


def compare_pdf_layouts(
    original_pdf: str | Path,
    rendered_pdf: str | Path,
    pages: Optional[Sequence[int]] = None,
) -> LayoutVerifyReport:
    """So khớp từng dòng chữ giữa PDF gốc (các trang `pages`) và PDF dựng lại từ DOCX."""
    rep = LayoutVerifyReport(available=True)
    with fitz.open(str(original_pdf)) as a_doc, fitz.open(str(rendered_pdf)) as b_doc:
        a = _collect_lines(a_doc, pages)
        b = _collect_lines(b_doc, None)
        rep.pdf_pages = len(pages) if pages is not None else len(a_doc)
        rep.docx_pages = len(b_doc)
    rep.pdf_lines, rep.docx_lines = len(a), len(b)

    sm = difflib.SequenceMatcher(a=[x[1] for x in a], b=[x[1] for x in b], autojunk=False)
    dys: list[float] = []
    dxs: list[float] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            if len(rep.samples) < 8:
                left = " | ".join(x[1][:40] for x in a[i1:i2][:2])
                right = " | ".join(x[1][:40] for x in b[j1:j2][:2])
                rep.samples.append(f"Khác ngắt dòng: «{left}» ↔ «{right}»")
            continue
        for i, j in zip(range(i1, i2), range(j1, j2)):
            pa, pb = a[i], b[j]
            rep.matched_lines += 1
            if pa[0] != pb[0]:
                rep.moved_page_lines += 1
                continue
            dy = abs(pb[4] - pa[4])
            dx = max(abs(pb[2] - pa[2]), abs(pb[3] - pa[3]))
            dys.append(dy)
            dxs.append(dx)
            if (dy > 2.0 or dx > 2.0) and len(rep.samples) < 8:
                rep.samples.append(f"Lệch {dx:.1f} pt ngang / {dy:.1f} pt dọc: «{pa[1][:50]}»")
    if dys:
        rep.max_dy_pt = round(max(dys), 2)
        rep.mean_dy_pt = round(statistics.fmean(dys), 2)
        rep.max_dx_pt = round(max(dxs), 2)
        rep.mean_dx_pt = round(statistics.fmean(dxs), 2)

    total = max(1, rep.pdf_lines)
    match_ratio = rep.matched_lines / total
    in_place = (rep.matched_lines - rep.moved_page_lines) / total
    if (
        rep.pdf_pages == rep.docx_pages
        and rep.moved_page_lines == 0
        and match_ratio >= 0.98
        and rep.max_dy_pt <= 2.0
        and rep.max_dx_pt <= 2.0
    ):
        rep.verdict = "match"
    elif match_ratio >= 0.9 and rep.pdf_pages == rep.docx_pages:
        rep.verdict = "minor"
    else:
        rep.verdict = "deviated"
    penalty_pos = min(15.0, 2.0 * rep.mean_dy_pt + 1.0 * max(0.0, rep.max_dy_pt - 2.0))
    penalty_page = 0.0 if rep.pdf_pages == rep.docx_pages else 15.0
    rep.score = round(max(0.0, 100.0 * in_place - penalty_pos - penalty_page), 1)
    return rep


def verify_docx_layout(
    pdf_path: str | Path,
    docx_path: str | Path,
    pages: Optional[Sequence[int]] = None,
    timeout_sec: int = 180,
) -> LayoutVerifyReport:
    """Dựng DOCX bằng Microsoft Word rồi so vị trí từng dòng với PDF gốc."""
    if not is_ms_word_available():
        return LayoutVerifyReport(available=False, verdict="unavailable", note="Máy chưa cài Microsoft Word.")
    tmp_dir = Path(tempfile.mkdtemp(prefix="qtpdf_render_"))
    try:
        rendered = tmp_dir / "rendered.pdf"
        if not export_docx_to_pdf_via_word(docx_path, rendered, timeout_sec=timeout_sec):
            return LayoutVerifyReport(available=False, verdict="unavailable", note="Microsoft Word không xuất được PDF.")
        return compare_pdf_layouts(pdf_path, rendered, pages)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
