"""Tự cập nhật ngầm QT PDF Pro (không phụ thuộc PySide6) — điều phối trên nền `core/update_check.py`.

Khi tự kiểm tra lúc khởi động thấy bản mới (và người dùng không «Bỏ qua bản này»):
1. `auto_install_blocker()` xem bản đang chạy có tự thay được không: phải là bản đóng gói `QTPdfPro.exe`
   (cài bằng `QTPdfPro_Setup.exe` vào `%LOCALAPPDATA%\\Programs\\QT PDF Pro` — không cần quyền quản trị),
   thư mục cài ghi được và bản phát hành có `QTPdfPro_Update.zip`.
2. `download_and_prepare()` tải ngầm `QTPdfPro_Update.zip` về `%LOCALAPPDATA%\\QT PDF Pro\\updates\\`
   (kiểm SHA-256), giải nén vào `updates\\staging\\` và sinh script `apply_update.ps1`.
3. Ứng dụng giữ `InstallPlan`; khi người dùng bấm «Khởi động lại» hoặc khi thoát, `update_check.launch_install()`
   chạy script PowerShell tách rời: đợi tiến trình thoát hẳn → hoán đổi thư mục cài (giữ `.old` dự phòng)
   → mở lại ứng dụng (chỉ khi người dùng bấm «Khởi động lại»).

Mọi hàm mạng / tệp gọi qua `uc.` để bài test thay thế được.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from qtpdfpro.core import update_check as uc


@dataclass
class PreparedUpdate:
    """Bản mới đã tải & giải nén xong, chờ thay vào thư mục cài khi ứng dụng thoát."""

    release: uc.ReleaseInfo
    zip_path: Path
    plan: uc.InstallPlan

    @property
    def version(self) -> str:
        return self.release.version


def auto_install_blocker(
    release: uc.ReleaseInfo, install_dir: Optional[Path] = None, frozen: Optional[bool] = None
) -> str:
    """Lý do không tự tải & cài ngầm được (chuỗi rỗng = được). `install_dir=None` → thư mục của bản đang chạy."""
    frozen = uc.is_frozen() if frozen is None else frozen
    install_dir = install_dir if install_dir is not None else uc.current_install_dir()
    if not frozen or install_dir is None:
        return "Đang chạy từ mã nguồn — chỉ báo có bản mới."
    if release.asset is None:
        return f"Bản v{release.version} chưa có tệp {uc.UPDATE_ASSET_NAME}."
    if not uc.can_write_install_dir(Path(install_dir)):
        return f"Không ghi được vào thư mục cài đặt «{install_dir}»."
    return ""


def download_and_prepare(
    release: uc.ReleaseInfo,
    install_dir: Path,
    should_cancel: Optional[uc.CancelCheck] = None,
    progress_cb: Optional[uc.ProgressCallback] = None,
) -> PreparedUpdate:
    """Tải `release.asset` (kiểm SHA-256) rồi giải nén + sinh script; lỗi ném `UpdateError`/`UpdateCancelled`."""
    if release.asset is None:
        raise uc.UpdateError(f"Bản v{release.version} chưa có tệp {uc.UPDATE_ASSET_NAME}.")
    zip_path = uc.download_asset(release.asset, progress_cb=progress_cb, should_cancel=should_cancel)
    plan = uc.prepare_install(
        zip_path, release.version, Path(install_dir), should_cancel=should_cancel, progress_cb=progress_cb
    )
    return PreparedUpdate(release=release, zip_path=zip_path, plan=plan)
