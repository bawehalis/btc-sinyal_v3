# ============================================================
#  signals/runner.py
#  BTC Sinyal Orkestratoru
# ============================================================

import asyncio
import logging
from datetime import datetime, timedelta
from config import BTC_SYMBOL, ALERT_COOLDOWN_H
from core.data_bus import data_bus
from signals.engine import compute_signal
from signals.confidence_gate import should_send, is_alert_worthy

logger = logging.getLogger(__name__)

# Son uyari takibi
_last_alert_ts:    float = 0.0
_last_alert_score: float = 0.0


class Runner:
    def __init__(self):
        self._telegram = None   # main.py tarafindan set edilir

    def set_telegram(self, telegram_bot):
        self._telegram = telegram_bot

    async def _fetch_prices(self) -> tuple:
        """Tum timeframe'ler icin fiyat verisini cek."""
        from data.price import fetch_klines, get_price_df

        for interval in ["4h", "1d", "1w"]:
            try:
                await fetch_klines(BTC_SYMBOL, interval, 500)
            except Exception as e:
                logger.warning(f"Kline hatasi [{interval}]: {e}")

        df_4h = await get_price_df(BTC_SYMBOL, "4h", 500)
        df_1d = await get_price_df(BTC_SYMBOL, "1d", 500)
        df_1w = await get_price_df(BTC_SYMBOL, "1w", 200)

        return df_4h, df_1d, df_1w

    async def run(self, timeframe: str = "4h") -> dict | None:
        """
        Tam sinyal dongusu:
        1. Fiyat cek
        2. Tum indiktorleri guncelle
        3. Sinyal hesapla
        4. Guven filtresi
        5. Telegram'a gonder
        6. DB'ye kaydet
        """
        logger.info(f"Sinyal dongusu basliyor: {timeframe}")

        # Fiyat verileri
        df_4h, df_1d, df_1w = await self._fetch_prices()

        # Indiktorler
        from data.indicators import fetch_all
        await fetch_all(
            price_df_4h=df_4h,
            price_df_1d=df_1d,
            price_df_1w=df_1w,
        )

        # DataBus kaliciligi
        await data_bus.persist_all()

        # Anlık fiyat
        from data.price import get_current_price
        price = await get_current_price(BTC_SYMBOL)

        # Sinyal hesapla
        indicators = await data_bus.get_all()

        df_map = {"4h": df_4h, "1d": df_1d, "1w": df_1w, "1M": df_1d}
        price_df = df_map.get(timeframe, df_1d)

        result = compute_signal(indicators, price_df, timeframe)

        # Guven filtresi
        send_ok, reason = should_send(result)
        if not send_ok:
            logger.info(f"Sinyal gonderilmedi: {reason}")
            # DB'ye kaydet (gonderilmedi olarak)
            await self._save_signal(result, price, sent=False)
            return result

        # Mesaj gonder
        if self._telegram:
            from bot.formatter import format_signal
            msg = format_signal(result, price, timeframe)
            await self._telegram.send(msg)

        # Anlık uyarı kontrolü
        await self._check_alert(result, price)

        # DB'ye kaydet
        await self._save_signal(result, price, sent=True)

        logger.info(
            f"Sinyal gonderildi: {result['label']} "
            f"(skor={result['score']:+.3f}, guven=%{int(result['confidence']*100)})"
        )
        return result

    async def _check_alert(self, result: dict, price: float):
        """Anlık güçlü uyarı kontrolü."""
        global _last_alert_ts, _last_alert_score

        now = datetime.now().timestamp()
        cooldown_ok = (now - _last_alert_ts) >= ALERT_COOLDOWN_H * 3600

        if not cooldown_ok:
            return

        alert_ok, _ = is_alert_worthy(result, _last_alert_score)
        if alert_ok and self._telegram:
            from bot.formatter import format_alert
            msg = format_alert(result, price)
            await self._telegram.send(msg)
            _last_alert_ts    = now
            _last_alert_score = result["score"]
            logger.info(f"Anlik uyari gonderildi: {result['label']}")

    async def _save_signal(self, result: dict, price: float, sent: bool):
        try:
            from db.database import save_signal, mark_signal_sent
            sig_id = await save_signal(result, price)
            if sent:
                await mark_signal_sent(sig_id)
        except Exception as e:
            logger.error(f"DB kayit hatasi: {e}")

    async def get_summary(self) -> dict:
        """
        /sinyal komutu icin tum timeframe'lerin ozeti.
        Veriyi tekrar cekmez, mevcut DataBus'u kullanir.
        """
        from data.price import get_current_price, get_price_df
        price  = await get_current_price(BTC_SYMBOL)
        df_4h  = await get_price_df(BTC_SYMBOL, "4h", 200)
        df_1d  = await get_price_df(BTC_SYMBOL, "1d", 200)
        df_1w  = await get_price_df(BTC_SYMBOL, "1w", 100)

        indicators = await data_bus.get_all()
        results    = {}

        for tf, df in [("4h", df_4h), ("1d", df_1d), ("1w", df_1w)]:
            results[tf] = compute_signal(indicators, df, tf)

        return {
            "price":   price,
            "results": results,
            "health":  await data_bus.health_report(),
        }


# Global instance
runner = Runner()
