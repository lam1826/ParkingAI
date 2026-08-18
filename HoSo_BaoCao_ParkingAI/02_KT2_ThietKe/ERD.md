# KT2 - THIẾT KẾ CƠ SỞ DỮ LIỆU VÀ ERD

Thiết kế gồm 12 bảng nghiệp vụ, được tách theo thực thể để hạn chế lặp dữ liệu và hỗ trợ chuẩn hóa 3NF.

```mermaid
erDiagram
    ROLES ||--o{ USERS : assigns
    USERS ||--o{ PARKING_SESSIONS : staff_in
    USERS |o--o{ PARKING_SESSIONS : staff_out
    USERS ||--o{ AI_REPORTS : generates
    VEHICLE_TYPES ||--o{ VEHICLES : classifies
    VEHICLE_TYPES ||--o{ PARKING_SLOTS : permits
    VEHICLE_TYPES ||--o{ PRICE_CONFIGS : priced_by
    ZONES ||--o{ PARKING_SLOTS : contains
    CUSTOMERS |o--o{ VEHICLES : owns
    CUSTOMERS ||--o{ MONTHLY_PASSES : registers
    VEHICLES ||--o{ MONTHLY_PASSES : receives
    VEHICLES ||--o{ PARKING_SESSIONS : has
    PARKING_SLOTS |o--o{ PARKING_SESSIONS : assigned_to
    MONTHLY_PASSES |o--o{ PARKING_SESSIONS : validates

    ROLES {
      int id PK
      string name UK
      string description
    }
    USERS {
      int id PK
      int role_id FK
      string username UK
      string password_hash
      string full_name
      boolean is_active
    }
    VEHICLE_TYPES {
      int id PK
      string name
      string description
      boolean is_active
    }
    ZONES {
      int id PK
      string name
      int capacity
      boolean is_active
    }
    PARKING_SLOTS {
      int id PK
      int zone_id FK
      int vehicle_type_id FK
      string slot_name
      boolean is_occupied
      boolean is_active
    }
    CUSTOMERS {
      int id PK
      string full_name
      string phone_number UK
      string email
    }
    VEHICLES {
      int id PK
      int vehicle_type_id FK
      int customer_id FK
      string license_plate UK
    }
    MONTHLY_PASSES {
      int id PK
      int customer_id FK
      int vehicle_id FK
      date start_date
      date end_date
      boolean is_active
    }
    PRICE_CONFIGS {
      int id PK
      int vehicle_type_id FK
      string ticket_type
      float price
      date effective_date
      boolean is_active
    }
    PARKING_SESSIONS {
      string id PK
      int vehicle_id FK
      int parking_slot_id FK
      int monthly_pass_id FK
      datetime check_in_time
      datetime check_out_time
      string image_in_url
      string image_out_url
      float parking_fee
      string status
      int staff_in_id FK
      int staff_out_id FK
    }
    AI_REPORTS {
      int id PK
      int generated_by_id FK
      string report_type
      text prompt_used
      text content
    }
    AUDIT_LOGS {
      int id PK
      int user_id
      string username
      string action
      string resource
      string method
      string path
      int status_code
      boolean success
    }
```

## Quan hệ chính

- Một vai trò có nhiều người dùng; mỗi người dùng thuộc một vai trò.
- Một khu vực chứa nhiều vị trí; mỗi vị trí dành cho một loại xe.
- Một khách hàng có thể sở hữu nhiều xe và đăng ký nhiều vé tháng.
- Một xe có nhiều phiên gửi theo thời gian, nhưng chỉ một phiên được phép `active` tại một thời điểm.
- Một phiên có thể gắn với vị trí và vé tháng; nhân viên vào là bắt buộc, nhân viên ra có thể rỗng trước check-out.
- `audit_logs.user_id` là ảnh chụp ID, không dùng khóa ngoại để lịch sử vẫn tồn tại nếu tài khoản bị xóa.
- Phiên gửi có vé tháng hợp lệ được gắn `monthly_pass_id` ngay khi check-in để truy vết lượt miễn phí.
- SQLite được bật `PRAGMA foreign_keys=ON` (backend/database.py) nên mọi khóa ngoại đều được thực thi;
  thao tác xóa dữ liệu đang được tham chiếu trả về mã 409.
- `image_in_url`/`image_out_url` là cột dự phòng cho hướng phát triển nhận dạng biển số bằng camera,
  hiện chưa có nghiệp vụ ghi giá trị.

## Lý do thiết kế

Các danh mục, giao dịch và lịch sử được tách riêng. Bảng giá lưu theo ngày hiệu lực để bảo toàn lịch sử. Phiên gửi xe tham chiếu các thực thể thay vì lặp tên/biển số/loại xe. Cấu trúc này giảm dư thừa, tránh phụ thuộc bắc cầu và phù hợp chuẩn hóa đến 3NF.
