"""Sinh icon ứng dụng `qtpdfpro/ui/assets/app_icon.ico` từ 2 tệp SVG nguồn.

Cỡ ≤ 32 px dùng `app_icon_small.svg` (giản lược để không nhoè), cỡ lớn hơn dùng
`app_icon.svg`. Mỗi cỡ được Qt dựng riêng rồi ghi vào .ico dạng ảnh PNG (Windows Vista+).

    python tools/make_app_icon.py [--preview anh_xem_truoc.png]
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parent.parent / "qtpdfpro" / "ui" / "assets"
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
SMALL_MAX = 32


def render(size: int) -> QImage:
    svg = ASSETS / ("app_icon_small.svg" if size <= SMALL_MAX else "app_icon.svg")
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise SystemExit(f"Không đọc được SVG: {svg}")
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return img


def png_bytes(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def write_ico(path: Path, images: dict[int, bytes]) -> None:
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in sorted(images.items()):
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    path.write_bytes(header + entries + blobs)


def write_preview(path: Path, images: dict[int, QImage]) -> None:
    pad = 16
    width = sum(s for s in SIZES) + pad * (len(SIZES) + 1)
    height = (max(SIZES) + pad * 2) * 2
    sheet = QImage(width, height, QImage.Format.Format_ARGB32)
    painter = QPainter(sheet)
    for row, bg in enumerate(("#F3F3F3", "#202020")):
        top = row * height // 2
        painter.fillRect(0, top, width, height // 2, QColor(bg))
        x = pad
        for s in SIZES:
            painter.drawImage(x, top + pad + max(SIZES) - s, images[s])
            x += s + pad
    painter.end()
    sheet.save(str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preview", help="Lưu thêm ảnh xem trước các cỡ trên nền sáng/tối")
    args = parser.parse_args()
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # cần cho phông chữ «PDF»
    images = {s: render(s) for s in SIZES}
    write_ico(ASSETS / "app_icon.ico", {s: png_bytes(img) for s, img in images.items()})
    images[256].save(str(ASSETS / "app_icon_256.png"))
    if args.preview:
        write_preview(Path(args.preview), images)
    print(f"Đã ghi {ASSETS / 'app_icon.ico'} ({len(SIZES)} cỡ: {', '.join(map(str, SIZES))})")
    del app
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
