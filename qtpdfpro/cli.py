"""Giao diện dòng lệnh (CLI) cho QT PDF Pro.

Hỗ trợ:
  python -m qtpdfpro.cli convert <input.pdf> [-o <output.docx>] [--mode auto|nd30|hybrid|exact|word_com]
                                 [--pages 1-3,5] [--nd30-policy faithful|nd30] [--verify-layout]
  python -m qtpdfpro.cli inspect <input.pdf>
  python -m qtpdfpro.cli nd30 <input.pdf>            # Đối chiếu thể thức Nghị định 30/2020/NĐ-CP
  python -m qtpdfpro.cli verify <input.pdf> <output.docx> [--render]
  python -m qtpdfpro.cli batch <thư mục | a.pdf b.pdf ...> [-o <thư mục ra>] [--mode auto] [--verify-layout]
                               [--recursive] [--report bao_cao.csv] [--json]

Chỉnh sửa PDF (tổ chức trang & chú thích):
  python -m qtpdfpro.cli merge a.pdf b.pdf:1-3 -o gop.pdf [--no-bookmarks]
  python -m qtpdfpro.cli split in.pdf [-o thu_muc] (--every 2 | --ranges "1-3,4-6" | --after 3,7)
  python -m qtpdfpro.cli organize in.pdf --order "3,1-2r90,blank,end" [-o out.pdf]
  python -m qtpdfpro.cli extract in.pdf --pages "1-3,5" [-o out.pdf]
  python -m qtpdfpro.cli annotate in.pdf [-o out.pdf] [--highlight "cụm từ"] [--underline ...] [--strikeout ...]
                                  [--color vang] [--stamp "ĐÃ DUYỆT" --stamp-date] [--ops thao_tac.json] [--flatten]
  python -m qtpdfpro.cli annots in.pdf [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from qtpdfpro import __app_name__, __version__
from qtpdfpro.core import annotations as annots_mod
from qtpdfpro.core import page_ops
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

    _add_edit_commands(sub)
    return parser


def _add_edit_commands(sub) -> None:
    """Lệnh «Chỉnh sửa PDF»: ghép / tách / sắp xếp / trích trang và chú thích."""
    p_merge = sub.add_parser("merge", help="Ghép nhiều tệp PDF thành một (mỗi tệp có thể kèm phạm vi trang: a.pdf:1-3)")
    p_merge.add_argument("inputs", nargs="+", help="Các tệp PDF theo thứ tự ghép")
    p_merge.add_argument("-o", "--output", required=True, help="Tệp PDF kết quả")
    p_merge.add_argument("--no-bookmarks", action="store_true", help="Không tạo mục lục theo từng tệp nguồn")
    p_merge.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    p_split = sub.add_parser("split", help="Tách tệp PDF thành nhiều tệp")
    p_split.add_argument("input_pdf", help="Tệp PDF cần tách")
    p_split.add_argument("-o", "--output-dir", help="Thư mục lưu các phần (mặc định: <tên tệp>_tach cạnh tệp gốc)")
    grp = p_split.add_mutually_exclusive_group(required=True)
    grp.add_argument("--every", type=int, help="Mỗi phần N trang (1 = mỗi trang một tệp)")
    grp.add_argument("--ranges", help="Mỗi khoảng là một tệp, vd '1-3,4-6,7'")
    grp.add_argument("--after", help="Cắt sau các trang, vd '3,7' → 1-3, 4-7, 8-hết")
    p_split.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    p_org = sub.add_parser(
        "organize",
        help="Sắp xếp / xoá / xoay / nhân bản trang, chèn trang trắng theo chuỗi thứ tự",
        description=(
            "Chuỗi thứ tự (số trang tính từ 1, phân tách bằng dấu phẩy): '5', '1-3', '8-6' (đảo), 'end' (trang cuối), "
            "'le'/'chan' (trang lẻ/chẵn), hậu tố xoay 'r90'/'r180'/'r270' (vd '2r90'), 'blank' (trang trắng). "
            "Trang không có trong chuỗi sẽ bị xoá."
        ),
    )
    p_org.add_argument("input_pdf", help="Tệp PDF nguồn")
    p_org.add_argument("--order", required=True, help="Chuỗi thứ tự trang, vd '3,1-2r90,blank,end'")
    p_org.add_argument("-o", "--output", help="Tệp kết quả (mặc định: <tên>_sap_xep.pdf)")
    p_org.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    p_ext = sub.add_parser("extract", help="Trích các trang chọn thành tệp PDF mới")
    p_ext.add_argument("input_pdf", help="Tệp PDF nguồn")
    p_ext.add_argument("-p", "--pages", required=True, help="Các trang cần trích, vd '1-3,5'")
    p_ext.add_argument("-o", "--output", help="Tệp kết quả (mặc định: <tên>_trich.pdf)")
    p_ext.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    p_ann = sub.add_parser("annotate", help="Thêm chú thích: tô sáng/gạch chân cụm từ, dấu đóng, thao tác JSON")
    p_ann.add_argument("input_pdf", help="Tệp PDF nguồn")
    p_ann.add_argument("-o", "--output", help="Tệp kết quả (mặc định: <tên>_chu_thich.pdf; trùng tệp gốc = ghi bổ sung)")
    p_ann.add_argument("--highlight", action="append", default=[], metavar="CỤM_TỪ", help="Tô sáng mọi chỗ có cụm từ")
    p_ann.add_argument("--underline", action="append", default=[], metavar="CỤM_TỪ", help="Gạch chân cụm từ")
    p_ann.add_argument("--strikeout", action="append", default=[], metavar="CỤM_TỪ", help="Gạch ngang cụm từ")
    p_ann.add_argument("--color", help="Màu: #RRGGBB hoặc vang, xanhla, xanhtroi, hong, cam, do, xanh, tim, den")
    p_ann.add_argument("--opacity", type=float, default=1.0, help="Độ đậm 0.05–1 (mặc định 1)")
    p_ann.add_argument("-p", "--pages", default="", help="Chỉ đánh dấu trên các trang này (vd '1-2')")
    p_ann.add_argument("--stamp", metavar="NHÃN", help="Đóng dấu, vd 'ĐÃ DUYỆT', 'BẢN SAO', 'MẬT'")
    p_ann.add_argument("--stamp-page", type=int, default=1, help="Trang đóng dấu (mặc định 1)")
    p_ann.add_argument("--stamp-at", help="Tâm dấu 'x,y' (pt, gốc trên-trái; mặc định lề trên bên phải)")
    p_ann.add_argument("--stamp-date", action="store_true", help="Thêm dòng ngày hôm nay vào dấu")
    p_ann.add_argument("--ops", help="Tệp JSON danh sách thao tác chú thích (xem annotations.apply_operations)")
    p_ann.add_argument("--author", help="Tên người chú thích (mặc định: tên đăng nhập Windows)")
    p_ann.add_argument("--flatten", action="store_true", help="Làm phẳng chú thích vào nội dung trang")
    p_ann.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    p_list = sub.add_parser("annots", help="Liệt kê chú thích trong tệp PDF")
    p_list.add_argument("input_pdf", help="Tệp PDF")
    p_list.add_argument("--json", action="store_true", help="In kết quả dạng JSON")


def _print_organize(res: page_ops.OrganizeResult, title: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
        return
    print(f"{title}: {len(res.output_paths)} tệp, {res.total_pages} trang")
    for path, n in zip(res.output_paths, res.page_counts):
        print(f"  - {path} ({n} trang)")


def _run_annotate(args: argparse.Namespace) -> int:
    import fitz

    src = Path(args.input_pdf).resolve()
    dst = Path(args.output).resolve() if args.output else src.with_name(f"{src.stem}_chu_thich.pdf")
    author = args.author if args.author is not None else annots_mod.default_author()
    opacity = max(0.05, min(1.0, args.opacity))
    doc = fitz.open(str(src))
    try:
        if doc.needs_pass:
            raise PermissionError("Tệp PDF được bảo vệ bằng mật khẩu.")
        pages = page_ops.parse_page_selection(args.pages, doc.page_count) if args.pages.strip() else None
        added = 0
        marks = (
            ("highlight", args.highlight, "#FACC15"),
            ("underline", args.underline, "#16A34A"),
            ("strikeout", args.strikeout, "#DC2626"),
        )
        for kind, needles, default_color in marks:
            for needle in needles:
                color = annots_mod.color_hex(annots_mod.parse_color(args.color, default_color))
                style = annots_mod.AnnotStyle(color=color, opacity=opacity)
                n = annots_mod.mark_text(doc, needle, kind, style, pages, author)
                if n == 0 and not args.json:
                    print(f"  ! Không tìm thấy «{needle}»")
                added += n
        if args.ops:
            ops = json.loads(Path(args.ops).read_text(encoding="utf-8-sig"))
            if isinstance(ops, dict):
                ops = ops.get("operations") or ops.get("ops") or []
            added += annots_mod.apply_operations(doc, ops, author)
        if args.stamp:
            page = doc[max(1, min(doc.page_count, args.stamp_page)) - 1]
            if args.stamp_at:
                x, y = (float(v) for v in args.stamp_at.split(","))
            else:
                x, y = page.rect.width - 110, 32  # lề trên bên phải, không đè Quốc hiệu
            label = args.stamp.strip()
            preset = dict(annots_mod.STAMP_PRESETS).get(annots_mod._nfc(label).upper(), "#DC2626")
            color = annots_mod.color_hex(annots_mod.parse_color(args.color or preset))
            style = annots_mod.AnnotStyle(color=color, font_size=18, opacity=opacity)
            date_text = annots_mod.stamp_date_text() if args.stamp_date else None
            annots_mod.add_stamp(page, fitz.Point(x, y) * page.derotation_matrix, label, style, author, date_text)
            added += 1
        if args.flatten:
            annots_mod.flatten_annotations(doc)
        if dst == src:
            doc.save(str(src), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        else:
            page_ops.save_pdf(doc, dst)
    finally:
        doc.close()
    if args.json:
        payload = {"output": str(dst), "added": added, "flattened": bool(args.flatten)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Đã thêm {added} chú thích → {dst}" + (" (đã làm phẳng)" if args.flatten else ""))
    return 0


def _run_edit_command(args: argparse.Namespace) -> int:
    """Chạy các lệnh chỉnh sửa PDF; trả về mã thoát."""
    try:
        if args.command == "merge":
            res = page_ops.merge_pdfs(args.inputs, args.output, bookmarks=not args.no_bookmarks)
            _print_organize(res, "Đã ghép", args.json)
        elif args.command == "split":
            src = Path(args.input_pdf).resolve()
            out_dir = Path(args.output_dir) if args.output_dir else src.with_name(f"{src.stem}_tach")
            after = [int(x) for x in args.after.replace(";", ",").split(",") if x.strip()] if args.after else None
            res = page_ops.split_pdf(src, out_dir, every=args.every, ranges=args.ranges, after=after)
            _print_organize(res, "Đã tách", args.json)
        elif args.command == "organize":
            src = Path(args.input_pdf).resolve()
            out = args.output or src.with_name(f"{src.stem}_sap_xep.pdf")
            _print_organize(page_ops.organize_pdf(src, args.order, out), "Đã sắp xếp", args.json)
        elif args.command == "extract":
            src = Path(args.input_pdf).resolve()
            out = args.output or src.with_name(f"{src.stem}_trich.pdf")
            _print_organize(page_ops.extract_pages(src, args.pages, out), "Đã trích", args.json)
        elif args.command == "annotate":
            return _run_annotate(args)
        elif args.command == "annots":
            import fitz

            with fitz.open(str(Path(args.input_pdf).resolve())) as doc:
                items = annots_mod.list_annotations(doc)
            if args.json:
                print(json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2))
            else:
                print(f"{Path(args.input_pdf).name}: {len(items)} chú thích")
                for i in items:
                    extra = f" — {i.content}" if i.content else ""
                    who = f" ({i.author})" if i.author else ""
                    print(f"  [Tr. {i.page_index + 1}] {i.label}{who}{extra}")
    except (page_ops.PageOpsError, annots_mod.AnnotationError, FileNotFoundError, PermissionError,
            ValueError, OSError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    return 0


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

    if args.command in ("merge", "split", "organize", "extract", "annotate", "annots"):
        return _run_edit_command(args)

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
