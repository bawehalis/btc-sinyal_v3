# ============================================================
#  core/regime.py
#  Piyasa rejimi tespiti — 6 rejim
# ============================================================

import logging
import numpy as np
from dataclasses import dataclass, field
from config import REGIMES

logger = logging.getLogger(__name__)


@dataclass
class RegimeState:
    regime:      str
    label:       str
    emoji:       str
    confidence:  float
    multipliers: dict = field(default_factory=dict)


def detect_regime(indicators: dict, price_df=None) -> RegimeState:
    """
    Mevcut piyasa rejimini tespit et.

    Girdi: DataBus'tan gelen indiktor sozlugu
    Cikti: RegimeState (rejim, etiket, guven, carpanlar)
    """
    scores = {r: 0.0 for r in REGIMES}

    # ── MVRV ─────────────────────────────────────────────
    mvrv = indicators.get("mvrv", {})
    mvrv_n = mvrv.get("normalized", 0)
    if mvrv_n > 0.6:
        scores["accumulation"] += 2.0
    elif mvrv_n > 0.2:
        scores["early_bull"]   += 1.5
    elif mvrv_n > -0.2:
        scores["mid_bull"]     += 1.0
    elif mvrv_n < -0.5:
        scores["late_bull"]    += 1.5
    else:
        scores["bear"]         += 1.0

    # ── NUPL ─────────────────────────────────────────────
    nupl = indicators.get("nupl", {})
    nupl_n = nupl.get("normalized", 0)
    if nupl_n > 0.5:
        scores["accumulation"] += 1.5
    elif nupl_n > 0.1:
        scores["early_bull"]   += 1.0
    elif nupl_n < -0.4:
        scores["late_bull"]    += 1.5
    else:
        scores["mid_bull"]     += 0.5

    # ── HASH RIBBON ──────────────────────────────────────
    hr = indicators.get("hash_ribbon", {})
    hr_n = hr.get("normalized", 0)
    if hr_n > 0.7:
        scores["early_bull"]   += 2.0
    elif hr_n > 0.3:
        scores["mid_bull"]     += 1.0
    elif hr_n < -0.3:
        scores["accumulation"] += 1.5
        scores["bear"]         += 1.0

    # ── FEAR & GREED ─────────────────────────────────────
    fg = indicators.get("fear_greed", {})
    fg_n = fg.get("normalized", 0)
    if fg_n > 0.6:
        scores["accumulation"] += 1.5   # Asiri korku = dip
    elif fg_n > 0.2:
        scores["early_bull"]   += 1.0
    elif fg_n < -0.5:
        scores["late_bull"]    += 1.5   # Asiri acgozluluk = tepe
    else:
        scores["mid_bull"]     += 0.5

    # ── VIX ──────────────────────────────────────────────
    vix = indicators.get("vix", {})
    vix_n = vix.get("normalized", 0)
    danger = vix.get("danger", False)
    if danger or vix_n < -0.5:
        scores["high_volatility"] += 3.0

    # ── REALIZED VOL ─────────────────────────────────────
    rv = indicators.get("realized_vol", {})
    rv_n = rv.get("normalized", 0)
    if rv_n < -0.4:
        scores["high_volatility"] += 1.5

    # ── FUNDING RATE ─────────────────────────────────────
    fr = indicators.get("funding_rate", {})
    fr_n = fr.get("normalized", 0)
    if fr_n < -0.5:
        scores["late_bull"]    += 1.0   # Asiri pozitif funding = gec boga
    elif fr_n > 0.5:
        scores["accumulation"] += 0.5   # Negatif funding = dip

    # ── TEKNIK TREND ─────────────────────────────────────
    tech = indicators.get("technicals", {})
    trend_score = tech.get("trend_score", 0)
    if isinstance(trend_score, (int, float)):
        if trend_score > 0.5:
            scores["mid_bull"]  += 1.0
            scores["early_bull"]+= 0.5
        elif trend_score < -0.5:
            scores["bear"]      += 1.5

    # ── FIYAT BANDI KONUMU ───────────────────────────────
    llb = indicators.get("log_log_band", {})
    band_pct = llb.get("band_pct", 50)
    if isinstance(band_pct, (int, float)):
        if band_pct < 20:
            scores["accumulation"] += 2.0
            scores["bear"]         += 1.0
        elif band_pct < 40:
            scores["early_bull"]   += 1.0
        elif band_pct > 80:
            scores["late_bull"]    += 2.0
        elif band_pct > 60:
            scores["mid_bull"]     += 1.0

    # ── KAZANAN REJIMi SEC ───────────────────────────────
    total = sum(scores.values()) or 1.0
    best_regime  = max(scores, key=scores.get)
    best_score   = scores[best_regime]
    confidence   = min(best_score / total * 2, 0.95)

    # Histerezis: guven cok dusukse NORMAL'a don
    if confidence < 0.25:
        best_regime = "accumulation"
        confidence  = 0.25

    regime_cfg = REGIMES[best_regime]

    logger.debug(
        f"Rejim: {best_regime} (guven: {confidence:.0%}) | "
        f"Skorlar: { {k: round(v,1) for k,v in scores.items()} }"
    )

    return RegimeState(
        regime      = best_regime,
        label       = regime_cfg["label"],
        emoji       = regime_cfg["emoji"],
        confidence  = round(confidence, 3),
        multipliers = regime_cfg["multipliers"],
    )
