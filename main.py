# ============================================================
#  main.py
#  BTC Sinyal Botu -- Ana Giris Noktasi
#
#  Mimari:
#  - Tek asyncio event loop
#  - APScheduler AsyncIOScheduler (thread yok)
#  - Telegram polling ayni loop'ta
#  - Circuit breaker ile API korumasi
#  - DataBus kaliciligi (SQLite)
#  - Accuracy tracker (sinyal basari takibi)
# ============================================================

import asyncio
import logging
import colorlog
from datetime import datetime
from pathlib import Path


def setup_logging():
    Path("logs").mkdir(exist_ok=True)

    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG":    "cyan",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
        }
    ))

    file_handler = logging.FileHandler("logs/bot.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(file_handler)


setup_logging()
logger = logging.getLogger("main")


async def startup():
    logger.info("=" * 55)
    logger.info("  BTC SINYAL BOTU v3.0")
    logger.info("  Temiz Mimari | Judge | Circuit Breaker | Async")
    logger.info("=" * 55)

    from db.database import init_db
    await init_db()
    logger.info("Veritabani hazir")

    from core.data_bus import data_bus
    await data_bus.restore_from_db()

    from data.price import fetch_klines
    from config import BTC_SYMBOL
    logger.info("Fiyat verisi cekiliyor...")
    for interval in ["4h", "1d", "1w"]:
        try:
            candles = await fetch_klines(BTC_SYMBOL, interval, 500)
            logger.info(f"  [{interval}] {len(candles)} mum")
        except Exception as e:
            logger.warning(f"  [{interval}] hata: {e}")

    from data.price import get_price_df
    from data.indicators import fetch_all
    logger.info("Indiktorler guncelleniyor...")
    try:
        df_4h = await get_price_df(BTC_SYMBOL, "4h", 500)
        df_1d = await get_price_df(BTC_SYMBOL, "1d", 500)
        df_1w = await get_price_df(BTC_SYMBOL, "1w", 200)
        await fetch_all(price_df_4h=df_4h, price_df_1d=df_1d, price_df_1w=df_1w)
        logger.info("Indiktorler guncellendi")
    except Exception as e:
        logger.warning(f"Indiktor guncelleme hatasi: {e}")

    from signals.runner import runner
    from bot.telegram_bot import telegram_bot
    runner.set_telegram(telegram_bot)

    logger.info("Ilk sinyal hesaplaniyor...")
    try:
        await runner.run("4h")
    except Exception as e:
        logger.error(f"Ilk sinyal hatasi: {e}")

    from config import CONFIDENCE_GATE
    await telegram_bot.send(
        f"*BTC Sinyal Botu v3.0 Aktif*\n"
        f"{'=' * 28}\n"
        f"{datetime.now().strftime('%d %b %Y - %H:%M')}\n\n"
        f"*Ozellikler:*\n"
        f"  20 indiktor, 5 katman\n"
        f"  Basyargic (Judge) mekanizmasi\n"
        f"  Guven filtresi (<%{int(CONFIDENCE_GATE*100)} susturulur)\n"
        f"  Circuit breaker API korumasi\n"
        f"  Sinyal basari takibi\n\n"
        f"/yardim -- Tum komutlar\n\n"
        f"Yatirim tavsiyesi degildir."
    )


async def _run_4h():
    from signals.runner import runner
    await runner.run("4h")


async def _run_1d():
    from signals.runner import runner
    await runner.run("1d")


async def _run_1w():
    from signals.runner import runner
    await runner.run("1w")


async def _run_1M():
    from signals.runner import runner
    await runner.run("1M")


async def _persist():
    from core.data_bus import data_bus
    try:
        await data_bus.persist_all()
    except Exception as e:
        logger.warning(f"DataBus persist hatasi: {e}")


async def _evaluate_accuracy():
    from signals.accuracy_tracker import evaluate_pending_signals
    try:
        await evaluate_pending_signals()
    except Exception as e:
        logger.warning(f"Accuracy tracker hatasi: {e}")


async def main():
    await startup()

    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler(timezone="Europe/Istanbul")

    scheduler.add_job(
        _run_4h, "interval", hours=4,
        id="signal_4h", name="4h Sinyal",
        max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        _run_1d, "cron",
        hour=8, minute=0,
        id="signal_1d", name="Gunluk Rapor",
        max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        _run_1w, "cron",
        day_of_week="mon", hour=9, minute=0,
        id="signal_1w", name="Haftalik Ozet",
        max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        _run_1M, "cron",
        day=1, hour=10, minute=0,
        id="signal_1M", name="Aylik Rapor",
        max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        _persist, "interval", minutes=30,
        id="persist", name="DataBus Kayit",
    )
    scheduler.add_job(
        _evaluate_accuracy, "interval", hours=6,
        id="accuracy", name="Basari Takibi",
    )

    scheduler.start()
    jobs = scheduler.get_jobs()
    logger.info(f"Zamanlayici aktif: {len(jobs)} gorev")
    for j in jobs:
        logger.info(f"  - {j.name}")

    from bot.telegram_bot import telegram_bot
    from signals.runner import runner

    app = await telegram_bot.build_app(runner)

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram polling aktif")

        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Kapatma sinyali alindi")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot durduruldu.")
    except Exception as e:
        logger.critical(f"Kritik hata: {e}", exc_info=True)
        raise
