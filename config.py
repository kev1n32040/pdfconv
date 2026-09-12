import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_СЮДА")

# Лимиты
FREE_DAILY_LIMIT = 3          # бесплатных операций в день
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ — лимит скачивания Bot API

# Пути
DOWNLOAD_DIR = "downloads"
DB_PATH = "bot.db"
