# Chính sách Bảo mật (Security Policy)

## Nguyên tắc bảo mật của QT PDF Pro

- **Xử lý cục bộ 100% (Offline-First)**: Mọi tệp PDF và DOCX của người dùng đều được đọc, phân tích và chuyển đổi hoàn toàn trên máy tính cục bộ. Ứng dụng **không tải tệp tài liệu lên bất kỳ máy chủ nào**.
- **An toàn XML**: Khi đọc/ghi cấu trúc OpenXML (`.docx`), sử dụng `lxml` với cấu hình không giải mã thực thể ngoại lai (`resolve_entities=False`) để chống lỗ hổng XXE.
- **Báo cáo lỗ hổng**: Vui lòng tạo Issue hoặc báo cáo qua mục Security Advisories trên kho lưu trữ GitHub của dự án.
