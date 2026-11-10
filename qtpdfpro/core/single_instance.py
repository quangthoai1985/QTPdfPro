"""Phần không phụ thuộc Qt của cơ chế «một cửa sổ duy nhất» (mục V1).

Mở nhiều PDF cùng lúc từ Explorer, Windows chạy MỘT tiến trình cho MỖI tệp (lệnh `"QTPdfPro.exe" "%1"`).
Tiến trình đầu tiên giành «quyền chính» (mutex có tên của Windows) và nghe trên một kênh cục bộ
(`QLocalServer`, xem `ui/single_instance.py`); các tiến trình sau gửi danh sách đường dẫn tới kênh đó rồi
thoát, cửa sổ đang chạy mở mỗi tệp thành một tab và tự đưa lên trước — giống Foxit Reader.

Lưu ý: trên Windows `QLocalServer.listen` KHÔNG báo lỗi khi tên kênh đã có người nghe (named pipe cho phép
nhiều phiên bản cùng tên) → không dùng được để bầu tiến trình chính; phải dùng mutex.
"""

from __future__ import annotations

import ctypes
import getpass
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from qtpdfpro.core.settings import get_data_dir

PROTOCOL_VERSION = 1
ACK = b"ok\n"
MAX_MESSAGE_BYTES = 1 << 20  # 1 MB — đủ cho hàng nghìn đường dẫn

_ERROR_ALREADY_EXISTS = 183
_ASFW_ANY = -1


def channel_name() -> str:
    """Tên kênh / mutex riêng theo người dùng VÀ thư mục dữ liệu.

    Gồm thư mục dữ liệu để bản chạy thử (`QT_PDF_PRO_DATA` trỏ thư mục tạm — pytest, Agent) không gửi tệp
    sang ứng dụng thật người dùng đang mở và ngược lại.
    """
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - không có biến môi trường người dùng
        user = "user"
    data_dir = os.path.normcase(str(get_data_dir().resolve()))
    digest = hashlib.sha256(f"{user}|{data_dir}".encode("utf-8")).hexdigest()[:16]
    return f"QTPdfPro.Instance.{digest}"


def normalize_paths(files: Iterable[str], cwd: Optional[str | Path] = None) -> List[str]:
    """Đường dẫn tuyệt đối (tiến trình phụ có thể khác thư mục làm việc với cửa sổ đang chạy), bỏ trùng."""
    base = Path(cwd) if cwd is not None else Path.cwd()
    out: List[str] = []
    seen = set()
    for f in files:
        if not f:
            continue
        p = Path(f)
        if not p.is_absolute():
            p = base / p
        try:
            p = p.resolve()
        except OSError:
            p = Path(os.path.abspath(p))
        key = os.path.normcase(str(p))
        if key in seen:
            continue
        seen.add(key)
        out.append(str(p))
    return out


def encode_message(files: Iterable[str]) -> bytes:
    """Một dòng JSON kết thúc bằng `\\n`: `{"v": 1, "files": [...]}` (danh sách rỗng = chỉ đưa cửa sổ lên)."""
    payload = {"v": PROTOCOL_VERSION, "files": list(files)}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"


def decode_message(data: bytes) -> Optional[List[str]]:
    """Danh sách đường dẫn, hoặc `None` nếu thông điệp hỏng / sai định dạng."""
    try:
        payload = json.loads(data.decode("utf-8").strip() or "null")
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    files = payload.get("files")
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        return None
    return [f for f in files if f]


class PrimaryLock:
    """Mutex có tên của Windows: tiến trình giữ được là tiến trình chính.

    Windows tự giải phóng khi tiến trình thoát (kể cả khi bị treo/đóng đột ngột). Ngoài Windows luôn coi là
    tiến trình chính (ứng dụng chỉ phát hành cho Windows; ở đó `QLocalServer.listen` tự báo trùng tên).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._handle = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        if self._handle is not None:
            return True
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            handle = kernel32.CreateMutexW(None, False, f"Local\\{self.name}")
            err = ctypes.get_last_error()
        except (AttributeError, OSError):
            return True  # không tạo được mutex → cư xử như trước (mỗi tiến trình một cửa sổ)
        if not handle:
            return True
        if err == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None or sys.platform != "win32":
            self._handle = None
            return
        try:
            kernel32 = ctypes.WinDLL("kernel32")
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle(self._handle)
        except (AttributeError, OSError):
            pass
        self._handle = None


def allow_foreground_for_any_process() -> None:
    """Tiến trình phụ vừa được người dùng mở (nên có quyền tiền cảnh) nhường quyền đó cho cửa sổ đang chạy.

    Không có bước này, `SetForegroundWindow` của cửa sổ chính bị Windows từ chối → chỉ nhấp nháy trên thanh tác vụ.
    """
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(_ASFW_ANY)
    except (AttributeError, OSError):
        pass
