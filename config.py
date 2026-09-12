import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_СЮДА")

# --- Крипто-оплата (Trybit / бывший CryptoCloud) ---
# Кабинет: «Мои проекты» → настройки проекта → API KEY и SHOP ID.
# Можно задать и через переменные окружения CRYPTOCLOUD_TOKEN / CRYPTOCLOUD_SHOP_ID.
CRYPTOCLOUD_TOKEN = os.getenv("CRYPTOCLOUD_TOKEN", "")
CRYPTOCLOUD_SHOP_ID = os.getenv("CRYPTOCLOUD_SHOP_ID", "")

# Лимиты
FREE_DAILY_LIMIT = 3          # бесплатных операций в день
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ — лимит скачивания Bot API

# Пути
DOWNLOAD_DIR = "downloads"
DB_PATH = "bot.db"
