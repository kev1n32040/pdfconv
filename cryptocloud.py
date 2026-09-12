"""Приём крипто-платежей через CryptoCloud (https://cryptocloud.plus).

Работает с юзерами из любых регионов, поддержка USDT/TON/BTC и др.
Регистрация: сайт → создать проект → получить API key (SHOP ID + token).
"""
import os

import aiohttp

BASE = "https://api.cryptocloud.plus/v2"


def _token() -> str:
    return os.getenv("CRYPTOCLOUD_TOKEN", "")


async def create_invoice(user_id: int, amount_usd: float) -> dict:
    """Создаёт счёт. Возвращает {'invoice_id': str, 'pay_url': str}."""
    headers = {"Authorization": f"Token {_token()}"}
    payload = {
        "amount": amount_usd,
        "currency": "USD",
        "order_id": f"premium_{user_id}",   # защита: связываем счёт с юзером
        "lifetime": 900,                     # счёт живёт 15 минут
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{BASE}/invoice/create", json=payload, headers=headers) as r:
            data = await r.json()
    if data.get("status") != "success":
        raise RuntimeError(str(data)[:200])
    res = data["result"]
    return {"invoice_id": res["uuid"], "pay_url": res["link"]}


async def check_invoice(invoice_id: str, user_id: int) -> bool:
    """True, если счёт оплачен И принадлежит этому юзеру."""
    headers = {"Authorization": f"Token {_token()}"}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{BASE}/invoice/merchant/info",
                          json={"uuids": [invoice_id]}, headers=headers) as r:
            data = await r.json()
    if data.get("status") != "success" or not data["result"]:
        return False
    inv = data["result"][0]
    return (
        inv.get("status") == "paid"
        and inv.get("order_id") == f"premium_{user_id}"
    )
