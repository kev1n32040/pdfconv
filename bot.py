"""Файл-обработчик: MVP телеграм-бота (сжатие/склейка PDF, лимиты, оплата Stars)."""
import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

import db
from config import (
    BOT_TOKEN,
    CRYPTOCLOUD_SHOP_ID,
    CRYPTOCLOUD_TOKEN,
    DOWNLOAD_DIR,
    FREE_DAILY_LIMIT,
    MAX_FILE_SIZE,
)
from pdf_tools import compress_pdf, human_size, merge_pdfs
from video_tools import video_to_note

logging.basicConfig(level=logging.INFO)
router = Router()

ADMIN_IDS: set[int] = {8593355445}
PREMIUM_PRICE_STARS = 100   # цена подписки на 30 дней в Telegram Stars
PREMIUM_PRICE_USDT = 2      # ориентировочная цена в USDT для крипто-оплаты



class MergeState(StatesGroup):
    collecting = State()


class CompressState(StatesGroup):
    waiting_quality = State()


def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗜 Сжать PDF", callback_data="mode_compress")],
        [InlineKeyboardButton(text="📎 Склеить PDF", callback_data="mode_merge")],
        [InlineKeyboardButton(text="⭕️ Видео в кружочек", callback_data="mode_note")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="buy_premium")],
        [InlineKeyboardButton(text="🔗 Пригласить друга (+бонусы)", callback_data="show_ref")],
    ])


@router.message(CommandStart())
async def cmd_start(m: Message, command: CommandObject, bot: Bot):
    # реферальный payload: /start ref123
    referrer = None
    if command.args and command.args.startswith("ref"):
        try:
            referrer = int(command.args[3:])
        except ValueError:
            pass

    is_new = await db.register_user(m.from_user.id, m.from_user.username, referrer)

    if is_new and referrer:
        # сообщаем пригласившему о бонусе
        try:
            await bot.send_message(
                referrer,
                f"🎉 По твоей ссылке пришёл новый пользователь! "
                f"+{db.REF_BONUS} бонусные операции на твой счёт.",
            )
        except Exception:
            pass  # юзер мог заблокировать бота

    bonus = await db.get_bonus(m.from_user.id)
    bonus_line = f"\n🎁 Бонусных операций: {bonus}" if bonus else ""

    await m.answer(
        "Привет! Я обрабатываю файлы прямо в Telegram.\n\n"
        "Что умею:\n"
        "• 🗜 Сжимать PDF\n"
        "• 📎 Склеивать несколько PDF в один\n"
        "• ⭕️ Превращать видео в кружочки\n\n"
        f"Бесплатно — {FREE_DAILY_LIMIT} операции в день. "
        f"Premium — без лимитов.{bonus_line}\n\nВыбери действие 👇",
        reply_markup=main_kb(),
    )


@router.message(Command("ref"))
async def cmd_ref(m: Message, bot: Bot):
    """Личная реферальная ссылка и счётчик приглашённых."""
    me = await bot.me()
    count = await db.get_ref_count(m.from_user.id)
    bonus = await db.get_bonus(m.from_user.id)
    link = f"https://t.me/{me.username}?start=ref{m.from_user.id}"
    await m.answer(
        "🔗 Твоя реферальная ссылка:\n"
        f"{link}\n\n"
        f"За каждого нового пользователя — +{db.REF_BONUS} бонусные операции "
        "(тратятся, когда дневной лимит кончился, и не сгорают).\n\n"
        f"👥 Приглашено: {count}\n"
        f"🎁 Бонусов на счету: {bonus}"
    )


@router.message(Command("stats"))
async def cmd_stats(m: Message):
    """Статистика бота — только для админа."""
    if m.from_user.id not in ADMIN_IDS:
        return
    s = await db.get_stats()
    await m.answer(
        "📊 Статистика:\n\n"
        f"👥 Пользователей всего: {s['users_total']} (+{s['users_today']} сегодня)\n"
        f"🔗 Из них по рефералкам: {s['refs_total']}\n"
        f"⚙️ Операций всего: {s['ops_total']} (сегодня: {s['ops_today']})\n"
        f"⭐ Активных premium: {s['premium_active']}\n"
        f"💰 Платежей: {s['payments_total']} на {s['payments_sum']} Stars"
    )


@router.message(Command("grant"))
async def cmd_grant(m: Message):
    """/grant <user_id> — выдать premium вручную (для админа/тестов)."""
    if m.from_user.id not in ADMIN_IDS:
        return
    try:
        uid = int(m.text.split()[1])
    except (IndexError, ValueError):
        await m.answer("Формат: /grant <user_id>")
        return
    await db.grant_premium(uid)
    await m.answer(f"Premium выдан пользователю {uid} на 30 дней.")


# ---------- Оплата через Telegram Stars ----------

@router.callback_query(F.data == "buy_premium")
async def cb_buy(cb):
    await cb.message.answer(
        "Выбери способ оплаты Premium (30 дней безлимита):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Telegram Stars ({PREMIUM_PRICE_STARS}⭐)", callback_data="pay_stars")],
            [InlineKeyboardButton(text=f"💎 Крипта (~{PREMIUM_PRICE_USDT} USDT / TON / BTC)", callback_data="pay_crypto")],
        ]),
    )
    await cb.answer()


@router.callback_query(F.data == "pay_stars")
async def cb_pay_stars(cb):
    prices = [LabeledPrice(label="Premium на 30 дней", amount=PREMIUM_PRICE_STARS)]
    await cb.message.answer_invoice(
        title="Premium-подписка",
        description="Безлимитные операции на 30 дней.",
        payload="premium_30d",
        currency="XTR",
        prices=prices,
    )
    await cb.answer()


@router.callback_query(F.data == "pay_crypto")
async def cb_pay_crypto(cb):
    from cryptocloud import CryptoError, create_invoice
    if not CRYPTOCLOUD_TOKEN or not CRYPTOCLOUD_SHOP_ID:
        await cb.message.answer("Крипто-оплата временно недоступна. Попробуй Stars ⭐")
        await cb.answer()
        return
    try:
        inv = await create_invoice(cb.from_user.id, PREMIUM_PRICE_USDT)
    except CryptoError as e:
        logging.error("crypto invoice failed: %s", e)
        await cb.message.answer(f"Не удалось создать счёт: {e}")
        await cb.answer()
        return
    except Exception as e:
        logging.exception("crypto invoice failed")
        await cb.message.answer("Платёжный сервис не отвечает. Попробуй позже или Stars ⭐")
        await cb.answer()
        return
    await cb.message.answer(
        f"💎 Счёт на {PREMIUM_PRICE_USDT} USDT (можно платить USDT, TON, BTC и др.):\n\n"
        "1. Оплати по кнопке ниже\n"
        "2. Вернись сюда и нажми «Проверить оплату»",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=inv["pay_url"])],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_crypto:{inv['invoice_id']}")],
        ]),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("check_crypto:"))
async def cb_check_crypto(cb):
    invoice_id = cb.data.split(":", 1)[1]
    from cryptocloud import check_invoice
    try:
        paid = await check_invoice(invoice_id, cb.from_user.id)
    except Exception as e:
        logging.exception("crypto check failed")
        await cb.message.answer("Платёжный сервис не отвечает. Нажми ещё раз через минуту.")
        await cb.answer()
        return
    if paid:
        await db.grant_premium(cb.from_user.id, days=30)
        await db.log_payment(cb.from_user.id, 0)  # крипта, сумма в Stars = 0
        await cb.message.answer("✅ Оплата получена! Premium активен на 30 дней. Спасибо!")
    else:
        await cb.answer(
            "Оплата пока не найдена. Если только что платил — подожди минуту и проверь снова.",
            show_alert=True,
        )
        return
    await cb.answer()


@router.message(F.successful_payment)
async def payment_ok(m: Message):
    await db.grant_premium(m.from_user.id, days=30)
    await db.log_payment(m.from_user.id, m.successful_payment.total_amount)
    await m.answer("✅ Оплата прошла! Premium активен 30 дней. Спасибо!")


# ---------- Сжатие PDF ----------

@router.callback_query(F.data == "mode_compress")
async def cb_compress(cb):
    await cb.message.answer("Пришли PDF-файл — сожму его (одним сообщением, как документ).")
    await cb.answer()


@router.callback_query(F.data == "mode_merge")
async def cb_merge(cb, state: FSMContext):
    await state.set_state(MergeState.collecting)
    await state.update_data(files=[])
    await cb.message.answer(
        "Режим склейки. Присылай PDF-файлы по одному. "
        "Когда закончишь — отправь /done. Отмена — /cancel."
    )
    await cb.answer()


async def download_doc(bot: Bot, m: Message) -> Path | None:
    doc = m.document
    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await m.answer("Файл больше 20 МБ — такие Bot API скачать не даёт 😔")
        return None
    if not (doc.file_name or "").lower().endswith(".pdf"):
        await m.answer("Пока умею только PDF. Пришли файл с расширением .pdf")
        return None
    Path(DOWNLOAD_DIR).mkdir(exist_ok=True)
    dest = Path(DOWNLOAD_DIR) / f"{m.from_user.id}_{doc.file_unique_id}.pdf"
    await bot.download(doc, destination=dest)
    return dest


@router.message(F.document, MergeState.collecting)
async def collect_for_merge(m: Message, state: FSMContext, bot: Bot):
    dest = await download_doc(bot, m)
    if not dest:
        return
    data = await state.get_data()
    data["files"].append(str(dest))
    await state.update_data(files=data["files"])
    await m.answer(f"Принял! Всего файлов: {len(data['files'])}. Ещё или /done")


@router.message(Command("done"), MergeState.collecting)
async def do_merge(m: Message, state: FSMContext):
    data = await state.get_data()
    files = [Path(p) for p in data.get("files", [])]
    await state.clear()
    if len(files) < 2:
        await m.answer("Нужно минимум 2 файла для склейки.")
        return
    if not await db.consume_quota(m.from_user.id):
        await m.answer(limit_text(), reply_markup=main_kb())
        return
    out = Path(DOWNLOAD_DIR) / f"{m.from_user.id}_merged.pdf"
    try:
        pages = await asyncio.to_thread(merge_pdfs, files, out)
        await m.answer_document(
            BufferedInputFile(out.read_bytes(), filename="merged.pdf"),
            caption=f"Готово! Склеено {len(files)} файлов, {pages} стр.",
        )
    finally:
        for f in files + [out]:
            f.unlink(missing_ok=True)


@router.message(Command("cancel"), MergeState.collecting)
async def cancel_merge(m: Message, state: FSMContext):
    data = await state.get_data()
    for p in data.get("files", []):
        Path(p).unlink(missing_ok=True)
    await state.clear()
    await m.answer("Отменил. Выбери действие 👇", reply_markup=main_kb())


@router.callback_query(F.data == "mode_note")
async def cb_note(cb):
    await cb.message.answer(
        "Пришли видео (как файл или обычным видео) — верну кружочком. "
        "Обрежу до 60 секунд, если длиннее."
    )
    await cb.answer()


@router.message(F.video | (F.document & F.document.mime_type.startswith("video/")))
async def do_video_note(m: Message, bot: Bot):
    """Видео → кружочек."""
    media = m.video or m.document
    if media.file_size and media.file_size > MAX_FILE_SIZE:
        await m.answer("Файл больше 20 МБ — такие Bot API скачать не даёт 😔")
        return
    if not await db.consume_quota(m.from_user.id):
        await m.answer(limit_text(), reply_markup=main_kb())
        return

    Path(DOWNLOAD_DIR).mkdir(exist_ok=True)
    src_path = Path(DOWNLOAD_DIR) / f"{m.from_user.id}_{media.file_unique_id}.mp4"
    dst = src_path.with_name(src_path.stem + "_note.mp4")
    wait = await m.answer("Конвертирую в кружочек… ⏳")
    try:
        await bot.download(media, destination=src_path)
        await video_to_note(src_path, dst)
        await m.answer_video_note(
            BufferedInputFile(dst.read_bytes(), filename="note.mp4")
        )
    except RuntimeError as e:
        await m.answer(f"Не получилось обработать видео: {e}")
    finally:
        await wait.delete()
        src_path.unlink(missing_ok=True)
        dst.unlink(missing_ok=True)


@router.message(F.document)
async def do_compress(m: Message, bot: Bot, state: FSMContext):
    """Любой документ вне режима склейки — сжимаем (с выбором качества)."""
    src_path = await download_doc(bot, m)
    if not src_path:
        return
    # сохраняем путь и оригинальное имя — file_unique_id может содержать "_"
    await state.set_state(CompressState.waiting_quality)
    await state.update_data(pdf_path=str(src_path), orig_name=m.document.file_name or "file.pdf")
    await m.answer(
        "Выбери качество сжатия:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Сильное (для экрана)", callback_data="q_low")],
            [InlineKeyboardButton(text="⚖️ Среднее", callback_data="q_medium")],
            [InlineKeyboardButton(text="🖨 Высокое (печать)", callback_data="q_high")],
        ]),
    )


@router.callback_query(F.data.startswith("q_"), CompressState.waiting_quality)
async def cb_compress_quality(cb, bot: Bot, state: FSMContext):
    preset = cb.data[2:]
    data = await state.get_data()
    await state.clear()
    src = Path(data["pdf_path"])
    orig_name = data.get("orig_name") or "file.pdf"

    if not await db.consume_quota(cb.from_user.id):
        src.unlink(missing_ok=True)
        await cb.message.answer(limit_text(), reply_markup=main_kb())
        await cb.answer()
        return

    wait = await cb.message.answer("Сжимаю… ⏳")
    dst = src.with_name(src.stem + "_min.pdf")
    try:
        before, after = await compress_pdf(src, dst, preset)
        if after < before:
            saved = 100 - round(after / before * 100)
            caption = f"Готово! {human_size(before)} → {human_size(after)} (−{saved}%)"
        else:
            caption = (
                "Сжать сильнее не получилось — файл уже оптимизирован "
                f"({human_size(before)})."
            )
        await cb.message.answer_document(
            BufferedInputFile(dst.read_bytes(), filename=f"compressed_{orig_name}"),
            caption=caption,
        )
    except RuntimeError as e:
        await cb.message.answer(f"Не получилось сжать файл: {e}")
    finally:
        await wait.delete()
        src.unlink(missing_ok=True)
        dst.unlink(missing_ok=True)
    await cb.answer()

def limit_text() -> str:
    return (
        f"Бесплатный лимит ({FREE_DAILY_LIMIT} операции в день) исчерпан.\n"
        "Оформи Premium — без ограничений 👇"
    )


async def main():
    await db.init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
