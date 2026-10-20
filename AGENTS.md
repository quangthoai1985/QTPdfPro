# AGENTS.md — Hướng dẫn Bàn giao Dự án QT PDF Pro cho AI Agent

> Mọi AI Agent (Antigravity, Claude, Cursor, GitHub Copilot, Windsurf...) khi làm việc với kho mã nguồn này **bắt buộc phải đọc tệp [CLAUDE.md](CLAUDE.md) và [CHANGELOG.md](CHANGELOG.md) trước tiên**.

## Tóm tắt nhanh cho Agent

1. **Tên dự án**: **QT PDF Pro** (`v0.4.0`) — Ứng dụng chuyên đọc PDF & chuyển đổi PDF sang DOCX chuẩn xác từng thành phần.
2. **Ngăn xếp công nghệ**: Python 3.14 + PySide6 (Qt6) + PyMuPDF (`fitz`) + `pdf2docx` + `python-docx` + `lxml` (OpenXML Precision Fixer).
3. **Tài liệu cốt lõi**:
   - Bàn giao toàn diện (Kiến trúc, Quy tắc, Rào cản kỹ thuật, Việc cần làm tiếp): **[CLAUDE.md](CLAUDE.md)**
   - Nhật ký phiên bản & lịch sử từng phiên làm việc: **[CHANGELOG.md](CHANGELOG.md)**
   - Nghiên cứu & Đề xuất công nghệ: **[docs/NGHIEN_CUU_CONG_NGHE.md](docs/NGHIEN_CUU_CONG_NGHE.md)**
   - Thiết kế kỹ thuật chi tiết: **[docs/THIET_KE.md](docs/THIET_KE.md)**
   - Lộ trình tính năng: **[docs/DE_XUAT_TINH_NANG.md](docs/DE_XUAT_TINH_NANG.md)**
4. **Quy trình bắt buộc cuối mỗi phiên làm việc**:
   - Chạy `python -m pytest -q tests` đảm bảo toàn bộ test vượt qua 100%.
   - Cập nhật [CHANGELOG.md](CHANGELOG.md) và [CLAUDE.md](CLAUDE.md) để ghi nhận tiến độ cho Agent kế tiếp.
   - Thực hiện `git commit` và `git push` lên GitHub (`quangthoai1985/QTPdfPro`).
