# English strings
EN = {
    # General
    "welcome": (
        "🎯 <b>Welcome to {bot_name}!</b>\n\n"
        "📌 Quick guide:\n"
        "1. Tap \"🛒 Shop\".\n"
        "2. Choose the product you want.\n"
        "3. Pay via QR code.\n"
        "4. Bot will auto-deliver your order.\n\n"
        "💡 Please choose from the menu:"
    ),
    "btn_shop": "🛒 Shop",
    "btn_profile": "👤 Profile",
    "btn_history": "📜 Purchase History",
    "btn_wallet": "👛 Wallet",
    "btn_support": "💬 Support",
    "btn_language": "🌐 Language",
    "btn_back": "⬅️ Back",
    "btn_back_menu": "⬅️ Main Menu",
    "btn_confirm": "✅ Confirm",
    "btn_cancel": "❌ Cancel",

    # Shop
    "shop_title": "🛒 <b>Products</b>\n\nSelect a product to purchase:",
    "shop_empty": "📭 No products available at the moment.",
    "product_detail": (
        "📦 <b>{name}</b>\n\n"
        "📝 {description}\n\n"
        "💰 Price: <b>{price}</b>\n"
        "{slot_info}"
        "\n🔢 Quantity: {quantity}"
    ),
    "slot_info": "📊 Available slots: {available}/{total}\n",
    "confirm_purchase": (
        "🛒 <b>Confirm Order</b>\n\n"
        "📦 Product: {name}\n"
        "🔢 Quantity: {quantity}\n"
        "💰 Price: {price}\n"
        "💵 Total: <b>{total}</b>\n\n"
        "💳 Wallet balance: {balance}\n\n"
        "Are you sure you want to purchase?"
    ),
    "purchase_success": (
        "✅ <b>Purchase successful!</b>\n\n"
        "🔐 <b>YOUR ACCOUNT:</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "{accounts}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "📦 {name} x{quantity}\n"
        "💰 Paid: {total}"
    ),
    "account_info": (
        "━━━━━━━━━━━━━━━\n"
        "👤 User: <code>{user}</code>\n"
        "🔑 Pass: <code>{password}</code>\n"
        "📧 Verify: <code>{verify_email}</code>\n"
    ),
    "purchase_insufficient": "❌ Insufficient balance!\n\n💳 Balance: {balance}\n💰 Required: {total}\n\nPlease top up your wallet.",
    "purchase_error": "❌ An error occurred. Please try again later.\n\nError: {error}",
    "product_out_of_stock": "❌ Product is out of stock.",
    "btn_buy": "🛒 Buy Now",
    "btn_quantity_up": "➕",
    "btn_quantity_down": "➖",

    # Wallet
    "wallet_title": (
        "👛 <b>Your Wallet</b>\n\n"
        "💰 Balance: <b>{balance}</b>\n\n"
        "Select an action:"
    ),
    "btn_deposit": "💳 Deposit",
    "btn_tx_history": "📜 Transaction History",
    "deposit_enter_amount": "💳 <b>Deposit</b>\n\nPlease enter the amount (VND):\n\n<i>Example: 50000, 100000, 200000</i>",
    "deposit_invalid_amount": "❌ Invalid amount. Please enter a number (minimum 10,000đ).",
    "deposit_qr": (
        "🏦 <b>Transfer to {bank_name} - {bank_account}</b>\n"
        "👤 Account holder: <b>{bank_account_name}</b>\n\n"
        "💰 Amount: <b>{amount}</b>\n"
        "📝 Transfer note: <code>{code}</code>\n"
        "⏰ Time remaining: <b>{expire_min} minutes</b>\n\n"
        "📱 Scan the QR code below to transfer.\n"
        "⚠️ <b>Note:</b> Enter the exact transfer note!"
    ),
    "deposit_success": "✅ <b>Deposit successful!</b>\n\n💰 Amount: {amount}\n💳 New balance: {balance}",
    "deposit_expired": "⏰ Deposit request has expired.",
    "tx_history_title": "📜 <b>Transaction History</b>\n\n",
    "tx_item": "{icon} {description} — <b>{amount}</b>\n   <i>{date}</i>\n\n",
    "tx_empty": "📭 No transactions yet.",

    # Profile
    "profile_title": (
        "👤 <b>Your Profile</b>\n\n"
        "📛 Name: {full_name}\n"
        "🆔 Username: @{username}\n"
        "💰 Balance: <b>{balance}</b>\n"
        "🛒 Total orders: {total_orders}\n"
        "📅 Joined: {joined}\n"
    ),

    # History
    "history_title": "📜 <b>Purchase History</b>\n\n",
    "history_item": "{status_icon} <b>{name}</b> x{qty}\n   💰 {price} — {date}\n\n",
    "history_empty": "📭 You haven't purchased anything yet.",
    "history_detail": (
        "📦 <b>Order #{id}</b>\n\n"
        "📋 Product: {name}\n"
        "🔢 Quantity: {quantity}\n"
        "💰 Price: {price}\n"
        "📅 Date: {date}\n\n"
        "📋 <b>Account details:</b>\n"
        "{accounts}"
    ),
    "btn_view_detail": "📋 View Details",
    "btn_prev_page": "⬅️ Prev",
    "btn_next_page": "➡️ Next",

    # Support
    "support_title": (
        "💬 <b>Support</b>\n\n"
        "Need help? Send us a message describing your issue.\n"
        "Our team will respond as soon as possible."
    ),
    "support_sent": "✅ Message sent to support team.\nWe'll get back to you soon!",
    "support_admin_notify": "📩 <b>Support Message</b>\n\nFrom: {user} (@{username})\nID: <code>{user_id}</code>\n\n{message}",

    # Language
    "language_title": "🌐 <b>Chọn ngôn ngữ / Select language</b>",
    "language_changed": "✅ Language changed to English.",

    # Admin
    "admin_title": (
        "🔧 <b>Admin Dashboard</b>\n\n"
        "👥 Total users: {users}\n"
        "🛒 Orders today: {today_orders}\n"
        "💰 Total revenue: {revenue}\n"
        "💳 Canboso balance: {canboso_balance}\n"
    ),
    "btn_admin_broadcast": "📢 Broadcast",
    "btn_admin_markup": "💰 Markup",
    "btn_admin_manual_credit": "💳 Manual Credit",
    "admin_broadcast_prompt": "📢 Enter broadcast message:",
    "admin_broadcast_done": "✅ Broadcast sent to {count} users.",
    "admin_credit_prompt": "💳 Enter Telegram ID and amount:\n\nExample: <code>123456789 100000</code>",
    "admin_credit_done": "✅ Credited {amount} to user {user_id}.\nNew balance: {balance}",

    # Errors
    "error_generic": "❌ An error occurred. Please try again.",
    "error_not_admin": "❌ Access denied.",
}
