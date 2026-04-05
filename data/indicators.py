# ============================================================
#  data/indicators.py
#  Tum indiktorleri toplayan orkestrator
#
#  Kaldirildi:
#  - hash_ribbon: onchain.py'den kaldirildi, guvenilmez proxy
#  - exchange_flow: onchain.py'den kaldirildi, guvenilmez proxy
# ============================================================

import asyncio
import logging
from core.data_bus import data_bus
from config import BTC_SYMBOL

logger = logging.getLogger(__name__)


async def fetch_all(price_df_4h=None, price_df_1d=None, price_df_1w=None):
    tasks = []

    if price_df_4h is not None and not price_df_4h.empty:
        tasks.append(_fetch_technicals(price_df_4h))
        tasks.append(_fetch_realized_vol(price_df_4h))

    if price_df_1d is not None and not price_df_1d.empty:
        tasks.append(_fetch_log_log_band(price_df_1d))
        tasks.append(_fetch_weekly_rsi(price_df_1d))
        tasks.append(_fetch_mvrv(price_df_1d))
        tasks.append(_fetch_nupl(price_df_1d))
        tasks.append(_fetch_miner_revenue(price_df_1d))

    tasks += [
        _fetch_funding_rate(),
        _fetch_open_interest(),
        _fetch_liquidations(),
        _fetch_coinbase_premium(),
        _fetch_fear_greed(),
        _fetch_m2(),
        _fetch_dxy(),
        _fetch_vix(),
        _fetch_whale_alert(),
        _fetch_altcoin_dominance(),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Indiktor gorme hatasi: {r}")

    logger.info("Tum indiktorler guncellendi")


async def _fetch_technicals(df):
    try:
        from data.price import compute_technicals
        await data_bus.set("technicals", compute_technicals(df), source="binance")
    except Exception as e:
        await data_bus.set_error("technicals", str(e))


async def _fetch_realized_vol(df):
    try:
        from data.price import compute_realized_vol
        await data_bus.set("realized_vol", compute_realized_vol(df), source="binance")
    except Exception as e:
        await data_bus.set_error("realized_vol", str(e))


async def _fetch_log_log_band(df):
    try:
        from data.price import compute_log_log_band
        await data_bus.set("log_log_band", compute_log_log_band(df), source="binance")
    except Exception as e:
        await data_bus.set_error("log_log_band", str(e))


async def _fetch_weekly_rsi(df):
    try:
        from data.price import compute_weekly_rsi
        await data_bus.set("weekly_rsi", compute_weekly_rsi(df), source="binance")
    except Exception as e:
        await data_bus.set_error("weekly_rsi", str(e))


async def _fetch_mvrv(df):
    try:
        from data.onchain import compute_mvrv_proxy
        await data_bus.set("mvrv", compute_mvrv_proxy(df), source="proxy")
    except Exception as e:
        await data_bus.set_error("mvrv", str(e))


async def _fetch_nupl(df):
    try:
        from data.onchain import compute_nupl_proxy
        await data_bus.set("nupl", compute_nupl_proxy(df), source="proxy")
    except Exception as e:
        await data_bus.set_error("nupl", str(e))


async def _fetch_miner_revenue(df):
    try:
        from data.onchain import compute_miner_revenue
        await data_bus.set("miner_revenue", compute_miner_revenue(df), source="proxy")
    except Exception as e:
        await data_bus.set_error("miner_revenue", str(e))


async def _fetch_funding_rate():
    try:
        from data.price import get_funding_rate
        await data_bus.set("funding_rate", await get_funding_rate(BTC_SYMBOL), source="binance_futures")
    except Exception as e:
        await data_bus.set_error("funding_rate", str(e))


async def _fetch_open_interest():
    try:
        from data.price import get_open_interest
        await data_bus.set("open_interest", await get_open_interest(BTC_SYMBOL), source="binance_futures")
    except Exception as e:
        await data_bus.set_error("open_interest", str(e))


async def _fetch_liquidations():
    try:
        from data.price import get_liquidations
        await data_bus.set("liquidations", await get_liquidations(BTC_SYMBOL), source="binance_futures")
    except Exception as e:
        await data_bus.set_error("liquidations", str(e))


async def _fetch_coinbase_premium():
    try:
        from data.price import get_coinbase_premium
        await data_bus.set("coinbase_premium", await get_coinbase_premium(), source="coinbase")
    except Exception as e:
        await data_bus.set_error("coinbase_premium", str(e))


async def _fetch_fear_greed():
    try:
        from data.onchain import get_fear_greed
        await data_bus.set("fear_greed", await get_fear_greed(), source="alternative_me")
    except Exception as e:
        await data_bus.set_error("fear_greed", str(e))


async def _fetch_m2():
    try:
        from data.onchain import get_m2
        await data_bus.set("m2", await get_m2(), source="fred")
    except Exception as e:
        await data_bus.set_error("m2", str(e))


async def _fetch_dxy():
    try:
        from data.onchain import get_dxy_alternative
        await data_bus.set("dxy", await get_dxy_alternative(), source="yahoo")
    except Exception as e:
        await data_bus.set_error("dxy", str(e))


async def _fetch_vix():
    try:
        from data.onchain import get_vix
        await data_bus.set("vix", await get_vix(), source="yahoo")
    except Exception as e:
        await data_bus.set_error("vix", str(e))


async def _fetch_whale_alert():
    try:
        from data.onchain import get_whale_alert
        await data_bus.set("whale_alert", await get_whale_alert(), source="whale_alert")
    except Exception as e:
        await data_bus.set_error("whale_alert", str(e))


async def _fetch_altcoin_dominance():
    try:
        from data.onchain import get_altcoin_dominance
        await data_bus.set("altcoin_dominance", await get_altcoin_dominance(), source="coingecko")
    except Exception as e:
        await data_bus.set_error("altcoin_dominance", str(e))
