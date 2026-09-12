"""Хранилище: лимиты, бонусы, рефералка, premium, статистика."""
import aiosqlite
from datetime import date, timedelta

from config import DB_PATH, FREE_DAILY_LIMIT

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS usage (
    user_id    INTEGER NOT NULL,
    day        TEXT    NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
CREATE TABLE IF NOT EXISTS premium (
    user_id    INTEGER PRIMARY KEY,
    until      TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_seen  TEXT    NOT NULL,
    referred_by INTEGER,
    bonus       INTEGER NOT NULL DEFAULT 0,
    total_ops   INTEGER NOT NULL DEFAULT 0,
    source      TEXT
);
CREATE TABLE IF NOT EXISTS payments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    amount     INTEGER NOT NULL,
    paid_at    TEXT    NOT NULL
);
"""

REF_BONUS = 3  # бонусных операций за приглашённого


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_SQL)
        # миграция старых баз: колонка source появилась позже
        try:
            await db.execute("ALTER TABLE users ADD COLUMN source TEXT")
        except aiosqlite.OperationalError:
            pass  # колонка уже есть
        await db.commit()


# ---------- Пользователи и рефералка ----------

async def register_user(user_id: int, username: str | None,
                        referrer_id: int | None = None,
                        source: str | None = None) -> bool:
    """Регистрирует юзера. Возвращает True, если юзер новый."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        is_new = await cur.fetchone() is None
        if is_new:
            # сам себе реферером быть не может
            ref = referrer_id if referrer_id and referrer_id != user_id else None
            await db.execute(
                "INSERT INTO users (user_id, username, first_seen, referred_by, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, username, date.today().isoformat(), ref, source),
            )
            if ref:
                # начисляем бонус, только если пригласивший существует
                cur = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (ref,))
                if await cur.fetchone():
                    await db.execute(
                        "UPDATE users SET bonus = bonus + ? WHERE user_id = ?",
                        (REF_BONUS, ref),
                    )
        else:
            await db.execute(
                "UPDATE users SET username = ? WHERE user_id = ?", (username, user_id)
            )
        await db.commit()
    return is_new


async def get_ref_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)
        )
        return (await cur.fetchone())[0]


async def get_bonus(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT bonus FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0


# ---------- Лимиты ----------

async def get_used_today(user_id: int) -> int:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT used FROM usage WHERE user_id = ? AND day = ?", (user_id, today)
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def consume_quota(user_id: int) -> bool:
    """Списывает операцию: дневной лимит → бонусы. True, если квота есть."""
    if await is_premium(user_id):
        await _count_op(user_id)
        return True

    today = date.today().isoformat()
    used = await get_used_today(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        if used < FREE_DAILY_LIMIT:
            await db.execute(
                """INSERT INTO usage (user_id, day, used) VALUES (?, ?, 1)
                   ON CONFLICT(user_id, day) DO UPDATE SET used = used + 1""",
                (user_id, today),
            )
        else:
            # дневной лимит исчерпан — пробуем бонус
            cur = await db.execute(
                "UPDATE users SET bonus = bonus - 1 WHERE user_id = ? AND bonus > 0",
                (user_id,),
            )
            if cur.rowcount == 0:
                return False
        await db.commit()
    await _count_op(user_id)
    return True


async def _count_op(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET total_ops = total_ops + 1 WHERE user_id = ?", (user_id,)
        )
        await db.commit()


# ---------- Premium и платежи ----------

async def is_premium(user_id: int) -> bool:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT until FROM premium WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return bool(row and row[0] >= today)


async def grant_premium(user_id: int, days: int = 30):
    until = (date.today() + timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO premium (user_id, until) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET until = excluded.until",
            (user_id, until),
        )
        await db.commit()


async def log_payment(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO payments (user_id, amount, paid_at) VALUES (?, ?, ?)",
            (user_id, amount, date.today().isoformat()),
        )
        await db.commit()


async def get_inactive_new_users() -> list[int]:
    """Юзеры, зарегистрированные вчера и не сделавшие ни одной операции."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id FROM users WHERE first_seen = ? AND total_ops = 0",
            (yesterday,),
        )
        return [r[0] for r in await cur.fetchall()]


async def get_source_stats(limit: int = 10) -> list[tuple[str, int]]:
    """Разбивка пользователей по источникам (метки src_...)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COALESCE(source, 'прямой заход / прочее'), COUNT(*) AS c "
            "FROM users GROUP BY source ORDER BY c DESC LIMIT ?",
            (limit,),
        )
        return await cur.fetchall()


# ---------- Статистика (для админа) ----------

async def get_stats() -> dict:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async def one(sql, params=()):
            cur = await db.execute(sql, params)
            return (await cur.fetchone())[0]

        return {
            "users_total": await one("SELECT COUNT(*) FROM users"),
            "users_today": await one(
                "SELECT COUNT(*) FROM users WHERE first_seen = ?", (today,)),
            "ops_total": await one("SELECT COALESCE(SUM(total_ops),0) FROM users"),
            "ops_today": await one(
                "SELECT COALESCE(SUM(used),0) FROM usage WHERE day = ?", (today,)),
            "premium_active": await one(
                "SELECT COUNT(*) FROM premium WHERE until >= ?", (today,)),
            "payments_total": await one("SELECT COUNT(*) FROM payments"),
            "payments_sum": await one("SELECT COALESCE(SUM(amount),0) FROM payments"),
            "refs_total": await one(
                "SELECT COUNT(*) FROM users WHERE referred_by IS NOT NULL"),
        }
