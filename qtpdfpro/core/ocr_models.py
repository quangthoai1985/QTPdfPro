"""Bộ mô hình OCR tiếng Việt: tải khi dùng lần đầu, cài vào thư mục dữ liệu (mục V5 cho B3).

Không phụ thuộc `PySide6`. Bộ cài không kèm mô hình (~88 MB): lần đầu người dùng mở «OCR tiếng Việt», giao diện
gọi `install_models()` trong luồng nền — tải `QTPdfPro_OCR_vi_v<N>.zip` từ GitHub Release (chỉ https + host
GitHub, kể cả từng bước chuyển hướng — dùng lại `update_check._open`), kiểm kích thước + SHA-256 ghim sẵn trong
mã, giải nén vào thư mục tạm (chặn đường dẫn thoát ra ngoài), kiểm từng tệp theo `manifest.json` rồi mới đổi tên
thành `<dữ liệu>/modules/ocr-vi-<N>/`. Lỗi hay huỷ giữa chừng thì không để lại bản cài dở.

Tệp zip dựng bằng `tools/export_ocr_models.py`. Biến môi trường `QT_PDF_PRO_OCR_MODELS` trỏ tới một thư mục mô
hình đã giải nén (chạy từ mã nguồn khi chưa đăng bản phát hành mô hình, hoặc bài test).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional

from qtpdfpro import __github_repo__
from qtpdfpro.core import update_check as uc
from qtpdfpro.core.settings import get_data_dir

BUNDLE_VERSION = 1
BUNDLE_ID = f"ocr-vi-{BUNDLE_VERSION}"
BUNDLE_TAG = f"ocr-models-v{BUNDLE_VERSION}"  # bản phát hành riêng (pre-release) chỉ chứa mô hình
BUNDLE_ASSET = uc.ReleaseAsset(
    name=f"QTPdfPro_OCR_vi_v{BUNDLE_VERSION}.zip",
    url=f"https://github.com/{__github_repo__}/releases/download/{BUNDLE_TAG}/QTPdfPro_OCR_vi_v{BUNDLE_VERSION}.zip",
    size=91937523,
    sha256="a9f6ea0ffda38b6458da2630a3c22cefb2c4915f7e13abc95d1f202dcf3a71b7",
)
MODELS_ENV = "QT_PDF_PRO_OCR_MODELS"
MANIFEST_NAME = "manifest.json"
DOWNLOAD_TIMEOUT = 30.0

ProgressCallback = Callable[[int, int], None]
CancelCheck = Callable[[], bool]


class OcrModelError(Exception):
    """Lỗi tải / cài / nạp bộ mô hình OCR (thông điệp tiếng Việt hiển thị được cho người dùng)."""


class OcrModelCancelled(OcrModelError):
    """Người dùng huỷ giữa chừng."""


@dataclass
class ModelBundle:
    """Bộ mô hình đã cài: thư mục + nội dung `manifest.json`."""

    root: Path
    manifest: Dict = field(default_factory=dict)

    def path(self, name: str) -> Path:
        return self.root / name

    @property
    def detector(self) -> Dict:
        return self.manifest.get("detector", {})

    @property
    def recognizer(self) -> Dict:
        return self.manifest.get("recognizer", {})


def modules_dir() -> Path:
    """`%LOCALAPPDATA%\\QTPdfPro\\modules` (theo `QT_PDF_PRO_DATA` khi kiểm thử)."""
    return get_data_dir() / "modules"  # chỉ tạo khi cài (`install_models`)


def bundle_dir() -> Path:
    return modules_dir() / BUNDLE_ID


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_bundle(root: Path, verify_hashes: bool = False) -> ModelBundle:
    """Đọc và kiểm một thư mục mô hình; thiếu tệp / sai kích thước (hoặc sai SHA-256) → `OcrModelError`."""
    root = Path(root)
    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OcrModelError(f"Bộ mô hình OCR ở «{root}» thiếu hoặc hỏng {MANIFEST_NAME}.") from exc
    files = manifest.get("files")
    if manifest.get("id") != "ocr-vi" or not isinstance(files, dict) or not files:
        raise OcrModelError(f"Thư mục «{root}» không phải bộ mô hình OCR tiếng Việt.")
    for name, info in files.items():
        target = (root / name).resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file():
            raise OcrModelError(f"Bộ mô hình OCR thiếu tệp «{name}».")
        if target.stat().st_size != int(info.get("size", -1)):
            raise OcrModelError(f"Tệp mô hình «{name}» sai kích thước — hãy tải lại bộ mô hình.")
        if verify_hashes and _sha256(target) != str(info.get("sha256", "")).lower():
            raise OcrModelError(f"Mã SHA-256 của «{name}» không khớp — tệp hỏng, hãy tải lại bộ mô hình.")
    return ModelBundle(root, manifest)


def find_bundle() -> Optional[ModelBundle]:
    """Bộ mô hình dùng được: `QT_PDF_PRO_OCR_MODELS` (nếu đặt) rồi `<dữ liệu>/modules/ocr-vi-<N>`; None nếu chưa cài."""
    override = os.environ.get(MODELS_ENV, "").strip()
    candidates = [Path(override)] if override else []
    candidates.append(bundle_dir())
    for cand in candidates:
        try:
            return read_bundle(cand)
        except OcrModelError:
            continue
    return None


def is_installed() -> bool:
    return find_bundle() is not None


def status() -> Dict:
    """Trạng thái cho CLI / giao diện."""
    bundle = find_bundle()
    return {
        "installed": bundle is not None,
        "path": str(bundle.root) if bundle else str(bundle_dir()),
        "version": BUNDLE_VERSION,
        "download_url": BUNDLE_ASSET.url,
        "download_size": BUNDLE_ASSET.size,
        "installed_size": sum(int(i.get("size", 0)) for i in bundle.manifest.get("files", {}).values()) if bundle else 0,
    }


def _download(asset: uc.ReleaseAsset, dest: Path, progress_cb: Optional[ProgressCallback],
              should_cancel: Optional[CancelCheck], timeout: float) -> None:
    resp = uc._open(asset.url, uc.DOWNLOAD_HOSTS, timeout, "application/octet-stream")
    part = dest.with_name(dest.name + ".part")
    hasher = hashlib.sha256()
    done = 0
    ok = False
    try:
        with open(part, "wb") as fh:
            if progress_cb:
                progress_cb(0, asset.size)
            while True:
                if should_cancel is not None and should_cancel():
                    raise OcrModelCancelled("Đã huỷ tải bộ mô hình OCR.")
                chunk = resp.read(uc.CHUNK_SIZE)
                if not chunk:
                    break
                done += len(chunk)
                if done > asset.size:
                    raise OcrModelError("Tệp mô hình tải về lớn hơn dự kiến — đã huỷ.")
                fh.write(chunk)
                hasher.update(chunk)
                if progress_cb:
                    progress_cb(done, asset.size)
        if done != asset.size:
            raise OcrModelError(
                f"Tải bộ mô hình OCR bị thiếu ({uc.format_size(done)} / {uc.format_size(asset.size)}). Hãy thử lại."
            )
        if hasher.hexdigest() != asset.sha256:
            raise OcrModelError("Mã SHA-256 của bộ mô hình tải về không khớp — tệp hỏng hoặc bị thay đổi, đã xoá.")
        os.replace(part, dest)
        ok = True
    finally:
        resp.close()
        if not ok:
            part.unlink(missing_ok=True)


def _extract(zip_path: Path, target: Path, should_cancel: Optional[CancelCheck]) -> None:
    root = target.resolve()
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                if should_cancel is not None and should_cancel():
                    raise OcrModelCancelled("Đã huỷ cài bộ mô hình OCR.")
                dest = (root / member.filename.replace("\\", "/")).resolve()
                if not dest.is_relative_to(root):
                    raise OcrModelError(f"Tệp mô hình chứa đường dẫn không an toàn: «{member.filename}».")
                zf.extract(member, root)
    except zipfile.BadZipFile as exc:
        raise OcrModelError("Tệp mô hình tải về không phải tệp .zip hợp lệ.") from exc


def install_models(
    progress_cb: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCheck] = None,
    asset: uc.ReleaseAsset = BUNDLE_ASSET,
    timeout: float = DOWNLOAD_TIMEOUT,
) -> ModelBundle:
    """Tải + kiểm + cài bộ mô hình vào `<dữ liệu>/modules/ocr-vi-<N>`; đã cài thì trả về luôn."""
    current = find_bundle()
    if current is not None:
        return current
    folder = modules_dir()
    folder.mkdir(parents=True, exist_ok=True)
    final = bundle_dir()
    staging = folder / f".{BUNDLE_ID}.staging"
    zip_path = folder / asset.name
    shutil.rmtree(staging, ignore_errors=True)
    try:
        try:
            _download(asset, zip_path, progress_cb, should_cancel, timeout)
        except uc.ReleaseNotFound as exc:
            raise OcrModelError("Chưa tìm thấy bộ mô hình OCR trên GitHub (lỗi 404) — hãy thử lại sau.") from exc
        except uc.UpdateError as exc:  # lỗi mạng / host không tin cậy từ update_check._open
            raise OcrModelError(str(exc)) from exc
        staging.mkdir(parents=True)
        _extract(zip_path, staging, should_cancel)
        bundle = read_bundle(staging, verify_hashes=True)
        if int(bundle.manifest.get("version", 0)) != BUNDLE_VERSION:
            raise OcrModelError("Bộ mô hình tải về không đúng phiên bản ứng dụng cần.")
        shutil.rmtree(final, ignore_errors=True)
        os.replace(staging, final)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
    return read_bundle(final)


def remove_models() -> bool:
    """Xoá bộ mô hình đã cài (giải phóng ~100 MB); True nếu có xoá."""
    target = bundle_dir()
    if not target.exists():
        return False
    shutil.rmtree(target)
    return True
