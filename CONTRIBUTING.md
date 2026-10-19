# Hướng dẫn Đóng góp (Contributing)

Cảm ơn bạn đã quan tâm đóng góp cho **QT PDF Pro**!

## Quy trình làm việc cho Lập trình viên & AI Agent

1. **Đọc tài liệu bàn giao**:
   - Đọc kỹ [CLAUDE.md](CLAUDE.md) (hoặc [AGENTS.md](AGENTS.md)) và [CHANGELOG.md](CHANGELOG.md) trước khi viết mã.
   - Xem thiết kế kỹ thuật tại [docs/THIET_KE.md](docs/THIET_KE.md) và nghiên cứu công nghệ tại [docs/NGHIEN_CUU_CONG_NGHE.md](docs/NGHIEN_CUU_CONG_NGHE.md).
2. **Môi trường phát triển**:
   ```bash
   python -m pip install -r requirements.txt
   python -m pytest -q tests
   ```
3. **Quy tắc kiểm thử**:
   - Mọi thay đổi trong `qtpdfpro/core/` phải có bài test tự động trong `tests/`.
   - Luôn chạy thử với biến môi trường `QT_PDF_PRO_DATA` trỏ tới thư mục tạm để không ảnh hưởng dữ liệu người dùng.
   - Sau mỗi phiên làm việc: cập nhật `CHANGELOG.md`, `CLAUDE.md`, chạy `pytest` xanh 100%, sau đó `git commit` và `git push`.
