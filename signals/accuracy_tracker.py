# ============================================================

# signals/accuracy_tracker.py

# Sinyal basari takibi

# ============================================================

import logging
from datetime import datetime
from config import BTC_SYMBOL

logger = logging.getLogger(**name**)

HORIZONS = {
“4h”: 24,
“1d”: 72,
“1w”: 168,
“1M”: 720,
}

async def evaluate_pending_signals():
from db.database import get_recent_signals, save_accuracy_record, get_prices
from data.price import get_current_price

```
now_ms = int(datetime.now().timestamp() * 1000)

# Zaten degerlendirilmis signal_id'leri once cek
import aiosqlite
from config import DB_PATH
evaluated_ids = set()
async with aiosqlite.connect(DB_PATH) as db:
    async with db.execute("SELECT signal_id FROM accuracy") as cur:
        rows = await cur.fetchall()
        evaluated_ids = {r[0] for r in rows}

# Fiyat gecmisini bir kez cek
price_rows = await get_prices(BTC_SYMBOL, "1h", 2000)

for timeframe, horizon_h in HORIZONS.items():
    try:
        signals = await get_recent_signals(hours=720, timeframe=timeframe)
        horizon_ms = horizon_h * 3600 * 1000

        for sig in signals:
            sig_id = sig["id"]
            sig_ts = sig["created_at"]
            score  = sig.get("score", 0)

            # Zaten degerlendirilmis mi?
            if sig_id in evaluated_ids:
                continue

            # Degerlendirme zamani geldi mi?
            if now_ms - sig_ts < horizon_ms:
                continue

            # BEKLE sinyallerini degerlendirme
            if -0.30 <= score <= 0.30:
                continue

            # Sinyal anindaki fiyat
            price_at_signal = sig.get("price") or 0

            # Fiyat yoksa o tarihe en yakin DB kaydini bul
            if not price_at_signal:
                min_diff = float("inf")
                for row in price_rows:
                    diff = abs(row["ts"] - sig_ts)
                    if diff < min_diff:
                        min_diff = diff
                        price_at_signal = row["close"]

            if not price_at_signal:
                logger.debug(f"Sinyal {sig_id} icin fiyat bulunamadi, atlaniyor")
                continue

            # Hedef zamandaki fiyat
            target_ts   = sig_ts + horizon_ms
            price_after = None
            min_diff    = float("inf")
            for row in price_rows:
                diff = abs(row["ts"] - target_ts)
                if diff < min_diff:
                    min_diff = diff
                    price_after = row["close"]

            if not price_after:
                continue

            pct_change = (price_after - price_at_signal) / (price_at_signal + 1e-9) * 100

            if score > 0.30:
                correct = 1 if pct_change > 2 else 0
            else:
                correct = 1 if pct_change < -2 else 0

            await save_accuracy_record({
                "signal_id":       sig_id,
                "timeframe":       timeframe,
                "signal_ts":       sig_ts,
                "score":           score,
                "label":           sig.get("label", ""),
                "price_at_signal": price_at_signal,
                "price_after":     price_after,
                "horizon_h":       horizon_h,
                "correct":         correct,
                "pct_change":      round(pct_change, 2),
            })
            evaluated_ids.add(sig_id)

            logger.info(
                f"Degerlendirme [{timeframe}] sinyal#{sig_id}: "
                f"{'DOGRU' if correct else 'YANLIS'} "
                f"(skor={score:+.2f}, degisim=%{pct_change:+.1f})"
            )

    except Exception as e:
        logger.warning(f"Accuracy tracker hatasi [{timeframe}]: {e}")

logger.info(f"Accuracy tracker tamamlandi. Toplam degerlendirilmis: {len(evaluated_ids)}")
```