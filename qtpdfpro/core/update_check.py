"""Kiểm tra & cài bản cập nhật QT PDF Pro từ GitHub Release (mục V4 — không phụ thuộc PySide6).

Luồng:
1. `check_for_update()` đọc `https://api.github.com/repos/<kho>/releases/latest`, so thẻ (`v1.0.0`) với
   `__version__` theo SemVer (bỏ qua bản nháp / pre-release) và chọn tệp `QTPdfPro_Update.zip` (bản phát hành
   trước v1.0.0 dùng tên `QTPdfPro-v<x.y.z>-win64.zip` — vẫn nhận).
2. `download_asset()` tải vào `%LOCALAPPDATA%\\QT PDF Pro\\updates\\` (có tiến trình, huỷ được), kiểm kích thước
   và SHA-256 (trường `digest` của asset).
3. Bản đóng gói onedir (`sys.frozen`): `prepare_install()` giải nén vào thư mục tạm + sinh script PowerShell;
   `launch_install()` chạy script khi ứng dụng thoát — script đợi tiến trình thoát, đổi thư mục cài thành
   `.old` (bản dự phòng, khôi phục nếu lỗi), đưa bản mới vào, chép lại tệp gỡ cài đặt `unins*` của bộ cài
   Inno Setup, cập nhật `DisplayVersion` trong «Apps & features» rồi mở lại ứng dụng. Lần khởi động sau
   `cleanup_previous_update()` xoá `.old`. Chạy từ mã nguồn thì chỉ báo có bản mới.

Điều phối tự tải ngầm nằm ở `core/updater.py`. Chỉ nhận https và host GitHub (kể cả từng bước chuyển hướng).
Biến môi trường `QT_PDF_PRO_UPDATE_API` (chỉ dùng khi kiểm thử) thay địa chỉ API và cho phép thêm
máy cục bộ `127.0.0.1` / `localhost`.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, List, NamedTuple, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from qtpdfpro import __app_name__, __github_repo__, __version__
from qtpdfpro.core.settings import get_data_dir

API_HOSTS = frozenset({"api.github.com"})
DOWNLOAD_HOSTS = frozenset({"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
API_OVERRIDE_ENV = "QT_PDF_PRO_UPDATE_API"

CHECK_INTERVAL = timedelta(days=1)
API_TIMEOUT = 10.0
DOWNLOAD_TIMEOUT = 30.0
MAX_API_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 1024 * 1024 * 1024
CHUNK_SIZE = 256 * 1024
USER_AGENT = f"QTPdfPro/{__version__} (+https://github.com/{__github_repo__})"

APP_EXE_NAME = "QTPdfPro.exe"
UPDATE_ASSET_NAME = "QTPdfPro_Update.zip"  # tệp cập nhật ngầm đính kèm mỗi bản phát hành (từ v1.0.0)
SETUP_ASSET_NAME = "QTPdfPro_Setup.exe"  # bộ cài Inno Setup (installer.iss) — người dùng mới tải tay
UPDATES_ROOT_NAME = "QT PDF Pro"  # %LOCALAPPDATA%\QT PDF Pro\updates
# AppId của bộ cài (installer.iss) — khoá gỡ cài đặt HKCU\...\Uninstall\<AppId>_is1; đổi thì phải đổi cả hai nơi
INNO_APP_ID = "{A23779E2-FE6A-4983-9D0C-82D2465C4D8B}"
UPDATE_SCRIPT_NAME = "apply_update.ps1"
UPDATE_LOG_NAME = "update.log"
PENDING_MARKER_NAME = "pending_update.json"
STAGING_DIR_NAME = "staging"

ProgressCallback = Callable[[int, int], None]
CancelCheck = Callable[[], bool]


class UpdateError(Exception):
    """Lỗi kiểm tra / tải / cài bản cập nhật (thông điệp tiếng Việt hiển thị được cho người dùng)."""


class UpdateCancelled(UpdateError):
    """Người dùng huỷ giữa chừng."""


class ReleaseNotFound(UpdateError):
    """Kho chưa có bản phát hành chính thức nào (API trả 404)."""


class InstallDirNotWritable(UpdateError):
    """Thư mục cài đặt không ghi được (ví dụ Program Files) — người dùng phải tự chép bản mới."""


# ─── Phiên bản SemVer ──────────────────────────────────────────────────────

_SEMVER_RE = re.compile(r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


class SemVer(NamedTuple):
    major: int
    minor: int
    patch: int
    prerelease: str = ""

    @property
    def core(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def text(self) -> str:
        return f"{self.core}-{self.prerelease}" if self.prerelease else self.core

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    def sort_key(self) -> tuple:
        # SemVer §11: bản pre-release đứng trước bản chính thức cùng lõi; định danh số so theo giá trị số
        if not self.prerelease:
            return (self.major, self.minor, self.patch, (1,))
        idents = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in self.prerelease.split("."))
        return (self.major, self.minor, self.patch, (0, idents))


def parse_version(text: str) -> Optional[SemVer]:
    """`'v0.5.0'`, `'0.5.0-beta.1'` → `SemVer`; chuỗi không đúng SemVer → None."""
    m = _SEMVER_RE.match((text or "").strip())
    if not m:
        return None
    return SemVer(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or "")


def is_newer(candidate: str, current: str = __version__) -> bool:
    """`candidate` mới hơn `current` theo thứ tự SemVer (chuỗi lỗi → False)."""
    a, b = parse_version(candidate), parse_version(current)
    if a is None or b is None:
        return False
    return a.sort_key() > b.sort_key()


# ─── Mô hình dữ liệu ───────────────────────────────────────────────────────


@dataclass
class ReleaseAsset:
    """Tệp đính kèm bản phát hành dùng để cập nhật."""

    name: str
    url: str
    size: int = 0
    sha256: str = ""  # hex chữ thường, lấy từ trường `digest` = "sha256:…" (rỗng nếu API không trả)
    content_type: str = ""


@dataclass
class ReleaseInfo:
    """Bản phát hành mới nhất trên GitHub."""

    tag: str
    version: str
    name: str = ""
    notes: str = ""  # trường `body` (Markdown)
    html_url: str = ""
    published_at: str = ""
    draft: bool = False
    prerelease: bool = False
    asset: Optional[ReleaseAsset] = None

    @property
    def title(self) -> str:
        return self.name or f"{__app_name__} v{self.version}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UpdateCheckResult:
    current_version: str
    latest: Optional[ReleaseInfo]
    update_available: bool
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "current_version": self.current_version,
            "update_available": self.update_available,
            "message": self.message,
            "latest": self.latest.to_dict() if self.latest else None,
        }


@dataclass
class InstallPlan:
    """Mọi thứ script cập nhật cần: thư mục bản mới đã giải nén → thay vào thư mục cài."""

    version: str
    zip_path: Path
    source_dir: Path
    target_dir: Path
    script_path: Path
    log_path: Path
    exe_name: str = APP_EXE_NAME


# ─── Phân tích phản hồi API ────────────────────────────────────────────────


def expected_asset_name(version: str) -> str:
    """Tên tệp theo phiên bản của các bản phát hành trước v1.0.0 (bản v0.5.0 chỉ nhận tên này).

    Từ v1.0.0 tệp cập nhật chính là `UPDATE_ASSET_NAME`; bản phát hành vẫn đính kèm thêm tệp tên cũ để
    người dùng v0.5.0 tự cập nhật được (CLAUDE.md mục 6).
    """
    return f"QTPdfPro-v{version}-win64.zip"


_SAFE_ASSET_RE = re.compile(r"^(?:QTPdfPro_Update|QTPdfPro-v[0-9A-Za-z.+-]+-win64)\.zip$", re.IGNORECASE)


def select_asset(assets: Any, version: str) -> Optional[ReleaseAsset]:
    """Chọn tệp cập nhật trong danh sách asset của API: ưu tiên `QTPdfPro_Update.zip`, sau đó tên cũ
    `QTPdfPro-v<version>-win64.zip`."""
    items = [item for item in (assets if isinstance(assets, list) else []) if isinstance(item, dict)]
    for want in (UPDATE_ASSET_NAME.lower(), expected_asset_name(version).lower()):
        found = _asset_from_item(next((i for i in items if str(i.get("name") or "").lower() == want), None))
        if found is not None:
            return found
    return None


def _asset_from_item(item: Optional[dict]) -> Optional[ReleaseAsset]:
    url = str(item.get("browser_download_url") or "").strip() if item is not None else ""
    if not url:
        return None
    algo, _, value = str(item.get("digest") or "").partition(":")
    sha = value.lower() if algo.lower() == "sha256" and re.fullmatch(r"[0-9a-fA-F]{64}", value) else ""
    try:
        size = max(0, int(item.get("size") or 0))
    except (TypeError, ValueError):
        size = 0
    return ReleaseAsset(
        name=str(item["name"]),
        url=url,
        size=size,
        sha256=sha,
        content_type=str(item.get("content_type") or ""),
    )


def parse_release(data: dict) -> ReleaseInfo:
    tag = str(data.get("tag_name") or "").strip()
    ver = parse_version(tag)
    if ver is None:
        raise UpdateError(f"Thẻ phiên bản trên GitHub không đúng SemVer: «{tag}».")
    return ReleaseInfo(
        tag=tag,
        version=ver.text,
        name=str(data.get("name") or "").strip(),
        notes=str(data.get("body") or ""),
        html_url=str(data.get("html_url") or f"https://github.com/{__github_repo__}/releases/tag/{tag}"),
        published_at=str(data.get("published_at") or ""),
        draft=bool(data.get("draft")),
        prerelease=bool(data.get("prerelease")) or ver.is_prerelease,
        asset=select_asset(data.get("assets"), ver.text),
    )


# ─── Mạng: chỉ https + host GitHub ─────────────────────────────────────────


def _loopback_allowed() -> bool:
    return bool(os.environ.get(API_OVERRIDE_ENV, "").strip())


def validate_url(url: str, allowed_hosts: frozenset = DOWNLOAD_HOSTS) -> None:
    """Từ chối mọi địa chỉ không phải https tới host GitHub (ngoại lệ máy cục bộ khi kiểm thử)."""
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if parts.scheme == "https" and host in allowed_hosts:
        return
    if _loopback_allowed() and parts.scheme in ("http", "https") and host in LOOPBACK_HOSTS:
        return
    raise UpdateError(f"Từ chối kết nối tới địa chỉ không tin cậy: {url or '(trống)'}")


class _GuardedRedirect(HTTPRedirectHandler):
    """Kiểm từng bước chuyển hướng (github.com → release-assets.githubusercontent.com)."""

    def __init__(self, allowed_hosts: frozenset) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001 - API urllib
        validate_url(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _urlopen(request: Request, timeout: float, allowed_hosts: frozenset):
    """Mở URL qua bộ chuyển hướng có kiểm host. Bài test thay hàm này để không gọi mạng thật."""
    return build_opener(_GuardedRedirect(allowed_hosts)).open(request, timeout=timeout)


def _open(url: str, allowed_hosts: frozenset, timeout: float, accept: str):
    validate_url(url, allowed_hosts)
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if "github" in accept:
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    try:
        resp = _urlopen(Request(url, headers=headers), timeout, allowed_hosts)
    except UpdateError:
        raise
    except HTTPError as exc:
        if exc.code == 404:
            raise ReleaseNotFound("Kho chưa có bản phát hành chính thức nào.") from exc
        if exc.code in (403, 429):
            raise UpdateError("GitHub đang tạm giới hạn số lần truy vấn — hãy thử lại sau ít phút.") from exc
        raise UpdateError(f"Máy chủ GitHub trả lỗi HTTP {exc.code}.") from exc
    except (URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise UpdateError(f"Không kết nối được tới GitHub ({reason}). Kiểm tra mạng rồi thử lại.") from exc
    final_url = resp.geturl() if hasattr(resp, "geturl") else url
    try:
        validate_url(final_url, allowed_hosts)
    except UpdateError:
        resp.close()
        raise
    return resp


def release_api_url(repo: str = __github_repo__) -> str:
    override = os.environ.get(API_OVERRIDE_ENV, "").strip()
    return override or f"https://api.github.com/repos/{repo}/releases/latest"


def fetch_latest_release(repo: str = __github_repo__, timeout: float = API_TIMEOUT) -> Optional[ReleaseInfo]:
    """Bản phát hành mới nhất (GitHub đã loại bản nháp / pre-release); None nếu kho chưa phát hành."""
    try:
        resp = _open(release_api_url(repo), API_HOSTS, timeout, "application/vnd.github+json")
    except ReleaseNotFound:
        return None
    try:
        raw = resp.read(MAX_API_BYTES + 1)
    finally:
        resp.close()
    if len(raw) > MAX_API_BYTES:
        raise UpdateError("Phản hồi của GitHub quá lớn.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UpdateError("Phản hồi của GitHub không phải JSON hợp lệ.") from exc
    if not isinstance(data, dict):
        raise UpdateError("Phản hồi của GitHub không đúng định dạng.")
    return parse_release(data)


def check_for_update(
    current_version: str = __version__, repo: str = __github_repo__, timeout: float = API_TIMEOUT
) -> UpdateCheckResult:
    """Hỏi GitHub và so phiên bản; lỗi mạng ném `UpdateError`."""
    rel = fetch_latest_release(repo, timeout)
    if rel is None:
        return UpdateCheckResult(current_version, None, False, "Kho chưa có bản phát hành chính thức nào.")
    if rel.draft or rel.prerelease:
        return UpdateCheckResult(current_version, rel, False, f"Bản v{rel.version} là bản thử nghiệm — bỏ qua.")
    if is_newer(rel.version, current_version):
        return UpdateCheckResult(current_version, rel, True, f"Đã có bản v{rel.version}.")
    return UpdateCheckResult(current_version, rel, False, f"Bạn đang dùng bản mới nhất (v{current_version}).")


# ─── Nhịp tự kiểm tra ──────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def should_auto_check(last_check: str, now: Optional[datetime] = None, interval: timedelta = CHECK_INTERVAL) -> bool:
    """Tối đa 1 lần / `interval` (mặc định 1 ngày) tính từ lần kiểm tra thành công gần nhất."""
    if not last_check:
        return True
    try:
        last = datetime.fromisoformat(last_check)
    except ValueError:
        return True
    now = now or datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last > now + timedelta(minutes=5):  # đồng hồ máy bị chỉnh lùi
        return True
    return now - last >= interval


# ─── Tải về ────────────────────────────────────────────────────────────────


def updates_dir() -> Path:
    """`%LOCALAPPDATA%\\QT PDF Pro\\updates` — ngoài thư mục cài `%LOCALAPPDATA%\\Programs\\QT PDF Pro` để script
    hoán đổi được cả thư mục cài. Khi đặt `QT_PDF_PRO_DATA` (kiểm thử) thì nằm trong thư mục dữ liệu đó."""
    if os.environ.get("QT_PDF_PRO_DATA", "").strip():
        path = get_data_dir() / "updates"
    else:
        local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = Path(local_app_data) / UPDATES_ROOT_NAME / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_size(num_bytes: int) -> str:
    """`129587401` → `'123,6 MB'` (dấu phẩy thập phân kiểu Việt Nam)."""
    if num_bytes >= 1024 * 1024:
        text = f"{num_bytes / (1024 * 1024):.1f} MB"
    else:
        text = f"{max(0, num_bytes) / 1024:.0f} KB"
    return text.replace(".", ",")


def download_asset(
    asset: ReleaseAsset,
    dest_dir: Optional[Path] = None,
    progress_cb: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCheck] = None,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> Path:
    """Tải `asset` về `dest_dir` (mặc định `<dữ liệu>/updates/`), kiểm kích thước + SHA-256.

    Ghi vào `<tên>.part` rồi mới đổi tên — lỗi, sai mã băm hoặc huỷ thì xoá tệp dở.
    """
    if not _SAFE_ASSET_RE.fullmatch(asset.name or ""):
        raise UpdateError(f"Tên tệp cập nhật không hợp lệ: «{asset.name}».")
    if asset.size > MAX_ASSET_BYTES:
        raise UpdateError("Tệp cập nhật lớn bất thường — từ chối tải.")
    folder = Path(dest_dir) if dest_dir else updates_dir()
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / asset.name
    part = folder / f"{asset.name}.part"

    resp = _open(asset.url, DOWNLOAD_HOSTS, timeout, "application/octet-stream")
    limit = asset.size or MAX_ASSET_BYTES
    total = asset.size
    if not total:
        try:
            total = int(resp.headers.get("Content-Length") or 0)
        except (AttributeError, TypeError, ValueError):
            total = 0
    hasher = hashlib.sha256()
    done = 0
    ok = False
    try:
        with open(part, "wb") as fh:
            if progress_cb:
                progress_cb(0, total)
            while True:
                if should_cancel is not None and should_cancel():
                    raise UpdateCancelled("Đã huỷ tải bản cập nhật.")
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                done += len(chunk)
                if done > limit:
                    raise UpdateError("Tệp tải về lớn hơn dung lượng GitHub công bố — đã huỷ.")
                fh.write(chunk)
                hasher.update(chunk)
                if progress_cb:
                    progress_cb(done, total)
        if asset.size and done != asset.size:
            raise UpdateError(f"Tệp tải về bị thiếu ({format_size(done)} / {format_size(asset.size)}). Hãy thử lại.")
        if asset.sha256 and hasher.hexdigest() != asset.sha256:
            raise UpdateError("Mã SHA-256 của tệp tải về không khớp với GitHub — tệp hỏng hoặc bị thay đổi, đã xoá.")
        os.replace(part, final)
        ok = True
    finally:
        resp.close()
        if not ok:
            part.unlink(missing_ok=True)
    return final


# ─── Cài bản mới (bản đóng gói onedir) ─────────────────────────────────────


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def current_install_dir() -> Optional[Path]:
    """Thư mục cài của bản PyInstaller onedir (chứa QTPdfPro.exe + `_internal`); None khi chạy từ mã nguồn."""
    if not is_frozen():
        return None
    root = Path(sys.executable).resolve().parent
    return root if (root / "_internal").is_dir() else None


def _dir_writable(path: Path) -> bool:
    try:
        fd, name = tempfile.mkstemp(prefix=".qtpdfpro-", dir=str(path))
    except OSError:
        return False
    os.close(fd)
    try:
        os.unlink(name)
    except OSError:
        pass
    return True


def can_write_install_dir(install_dir: Optional[Path]) -> bool:
    """Ghi được vào thư mục cài và thư mục cha (để đổi tên thành `.old`) hay không."""
    if install_dir is None or not Path(install_dir).is_dir():
        return False
    install_dir = Path(install_dir)
    return _dir_writable(install_dir) and _dir_writable(install_dir.parent)


def find_app_dir(root: Path) -> Optional[Path]:
    """Thư mục chứa `QTPdfPro.exe` + `_internal` (gốc tệp nén hoặc thư mục `QTPdfPro/` bên trong)."""
    candidates = [root] + sorted(p for p in root.iterdir() if p.is_dir())
    for cand in candidates:
        if (cand / APP_EXE_NAME).is_file() and (cand / "_internal").is_dir():
            return cand
    return None


def extract_update(
    zip_path: Path,
    staging_dir: Optional[Path] = None,
    should_cancel: Optional[CancelCheck] = None,
    progress_cb: Optional[ProgressCallback] = None,
) -> Path:
    """Giải nén vào thư mục tạm (chặn đường dẫn thoát ra ngoài) → thư mục ứng dụng mới."""
    staging = Path(staging_dir) if staging_dir else updates_dir() / STAGING_DIR_NAME
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    root = staging.resolve()
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.infolist()
            total = sum(m.file_size for m in members)
            done = 0
            for member in members:
                if should_cancel is not None and should_cancel():
                    raise UpdateCancelled("Đã huỷ giải nén bản cập nhật.")
                target = (root / member.filename.replace("\\", "/")).resolve()
                if not target.is_relative_to(root):
                    raise UpdateError(f"Tệp nén chứa đường dẫn không an toàn: «{member.filename}».")
                zf.extract(member, root)
                done += member.file_size
                if progress_cb:
                    progress_cb(done, total)
    except zipfile.BadZipFile as exc:
        raise UpdateError("Tệp tải về không phải tệp .zip hợp lệ.") from exc
    app_dir = find_app_dir(root)
    if app_dir is None:
        raise UpdateError(f"Tệp nén không chứa {APP_EXE_NAME} và thư mục _internal.")
    return app_dir


_PS_APPLY_UPDATE = r"""param(
    [int]$ProcessId = 0,
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [Parameter(Mandatory = $true)][string]$TargetDir,
    [string]$ExeName = 'QTPdfPro.exe',
    [string]$LogFile = '',
    [string]$Version = '',
    [string]$AppId = '',
    [switch]$NoRestart
)
# Trình cập nhật QT PDF Pro — sinh bởi qtpdfpro/core/update_check.py; `param` phải là câu lệnh đầu tiên.
# Đợi ứng dụng thoát -> đổi thư mục cài thành «.old» (bản dự phòng) -> đưa bản mới vào -> giữ tệp gỡ cài
# đặt của bộ cài -> mở lại ứng dụng. Lỗi giữa chừng thì khôi phục thư mục cũ. Ứng dụng xoá «.old» ở lần
# khởi động sau.
$ErrorActionPreference = 'Stop'

function Write-Log([string]$Text) {
    if ($LogFile) {
        $line = '{0:yyyy-MM-dd HH:mm:ss}  {1}' -f (Get-Date), $Text
        Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    }
}

function Start-App([string]$Dir) {
    if ($NoRestart) { return }
    $exe = Join-Path $Dir $ExeName
    if (Test-Path -LiteralPath $exe) { Start-Process -FilePath $exe -WorkingDirectory $Dir }
}

Write-Log "Bắt đầu cập nhật: $SourceDir -> $TargetDir"

# 1. Đợi tiến trình ứng dụng thoát hẳn (tối đa 120 giây)
if ($ProcessId -gt 0) {
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($proc -and -not $proc.WaitForExit(120000)) {
        Write-Log 'Ứng dụng chưa thoát sau 120 giây — huỷ cập nhật.'
        exit 2
    }
}
Start-Sleep -Milliseconds 800

if (-not (Test-Path -LiteralPath (Join-Path $SourceDir $ExeName))) {
    Write-Log "Bản mới không có $ExeName — huỷ cập nhật, giữ nguyên bản cũ."
    Start-App $TargetDir
    exit 3
}

# 2. Đổi tên thư mục cài hiện tại thành bản dự phòng «.old» (thử lại khi tệp còn bị khoá)
$Backup = "$TargetDir.old"
if (Test-Path -LiteralPath $Backup) {
    Remove-Item -LiteralPath $Backup -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $Backup) { $Backup = '{0}.old-{1:yyyyMMddHHmmss}' -f $TargetDir, (Get-Date) }
}
$renamed = $false
for ($i = 0; $i -lt 30 -and -not $renamed; $i++) {
    try {
        Rename-Item -LiteralPath $TargetDir -NewName (Split-Path -Leaf $Backup)
        $renamed = $true
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $renamed) {
    Write-Log 'Không đổi tên được thư mục cài đặt (tệp đang bị khoá) — giữ nguyên bản cũ.'
    Start-App $TargetDir
    exit 4
}
Write-Log "Đã chuyển bản cũ sang $Backup"

# 3. Đưa bản mới vào đúng chỗ (cùng ổ đĩa: chuyển; khác ổ đĩa: chép)
try {
    if ([IO.Path]::GetPathRoot($SourceDir) -eq [IO.Path]::GetPathRoot($TargetDir)) {
        Move-Item -LiteralPath $SourceDir -Destination $TargetDir
    } else {
        Copy-Item -LiteralPath $SourceDir -Destination $TargetDir -Recurse
        Remove-Item -LiteralPath $SourceDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path -LiteralPath (Join-Path $TargetDir $ExeName))) { throw "Thiếu $ExeName sau khi chép." }
    Write-Log 'Đã thay bản mới.'
} catch {
    Write-Log "Lỗi khi thay bản mới: $($_.Exception.Message) — khôi phục bản cũ."
    if (Test-Path -LiteralPath $TargetDir) { Remove-Item -LiteralPath $TargetDir -Recurse -Force -ErrorAction SilentlyContinue }
    try {
        Rename-Item -LiteralPath $Backup -NewName (Split-Path -Leaf $TargetDir)
    } catch {
        Write-Log "Không khôi phục được bản cũ: $($_.Exception.Message) — bản dự phòng ở $Backup"
    }
    Start-App $TargetDir
    exit 5
}

# 4. Bản cài bằng QTPdfPro_Setup.exe: chép lại trình gỡ cài đặt (unins000.exe/.dat) và báo phiên bản mới
#    cho «Apps & features». Lỗi ở bước này không làm hỏng bản cập nhật.
try {
    Get-ChildItem -LiteralPath $Backup -File -Filter 'unins*' -ErrorAction SilentlyContinue | ForEach-Object {
        $dest = Join-Path $TargetDir $_.Name
        if (-not (Test-Path -LiteralPath $dest)) { Copy-Item -LiteralPath $_.FullName -Destination $dest }
    }
    if ($Version -and $AppId) {
        $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$($AppId)_is1"
        if (Test-Path -LiteralPath $key) {
            Set-ItemProperty -LiteralPath $key -Name 'DisplayVersion' -Value $Version
            Write-Log "Đã ghi DisplayVersion = $Version"
        }
    }
} catch {
    Write-Log "Không giữ được thông tin gỡ cài đặt: $($_.Exception.Message)"
}

# 5. Mở lại ứng dụng
Start-App $TargetDir
Write-Log 'Hoàn tất cập nhật.'
exit 0
"""


def update_script_text() -> str:
    return _PS_APPLY_UPDATE


def write_update_script(path: Optional[Path] = None) -> Path:
    """Ghi script PowerShell (UTF-8 có BOM để PowerShell 5.1 đọc đúng tiếng Việt, xuống dòng CRLF)."""
    path = Path(path) if path else updates_dir() / UPDATE_SCRIPT_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_PS_APPLY_UPDATE, encoding="utf-8-sig", newline="\r\n")
    return path


def prepare_install(
    zip_path: Path,
    version: str,
    target_dir: Optional[Path] = None,
    should_cancel: Optional[CancelCheck] = None,
    progress_cb: Optional[ProgressCallback] = None,
) -> InstallPlan:
    """Giải nén bản mới + sinh script; ném `InstallDirNotWritable` nếu không thay được thư mục cài."""
    target = Path(target_dir) if target_dir else current_install_dir()
    if target is None:
        raise UpdateError("Chỉ bản đóng gói (QTPdfPro.exe) mới tự cập nhật được.")
    target = target.resolve()
    folder = updates_dir().resolve()
    if folder == target or folder.is_relative_to(target):
        raise UpdateError("Thư mục dữ liệu nằm trong thư mục cài đặt — không thể tự thay bản mới.")
    if not can_write_install_dir(target):
        raise InstallDirNotWritable(
            f"Không ghi được vào thư mục cài đặt «{target}» (thường do nằm trong Program Files)."
        )
    app_dir = extract_update(Path(zip_path), folder / STAGING_DIR_NAME, should_cancel, progress_cb)
    script = write_update_script(folder / UPDATE_SCRIPT_NAME)
    return InstallPlan(
        version=version,
        zip_path=Path(zip_path),
        source_dir=app_dir,
        target_dir=target,
        script_path=script,
        log_path=folder / UPDATE_LOG_NAME,
    )


def _powershell_exe() -> str:
    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    exe = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(exe) if exe.is_file() else "powershell.exe"


def build_launch_command(plan: InstallPlan, pid: int, relaunch: bool = True) -> List[str]:
    cmd = [
        _powershell_exe(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden", "-File", str(plan.script_path),
        "-ProcessId", str(int(pid)),
        "-SourceDir", str(plan.source_dir),
        "-TargetDir", str(plan.target_dir),
        "-ExeName", plan.exe_name,
        "-LogFile", str(plan.log_path),
        "-Version", plan.version,
        "-AppId", INNO_APP_ID,
    ]  # fmt: skip
    if not relaunch:
        cmd.append("-NoRestart")
    return cmd


def _child_environment() -> dict:
    """Môi trường cho script: bỏ biến của bootloader PyInstaller và đường dẫn trỏ vào `_internal` cũ."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("_PYI_", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle and env.get("PATH"):
        bundle_lower = str(Path(bundle)).lower()
        env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep) if not p.lower().startswith(bundle_lower))
    return env


def _reset_dll_directory() -> None:
    # Bootloader gọi SetDllDirectory(_internal) và tiến trình con kế thừa — PowerShell có thể nạp DLL
    # từ `_internal` cũ rồi giữ khoá, làm thư mục cài không đổi tên được.
    if sys.platform == "win32" and is_frozen():
        try:
            import ctypes

            ctypes.windll.kernel32.SetDllDirectoryW(None)
        except (AttributeError, OSError):
            pass


def write_pending_marker(plan: InstallPlan) -> Path:
    path = updates_dir() / PENDING_MARKER_NAME
    payload = {
        "version": plan.version,
        "from_version": __version__,
        "zip": str(plan.zip_path),
        "target_dir": str(plan.target_dir),
        "log": str(plan.log_path),
        "created": now_iso(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return path


def consume_pending_marker(current_version: str = __version__) -> Optional[dict]:
    """Đọc rồi xoá dấu «đang cập nhật»; `ok` = phiên bản đang chạy đúng bản đã cài."""
    path = updates_dir() / PENDING_MARKER_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        data = {}
    path.unlink(missing_ok=True)
    if not isinstance(data, dict) or not data.get("version"):
        return None
    data["ok"] = str(data["version"]) == current_version
    return data


def launch_install(plan: InstallPlan, pid: Optional[int] = None, relaunch: bool = True) -> subprocess.Popen:
    """Chạy script cập nhật tách rời; ứng dụng phải thoát ngay sau đó để script thay thư mục."""
    if sys.platform != "win32":
        raise UpdateError("Tự cập nhật chỉ hỗ trợ Windows.")
    write_pending_marker(plan)
    _reset_dll_directory()
    cmd = build_launch_command(plan, os.getpid() if pid is None else pid, relaunch)
    base_flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    kwargs = dict(cwd=str(plan.script_path.parent), env=_child_environment(), close_fds=True)
    try:
        return subprocess.Popen(cmd, creationflags=base_flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kwargs)
    except OSError:
        # Job của tiến trình cha không cho tách → chạy thường (vẫn sống sau khi ứng dụng thoát)
        return subprocess.Popen(cmd, creationflags=base_flags, **kwargs)


def cleanup_previous_update(install_dir: Optional[Path] = None, current_version: str = __version__) -> List[Path]:
    """Lần khởi động sau khi cập nhật: xoá thư mục `.old`, thư mục giải nén tạm, tệp tải dở / tệp cũ."""
    removed: List[Path] = []
    install_dir = install_dir or current_install_dir()
    if install_dir is not None:
        install_dir = Path(install_dir)
        pattern = glob.escape(str(install_dir)) + ".old*"
        for p in glob.glob(pattern):
            path = Path(p)
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed.append(path)
    folder = updates_dir()
    staging = folder / STAGING_DIR_NAME
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
        removed.append(staging)
    current = parse_version(current_version)
    for f in folder.iterdir():
        if not f.is_file():
            continue
        if f.name.lower() in (UPDATE_ASSET_NAME.lower(), f"{UPDATE_ASSET_NAME}.part".lower()):
            f.unlink(missing_ok=True)  # tên không kèm phiên bản: lúc khởi động thì chắc chắn là tệp của lần trước
            removed.append(f)
            continue
        m = re.fullmatch(r"QTPdfPro-v(.+)-win64\.zip(\.part)?", f.name, re.IGNORECASE)
        if not m:
            continue
        ver = parse_version(m.group(1))
        stale = bool(m.group(2)) or ver is None or (current is not None and ver.sort_key() <= current.sort_key())
        if stale:
            f.unlink(missing_ok=True)
            removed.append(f)
    return removed
