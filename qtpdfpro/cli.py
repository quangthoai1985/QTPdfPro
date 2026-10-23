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

Cập nhật (GitHub Release):
  python -m qtpdfpro.cli update --check [--json]
  python -m qtpdfpro.cli update --download [-o thu_muc] [--json]
Liên kết tệp .pdf với Windows (theo người dùng, không cần quyền quản trị):
  python -m qtpdfpro.cli assoc [--status] [--json]                 # đã đăng ký / đã là trình mở PDF mặc định chưa
  python -m qtpdfpro.cli assoc --register --exe dist/QTPdfPro/QTPdfPro.exe     # ghi ProgID + Capabilities (HKCU)
  python -m qtpdfpro.cli assoc --open-settings                     # mở trang «Ứng dụng mặc định» của QT PDF Pro
In tài liệu:
  python -m qtpdfpro.cli print in.pdf --pages "1-3,5,8-" --to-pdf ban_in.pdf     # dựng bản in ra PDF, không cần máy in
  python -m qtpdfpro.cli print in.pdf --printer "Canon LBP2900" [--copies 2] [--duplex long] [--grayscale]
  python -m qtpdfpro.cli print in.pdf --plan [--paper A4 --orientation auto --scale fit] [--json]
  python -m qtpdfpro.cli print --list-printers
Công cụ văn phòng (nén, dấu nước, đánh số trang, mật khẩu — mọi lệnh có --json, --password, tệp ký số cần --force):
  python -m qtpdfpro.cli compress in.pdf [-o out.pdf] [--level nhe|vua|manh]
  python -m qtpdfpro.cli watermark in.pdf --text "BẢN SAO" [--size 56] [--opacity 0.2] [--angle 45] [--color do]
                                   [--font sans|serif] [--tile] [--behind] [--pages 1-3]
  python -m qtpdfpro.cli number in.pdf [--preset nd30] [--format "Trang {n} / {total}"] [--position bottom-center]
                                [--start 1] [--skip-first] [--size 12] [--font serif] [--margin 10] [--pages 2-5]
  python -m qtpdfpro.cli protect in.pdf [--user-password MK_MO] [--owner-password MK_CHU] [--no-print] [--no-copy]
                                 [--no-modify] [--no-annotate]
  python -m qtpdfpro.cli unlock in.pdf --password MK [-o out.pdf]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from qtpdfpro import __app_name__, __version__
from qtpdfpro.core import annotations as annots_mod
from qtpdfpro.core import compress as compress_mod
from qtpdfpro.core import page_ops, page_stamp, pdf_security
from qtpdfpro.core import printing
from qtpdfpro.core import file_assoc, fill_sign, update_check
from qtpdfpro.core.pdf_io import PdfToolError, ToolResult, format_size
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
    _add_fill_sign_commands(sub)
    _add_update_command(sub)
    _add_assoc_command(sub)
    _add_print_command(sub)
    _add_office_commands(sub)
    return parser


def _add_print_command(sub) -> None:
    """Lệnh «In tài liệu»: ra tệp PDF bản in (kiểm tra không cần máy in) hoặc gửi tới máy in."""
    p = sub.add_parser(
        "print",
        help="In tài liệu PDF ra máy in, hoặc dựng bản in thành tệp PDF",
        description=(
            "Khoảng trang (số trang tính từ 1): '1-3,5', '8-' (từ trang 8 tới hết), '-3', 'end', 'le'/'chan'. "
            "Phải chọn một đích: --to-pdf, --printer, --plan hoặc --list-printers (không tự in ra máy in mặc định)."
        ),
    )
    p.add_argument("input_pdf", nargs="?", help="Tệp PDF cần in")
    p.add_argument("-p", "--pages", default="", help="Khoảng trang cần in (bỏ trống = tất cả)")
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--to-pdf", metavar="OUT.pdf", help="Dựng bản in (ảnh trang đã dàn khổ giấy) thành tệp PDF")
    dest.add_argument("--printer", metavar="TÊN", help="Gửi tới máy in (dùng 'mac-dinh' cho máy in mặc định của Windows)")
    dest.add_argument("--plan", action="store_true", help="Chỉ xem kế hoạch in (hướng, tỷ lệ, xoay từng tờ)")
    dest.add_argument("--list-printers", action="store_true", help="Liệt kê máy in đã cài")
    p.add_argument("--paper", choices=list(printing.PAPER_SIZES), default="A4", help="Khổ giấy (mặc định A4)")
    p.add_argument("--orientation", choices=list(printing.ORIENTATIONS), default="auto",
                   help="Hướng giấy: auto = theo đa số trang (mặc định)")
    p.add_argument("--scale", choices=list(printing.SCALE_MODES), default="fit",
                   help="fit = vừa khổ giấy (mặc định), actual = cỡ thật, shrink = chỉ thu nhỏ trang quá khổ")
    p.add_argument("--no-auto-rotate", action="store_true", help="Không xoay trang khác hướng giấy")
    p.add_argument("--grayscale", action="store_true", help="In đen trắng (thang xám)")
    p.add_argument("--duplex", choices=list(printing.DUPLEX_MODES), default="none",
                   help="In 2 mặt: long = lật cạnh dài, short = lật cạnh ngắn")
    p.add_argument("--copies", type=int, default=1, help="Số bản (mặc định 1)")
    p.add_argument("--no-collate", action="store_true", help="Không in trọn từng bộ (1-1, 2-2…)")
    p.add_argument("--subset", choices=list(printing.SUBSETS), default="all", help="Chỉ trang lẻ / chẵn")
    p.add_argument("--reverse", action="store_true", help="In ngược thứ tự")
    p.add_argument("--no-annots", action="store_true", help="Không in chú thích, con dấu, chữ ký")
    p.add_argument("--dpi", type=int, help="DPI ảnh trang (--to-pdf mặc định 300; máy in: trần 300–600, mặc định 600)")
    p.add_argument("--json", action="store_true", help="In kết quả dạng JSON")


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


def _add_fill_sign_commands(sub) -> None:
    """Lệnh «fill» (Điền & Ký) và «signature» (thư viện chữ ký, tách nền ảnh chụp)."""
    p = sub.add_parser(
        "fill",
        help="Điền & Ký: gõ chữ vào dòng chấm, dấu ✓ ✕ ● ─, ngày tháng, chữ ký hình ảnh",
        description="Toạ độ là pt trên trang đang hiển thị (gốc trên-trái); mỗi mục dạng 'TRANG:X,Y[:NỘI_DUNG]'. "
                    "Chữ & ngày tự bắt vào dòng chấm «……» / gạch dưới / đường kẻ gần điểm đó.",
    )
    p.add_argument("input_pdf", help="Tệp PDF nguồn")
    p.add_argument("-o", "--output", help="Tệp kết quả (mặc định: <tên>_da_dien.pdf; trùng tệp gốc = ghi bổ sung)")
    p.add_argument("--text", action="append", default=[], metavar="TRANG:X,Y:CHỮ", help="Gõ chữ, vd '1:200,97:Nguyễn Văn A'")
    for mark, (symbol, name) in fill_sign.MARKS.items():
        p.add_argument(f"--{mark}", action="append", default=[], metavar="TRANG:X,Y", help=f"{name} {symbol}")
    p.add_argument("--date", action="append", default=[], metavar="TRANG:X,Y", help="Ghi ngày hôm nay")
    p.add_argument("--date-format", default="dmy", choices=[k for k, _f in fill_sign.DATE_FORMATS],
                   help="Mẫu ngày: dmy=23/10/2026, nd30=ngày 23 tháng 10 năm 2026, nd30_cap, dmy_dash, dmy_dot")
    p.add_argument("--sign", action="append", default=[], metavar="TRANG:X,Y", help="Đặt chữ ký (tâm tại X,Y)")
    p.add_argument("--initials", action="append", default=[], metavar="TRANG:X,Y", help="Đặt chữ ký nháy")
    p.add_argument("--signature-id", help="Mã chữ ký trong thư viện (xem 'signature list')")
    p.add_argument("--signature-image", help="Ảnh chữ ký / con dấu (PNG nền trong suốt, hoặc ảnh chụp — tự tách nền)")
    p.add_argument("--signature-text", help="Ký bằng tên gõ (phông Times New Roman nghiêng)")
    p.add_argument("--sign-width", type=float, help="Chiều rộng chữ ký (pt; mặc định 150, chữ ký nháy 60)")
    p.add_argument("--font-size", type=float, default=12.0, help="Cỡ chữ khi không bắt được dòng chấm (mặc định 12)")
    p.add_argument("--color", help="Màu chữ / dấu (mặc định đen; vd xanh, do, #1E3A8A)")
    p.add_argument("--no-snap", action="store_true", help="Không tự bắt dòng chấm / ô vuông")
    p.add_argument("--ops", help="Tệp JSON danh sách thao tác (xem fill_sign.apply_fill_operations)")
    p.add_argument("--leaders", action="store_true", help="Chỉ liệt kê dòng chấm / đường kẻ / ô vuông tìm được")
    p.add_argument("--author", help="Tên người điền (mặc định: tên đăng nhập Windows)")
    p.add_argument("--flatten", action="store_true", help="Làm phẳng vào nội dung trang (không sửa / xoá được nữa)")
    p.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    s = sub.add_parser("signature", help="Thư viện chữ ký (mã hoá DPAPI) & tách nền ảnh chụp chữ ký")
    s_sub = s.add_subparsers(dest="sig_command", required=True)
    s_list = s_sub.add_parser("list", help="Liệt kê chữ ký đã lưu")
    s_list.add_argument("--json", action="store_true", help="In kết quả dạng JSON")
    s_add = s_sub.add_parser("add", help="Lưu chữ ký mới từ ảnh (tự tách nền) hoặc tên gõ")
    s_add.add_argument("--image", help="Ảnh chữ ký / ảnh chụp chữ ký trên giấy")
    s_add.add_argument("--text", help="Tên gõ")
    s_add.add_argument("--initials", action="store_true", help="Lưu làm chữ ký nháy")
    s_add.add_argument("--name", default="", help="Tên gợi nhớ")
    s_add.add_argument("--json", action="store_true", help="In kết quả dạng JSON")
    s_del = s_sub.add_parser("delete", help="Xoá chữ ký đã lưu")
    s_del.add_argument("id", help="Mã chữ ký")
    s_clean = s_sub.add_parser("clean", help="Tách nền ảnh chụp chữ ký / con dấu thành PNG nền trong suốt")
    s_clean.add_argument("image", help="Ảnh chụp (JPG, PNG…)")
    s_clean.add_argument("-o", "--output", help="Tệp PNG kết quả (mặc định: <tên>_tach_nen.png)")
    s_clean.add_argument("--sensitivity", type=int, default=50, help="Độ nhạy mực 0–100 (mặc định 50)")
    s_clean.add_argument("--one-color", action="store_true", help="Tô một màu trung bình thay vì giữ màu từng điểm")


def _add_update_command(sub) -> None:
    """Lệnh «update»: kiểm tra / tải bản mới từ GitHub Release (không tự cài)."""
    p_upd = sub.add_parser("update", help="Kiểm tra hoặc tải bản QT PDF Pro mới nhất từ GitHub Release")
    grp = p_upd.add_mutually_exclusive_group()
    grp.add_argument("--check", action="store_true", help="Chỉ kiểm tra có bản mới hay không (mặc định)")
    grp.add_argument("--download", action="store_true", help="Tải tệp .zip bản mới (kiểm SHA-256)")
    p_upd.add_argument("-o", "--output-dir", help="Thư mục lưu tệp tải về (mặc định: %%LOCALAPPDATA%%\\QT PDF Pro\\updates)")
    p_upd.add_argument("--json", action="store_true", help="In kết quả dạng JSON")


def _add_assoc_command(sub) -> None:
    """Lệnh «assoc»: đăng ký QT PDF Pro làm trình mở .pdf với Windows (HKCU)."""
    p_as = sub.add_parser("assoc", help="Đăng ký QT PDF Pro làm trình mở tệp .pdf với Windows (theo người dùng)")
    grp = p_as.add_mutually_exclusive_group()
    grp.add_argument("--status", action="store_true", help="Xem trạng thái đăng ký (mặc định)")
    grp.add_argument("--register", action="store_true", help="Ghi ProgID, Open with, Capabilities vào HKCU")
    grp.add_argument("--open-settings", action="store_true", help="Mở Cài đặt › Ứng dụng mặc định của QT PDF Pro")
    p_as.add_argument("--exe", help="Đường dẫn QTPdfPro.exe để đăng ký (mặc định: tệp .exe đang chạy)")
    p_as.add_argument("--json", action="store_true", help="In kết quả dạng JSON")


def _assoc_status() -> dict:
    return {
        "registered": file_assoc.is_registered(),
        "registered_exe": file_assoc.registered_exe(),
        "default_progid": file_assoc.current_default_progid(),
        "is_default": file_assoc.is_default_pdf_app(),
        "prog_id": file_assoc.PROG_ID,
    }


def _run_assoc(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        print("Lỗi: lệnh assoc chỉ hỗ trợ Windows.", file=sys.stderr)
        return 1
    if args.register:
        exe = Path(args.exe) if args.exe else (Path(sys.executable) if update_check.is_frozen() else None)
        if exe is None or exe.name.lower() != file_assoc.APP_EXE_NAME.lower() or not exe.is_file():
            print(f"Lỗi: cần --exe trỏ tới {file_assoc.APP_EXE_NAME} đã đóng gói.", file=sys.stderr)
            return 1
        try:
            file_assoc.register_pdf_handler(exe.resolve())
        except OSError as exc:
            print(f"Lỗi: không ghi được registry: {exc}", file=sys.stderr)
            return 1
    if args.open_settings and not file_assoc.open_default_apps_settings():
        print("Lỗi: không mở được Cài đặt Windows.", file=sys.stderr)
        return 1
    status = _assoc_status()
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0
    if args.register:
        print(f"Đã đăng ký {status['registered_exe']} làm trình mở .pdf (ProgID {file_assoc.PROG_ID}).")
    if args.open_settings:
        print("Đã mở Cài đặt Windows — bấm «Đặt mặc định» cho QT PDF Pro.")
    print(f"  - Đã đăng ký với Windows : {'có' if status['registered'] else 'chưa'}")
    print(f"  - Trình mở PDF mặc định  : {status['default_progid'] or '(Windows tự chọn)'}")
    print(f"  - QT PDF Pro là mặc định : {'có' if status['is_default'] else 'chưa'}")
    return 0


def _run_update(args: argparse.Namespace) -> int:
    try:
        result = update_check.check_for_update()
    except update_check.UpdateError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    payload = result.to_dict()
    rel = result.latest
    if not args.download:
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(result.message)
            if result.update_available and rel is not None:
                print(f"  - Bản mới      : {rel.title}")
                print(f"  - Trang phát hành: {rel.html_url}")
                if rel.asset is not None:
                    print(f"  - Tệp tải về   : {rel.asset.name} ({update_check.format_size(rel.asset.size)})")
        return 0

    if not result.update_available or rel is None:
        if args.json:
            print(json.dumps({**payload, "downloaded": None}, ensure_ascii=False, indent=2))
        else:
            print(result.message)
        return 0
    if rel.asset is None:
        print(
            f"Lỗi: bản v{rel.version} chưa có tệp {update_check.UPDATE_ASSET_NAME} — "
            f"tải thủ công tại {rel.html_url}",
            file=sys.stderr,
        )
        return 1

    def _on_progress(done: int, total: int) -> None:
        if args.json:
            return
        if total:
            text = f"{update_check.format_size(done)} / {update_check.format_size(total)} ({done * 100 // total}%)"
        else:
            text = update_check.format_size(done)
        print(f"\r  Đang tải: {text}   ", end="", file=sys.stderr, flush=True)

    try:
        path = update_check.download_asset(
            rel.asset, Path(args.output_dir) if args.output_dir else None, progress_cb=_on_progress
        )
    except update_check.UpdateError as exc:
        if not args.json:
            print(file=sys.stderr)
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({**payload, "downloaded": str(path)}, ensure_ascii=False, indent=2))
    else:
        print(file=sys.stderr)
        check = "khớp SHA-256" if rel.asset.sha256 else "đúng dung lượng"
        print(f"Đã tải bản v{rel.version} ({check}): {path}")
        print("  Giải nén và chép đè thư mục QTPdfPro để cập nhật (hoặc cập nhật ngay trong ứng dụng).")
    return 0


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


def _parse_fill_spec(spec: str, with_text: bool) -> tuple:
    """'TRANG:X,Y[:NỘI_DUNG]' → (trang 1-based, x, y, nội dung)."""
    parts = spec.split(":", 2)
    if len(parts) < 2:
        raise ValueError(f"Mục «{spec}» phải có dạng TRANG:X,Y" + (":CHỮ" if with_text else ""))
    xy = parts[1].split(",")
    if len(xy) != 2:
        raise ValueError(f"Toạ độ «{parts[1]}» phải có dạng X,Y")
    text = parts[2] if len(parts) > 2 else ""
    if with_text and not text.strip():
        raise ValueError(f"Mục «{spec}» thiếu nội dung cần điền")
    return int(parts[0]), float(xy[0]), float(xy[1]), text


def _run_fill(args: argparse.Namespace) -> int:
    import fitz

    src = Path(args.input_pdf).resolve()
    doc = fitz.open(str(src))
    try:
        if doc.needs_pass:
            raise PermissionError("Tệp PDF được bảo vệ bằng mật khẩu.")
        if args.leaders:
            payload = []
            for page in doc:
                payload.append({
                    "page": page.number + 1,
                    "leaders": [ld.to_dict() for ld in fill_sign.find_leaders(page, args.font_size)],
                    "boxes": [[round(v, 2) for v in b] for b in fill_sign.find_boxes(page)],
                })
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                for item in payload:
                    print(f"Trang {item['page']}: {len(item['leaders'])} chỗ điền, {len(item['boxes'])} ô vuông")
                    for ld in item["leaders"]:
                        kind = "dòng chấm" if ld["source"] == "text" else "đường kẻ"
                        print(f"  - {kind}: x {ld['x0']:g}–{ld['x1']:g}, chân chữ y {ld['baseline']:g}, "
                              f"cỡ {ld['font_size']:g} pt")
            return 0

        color = args.color or "#111827"
        common = {"color": color, "font_size": args.font_size, "snap": not args.no_snap}
        ops: list = []
        for spec in args.text:
            pg, x, y, text = _parse_fill_spec(spec, True)
            ops.append({"type": "text", "page": pg, "at": [x, y], "text": text, **common})
        for spec in args.date:
            pg, x, y, _t = _parse_fill_spec(spec, False)
            ops.append({"type": "date", "page": pg, "at": [x, y], "format": args.date_format, **common})
        for mark in fill_sign.MARKS:
            for spec in getattr(args, mark):
                pg, x, y, _t = _parse_fill_spec(spec, False)
                ops.append({"type": mark, "page": pg, "at": [x, y], **common})
        sig_specs = [(s, False) for s in args.sign] + [(s, True) for s in args.initials]
        if sig_specs:
            base: dict = {}
            if args.signature_id:
                base["id"] = args.signature_id
            elif args.signature_image:
                base["image"] = args.signature_image
            elif args.signature_text:
                base["text"] = args.signature_text
            else:
                raise ValueError("Đặt chữ ký cần --signature-id, --signature-image hoặc --signature-text")
            for spec, initials in sig_specs:
                pg, x, y, _t = _parse_fill_spec(spec, False)
                op = {"type": "signature", "page": pg, "at": [x, y], "initials": initials, **base}
                if args.sign_width:
                    op["width"] = args.sign_width
                if args.color and "text" in base:
                    op["color"] = args.color
                ops.append(op)
        if args.ops:
            extra = json.loads(Path(args.ops).read_text(encoding="utf-8-sig"))
            if isinstance(extra, dict):
                extra = extra.get("operations") or extra.get("ops") or []
            ops.extend(extra)
        if not ops:
            raise ValueError("Chưa có gì để điền — dùng --text, --check, --date, --sign… hoặc --ops")
        author = args.author if args.author is not None else annots_mod.default_author()
        added = fill_sign.apply_fill_operations(doc, ops, author)
        dst = Path(args.output).resolve() if args.output else src.with_name(f"{src.stem}_da_dien.pdf")
        if args.flatten:
            annots_mod.flatten_annotations(doc)
        if dst == src:
            doc.save(str(src), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        else:
            page_ops.save_pdf(doc, dst)
    finally:
        doc.close()
    if args.json:
        print(json.dumps({"output": str(dst), "added": added, "flattened": bool(args.flatten)},
                         ensure_ascii=False, indent=2))
    else:
        print(f"Đã điền {added} mục → {dst}" + (" (đã làm phẳng)" if args.flatten else ""))
    return 0


def _run_signature(args: argparse.Namespace) -> int:
    lib = fill_sign.SignatureLibrary()
    if args.sig_command == "list":
        sigs = lib.list()
        if args.json:
            payload = [{"id": s.id, "kind": s.kind, "initials": s.initials, "name": s.name, "label": s.label}
                       for s in sigs]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"{len(sigs)} chữ ký đã lưu ở {lib.folder}")
            for s in sigs:
                print(f"  - {s.id}: {s.label}")
        return 0
    if args.sig_command == "add":
        if args.image:
            png = fill_sign.prepare_signature_image(Path(args.image).read_bytes())
            sig = fill_sign.Signature("image", args.initials, name=args.name, png=png)
        elif args.text:
            sig = fill_sign.Signature("typed", args.initials, name=args.name, text=args.text)
        else:
            raise ValueError("Cần --image hoặc --text")
        lib.save(sig)
        if args.json:
            print(json.dumps({"id": sig.id, "label": sig.label}, ensure_ascii=False, indent=2))
        else:
            print(f"Đã lưu {sig.label} — mã {sig.id}")
        return 0
    if args.sig_command == "delete":
        if not lib.delete(args.id):
            raise ValueError(f"Không có chữ ký mã «{args.id}»")
        print(f"Đã xoá chữ ký {args.id}")
        return 0
    src = Path(args.image).resolve()
    dst = Path(args.output).resolve() if args.output else src.with_name(f"{src.stem}_tach_nen.png")
    png = fill_sign.clean_signature_photo(src.read_bytes(), args.sensitivity, keep_color=not args.one_color)
    dst.write_bytes(png)
    print(f"Đã tách nền → {dst}")
    return 0


def _run_fill_sign_command(args: argparse.Namespace) -> int:
    try:
        return _run_fill(args) if args.command == "fill" else _run_signature(args)
    except (fill_sign.FillSignError, annots_mod.AnnotationError, ValueError, OSError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1


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


OFFICE_COMMANDS = ("compress", "watermark", "number", "protect", "unlock")


def _add_office_commands(sub) -> None:
    """Công cụ văn phòng: nén, dấu nước, đánh số trang, đặt / gỡ mật khẩu."""

    def common(p, signed: bool = True) -> None:
        p.add_argument("input_pdf", help="Tệp PDF nguồn")
        p.add_argument("-o", "--output", help="Tệp kết quả (mặc định: cạnh tệp gốc, thêm hậu tố)")
        p.add_argument("--password", help="Mật khẩu của tệp nguồn nếu có (tệp hạn chế quyền cần mật khẩu chủ)")
        if signed:
            p.add_argument("--force", action="store_true", help="Vẫn xử lý tệp có chữ ký số (chữ ký sẽ mất hiệu lực)")
        p.add_argument("--json", action="store_true", help="In kết quả dạng JSON")

    p_cmp = sub.add_parser("compress", help="Nén PDF: giảm độ phân giải ảnh, nhúng tập con phông, dọn đối tượng thừa")
    common(p_cmp)
    p_cmp.add_argument("--level", default="vua", help="Mức nén: nhe (in đẹp) | vua (mặc định) | manh (gửi thư)")

    p_wm = sub.add_parser("watermark", help="Đóng dấu nước chữ (tiếng Việt) lên các trang")
    common(p_wm)
    p_wm.add_argument("--text", required=True, help=r"Nội dung dấu nước; xuống dòng bằng \n")
    p_wm.add_argument("--size", type=float, default=56.0, help="Cỡ chữ (pt, mặc định 56)")
    p_wm.add_argument("--opacity", type=float, default=0.2, help="Độ đậm 0.02–1 (mặc định 0.2)")
    p_wm.add_argument("--angle", type=float, default=45.0, help="Góc xoay (độ, mặc định 45)")
    p_wm.add_argument("--color", default="#DC2626", help="Màu: #RRGGBB hoặc do, xanh, den…")
    p_wm.add_argument("--font", default="sans", choices=["sans", "serif"], help="sans = Arial, serif = Times New Roman")
    p_wm.add_argument("--no-bold", action="store_true", help="Chữ thường (mặc định chữ đậm)")
    p_wm.add_argument("--tile", action="store_true", help="Lát gạch kín trang (mặc định: một dấu giữa trang)")
    p_wm.add_argument("--behind", action="store_true", help="Đặt dưới nội dung trang")
    p_wm.add_argument("-p", "--pages", default="", help="Các trang đóng dấu, vd '1-3,5' (mặc định: tất cả)")

    p_num = sub.add_parser("number", help="Đánh số trang (6 vị trí đầu/chân trang, mẫu «Chuẩn NĐ30»)")
    common(p_num)
    p_num.add_argument("--preset", choices=["nd30"], help="nd30 = giữa lề trên, Times New Roman 13, bỏ số trang 1")
    p_num.add_argument("--format", dest="template", help="Mẫu: '{n}', 'Trang {n}', '{n} / {total}' (mặc định '{n}')")
    p_num.add_argument("--position", help="top-left|top-center|top-right|bottom-left|bottom-center|bottom-right")
    p_num.add_argument("--start", type=int, help="Số của trang đầu tiên trong phạm vi (mặc định 1)")
    p_num.add_argument("--skip-first", action="store_true", default=None, help="Không in số lên trang đầu")
    p_num.add_argument("--size", type=float, help="Cỡ chữ (pt, mặc định 12)")
    p_num.add_argument("--font", choices=["serif", "sans"], help="serif = Times New Roman (mặc định), sans = Arial")
    p_num.add_argument("--bold", action="store_true", default=None, help="Chữ đậm")
    p_num.add_argument("--color", help="Màu chữ (mặc định đen)")
    p_num.add_argument("--margin", type=float, help="Cách mép trên/dưới (mm, mặc định 10)")
    p_num.add_argument("--side-margin", type=float, help="Cách mép trái/phải với vị trí trái/phải (mm, mặc định 20)")
    p_num.add_argument("-p", "--pages", help="Phạm vi đánh số, vd '2-10' (mặc định: tất cả)")

    p_pro = sub.add_parser("protect", help="Đặt mật khẩu AES-256 & hạn chế quyền in / sao chép / sửa / chú thích")
    common(p_pro)
    p_pro.add_argument("-u", "--user-password", default="", help="Mật khẩu mở tệp (bỏ trống = mở không cần mật khẩu)")
    p_pro.add_argument("-O", "--owner-password", default="", help="Mật khẩu chủ (bắt buộc khi hạn chế quyền)")
    p_pro.add_argument("--no-print", action="store_true", help="Cấm in")
    p_pro.add_argument("--no-copy", action="store_true", help="Cấm sao chép nội dung")
    p_pro.add_argument("--no-modify", action="store_true", help="Cấm sửa nội dung, sắp xếp trang")
    p_pro.add_argument("--no-annotate", action="store_true", help="Cấm chú thích, điền biểu mẫu")

    p_unl = sub.add_parser("unlock", help="Gỡ mật khẩu & hạn chế quyền khi biết mật khẩu")
    common(p_unl, signed=False)


def _number_options(args: argparse.Namespace) -> page_stamp.PageNumberOptions:
    opts = page_stamp.nd30_page_number_options() if args.preset == "nd30" else page_stamp.PageNumberOptions()
    overrides = {
        "template": args.template, "position": args.position, "start": args.start, "skip_first": args.skip_first,
        "font_size": args.size, "font_family": args.font, "bold": args.bold, "color": args.color,
        "margin_mm": args.margin, "side_margin_mm": args.side_margin, "pages": args.pages,
    }
    for key, value in overrides.items():
        if value is not None:
            setattr(opts, key, value)
    return opts


def _print_tool_result(res: ToolResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
        return
    if not res.written:
        print(res.note)
        return
    titles = {"compress": "Đã nén", "watermark": "Đã đóng dấu nước", "number": "Đã đánh số trang",
              "protect": "Đã đặt mật khẩu", "unlock": "Đã gỡ mật khẩu"}
    print(f"{titles.get(res.tool, 'Xong')} → {res.output_path}")
    if res.tool in ("watermark", "number"):
        print(f"  - {res.pages_changed}/{res.pages} trang")
    if res.note:
        print(f"  - {res.note}")
    if res.tool != "compress":
        print(f"  - Dung lượng: {format_size(res.input_size)} → {format_size(res.output_size)}")
    if res.encrypted and res.tool != "protect":
        print("  - Tệp kết quả giữ nguyên mật khẩu của tệp gốc")


def _run_office_command(args: argparse.Namespace) -> int:
    """Chạy các lệnh nén / dấu nước / đánh số trang / mật khẩu; trả về mã thoát."""
    force = bool(getattr(args, "force", False))
    try:
        if args.command == "compress":
            res = compress_mod.compress_pdf(args.input_pdf, args.output, args.level, args.password, force)
        elif args.command == "watermark":
            opts = page_stamp.WatermarkOptions(
                text=args.text.replace(r"\n", "\n"), font_size=args.size, opacity=args.opacity, angle=args.angle,
                color=args.color, font_family=args.font, bold=not args.no_bold,
                layout="tile" if args.tile else "center", pages=args.pages, behind=args.behind,
            )
            res = page_stamp.watermark_pdf(args.input_pdf, args.output, opts, args.password, force)
        elif args.command == "number":
            res = page_stamp.number_pages(args.input_pdf, args.output, _number_options(args), args.password, force)
        elif args.command == "protect":
            opts = pdf_security.ProtectOptions(
                user_password=args.user_password, owner_password=args.owner_password,
                allow_print=not args.no_print, allow_copy=not args.no_copy,
                allow_modify=not args.no_modify, allow_annotate=not args.no_annotate,
            )
            res = pdf_security.protect_pdf(args.input_pdf, args.output, opts, args.password, force)
        else:
            if not args.password:
                raise PdfToolError("Hãy nhập mật khẩu bằng --password.")
            res = pdf_security.unlock_pdf(args.input_pdf, args.output, args.password)
    except (PdfToolError, page_ops.PageOpsError, FileNotFoundError, PermissionError, ValueError, OSError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    _print_tool_result(res, args.json)
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


def _qt_app():
    """QApplication tối thiểu cho QPrinter khi chạy từ dòng lệnh."""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(["qtpdfpro-print"])


def _run_print(args: argparse.Namespace) -> int:
    """Lệnh `print`: liệt kê máy in, xem kế hoạch, in ra PDF hoặc gửi máy in."""
    import fitz

    if args.list_printers:
        from qtpdfpro.ui import print_job  # cần Qt — chỉ nạp khi dùng tới máy in

        _app = _qt_app()
        names, default = print_job.available_printers(), print_job.default_printer_name()
        if args.json:
            print(json.dumps({"printers": names, "default": default}, ensure_ascii=False, indent=2))
        else:
            for n in names:
                print(f"  {'*' if n == default else ' '} {n}")
            print("(* = máy in mặc định)")
        return 0
    if not args.input_pdf:
        print("Lỗi: thiếu tệp PDF cần in.", file=sys.stderr)
        return 2

    src = Path(args.input_pdf).resolve()
    opts = printing.PrintOptions(
        copies=args.copies, collate=not args.no_collate, paper=args.paper, orientation=args.orientation,
        scale=args.scale, auto_rotate=not args.no_auto_rotate, duplex=args.duplex, grayscale=args.grayscale,
        annotations=not args.no_annots, subset=args.subset, reverse=args.reverse,
        max_dpi=args.dpi if (args.printer and args.dpi) else printing.MAX_PRINT_DPI,
    ).normalized()
    try:
        doc = fitz.open(str(src))
    except Exception as exc:
        print(f"Lỗi: không mở được {src}: {exc}", file=sys.stderr)
        return 1
    try:
        if doc.needs_pass:
            raise printing.PrintError("Tệp PDF có mật khẩu — hãy mở bằng giao diện để in.")
        if not printing.printing_allowed(doc):
            raise printing.PrintError("Tài liệu không cho phép in (chủ sở hữu đã tắt quyền in).")
        pages = printing.parse_print_range(args.pages, doc.page_count)
        payload: dict = {"input": str(src), "pages": [i + 1 for i in pages]}

        if args.plan or args.to_pdf:
            plan = printing.plan_document(doc, pages, opts)
            payload["plan"] = plan.to_dict()
            if args.plan:
                if args.json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"{src.name}: {plan.summary()} (chưa tính lề không in được của máy in)")
                    for k, sh in enumerate(plan.sheets, 1):
                        rot = f", xoay {sh.rotate}°" if sh.rotate else ""
                        cut = " — mất mép (lớn hơn khổ giấy)" if sh.clipped else ""
                        print(f"  Tờ {k}: trang {sh.page_index + 1}, tỷ lệ {sh.scale * 100:.1f}%{rot}{cut}")
                return 0
            res = printing.print_to_pdf(doc, plan, args.to_pdf, dpi=args.dpi or printing.MIN_PRINT_DPI)
        else:
            from qtpdfpro.ui import print_job  # cần Qt — chỉ nạp khi dùng tới máy in

            _app = _qt_app()
            name = "" if args.printer.strip().lower() in ("mac-dinh", "macdinh", "default", "") else args.printer
            printer = print_job.create_printer(name)
            res = print_job.print_document(printer, doc, pages, opts, doc_name=src.name)
    except (printing.PrintError, OSError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    finally:
        doc.close()

    payload["result"] = res.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif res.output_path:
        print(f"Đã dựng bản in {res.sheets_printed} tờ ({res.dpi} dpi) → {res.output_path}")
    else:
        print(f"Đã gửi {res.sheets_printed} tờ tới máy in «{res.printer}» ({res.dpi} dpi)")
    return 0


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

    if args.command == "print":
        return _run_print(args)

    if args.command in ("merge", "split", "organize", "extract", "annotate", "annots"):
        return _run_edit_command(args)

    if args.command in ("fill", "signature"):
        return _run_fill_sign_command(args)

    if args.command == "update":
        return _run_update(args)
    if args.command == "assoc":
        return _run_assoc(args)
    if args.command in OFFICE_COMMANDS:
        return _run_office_command(args)

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
