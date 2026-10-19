"""Cấu hình Pytest và các Fixture tạo tài liệu PDF tiếng Việt mẫu cho kiểm thử tự động."""

from __future__ import annotations

import os
from pathlib import Path

import fitz  # PyMuPDF
import pytest


@pytest.fixture(autouse=True)
def isolated_app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Cô lập thư mục dữ liệu ứng dụng vào thư mục tạm trong mọi bài test."""
    data_dir = tmp_path / "qtpdfpro_appdata"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("QT_PDF_PRO_DATA", str(data_dir))
    return data_dir


def _find_windows_unicode_font() -> str | None:
    candidates = [
        Path(r"C:\Windows\Fonts\times.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\tahoma.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


@pytest.fixture()
def sample_vietnamese_pdf(tmp_path: Path) -> Path:
    """Tạo một tệp PDF 2 trang có tiếng Việt có dấu, bảng biểu có viền, hình ảnh và mục lục."""
    pdf_path = tmp_path / "van_ban_mau_tieng_viet.pdf"
    font_file = _find_windows_unicode_font()

    doc = fitz.open()
    doc.set_metadata(
        {
            "title": "Quyết định ban hành quy chế QT PDF Pro",
            "author": "Quang Thoại",
            "subject": "Tài liệu kiểm thử độ chính xác PDF sang DOCX",
            "creator": "QT PDF Pro Test Suite",
        }
    )

    # ─── Trang 1: Văn bản hành chính + Bảng biểu + Hình ảnh ───
    p1 = doc.new_page(width=595, height=842)
    font_kwargs = {"fontname": "vnfont", "fontfile": font_file} if font_file else {"fontname": "helv"}

    # Quốc hiệu - Tiêu ngữ (2 cột song song)
    p1.insert_text((55, 60), "UBND TỈNH AN GIANG", fontsize=11, **font_kwargs)
    p1.insert_text((55, 76), "SỐ: 125/QĐ-UBND", fontsize=10, **font_kwargs)
    p1.insert_text((260, 60), "CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM", fontsize=11, **font_kwargs)
    p1.insert_text((300, 76), "Độc lập - Tự do - Hạnh phúc", fontsize=11, **font_kwargs)
    p1.draw_line((310, 82), (450, 82), color=(0, 0, 0), width=0.8)

    # Tiêu đề chính
    p1.insert_text((195, 125), "QUYẾT ĐỊNH", fontsize=15, **font_kwargs)
    p1.insert_text(
        (95, 148),
        "Về việc ứng dụng chuyển đổi tài liệu PDF sang Word chuẩn xác",
        fontsize=12,
        **font_kwargs,
    )

    # Đoạn văn nội dung
    p1.insert_text(
        (55, 185),
        "Điều 1. Phê duyệt quy trình đọc tệp PDF và chuyển đổi sang định dạng DOCX",
        fontsize=11,
        **font_kwargs,
    )
    p1.insert_text(
        (55, 205),
        "giữ nguyên bố cục, phông chữ tiếng Việt, bảng biểu và hình ảnh minh hoạ.",
        fontsize=11,
        **font_kwargs,
    )

    # Bảng biểu có viền (3 hàng × 3 cột) tại y = 240..340
    col_x = [55, 130, 380, 540]
    row_y = [240, 272, 304, 336]
    # Tô nền hàng tiêu đề bảng
    p1.draw_rect((col_x[0], row_y[0], col_x[-1], row_y[1]), color=None, fill=(0.9, 0.93, 0.98))
    for y in row_y:
        p1.draw_line((col_x[0], y), (col_x[-1], y), color=(0, 0, 0), width=1.0)
    for x in col_x:
        p1.draw_line((x, row_y[0]), (x, row_y[-1]), color=(0, 0, 0), width=1.0)

    table_cells = [
        ["STT", "Hạng mục kiểm định", "Kết quả đạt được"],
        ["01", "Bảo toàn phông chữ tiếng Việt", "Đạt 100% NFC"],
        ["02", "Giữ nguyên khung bảng biểu", "Không rớt dòng"],
    ]
    for r_idx, row_vals in enumerate(table_cells):
        for c_idx, cell_txt in enumerate(row_vals):
            p1.insert_text(
                (col_x[c_idx] + 8, row_y[r_idx] + 20),
                cell_txt,
                fontsize=10.5,
                **font_kwargs,
            )

    # Chèn một ảnh PNG nhỏ minh hoạ ở góc dưới
    img_pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 40), False)
    img_pix.set_rect(img_pix.irect, (37, 99, 235))
    p1.insert_image(fitz.Rect(55, 370, 155, 420), pixmap=img_pix)

    # ─── Trang 2: Báo cáo kỹ thuật ───
    p2 = doc.new_page(width=595, height=842)
    font_kwargs_p2 = {"fontname": "vnfont2", "fontfile": font_file} if font_file else {"fontname": "helv"}
    p2.insert_text(
        (55, 70),
        "PHẦN II: ĐÁNH GIÁ HIỆU NĂNG VÀ ĐỘ CHÍNH XÁC BỐ CỤC",
        fontsize=13,
        **font_kwargs_p2,
    )
    p2.insert_text(
        (55, 105),
        "Hệ thống QT PDF Pro hỗ trợ cả chế độ tái tạo cấu trúc (Hybrid Structural Flow)",
        fontsize=11,
        **font_kwargs_p2,
    )
    p2.insert_text(
        (55, 125),
        "và chế độ giữ vị trí tuyệt đối 1:1 (Exact Visual Frame) cho biểu mẫu phức tạp.",
        fontsize=11,
        **font_kwargs_p2,
    )

    # Mục lục (TOC)
    doc.set_toc(
        [
            [1, "Phần I: Quyết định hành chính", 1],
            [2, "Bảng kết quả kiểm định", 1],
            [1, "Phần II: Đánh giá hiệu năng", 2],
        ]
    )

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path
