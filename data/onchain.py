# ============================================================
#  data/onchain.py
#  Zincir ici + makro indiktorler
# ============================================================

import asyncio
import aiohttp
import logging
import numpy as np
import pandas as pd
from config import FRED_API_KEY, WHALE_ALERT_KEY
from core.circuit_breaker import with_circuit_breaker

logger = logging.getLogger(__name__)


async def _get(url: str, params: dict = None) -> dict | list | None:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.warning(f"HTTP hatasi {url}: {e}")
    return None


# ── MVRV Z-SCORE PROXY ───────────────────────────────────

def compute_mvrv_proxy(df: pd.DataFrame) -> dict:
    """
    Gercek MVRV icin Glassnode API gerekir.
    Proxy: realized price = 200 gunluk EMA (yaklasik).
    """
    if df.empty or len(df) < 50:
        return {"normalized": 0}

    close        = df["close"]
    realized     = float(close.ewm(span=200).mean().iloc[-1])
    current      = float(close.iloc[-1])
    mvrv_ratio   = current / (realized + 1e-9)

    # Tarihsel: <1 = ucuz, >3.5 = pahali
    if mvrv_ratio < 1.0:
        normalized = (1.0 - mvrv_ratio) * 1.0    # Cok ucuz = guclu al
    elif mvrv_ratio > 3.5:
        normalized = -(mvrv_ratio - 3.5) / 2.0   # Pahali = sat
    else:
        normalized = float(np.tanh((1.8 - mvrv_ratio) / 1.2))

    normalized = float(np.clip(normalized, -1.0, 1.0))

    return {
        "ratio":          round(mvrv_ratio, 4),
        "realized_price": round(realized),
        "normalized":     round(normalized, 4),
        "signal":         "UCUZ" if mvrv_ratio < 1.2 else "PAHALI" if mvrv_ratio > 3.0 else "NORMAL",
    }


# ── NUPL PROXY ───────────────────────────────────────────

def compute_nupl_proxy(df: pd.DataFrame) -> dict:
    """
    NUPL (Net Unrealized Profit/Loss) proxy.
    Realized cap proxy olarak 155 gunluk EMA kullanilir.
    """
    if df.empty or len(df) < 60:
        return {"normalized": 0}

    close      = df["close"]
    realized   = float(close.ewm(span=155).mean().iloc[-1])
    current    = float(close.iloc[-1])
    market_cap = current    # Normalize icin
    real_cap   = realized

    nupl = (market_cap - real_cap) / (market_cap + 1e-9)

    # -0.25 altı = kapitülasyon, 0.75 üstü = oryonik mutluluk
    if nupl < -0.25:
        normalized = 1.0                             # Guclu al
    elif nupl < 0:
        normalized = float(-nupl / 0.25)
    elif nupl < 0.5:
        normalized = float(0.3 - nupl * 0.6)
    elif nupl < 0.75:
        normalized = float(-0.5 - (nupl - 0.5) * 2)
    else:
        normalized = -1.0                            # Guclu sat

    return {
        "nupl":       round(nupl, 4),
        "normalized": round(float(np.clip(normalized, -1.0, 1.0)), 4),
        "phase": (
            "Kapitulasyon" if nupl < -0.25 else
            "Umit"         if nupl < 0     else
            "Iyimserlik"   if nupl < 0.5   else
            "Inanic"       if nupl < 0.75  else
            "Oryonik"
        ),
    }


# ── HASH RIBBON ──────────────────────────────────────────

def compute_hash_ribbon(df: pd.DataFrame) -> dict:
    """
    30 gunluk ve 60 gunluk hash rate proxy (fiyat hacmi ile).
    MA30 > MA60 ve gecikten sonra kesisme = boga baslangici.
    """
    if df.empty or len(df) < 70:
        return {"normalized": 0}

    # Proxy: kapanış fiyatı * hacim (mining revenue proxy)
    proxy = df["close"] * df["volume"]

    ma30 = proxy.rolling(30).mean()
    ma60 = proxy.rolling(60).mean()

    ratio = float(ma30.iloc[-1] / (ma60.iloc[-1] + 1e-9))

    # MA30 > MA60: toparlama, madenci saglikli
    if ratio > 1.05:
        normalized = min((ratio - 1.0) * 8, 1.0)
    elif ratio > 0.95:
        normalized = (ratio - 1.0) * 4
    else:
        normalized = max((ratio - 1.0) * 5, -1.0)

    # Kesisme tespiti (son 5 gunde)
    cross_bull = False
    for i in range(-5, 0):
        if (ma30.iloc[i-1] <= ma60.iloc[i-1] and
                ma30.iloc[i] > ma60.iloc[i]):
            cross_bull = True
            break

    if cross_bull:
        normalized = min(normalized + 0.3, 1.0)

    return {
        "ratio":      round(ratio, 4),
        "cross_bull": cross_bull,
        "normalized": round(float(normalized), 4),
        "signal":     "TOPARLAMA" if ratio > 1.0 else "BASKI",
    }


# ── FEAR & GREED ─────────────────────────────────────────

@with_circuit_breaker("alternative_me", fallback={"normalized": 0})
async def get_fear_greed() -> dict:
    """
    Alternative.me Fear & Greed Endeksi (0-100).
    0 = Asiri korku (al firsati), 100 = Asiri acgozluluk (sat).
    """
    data = await _get("https://api.alternative.me/fng/?limit=1")
    if not data:
        return {"normalized": 0}

    value = int(data["data"][0]["value"])
    label = data["data"][0]["value_classification"]

    # Ters mantik: dusuk korku endeksi = yuksek al firsati
    # 0-25: guclu al, 25-45: al, 45-55: notr, 55-75: dikkat, 75-100: sat
    if value <= 25:
        normalized = (25 - value) / 25 * 1.0
    elif value <= 45:
        normalized = (45 - value) / 20 * 0.4
    elif value <= 55:
        normalized = 0.0
    elif value <= 75:
        normalized = -(value - 55) / 20 * 0.5
    else:
        normalized = -(value - 75) / 25 * 1.0

    return {
        "value":      value,
        "label":      label,
        "normalized": round(float(normalized), 4),
    }


# ── M2 PARA ARZI ─────────────────────────────────────────

@with_circuit_breaker("fred", fallback={"normalized": 0})
async def get_m2() -> dict:
    """
    ABD M2 para arzi buyume hizi (FRED API).
    Genisleyen M2 → risk varliklarini destekler.
    """
    if not FRED_API_KEY:
        return {"normalized": 0, "signal": "API_KEY_YOK"}

    data = await _get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id":      "M2SL",
            "api_key":        FRED_API_KEY,
            "file_type":      "json",
            "limit":          13,
            "sort_order":     "desc",
        }
    )
    if not data or "observations" not in data:
        return {"normalized": 0}

    obs = [float(o["value"]) for o in data["observations"]
           if o["value"] != "."]
    if len(obs) < 2:
        return {"normalized": 0}

    growth_yoy = (obs[0] - obs[-1]) / (obs[-1] + 1e-9) * 100
    normalized = float(np.tanh(growth_yoy / 5))

    return {
        "current":    round(obs[0], 2),
        "growth_yoy": round(growth_yoy, 2),
        "normalized": round(normalized, 4),
        "signal":     "GENISLIYOR" if growth_yoy > 3 else "DARALIYOR",
    }


# ── DXY ──────────────────────────────────────────────────

@with_circuit_breaker("stooq", fallback={"normalized": 0})
async def get_dxy() -> dict:
    """
    DXY (ABD Dolar Endeksi) — stooq.com
    DXY duser → risk varliklarina para girer → bullish BTC
    """
    data = await _get("https://stooq.com/q/l/?s=dx.f&f=sd2t2ohlcv&h&e=csv")
    if not data:
        return {"normalized": 0}

    # Basit CSV parse (text response)
    return {"normalized": 0, "signal": "STOOQ_CSV"}


@with_circuit_breaker("alternative_dxy", fallback={"normalized": 0})
async def get_dxy_alternative() -> dict:
    """Alternatif DXY kaynagi."""
    try:
        data = await _get(
            "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
            params={"interval": "1d", "range": "5d"}
        )
        if not data:
            return {"normalized": 0}

        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if len(closes) < 2:
            return {"normalized": 0}

        current  = closes[-1]
        previous = closes[-2]
        change   = (current - previous) / (previous + 1e-9) * 100

        # DXY yukselis = BTC icin bearish
        normalized = float(-np.tanh(change / 1.5))

        return {
            "current":    round(current, 3),
            "change_pct": round(change, 3),
            "normalized": round(normalized, 4),
            "signal":     "GUCLENIYOR" if change > 0 else "ZAYIFLIYOR",
        }
    except Exception as e:
        logger.warning(f"DXY alternatif hatasi: {e}")
        return {"normalized": 0}


# ── VIX ──────────────────────────────────────────────────

@with_circuit_breaker("alternative_vix", fallback={"normalized": 0, "danger": False})
async def get_vix() -> dict:
    """
    VIX korku endeksi (Yahoo Finance).
    Yuksek VIX → panik → kisa vadeli dip firsati olabilir.
    VIX > 30 → tehlike bolgesi.
    """
    try:
        data = await _get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",
            params={"interval": "1d", "range": "5d"}
        )
        if not data:
            return {"normalized": 0, "danger": False}

        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if not closes:
            return {"normalized": 0, "danger": False}

        current = closes[-1]
        danger  = current > 30

        # Yuksek VIX = panik = potansiyel al firsati (kontrarian)
        # Ama aynı zamanda risk = guven duser
        if current > 40:
            normalized   = 0.5       # Asiri panik = al firsati
            risk_mult    = 0.4       # Ama guven cok dusuk
        elif current > 30:
            normalized   = 0.2
            risk_mult    = 0.6
        elif current > 20:
            normalized   = 0.0
            risk_mult    = 0.85
        else:
            normalized   = 0.1       # Dusuk VIX = sakin piyasa
            risk_mult    = 1.0

        return {
            "current":      round(current, 2),
            "danger":       danger,
            "normalized":   round(normalized, 4),
            "risk_multiplier": risk_mult,
        }
    except Exception as e:
        logger.warning(f"VIX hatasi: {e}")
        return {"normalized": 0, "danger": False, "risk_multiplier": 1.0}


# ── WHALE ALERT ──────────────────────────────────────────

@with_circuit_breaker("whale_alert", fallback={"normalized": 0})
async def get_whale_alert() -> dict:
    """
    Buyuk BTC transferleri.
    Borsaya giden = satis baskisi.
    Borsadan cikan = uzun vadeli hodl.
    """
    if not WHALE_ALERT_KEY:
        return {"normalized": 0, "signal": "API_KEY_YOK"}

    data = await _get(
        "https://api.whale-alert.io/v1/transactions",
        params={
            "api_key":  WHALE_ALERT_KEY,
            "min_value": 1_000_000,
            "currency": "btc",
            "limit":    20,
        }
    )
    if not data or "transactions" not in data:
        return {"normalized": 0}

    exchange_in  = 0.0  # Borsaya giren (potansiyel satis)
    exchange_out = 0.0  # Borsadan cikan (hodl sinyali)

    for tx in data["transactions"]:
        usd = float(tx.get("amount_usd", 0))
        to_ex   = tx.get("to", {}).get("owner_type") == "exchange"
        from_ex = tx.get("from", {}).get("owner_type") == "exchange"

        if to_ex and not from_ex:
            exchange_in  += usd
        elif from_ex and not to_ex:
            exchange_out += usd

    total = exchange_in + exchange_out
    if total < 1e6:
        return {"normalized": 0}

    net_flow   = exchange_out - exchange_in
    normalized = float(np.tanh(net_flow / (total + 1e-9) * 3))

    return {
        "exchange_in_usd":  round(exchange_in  / 1e6, 2),
        "exchange_out_usd": round(exchange_out / 1e6, 2),
        "net_flow_usd":     round(net_flow     / 1e6, 2),
        "normalized":       round(normalized, 4),
    }


# ── BORSA NET AKISI (Exchange Net Flow) ──────────────────

@with_circuit_breaker("binance_spot", fallback={"normalized": 0})
async def get_exchange_flow() -> dict:
    """
    Binance BTC net akisi proxy.
    Satici baskisi vs talep baskisi.
    """
    # Binance API'den 24h net flow: buy_vol - sell_vol
    data = await _get(
        "https://api.binance.com/api/v3/ticker/24hr",
        params={"symbol": "BTCUSDT"}
    )
    if not data:
        return {"normalized": 0}

    # Takerbuyvol / Takersellvol yerine quote vol proxy
    buy_vol  = float(data.get("takerBuyBaseAssetVolume", 0))
    total_vol= float(data.get("volume", 1))
    sell_vol = total_vol - buy_vol

    ratio     = buy_vol / (total_vol + 1e-9)
    normalized= float(np.tanh((ratio - 0.5) * 8))

    return {
        "buy_ratio":  round(ratio, 4),
        "normalized": round(normalized, 4),
        "signal":     "TALEP" if ratio > 0.52 else "SATIS" if ratio < 0.48 else "DENGELI",
    }


# ── MADEN GELIRI (Miner Revenue) ─────────────────────────

def compute_miner_revenue(df: pd.DataFrame) -> dict:
    """
    Madenci gelir proxy: fiyat * hacim * 0.00000625 (blok odulu etkisi).
    Dusuk gelir → kapitulasyon → potansiyel dip.
    """
    if df.empty or len(df) < 30:
        return {"normalized": 0}

    revenue_proxy = df["close"] * df["volume"] * 6.25 / 1e6  # BTC cinsinden
    rv30  = float(revenue_proxy.rolling(30).mean().iloc[-1])
    rv90  = float(revenue_proxy.rolling(90).mean().iloc[-1]) if len(df) >= 90 else rv30

    ratio = rv30 / (rv90 + 1e-9)

    # Dusuk gelir = kapitulasyon = al firsati
    if ratio < 0.7:
        normalized = 0.8
    elif ratio < 0.9:
        normalized = 0.3
    elif ratio < 1.1:
        normalized = 0.0
    elif ratio < 1.3:
        normalized = -0.2
    else:
        normalized = -0.5

    return {
        "revenue_30d": round(rv30, 4),
        "ratio_30_90": round(ratio, 4),
        "normalized":  round(normalized, 4),
    }


# ── ALTCOIN DOMINANSI ────────────────────────────────────

@with_circuit_breaker("coinmarketcap", fallback={"normalized": 0})
async def get_altcoin_dominance() -> dict:
    """
    BTC dominansi (CoinGecko global API).
    Dusuk BTC dominansi → risk ishtahi yuksek → gec boga.
    """
    data = await _get("https://api.coingecko.com/api/v3/global")
    if not data:
        return {"normalized": 0}

    btc_dom = float(
        data.get("data", {})
            .get("market_cap_percentage", {})
            .get("btc", 50)
    )

    # Yuksek BTC dominansi = erken boga, dusuk = gec boga
    # Ters mantik: yuksek dom = BTC yukseliyor = al sinyali
    normalized = float(np.tanh((btc_dom - 50) / 15))

    return {
        "btc_dominance": round(btc_dom, 2),
        "normalized":    round(normalized, 4),
        "phase": (
            "ERKEN_BOGA" if btc_dom > 55 else
            "GEC_BOGA"   if btc_dom < 40 else
            "NORMAL"
        ),
    }
