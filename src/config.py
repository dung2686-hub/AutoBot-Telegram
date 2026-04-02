import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Telegram
    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    admin_chat_id: int = field(default_factory=lambda: int(os.getenv("ADMIN_CHAT_ID", "0")))

    # Canboso
    canboso_api_key: str = field(default_factory=lambda: os.getenv("CANBOSO_API_KEY", ""))
    canboso_api_url: str = field(default_factory=lambda: os.getenv("CANBOSO_API_URL", "https://canboso.com/api"))

    # SePay
    sepay_secret_key: str = field(default_factory=lambda: os.getenv("SEPAY_SECRET_KEY", ""))
    webhook_host: str = field(default_factory=lambda: os.getenv("WEBHOOK_HOST", "0.0.0.0"))
    webhook_port: int = field(default_factory=lambda: int(os.getenv("WEBHOOK_PORT", "8443")))

    # VietQR
    vietqr_client_id: str = field(default_factory=lambda: os.getenv("VIETQR_CLIENT_ID", ""))
    vietqr_api_key: str = field(default_factory=lambda: os.getenv("VIETQR_API_KEY", ""))

    # Bank
    bank_bin: str = field(default_factory=lambda: os.getenv("BANK_BIN", ""))
    bank_account: str = field(default_factory=lambda: os.getenv("BANK_ACCOUNT", ""))
    bank_account_name: str = field(default_factory=lambda: os.getenv("BANK_ACCOUNT_NAME", ""))

    # Bot
    default_markup_percent: int = field(default_factory=lambda: int(os.getenv("DEFAULT_MARKUP_PERCENT", "20")))
    deposit_expire_minutes: int = field(default_factory=lambda: int(os.getenv("DEPOSIT_EXPIRE_MINUTES", "30")))
    default_language: str = field(default_factory=lambda: os.getenv("DEFAULT_LANGUAGE", "vi"))


config = Config()
