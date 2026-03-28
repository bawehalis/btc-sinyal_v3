# ============================================================
#  config.py
#  Merkezi konfigurasyon — agirliklar, esikler, API ayarlari
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()

# ── TELEGRAM ─────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── API ANAHTARLARI ──────────────────────────────────────
FRED_API_KEY       = os.getenv("FRED_API_KEY", "")
WHALE_ALERT_KEY    = os.getenv("WHALE_ALERT_KEY", "")
GLASSNODE_KEY      = os.getenv("GLASSNODE_KEY", "")

# ── BINANCE ──────────────────────────────────────────────
BINANCE_BASE  = "https://api.binance.com/api/v3"
BINANCE_FAPI  = "https://fapi.binance.com/fapi/v1"
BTC_SYMBOL    = "BTCUSDT"

# ── VERITABANI ───────────────────────────────────────────
DB_PATH = "db/btc_signal.db"

# ── SINYAL AYARLARI ──────────────────────────────────────
CONFIDENCE_GATE = 0.30       # Bu altinda sinyal gonderilmez
ALERT_SCORE_MIN = 0.65       # Bu skoru gecince anlik uyari
ALERT_CONF_MIN  = 0.55       # Anlik uyari icin minimum guven
ALERT_COOLDOWN_H = 6         # Ayni yon icin tekrar uyari bekleme

# ── SINYAL ETIKET ESIKLERI ───────────────────────────────
THRESHOLDS = {
    "strong_buy":  0.60,
    "buy":         0.30,
    "neutral_low": -0.30,
    "sell":        -0.60,
}

# ── 20 INDIKTOR AGIRLIK TABLOSU (toplam = 1.00) ──────────
BASE_WEIGHTS = {
    # Uzun vadeli degerleme
    "log_log_band":     0.08,
    "mvrv":             0.07,
    "nupl":             0.05,
    "hash_ribbon":      0.06,
    # Makro & Risk
    "m2":               0.06,
    "dxy":              0.05,
    "vix":              0.05,
    "fear_greed":       0.05,
    # Piyasa yapisi & Kaldirac
    "funding_rate":     0.08,
    "open_interest":    0.05,
    "liquidations":     0.07,
    "exchange_flow":    0.05,
    # Zincir ici aktivite
    "miner_revenue":    0.05,
    "whale_alert":      0.04,
    # Teknik & Momentum
    "weekly_rsi":       0.04,
    "technicals":       0.05,
    "realized_vol":     0.03,
    # Premium & Dominans
    "coinbase_premium": 0.04,
    "altcoin_dominance":0.03,
}

# Toplam kontrol
assert abs(sum(BASE_WEIGHTS.values()) - 1.0) < 1e-9, \
    f"Agirlik toplami 1.0 olmali: {sum(BASE_WEIGHTS.values())}"

# ── ZAMAN DILIMINE GORE AKTIF INDIKTORLER ────────────────
TIMEFRAME_ACTIVE = {
    "4h": {
        "log_log_band", "technicals", "realized_vol",
        "funding_rate", "open_interest", "coinbase_premium",
        "whale_alert", "liquidations", "exchange_flow",
        "fear_greed", "vix",
    },
    "1d": {
        "log_log_band", "weekly_rsi", "technicals", "realized_vol",
        "funding_rate", "open_interest", "coinbase_premium",
        "whale_alert", "liquidations", "exchange_flow",
        "mvrv", "nupl", "fear_greed", "m2", "dxy", "vix",
        "miner_revenue", "altcoin_dominance",
    },
    "1w": {
        "log_log_band", "weekly_rsi", "mvrv", "nupl",
        "hash_ribbon", "m2", "dxy", "vix", "fear_greed",
        "miner_revenue", "altcoin_dominance",
    },
    "1M": {
        "log_log_band", "mvrv", "nupl",
        "hash_ribbon", "m2", "dxy", "vix", "fear_greed",
    },
}

# ── REJIM TANIMLARI ──────────────────────────────────────
REGIMES = {
    "accumulation": {
        "label":      "Birikim Fazi",
        "emoji":      "🟤",
        "multipliers": {
            "log_log_band": 1.4, "mvrv": 1.3, "nupl": 1.3,
            "hash_ribbon":  1.2, "fear_greed": 1.2,
            "funding_rate": 0.8, "liquidations": 0.8,
        },
    },
    "early_bull": {
        "label":      "Erken Boga",
        "emoji":      "🟢",
        "multipliers": {
            "hash_ribbon":  1.3, "mvrv": 1.2,
            "technicals":   1.2, "funding_rate": 1.1,
            "exchange_flow":1.2,
        },
    },
    "mid_bull": {
        "label":      "Orta Boga",
        "emoji":      "🚀",
        "multipliers": {
            "funding_rate":  1.3, "open_interest": 1.2,
            "liquidations":  1.3, "coinbase_premium": 1.2,
            "fear_greed":    1.2,
        },
    },
    "late_bull": {
        "label":      "Gec Boga",
        "emoji":      "⚠️",
        "multipliers": {
            "nupl":          1.4, "fear_greed": 1.3,
            "mvrv":          1.3, "altcoin_dominance": 1.2,
            "funding_rate":  0.7,
        },
    },
    "bear": {
        "label":      "Aya Pazari",
        "emoji":      "🔴",
        "multipliers": {
            "log_log_band": 1.3, "mvrv": 1.2,
            "hash_ribbon":  1.2, "m2": 1.2,
            "funding_rate": 0.8,
        },
    },
    "high_volatility": {
        "label":      "Yuksek Volatilite",
        "emoji":      "⚡",
        "multipliers": {
            "vix":          1.4, "realized_vol": 1.3,
            "liquidations": 1.4, "fear_greed": 1.2,
            "funding_rate": 0.7,
        },
    },
}

# ── VERI YASLANMA SURELERI (saniye) ──────────────────────
# Indiktorun guncellenme periyodunun 2 kati
INDICATOR_MAX_AGE = {
    "funding_rate":     8  * 3600,    # 8s guncelleme → 16s max
    "open_interest":    1  * 3600,    # 1s guncelleme → 2s max
    "liquidations":     1  * 3600,
    "exchange_flow":    4  * 3600,
    "whale_alert":      4  * 3600,
    "coinbase_premium": 1  * 3600,
    "technicals":       4  * 3600,
    "realized_vol":     24 * 3600,
    "log_log_band":     24 * 3600,
    "weekly_rsi":       24 * 3600,
    "mvrv":             24 * 3600,
    "nupl":             24 * 3600,
    "hash_ribbon":      7  * 24 * 3600,
    "miner_revenue":    24 * 3600,
    "fear_greed":       24 * 3600,
    "altcoin_dominance":4  * 3600,
    "m2":               30 * 24 * 3600,
    "dxy":              24 * 3600,
    "vix":              24 * 3600,
}

# ── CIRCUIT BREAKER AYARLARI ─────────────────────────────
CIRCUIT_BREAKER = {
    "max_failures":    3,       # Kac ardisik hatada devre aciyor
    "cooldown_sec":    300,     # Devre acikken bekleme suresi (5dk)
    "half_open_after": 60,      # 1dk sonra yari acik test
}

# ── ZAMANLAYICI ──────────────────────────────────────────
SCHEDULE = {
    "4h":      {"type": "interval", "hours": 4},
    "1d":      {"type": "cron",     "hour": 8,  "minute": 0},
    "1w":      {"type": "cron",     "day_of_week": "mon", "hour": 9, "minute": 0},
    "1M":      {"type": "cron",     "day": 1,   "hour": 10, "minute": 0},
}
