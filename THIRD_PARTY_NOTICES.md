# Thông báo Thư viện Bên thứ ba (Third-Party Notices)

**QT PDF Pro** sử dụng các thư viện mã nguồn mở sau đây:

| Thư viện | Giấy phép | Mô tả |
|---|---|---|
| **Python** | PSF License | Ngôn ngữ lập trình và thư viện chuẩn |
| **PySide6 (Qt for Python)** | LGPL-3.0 | Bộ công cụ giao diện người dùng đa nền tảng |
| **PyMuPDF (fitz)** | AGPL-3.0 / Commercial | Engine đọc, kết xuất và phân tích bố cục PDF tốc độ cao |
| **pdf2docx** | GPL-3.0 | Thư viện phân tích hình học PDF sang cấu trúc DOCX |
| **python-docx** | MIT License | Thư viện đọc/ghi tệp Word OpenXML (.docx) |
| **lxml** | BSD-3-Clause | Thư viện xử lý XML/HTML tốc độ cao (dùng cho hậu xử lý OpenXML) |
| **fonttools** | MIT License | Xử lý thông tin bảng mã và phông chữ |
| **NumPy** | BSD-3-Clause | Tính toán mảng số học |
| **OpenCV (opencv-python-headless)** | Apache-2.0 | Xử lý ảnh hỗ trợ phân tích bố cục |
| **ONNX Runtime (onnxruntime)** | MIT License | Chạy mô hình OCR tiếng Việt trên CPU |

## Mô hình OCR tiếng Việt (tải khi dùng lần đầu, không nằm trong bộ cài)

Bộ `QTPdfPro_OCR_vi_v1.zip` (dựng bằng `tools/export_ocr_models.py`, tải từ GitHub Release `ocr-models-v1` vào
`%LOCALAPPDATA%\QTPdfPro\modules\ocr-vi-1\`, có tệp `NOTICE.txt` đi kèm):

| Mô hình | Giấy phép | Nguồn |
|---|---|---|
| **PP-OCRv6 det small** (tìm dòng chữ) | Apache-2.0 | PaddleOCR — https://github.com/PaddlePaddle/PaddleOCR ; bản ONNX của RapidOCR (Apache-2.0) — https://github.com/RapidAI/RapidOCR |
| **VietOCR vgg_seq2seq** (đọc chữ tiếng Việt, chuyển sang ONNX) | Apache-2.0 | VietOCR — https://github.com/pbcquoc/vietocr |
