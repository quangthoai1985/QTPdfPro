"""Giao diện dòng lệnh (CLI) cho QT PDF Pro.

Hỗ trợ:
  python -m qtpdfpro.cli convert <input.pdf> [-o <output.docx>] [--mode auto|nd30|hybrid|exact|word_com]
                                 [--pages 1-3,5] [--nd30-policy faithful|nd30] [--verify-layout]
  python -m qtpdfpro.cli inspect <input.pdf>
  python -m qtpdfpro.cli nd30 <input.pdf>            # Đối chiếu thể thức Nghị định 30/2020/NĐ-CP
  python -m qtpdfpro.cli verify <input.pdf> <output.docx> [--render]
  python -m qtpdfpro.cli batch <thư mục | a.pdf b.pdf ...> [-o <thư mục ra>] [--mode auto] [--verify-layout]
                               [--recursive] [--report bao_cao.csv] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from qtpdfpro import __app_name__, __version__
from qtpdfpro.core.batch import (
    STATUS_FAILED,
    STATUS_OK,
    BatchItemResult,
    BatchProgress,
    collect_pdf_paths,
    convert_batch,
    write_batch_report,
)
from qtpdfpro.core.converter import (
    ConversionError,
    ConversionOptions,
    convert_pdf_to_docx,
    parse_page_range,
)
from qtpdfpro.core.fidelity import evaluate_conversion_fidelity
from qtpdfpro.core.layout_verify import LayoutVerifyReport, verify_docx_layout
from qtpdfpro.core.nd30_engine import analyze_pdf_nd30
from qtpdfpro.core.nd30_standard import build_docx_plan
from qtpdfpro.core.reader import PDFDocumentReader

_STATUS_ICON = {"ok": "✔", "warn": "!", "fail": "✘", "na": "–"}


def _print_layout_check(lc: LayoutVerifyReport) -> None:
    print(f"  - Kiểm chứng Word : {lc.verdict_text}", end="")
    if lc.available:
        print(
            f" (điểm {lc.score:.1f}; {lc.docx_pages}/{lc.pdf_pages} trang; "
            f"{lc.matched_lines}/{lc.pdf_lines} dòng khớp; lệch dọc tối đa {lc.max_dy_pt:.2f} pt, "
            f"ngang {lc.max_dx_pt:.2f} pt)"
        )
        for smp in lc.samples[:5]:
            print(f"      · {smp}")
    else:
        print(f" — {lc.note}")


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
        choices=["auto", "nd30", "hybrid", "exact", "word_com"],
        default="hybrid",
        help=(
            "Chế độ chuyển đổi: nd30 (văn bản hành chính chuẩn NĐ30), hybrid (cấu trúc pdf2docx), "
            "exact (vị trí 1:1), auto (tự chọn — văn bản hành chính dùng nd30), word_com"
        ),
    )
    p_conv.add_argument(
        "--nd30-policy",
        choices=["faithful", "nd30"],
        default="faithful",
        help=(
            "Chế độ nd30: faithful = giữ đúng bố cục PDF, chỉ ước lượng về giá trị chuẩn khi sai số đo nhỏ "
            "(mặc định); nd30 = ép chuẩn hoá lề/cỡ chữ/giãn dòng/cách đoạn theo NĐ30 (có thể đổi dàn trang)"
        ),
    )
    p_conv.add_argument(
        "--verify-layout",
        action="store_true",
        help="Dựng lại DOCX bằng Microsoft Word và so vị trí từng dòng với PDF gốc",
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

    # Lệnh nd30
    p_nd = sub.add_parser("nd30", help="Đối chiếu thể thức văn bản hành chính theo Nghị định 30/2020/NĐ-CP")
    p_nd.add_argument("input_pdf", help="Đường dẫn tệp PDF cần đối chiếu")
    p_nd.add_argument("-p", "--pages", default="", help="Phạm vi trang (1-based). Bỏ trống = tất cả trang.")
    p_nd.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    # Lệnh verify
    p_ver = sub.add_parser("verify", help="Kiểm định độ chính xác giữa PDF gốc và DOCX")
    p_ver.add_argument("input_pdf", help="Đường dẫn tệp PDF gốc")
    p_ver.add_argument("output_docx", help="Đường dẫn tệp DOCX đã chuyển đổi")
    p_ver.add_argument(
        "--render",
        action="store_true",
        help="Dựng DOCX bằng Microsoft Word rồi so vị trí từng dòng với PDF (cần MS Word)",
    )
    p_ver.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    # Lệnh batch
    p_bat = sub.add_parser("batch", help="Chuyển đổi hàng loạt nhiều tệp PDF sang Word (.docx)")
    p_bat.add_argument("inputs", nargs="+", help="Các tệp PDF và/hoặc thư mục chứa tệp PDF")
    p_bat.add_argument(
        "-o",
        "--output-dir",
        help="Thư mục lưu các tệp DOCX (mặc định: cạnh từng tệp PDF gốc)",
    )
    p_bat.add_argument(
        "-m",
        "--mode",
        choices=["auto", "nd30", "hybrid", "exact", "word_com"],
        default="auto",
        help="Chế độ chuyển đổi cho mọi tệp (mặc định auto — văn bản hành chính dùng nd30)",
    )
    p_bat.add_argument(
        "--nd30-policy",
        choices=["faithful", "nd30"],
        default="faithful",
        help="Chính sách engine nd30: faithful = giữ đúng bố cục PDF (mặc định), nd30 = ép chuẩn hoá",
    )
    p_bat.add_argument(
        "--verify-layout",
        action="store_true",
        help="Kiểm chứng từng DOCX bằng Microsoft Word (chậm, cần MS Word)",
    )
    p_bat.add_argument("-r", "--recursive", action="store_true", help="Duyệt cả thư mục con")
    p_bat.add_argument("--dpi", type=int, default=180, help="Độ phân giải lớp nền chế độ exact (mặc định 180)")
    p_bat.add_argument("--report", help="Lưu báo cáo tổng hợp ra tệp .csv hoặc .json")
    p_bat.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    return parser


def _print_batch_item(item: BatchItemResult, total: int) -> None:
    head = f"[{item.index + 1}/{total}] {Path(item.pdf_path).name}"
    if not item.ok:
        print(f"  ✘ {head} — {item.status_text}: {item.error}" if item.error else f"  – {head} — {item.status_text}")
        return
    line = f"  ✔ {head} → {Path(item.docx_path).name} | {item.mode_used} | chuẩn xác {item.fidelity_score:.1f}%"
    if item.nd30_score is not None:
        line += f" | thể thức NĐ30 {item.nd30_score:.1f}%"
    if item.layout_verdict is not None:
        line += f" | kiểm chứng Word: {item.layout_verdict_text}"
    print(line + f" ({item.elapsed_seconds:.1f} giây)")


def _run_batch(args: argparse.Namespace) -> int:
    pdfs = collect_pdf_paths(args.inputs, recursive=args.recursive)
    if not pdfs:
        print("Lỗi: không tìm thấy tệp PDF nào trong các đường dẫn đã cho.", file=sys.stderr)
        return 1
    opts = ConversionOptions(
        mode=args.mode,
        exact_background_dpi=args.dpi,
        nd30_policy=args.nd30_policy,
        verify_layout=args.verify_layout,
    )

    def _on_progress(ev: BatchProgress) -> None:
        # Chỉ in khi một tệp vừa kết thúc; chế độ --json giữ stdout sạch cho JSON
        if not args.json and ev.item is not None and ev.item.status in (STATUS_OK, STATUS_FAILED):
            _print_batch_item(ev.item, ev.total_files)

    if not args.json:
        dest = Path(args.output_dir).resolve() if args.output_dir else "cạnh từng tệp PDF gốc"
        print(f"Chuyển đổi hàng loạt {len(pdfs)} tệp PDF (chế độ {args.mode}) → {dest}")
    report = convert_batch(pdfs, args.output_dir, options=opts, progress_cb=_on_progress)

    report_path: Optional[Path] = None
    if args.report:
        try:
            report_path = write_batch_report(report, args.report)
        except OSError as exc:
            print(f"Lỗi: không lưu được báo cáo {args.report}: {exc}", file=sys.stderr)

    if args.json:
        payload = report.to_dict()
        if report_path is not None:
            payload["report_path"] = str(report_path)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        summary = (
            f"Kết quả: {report.ok_count}/{report.total} tệp thành công, {report.failed_count} thất bại "
            f"({report.elapsed_seconds:.1f} giây)"
        )
        if report.average_fidelity is not None:
            summary += f"; điểm chuẩn xác trung bình {report.average_fidelity:.1f}%"
        if report.average_nd30 is not None:
            summary += f"; thể thức NĐ30 trung bình {report.average_nd30:.1f}%"
        print(summary)
        if report_path is not None:
            print(f"Đã lưu báo cáo tổng hợp: {report_path}")
    return 0 if report.failed_count == 0 else 1


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
                nd30_policy=args.nd30_policy,
                verify_layout=args.verify_layout,
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
                "notes": res.notes,
            }
            if res.nd30_report is not None:
                payload["nd30_score"] = res.nd30_report.score
                payload["nd30_report"] = res.nd30_report.to_dict()
            if res.nd30_plan is not None:
                payload["nd30_plan"] = res.nd30_plan.to_dict()
            if res.layout_check is not None:
                payload["layout_check"] = res.layout_check.to_dict()
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Đã chuyển đổi thành công: {res.docx_path}")
            print(f"  - Chế độ sử dụng : {res.mode_used}")
            print(f"  - Số trang chuyển: {res.pages_converted} trang ({res.elapsed_seconds:.2f} giây)")
            print(f"  - Điểm chuẩn xác : {res.fidelity.overall_score:.1f}% "
                  f"(Giữ chữ: {res.fidelity.word_retention_ratio * 100:.1f}%)")
            print(f"  - Phông chữ DOCX : {', '.join(res.fidelity.docx_fonts) or 'Mặc định'}")
            if res.nd30_report is not None:
                print(
                    f"  - Thể thức NĐ30  : {res.nd30_report.score:.1f}% "
                    f"({res.nd30_report.ok_count} đạt, {res.nd30_report.warn_count} cần xem, "
                    f"{res.nd30_report.fail_count} chưa đạt)"
                )
            if res.nd30_plan is not None:
                pl = res.nd30_plan
                print(
                    f"  - Lề DOCX (mm)   : trên {pl.margin_top_mm:g}, dưới {pl.margin_bottom_mm:g}, "
                    f"trái {pl.margin_left_mm:g}, phải {pl.margin_right_mm:g}"
                )
            if res.layout_check is not None:
                _print_layout_check(res.layout_check)
            for note in res.notes:
                print(f"  * {note}")
        return 0

    if args.command == "batch":
        return _run_batch(args)

    if args.command == "nd30":
        src = Path(args.input_pdf).resolve()
        try:
            with PDFDocumentReader(src) as reader:
                total_pages = reader.page_count
            pages_list = parse_page_range(args.pages, total_pages) if args.pages.strip() else None
            ad, rep = analyze_pdf_nd30(src, pages=pages_list)
        except (ConversionError, FileNotFoundError, PermissionError, ValueError) as exc:
            print(f"Lỗi: {exc}", file=sys.stderr)
            return 1
        plan = build_docx_plan(ad, "faithful")
        if args.json:
            payload = rep.to_dict()
            payload["docx_plan"] = plan.to_dict()
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            kind = "Văn bản hành chính" if rep.is_admin_document else "Không nhận ra văn bản hành chính"
            print(f"Đối chiếu thể thức NĐ30: {src.name} — {kind}")
            print(
                f"Điểm thể thức: {rep.score:.1f}% ({rep.ok_count} đạt, {rep.warn_count} cần xem, "
                f"{rep.fail_count} chưa đạt)"
            )
            for c in rep.checks:
                line = f"  [{_STATUS_ICON.get(c.status, '?')}] {c.name}: {c.measured}  (quy định: {c.expected})"
                if c.note:
                    line += f" — {c.note}"
                print(line)
            print(
                f"Thông số Word ước lượng: lề trên {plan.margin_top_mm:g} mm, dưới {plan.margin_bottom_mm:g} mm, "
                f"trái {plan.margin_left_mm:g} mm, phải {plan.margin_right_mm:g} mm; cỡ chữ {plan.body_size:g} pt; "
                + (
                    f"giãn dòng {plan.line_multiple:g} lines; "
                    if plan.line_exact_pt is None
                    else f"giãn dòng Exactly {plan.line_exact_pt:g} pt; "
                )
                + f"cách đoạn {plan.para_spacing_pt:g} pt; thụt đầu dòng {plan.first_indent_mm:g} mm."
            )
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
        layout_check = verify_docx_layout(args.input_pdf, args.output_docx) if args.render else None
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
                        "layout_check": layout_check.to_dict() if layout_check else None,
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
            if layout_check is not None:
                _print_layout_check(layout_check)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
