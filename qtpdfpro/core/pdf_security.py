"""Đặt / gỡ mật khẩu PDF (mã hoá AES-256) và quyền sử dụng.

Không phụ thuộc `PySide6`.

- **Mật khẩu mở** (user): cần để mở tệp. Có thể bỏ trống nếu chỉ muốn hạn chế quyền.
- **Mật khẩu chủ** (owner): toàn quyền, dùng để đổi quyền hoặc gỡ bảo vệ. Bắt buộc khi hạn chế quyền và phải
  khác mật khẩu mở (nếu trùng, ai mở được tệp cũng có toàn quyền → hạn chế vô nghĩa).
- **Quyền**: in, sao chép nội dung, sửa nội dung (gồm sắp xếp trang), chú thích (gồm điền biểu mẫu).
  Quyền hỗ trợ người khiếm thị (`PDF_PERM_ACCESSIBILITY`) luôn bật.

Gỡ bảo vệ / đổi mật khẩu một tệp đang hạn chế quyền cần **mật khẩu chủ**; mật khẩu mở chỉ đủ khi tệp không
hạn chế quyền nào. Lưu ý: hạn chế quyền là quy ước — trình đọc PDF tuân thủ chuẩn sẽ tôn trọng, nhưng không
ngăn được người cố tình dùng phần mềm bẻ khoá; mật khẩu mở AES-256 mới thực sự mã hoá nội dung.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # PyMuPDF

from qtpdfpro.core.page_ops import save_pdf
from qtpdfpro.core.pdf_io import (
    ALL_PERMISSIONS,
    PathLike,
    PdfToolError,
    ToolResult,
    check_signature,
    encryption_method,
    is_protected,
    is_restricted,
    open_pdf,
    resolve_output,
)

PROTECT_SUFFIX = "_bao_ve"
UNLOCK_SUFFIX = "_mo_khoa"

# (khoá, nhãn tiếng Việt, cờ PDF_PERM_*)
PERMISSIONS: List[Tuple[str, str, int]] = [
    ("print", "In tài liệu", fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ),
    ("copy", "Sao chép nội dung", fitz.PDF_PERM_COPY),
    ("modify", "Sửa nội dung, sắp xếp trang", fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_ASSEMBLE),
    ("annotate", "Thêm chú thích, điền biểu mẫu", fitz.PDF_PERM_ANNOTATE | fitz.PDF_PERM_FORM),
]


@dataclass
class ProtectOptions:
    """Mật khẩu & quyền khi đặt bảo vệ."""

    user_password: str = ""  # mật khẩu mở ("" = mở không cần mật khẩu)
    owner_password: str = ""  # mật khẩu chủ ("" = dùng mật khẩu mở khi không hạn chế quyền)
    allow_print: bool = True
    allow_copy: bool = True
    allow_modify: bool = True
    allow_annotate: bool = True

    @property
    def restricted(self) -> bool:
        return not (self.allow_print and self.allow_copy and self.allow_modify and self.allow_annotate)

    def permission_flags(self) -> int:
        allowed = {"print": self.allow_print, "copy": self.allow_copy, "modify": self.allow_modify,
                   "annotate": self.allow_annotate}
        flags = fitz.PDF_PERM_ACCESSIBILITY
        for key, _label, bits in PERMISSIONS:
            if allowed[key]:
                flags |= bits
        return flags


@dataclass
class SecurityInfo:
    """Tình trạng bảo vệ của một tệp PDF (đọc được khi chưa có mật khẩu)."""

    needs_password: bool
    encrypted: bool
    method: str
    permissions: dict  # khoá → được phép

    def to_dict(self) -> dict:
        return {"needs_password": self.needs_password, "encrypted": self.encrypted, "method": self.method,
                "permissions": self.permissions}


def permissions_dict(flags: int) -> dict:
    return {key: (flags & bits) == bits for key, _label, bits in PERMISSIONS}


def security_info(path: PathLike) -> SecurityInfo:
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp PDF: {p}")
    with fitz.open(str(p)) as doc:
        locked = bool(doc.needs_pass)
        method = encryption_method(doc)
        if locked:
            perms: dict = {}  # chưa có mật khẩu: chưa đọc được quyền
        elif is_protected(doc):
            perms = permissions_dict(doc.permissions)
        else:
            perms = permissions_dict(ALL_PERMISSIONS)
        return SecurityInfo(locked, bool(method or locked), method, perms)


def _validate(opts: ProtectOptions) -> Tuple[str, str]:
    user = opts.user_password or ""
    owner = opts.owner_password or ""
    if not user and not owner:
        raise PdfToolError("Hãy nhập mật khẩu mở hoặc mật khẩu chủ.")
    if opts.restricted:
        if not owner:
            raise PdfToolError("Hạn chế quyền cần có mật khẩu chủ (owner) — người giữ mật khẩu chủ mới đổi được quyền.")
        if owner == user:
            raise PdfToolError("Mật khẩu chủ phải khác mật khẩu mở, nếu không ai mở được tệp cũng có toàn quyền.")
    if not owner:
        owner = user
    return user, owner


def _require_full_access(doc: fitz.Document, owner: bool, name: str) -> None:
    """Gỡ / đổi bảo vệ: cần mật khẩu chủ nếu tệp đang hạn chế quyền."""
    if is_restricted(doc) and not owner:
        raise PermissionError(
            f"Tệp «{name}» đang hạn chế quyền — cần mật khẩu chủ (owner) để gỡ hoặc đổi bảo vệ; "
            "mật khẩu mở chỉ cho phép đọc."
        )


def protect_pdf(
    src: PathLike,
    output: Optional[PathLike] = None,
    options: Optional[ProtectOptions] = None,
    password: Optional[str] = None,
    allow_signed: bool = False,
) -> ToolResult:
    """Đặt mật khẩu AES-256 cho `src` → `output` (mặc định `<tên>_bao_ve.pdf`).

    `password`: mật khẩu hiện tại nếu tệp nguồn đã được bảo vệ (đổi mật khẩu cần mật khẩu chủ khi tệp hạn chế quyền).
    """
    opts = options or ProtectOptions()
    user, owner_pw = _validate(opts)
    src_path = Path(src).resolve()
    out = resolve_output(src_path, output, PROTECT_SUFFIX)
    doc, owner, _locked = open_pdf(src_path, password)
    try:
        _require_full_access(doc, owner, src_path.name)
        check_signature(doc, allow_signed)
        pages = doc.page_count
        saved = save_pdf(
            doc, out, garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw=user, owner_pw=owner_pw, permissions=opts.permission_flags(),
        )
    finally:
        doc.close()
    res = ToolResult("protect", str(src_path), str(saved), True, pages, src_path.stat().st_size,
                     saved.stat().st_size, encrypted=True)
    parts = ["AES-256", "có mật khẩu mở" if user else "mở không cần mật khẩu"]
    denied = [label.lower() for key, label, _bits in PERMISSIONS if not getattr(opts, f"allow_{key}")]
    parts.append("cấm " + ", ".join(denied) if denied else "đủ quyền")
    res.note = " · ".join(parts)
    return res


def unlock_pdf(src: PathLike, output: Optional[PathLike] = None, password: str = "") -> ToolResult:
    """Gỡ mật khẩu & hạn chế quyền của `src` → `output` (mặc định `<tên>_mo_khoa.pdf`) khi biết mật khẩu."""
    src_path = Path(src).resolve()
    out = resolve_output(src_path, output, UNLOCK_SUFFIX)
    doc, owner, locked = open_pdf(src_path, password or None)
    try:
        if not is_protected(doc):
            raise PdfToolError(f"Tệp «{src_path.name}» không có mật khẩu hay hạn chế quyền nào.")
        if password and not owner and not locked:
            raise PermissionError(f"Sai mật khẩu chủ của tệp «{src_path.name}».")
        _require_full_access(doc, owner, src_path.name)
        pages = doc.page_count
        saved = save_pdf(doc, out, garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
    finally:
        doc.close()
    return ToolResult("unlock", str(src_path), str(saved), True, pages, src_path.stat().st_size,
                      saved.stat().st_size, encrypted=False, note="Đã gỡ mật khẩu và mọi hạn chế quyền")
