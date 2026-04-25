# 🗄️ Bản Đồ Database — Giải Thích Tiếng Việt

> File gốc: `src/database/schema.sql`
> Database: SQLite (file `bot.db`)

---

## 1. `users` — Bảng người dùng

| Cột | Kiểu | Ý nghĩa |
|-----|------|---------|
| `id` | Số tự tăng | ID nội bộ (dùng trong các bảng khác) |
| `telegram_id` | Số | ID Telegram của user (duy nhất) |
| `username` | Text | Username Telegram (VD: @dunguser) |
| `full_name` | Text | Tên hiển thị trên Telegram |
| `balance` | Số nguyên | **Số dư ví** (đơn vị VNĐ, VD: 150000 = 150k) |
| `language` | Text | Ngôn ngữ: `vi` hoặc `en` |
| `referral_code` | Text | ⚠️ Không dùng nữa (đã tắt referral) |
| `referred_by` | Số | ⚠️ Không dùng nữa |
| `created_at` | Thời gian | Ngày đăng ký (lần đầu bấm /start) |
| `updated_at` | Thời gian | Lần cuối cập nhật (đổi số dư hoặc ngôn ngữ) |

---

## 2. `product_markups` — Cài đặt giá bán từng sản phẩm

| Cột | Kiểu | Ý nghĩa |
|-----|------|---------|
| `product_id` | Text | ID sản phẩm trên Canboso |
| `product_name` | Text | Tên SP (lưu lại để admin dễ đọc) |
| `markup_percent` | Số | **% lợi nhuận** cộng thêm (VD: 30 = cộng 30% giá vốn) |
| `fixed_price` | Số | **Giá cố định** (nếu > 0 thì bỏ qua markup %) |
| `is_active` | 0/1 | 1 = hiện trong shop, 0 = ẩn |
| `custom_note` | Text | Ghi chú của shop hiện dưới mô tả SP |

---

## 3. `deposits` — Lệnh nạp tiền

| Cột | Kiểu | Ý nghĩa |
|-----|------|---------|
| `user_id` | Số | → liên kết tới `users.id` |
| `amount` | Số | Số tiền nạp (VNĐ) |
| `code` | Text | Mã chuyển khoản (VD: `NAP123`) |
| `status` | Text | `pending` = đang chờ, `completed` = đã nạp, `expired` = hết hạn |
| `reference_code` | Text | Mã giao dịch từ SePay (chống trùng) |
| `expires_at` | Thời gian | Hết hạn sau 5 phút |
| `completed_at` | Thời gian | Thời điểm nạp thành công |

**Luồng:** User bấm Nạp tiền → tạo `pending` → chuyển khoản → SePay webhook xác nhận → `completed`

---

## 4. `orders` — Đơn hàng

| Cột | Kiểu | Ý nghĩa |
|-----|------|---------|
| `user_id` | Số | → liên kết tới `users.id` |
| `order_code` | Text | Mã đơn trên Canboso (sau khi mua sỉ thành công) |
| `product_id` | Text | ID sản phẩm Canboso |
| `product_name` | Text | Tên SP |
| `quantity` | Số | Số lượng mua |
| `original_price` | Số | **Giá vốn** (giá mua từ Canboso) |
| `sell_price` | Số | **Giá bán** (sau markup, user trả giá này) |
| `total_amount` | Số | **Tổng tiền** = `sell_price × quantity` |
| `delivered_data` | JSON | Tài khoản đã giao (user/pass/email) |
| `status` | Text | `completed` / `pending` / `failed` / `expired` |

**Tính lãi:** `total_amount - (original_price × quantity)` = lợi nhuận

---

## 5. `transactions` — Lịch sử giao dịch ví

| Cột | Kiểu | Ý nghĩa |
|-----|------|---------|
| `user_id` | Số | → liên kết tới `users.id` |
| `type` | Text | Loại: `deposit` (nạp), `purchase` (mua), `refund` (hoàn), `admin_credit` (admin nạp) |
| `amount` | Số | Số tiền (dương = cộng vào ví, âm = trừ từ ví) |
| `balance_after` | Số | Số dư SAU giao dịch |
| `description` | Text | Mô tả (VD: "Nạp tiền NAP123") |
| `reference_id` | Text | Liên kết tới deposit.id hoặc order.id |

---

## 6. `custom_products` — Sản phẩm tự thêm (không qua Canboso)

| Cột | Kiểu | Ý nghĩa |
|-----|------|---------|
| `name` | Text | Tên SP |
| `price` | Số | Giá bán (VNĐ) |
| `is_active` | 0/1 | 1 = hiện, 0 = ẩn |

---

## 7. `processed_webhooks` — Chống trùng webhook

| Cột | Kiểu | Ý nghĩa |
|-----|------|---------|
| `reference_code` | Text | Mã tham chiếu SePay (mỗi giao dịch ngân hàng 1 mã) |
| `prefix` | Text | `NAP` (nạp tiền) hoặc `MUA` (mua hàng) |
| `code_id` | Số | ID deposit hoặc order |
| `status` | Text | `processing` / `completed` / `failed` |

**Mục đích:** Nếu SePay gửi webhook 2 lần cho cùng 1 giao dịch → bảng này chặn xử lý lần 2.

---

## Sơ đồ liên kết

```
users (1) ──→ (N) deposits      "1 user có nhiều lệnh nạp"
users (1) ──→ (N) orders         "1 user có nhiều đơn hàng"  
users (1) ──→ (N) transactions   "1 user có nhiều giao dịch"
```
