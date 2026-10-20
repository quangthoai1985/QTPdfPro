"""Chuyển đổi hàng loạt nhiều tệp PDF sang Word (.docx) kèm báo cáo tổng hợp.

Mỗi tệp được chuyển lần lượt bằng `convert_pdf_to_docx` (mặc định chế độ `auto`: văn bản hành chính
tự dùng engine `nd30` với chính sách `faithful`). Lỗi ở một tệp chỉ đánh dấu tệp đó thất bại, không
dừng cả lượt. Kết quả từng tệp gồm chế độ thực thi, điểm chuẩn xác (fidelity), điểm thể thức NĐ30
(nếu là văn bản hành chính) và kết quả kiểm chứng bằng Microsoft Word (nếu bật `verify_layout`).

Chạy tuần tự trong một luồng: bộ vá `pdf2docx` trong `converter.py` dùng biến toàn cục theo trang
nên không an toàn khi chạy song song nhiều tệp trong cùng tiến trình.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

from qtpdfpro.core.converter import ConversionOptions, ConversionResult, convert_pdf_to_docx
from qtpdfpro.core.layout_verify import LayoutVerifyReport

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

STATUS_TEXT = {
    STATUS_PENDING: "Đang chờ",
    STATUS_RUNNING: "Đang chuyển…",
    STATUS_OK: "Hoàn tất",
    STATUS_FAILED: "Thất bại",
    STATUS_CANCELLED: "Đã huỷ",
}


@dataclass
class BatchItemResult:
    """Kết quả chuyển đổi của một tệp trong lượt hàng loạt."""

    index: int
    pdf_path: str
    docx_path: str
    status: str = STATUS_PENDING
    mode_used: str = ""
    pages_converted: int = 0
    elapsed_seconds: float = 0.0
    fidelity_score: Optional[float] = None
    word_retention_ratio: Optional[float] = None
    nd30_score: Optional[float] = None
    layout_verdict: Optional[str] = None
    layout_score: Optional[float] = None
    error: str = ""
    notes: List[str] = field(default_factory=list)
    result: Optional[ConversionResult] = field(default=None, repr=False, compare=False)

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    @property
    def status_text(self) -> str:
        return STATUS_TEXT.get(self.status, self.status)

    @property
    def layout_verdict_text(self) -> str:
        """Kết luận kiểm chứng bằng Word bằng tiếng Việt («» nếu không kiểm chứng)."""
        return LayoutVerifyReport(verdict=self.layout_verdict).verdict_text if self.layout_verdict else ""

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "pdf_path": self.pdf_path,
            "docx_path": self.docx_path,
            "status": self.status,
            "mode_used": self.mode_used,
            "pages_converted": self.pages_converted,
            "elapsed_seconds": self.elapsed_seconds,
            "fidelity_score": self.fidelity_score,
            "word_retention_ratio": self.word_retention_ratio,
            "nd30_score": self.nd30_score,
            "layout_verdict": self.layout_verdict,
            "layout_verdict_text": self.layout_verdict_text,
            "layout_score": self.layout_score,
            "error": self.error,
            "notes": list(self.notes),
        }


@dataclass
class BatchReport:
    """Báo cáo tổng hợp một lượt chuyển đổi hàng loạt."""

    items: List[BatchItemResult] = field(default_factory=list)
    out_dir: Optional[str] = None  # None = lưu cạnh từng tệp PDF gốc
    mode: str = "auto"
    elapsed_seconds: float = 0.0
    cancelled: bool = False

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def ok_count(self) -> int:
        return sum(1 for it in self.items if it.status == STATUS_OK)

    @property
    def failed_count(self) -> int:
        return sum(1 for it in self.items if it.status == STATUS_FAILED)

    @property
    def cancelled_count(self) -> int:
        return sum(1 for it in self.items if it.status == STATUS_CANCELLED)

    @property
    def average_fidelity(self) -> Optional[float]:
        scores = [it.fidelity_score for it in self.items if it.ok and it.fidelity_score is not None]
        return round(sum(scores) / len(scores), 1) if scores else None

    @property
    def average_nd30(self) -> Optional[float]:
        scores = [it.nd30_score for it in self.items if it.ok and it.nd30_score is not None]
        return round(sum(scores) / len(scores), 1) if scores else None

    def to_dict(self) -> dict:
        return {
            "out_dir": self.out_dir,
            "mode": self.mode,
            "total": self.total,
            "ok": self.ok_count,
            "failed": self.failed_count,
            "cancelled": self.cancelled_count,
            "average_fidelity": self.average_fidelity,
            "average_nd30": self.average_nd30,
            "elapsed_seconds": self.elapsed_seconds,
            "items": [it.to_dict() for it in self.items],
        }


@dataclass
class BatchProgress:
    """Sự kiện tiến trình gửi cho `progress_cb` (chạy trên luồng đang chuyển đổi).

    `item` (bản sao trạng thái lúc phát) chỉ có khi một tệp vừa bắt đầu (`status == running`) hoặc vừa kết thúc.
    Tỷ lệ hoàn thành cả lượt: `(file_index + step / steps) / total_files`.
    """

    file_index: int
    total_files: int
    step: int
    steps: int
    message: str
    item: Optional[BatchItemResult] = None

    @property
    def fraction(self) -> float:
        if self.total_files <= 0:
            return 1.0
        inner = (self.step / self.steps) if self.steps > 0 else 0.0
        return min(1.0, (self.file_index + min(1.0, inner)) / self.total_files)


BatchProgressCallback = Optional[Callable[[BatchProgress], None]]


def default_batch_options() -> ConversionOptions:
    """Tuỳ chọn mặc định khi chuyển hàng loạt: `auto` + NĐ30 `faithful`, không kiểm chứng bằng Word."""
    return ConversionOptions(mode="auto", nd30_policy="faithful", verify_layout=False)


def _path_key(p: Path) -> str:
    return str(p).lower()  # Windows không phân biệt hoa/thường trong đường dẫn


def collect_pdf_paths(inputs: Iterable[str | Path], recursive: bool = False) -> List[Path]:
    """Gom danh sách tệp PDF từ các đường dẫn tệp và/hoặc thư mục (bỏ trùng, giữ thứ tự).

    Thư mục được mở rộng thành các tệp `*.pdf` bên trong (sắp theo tên; `recursive=True` duyệt cả
    thư mục con). Tệp chỉ định trực tiếp được giữ nguyên kể cả khi chưa tồn tại — lỗi sẽ được báo
    ở bước chuyển đổi của tệp đó.
    """
    found: List[Path] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        key = _path_key(p)
        if key not in seen:
            seen.add(key)
            found.append(p)

    for raw in inputs:
        p = Path(raw).expanduser()
        p = p.resolve() if p.exists() else p.absolute()
        if p.is_dir():
            pattern = p.rglob("*") if recursive else p.iterdir()
            pdfs = [c for c in pattern if c.is_file() and c.suffix.lower() == ".pdf"]
            for c in sorted(pdfs, key=lambda c: _path_key(c.relative_to(p))):
                _add(c.resolve())
        else:
            _add(p)
    return found


def plan_output_paths(pdf_paths: Sequence[str | Path], out_dir: Optional[str | Path] = None) -> List[Path]:
    """Đường dẫn DOCX cho từng PDF: `<out_dir>/<tên>.docx` (hoặc cạnh tệp gốc nếu `out_dir` là None).

    Hai tệp trùng tên (ở các thư mục khác nhau) không ghi đè lẫn nhau: tệp sau nhận hậu tố `_2`, `_3`…
    """
    base = Path(out_dir).expanduser().resolve() if out_dir else None
    used: set[str] = set()
    outputs: List[Path] = []
    for raw in pdf_paths:
        pdf = Path(raw)
        folder = base if base is not None else pdf.parent
        candidate = folder / f"{pdf.stem}.docx"
        n = 2
        while _path_key(candidate) in used:
            candidate = folder / f"{pdf.stem}_{n}.docx"
            n += 1
        used.add(_path_key(candidate))
        outputs.append(candidate)
    return outputs


def _fill_from_result(item: BatchItemResult, res: ConversionResult) -> None:
    item.docx_path = res.docx_path
    item.mode_used = res.mode_used
    item.pages_converted = res.pages_converted
    item.fidelity_score = round(res.fidelity.overall_score, 1)
    item.word_retention_ratio = round(res.fidelity.word_retention_ratio, 4)
    if res.nd30_report is not None:
        item.nd30_score = round(res.nd30_report.score, 1)
    if res.layout_check is not None:
        item.layout_verdict = res.layout_check.verdict or "unavailable"
        item.layout_score = round(res.layout_check.score, 1) if res.layout_check.available else None
    item.notes = list(res.notes)
    item.result = res


def convert_batch(
    pdf_paths: Sequence[str | Path],
    out_dir: Optional[str | Path] = None,
    options: Optional[ConversionOptions] = None,
    progress_cb: BatchProgressCallback = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> BatchReport:
    """Chuyển lần lượt từng tệp PDF sang DOCX và trả về báo cáo tổng hợp.

    - `out_dir`: thư mục lưu DOCX (tự tạo); `None` = lưu cạnh từng tệp PDF gốc.
    - `options`: mặc định `default_batch_options()`; `pages` (nếu có) áp dụng cho mọi tệp.
    - `progress_cb`: nhận `BatchProgress` khi bắt đầu / trong khi / sau khi chuyển mỗi tệp.
    - `should_cancel`: kiểm tra trước mỗi tệp; trả về True thì các tệp còn lại được đánh dấu «Đã huỷ».
    """
    t0 = time.perf_counter()
    opts = replace(options) if options is not None else default_batch_options()
    sources = [Path(p) for p in pdf_paths]
    targets = plan_output_paths(sources, out_dir)
    report = BatchReport(
        items=[
            BatchItemResult(index=i, pdf_path=str(src), docx_path=str(dst))
            for i, (src, dst) in enumerate(zip(sources, targets))
        ],
        out_dir=str(Path(out_dir).expanduser().resolve()) if out_dir else None,
        mode=opts.mode,
    )
    total = report.total

    def _emit(i: int, step: int, steps: int, message: str, item: Optional[BatchItemResult] = None) -> None:
        if progress_cb is not None:
            # Gửi bản sao để sự kiện giữ đúng trạng thái tại thời điểm phát (item còn được cập nhật tiếp)
            snapshot = replace(item, notes=list(item.notes)) if item is not None else None
            progress_cb(BatchProgress(i, total, step, steps, message, snapshot))

    for i, item in enumerate(report.items):
        if should_cancel is not None and should_cancel():
            report.cancelled = True
            for rest in report.items[i:]:
                rest.status = STATUS_CANCELLED
            break

        name = Path(item.pdf_path).name
        prefix = f"[{i + 1}/{total}] {name}"
        item.status = STATUS_RUNNING
        _emit(i, 0, 1, f"{prefix} — bắt đầu chuyển đổi…", item)

        t_item = time.perf_counter()
        try:
            res = convert_pdf_to_docx(
                item.pdf_path,
                item.docx_path,
                options=opts,
                progress_cb=lambda cur, tot, msg, _i=i, _p=prefix: _emit(_i, cur, max(1, tot) + 1, f"{_p} — {msg}"),
            )
            _fill_from_result(item, res)
            item.status = STATUS_OK
            item.elapsed_seconds = res.elapsed_seconds
            done_msg = f"{prefix} — xong ({item.mode_used}, điểm {item.fidelity_score:.1f}%)"
        except Exception as exc:  # một tệp lỗi không được dừng cả lượt
            item.status = STATUS_FAILED
            item.error = str(exc).strip() or type(exc).__name__
            item.elapsed_seconds = round(time.perf_counter() - t_item, 3)
            done_msg = f"{prefix} — lỗi: {item.error}"
        _emit(i, 1, 1, done_msg, item)

    report.elapsed_seconds = round(time.perf_counter() - t0, 3)
    _emit(total, 0, 1, f"Hoàn tất {report.ok_count}/{total} tệp ({report.elapsed_seconds:.1f} giây).")
    return report


_CSV_COLUMNS = [
    ("STT", lambda it: it.index + 1),
    ("Tệp PDF", lambda it: it.pdf_path),
    ("Tệp Word", lambda it: it.docx_path if it.ok else ""),
    ("Trạng thái", lambda it: it.status_text),
    ("Chế độ", lambda it: it.mode_used),
    ("Số trang", lambda it: it.pages_converted or ""),
    ("Điểm chuẩn xác (%)", lambda it: "" if it.fidelity_score is None else f"{it.fidelity_score:.1f}"),
    ("Thể thức NĐ30 (%)", lambda it: "" if it.nd30_score is None else f"{it.nd30_score:.1f}"),
    ("Kiểm chứng Word", lambda it: it.layout_verdict_text),
    ("Thời gian (giây)", lambda it: f"{it.elapsed_seconds:.2f}"),
    ("Lỗi / Ghi chú", lambda it: it.error or " | ".join(it.notes)),
]


def write_batch_report(report: BatchReport, path: str | Path) -> Path:
    """Lưu báo cáo tổng hợp ra `.csv` (UTF-8 có BOM để Excel đọc đúng tiếng Việt) hoặc `.json`."""
    dst = Path(path).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.suffix.lower() == ".json":
        dst.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return dst
    with dst.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([title for title, _ in _CSV_COLUMNS])
        for it in report.items:
            writer.writerow([getter(it) for _, getter in _CSV_COLUMNS])
    return dst
