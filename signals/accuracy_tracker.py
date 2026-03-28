# ============================================================
#  signals/accuracy_tracker.py
#  Sinyal sonuclarini takip et — basari orani hesapla
#
#  Akis:
#  Her sinyalden X saat sonra fiyata bak.
#  Sinyal yonuyle fiyat hareketi urusuyorsa "dogru".
#  Sonucu DB'ye kaydet.
# ============================================================

import asyncio
import logging
from datetime import datetime, timedelta
from config import BTC_SYMBOL

logger = logging.getLogger(__name__)

# Kac saat sonra degerlendirme yapilacak
HORIZONS = {
    "4h":  24,    # 4 saatlik sinyal → 24 saat sonra bak
    "1d":  72,    # Gunluk sinyal → 3 gun sonra bak
    "1w":  168,   # Haftalik sinyal → 7 gun sonra bak
    "1M":  720,   # Aylik sinyal → 30 gun sonra bak
}


async def evaluate_pending_signals():
    """
    Degerlendirme suresi dolan sinyalleri kontrol et.
    APScheduler ile periyodik calistirilir.
    """
    from db.database import get_recent_signals, save_accuracy_record, get_prices
    from data.price import get_current_price

    now_ms = int(datetime.now().timestamp() * 1000)

    for timeframe, horizon_h in HORIZONS.items():
        try:
            # Bu timeframe icin son 30 gunluk sinyalleri al
            signals = await get_recent_signals(hours=720, timeframe=timeframe)

            for sig in signals:
                sig_ts   = sig["created_at"]
                sig_id   = sig["id"]
                horizon_ms = horizon_h * 3600 * 1000

                # Degerlendirme zamani geldiyse ve henuz degerlendirilmediyse
                if now_ms - sig_ts < horizon_ms:
                    continue

                # Zaten degerlendirilmis mi?
                # (DB'de accuracy kaydi var mi — basit kontrol)
                # Simdilik atla, production'da duplicate check ekle
                price_at_signal = sig.get("price", 0)
                if not price_at_signal:
                    continue

                # O tarihteki fiyati bul (DB'den)
                target_ts = sig_ts + horizon_ms
                rows = await get_prices(BTC_SYMBOL, "1h", 1000)

                # Hedef zamana en yakin fiyati bul
                price_after = None
                min_diff = float("inf")
                for row in rows:
                    diff = abs(row["ts"] - target_ts)
                    if diff < min_diff:
                        min_diff = diff
                        price_after = row["close"]

                if price_after is None:
                    continue

                pct_change = (price_after - price_at_signal) / (price_at_signal + 1e-9) * 100
                score      = sig["score"]

                # Dogru mu?
                # AL sinyali + fiyat yukseldi = dogru
                # SAT sinyali + fiyat dustü = dogru
                if score > 0.30:
                    correct = 1 if pct_change > 2 else 0
                elif score < -0.30:
                    correct = 1 if pct_change < -2 else 0
                else:
                    # BEKLE — neutral, degerlendirme yok
                    continue

                await save_accuracy_record({
                    "signal_id":      sig_id,
                    "timeframe":      timeframe,
                    "signal_ts":      sig_ts,
                    "score":          score,
                    "label":          sig["label"],
                    "price_at_signal": price_at_signal,
                    "price_after":    price_after,
                    "horizon_h":      horizon_h,
                    "correct":        correct,
                    "pct_change":     round(pct_change, 2),
                })
                logger.info(
                    f"Sinyal degerlendirme [{timeframe}]: "
                    f"{'DOGRU' if correct else 'YANLIS'} "
                    f"(skor={score:+.2f}, degisim=%{pct_change:+.1f})"
                )

        except Exception as e:
            logger.warning(f"Accuracy tracker hatasi [{timeframe}]: {e}")
