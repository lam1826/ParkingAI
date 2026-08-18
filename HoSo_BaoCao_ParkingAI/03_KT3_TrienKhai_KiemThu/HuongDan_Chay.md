# HƯỚNG DẪN CÀI ĐẶT VÀ CHẠY

## Yêu cầu

- Python 3.11 trở lên.
- Node.js 20 trở lên.

## Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r SourceCode\backend\requirements.txt
Copy-Item SourceCode\backend\.env.example SourceCode\backend\.env
Set-Location SourceCode\backend
uvicorn main:app --reload
```

Cập nhật `SECRET_KEY`, `GEMINI_API_KEY`, `MANAGER_REGISTRATION_CODE` và `ADMIN_REGISTRATION_CODE` trong `.env` trước khi chạy thực tế.

## Frontend

```powershell
Set-Location SourceCode\frontend
npm.cmd install
npm.cmd run dev
```

- Giao diện: `http://localhost:5173`
- Swagger API: `http://127.0.0.1:8000/docs`

## Kiểm thử

Thư mục `tests` đã nằm cạnh `backend` trong `SourceCode`. Chạy từ thư mục `SourceCode`:

```powershell
Set-Location SourceCode
..\..\..\.venv\Scripts\python.exe -m pytest tests -q
```

(Hoặc kích hoạt virtualenv rồi chạy `python -m pytest tests -q`.) Kết quả mong đợi: toàn bộ test đạt.
