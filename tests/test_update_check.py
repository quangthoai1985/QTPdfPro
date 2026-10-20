"""Kiểm thử lõi cập nhật `core/update_check.py` và lệnh `cli update` — không gọi mạng thật.

Mạng được giả lập bằng cách thay `update_check._urlopen`; riêng một bài dựng HTTP server cục bộ
(chỉ chấp nhận khi đặt `QT_PDF_PRO_UPDATE_API`) để chạy qua đúng ngăn xếp `urllib`.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from qtpdfpro import __github_repo__, __version__
from qtpdfpro.cli import main as cli_main
from qtpdfpro.core import update_check as uc
from qtpdfpro.core.settings import AppSettings, get_data_dir

API_URL = f"https://api.github.com/repos/{__github_repo__}/releases/latest"
ASSET_NAME = "QTPdfPro-v0.9.0-win64.zip"
ASSET_URL = f"https://github.com/{__github_repo__}/releases/download/v0.9.0/{ASSET_NAME}"
CDN_URL = "https://release-assets.githubusercontent.com/github-production-release-asset/1/abc"


class FakeResponse:
    """Thay cho đối tượng trả về của `urlopen`: read / geturl / headers / close."""

    def __init__(self, body: bytes, url: str, headers: Dict[str, str] | None = None) -> None:
        self._buf = io.BytesIO(body)
        self._url = url
        self.headers = headers if headers is not None else {"Content-Length": str(len(body))}
        self.closed = False

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def geturl(self) -> str:
        return self._url

    def close(self) -> None:
        self.closed = True


def make_app_zip(version_text: str = "ban moi") -> bytes:
    """Tệp nén giống bản phát hành: thư mục gốc QTPdfPro/ chứa QTPdfPro.exe + _internal/."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("QTPdfPro/QTPdfPro.exe", version_text)
        zf.writestr("QTPdfPro/_internal/base_library.zip", "x" * 2048)
        zf.writestr("QTPdfPro/LICENSE", "MIT")
    return buf.getvalue()


def release_json(
    tag: str = "v0.9.0",
    prerelease: bool = False,
    draft: bool = False,
    payload: bytes = b"",
    digest: str | None = None,
    asset_url: str = ASSET_URL,
    update_zip: bool = False,
) -> dict:
    """`update_zip=True`: tệp chính tên `QTPdfPro_Update.zip` (từ v1.0.0), kèm tệp tên cũ trỏ tới URL khác."""
    sha = hashlib.sha256(payload).hexdigest()
    version = tag.lstrip("v")
    main_name = uc.UPDATE_ASSET_NAME if update_zip else f"QTPdfPro-v{version}-win64.zip"
    legacy = [{"name": f"QTPdfPro-v{version}-win64.zip", "browser_download_url": asset_url + "-legacy", "size": 1}]
    return {
        "tag_name": tag,
        "name": f"QT PDF Pro {tag} — Cập nhật tự động",
        "body": "## Có gì mới\n- **Tự kiểm tra cập nhật** và tải bản mới từ GitHub.",
        "html_url": f"https://github.com/{__github_repo__}/releases/tag/{tag}",
        "published_at": "2026-10-21T03:00:00Z",
        "draft": draft,
        "prerelease": prerelease,
        "assets": [
            {"name": f"QTPdfPro-v{version}-win64.zip.sha256", "browser_download_url": asset_url + ".sha256",
             "size": 64},
            {"name": f"QTPdfPro-v{version}-src.zip", "browser_download_url": asset_url.replace("win64", "src"),
             "size": 10},
            {"name": uc.SETUP_ASSET_NAME, "browser_download_url": asset_url + "-setup", "size": 99},
            {"name": main_name, "browser_download_url": asset_url, "size": len(payload),
             "digest": f"sha256:{sha}" if digest is None else digest, "content_type": "application/zip"},
        ] + (legacy if update_zip else []),
    }  # fmt: skip


def fake_network(monkeypatch: pytest.MonkeyPatch, routes: Dict[str, Callable[[], object]]) -> list:
    """Giả lập `_urlopen`: mỗi URL ứng với một hàm trả FakeResponse hoặc ném lỗi."""
    calls: list = []

    def _fake(request: Request, timeout: float, allowed_hosts: frozenset):
        calls.append({"url": request.full_url, "timeout": timeout, "headers": dict(request.header_items())})
        factory = routes.get(request.full_url)
        if factory is None:
            raise AssertionError(f"Không chờ đợi truy cập: {request.full_url}")
        result = factory()
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(uc, "_urlopen", _fake)
    return calls


def api_route(data: dict) -> Callable[[], FakeResponse]:
    return lambda: FakeResponse(json.dumps(data).encode("utf-8"), API_URL)


# ─── Phiên bản ─────────────────────────────────────────────────────────────


def test_semver_parse_and_compare() -> None:
    assert uc.parse_version("v0.4.0") == uc.SemVer(0, 4, 0, "")
    assert uc.parse_version("0.5.0-beta.1+build.7") == uc.SemVer(0, 5, 0, "beta.1")
    assert uc.parse_version("v0.4") is None and uc.parse_version("ban-moi") is None
    assert uc.is_newer("v0.5.0", "0.4.0")
    assert uc.is_newer("0.10.0", "0.9.9")  # so theo số, không theo chuỗi
    assert not uc.is_newer("v0.4.0", "0.4.0")
    assert not uc.is_newer("v0.3.9", "0.4.0")
    assert not uc.is_newer("khong-hop-le", "0.4.0")
    ordered = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
    keys = [uc.parse_version(v).sort_key() for v in ordered]
    assert keys == sorted(keys)
    assert not uc.is_newer("1.0.0-rc.1", "1.0.0")


def test_check_reports_newer_release_and_selects_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = make_app_zip()
    calls = fake_network(monkeypatch, {API_URL: api_route(release_json(payload=payload))})
    res = uc.check_for_update(current_version="0.4.0")
    assert res.update_available is True
    assert res.latest is not None and res.latest.version == "0.9.0"
    assert "Tự kiểm tra cập nhật" in res.latest.notes
    asset = res.latest.asset
    assert asset is not None and asset.name == ASSET_NAME and asset.url == ASSET_URL
    assert asset.size == len(payload) and asset.sha256 == hashlib.sha256(payload).hexdigest()
    json.dumps(res.to_dict(), ensure_ascii=False)  # in được bằng `cli update --json`
    # Tiêu đề yêu cầu: User-Agent, Accept JSON của GitHub, có timeout
    assert calls[0]["url"] == API_URL and calls[0]["timeout"] == uc.API_TIMEOUT
    headers = {k.lower(): v for k, v in calls[0]["headers"].items()}
    assert headers["user-agent"].startswith("QTPdfPro/") and "github" in headers["accept"]


def test_check_up_to_date_prerelease_draft_and_no_release(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [
        (release_json(tag=f"v{__version__}"), "mới nhất"),
        (release_json(tag="v0.9.0", prerelease=True), "thử nghiệm"),
        (release_json(tag="v0.9.0-rc.1"), "thử nghiệm"),  # thẻ pre-release dù cờ prerelease = false
        (release_json(tag="v0.9.0", draft=True), "thử nghiệm"),
    ]
    for data, word in cases:
        fake_network(monkeypatch, {API_URL: api_route(data)})
        res = uc.check_for_update()
        assert res.update_available is False and word in res.message, data["tag_name"]

    fake_network(monkeypatch, {API_URL: lambda: HTTPError(API_URL, 404, "Not Found", None, None)})
    res = uc.check_for_update()
    assert res.update_available is False and res.latest is None
    fake_network(monkeypatch, {API_URL: lambda: HTTPError(API_URL, 403, "rate limit", None, None)})
    with pytest.raises(uc.UpdateError, match="giới hạn"):
        uc.check_for_update()
    fake_network(monkeypatch, {API_URL: lambda: FakeResponse(b"<html>", API_URL)})
    with pytest.raises(uc.UpdateError, match="JSON"):
        uc.check_for_update()


def test_select_asset_requires_exact_release_name() -> None:
    assets = release_json(payload=b"abc")["assets"]
    assert uc.select_asset(assets, "0.9.0").name == ASSET_NAME
    assert uc.select_asset(assets, "0.9.1") is None
    assert uc.select_asset([{"name": "QTPdfPro-v0.9.0-WIN64.ZIP", "browser_download_url": ASSET_URL}], "0.9.0")
    no_digest = uc.select_asset([{"name": ASSET_NAME, "browser_download_url": ASSET_URL, "size": 3}], "0.9.0")
    assert no_digest is not None and no_digest.sha256 == ""
    assert uc.expected_asset_name("0.5.0") == "QTPdfPro-v0.5.0-win64.zip"
    # Từ v1.0.0: ưu tiên QTPdfPro_Update.zip, bỏ qua bộ cài QTPdfPro_Setup.exe
    new_assets = release_json(tag="v1.2.0", payload=b"abc", update_zip=True)["assets"]
    chosen = uc.select_asset(new_assets, "1.2.0")
    assert chosen.name == uc.UPDATE_ASSET_NAME and chosen.url == ASSET_URL
    assert chosen.sha256 == hashlib.sha256(b"abc").hexdigest()
    only_legacy = [a for a in new_assets if a["name"] != uc.UPDATE_ASSET_NAME]
    assert uc.select_asset(only_legacy, "1.2.0").name == "QTPdfPro-v1.2.0-win64.zip"
    assert uc.select_asset([a for a in new_assets if a["name"] == uc.SETUP_ASSET_NAME], "1.2.0") is None


# ─── Tải về ────────────────────────────────────────────────────────────────


def _asset(payload: bytes, sha: str | None = None, url: str = ASSET_URL, size: int | None = None) -> uc.ReleaseAsset:
    return uc.ReleaseAsset(
        name=ASSET_NAME,
        url=url,
        size=len(payload) if size is None else size,
        sha256=hashlib.sha256(payload).hexdigest() if sha is None else sha,
    )


def test_download_accepts_matching_sha256(monkeypatch: pytest.MonkeyPatch, isolated_app_data: Path) -> None:
    payload = make_app_zip() * 30  # vài chục KB → nhiều khối
    monkeypatch.setattr(uc, "CHUNK_SIZE", 4096)
    calls = fake_network(monkeypatch, {ASSET_URL: lambda: FakeResponse(payload, CDN_URL)})
    seen: list = []
    path = uc.download_asset(_asset(payload), progress_cb=lambda d, t: seen.append((d, t)))
    assert path == isolated_app_data / "updates" / ASSET_NAME
    assert path.read_bytes() == payload
    assert not (path.parent / f"{ASSET_NAME}.part").exists()
    assert seen[0] == (0, len(payload)) and seen[-1] == (len(payload), len(payload)) and len(seen) > 3
    headers = {k.lower(): v for k, v in calls[0]["headers"].items()}
    assert headers["user-agent"].startswith("QTPdfPro/") and calls[0]["timeout"] == uc.DOWNLOAD_TIMEOUT


def test_download_rejects_bad_hash_and_size(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dest = tmp_path / "dl"
    payload = make_app_zip()
    fake_network(monkeypatch, {ASSET_URL: lambda: FakeResponse(payload, CDN_URL)})
    with pytest.raises(uc.UpdateError, match="SHA-256"):
        uc.download_asset(_asset(payload, sha="0" * 64), dest)
    with pytest.raises(uc.UpdateError, match="thiếu"):
        uc.download_asset(_asset(payload, size=len(payload) + 10), dest)
    with pytest.raises(uc.UpdateError, match="lớn hơn"):
        uc.download_asset(_asset(payload, size=len(payload) - 10), dest)
    assert list(dest.iterdir()) == []  # không để lại tệp dở


def test_download_rejects_untrusted_hosts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dest = tmp_path / "dl"
    payload = make_app_zip()
    calls = fake_network(monkeypatch, {})
    for bad in (
        "https://evil.example.com/QTPdfPro-v0.9.0-win64.zip",
        f"http://github.com/{__github_repo__}/releases/download/v0.9.0/{ASSET_NAME}",  # không phải https
        "https://github.com.evil.example/x.zip",
        "http://127.0.0.1:8000/x.zip",  # máy cục bộ chỉ được phép khi kiểm thử có QT_PDF_PRO_UPDATE_API
        "file:///C:/Windows/notepad.exe",
    ):
        with pytest.raises(uc.UpdateError, match="không tin cậy"):
            uc.download_asset(_asset(payload, url=bad), dest)
    assert calls == []  # bị chặn trước khi kết nối
    with pytest.raises(uc.UpdateError, match="không hợp lệ"):
        uc.download_asset(uc.ReleaseAsset(name="..\\QTPdfPro.exe", url=ASSET_URL), dest)

    # Chuyển hướng sang host lạ: bị chặn ở bộ chuyển hướng và ở URL cuối
    handler = uc._GuardedRedirect(uc.DOWNLOAD_HOSTS)
    req = Request(ASSET_URL)
    with pytest.raises(uc.UpdateError):
        handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example.com/x.zip")
    assert handler.redirect_request(req, None, 302, "Found", {}, CDN_URL) is not None
    fake_network(monkeypatch, {ASSET_URL: lambda: FakeResponse(payload, "https://evil.example.com/x.zip")})
    with pytest.raises(uc.UpdateError, match="không tin cậy"):
        uc.download_asset(_asset(payload), dest)
    assert list(dest.iterdir()) == []


def test_download_cancel_midway(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dest = tmp_path / "dl"
    payload = b"z" * 50_000
    monkeypatch.setattr(uc, "CHUNK_SIZE", 4096)
    fake_network(monkeypatch, {ASSET_URL: lambda: FakeResponse(payload, CDN_URL)})
    progress: list = []
    with pytest.raises(uc.UpdateCancelled):
        uc.download_asset(
            _asset(payload), dest, progress_cb=lambda d, t: progress.append(d),
            should_cancel=lambda: len(progress) > 3,
        )  # fmt: skip
    assert 0 < progress[-1] < len(payload)
    assert list(dest.iterdir()) == []


def test_local_http_server_end_to_end(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Đi qua đúng urllib + bộ chuyển hướng: API → asset (302) → tệp; host lạ trong chuyển hướng bị chặn."""
    payload = make_app_zip("ban 0.9.0")
    state: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - API http.server
            base = f"http://127.0.0.1:{state['port']}"
            if self.path == "/api/latest":
                body = json.dumps(release_json(payload=payload, asset_url=f"{base}/dl/{ASSET_NAME}")).encode()
                self._send(200, body, "application/json")
            elif self.path == f"/dl/{ASSET_NAME}":
                self.send_response(302)
                self.send_header("Location", f"{base}/cdn/{ASSET_NAME}")
                self.end_headers()
            elif self.path == "/dl/evil":
                self.send_response(302)
                self.send_header("Location", "https://evil.example.com/QTPdfPro-v0.9.0-win64.zip")
                self.end_headers()
            elif self.path == f"/cdn/{ASSET_NAME}":
                self._send(200, payload, "application/zip")
            else:
                self._send(404, b"not found", "text/plain")

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # noqa: ANN002 - im lặng khi chạy test
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state["port"] = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        api = f"http://127.0.0.1:{state['port']}/api/latest"
        with pytest.raises(uc.UpdateError, match="không tin cậy"):
            uc.validate_url(api, uc.API_HOSTS)  # chưa bật chế độ kiểm thử
        monkeypatch.setenv(uc.API_OVERRIDE_ENV, api)
        res = uc.check_for_update(current_version="0.4.0")
        assert res.update_available and res.latest.asset is not None
        path = uc.download_asset(res.latest.asset, tmp_path / "dl")
        assert path.read_bytes() == payload
        evil = uc.ReleaseAsset(name=ASSET_NAME, url=f"http://127.0.0.1:{state['port']}/dl/evil", size=len(payload))
        with pytest.raises(uc.UpdateError, match="không tin cậy"):
            uc.download_asset(evil, tmp_path / "dl2")
    finally:
        server.shutdown()
        server.server_close()


# ─── Nhịp kiểm tra 1 lần/ngày & cài đặt ────────────────────────────────────


def test_should_auto_check_once_per_day() -> None:
    now = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
    assert uc.should_auto_check("", now) is True
    assert uc.should_auto_check("không phải ngày", now) is True
    assert uc.should_auto_check((now - timedelta(hours=1)).isoformat(), now) is False
    assert uc.should_auto_check((now - timedelta(hours=23, minutes=59)).isoformat(), now) is False
    assert uc.should_auto_check((now - timedelta(hours=24)).isoformat(), now) is True
    assert uc.should_auto_check((now - timedelta(days=3)).isoformat(), now) is True
    assert uc.should_auto_check((now + timedelta(days=2)).isoformat(), now) is True  # đồng hồ bị chỉnh lùi
    assert uc.should_auto_check("2026-10-20T07:30:00", now) is False  # không múi giờ → coi là UTC
    assert uc.should_auto_check(uc.now_iso()) is False


def test_update_settings_persist(isolated_app_data: Path) -> None:
    s = AppSettings.load()
    assert s.auto_check_updates is True and s.last_update_check == "" and s.skipped_update_version == ""
    s.auto_check_updates = False
    s.last_update_check = "2026-10-20T08:00:00+00:00"
    s.skipped_update_version = "0.9.0"
    s.save()
    again = AppSettings.load()
    assert (again.auto_check_updates, again.last_update_check, again.skipped_update_version) == (
        False, "2026-10-20T08:00:00+00:00", "0.9.0",
    )  # fmt: skip
    assert AppSettings.settings_file().parent == isolated_app_data


# ─── Giải nén, script cập nhật, dọn dẹp ────────────────────────────────────


def test_extract_update_finds_app_and_blocks_zip_slip(tmp_path: Path) -> None:
    good = tmp_path / "good.zip"
    good.write_bytes(make_app_zip())
    app_dir = uc.extract_update(good, tmp_path / "staging")
    assert app_dir == (tmp_path / "staging" / "QTPdfPro").resolve()
    assert (app_dir / "QTPdfPro.exe").read_text() == "ban moi"

    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("QTPdfPro/QTPdfPro.exe", "x")
        zf.writestr("../../ngoai.txt", "thoát ra ngoài")
    with pytest.raises(uc.UpdateError, match="không an toàn"):
        uc.extract_update(evil, tmp_path / "staging2")
    assert not (tmp_path / "ngoai.txt").exists()

    no_exe = tmp_path / "no_exe.zip"
    with zipfile.ZipFile(no_exe, "w") as zf:
        zf.writestr("README.txt", "x")
    with pytest.raises(uc.UpdateError, match="QTPdfPro.exe"):
        uc.extract_update(no_exe, tmp_path / "staging3")
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"khong phai zip")
    with pytest.raises(uc.UpdateError, match="zip"):
        uc.extract_update(bad, tmp_path / "staging4")


def _fake_install(root: Path, exe_text: str) -> Path:
    (root / "_internal").mkdir(parents=True)
    (root / "QTPdfPro.exe").write_text(exe_text)
    (root / "_internal" / "base_library.zip").write_text(exe_text)
    return root


def test_prepare_install_builds_plan_and_respects_write_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, isolated_app_data: Path
) -> None:
    target = _fake_install(tmp_path / "Apps" / "QTPdfPro", "ban cu")
    zpath = tmp_path / ASSET_NAME
    zpath.write_bytes(make_app_zip())
    plan = uc.prepare_install(zpath, "0.9.0", target)
    upd = (isolated_app_data / "updates").resolve()
    assert plan.target_dir == target.resolve() and plan.version == "0.9.0"
    assert plan.source_dir == upd / "staging" / "QTPdfPro"
    assert plan.script_path == upd / uc.UPDATE_SCRIPT_NAME and plan.script_path.is_file()
    assert plan.log_path == upd / uc.UPDATE_LOG_NAME

    monkeypatch.setattr(uc, "can_write_install_dir", lambda path: False)
    with pytest.raises(uc.InstallDirNotWritable, match="Program Files"):
        uc.prepare_install(zpath, "0.9.0", target)
    with pytest.raises(uc.UpdateError, match="đóng gói"):
        uc.prepare_install(zpath, "0.9.0", None)  # chạy từ mã nguồn: không có thư mục cài


def test_update_script_content_and_encoding(tmp_path: Path) -> None:
    script = uc.write_update_script(tmp_path / "apply_update.ps1")
    raw = script.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "PowerShell 5.1 cần UTF-8 có BOM để đọc đúng tiếng Việt"
    text = raw[3:].decode("utf-8")
    assert text.splitlines()[0] == "param(", "`param` phải là câu lệnh đầu tiên (CLAUDE.md mục 5)"
    assert b"\n" not in raw.replace(b"\r\n", b"")
    for needle in ("WaitForExit", '"$TargetDir.old"', "Rename-Item", "Move-Item", "Copy-Item",
                   "khôi phục bản cũ", "Start-Process", "$NoRestart"):  # fmt: skip
        assert needle in text, needle
    assert text.index("param(") < text.index("$ErrorActionPreference")

    plan = uc.InstallPlan(
        version="0.9.0", zip_path=tmp_path / ASSET_NAME, source_dir=tmp_path / "staging" / "QTPdfPro",
        target_dir=tmp_path / "Ứng dụng" / "QTPdfPro", script_path=script, log_path=tmp_path / "update.log",
    )  # fmt: skip
    cmd = uc.build_launch_command(plan, 4321)
    assert cmd[0].lower().endswith("powershell.exe")
    assert cmd[cmd.index("-ExecutionPolicy") + 1] == "Bypass" and cmd[cmd.index("-File") + 1] == str(script)
    assert cmd[cmd.index("-ProcessId") + 1] == "4321"
    assert cmd[cmd.index("-TargetDir") + 1] == str(plan.target_dir)
    assert "-NoRestart" not in cmd and "-NoRestart" in uc.build_launch_command(plan, 4321, relaunch=False)
    assert cmd[cmd.index("-Version") + 1] == "0.9.0" and cmd[cmd.index("-AppId") + 1] == uc.INNO_APP_ID
    for needle in ("unins*", "DisplayVersion", "_is1"):
        assert needle in text, needle


@pytest.mark.skipif(sys.platform != "win32" or shutil.which("powershell") is None, reason="Cần Windows PowerShell")
def test_update_script_swaps_fake_install_folders(tmp_path: Path) -> None:
    """Chạy script thật trên thư mục giả trong tmp (không đụng bản cài thật, không mở lại ứng dụng)."""
    script = uc.write_update_script(tmp_path / "apply_update.ps1")
    target = _fake_install(tmp_path / "Ứng dụng" / "QTPdfPro", "ban cu")
    (target / "unins000.exe").write_text("trinh go")  # bản cài bằng QTPdfPro_Setup.exe (Inno Setup)
    (target / "unins000.dat").write_text("nhat ky go")
    source = _fake_install(tmp_path / "staging" / "QTPdfPro", "ban moi")
    log = tmp_path / "update.log"

    def run(src: Path) -> subprocess.CompletedProcess:
        plan = uc.InstallPlan("0.9.0", tmp_path / "x.zip", src, target, script, log)
        return subprocess.run(uc.build_launch_command(plan, 0, relaunch=False), capture_output=True, timeout=120)

    proc = run(source)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert (target / "QTPdfPro.exe").read_text() == "ban moi"
    backup = target.with_name("QTPdfPro.old")
    assert (backup / "QTPdfPro.exe").read_text() == "ban cu"
    assert (target / "unins000.exe").read_text() == "trinh go" and (target / "unins000.dat").is_file()
    assert not source.exists()
    assert "Hoàn tất cập nhật" in log.read_text(encoding="utf-8-sig")

    # Bản mới thiếu QTPdfPro.exe → không đụng thư mục cài
    broken = tmp_path / "staging2" / "QTPdfPro"
    (broken / "_internal").mkdir(parents=True)
    proc = run(broken)
    assert proc.returncode == 3
    assert (target / "QTPdfPro.exe").read_text() == "ban moi"

    # Lần khởi động sau: xoá bản dự phòng .old
    removed = uc.cleanup_previous_update(target, current_version="0.9.0")
    assert backup in removed and not backup.exists() and target.exists()


def test_pending_marker_and_cleanup(tmp_path: Path, isolated_app_data: Path) -> None:
    upd = uc.updates_dir()
    plan = uc.InstallPlan("0.9.0", upd / ASSET_NAME, upd / "staging" / "QTPdfPro", tmp_path / "QTPdfPro",
                          upd / uc.UPDATE_SCRIPT_NAME, upd / uc.UPDATE_LOG_NAME)  # fmt: skip
    uc.write_pending_marker(plan)
    marker = uc.consume_pending_marker(current_version="0.9.0")
    assert marker["ok"] is True and marker["version"] == "0.9.0" and marker["from_version"] == __version__
    assert uc.consume_pending_marker() is None  # đã xoá sau khi đọc
    uc.write_pending_marker(plan)
    assert uc.consume_pending_marker(current_version="0.4.0")["ok"] is False

    install = _fake_install(tmp_path / "QTPdfPro", "ban moi")
    old = _fake_install(tmp_path / "QTPdfPro.old", "ban cu")
    (upd / "staging" / "QTPdfPro").mkdir(parents=True)
    for name in ("QTPdfPro-v0.4.0-win64.zip", "QTPdfPro-v0.9.0-win64.zip", "QTPdfPro-v1.0.0-win64.zip.part",
                 "QTPdfPro-v1.0.0-win64.zip", "ghi_chu.txt", uc.UPDATE_ASSET_NAME, f"{uc.UPDATE_ASSET_NAME}.part"):  # fmt: skip
        (upd / name).write_bytes(b"x")
    uc.cleanup_previous_update(install, current_version="0.9.0")
    assert not old.exists() and install.exists() and not (upd / "staging").exists()
    left = sorted(p.name for p in upd.iterdir())
    assert left == ["QTPdfPro-v1.0.0-win64.zip", "ghi_chu.txt"]
    assert upd.parent == get_data_dir()


def test_updates_dir_default_location(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Không đặt QT_PDF_PRO_DATA: tải về %LOCALAPPDATA%/QT PDF Pro/updates (ngoài thư mục cài Programs)."""
    monkeypatch.delenv("QT_PDF_PRO_DATA", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert uc.updates_dir() == tmp_path / "QT PDF Pro" / "updates" and uc.updates_dir().is_dir()


def test_format_size_vietnamese() -> None:
    assert uc.format_size(129587401) == "123,6 MB"
    assert uc.format_size(2048) == "2 KB"


# ─── CLI ───────────────────────────────────────────────────────────────────


def test_cli_update_check_and_download(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path: Path
) -> None:
    payload = make_app_zip()
    url = f"https://github.com/{__github_repo__}/releases/download/v9.0.0/{uc.UPDATE_ASSET_NAME}"
    fake_network(monkeypatch, {
        API_URL: api_route(release_json(tag="v9.0.0", payload=payload, asset_url=url, update_zip=True)),
        url: lambda: FakeResponse(payload, CDN_URL),
    })  # fmt: skip
    assert cli_main(["update", "--check", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["update_available"] is True and data["latest"]["asset"]["name"] == uc.UPDATE_ASSET_NAME

    assert cli_main(["update"]) == 0
    assert "Đã có bản v9.0.0" in capsys.readouterr().out

    out_dir = tmp_path / "tai_ve"
    assert cli_main(["update", "--download", "-o", str(out_dir), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert Path(data["downloaded"]) == out_dir / uc.UPDATE_ASSET_NAME
    assert (out_dir / uc.UPDATE_ASSET_NAME).read_bytes() == payload

    fake_network(monkeypatch, {API_URL: api_route(release_json(tag=f"v{__version__}"))})
    assert cli_main(["update", "--download", "-o", str(out_dir)]) == 0
    assert "mới nhất" in capsys.readouterr().out

    fake_network(monkeypatch, {API_URL: lambda: OSError("mất mạng")})
    assert cli_main(["update", "--check"]) == 1
    assert "Không kết nối được" in capsys.readouterr().err
