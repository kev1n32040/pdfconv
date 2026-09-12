"""Крипто-платежи через Trybit (бывший CryptoCloud) — https://trybit.com.

Ключи: кабинет → «Мои проекты» → настройки проекта → API KEY и SHOP ID.
Ключи ищутся в config.py (CRYPTOCLOUD_TOKEN / CRYPTOCLOUD_SHOP_ID),
а если их там нет — в переменных окружения. Код не падает,
если config.py старой версии.
"""
import os

import aiohttp

BASE = "https://api.trybit.com/v2"

# Монеты, которые показывать на странице оплаты (пустой список = все из проекта)
AVAILABLE_CURRENCIES = ["USDT_TRC20", "USDT_TON", "TON", "TRX", "BTC", "ETH"]


class CryptoError(RuntimeError):
    pass


def creds() -> tuple[str, str]:
    """(token, shop_id) из config.py или env. Пустые строки, если не заданы."""
    try:
        import config
    except Exception:
        config = None
    token = (getattr(config, "CRYPTOCLOUD_TOKEN", "") if config else "") \
        or os.getenv("CRYPTOCLOUD_TOKEN", "")
    shop = (getattr(config, "CRYPTOCLOUD_SHOP_ID", "") if config else "") \
        or os.getenv("CRYPTOCLOUD_SHOP_ID", "")
    return token.strip(), shop.strip()


def missing_creds() -> list[str]:
    token, shop = creds()
    miss = []
    if not token:
        miss.append("CRYPTOCLOUD_TOKEN")
    if not shop:
        miss.append("CRYPTOCLOUD_SHOP_ID")
    return miss


def _headers() -> dict:
    token, _ = creds()
    return {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }


async def create_invoice(user_id: int, amount_usd: float, minutes: int = 15) -> dict:
    """Создаёт счёт. Возвращает {'invoice_id': 'INV-...', 'pay_url': 'https://...'}."""
    token, shop = creds()
    if not token or not shop:
        raise CryptoError("не заданы ключи: " + ", ".join(missing_creds()))
    payload = {
        "shop_id": shop,
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
