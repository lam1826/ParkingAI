# HỒ SƠ ĐỒ ÁN PARKINGAI

Thư mục này đóng gói nội dung theo ba phần trên bảng:

1. `01_KT1_KhaoSat_YeuCau`: khảo sát bài toán, phạm vi và yêu cầu hệ thống.
2. `02_KT2_ThietKe`: các biểu đồ UML và sơ đồ ERD.
3. `03_KT3_TrienKhai_KiemThu`: mã nguồn frontend/backend, bộ kiểm thử và kết quả xác minh.
4. `04_BaoCao`: báo cáo tổng hợp định dạng Word.

## Công nghệ

- Backend: FastAPI, SQLAlchemy 2.x, SQLite.
- Frontend: React, Vite, Material UI, Recharts.
- AI: Gemini.
- Kiểm thử: pytest, ESLint và Vite production build.

## Kết quả xác minh ngày 18/08/2026

- Backend: 79 kiểm thử đạt, 1 cảnh báo deprecation từ thư viện TestClient.
- Frontend: ESLint đạt.
- Frontend: production build đạt.

## Lưu ý bảo mật

Bản đóng gói không chứa `.env`, khóa API, cơ sở dữ liệu chạy thật, `node_modules`, môi trường ảo hoặc thư mục build. Hãy tạo `.env` từ `.env.example` trước khi chạy.
