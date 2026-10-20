"""Đăng ký QT PDF Pro với Windows làm trình mở tệp `.pdf` (theo người dùng, HKCU — không cần quyền quản trị).

Windows 10/11 không cho ứng dụng tự đặt mình làm mặc định: lựa chọn của người dùng nằm ở
`...\\FileExts\\.pdf\\UserChoice` (có mã băm chống ghi, Windows 11 còn có driver UCPD bảo vệ riêng `.pdf`).
Cách được phép và module này làm:
1. `register_pdf_handler()` ghi ProgID `QTPdfPro.PDF`, `Applications\\QTPdfPro.exe`, `.pdf\\OpenWithProgids`,
   `Capabilities\\FileAssociations` + `RegisteredApplications` (ứng dụng hiện trong «Open with» và «Default apps»).
   Bộ cài `installer.iss` ghi đúng các khoá này (`registry_entries()` là nguồn chuẩn — test đối chiếu).
2. `open_default_apps_settings()` mở `ms-settings:defaultapps?registeredAppUser=QTPdfPro` — trang cài đặt của
   chính QT PDF Pro, người dùng bấm «Đặt mặc định» một lần.
3. `is_default_pdf_app()` đọc `UserChoice` / `UserChoiceLatest` để biết đã là mặc định chưa.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

PROG_ID = "QTPdfPro.PDF"
APP_EXE_NAME = "QTPdfPro.exe"
REGISTERED_APP_NAME = "QTPdfPro"  # tên giá trị trong HKCU\Software\RegisteredApplications
CAPABILITIES_KEY = r"Software\QTPdfPro\Capabilities"
APP_DISPLAY_NAME = "QT PDF Pro"
APP_DESCRIPTION = "Đọc PDF tốc độ cao, chuyển PDF sang Word chuẩn xác, in, chỉnh sửa và công cụ văn phòng."
FILE_TYPE_NAME = "Tài liệu PDF (QT PDF Pro)"
DEFAULT_APPS_URI = f"ms-settings:defaultapps?registeredAppUser={REGISTERED_APP_NAME}"
USER_CHOICE_KEYS = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoiceLatest",
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoice",
)

_SHCNE_ASSOCCHANGED = 0x08000000
_SHCNF_IDLIST = 0x0000


@dataclass(frozen=True)
class RegValue:
    """Một giá trị chuỗi dưới HKCU. `name=""` = giá trị mặc định của khoá."""

    subkey: str
    name: str
    value: str


def registry_entries(exe_path: Path | str) -> List[RegValue]:
    """Toàn bộ giá trị HKCU cần ghi để QT PDF Pro mở được `.pdf` và hiện trong «Default apps»."""
    exe = str(exe_path)
    command = f'"{exe}" "%1"'
    icon = f'"{exe}",0'
    prog = rf"Software\Classes\{PROG_ID}"
    app = rf"Software\Classes\Applications\{APP_EXE_NAME}"
    return [
        RegValue(prog, "", FILE_TYPE_NAME),
        RegValue(prog, "FriendlyTypeName", FILE_TYPE_NAME),
        RegValue(rf"{prog}\DefaultIcon", "", icon),
        RegValue(rf"{prog}\shell\open", "FriendlyAppName", APP_DISPLAY_NAME),
        RegValue(rf"{prog}\shell\open\command", "", command),
        RegValue(r"Software\Classes\.pdf\OpenWithProgids", PROG_ID, ""),
        RegValue(app, "FriendlyAppName", APP_DISPLAY_NAME),
        RegValue(rf"{app}\DefaultIcon", "", icon),
        RegValue(rf"{app}\SupportedTypes", ".pdf", ""),
        RegValue(rf"{app}\shell\open\command", "", command),
        RegValue(CAPABILITIES_KEY, "ApplicationName", APP_DISPLAY_NAME),
        RegValue(CAPABILITIES_KEY, "ApplicationDescription", APP_DESCRIPTION),
        RegValue(CAPABILITIES_KEY, "ApplicationIcon", icon),
        RegValue(rf"{CAPABILITIES_KEY}\FileAssociations", ".pdf", PROG_ID),
        RegValue(r"Software\RegisteredApplications", REGISTERED_APP_NAME, CAPABILITIES_KEY),
        RegValue(rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{APP_EXE_NAME}", "", exe),
    ]


def _winreg():
    if sys.platform != "win32":
        raise OSError("Đăng ký liên kết tệp chỉ hỗ trợ Windows.")
    import winreg

    return winreg


def _join(prefix: str, subkey: str) -> str:
    return f"{prefix}\\{subkey}" if prefix else subkey


def write_entries(entries: List[RegValue], prefix: str = "") -> None:
    """Ghi các giá trị vào HKCU (`prefix` chỉ dùng khi kiểm thử: ghi dưới một khoá tạm)."""
    winreg = _winreg()
    for e in entries:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _join(prefix, e.subkey), 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, e.name, 0, winreg.REG_SZ, e.value)


def read_value(subkey: str, name: str = "", prefix: str = "") -> Optional[str]:
    """Đọc một giá trị chuỗi dưới HKCU; None nếu không có."""
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _join(prefix, subkey)) as key:
            value, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return str(value)


def notify_shell() -> None:
    """Báo Explorer làm mới bảng liên kết tệp (SHChangeNotify SHCNE_ASSOCCHANGED)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(_SHCNE_ASSOCCHANGED, _SHCNF_IDLIST, None, None)
    except (AttributeError, OSError):
        pass


def register_pdf_handler(exe_path: Path | str, prefix: str = "") -> List[RegValue]:
    """Đăng ký `exe_path` làm trình mở `.pdf` khả dụng (không đổi lựa chọn mặc định của người dùng)."""
    entries = registry_entries(Path(exe_path))
    write_entries(entries, prefix)
    if not prefix:
        notify_shell()
    return entries


def registered_exe(prefix: str = "") -> Optional[str]:
    """Đường dẫn .exe đang đăng ký trong `App Paths` (None nếu chưa đăng ký)."""
    return read_value(rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{APP_EXE_NAME}", "", prefix)


def is_registered(exe_path: Path | str | None = None, prefix: str = "") -> bool:
    """Đã có ProgID + RegisteredApplications (và, nếu cho `exe_path`, trỏ đúng tệp .exe này)."""
    if read_value(r"Software\RegisteredApplications", REGISTERED_APP_NAME, prefix) != CAPABILITIES_KEY:
        return False
    command = read_value(rf"Software\Classes\{PROG_ID}\shell\open\command", "", prefix)
    if command is None:
        return False
    if exe_path is None:
        return True
    return os.path.normcase(command) == os.path.normcase(f'"{exe_path}" "%1"')


def current_default_progid(prefix: str = "") -> Optional[str]:
    """ProgID người dùng đã chọn cho `.pdf` (None = chưa chọn / để Windows quyết định)."""
    for key in USER_CHOICE_KEYS:
        value = read_value(key, "ProgId", prefix)
        if value:
            return value
    return None


def is_default_pdf_app(prefix: str = "") -> bool:
    try:
        return (current_default_progid(prefix) or "").lower() == PROG_ID.lower()
    except OSError:
        return False


def open_default_apps_settings() -> bool:
    """Mở trang «Default apps» của QT PDF Pro trong Cài đặt Windows (Windows 10 mở trang chung)."""
    if sys.platform != "win32":
        return False
    try:
        os.startfile(DEFAULT_APPS_URI)  # type: ignore[attr-defined]
        return True
    except OSError:
        try:
            os.startfile("ms-settings:defaultapps")  # type: ignore[attr-defined]
            return True
        except OSError:
            return False
