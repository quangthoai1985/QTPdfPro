"""Cầu nối Microsoft Word Native Reflow (Chế độ 3 — MS Word COM Bridge).

Khi máy tính Windows có cài đặt Microsoft Word (`WINWORD.EXE`), mô-đun này cho phép
gọi bộ chuyển đổi PDF Reflow thương mại của Microsoft Word ở chế độ nền (headless COM),
sau đó kết hợp với Bộ Hậu xử lý Chuẩn xác OpenXML (`openxml_fixer.py`) của QT PDF Pro.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

import fitz  # PyMuPDF


def is_ms_word_available() -> bool:
    """Kiểm tra nhanh xem Microsoft Word có được cài đặt trên máy Windows không."""
    common_paths = [
        Path(r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE"),
        Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE"),
        Path(r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE"),
    ]
    return any(p.exists() for p in common_paths)


def convert_via_ms_word_com(
    pdf_path: str | Path,
    docx_path: str | Path,
    pages: Optional[List[int]] = None,
    timeout_sec: int = 90,
) -> bool:
    """Chuyển đổi PDF sang DOCX thông qua COM Automation của Microsoft Word.

    Trả về `True` nếu chuyển đổi thành công và tạo ra tệp `.docx` hợp lệ,
    ngược lại trả về `False` để bộ điều phối tự động chuyển về Engine `Hybrid Structural Flow`.
    """
    src = Path(pdf_path).resolve()
    dst = Path(docx_path).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix="qtpdf_wordcom_"))
    try:
        input_pdf = src
        if pages is not None:
            # Nếu chỉ chọn một số trang, trích xuất các trang đó ra tệp PDF tạm
            input_pdf = tmp_dir / "subset.pdf"
            with fitz.open(str(src)) as doc_in, fitz.open() as doc_sub:
                for p in pages:
                    if 0 <= p < len(doc_in):
                        doc_sub.insert_pdf(doc_in, from_page=p, to_page=p)
                doc_sub.save(str(input_pdf))

        ps_script = tmp_dir / "convert_word.ps1"
        ps_code = (
            # `param(...)` bắt buộc là câu lệnh đầu tiên của script PowerShell
            "param([string]$PdfFile, [string]$DocxFile)\n"
            "$ErrorActionPreference = 'Stop'\n"
            "$word = $null\n"
            "$doc = $null\n"
            "try {\n"
            "    $word = New-Object -ComObject Word.Application\n"
            "    $word.Visible = $false\n"
            "    $word.DisplayAlerts = 0\n"
            "    $doc = $word.Documents.Open($PdfFile, $false, $true, $false)\n"
            "    $wdFormatXMLDocument = 16\n"
            "    $doc.SaveAs2([ref]$DocxFile, [ref]$wdFormatXMLDocument)\n"
            "    $doc.Close($false)\n"
            "    $word.Quit()\n"
            "    exit 0\n"
            "} catch {\n"
            "    if ($doc -ne $null) { try { $doc.Close($false) } catch {} }\n"
            "    if ($word -ne $null) { try { $word.Quit() } catch {} }\n"
            "    exit 1\n"
            "}\n"
        )
        # BOM UTF-8 để Windows PowerShell 5.1 đọc đúng đường dẫn tiếng Việt
        ps_script.write_text(ps_code, encoding="utf-8-sig")

        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps_script),
                str(input_pdf),
                str(dst),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        return proc.returncode == 0 and dst.exists() and dst.stat().st_size > 1024
    except Exception:
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
