# Kế Hoạch: Hệ Thống Thông Báo Hàng Về (Restock Broadcast)

Tính năng này giúp Bot tự động gửi tin nhắn thông báo cho toàn bộ người dùng khi phát hiện có số lượng hàng mới được bổ sung từ nguồn (Canboso API), hoạt động giống như một thông báo "Hàng về". Để đảm bảo an toàn và tránh bị Telegram cấm (Ban) vì spam, hệ thống sử dụng quy trình xếp hàng chậm.

---

## 🔴 Phần Cần Bạn Xác Nhận (User Review Required)

> [!WARNING]
> Vì bot sẽ gửi tin nhắn SMS tới TẤT CẢ mọi người có ID lưu ở SQLite Database, tính năng này cực kì hiệu quả khi số lượng người dùng từ nhỏ đến trung bình (< 5.000). Nếu tương lai đạt tới 10.000 - 50.000 user, quá trình gửi có thể mất 15-20 phút và bạn nên chuyển sang dùng Kênh (Channel) riêng.

### ❓ Câu Hỏi Mở (Open Questions)

Bạn muốn mẫu tin nhắn hiển thị trông như thế nào? Dưới đây là mẫu tôi đề xuất:

```text
🚀 HÀNG MỚI VỪA VỀ
📦 Veo3 + Anti Ultra 25K credit BH 24h
➕ Thêm: 57
📦 Tồn kho hiện tại: 62

👉 Bấm /shop để mua ngay không lỡ nhé!
```

*Bạn có muốn chỉnh sửa text nào ở câu chào, hoặc câu "mua ngay" không?*

---

## 🛠️ Chi Tiết Thay Đổi Kỹ Thuật (Nơi phân chia công việc)

### 1. Dịch Vụ API: `src/services/canboso.py`
Nhiệm vụ: Ghi nhớ số tồn kho cũ và phát hiện khi có hàng mới.

* **Thêm Biến Nhớ Tạm**: 
  Thêm `self._last_stock: dict[str, int] = {}` để lưu lại kho hàng sau mỗi lần quét.
  Thêm `self.pending_restocks: list[dict] = []` để lưu danh sách các món hàng vừa được bơm thêm số lượng.
* **So sánh Tồn kho (Delta Logic)**:
  Bên trong hàm `get_products()`, khi lặp qua danh sách sản phẩm lấy được, Bot sẽ so sánh số lượng `available` mới với `_last_stock`.
  *Nếu `Số Mới > Số Cũ` (và món này đã từng được quét trước đó)*, nhét nó vào danh sách `pending_restocks`.
  Cuối cùng, ghi đè `_last_stock` bằng thông tin mới nhất. (Lần đầu khởi động Bot sẽ không báo để tránh spam nguyên cả shop).

### 2. Hệ Điều Phối Lịch: `src/main.py`
Nhiệm vụ: Lấy những hàng bị dồn lại từ bước 1 và tiến hành chiến dịch gửi tin nhắn rải rác. 

* **Thêm hàm `check_and_broadcast_restocks`**:
  * Kiểm tra `canboso.pending_restocks`. Nếu rỗng -> Bỏ qua.
  * Nếu có hàng mới: Gắp danh sách rỗng ra và làm sạch list của Canboso.
  * Ghi lại thành đoạn Text sinh động có Icon (như mẫu ở trên).
  * Lấy `toàn bộ user ID` bằng lệnh `await db.get_all_user_ids()`.
  * **Hệ thống Giảm xóc (Rate Limiting)**: Lồng vòng lặp gửi tin qua cấu trúc `try...except`, sau mỗi tin gửi đi, dùng `await asyncio.sleep(0.05)` (Chờ 50 mili-giây) để đảm bảo không vượt ngưỡng 30 tin/giây của API Telegram. 

* **Gắn vào Scheduler**:
  Cho hàm `check_and_broadcast_restocks` chạy tự động mỗi chu kỳ 1 phút cùng với các tác vụ bảo trì khác.

---

## 🧪 Kế Hoạch Kiểm Tra (Verification Plan)

1. Cố tình sửa DB lưu trữ số lượng hàng tồn của sản phẩm (giả lập việc Canboso tăng kho). Hoặc chúng ta sẽ mua 1 món (để số dư giả từ 10 xuống 9), sau đó chỉnh giá trên file để nó nhảy lại lên 20.
2. Kiểm tra Logs để xem hàm `check_and_broadcast_restocks` có bắt được khoảng chênh (11 món) và tiến hành broadcast hay không.
3. Nhận tin nhắn thông báo trên chính tài khoản Telegram test.
