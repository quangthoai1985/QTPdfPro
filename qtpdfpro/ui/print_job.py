"""Gửi lệnh in tới máy in (hoặc tệp PDF) bằng `QPrinter`, theo kế hoạch của `core/printing.py`.

Dùng chung cho hộp thoại «In» (chạy trong `QThread` — Qt cho phép vẽ lên `QPrinter` ngoài luồng giao diện) và lệnh
`cli print --printer`. Mỗi tờ: kết xuất trang bằng PyMuPDF ở DPI máy in (300–600 dpi) rồi vẽ ảnh vào đúng khung
trên tờ giấy (`setFullPage(True)` → gốc toạ độ là góc tờ giấy, không phải góc vùng in được).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF
from PySide6.QtCore import QMarginsF, QRectF
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

from qtpdfpro.core.printing import (
    PrintError,
    PrintImage,
    PrintOptions,
    PrintPlan,
    PrintResult,
    apply_subset,
    choose_landscape,
    clamp_print_dpi,
    page_sizes,
    plan_print,
    render_sheet,
)

PAGE_SIZE_IDS = {
    "A4": QPageSize.PageSizeId.A4,
    "A5": QPageSize.PageSizeId.A5,
    "A3": QPageSize.PageSizeId.A3,
    "Letter": QPageSize.PageSizeId.Letter,
    "Legal": QPageSize.PageSizeId.Legal,
}
DUPLEX_IDS = {
    "none": QPrinter.DuplexMode.DuplexNone,
    "long": QPrinter.DuplexMode.DuplexLongSide,
    "short": QPrinter.DuplexMode.DuplexShortSide,
}
# Máy in ảo tự hỏi nơi lưu tệp trong lúc bắt đầu in → hộp thoại hỏi trước, ghi thẳng ra tệp
FILE_PRINTERS = {"microsoft print to pdf": ".pdf", "microsoft xps document writer": ".xps"}


def available_printers() -> List[str]:
    return list(QPrinterInfo.availablePrinterNames())


def default_printer_name() -> str:
    return QPrinterInfo.defaultPrinterName()


def file_printer_suffix(name: str) -> str:
    """Đuôi tệp nếu `name` là máy in ảo ghi ra tệp (Microsoft Print to PDF…), ngược lại chuỗi rỗng."""
    return FILE_PRINTERS.get((name or "").strip().lower(), "")


def printer_capabilities(name: str) -> dict:
    """Khả năng của máy in: in 2 mặt, in màu (đọc từ trình điều khiển, có thể chậm với máy in mạng)."""
    info = QPrinterInfo.printerInfo(name) if name else QPrinterInfo.defaultPrinter()
    if info.isNull():
        return {"duplex": False, "color": True, "default_color": True}
    duplex_modes = set(info.supportedDuplexModes())
    color_modes = set(info.supportedColorModes())
    return {
        "duplex": bool(duplex_modes - {QPrinter.DuplexMode.DuplexNone}),
        "color": QPrinter.ColorMode.Color in color_modes or not color_modes,
        "default_color": info.defaultColorMode() == QPrinter.ColorMode.Color,
    }


def create_printer(printer_name: str = "", output_file: Optional[str | Path] = None) -> QPrinter:
    """`QPrinter` độ phân giải cao cho máy in `printer_name` (trống = mặc định), hoặc ghi ra `output_file`.

    `output_file` đuôi `.pdf` → Qt tự dựng PDF (không qua trình điều khiển); đuôi khác → in ra tệp qua trình điều khiển.
    """
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    if output_file is not None and str(output_file).lower().endswith(".pdf"):
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output_file))
        return printer
    if printer_name:
        info = QPrinterInfo.printerInfo(printer_name)
        if info.isNull():
            raise PrintError(f"Không tìm thấy máy in «{printer_name}».")
        printer.setPrinterName(info.printerName())
    if output_file is not None:
        printer.setOutputFileName(str(output_file))
    return printer


def printer_margins_pt(printer: QPrinter) -> Tuple[float, float, float, float]:
    """Lề phần cứng (vùng không in được), pt — lấy lề lớn nhất cho cả 4 cạnh.

    Qt trả cùng một bộ lề cho cả hướng dọc lẫn ngang (không xoay theo hướng giấy), nên dùng lề đều 4 cạnh để
    «Vừa khổ giấy» luôn nằm trọn trong vùng in được dù tờ quay hướng nào.
    """
    layout = QPageLayout(printer.pageLayout())
    layout.setUnits(QPageLayout.Unit.Point)
    m = layout.minimumMargins()
    side = max(0.0, m.left(), m.top(), m.right(), m.bottom())
    return (side, side, side, side)


def configure_printer(printer: QPrinter, options: PrintOptions, landscape: bool, doc_name: str = "") -> bool:
    """Đặt khổ giấy, hướng, màu, 2 mặt, số bản. Trả về True nếu trình điều khiển tự in nhiều bản."""
    o = options.normalized()
    printer.setPageSize(QPageSize(PAGE_SIZE_IDS[o.paper]))
    printer.setPageOrientation(QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait)
    printer.setFullPage(True)
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
    printer.setColorMode(QPrinter.ColorMode.GrayScale if o.grayscale else QPrinter.ColorMode.Color)
    printer.setDuplex(DUPLEX_IDS[o.duplex])
    if doc_name:
        printer.setDocName(doc_name)
    native = printer.outputFormat() == QPrinter.OutputFormat.NativeFormat
    driver_copies = native and o.copies > 1 and printer.supportsMultipleCopies()
    printer.setCopyCount(o.copies if driver_copies else 1)
    printer.setCollateCopies(o.collate)
    return driver_copies


def to_qimage(img: PrintImage) -> QImage:
    """`QImage` dùng chung bộ nhớ với `img.samples` — giữ `img` sống tới khi vẽ xong."""
    fmt = QImage.Format.Format_Grayscale8 if img.grayscale else QImage.Format.Format_RGB888
    return QImage(img.samples, img.width, img.height, img.stride, fmt)


def plan_for_printer(
    printer: QPrinter,
    doc: fitz.Document,
    indices: Sequence[int],
    options: PrintOptions,
    doc_name: str = "",
) -> Tuple[PrintPlan, bool]:
    """Cấu hình `printer` và lập kế hoạch theo lề phần cứng thật. Trả về (kế hoạch, máy in tự nhân bản?)."""
    opts = options.normalized()
    pages = apply_subset(indices, opts.subset, opts.reverse)
    if not pages:
        raise PrintError("Không có trang nào để in.")
    sizes = page_sizes(doc)
    landscape = choose_landscape(sizes, pages, opts)
    driver_copies = configure_printer(printer, opts, landscape, doc_name)
    plan = plan_print(sizes, pages, opts, printer_margins_pt(printer))
    return plan, driver_copies


def print_document(
    printer: QPrinter,
    doc: fitz.Document,
    indices: Sequence[int],
    options: PrintOptions,
    *,
    doc_name: str = "",
    progress: Optional[Callable[[int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> PrintResult:
    """In các trang `indices` (0-based) của `doc` ra `printer`. Ném `PrintError` nếu không mở được lệnh in."""
    plan, driver_copies = plan_for_printer(printer, doc, indices, options, doc_name)
    o = plan.options
    sheets = plan.job_sheets(manual_copies=not driver_copies)
    res = printer.resolution() or 600
    dpi = clamp_print_dpi(res, o.max_dpi)
    k = res / 72.0
    out_file = printer.outputFileName()
    result = PrintResult(total_sheets=len(sheets), dpi=dpi, printer=out_file or printer.printerName(),
                         output_path=out_file)

    painter = QPainter()
    if not painter.begin(printer):
        raise PrintError(
            "Không bắt đầu được lệnh in — máy in có thể đang tắt, mất kết nối hoặc lệnh in đã bị huỷ."
            if not out_file else f"Không ghi được tệp «{out_file}» (tệp đang mở ở chương trình khác?)."
        )
    # Bộ in Windows (QAlphaPaintEngine) ghi lại lệnh vẽ của cả trang rồi mới phát lại khi sang trang / kết thúc,
    # còn QImage chỉ trỏ vào bộ đệm của PyMuPDF → giữ ảnh của trang đang vẽ tới sau newPage()/end().
    current: List[tuple] = []
    try:
        for i, sheet in enumerate(sheets):
            if should_cancel is not None and should_cancel():
                result.cancelled = True
                printer.abort()
                break
            if i > 0:
                if not printer.newPage():
                    raise PrintError("Máy in từ chối sang trang mới — lệnh in bị gián đoạn.")
                current.clear()
            img = render_sheet(doc, sheet, dpi, o.grayscale, o.annotations)
            if img is not None:
                qimg = to_qimage(img)
                current.append((img, qimg))
                x0, y0, x1, y1 = sheet.target
                painter.drawImage(QRectF(x0 * k, y0 * k, (x1 - x0) * k, (y1 - y0) * k), qimg)
            result.sheets_printed = i + 1
            if progress is not None:
                progress(i + 1, len(sheets))
    finally:
        painter.end()
        current.clear()
    if result.cancelled and out_file:
        Path(out_file).unlink(missing_ok=True)
        result.output_path = ""
    return result
