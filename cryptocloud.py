"""Крипто-платежи через Trybit (бывший CryptoCloud) — https://trybit.com.

Ключи: кабинет → «Мои проекты» → настройки проекта → API KEY и SHOP ID.
Новые проекты стартуют в тест-режиме: счёт можно подтвердить из кабинета
кнопкой «Confirm invoice without payment» — удобно для проверки без денег.
"""
import aiohttp

from config import CRYPTOCLOUD_SHOP_ID, CRYPTOCLOUD_TOKEN

BASE = "https://api.trybit.com/v2"

# Монеты, которые показывать на странице оплаты (пустой список = все из проекта)
AVAILABLE_CURRENCIES = ["USDT_TRC20", "USDT_TON", "TON", "TRX", "BTC", "ETH"]


class CryptoError(RuntimeError):
    pass


def _headers() -> dict:
    return {
        "Authorization": f"Token {CRYPTOCLOUD_TOKEN}",
        "Content-Type": "application/json",
    }


async def create_invoice(user_id: int, amount_usd: float, minutes: int = 15) -> dict:
    """Создаёт счёт. Возвращает {'invoice_id': 'INV-...', 'pay_url': 'https://...'}."""
    if not CRYPTOCLOUD_TOKEN or not CRYPTOCLOUD_SHOP_ID:
        raise CryptoError(
            "не заполнены CRYPTOCLOUD_TOKEN / CRYPTOCLOUD_SHOP_ID в config.py"
        )
    payload = {
        "shop_id": CRYPTOCLOUD_SHOP_ID,
        "amount": amount_usd,
        "currency": "USD",
        "order_id": f"premium_{user_id}",  # привязка счёта к юзеру
        "add_fields": {
            "time_to_pay": {"hours": minutes // 60, "minutes": minutes % 60},
        },
    }
    if AVAILABLE_CURRENCIES:
        payload["add_fields"]["available_currencies"] = AVAILABLE_CURRENCIES

    async with aiohttp.ClientSession() as s:
        async with s.post(f"{BASE}/invoice/create", json=payload, headers=_headers()) as r:
            data = await r.json()
    if data.get("status") != "success":
        raise CryptoError(str(data.get("detail") or data)[:200])

    res = data["result"]
    link = res.get("link") or ""
    if link and not link.startswith("http"):
        link = "https://" + link
    return {"invoice_id": res["uuid"], "pay_url": link}


async def check_invoice(invoice_id: str, user_id: int) -> bool:
    """True, если счёт оплачен И принадлежит этому юзеру."""
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{BASE}/invoice/merchant/info",
            json={"uuids": [invoice_id]},
            headers=_headers(),
        ) as r:
            data = await r.json()
    if data.get("status") != "success" or not data.get("result"):
        return False
    inv = data["result"][0]
    return (
        inv.get("status") == "paid"
        and str(inv.get("order_id")) == f"premium_{user_id}"
    )
