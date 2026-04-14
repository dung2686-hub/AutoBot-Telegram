import sys
import io

sys.path.insert(0, ".")
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.config import config
from src.database.db import Database
from src.services.canboso import CanbosoClient
from src.services.vietqr import generate_qr_image
from src.i18n import t
from src.utils.keyboards import main_menu_keyboard
from src.utils.formatters import format_vnd
from src.utils.decorators import ensure_user

print("All imports OK")
print(f"Default lang: {config.default_language}")
print(f"Markup: {config.default_markup_percent}%")
print(f"i18n vi: {t('btn_shop', 'vi')}")
print(f"i18n en: {t('btn_shop', 'en')}")
print(f"Format VND: {format_vnd(100000)}")
print(f"Format VND: {format_vnd(1500000)}")

# Test handlers import
from src.handlers.start import start_command
from src.handlers.shop import shop_menu, execute_purchase
from src.handlers.wallet import wallet_menu, get_deposit_conversation
from src.handlers.profile import profile_menu
from src.handlers.history import history_menu
from src.handlers.support import get_support_conversation
from src.handlers.language import language_menu
from src.handlers.admin import admin_command, get_admin_conversation

print("All handlers imported OK")

# Test main build
from src.main import build_application
print("Application builder OK")

print("\n=== ALL TESTS PASSED ===")
