# Vietnamese strings
VI = {
    # General
    "welcome": (
        "🎯 <b>Chào mừng bạn đến với {bot_name}!</b>\n\n"
        "📌 Hướng dẫn nhanh:\n"
        "1. Nhấn nút \"🛒 Mua hàng\".\n"
        "2. Chọn sản phẩm bạn muốn mua.\n"
        "3. Thanh toán bằng QR và quét mã để thanh toán.\n"
        "4. Sau khi thanh toán xong, bot sẽ tự động xử lý đơn hàng.\n\n"
        "💡 Vui lòng chọn menu:"
    ),
    "btn_shop": "🛒 Mua hàng",
    "btn_profile": "👤 Hồ sơ",
    "btn_history": "📜 Lịch sử mua",
    "btn_wallet": "👛 Ví",
    "btn_support": "💬 Hỗ trợ",
    "btn_language": "🌐 Ngôn ngữ",
    "btn_back": "⬅️ Quay lại",
    "btn_back_menu": "⬅️ Menu chính",
    "btn_confirm": "✅ Xác nhận",
    "btn_cancel": "❌ Hủy",

    # Shop
    "shop_title": "🛒 <b>Danh sách sản phẩm</b>\n\nChọn sản phẩm bạn muốn mua:",
    "shop_empty": "📭 Hiện tại chưa có sản phẩm nào.",
    "product_detail": (
        "📦 <b>{name}</b>\n\n"
        "📝 {description}\n\n"
        "💰 Giá: <b>{price}</b>\n"
        "{slot_info}"
        "\n🔢 Số lượng: {quantity}"
    ),
    "slot_info": "📊 Còn lại: {available} sản phẩm\n",
    "confirm_purchase": (
        "🛒 <b>Xác nhận đơn hàng</b>\n\n"
        "📦 Sản phẩm: {name}\n"
        "🔢 Số lượng: {quantity}\n"
        "💰 Đơn giá: {price}\n"
        "💵 Tổng cộng: <b>{total}</b>\n\n"
        "💳 Số dư ví: {balance}\n\n"
        "Bạn có chắc chắn muốn mua?"
    ),
    "purchase_success": (
        "✅ <b>Mua hàng thành công!</b>\n\n"
        "📦 Sản phẩm: {name}\n"
        "🔢 Số lượng: {quantity}\n"
        "💵 Đã trừ: {total}\n"
        "💳 Số dư còn: {balance}\n\n"
        "📋 <b>Thông tin tài khoản:</b>\n"
        "{accounts}"
    ),
    "account_info": (
        "━━━━━━━━━━━━━━━\n"
        "👤 User: <code>{user}</code>\n"
        "🔑 Pass: <code>{password}</code>\n"
        "📧 Verify: <code>{verify_email}</code>\n"
    ),
    "purchase_insufficient": "❌ Số dư không đủ!\n\n💳 Số dư: {balance}\n💰 Cần: {total}\n\nVui lòng nạp thêm tiền vào ví.",
    "purchase_error": "❌ Có lỗi xảy ra khi mua hàng. Vui lòng thử lại sau.\n\nLỗi: {error}",
    "product_out_of_stock": "❌ Sản phẩm đã hết hàng.",
    "btn_buy": "🛒 Mua ngay",
    "btn_quantity_up": "➕",
    "btn_quantity_down": "➖",

    # Wallet
    "wallet_title": (
        "👛 <b>Ví của bạn</b>\n\n"
        "💰 Số dư: <b>{balance}</b>\n\n"
        "Chọn thao tác:"
    ),
    "btn_deposit": "💳 Nạp tiền",
    "btn_tx_history": "📜 Lịch sử giao dịch",
    "deposit_enter_amount": "💳 <b>Nạp tiền</b>\n\nVui lòng nhập số tiền muốn nạp (VNĐ):\n\n<i>Ví dụ: 50000, 100000, 200000</i>",
    "deposit_invalid_amount": "❌ Số tiền không hợp lệ. Vui lòng nhập số nguyên (tối thiểu 10,000đ).",
    "deposit_qr": (
        "💳 <b>Nạp tiền</b>\n\n"
        "💰 Số tiền: <b>{amount}</b>\n"
        "📝 Nội dung CK: <code>{code}</code>\n"
        "⏰ Hết hạn sau: {expire_min} phút\n\n"
        "📱 Quét mã QR bên dưới để chuyển khoản.\n"
        "⚠️ <b>Lưu ý:</b> Nhập đúng nội dung chuyển khoản!"
    ),
    "deposit_success": "✅ <b>Nạp tiền thành công!</b>\n\n💰 Số tiền: {amount}\n💳 Số dư mới: {balance}",
    "deposit_expired": "⏰ Lệnh nạp tiền đã hết hạn.",
    "tx_history_title": "📜 <b>Lịch sử giao dịch</b>\n\n",
    "tx_item": "{icon} {description} — <b>{amount}</b>\n   <i>{date}</i>\n\n",
    "tx_empty": "📭 Chưa có giao dịch nào.",

    # Profile
    "profile_title": (
        "👤 <b>Hồ sơ của bạn</b>\n\n"
        "📛 Tên: {full_name}\n"
        "🆔 Username: @{username}\n"
        "💰 Số dư: <b>{balance}</b>\n"
        "🛒 Tổng đơn hàng: {total_orders}\n"
        "📅 Ngày tham gia: {joined}\n"
    ),

    # History
    "history_title": "📜 <b>Lịch sử mua hàng</b>\n\n",
    "history_item": "🔹 <b>{name}</b> x{qty}\n   💰 {price} — {date}\n\n",
    "history_empty": "📭 Bạn chưa mua sản phẩm nào.",
    "history_detail": (
        "📦 <b>Chi tiết đơn hàng #{id}</b>\n\n"
        "📋 Sản phẩm: {name}\n"
        "🔢 Số lượng: {quantity}\n"
        "💰 Giá: {price}\n"
        "📅 Ngày mua: {date}\n\n"
        "📋 <b>Thông tin tài khoản:</b>\n"
        "{accounts}"
    ),
    "btn_view_detail": "📋 Xem chi tiết",
    "btn_prev_page": "⬅️ Trước",
    "btn_next_page": "➡️ Sau",

    # Support
    "support_title": (
        "💬 <b>Hỗ trợ</b>\n\n"
        "Bạn cần hỗ trợ? Hãy gửi tin nhắn mô tả vấn đề của bạn ngay tại đây.\n"
        "Đội ngũ hỗ trợ sẽ nhận được thông báo và phản hồi sớm nhất có thể.\n\n"
        "Hoặc liên hệ trực tiếp Admin: @dunghanhshop"
    ),
    "support_sent": "✅ Tin nhắn đã được gửi tới đội ngũ hỗ trợ.\nChúng tôi sẽ phản hồi sớm nhất!",
    "support_admin_notify": "📩 <b>Tin nhắn hỗ trợ</b>\n\nTừ: {user} (@{username})\nID: <code>{user_id}</code>\n\n{message}",

    # Language
    "language_title": "🌐 <b>Chọn ngôn ngữ / Select language</b>",
    "language_changed": "✅ Đã chuyển sang Tiếng Việt.",

    # Admin
    "admin_title": (
        "🔧 <b>Admin Dashboard</b>\n\n"
        "👥 Tổng users: {users}\n"
        "🛒 Đơn hàng hôm nay: {today_orders}\n"
        "💰 Tổng doanh thu: {revenue}\n"
        "💳 Số dư Canboso: {canboso_balance}\n"
    ),
    "btn_admin_broadcast": "📢 Broadcast",
    "btn_admin_markup": "💰 Markup",
    "btn_admin_manual_credit": "💳 Nạp ví thủ công",
    "admin_broadcast_prompt": "📢 Nhập tin nhắn broadcast:",
    "admin_broadcast_done": "✅ Đã gửi broadcast tới {count} users.",
    "admin_credit_prompt": "💳 Nhập Telegram ID và số tiền:\n\nVí dụ: <code>123456789 100000</code>",
    "admin_credit_done": "✅ Đã nạp {amount} cho user {user_id}.\nSố dư mới: {balance}",

    # Errors
    "error_generic": "❌ Có lỗi xảy ra. Vui lòng thử lại sau.",
    "error_not_admin": "❌ Bạn không có quyền truy cập.",
}
