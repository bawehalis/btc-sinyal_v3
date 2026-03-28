# ============================================================
#  bot/telegram_bot.py
#  Telegram bot -- temiz async, tek event loop
# ============================================================

import asyncio
import logging
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self):
        self.token   = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self._app    = None

    async def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        try:
            from telegram import Bot
            bot = Bot(token=self.token)
            await bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
            )
            return True
        except Exception as e:
            if "can't parse" in str(e).lower():
                try:
                    from telegram import Bot
                    bot = Bot(token=self.token)
                    await bot.send_message(
                        chat_id=self.chat_id,
                        text=text,
                    )
                    return True
                except Exception as e2:
                    logger.error(f"Telegram gonderim hatasi (plain): {e2}")
                    return False
            logger.error(f"Telegram gonderim hatasi: {e}")
            return False

    async def build_app(self, runner):
        from telegram.ext import Application, CommandHandler

        app = Application.builder().token(self.token).build()

        async def cmd_sinyal(update, context):
            await update.message.reply_text("Hesaplaniyor...")
            try:
                summary = await runner.get_summary()
                from bot.formatter import format_summary
                await update.message.reply_text(
                    format_summary(summary), parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"Hata: {e}")

        async def cmd_4s(update, context):
            await update.message.reply_text("Hesaplaniyor...")
            try:
                result, price = await runner.compute_only("4h")
                from bot.formatter import format_signal
                await update.message.reply_text(
                    format_signal(result, price, "4h"), parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"Hata: {e}")

        async def cmd_gunluk(update, context):
            await update.message.reply_text("Hesaplaniyor...")
            try:
                result, price = await runner.compute_only("1d")
                from bot.formatter import format_signal
                await update.message.reply_text(
                    format_signal(result, price, "1d"), parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"Hata: {e}")

        async def cmd_haftalik(update, context):
            await update.message.reply_text("Hesaplaniyor...")
            try:
                result, price = await runner.compute_only("1w")
                from bot.formatter import format_signal
                await update.message.reply_text(
                    format_signal(result, price, "1w"), parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"Hata: {e}")

        async def cmd_band(update, context):
            try:
                from core.data_bus import data_bus
                from data.price import get_current_price
                from bot.formatter import format_band
                from config import BTC_SYMBOL
                band  = await data_bus.get("log_log_band")
                price = await get_current_price(BTC_SYMBOL)
                await update.message.reply_text(
                    format_band(band or {}, price), parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"Hata: {e}")

        async def cmd_basari(update, context):
            try:
                from db.database import get_accuracy_stats
                from bot.formatter import format_accuracy
                stats = await get_accuracy_stats()
                await update.message.reply_text(
                    format_accuracy(stats), parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"Hata: {e}")

        async def cmd_whale(update, context):
            try:
                from core.data_bus import data_bus
                from bot.formatter import format_whale
                whale = await data_bus.get("whale_alert")
                await update.message.reply_text(
                    format_whale(whale or {}), parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"Hata: {e}")

        async def cmd_durum(update, context):
            try:
                from core.data_bus import data_bus
                from core.circuit_breaker import all_statuses
                from bot.formatter import format_health
                health      = await data_bus.health_report()
                cb_statuses = all_statuses()
                msg         = format_health(health)
                open_cbs    = [s for s in cb_statuses if s["state"] != "CLOSED"]
                if open_cbs:
                    msg += "\n\nAcik Devreler:\n"
                    for cb in open_cbs:
                        msg += f"  [{cb['name']}]: {cb['state']} ({cb['failures']} hata)\n"
                await update.message.reply_text(msg, parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"Hata: {e}")

        async def cmd_yardim(update, context):
            await update.message.reply_text(
                "*BTC Sinyal Botu*\n"
                "============================\n"
                "/sinyal   -- Tum zaman dilimlerinin ozeti\n"
                "/4s       -- 4 saatlik sinyal\n"
                "/gunluk   -- Gunluk rapor\n"
                "/haftalik -- Haftalik ozet\n"
                "/band     -- Log-Log guc yasasi bandi\n"
                "/basari   -- Gecmis basari oranlari\n"
                "/whale    -- Son balina hareketleri\n"
                "/durum    -- Sistem ve veri sagligi\n"
                "/yardim   -- Bu mesaj",
                parse_mode="Markdown"
            )

        handlers = [
            ("sinyal",   cmd_sinyal),
            ("4s",       cmd_4s),
            ("gunluk",   cmd_gunluk),
            ("haftalik", cmd_haftalik),
            ("band",     cmd_band),
            ("basari",   cmd_basari),
            ("whale",    cmd_whale),
            ("durum",    cmd_durum),
            ("yardim",   cmd_yardim),
        ]

        for cmd, fn in handlers:
            app.add_handler(CommandHandler(cmd, fn))

        self._app = app
        logger.info(f"{len(handlers)} komut kaydedildi")
        return app


# Global instance
telegram_bot = TelegramBot()

from core.data_bus import data_bus
