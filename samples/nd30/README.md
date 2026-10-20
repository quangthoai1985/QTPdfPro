# Văn bản mẫu chuẩn Nghị định 30/2020/NĐ-CP (dữ liệu kiểm thử)

Các tệp trong thư mục này có **nội dung hư cấu** (số văn bản, người ký "Nguyễn Văn A", "Lê Văn C", "Trần Thị B" đều không có thật), dùng để kiểm thử engine `nd30` của QT PDF Pro vì **biết trước thông số gốc**:

| Tệp | Nguồn | Thông số gốc |
|---|---|---|
| `quyet_dinh_mau.pdf` / `quyet_dinh_mau_goc.docx` | Quyết định, 2 trang | Lề 20/20/30/20 mm (trên/dưới/trái/phải), Times New Roman 14, giãn dòng 1,5 lines, cách đoạn 6 pt, thụt đầu dòng 1 cm, phần đầu & khối ký trong bảng không viền |
| `ke_hoach_mau.pdf` / `ke_hoach_mau_goc.docx` | Kế hoạch, 2 trang | Lề 25/20/35/15 mm, cỡ 13, giãn dòng Exactly 18 pt, cách đoạn 0 pt (cố ý **không đạt** NĐ30 để kiểm thử đối chiếu), thụt 1,27 cm, bảng dữ liệu có viền; PDF được đóng thêm ảnh con dấu đỏ đè lên chữ ký |
| `cong_van_mau.pdf` | Công văn, 1 trang | Như Quyết định; trích yếu «V/v …» dưới số ký hiệu, «Kính gửi» căn giữa |

Cách tạo: tệp `.docx` gốc sinh bằng bộ tạo văn bản chuẩn NĐ30 (docx-js), sau đó **Microsoft Word 2024** xuất PDF (`ExportAsFixedFormat`) — tức là giống hệt PDF người dùng nhận được từ cơ quan soạn bằng Word.

Kiểm chứng: `python -m qtpdfpro.cli convert samples/nd30/quyet_dinh_mau.pdf -o %TEMP%\qd.docx --mode nd30 --verify-layout`
(không ghi tệp kết quả vào thư mục `samples/`).
