# PDF & Video Tools Bot

Телеграм-бот для обработки файлов: сжатие и склейка PDF, конвертация видео в кружочки.
Встроены: дневные лимиты, реферальная система с бонусами, premium-подписка через Telegram Stars.

## Возможности

- 🗜 Сжатие PDF (пережатие изображений)
- 📎 Склейка нескольких PDF в один
- ⭕️ Конвертация видео в кружочек (нужен ffmpeg на сервере)
- 🎁 Реферальная программа: +3 бонусные операции за каждого приглашённого
- ⭐ Premium-подписка через Telegram Stars (безлимит на 30 дней)
- 📊 Админская статистика: `/stats`

## Запуск

```bash
pip install -r requirements.txt
apt install ffmpeg  # нужен для видео-функций
export BOT_TOKEN="токен_от_BotFather"
python bot.py
```

## Настройка

В `config.py`:
- `BOT_TOKEN` — токен бота (или env-переменная `BOT_TOKEN`)
- `FREE_DAILY_LIMIT` — бесплатных операций в день (по умолчанию 3)

В `bot.py`:
- `ADMIN_IDS` — user_id админов (команды `/stats`, `/grant <user_id>`)
- `PREMIUM_PRICE_STARS` — цена подписки в Telegram Stars

## Команды

- `/start` — главное меню
- `/ref` — реферальная ссылка и бонусы
- `/done`, `/cancel` — управление склейкой PDF
- `/stats` — статистика (админ)
- `/grant <user_id>` — выдать premium вручную (админ)
