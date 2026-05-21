"""Persistence layer — SQLite via aiosqlite.

DB_PATH : /data/trades.db sur Railway Volume, sinon ./telegram/trades.db en local.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

DB_PATH = (
    "/data/trades.db"
    if os.path.isdir("/data")
    else os.path.join(os.path.dirname(__file__), "trades.db")
)


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id   INTEGER,
                text_hash    TEXT NOT NULL,
                processed_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (message_id, text_hash)
            );

            CREATE TABLE IF NOT EXISTS trades (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                source_message_id INTEGER,
                asset             TEXT NOT NULL,
                symbol            TEXT NOT NULL,
                direction         TEXT NOT NULL,
                entry1            REAL NOT NULL,
                entry2            REAL,
                targets           TEXT NOT NULL,
                stop_loss         REAL NOT NULL,
                status            TEXT DEFAULT 'waiting',
                entry_price       REAL,
                hit_entry1        INTEGER DEFAULT 0,
                hit_entry2        INTEGER DEFAULT 0,
                highest_tp_index  INTEGER DEFAULT 0,
                sl_level          REAL,
                close_reason      TEXT,
                pnl_pct           REAL,
                created_at        TEXT DEFAULT (datetime('now')),
                closed_at         TEXT,
                expires_at        TEXT,
                last_checked_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS tp_hits (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id   INTEGER NOT NULL,
                tp_index   INTEGER NOT NULL,
                tp_price   REAL NOT NULL,
                hit_at     TEXT DEFAULT (datetime('now')),
                UNIQUE (trade_id, tp_index),
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            );

            CREATE TABLE IF NOT EXISTS app_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        await conn.commit()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


async def is_processed(message_id: int, text: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT 1 FROM processed_messages WHERE message_id = ? OR text_hash = ?",
            (message_id, _hash(text)),
        ) as cur:
            return await cur.fetchone() is not None


async def mark_processed(message_id: int, text: str) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id, text_hash) VALUES (?, ?)",
            (message_id, _hash(text)),
        )
        await conn.commit()


async def add_trade(
    source_message_id: int,
    asset: str,
    symbol: str,
    direction: str,
    entry1: float,
    entry2: Optional[float],
    targets: list[float],
    stop_loss: float,
) -> int:
    expires_at = (datetime.utcnow() + timedelta(days=60)).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO trades
               (source_message_id, asset, symbol, direction, entry1, entry2,
                targets, stop_loss, sl_level, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_message_id, asset, symbol, direction,
                entry1, entry2, json.dumps(targets), stop_loss, stop_loss, expires_at,
            ),
        )
        await conn.commit()
        return cur.lastrowid


async def get_active_trades() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM trades WHERE status IN ('waiting', 'active')"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def update_trade(trade_id: int, **fields) -> None:
    if not fields:
        return
    clause = ", ".join(f"{k} = ?" for k in fields)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE trades SET {clause} WHERE id = ?",
            [*fields.values(), trade_id],
        )
        await conn.commit()


async def add_tp_hit(trade_id: int, tp_index: int, tp_price: float) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO tp_hits (trade_id, tp_index, tp_price) VALUES (?, ?, ?)",
            (trade_id, tp_index, tp_price),
        )
        await conn.commit()


async def get_closed_trades_since(since: datetime) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM trades WHERE status = 'closed' AND closed_at >= ?",
            (since.isoformat(),),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_open_trades() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM trades WHERE status IN ('waiting', 'active')"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_app_state(key: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute(
            "SELECT value FROM app_state WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def set_app_state(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)", (key, value)
        )
        await conn.commit()
