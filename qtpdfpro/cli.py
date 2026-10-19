"""Giao diện dòng lệnh (CLI) cho QT PDF Pro.

Hỗ trợ:
  python -m qtpdfpro.cli convert <input.pdf> [-o <output.docx>] [--mode hybrid|exact|auto|word_com] [--pages 1-3,5]
  python -m qtpdfpro.cli inspect <input.pdf>
  python -m qtpdfpro.cli verify <input.pdf> <output.docx>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from qtpdfpro import __app_name__, __version__
from qtpdfpro.core.converter import (
    ConversionError,
    ConversionOptions,
    convert_pdf_to_docx,
    parse_page_range,
)
from qtpdfpro.core.fidelity import evaluate_conversion_fidelity
from qtpdfpro.core.reader import PDFDocumentReader


def _ensure_utf8_console() -> None:
    """Đảm bảo stdout/stderr trên Windows hỗ trợ in tiếng Việt UTF-8 không lỗi."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qtpdfpro-cli",
        description=f"{__app_name__} v{__version__} — Đọc PDF & Chuyển đổi PDF sang DOCX chuẩn xác.",
    )
    parser.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # Lệnh convert
    p_conv = sub.add_parser("convert", help="Chuyển đổi tệp PDF sang Word (.docx)")
    p_conv.add_argument("input_pdf", help="Đường dẫn tệp PDF đầu vào")
    p_conv.add_argument("-o", "--output", help="Đường dẫn tệp DOCX đầu ra (mặc định: cùng tên với PDF)")
    p_conv.add_argument(
        "-m",
        "--mode",
        choices=["auto", "hybrid", "exact", "word_com"],
        default="hybrid",
        help="Chế độ chuyển đổi: hybrid (cấu trúc chuẩn), exact (vị trí 1:1), auto, word_com",
    )
    p_conv.add_argument(
        "-p",
        "--pages",
        default="",
        help="Phạm vi trang cần chuyển (1-based, vd: '1-3,5'). Bỏ trống = tất cả trang.",
    )
    p_conv.add_argument(
        "--dpi",
        type=int,
        default=180,
        help="Độ phân giải lớp đồ hoạ nền cho chế độ exact (mặc định: 180 DPI)",
    )
    p_conv.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    # Lệnh inspect
    p_insp = sub.add_parser("inspect", help="Phân tích thông tin và bố cục tệp PDF")
    p_insp.add_argument("input_pdf", help="Đường dẫn tệp PDF cần phân tích")
    p_insp.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    # Lệnh verify
    p_ver = sub.add_parser("verify", help="Kiểm định độ chính xác giữa PDF gốc và DOCX")
    p_ver.add_argument("input_pdf", help="Đường dẫn tệp PDF gốc")
    p_ver.add_argument("output_docx", help="Đường dẫn tệp DOCX đã chuyển đổi")
    p_ver.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "convert":
        src = Path(args.input_pdf).resolve()
        dst = Path(args.output).resolve() if args.output else src.with_suffix(".docx")

        try:
            with PDFDocumentReader(src) as reader:
                total_pages = reader.page_count
            pages_list = (
                parse_page_range(args.pages, total_pages) if args.pages.strip() else None
            )
            opts = ConversionOptions(
                mode=args.mode,
                pages=pages_list,
                exact_background_dpi=args.dpi,
            )
            res = convert_pdf_to_docx(src, dst, options=opts)
        except (ConversionError, FileNotFoundError, PermissionError) as exc:
            print(f"Lỗi: {exc}", file=sys.stderr)
            return 1

        if args.json:
            payload = {
                "pdf_path": res.pdf_path,
                "docx_path": res.docx_path,
                "mode_used": res.mode_used,
                "pages_converted": res.pages_converted,
                "elapsed_seconds": res.elapsed_seconds,
                "overall_score": res.fidelity.overall_score,
                "word_retention_ratio": res.fidelity.word_retention_ratio,
                "docx_tables": res.fidelity.docx_tables,
                "docx_images": res.fidelity.docx_images,
                "docx_fonts": res.fidelity.docx_fonts,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Đã chuyển đổi thành công: {res.docx_path}")
            print(f"  - Chế độ sử dụng : {res.mode_used}")
            print(f"  - Số trang chuyển: {res.pages_converted} trang ({res.elapsed_seconds:.2f} giây)")
            print(f"  - Điểm chuẩn xác : {res.fidelity.overall_score:.1f}% "
                  f"(Giữ chữ: {res.fidelity.word_retention_ratio * 100:.1f}%)")
            print(f"  - Phông chữ DOCX : {', '.join(res.fidelity.docx_fonts) or 'Mặc định'}")
        return 0

    if args.command == "inspect":
        src = Path(args.input_pdf).resolve()
        with PDFDocumentReader(src) as reader:
            info = reader.get_info()
            layouts = [reader.get_page_layout(i) for i in range(reader.page_count)]
            toc = reader.get_bookmarks()

        if args.json:
            payload = {
                "file_name": info.file_name,
                "page_count": info.page_count,
                "title": info.title,
                "author": info.author,
                "bookmarks": len(toc),
                "pages": [
                    {
                        "page": ly.page_index + 1,
                        "size_pt": [round(ly.width, 1), round(ly.height, 1)],
                        "text_blocks": ly.text_block_count,
                        "tables": ly.table_count,
                        "images": ly.image_count,
                        "vectors": ly.vector_count,
                        "fonts": ly.fonts_used,
                        "recommended_mode": ly.recommended_mode,
                    }
                    for ly in layouts
                ],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Tệp PDF: {info.file_name} ({info.page_count} trang, {info.file_size_bytes:,} bytes)")
            print(f"Tiêu đề: {info.title or '(Trống)'} | Tác giả: {info.author or '(Trống)'}")
            for ly in layouts:
                print(
                    f"  Trang {ly.page_index + 1}: {ly.width:.0f}×{ly.height:.0f}pt | "
                    f"Khối chữ: {ly.text_block_count} | Bảng: {ly.table_count} | "
                    f"Ảnh: {ly.image_count} | Vector: {ly.vector_count} | "
                    f"Phông: {', '.join(ly.fonts_used) or 'Không có'}"
                )
        return 0

    if args.command == "verify":
        rep = evaluate_conversion_fidelity(args.input_pdf, args.output_docx)
        if args.json:
            print(
                json.dumps(
                    {
                        "overall_score": rep.overall_score,
                        "word_retention_ratio": rep.word_retention_ratio,
                        "char_retention_ratio": rep.char_retention_ratio,
                        "page_size_match": rep.page_size_match,
                        "docx_tables": rep.docx_tables,
                        "docx_images": rep.docx_images,
                        "docx_fonts": rep.docx_fonts,
                        "notes": rep.notes,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"Điểm chuẩn xác: {rep.overall_score:.1f}/100")
            print(f"  - Tỷ lệ giữ từ vựng: {rep.word_retention_ratio * 100:.1f}% ({rep.docx_word_count}/{rep.pdf_word_count} từ)")
            print(f"  - Tỷ lệ giữ ký tự  : {rep.char_retention_ratio * 100:.1f}%")
            print(f"  - Khớp cỡ trang    : {'Có' if rep.page_size_match else 'Không'}")
            print(f"  - Bảng / Khung / Ảnh: {rep.docx_tables} bảng, {rep.docx_frames} khung, {rep.docx_images} ảnh")
            for note in rep.notes:
                print(f"  * {note}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
