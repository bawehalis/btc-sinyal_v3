# ============================================================
#  data/onchain.py
#  Zincir ici + makro indiktorler
#
#  Kaldirildi:
#  - hash_ribbon: proxy guvenilmez, surekli yanlis negatif uretiyordu
#  - exchange_flow: binance buy/sell ratio proxy cok gurultulu
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
            async with s.get(
                url, params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.warning(f"HTTP hatasi {url}: {e}")
    return None


# ── MVRV PROXY ───────────────────────────────────────────

def compute_mvrv_proxy(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 50:
        return {"normalized": 0}
    close      = df["close"]
    realized   = float(close.ewm(span=200).mean().iloc[-1])
    current    = float(close.iloc[-1])
    mvrv_ratio = current / (realized + 1e-9)

    if mvrv_ratio < 1.0:
        normalized = (1.0 - mvrv_ratio) * 1.0
    elif mvrv_ratio > 3.5:
        normalized = -(mvrv_ratio - 3.5) / 2.0
    else:
        normalized = float(np.tanh((1.8 - mvrv_ratio) / 1.2))

    return {
        "ratio":          round(mvrv_ratio, 4),
        "realized_price": round(realized),
        "normalized":     round(float(np.clip(normalized, -1.0, 1.0)), 4),
        "signal": "UCUZ" if mvrv_ratio < 1.2 else "PAHALI" if mvrv_ratio > 3.0 else "NORMAL",
    }


# ── NUPL PROXY ───────────────────────────────────────────

def compute_nupl_proxy(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 60:
        return {"normalized": 0}
    close    = df["close"]
    realized = float(close.ewm(span=155).mean().iloc[-1])
    current  = float(close.iloc[-1])
    nupl     = (current - realized) / (current + 1e-9)

    if nupl < -0.25:
        normalized = 1.0
    elif nupl < 0:
        normalized = float(-nupl / 0.25)
    elif nupl < 0.5:
        normalized = float(0.3 - nupl * 0.6)
    elif nupl < 0.75:
        normalized = float(-0.5 - (nupl - 0.5) * 2)
    else:
        normalized = -1.0

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


# ── MINER REVENUE PROXY ──────────────────────────────────

def compute_miner_revenue(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 30:
        return {"normalized": 0}
    revenue = df["close"] * df["volume"] * 6.25 / 1e6
    rv30 = float(revenue.rolling(30).mean().iloc[-1])
    rv90 = float(revenue.rolling(90).mean().iloc[-1]) if len(df) >= 90 else rv30
    ratio = rv30 / (rv90 + 1e-9)

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


# ── FEAR & GREED ─────────────────────────────────────────

@with_circuit_breaker("alternative_me", fallback={"normalized": 0})
async def get_fear_greed() -> dict:
    data = await _get("https://api.alternative.me/fng/?limit=1")
    if not data:
        return {"normalized": 0}

    value = int(data["data"][0]["value"])
    label = data["data"][0]["value_classification"]

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
    if not FRED_API_KEY:
        return {"normalized": 0, "signal": "API_KEY_YOK"}

    data = await _get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id":  "M2SL",
            "api_key":    FRED_API_KEY,
            "file_type":  "json",
            "limit":      13,
            "sort_order": "desc",
        }
    )
    if not data or "observations" not in data:
        return {"normalized": 0}

    obs = [float(o["value"]) for o in data["observations"] if o["value"] != "."]
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

@with_circuit_breaker("yahoo_dxy", fallback={"normalized": 0})
async def get_dxy_alternative() -> dict:
    try:
        data = await _get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",
            params={"interval": "1d", "range": "5d"}
        )
        # DXY icin ayri cagri
        dxy_data = await _get(
            "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
            params={"interval": "1d", "range": "5d"}
        )
        if not dxy_data:
            return {"normalized": 0}

        closes = dxy_data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if len(closes) < 2:
            return {"normalized": 0}

        current  = closes[-1]
        previous = closes[-2]
        change   = (current - previous) / (previous + 1e-9) * 100
        normalized = float(-np.tanh(change / 1.5))

        return {
            "current":    round(current, 3),
            "change_pct": round(change, 3),
            "normalized": round(normalized, 4),
            "signal":     "GUCLENIYOR" if change > 0 else "ZAYIFLIYOR",
        }
    except Exception as e:
        logger.warning(f"DXY hatasi: {e}")
        return {"normalized": 0}


# ── VIX ──────────────────────────────────────────────────

@with_circuit_breaker("yahoo_vix", fallback={"normalized": 0, "danger": False})
async def get_vix() -> dict:
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

        if current > 40:
            normalized = 0.5
            risk_mult  = 0.4
        elif current > 30:
            normalized = 0.2
            risk_mult  = 0.6
        elif current > 20:
            normalized = 0.0
            risk_mult  = 0.85
        else:
            normalized = 0.1
            risk_mult  = 1.0

        return {
            "current":         round(current, 2),
            "danger":          danger,
            "normalized":      round(normalized, 4),
            "risk_multiplier": risk_mult,
        }
    except Exception as e:
        logger.warning(f"VIX hatasi: {e}")
        return {"normalized": 0, "danger": False, "risk_multiplier": 1.0}


# ── WHALE ALERT ──────────────────────────────────────────

@with_circuit_breaker("whale_alert", fallback={"normalized": 0})
async def get_whale_alert() -> dict:
    if not WHALE_ALERT_KEY:
        return {"normalized": 0, "signal": "API_KEY_YOK"}

    data = await _get(
        "https://api.whale-alert.io/v1/transactions",
        params={
            "api_key":   WHALE_ALERT_KEY,
            "min_value": 1_000_000,
            "currency":  "btc",
            "limit":     20,
        }
    )
    if not data or "transactions" not in data:
        return {"normalized": 0}

    exchange_in  = 0.0
    exchange_out = 0.0

    for tx in data["transactions"]:
        usd     = float(tx.get("amount_usd", 0))
        to_ex   = tx.get("to",   {}).get("owner_type") == "exchange"
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


# ── ALTCOIN DOMINANSI ────────────────────────────────────

@with_circuit_breaker("coingecko", fallback={"normalized": 0})
async def get_altcoin_dominance() -> dict:
    data = await _get("https://api.coingecko.com/api/v3/global")
    if not data:
        return {"normalized": 0}

    btc_dom = float(
        data.get("data", {})
            .get("market_cap_percentage", {})
            .get("btc", 50)
    )
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
