"""Kiểm thử bộ cài & liên kết tệp: `core/file_assoc.py`, `installer.iss`, `tools/build_release.py`.

Registry thật chỉ được ghi dưới một khoá tạm `HKCU\\Software\\QTPdfProTest-<uuid>` (tham số `prefix`) và xoá ngay
sau bài — không đụng liên kết .pdf thật của người dùng.
"""

from __future__ import annotations

import re
import sys
import uuid
import zipfile
from pathlib import Path

import pytest

from qtpdfpro import __version__
from qtpdfpro.core import file_assoc as fa
from qtpdfpro.core import update_check as uc

ROOT = Path(__file__).resolve().parent.parent
ISS = ROOT / "installer.iss"
ISL = ROOT / "installer" / "Vietnamese.isl"
sys.path.insert(0, str(ROOT / "tools"))



def _delete_tree(root, subkey: str) -> None:  # noqa: ANN001 - khoá gốc winreg
    import winreg

    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(root, f"{subkey}\\{child}")
        winreg.DeleteKey(root, subkey)
    except FileNotFoundError:
        pass


@pytest.fixture
def reg_prefix():
    if sys.platform != "win32":
        pytest.skip("Cần Windows registry")
    import winreg

    prefix = f"Software\\QTPdfProTest-{uuid.uuid4().hex[:12]}"
    yield prefix
    _delete_tree(winreg.HKEY_CURRENT_USER, prefix)


def test_registry_entries_cover_progid_capabilities_and_open_with() -> None:
    exe = Path(r"C:\Users\Ai Đó\AppData\Local\Programs\QT PDF Pro\QTPdfPro.exe")
    entries = {(e.subkey, e.name): e.value for e in fa.registry_entries(exe)}
    assert entries[(r"Software\Classes\QTPdfPro.PDF\shell\open\command", "")] == f'"{exe}" "%1"'
    assert entries[(r"Software\Classes\.pdf\OpenWithProgids", "QTPdfPro.PDF")] == ""
    assert entries[(r"Software\QTPdfPro\Capabilities\FileAssociations", ".pdf")] == "QTPdfPro.PDF"
    assert entries[(r"Software\RegisteredApplications", "QTPdfPro")] == fa.CAPABILITIES_KEY
    assert entries[(fa.CAPABILITIES_KEY, "ApplicationName")] == "QT PDF Pro"
    assert entries[(r"Software\Classes\Applications\QTPdfPro.exe\SupportedTypes", ".pdf")] == ""
    assert fa.DEFAULT_APPS_URI == "ms-settings:defaultapps?registeredAppUser=QTPdfPro"


def test_register_and_read_back_under_temp_key(reg_prefix: str, tmp_path: Path) -> None:
    exe = tmp_path / "Ứng dụng" / "QTPdfPro.exe"
    assert fa.is_registered(prefix=reg_prefix) is False and fa.registered_exe(reg_prefix) is None
    fa.register_pdf_handler(exe, prefix=reg_prefix)
    assert fa.is_registered(prefix=reg_prefix) and fa.is_registered(exe, prefix=reg_prefix)
    assert not fa.is_registered(tmp_path / "khac" / "QTPdfPro.exe", prefix=reg_prefix)
    assert fa.registered_exe(reg_prefix) == str(exe)

    # Lựa chọn mặc định của người dùng: UserChoiceLatest (Windows 11 mới) được ưu tiên hơn UserChoice
    assert fa.current_default_progid(reg_prefix) is None and not fa.is_default_pdf_app(reg_prefix)
    fa.write_entries([fa.RegValue(fa.USER_CHOICE_KEYS[1], "ProgId", "QTPdfPro.PDF")], reg_prefix)
    assert fa.is_default_pdf_app(reg_prefix)
    fa.write_entries([fa.RegValue(fa.USER_CHOICE_KEYS[0], "ProgId", "MSEdgePDF")], reg_prefix)
    assert fa.current_default_progid(reg_prefix) == "MSEdgePDF" and not fa.is_default_pdf_app(reg_prefix)


def test_installer_iss_matches_core_constants() -> None:
    raw = ISS.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "installer.iss có tiếng Việt → phải UTF-8 có BOM"
    text = raw[3:].decode("utf-8").replace("\r\n", "\n")
    assert "{{" + uc.INNO_APP_ID[1:] in text, "AppId phải trùng update_check.INNO_APP_ID"
    assert re.search(r"^PrivilegesRequired=lowest$", text, re.M), "cài theo người dùng, không UAC"
    assert r"DefaultDirName={localappdata}\Programs\{#AppName}" in text and '#define AppName "QT PDF Pro"' in text
    assert "OutputBaseFilename=QTPdfPro_Setup" in text and uc.SETUP_ASSET_NAME == "QTPdfPro_Setup.exe"
    assert "ChangesAssociations=yes" in text
    from qtpdfpro.ui.app import APP_MUTEX_NAME

    assert f"AppMutex={APP_MUTEX_NAME}" in text
    assert "ms-settings:defaultapps?registeredAppUser={#RegAppName}" in text and "Check: not IsDefaultPdfApp" in text
    assert "--skip-default-prompt" in text
    assert "[UninstallDelete]" in text and r"{localappdata}\{#AppName}" in text

    # Mọi giá trị registry của file_assoc đều có trong [Registry] (sau khi thay hằng #define)
    defines = dict(re.findall(r'^#define (\w+) "(.*)"$', text, re.M))
    section = text.split("\n[Registry]\n", 1)[1].split("\n[", 1)[0]
    for key, val in defines.items():
        section = section.replace("{#" + key + "}", val)
    exe = r"{app}\QTPdfPro.exe"
    lines = []
    for line in section.splitlines():
        m = dict(re.findall(r'(\w+): ("(?:[^"]|"")*"|[^;]+)', line))
        if "Subkey" in m and "ValueName" in m:
            lines.append((m["Subkey"].strip('"'), m["ValueName"][1:-1], m["ValueData"][1:-1].replace('""', '"')))
    for e in fa.registry_entries(exe):
        assert (e.subkey, e.name, e.value) in lines, e


def test_vietnamese_isl_is_bom_and_overrides_known_messages() -> None:
    raw = ISL.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw[3:].decode("utf-8")
    assert "LanguageName=Tiếng Việt" in text and "ButtonNext=&Tiếp >" in text
    assert "SetDefaultPdf=" in text and "RemoveSettings=" in text  # [CustomMessages] dùng trong installer.iss


def test_make_update_zip_has_app_root_folder(tmp_path: Path) -> None:
    import build_release

    app = tmp_path / "dist" / "QTPdfPro"
    (app / "_internal" / "PySide6").mkdir(parents=True)
    (app / "QTPdfPro.exe").write_text("exe")
    (app / "_internal" / "PySide6" / "Qt6Core.dll").write_text("dll")
    out = build_release.make_update_zip(app, tmp_path / "dist" / uc.UPDATE_ASSET_NAME)
    with zipfile.ZipFile(out) as zf:
        names = sorted(zf.namelist())
    assert names == ["QTPdfPro/QTPdfPro.exe", "QTPdfPro/_internal/PySide6/Qt6Core.dll"]
    # Đúng cấu trúc trình cập nhật cần
    assert uc.extract_update(out, tmp_path / "staging") == (tmp_path / "staging" / "QTPdfPro").resolve()
    assert build_release.sha256_of(out) and __version__
