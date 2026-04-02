# 🤖 AI Store Bot — Telegram

Bot Telegram bán sản phẩm AI (ChatGPT Plus, Business Slots, v.v.) với thanh toán QR tự động, ví nội bộ, và liên kết Canboso API.

## ✨ Tính năng

- 🛒 **Mua hàng** — Duyệt và mua sản phẩm AI, giao hàng tự động
- 👛 **Ví** — Nạp tiền qua QR VietQR, tự động xác nhận qua SePay webhook
- 👤 **Hồ sơ** — Xem thông tin tài khoản
- 📜 **Lịch sử** — Theo dõi đơn hàng và giao dịch
- 💬 **Hỗ trợ** — Gửi tin nhắn trực tiếp tới admin
- 🌐 **Đa ngôn ngữ** — Tiếng Việt / English
- 🔧 **Admin** — Dashboard, broadcast, markup settings, nạp ví thủ công

## 🚀 Setup nhanh

### 1. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 2. Tạo bot trên Telegram

1. Mở Telegram, tìm [@BotFather](https://t.me/BotFather)
2. Gửi `/newbot` → đặt tên → lấy **Token**
3. Gửi `/mybots` → chọn bot → **Bot Settings** → **Inline Mode** → Enable

### 3. Cấu hình `.env`

```bash
cp .env.example .env
```

Điền các thông tin:

| Biến | Mô tả | Cách lấy |
|------|--------|----------|
| `TELEGRAM_BOT_TOKEN` | Token từ BotFather | Xem bước 2 |
| `ADMIN_CHAT_ID` | Telegram ID của bạn | Gửi tin nhắn tới [@userinfobot](https://t.me/userinfobot) |
| `CANBOSO_API_KEY` | API key Canboso | Lấy từ Bot B (Liên kết API) |
| `CANBOSO_API_URL` | URL API | `https://canboso.com/api` |
| `SEPAY_SECRET_KEY` | Secret key webhook | Lấy từ SePay dashboard |
| `BANK_BIN` | Mã BIN ngân hàng | [Danh sách BIN](https://api.vietqr.io/v2/banks) |
| `BANK_ACCOUNT` | Số tài khoản | Số TK ngân hàng của bạn |
| `BANK_ACCOUNT_NAME` | Tên chủ TK | Tên trên tài khoản |
| `DEFAULT_MARKUP_PERCENT` | % markup mặc định | Ví dụ: 20 = bán cao hơn 20% |

### 4. Setup SePay (thanh toán tự động)

1. Đăng ký tại [my.sepay.vn](https://my.sepay.vn) (hoặc [sandbox](https://my.dev.sepay.vn) để test)
2. Liên kết tài khoản ngân hàng
3. Vào **Webhooks** → **+ Thêm Webhook**:
   - URL: `http://your-server:8443/webhook/sepay`
   - Sự kiện: "Có tiền vào"
   - Xác thực: API Key → nhập secret key
4. Copy secret key vào `SEPAY_SECRET_KEY` trong `.env`

### 5. Setup VietQR (tạo mã QR)

1. Đăng ký tại [vietqr.io](https://vietqr.io)
2. Lấy `Client ID` và `API Key`
3. Điền vào `VIETQR_CLIENT_ID` và `VIETQR_API_KEY`

> ⚠️ Nếu chưa có VietQR API, bot vẫn tạo được QR offline (chỉ chứa thông tin CK text).

### 6. Chạy bot

```bash
python src/main.py
```

## 📁 Cấu trúc dự án

```
AutoBot-Telegram/
├── .env.example
├── requirements.txt
├── bot.db                  # SQLite (auto-created)
└── src/
    ├── main.py             # Entry point
    ├── config.py           # Config loader
    ├── database/
    │   ├── schema.sql      # DB schema
    │   └── db.py           # Async SQLite wrapper
    ├── services/
    │   ├── canboso.py      # Canboso API client
    │   ├── vietqr.py       # QR generator
    │   └── sepay_webhook.py # Payment webhook
    ├── handlers/
    │   ├── start.py        # Main menu
    │   ├── shop.py         # Product + purchase
    │   ├── wallet.py       # Balance + deposit
    │   ├── profile.py      # User profile
    │   ├── history.py      # Order history
    │   ├── support.py      # Support messages
    │   ├── language.py     # Language switch
    │   └── admin.py        # Admin panel
    ├── i18n/
    │   ├── vi.py           # Tiếng Việt
    │   └── en.py           # English
    └── utils/
        ├── keyboards.py    # Inline keyboards
        ├── formatters.py   # VND, date, account formatting
        └── decorators.py   # Auth, error handling
```

## 🔧 Admin Commands

- `/admin` — Mở admin dashboard
- Broadcast: gửi tin nhắn tới tất cả users
- Markup: cấu hình % markup cho từng sản phẩm
- Manual Credit: nạp ví thủ công cho user

## 🌐 Dev local (ngrok)

Nếu chưa có VPS, dùng ngrok để expose webhook port:

```bash
ngrok http 8443
```

Copy URL ngrok (vd: `https://abc123.ngrok.io`) → cấu hình SePay webhook URL: `https://abc123.ngrok.io/webhook/sepay`
