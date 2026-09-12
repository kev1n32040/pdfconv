"""Приём крипто-платежей через Crypto Bot API (@CryptoBot).

Регистрация: @CryptoBot → Crypto Pay → Create App → получить токен.
Для тестов без реальных денег: @CryptoTestnetBot (тестовая сеть).
"""
import aiohttp

MAINNET = "https://pay.crypt.bot/api"
TESTNET = "https://testnet-pay.crypt.bot/api"


def _base(token: str) -> str:
    # тестнет-токены отличаются — их выдаёт @CryptoTestnetBot; определяем по префиксу не надёжно,
    # поэтому просто: тестнет включается отдельным env (см. create_invoice вызовы).
    import os
    return TESTNET if os.getenv("CRYPTOBOT_TESTNET") == "1" else MAINNET


async def create_invoice(token: str, user_id: int, amount_usd: float) -> dict:
    """Создаёт счёт. Возвращает {'invoice_id': int, 'pay_url': str}."""
    headers = {"Crypto-Pay-API-Token": token}
    payload = {
        "currency_type": "fiat",
        "fiat": "USD",
        "amount": str(amount_usd),
        "accepted_assets": "USDT,TON,BTC,ETH,LTC,BNB,TRX,USDC",
        "payload": str(user_id),  # вернётся при проверке — защита от чужой оплаты
        "description": "Premium-подписка на 30 дней",
        "expires_in": 900,  # счёт живёт 15 минут
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{_base(token)}/createInvoice", json=payload, headers=headers) as r:
            data = await r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error", {}).get("name", "unknown crypto api error"))
    inv = data["result"]
    return {"invoice_id": inv["invoice_id"], "pay_url": inv["bot_invoice_url"]}


async def check_invoice(token: str, invoice_id: int, user_id: int) -> bool:
    """True, если счёт оплачен И принадлежит этому юзеру."""
    headers = {"Crypto-Pay-API-Token": token}
    params = {"invoice_ids": str(invoice_id), "status": "paid"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{_base(token)}/getInvoices", params=params, headers=headers) as r:
            data = await r.json()
    if not data.get("ok"):
        return False
    items = data["result"].get("items", [])
    if not items:
        return False
    inv = items[0]
    # сверяем payload с user_id — чтобы нельзя было проверить чужой счёт
    return inv.get("payload") == str(user_id)
