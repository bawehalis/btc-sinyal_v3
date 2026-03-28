# ============================================================
#  db/database.py
#  Async SQLite veritabani — aiosqlite
# ============================================================

import aiosqlite
import json
import logging
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger(__name__)


# ── TABLO OLUSTURMA ──────────────────────────────────────

CREATE_TABLES = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS prices (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT    NOT NULL,
    timeframe TEXT    NOT NULL,
    ts        INTEGER NOT NULL,
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL,
    volume    REAL,
    UNIQUE(symbol, timeframe, ts)
);

CREATE TABLE IF NOT EXISTS signals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   INTEGER NOT NULL,
    timeframe    TEXT    NOT NULL,
    score        REAL    NOT NULL,
    raw_score    REAL,
    label        TEXT    NOT NULL,
    confidence   REAL    NOT NULL,
    regime       TEXT,
    judge_verdict TEXT,
    price        REAL,
    detail       TEXT,
    sent         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS indicator_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    updated_at  INTEGER NOT NULL,
    name        TEXT    NOT NULL UNIQUE,
    value       TEXT    NOT NULL,
    source      TEXT,
    is_error    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS accuracy (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER NOT NULL,
    timeframe   TEXT    NOT NULL,
    signal_ts   INTEGER NOT NULL,
    score       REAL    NOT NULL,
    label       TEXT    NOT NULL,
    price_at_signal REAL,
    price_after     REAL,
    horizon_h   INTEGER,
    correct     INTEGER,
    pct_change  REAL,
    evaluated_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_prices_symbol_tf ON prices(symbol, timeframe, ts);
CREATE INDEX IF NOT EXISTS idx_signals_tf ON signals(timeframe, created_at);
CREATE INDEX IF NOT EXISTS idx_accuracy_tf ON accuracy(timeframe, signal_ts);
"""


async def init_db():
    """Veritabanini olustur ve tablolari hazirla."""
    import os
    os.makedirs("db", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        await db.commit()
    logger.info(f"Veritabani hazir: {DB_PATH}")


# ── FIYAT ISLEMLERI ──────────────────────────────────────

async def save_prices(candles: list, symbol: str, timeframe: str):
    if not candles:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """INSERT OR REPLACE INTO prices
               (symbol, timeframe, ts, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(symbol, timeframe,
              c["ts"], c["open"], c["high"], c["low"], c["close"], c["volume"])
             for c in candles]
        )
        await db.commit()


async def get_prices(symbol: str, timeframe: str, limit: int = 500) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT ts, open, high, low, close, volume
               FROM prices
               WHERE symbol = ? AND timeframe = ?
               ORDER BY ts DESC LIMIT ?""",
            (symbol, timeframe, limit)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in reversed(rows)]


# ── SINYAL ISLEMLERI ─────────────────────────────────────

async def save_signal(result: dict, price: float) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO signals
               (created_at, timeframe, score, raw_score, label,
                confidence, regime, judge_verdict, price, detail, sent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                result["ts"],
                result["timeframe"],
                result["score"],
                result.get("raw_score", 0),
                result["label"],
                result["confidence"],
                result.get("regime", ""),
                result.get("judge_verdict", ""),
                price,
                json.dumps(result.get("detail", {})),
            )
        )
        await db.commit()
        return cur.lastrowid


async def mark_signal_sent(signal_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE signals SET sent = 1 WHERE id = ?", (signal_id,)
        )
        await db.commit()


async def get_recent_signals(hours: int = 720, timeframe: str = "4h") -> list:
    since = int(datetime.now().timestamp() * 1000) - hours * 3600 * 1000
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM signals
               WHERE timeframe = ? AND created_at > ?
               ORDER BY created_at DESC""",
            (timeframe, since)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── INDIKTOR SNAPSHOT (DataBus kaliciligi) ───────────────

async def save_indicator_snapshot(name: str, value: dict,
                                   source: str = "", is_error: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO indicator_snapshots
               (updated_at, name, value, source, is_error)
               VALUES (?, ?, ?, ?, ?)""",
            (int(datetime.now().timestamp()),
             name, json.dumps(value), source, int(is_error))
        )
        await db.commit()


async def load_indicator_snapshots() -> dict:
    """Bot baslangicinda son gecerli indiktr degerlerini yukle."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT name, value, updated_at, is_error FROM indicator_snapshots"
        ) as cur:
            rows = await cur.fetchall()
    result = {}
    for r in rows:
        if not r["is_error"]:
            try:
                result[r["name"]] = {
                    "data":       json.loads(r["value"]),
                    "updated_at": r["updated_at"],
                }
            except Exception:
                pass
    return result


# ── BASARI TAKIBI ────────────────────────────────────────

async def save_accuracy_record(record: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO accuracy
               (signal_id, timeframe, signal_ts, score, label,
                price_at_signal, price_after, horizon_h,
                correct, pct_change, evaluated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["signal_id"], record["timeframe"],
                record["signal_ts"], record["score"], record["label"],
                record["price_at_signal"], record["price_after"],
                record["horizon_h"], record["correct"],
                record["pct_change"],
                int(datetime.now().timestamp()),
            )
        )
        await db.commit()


async def get_accuracy_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT timeframe,
                      COUNT(*) as total,
                      SUM(correct) as correct_count,
                      AVG(pct_change) as avg_pct
               FROM accuracy
               WHERE correct IS NOT NULL
               GROUP BY timeframe"""
        ) as cur:
            rows = await cur.fetchall()
    stats = {}
    for r in rows:
        total = r["total"]
        correct = r["correct_count"] or 0
        stats[r["timeframe"]] = {
            "total":    total,
            "correct":  correct,
            "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
            "avg_pct":  round(r["avg_pct"] or 0, 2),
        }
    return stats
