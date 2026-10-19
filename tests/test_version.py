"""Kiểm tra đồng bộ phiên bản, tệp bàn giao Agent và quy tắc tệp .bat ASCII."""

from __future__ import annotations

import re
from pathlib import Path

from qtpdfpro import __version__

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_version_semver_and_changelog() -> None:
    assert re.match(r"^\d+\.\d+\.\d+$", __version__), f"Phiên bản không đúng SemVer: {__version__}"
    changelog = (ROOT_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog, (
        f"CHANGELOG.md chưa có mục '## [{__version__}]'"
    )


def test_required_project_and_agent_docs_exist() -> None:
    required_files = [
        "README.md",
        "CLAUDE.md",
        "AGENTS.md",
        "CHANGELOG.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "requirements.txt",
        "run.bat",
        "build.bat",
        "docs/NGHIEN_CUU_CONG_NGHE.md",
        "docs/THIET_KE.md",
        "docs/DE_XUAT_TINH_NANG.md",
    ]
    for rel in required_files:
        p = ROOT_DIR / rel
        assert p.exists(), f"Thiếu tệp bắt buộc: {rel}"
        assert p.stat().st_size > 50, f"Tệp {rel} quá ngắn hoặc rỗng"


def test_bat_files_are_pure_ascii_and_crlf() -> None:
    for bat_name in ("run.bat", "build.bat"):
        raw = (ROOT_DIR / bat_name).read_bytes()
        try:
            raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise AssertionError(f"Tệp {bat_name} phải thuần ASCII để cmd.exe không lỗi: {exc}") from exc
        assert b"\r\n" in raw, f"Tệp {bat_name} phải dùng dòng kết thúc CRLF"
        assert b"\n" not in raw.replace(b"\r\n", b""), f"Tệp {bat_name} không được chứa LF đơn lẻ"
