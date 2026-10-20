"""Quản lý cấu hình ứng dụng và danh sách tệp mở gần đây.

Sử dụng biến môi trường `QT_PDF_PRO_DATA` khi chạy thử nghiệm (test) để cô lập hoàn toàn
với thư mục cấu hình thật của người dùng tại `%LOCALAPPDATA%\\QTPdfPro`.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


def get_data_dir() -> Path:
    """Trả về thư mục lưu dữ liệu cấu hình của ứng dụng."""
    override = os.environ.get("QT_PDF_PRO_DATA", "").strip()
    if override:
        path = Path(override)
    else:
        local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = Path(local_app_data) / "QTPdfPro"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class AppSettings:
    """Cấu hình người dùng của QT PDF Pro."""

    theme: str = "dark"  # "dark" | "light"
    recent_files: List[str] = field(default_factory=list)
    default_convert_mode: str = "auto"  # "auto" | "nd30" | "hybrid" | "exact" | "word_com"
    default_zoom_mode: str = "fit_width"  # "fit_width" | "fit_page" | "percent"
    default_zoom_percent: int = 100
    continuous_scroll: bool = True
    show_layout_overlay: bool = False
    normalize_vietnamese: bool = True
    fix_table_padding: bool = True
    prevent_line_overflow: bool = True
    exact_background_dpi: int = 180
    nd30_policy: str = "faithful"  # "faithful" (giữ đúng bố cục PDF) | "nd30" (ép chuẩn hoá NĐ30)
    verify_layout: bool = True  # Kiểm chứng DOCX bằng Microsoft Word sau khi chuyển (nếu máy có Word)
    batch_output_dir: str = ""  # Thư mục lưu của «Chuyển đổi hàng loạt»; trống = lưu cạnh từng tệp PDF gốc
    annot_author: str = ""  # Tên người chú thích ghi vào PDF; trống = tên đăng nhập Windows
    auto_check_updates: bool = True  # Tự kiểm tra bản mới trên GitHub Release lúc khởi động (tối đa 1 lần/ngày)
    auto_download_updates: bool = True  # Bản đóng gói: thấy bản mới thì tải ngầm + cài khi thoát (core/updater.py)
    last_update_check: str = ""  # Thời điểm kiểm tra cập nhật thành công gần nhất (ISO 8601, UTC)
    skipped_update_version: str = ""  # Bản người dùng chọn «Bỏ qua bản này» (không tự báo nữa)
    default_app_prompted: bool = False  # Đã hỏi «Đặt làm trình xem PDF mặc định» lần đầu chạy bản cài (ui/default_app.py)
    print_settings: Dict[str, Any] = field(default_factory=dict)  # Thiết lập in lần trước (PrintOptions.to_settings)

    @classmethod
    def settings_file(cls) -> Path:
        return get_data_dir() / "settings.json"

    @classmethod
    def load(cls) -> "AppSettings":
        """Đọc cấu hình từ đĩa (chịu được UTF-8 BOM từ PowerShell)."""
        file_path = cls.settings_file()
        if not file_path.exists():
            return cls()
        try:
            raw = file_path.read_text(encoding="utf-8-sig")
            data = json.loads(raw)
            if not isinstance(data, dict):
                return cls()
            valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in valid_keys}
            return cls(**filtered)
        except Exception:
            return cls()

    def save(self) -> None:
        """Lưu cấu hình xuống đĩa bằng UTF-8."""
        file_path = self.settings_file()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_recent_file(self, pdf_path: str | Path, max_items: int = 15) -> None:
        """Thêm một tệp PDF vào đầu danh sách mở gần đây."""
        norm = str(Path(pdf_path).resolve())
        items = [p for p in self.recent_files if p.lower() != norm.lower()]
        items.insert(0, norm)
        self.recent_files = items[:max_items]
        self.save()
