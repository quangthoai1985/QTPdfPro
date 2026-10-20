"""Đóng gói bản phát hành QT PDF Pro: PyInstaller → bộ cài Inno Setup → tệp cập nhật ngầm.

    python tools/build_release.py                 # build.bat + iscc + zip, in mã SHA-256
    python tools/build_release.py --skip-build    # dùng lại dist\\QTPdfPro đã build

Kết quả trong `dist/`:
- `QTPdfPro_Setup.exe`          bộ cài theo người dùng (installer.iss), không cần UAC
- `QTPdfPro_Update.zip`         thư mục gốc `QTPdfPro/` (QTPdfPro.exe + _internal) cho trình cập nhật ngầm
- `QTPdfPro-v<x.y.z>-win64.zip` cùng nội dung, tên cũ — bản v0.5.0 chỉ nhận tên này (bỏ bằng --no-legacy-zip)

Tự cài công cụ còn thiếu: PyInstaller (pip), Inno Setup (winget, rồi choco).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qtpdfpro import __version__  # noqa: E402
from qtpdfpro.core import update_check as uc  # noqa: E402

DIST = ROOT / "dist"
APP_DIR_NAME = "QTPdfPro"


def iscc_candidates() -> List[Path]:
    found = shutil.which("iscc")
    paths = [Path(found)] if found else []
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            sub = "Programs/Inno Setup 6" if base == os.environ.get("LOCALAPPDATA") else "Inno Setup 6"
            paths.append(Path(base) / sub / "ISCC.exe")
    return paths


def find_iscc() -> Optional[Path]:
    return next((p for p in iscc_candidates() if p.is_file()), None)


def run(cmd: List[str], **kwargs) -> None:  # noqa: ANN003
    print("»", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(ROOT), **kwargs)


def ensure_pyinstaller() -> None:
    if importlib.util.find_spec("PyInstaller") is None:
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def ensure_iscc() -> Path:
    iscc = find_iscc()
    if iscc is not None:
        return iscc
    installers = []
    if shutil.which("winget"):
        installers.append(["winget", "install", "--id", "JRSoftware.InnoSetup", "-e", "--scope", "user",
                           "--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity"])
    if shutil.which("choco"):
        installers.append(["choco", "install", "innosetup", "-y"])
    for cmd in installers:
        try:
            run(cmd)
        except subprocess.CalledProcessError:
            continue
        iscc = find_iscc()
        if iscc is not None:
            return iscc
    raise SystemExit("Không tìm thấy / không cài được Inno Setup (ISCC.exe). Cài thủ công: winget install JRSoftware.InnoSetup")


def make_update_zip(app_dir: Path, out_path: Path) -> Path:
    """Nén `app_dir` thành `<out>` với thư mục gốc `QTPdfPro/` (đúng cấu trúc `update_check.extract_update` cần)."""
    if not (app_dir / uc.APP_EXE_NAME).is_file() or not (app_dir / "_internal").is_dir():
        raise SystemExit(f"{app_dir} không có {uc.APP_EXE_NAME} + _internal — hãy build trước.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".zip.part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(app_dir.rglob("*")):
            if path.is_file():
                zf.write(path, Path(APP_DIR_NAME) / path.relative_to(app_dir))
    os.replace(tmp, out_path)
    return out_path


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: Optional[List[str]] = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Đóng gói bản phát hành QT PDF Pro (Setup + Update.zip)")
    parser.add_argument("--skip-build", action="store_true", help="Không chạy lại build.bat (PyInstaller)")
    parser.add_argument("--skip-installer", action="store_true", help="Không biên dịch installer.iss")
    parser.add_argument("--no-legacy-zip", action="store_true", help="Không tạo QTPdfPro-v<x.y.z>-win64.zip")
    parser.add_argument("--json", action="store_true", help="In danh sách tệp dạng JSON")
    args = parser.parse_args(argv)

    app_dir = DIST / APP_DIR_NAME
    if not args.skip_build:
        ensure_pyinstaller()
        run(["cmd.exe", "/c", str(ROOT / "build.bat")])
    outputs: List[Path] = []
    if not args.skip_installer:
        iscc = ensure_iscc()
        run([str(iscc), "/Qp", f"/DAppVersion={__version__}", f"/DSourceDir={app_dir}", str(ROOT / "installer.iss")])
        outputs.append(DIST / uc.SETUP_ASSET_NAME)
    update_zip = make_update_zip(app_dir, DIST / uc.UPDATE_ASSET_NAME)
    outputs.append(update_zip)
    if not args.no_legacy_zip:
        legacy = DIST / uc.expected_asset_name(__version__)
        shutil.copyfile(update_zip, legacy)
        outputs.append(legacy)

    report = [{"file": str(p), "size": p.stat().st_size, "sha256": sha256_of(p)} for p in outputs]
    if args.json:
        print(json.dumps({"version": __version__, "assets": report}, ensure_ascii=False, indent=2))
    else:
        print(f"\nQT PDF Pro v{__version__} — tệp phát hành:")
        for item in report:
            print(f"  {Path(item['file']).name:32} {uc.format_size(item['size']):>10}  sha256:{item['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
