# Giá lúc nhận xe và xử lý ngoại lệ

P1 của phương án đã duyệt. Mã đã ghép, kiểm tra chức năng/API/UI và phục hồi đã đạt; hồi quy baseline và kiểm lại hai fixture được ghi riêng; kết quả nghiệm thu được ghi trong IMPLEMENTATION.md, không suy từ tài liệu này.

## Căn cứ tính phí

Lượt mới lưu phiên bản `entry-v1`, mã bảng giá nguồn, đơn giá VND, loại block giờ/ngày và ngày hiệu lực lúc nhận xe. Các giá trị này không sửa lại trong vòng đời lượt gửi. Đơn giá thay đổi chỉ tác động lượt nhận sau đó.

Thời gian thu được làm tròn lên theo block: 1 giờ hoặc 24 giờ, tùy bảng giá. Phần lẻ một giây vẫn tính trong block tiếp theo; phép tính dùng số nguyên để tránh sai ở biên thời gian. Thời lượng bằng 0 có 0 block. Frontend hiển thị căn cứ và số tiền server trả, không tự tính tiền.

Vé tháng chốt quyền lợi khi nhận xe, đến hết ngày cuối đã được thanh toán. Lượt `entry-v1` chỉ thu thời gian sau mốc 00:00 ngày tiếp theo. Ví dụ vào 23:00 ngày 15/09, vé hết 15/09, ra 00:30 ngày 16/09: thu 30 phút ngoài quyền lợi, làm tròn một block giờ. Gia hạn sau khi xe đã vào không thay snapshot của lượt đang mở.

Quote giữ hạn 120 giây và ràng buộc lượt/nhân viên/trạng thái/căn cứ phí. Người vận hành xem phí rồi xác nhận đã thu hoặc xác nhận miễn phí. Trả xe và phiếu thu cùng giao dịch; thử lại cùng xác nhận không thu thêm lần nữa. Nếu bước đầu chưa rõ thành công, dùng lại yêu cầu đang giữ.

## Lượt cũ

Migration chỉ thêm cột nullable. Lượt cũ không có đủ bằng chứng giá lúc vào giữ `billing_policy_version = NULL`, không được điền đơn giá phỏng đoán.

Lượt cũ đang mở tiếp tục cách tính trước nâng cấp: chọn giá hiện hành và có thể tính cả lượt nếu ra ngoài thời hạn vé tháng. Bảng giá vẫn bị bảo vệ khi còn loại lượt này phụ thuộc vào nó. Phiếu thu, thời gian và tiền của lượt đã hoàn tất được giữ nguyên. Chi tiết thiếu căn cứ snapshot ghi rõ giới hạn đó.

Các trường snapshot của lượt mới và căn cứ tính phí được đọc lại từ thời gian cùng phiên bản chính sách đã lưu. Mọi thay đổi chính sách tính sau này cần phiên bản mới, không đổi nghĩa `entry-v1` để tính lại lịch sử.

## Ngoại lệ vận hành

| Thao tác | Ai xác nhận | Kết quả |
|---|---|---|
| Hủy nhận nhầm | Quản lý | Lượt chuyển sang đã hủy, trả chỗ, giữ lý do/người/thời gian và dữ liệu trước/sau |
| Mất vé | Quản lý | Ghi xác nhận sau khi kiểm tra xe; nhân viên tiếp tục trả xe bình thường, không tự cộng tiền phạt |
| Sửa biển đã nhận | Quản lý | Hủy lượt sai và tạo vé thay thế trong một giao dịch; giữ giờ vào, loại xe, chỗ, nhân viên vào và đơn giá đã chốt |
| Hoàn tiền | Quản lý | Dùng luồng hoàn hiện có, gắn phiếu thu gốc và lý do, không vượt số tiền còn được hoàn |

Hủy không áp dụng lượt đã có chứng từ hoặc đang gắn quyền vé/đặt chỗ cần xử lý riêng. Sửa biển bằng vé thay thế áp dụng lượt `entry-v1` của xe vãng lai cùng loại, chưa gắn khách, vé tháng, nhóm xe hoặc đặt chỗ. Hệ thống hiển thị lý do khi không đủ điều kiện; không sửa biển trên hồ sơ xe cũ để làm đổi lịch sử.

Mỗi yêu cầu ngoại lệ có mã riêng để thử lại. Dùng lại mã với lý do/người/thao tác khác bị từ chối. Nhật ký ngoại lệ không cho sửa/xóa; lượt nguồn và lượt thay thế có liên kết. Báo cáo lưu lượng bỏ lượt đã hủy, còn tra cứu lịch sử vẫn hiển thị chúng. Có thể tìm chính xác theo mã lượt bên cạnh bộ lọc biển số, trạng thái và ngày vào.

## Nâng cấp và phục hồi

SQLite dùng công cụ `db_rollout` đã có; PostgreSQL có migration Alembic thêm snapshot và bảng sự kiện. Đường SQLite kiểm bản sao trước khi công bố file mới. `scripts/verify_single_lot_upgrade.py` tạo bản sao mới, so sánh giá trị cột cũ, chỉ cho phép phần nhập bù tài chính lịch sử được xác minh (liên kết thẻ và biên nhận 0 đồng cho ba vé mẫu miễn phí), chạy migration lặp, integrity/foreign-key/readiness và xác nhận không bịa snapshot cho lượt cũ.

Giữ bản trước migration và kiểm khôi phục trên file riêng. Sau khi có lượt `entry-v1`, phiên bản ứng dụng chạy phải hiểu chính sách này. Quay thẳng về backend P0 có thể làm sai phí cho lượt đang gửi, vì P0 đọc giá hiện hành. Ưu tiên sửa tiếp trên phiên bản tương thích hoặc rollback riêng giao diện; không bỏ dữ liệu snapshot/sự kiện để hạ phiên bản.

DB nghiệm thu được tách khỏi DB trình bày và dữ liệu cũ. Khôi phục bản sao cũ chỉ là rehearsal; không dùng nó để ghi đè các chứng từ mới phát sinh.
