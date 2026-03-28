# ============================================================
#  data/price.py
#  Fiyat verisi — Binance
#
#  Global state YOK. Tum fonksiyonlar symbol parametresi alir.
# ============================================================

import asyncio
import aiohttp
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from config import BINANCE_BASE, BINANCE_FAPI, BTC_SYMBOL
from core.circuit_breaker import with_circuit_breaker

logger = logging.getLogger(__name__)

# Bitcoin genesis tarihi (Log-Log band icin)
BTC_GENESIS = pd.Timestamp("2009-01-03")


# ── HTTP YARDIMCI ────────────────────────────────────────

async def _get(url: str, params: dict = None,
               session: aiohttp.ClientSession = None,
               retries: int = 3) -> dict | list | None:
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    try:
        for attempt in range(retries):
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        return await r.json()
                    logger.warning(f"HTTP {r.status}: {url}")
            except Exception as e:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
    finally:
        if close_session:
            await session.close()
    return None


# ── OHLCV ────────────────────────────────────────────────

@with_circuit_breaker("binance_spot", fallback=[])
async def fetch_klines(symbol: str = BTC_SYMBOL,
                       interval: str = "1h",
                       limit: int = 500) -> list:
    """Binance'dan OHLCV verisi cek, DB'ye kaydet."""
    data = await _get(f"{BINANCE_BASE}/klines", {
        "symbol": symbol, "interval": interval, "limit": limit
    })
    if not data:
        return []

    candles = [{
        "ts":     int(c[0]),
        "open":   float(c[1]),
        "high":   float(c[2]),
        "low":    float(c[3]),
        "close":  float(c[4]),
        "volume": float(c[5]),
    } for c in data]

    from db.database import save_prices
    await save_prices(candles, symbol=symbol, timeframe=interval)
    logger.info(f"{len(candles)} mum kaydedildi ({symbol} {interval})")
    return candles


async def get_price_df(symbol: str = BTC_SYMBOL,
                       timeframe: str = "1h",
                       limit: int = 500) -> pd.DataFrame:
    """DB'den fiyat DataFrame'i al, yoksa fetch et."""
    from db.database import get_prices
    rows = await get_prices(symbol=symbol, timeframe=timeframe, limit=limit)

    if len(rows) < 10:
        await fetch_klines(symbol=symbol, interval=timeframe, limit=limit)
        rows = await get_prices(symbol=symbol, timeframe=timeframe, limit=limit)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.set_index("ts").sort_index()
    return df


@with_circuit_breaker("binance_spot", fallback=0.0)
async def get_current_price(symbol: str = BTC_SYMBOL) -> float:
    data = await _get(f"{BINANCE_BASE}/ticker/price", {"symbol": symbol})
    return float(data["price"]) if data else 0.0


# ── FUNDING RATE ─────────────────────────────────────────

@with_circuit_breaker("binance_futures", fallback={"normalized": 0})
async def get_funding_rate(symbol: str = BTC_SYMBOL) -> dict:
    """
    Anlık funding rate + 30 günlük geçmiş.
    Yüksek pozitif → herkes long → kontrarian bearish
    Düşük/negatif → herkes short → kontrarian bullish
    """
    fapi_sym = symbol  # BTCUSDT hem spot hem futures

    cur = await _get(f"{BINANCE_FAPI}/premiumIndex", {"symbol": fapi_sym})
    if not cur:
        return {"normalized": 0}

    current_rate = float(cur.get("lastFundingRate", 0)) * 100

    hist = await _get(f"{BINANCE_FAPI}/fundingRate", {
        "symbol": fapi_sym, "limit": 90
    })
    rates = [float(h["fundingRate"]) * 100 for h in hist] if hist else [current_rate]
    avg   = float(np.mean(rates))

    # Kontrarian normalize: yüksek pozitif → bearish → negatif norm
    # Eşik: ±0.08% aşırı
    if abs(current_rate) > 0.08:
        normalized = float(-np.sign(current_rate) * 0.8)
    else:
        normalized = float(-np.tanh(current_rate / 0.04))

    return {
        "current":    round(current_rate, 5),
        "avg_30d":    round(avg, 5),
        "normalized": round(normalized, 4),
        "extreme":    abs(current_rate) > 0.08,
    }


# ── OPEN INTEREST ────────────────────────────────────────

@with_circuit_breaker("binance_futures", fallback={"normalized": 0})
async def get_open_interest(symbol: str = BTC_SYMBOL) -> dict:
    cur = await _get(f"{BINANCE_FAPI}/openInterest", {"symbol": symbol})
    if not cur:
        return {"normalized": 0}

    oi_now = float(cur["openInterest"])

    hist = await _get(f"{BINANCE_FAPI}/openInterestHist", {
        "symbol": symbol, "period": "1h", "limit": 25
    })
    if not hist or len(hist) < 2:
        return {"current": oi_now, "normalized": 0}

    oi_24h_ago = float(hist[0]["sumOpenInterest"])
    change_pct = (oi_now - oi_24h_ago) / (oi_24h_ago + 1e-9) * 100

    price_now  = await get_current_price(symbol)
    price_hist_data = await _get(f"{BINANCE_BASE}/klines", {
        "symbol": symbol, "interval": "1h", "limit": 25
    })
    price_24h  = float(price_hist_data[0][4]) if price_hist_data else price_now
    price_chg  = (price_now - price_24h) / (price_24h + 1e-9) * 100

    # Yorumlama
    if change_pct > 5 and price_chg > 2:
        normalized = 0.8    # Guclu yukselis trendi
    elif change_pct > 5 and price_chg < -2:
        normalized = -0.4   # Zayif trend
    elif change_pct < -5:
        normalized = -0.5   # Pozisyon kapaniyor
    else:
        normalized = float(np.tanh(change_pct / 10) * 0.5)

    return {
        "current":    oi_now,
        "change_pct": round(change_pct, 2),
        "normalized": round(normalized, 4),
    }


# ── LIKIDASYONLAR ────────────────────────────────────────

@with_circuit_breaker("binance_futures", fallback={"normalized": 0})
async def get_liquidations(symbol: str = BTC_SYMBOL) -> dict:
    """
    Son 24 saatlik likidasyon verisi.
    Yüksek long likidasyon → sert düşüş başlangıcı
    Yüksek short likidasyon → sert yükseliş başlangıcı
    """
    data = await _get(f"{BINANCE_FAPI}/allForceOrders", {
        "symbol": symbol, "limit": 200
    })
    if not data:
        return {"normalized": 0}

    long_liq  = sum(float(o["origQty"]) * float(o["price"])
                    for o in data if o.get("side") == "SELL")
    short_liq = sum(float(o["origQty"]) * float(o["price"])
                    for o in data if o.get("side") == "BUY")
    total     = long_liq + short_liq

    if total < 1e6:  # 1M$ altinda anlamsiz
        return {"normalized": 0, "total_usd": total}

    # Buyuk long likidasyon → potansiyel dip / oversold
    # Buyuk short likidasyon → potansiyel tepe / overbought
    ratio = (short_liq - long_liq) / (total + 1e-9)
    normalized = float(np.tanh(ratio * 3))

    return {
        "long_liq_usd":  round(long_liq / 1e6, 2),
        "short_liq_usd": round(short_liq / 1e6, 2),
        "total_usd":     round(total / 1e6, 2),
        "normalized":    round(normalized, 4),
    }


# ── COINBASE PREMIUM ─────────────────────────────────────

@with_circuit_breaker("coinbase", fallback={"normalized": 0})
async def get_coinbase_premium(symbol: str = "BTC-USD") -> dict:
    """
    Coinbase BTC/USD ile Binance BTC/USDT arasindaki fark.
    Pozitif premium → ABD kurumsal talep → bullish
    """
    cb_price  = await get_current_price("BTCUSDT")  # Binance referans

    # Coinbase API (public)
    cb_data = await _get(
        f"https://api.coinbase.com/v2/prices/{symbol}/spot"
    )
    if not cb_data:
        return {"normalized": 0}

    coinbase_price = float(cb_data.get("data", {}).get("amount", cb_price))
    premium_pct    = (coinbase_price - cb_price) / (cb_price + 1e-9) * 100
    normalized     = float(np.tanh(premium_pct / 0.3))

    return {
        "premium_pct": round(premium_pct, 4),
        "normalized":  round(normalized, 4),
    }


# ── TEKNIK INDIKTORLER ───────────────────────────────────

def compute_technicals(df: pd.DataFrame) -> dict:
    """RSI, MACD, Bollinger Band, trend skoru."""
    if df.empty or len(df) < 30:
        return {"normalized": 0}

    close = df["close"]

    # RSI
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / (loss + 1e-9)
    rsi   = 100 - (100 / (1 + rs))
    rsi_now = float(rsi.iloc[-1])

    # RSI normalize
    if rsi_now < 30:
        rsi_norm = (30 - rsi_now) / 30
    elif rsi_now > 70:
        rsi_norm = -(rsi_now - 70) / 30
    else:
        rsi_norm = (50 - rsi_now) / 50 * 0.2

    # MACD
    ema12  = close.ewm(span=12).mean()
    ema26  = close.ewm(span=26).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    macd_h = float(macd.iloc[-1] - signal.iloc[-1])
    macd_norm = float(np.tanh(macd_h / (close.mean() * 0.005 + 1e-9)))

    # Bollinger
    bb_mid   = close.rolling(20).mean()
    bb_std   = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_pct   = float((close.iloc[-1] - bb_lower.iloc[-1]) /
                     (bb_upper.iloc[-1] - bb_lower.iloc[-1] + 1e-9))
    bb_norm  = float(np.tanh((0.5 - bb_pct) * 2) * 0.5)

    # Trend skoru (EMA50 vs EMA200)
    ema50  = float(close.ewm(span=50).mean().iloc[-1])
    ema200 = float(close.ewm(span=200).mean().iloc[-1]) if len(df) >= 200 else ema50
    trend_score = float(np.tanh((ema50 - ema200) / (ema200 * 0.05 + 1e-9)))

    # Kompozit
    normalized = float(
        rsi_norm * 0.35 +
        macd_norm * 0.30 +
        bb_norm   * 0.20 +
        trend_score * 0.15
    )
    normalized = float(np.clip(normalized, -1.0, 1.0))

    return {
        "rsi":         round(rsi_now, 2),
        "rsi_norm":    round(rsi_norm, 4),
        "macd_norm":   round(macd_norm, 4),
        "bb_pct":      round(bb_pct, 4),
        "trend_score": round(trend_score, 4),
        "normalized":  round(normalized, 4),
    }


def compute_weekly_rsi(df: pd.DataFrame) -> dict:
    """Haftalik RSI — oversold/overbought."""
    if df.empty or len(df) < 14:
        return {"normalized": 0}

    close = df["close"]
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / (loss + 1e-9)
    rsi   = float((100 - 100 / (1 + rs)).iloc[-1])

    if rsi < 30:
        normalized = (30 - rsi) / 30
    elif rsi > 70:
        normalized = -(rsi - 70) / 30
    else:
        normalized = 0.0

    return {
        "rsi":        round(rsi, 2),
        "normalized": round(float(normalized), 4),
    }


def compute_realized_vol(df: pd.DataFrame, window: int = 30) -> dict:
    """30 gunluk gerceklesmiş volatilite."""
    if df.empty or len(df) < window + 1:
        return {"normalized": 0}

    log_ret = np.log(df["close"] / df["close"].shift(1)).dropna()
    rv = float(log_ret.rolling(window).std().iloc[-1] * np.sqrt(365) * 100)

    # Yüksek vol → belirsizlik → hafif negatif
    normalized = float(np.tanh((50 - rv) / 30) * 0.4)

    return {
        "realized_vol": round(rv, 2),
        "normalized":   round(normalized, 4),
        "level": "YUKSEK" if rv > 80 else "ORTA" if rv > 40 else "DUSUK",
    }


def compute_log_log_band(df: pd.DataFrame) -> dict:
    """
    Bitcoin Power Law (Log-Log Regresyon)
    Genesis: 3 Ocak 2009
    """
    if df.empty or len(df) < 50:
        return {"normalized": 0, "band_pct": 50}

    close = df["close"].copy()
    days  = (close.index - BTC_GENESIS).days.values.astype(float)
    days  = np.maximum(days, 1)

    log_d = np.log(days)
    log_p = np.log(close.values)

    valid = np.isfinite(log_d) & np.isfinite(log_p) & (days > 100)
    if valid.sum() < 20:
        return {"normalized": 0, "band_pct": 50}

    b, a = np.polyfit(log_d[valid], log_p[valid], 1)

    today_days = float((pd.Timestamp.now() - BTC_GENESIS).days)
    log_fair   = a + b * np.log(max(today_days, 1))
    fair_price = float(np.exp(log_fair))

    residuals = log_p[valid] - (a + b * log_d[valid])
    std        = float(np.std(residuals))
    upper      = float(np.exp(log_fair + 2 * std))
    lower      = float(np.exp(log_fair - 2 * std))

    current  = float(close.iloc[-1])
    band_pct = float(
        (np.log(current) - np.log(lower)) /
        (np.log(upper) - np.log(lower) + 1e-9) * 100
    )
    band_pct = max(0.0, min(100.0, band_pct))

    # Alt bantta = ucuz = bullish = pozitif norm
    normalized = float(np.tanh((50 - band_pct) / 25))

    return {
        "fair_price": round(fair_price),
        "upper_band": round(upper),
        "lower_band": round(lower),
        "current":    round(current),
        "band_pct":   round(band_pct, 1),
        "normalized": round(normalized, 4),
        "verdict":    "UCUZ" if band_pct < 30 else "PAHALI" if band_pct > 70 else "NORMAL",
    }
