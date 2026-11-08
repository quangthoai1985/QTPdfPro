"""Tải biểu tượng Lucide (lucide-static, ghim phiên bản) vào qtpdfpro/ui/assets/icons.

Chạy một lần lúc phát triển: `python tools/fetch_lucide_icons.py`. Tên không tồn tại → in tên và thoát mã 1.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qtpdfpro.ui.icons import ICON_DIR, ICON_NAMES  # noqa: E402

LUCIDE_VERSION = "0.460.0"
URL = "https://cdn.jsdelivr.net/npm/lucide-static@{v}/icons/{name}.svg"
LICENSE_URL = "https://cdn.jsdelivr.net/npm/lucide-static@{v}/LICENSE"


def _get(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(f"Chỉ chấp nhận https: {url}")
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    for name in ICON_NAMES:
        try:
            text = _get(URL.format(v=LUCIDE_VERSION, name=name)).decode("utf-8")
        except urllib.error.HTTPError:
            missing.append(name)
            continue
        if "<svg" not in text[:400]:  # tệp lucide-static mở đầu bằng dòng chú thích giấy phép rồi tới <svg
            missing.append(name)
            continue
        (ICON_DIR / f"{name}.svg").write_text(text, encoding="utf-8", newline="\n")
    if missing:
        print("Không tìm thấy biểu tượng Lucide:", ", ".join(missing))
        return 1
    lic = _get(LICENSE_URL.format(v=LUCIDE_VERSION)).decode("utf-8")
    (ICON_DIR / "LICENSE-lucide.txt").write_text(
        f"lucide-static {LUCIDE_VERSION}\n\n{lic}", encoding="utf-8", newline="\n"
    )
    print(f"Đã tải {len(ICON_NAMES)} biểu tượng (lucide-static {LUCIDE_VERSION}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
