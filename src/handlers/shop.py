import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.config import config
from src.i18n import t
from src.utils.decorators import ensure_user, error_handler
from src.utils.formatters import format_vnd
from src.utils.keyboards import product_detail_keyboard, back_to_menu_keyboard, confirm_cancel_keyboard

logger = logging.getLogger(__name__)


@error_handler
@ensure_user
async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product listing."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]

    products = await canboso.get_products()
    if not products:
        await query.edit_message_text(
            t("shop_empty", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    keyboard = []
    for p in products:
        if p.get("hiddenInBotMenu"):
            continue
        name = p.get("product_name", "Unknown")
        price = p.get("walletPricing", 0)
        product_id = p.get("_id", "")

        markup = await db.get_markup(product_id, config.default_markup_percent)
        sell_price = int(price * (1 + markup / 100))

        stats = p.get("stats", {})
        available = stats.get("available")
        stock_text = f" ({available})" if available is not None else ""

        keyboard.append([
            InlineKeyboardButton(
                f"{name} — {format_vnd(sell_price)}{stock_text}",
                callback_data=f"shop:detail:{product_id}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(t("btn_back_menu", lang), callback_data="menu:main")
    ])

    await query.edit_message_text(
        t("shop_title", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


@error_handler
@ensure_user
async def product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show product detail with quantity selector."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]

    parts = query.data.split(":")
    product_id = parts[2]
    quantity = int(parts[3]) if len(parts) > 3 else 1

    product = canboso.find_product(product_id)
    if not product:
        await canboso.refresh_cache()
        product = canboso.find_product(product_id)

    if not product:
        await query.edit_message_text(
            t("product_out_of_stock", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    markup = await db.get_markup(product_id, config.default_markup_percent)
    sell_price = int(product.get("walletPricing", 0) * (1 + markup / 100))

    stats = product.get("stats", {})
    slot_info = ""
    if stats.get("total") is not None:
        slot_info = t("slot_info", lang,
            available=stats.get("available", 0),
            total=stats.get("total", 0),
        )

    text = t("product_detail", lang,
        name=product.get("product_name", ""),
        description=product.get("description", ""),
        price=format_vnd(sell_price),
        slot_info=slot_info,
        quantity=quantity,
    )

    keyboard = product_detail_keyboard(product_id, quantity, lang)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


@error_handler
@ensure_user
async def quantity_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quantity +/- buttons."""
    await product_detail(update, context)


@error_handler
@ensure_user
async def buy_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show purchase confirmation."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]
    db_user = context.user_data["db_user"]

    parts = query.data.split(":")
    product_id = parts[2]
    quantity = int(parts[3]) if len(parts) > 3 else 1

    product = canboso.find_product(product_id)
    if not product:
        await query.edit_message_text(
            t("product_out_of_stock", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    markup = await db.get_markup(product_id, config.default_markup_percent)
    sell_price = int(product.get("walletPricing", 0) * (1 + markup / 100))
    total = sell_price * quantity
    balance = db_user["balance"]

    text = t("confirm_purchase", lang,
        name=product.get("product_name", ""),
        quantity=quantity,
        price=format_vnd(sell_price),
        total=format_vnd(total),
        balance=format_vnd(balance),
    )

    keyboard = confirm_cancel_keyboard(
        f"shop:execute:{product_id}:{quantity}", lang
    )
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


@error_handler
@ensure_user
async def execute_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute the actual purchase via Canboso API."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "vi")
    db = context.bot_data["db"]
    canboso = context.bot_data["canboso"]
    db_user = context.user_data["db_user"]
    telegram_id = update.effective_user.id

    parts = query.data.split(":")
    product_id = parts[2]
    quantity = int(parts[3]) if len(parts) > 3 else 1

    product = canboso.find_product(product_id)
    if not product:
        await query.edit_message_text(
            t("product_out_of_stock", lang),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    markup = await db.get_markup(product_id, config.default_markup_percent)
    sell_price = int(product.get("walletPricing", 0) * (1 + markup / 100))
    total = sell_price * quantity

    # Check balance
    current_balance = await db.get_balance(telegram_id)
    if current_balance < total:
        await query.edit_message_text(
            t("purchase_insufficient", lang,
                balance=format_vnd(current_balance),
                total=format_vnd(total),
            ),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    # Call Canboso API
    result = await canboso.purchase(
        product_id=product_id,
        quantity=quantity,
    )

    if not result.get("success"):
        error_msg = result.get("message", "Unknown error")
        await query.edit_message_text(
            t("purchase_error", lang, error=error_msg),
            reply_markup=back_to_menu_keyboard(lang),
            parse_mode="HTML",
        )
        return

    # Deduct balance
    new_balance = await db.update_balance(telegram_id, -total)

    # Get delivered accounts
    delivered = result.get("deliveredAccounts", [])

    # Save order
    user = await db.get_user(telegram_id)
    await db.create_order(
        user_id=user["id"],
        order_code=result.get("orderCode", ""),
        product_id=product_id,
        product_name=product.get("product_name", ""),
        quantity=quantity,
        original_price=product.get("walletPricing", 0),
        sell_price=sell_price,
        delivered_data=delivered,
    )

    # Log transaction
    await db.add_transaction(
        user_id=user["id"],
        tx_type="purchase",
        amount=-total,
        balance_after=new_balance,
        description=f"Mua {product.get('product_name', '')} x{quantity}",
    )

    # Format accounts
    from src.utils.formatters import format_account_list
    accounts_text = format_account_list(delivered, lang)

    text = t("purchase_success", lang,
        name=product.get("product_name", ""),
        quantity=quantity,
        total=format_vnd(total),
        balance=format_vnd(new_balance),
        accounts=accounts_text,
    )

    await query.edit_message_text(text, reply_markup=back_to_menu_keyboard(lang), parse_mode="HTML")

    # Refresh product cache
    await canboso.refresh_cache()
