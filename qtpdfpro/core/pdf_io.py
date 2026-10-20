"""Hàm dùng chung cho các công cụ PDF ghi ra tệp mới: nén, dấu nước, đánh số trang, đặt / gỡ mật khẩu.

Không phụ thuộc `PySide6`. Quy ước chung của mọi công cụ:

- Mở tệp nguồn theo đường dẫn, kèm mật khẩu nếu có (`open_pdf`). Tệp đang hạn chế quyền sửa thì chỉ xử lý
  khi đăng nhập bằng **mật khẩu chủ** — tôn trọng quyền tác giả đã đặt.
- Văn bản có **chữ ký số**: mọi công cụ đều ghi lại toàn bộ tệp nên chữ ký mất hiệu lực → từ chối nếu không
  được phép rõ ràng (`allow_signed=True`, CLI `--force`, giao diện hỏi trước).
- Tệp kết quả không được trùng tệp nguồn; ghi qua tệp tạm rồi đổi tên (`page_ops.save_pdf`).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NamedTuple, Optional, Union

import fitz  # PyMuPDF

PathLike = Union[str, Path]

ALL_PERMISSIONS = (
    fitz.PDF_PERM_PRINT | fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_COPY | fitz.PDF_PERM_ANNOTATE
    | fitz.PDF_PERM_FORM | fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_ASSEMBLE | fitz.PDF_PERM_PRINT_HQ
)


class PdfToolError(ValueError):
    """Lỗi tham số hoặc tệp không xử lý được (thông báo tiếng Việt)."""


class SignedDocumentError(PdfToolError):
    """Tệp có chữ ký số — xử lý sẽ làm chữ ký mất hiệu lực."""


class OpenedPdf(NamedTuple):
    """Tài liệu đã mở bằng `open_pdf`."""

    doc: fitz.Document
    owner: bool  # đã đăng nhập bằng mật khẩu chủ (hoặc tệp không mã hoá — toàn quyền)
    locked: bool  # tệp cần mật khẩu mới mở được (đọc `needs_pass` trước khi đăng nhập)


@dataclass
class ToolResult:
    """Kết quả một lần chạy công cụ PDF (dùng chung cho CLI `--json` và giao diện)."""

    tool: str
    input_path: str
    output_path: str  # "" khi không ghi tệp
    written: bool
    pages: int
    input_size: int
    output_size: int = 0
    pages_changed: int = 0
    encrypted: bool = False  # tệp kết quả có mật khẩu / mã hoá
    note: str = ""

    @property
    def saved_bytes(self) -> int:
        return self.input_size - self.output_size

    @property
    def saved_ratio(self) -> float:
        """Tỷ lệ dung lượng giảm được (0..1)."""
        return self.saved_bytes / self.input_size if self.input_size and self.output_size else 0.0

    def to_dict(self) -> dict:
        data = asdict(self)
        data["saved_bytes"] = self.saved_bytes
        data["saved_percent"] = round(self.saved_ratio * 100, 1)
        return data


def format_size(n: int) -> str:
    """Dung lượng dễ đọc kiểu Việt Nam: «850 KB», «1,25 MB»."""
    value = float(max(0, n))
    for unit in ("B", "KB", "MB"):
        if value < 1024 or unit == "MB":
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} B"
    text = f"{value:.0f}" if value >= 100 else f"{value:.1f}" if value >= 10 else f"{value:.2f}"
    return f"{text.replace('.', ',')} {unit}"


# Lưu ý MuPDF 1.28: KHÔNG đọc `doc.needs_pass` sau `doc.authenticate()` — hàm đó thử lại mật khẩu rỗng và làm
# hỏng khoá giải mã, lần lưu sau ghi ra luồng nội dung rác (trang trắng). Các hàm dưới chỉ dùng `is_encrypted`
# (còn khoá) và `metadata["encryption"]` (đã mở khoá / tệp chỉ có mật khẩu chủ).


def encryption_method(doc: fitz.Document) -> str:
    """Tên kiểu mã hoá (vd «Standard V5 R6 256-bit AES»); "" nếu tệp không mã hoá."""
    if doc.is_encrypted:
        return "?"  # chưa đăng nhập: chưa đọc được từ điển /Encrypt
    meta = doc.metadata or {}
    return str(meta.get("encryption") or "")


def is_protected(doc: fitz.Document) -> bool:
    """Tệp có mật khẩu mở hoặc mật khẩu chủ (hạn chế quyền)."""
    return bool(encryption_method(doc))


def is_restricted(doc: fitz.Document) -> bool:
    """Tệp mã hoá đang tắt bớt quyền (in / sao chép / sửa / chú thích…)."""
    return is_protected(doc) and (doc.permissions & ALL_PERMISSIONS) != ALL_PERMISSIONS


def has_signature(doc: fitz.Document) -> bool:
    try:
        return doc.get_sigflags() > 0
    except Exception:
        return False


def open_pdf(path: PathLike, password: Optional[str] = None, need: int = 0) -> OpenedPdf:
    """Mở tệp PDF (đăng nhập bằng `password` nếu cần) → `OpenedPdf(doc, owner, locked)`.

    `need`: các cờ `PDF_PERM_*` công cụ cần. Tệp hạn chế những quyền đó thì phải có mật khẩu chủ.
    """
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp PDF: {p}")
    try:
        doc = fitz.open(str(p))
    except Exception as exc:
        raise PdfToolError(f"Không mở được tệp PDF «{p.name}»: {exc}") from exc
    if not doc.is_pdf:
        doc.close()
        raise PdfToolError(f"Không phải tệp PDF: {p.name}")
    owner = False
    locked = bool(doc.needs_pass)
    if locked:
        rc = doc.authenticate(password) if password else 0
        if not rc:
            doc.close()
            if password:
                raise PermissionError(f"Sai mật khẩu của tệp «{p.name}».")
            raise PermissionError(f"Tệp PDF «{p.name}» được bảo vệ bằng mật khẩu — hãy nhập mật khẩu.")
        owner = bool(rc & 4)
    elif password and encryption_method(doc):
        owner = bool(doc.authenticate(password) & 4)
    elif not is_protected(doc):
        owner = True  # tệp không mã hoá: toàn quyền
    if need and is_protected(doc) and not owner and (doc.permissions & need) != need:
        doc.close()
        raise PermissionError(
            f"Tệp «{p.name}» đã bị hạn chế quyền sửa — hãy nhập mật khẩu chủ (owner) để tiếp tục."
        )
    return OpenedPdf(doc, owner, locked)


def same_file(a: PathLike, b: PathLike) -> bool:
    pa, pb = Path(a).resolve(), Path(b).resolve()
    if os.path.normcase(str(pa)) == os.path.normcase(str(pb)):
        return True
    try:
        return pa.exists() and pb.exists() and os.path.samefile(pa, pb)
    except OSError:
        return False


def default_output(src: PathLike, suffix: str) -> Path:
    """`D:/a/van_ban.pdf` + `_nen` → `D:/a/van_ban_nen.pdf`."""
    p = Path(src).resolve()
    return p.with_name(f"{p.stem}{suffix}.pdf")


def resolve_output(src: PathLike, output: Optional[PathLike], suffix: str) -> Path:
    """Đường dẫn tệp kết quả (mặc định theo hậu tố); từ chối ghi đè tệp nguồn."""
    out = Path(output).resolve() if output else default_output(src, suffix)
    if out.suffix.lower() != ".pdf":
        out = out.with_name(out.name + ".pdf")
    if same_file(src, out):
        raise PdfToolError(f"Tệp kết quả trùng tệp nguồn — hãy chọn tên khác: {out.name}")
    return out


def check_signature(doc: fitz.Document, allow_signed: bool) -> None:
    if not allow_signed and has_signature(doc):
        raise SignedDocumentError(
            "Tệp có chữ ký số: công cụ này ghi lại toàn bộ tệp nên chữ ký số sẽ mất hiệu lực. "
            "Nếu vẫn muốn tiếp tục, hãy xác nhận (dòng lệnh: thêm --force)."
        )


def write_pdf_bytes(data: bytes, path: PathLike) -> Path:
    """Ghi dữ liệu PDF qua tệp tạm rồi đổi tên — không để lại tệp hỏng khi lỗi giữa chừng."""
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.stem}.qtpdfpro-tmp.pdf")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return target
