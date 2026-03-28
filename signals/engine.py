# ============================================================
#  signals/engine.py
#  Sinyal motoru — Judge entegreli, temiz mimari
# ============================================================

import logging
import numpy as np
from datetime import datetime
from config import THRESHOLDS, TIMEFRAME_ACTIVE
from core.weights import get_weights
from core.regime import detect_regime
from core.judge import judge

logger = logging.getLogger(__name__)

# Ayni kategorideki indiktorler (korelasyon cezasi)
CORR_GROUPS = [
    ["funding_rate", "open_interest", "liquidations"],
    ["log_log_band", "mvrv", "nupl"],
    ["whale_alert",  "exchange_flow"],
    ["dxy",          "m2"],
    ["mvrv",         "weekly_rsi"],
]


def _apply_correlation_penalty(components: dict) -> dict:
    """Ayni grupta hepsi ayni yonde → %30 ceza."""
    adjusted = {k: dict(v) for k, v in components.items()}
    for group in CORR_GROUPS:
        present = [k for k in group if k in adjusted]
        if len(present) < 2:
            continue
        vals  = [adjusted[k]["normalized"] for k in present]
        signs = [np.sign(v) for v in vals if abs(v) > 0.01]
        if len(signs) >= 2 and all(s == signs[0] for s in signs):
            for k in present:
                adjusted[k].setdefault("_corr_penalty", 0.70)
    return adjusted


def score_to_label(score: float) -> str:
    t = THRESHOLDS
    if score >= t["strong_buy"]:  return "GUCLU AL"
    if score >= t["buy"]:         return "TEMKINLI AL"
    if score > t["neutral_low"]:  return "BEKLE"
    if score > t["sell"]:         return "DIKKAT"
    return "GUCLU KACIN"


def compute_signal(indicators: dict,
                   price_df,
                   timeframe: str = "4h") -> dict:
    """
    Ana sinyal hesaplama fonksiyonu.

    Akis:
    1. Rejim tespiti
    2. Agirlik hesabi (rejim + zaman dilimi)
    3. Aktif indiktorleri filtrele
    4. Korelasyon cezasi uygula
    5. Agirlikli skor hesapla
    6. VIX risk filtresi
    7. Judge — katman bazli cakisma analizi
    8. Guven skoru
    9. Final karar
    """
    # ── 1. Rejim ─────────────────────────────────────────
    regime = detect_regime(indicators, price_df)

    # ── 2. Agirliklar ────────────────────────────────────
    weights = get_weights(
        timeframe=timeframe,
        regime_multipliers=regime.multipliers,
    )
    if not weights:
        return _empty(timeframe, regime)

    # ── 3. Aktif indiktorleri topla ──────────────────────
    active_set   = TIMEFRAME_ACTIVE.get(timeframe, set(weights.keys()))
    components_raw = {}

    for name in active_set:
        if name not in weights:
            continue
        ind = indicators.get(name)
        if not ind:
            continue
        norm = ind.get("normalized", 0)
        if not np.isfinite(norm):
            norm = 0.0
        components_raw[name] = {
            "normalized": float(norm),
            "raw":        ind,
        }

    # ── 4. Korelasyon cezasi ─────────────────────────────
    components = _apply_correlation_penalty(components_raw)

    # ── 5. Agirlikli skor ────────────────────────────────
    total_w  = 0.0
    weighted = 0.0
    detail   = {}

    for name, comp in components.items():
        norm    = comp["normalized"]
        base_w  = weights.get(name, 0)
        penalty = comp.get("_corr_penalty", 1.0)
        w       = base_w * penalty

        # Funding rate kontrarian: asiri pozitif/negatif dondur
        if name == "funding_rate":
            if comp["raw"].get("extreme", False):
                norm = -norm * 0.7
                logger.debug(f"Funding rate kontrarian devreye girdi")

        weighted += norm * w
        total_w  += w

        detail[name] = {
            "normalized":    round(norm, 4),
            "weight":        round(w, 4),
            "contribution":  round(norm * w, 5),
            "corr_penalty":  penalty,
            "stale":         bool(comp["raw"].get("_stale", False)),
            "error":         bool(comp["raw"].get("_error", False)),
        }

    if total_w == 0:
        return _empty(timeframe, regime)

    raw_score = weighted / total_w

    # ── 6. VIX risk filtresi ─────────────────────────────
    vix_data  = indicators.get("vix", {})
    risk_mult = vix_data.get("risk_multiplier", 1.0)
    vix_danger= vix_data.get("danger", False)

    score_after_vix = raw_score * risk_mult

    # ── 7. Rejim guven duzeltmesi ────────────────────────
    regime_pull  = 1.0 - (1.0 - regime.confidence) * 0.2
    score_after_regime = score_after_vix * regime_pull

    # ── 8. Temel guven skoru ─────────────────────────────
    n_signals   = len(detail)
    stale_count = sum(1 for v in detail.values() if v["stale"])
    error_count = sum(1 for v in detail.values() if v["error"])

    agreement = (
        np.mean([
            1 if v["normalized"] * score_after_regime > 0 else 0
            for v in detail.values() if abs(v["normalized"]) > 0.01
        ]) if detail else 0.5
    )

    base_confidence = float(
        agreement
        * min(n_signals / 10, 1.0)
        * (1 - (stale_count + error_count) / max(n_signals, 1) * 0.4)
        * regime.confidence
    )
    base_confidence = float(np.clip(base_confidence, 0.0, 0.95))

    # ── 9. JUDGE — katman bazli cakisma analizi ──────────
    verdict = judge(detail, score_after_regime, base_confidence)

    # Judge sonucunu uygula
    final_confidence = float(np.clip(
        base_confidence * verdict.confidence_adj, 0.0, 0.95
    ))

    # Ciddi cakismada skoru merkeze cek
    if verdict.verdict in ("YUKSEK_BELIRSIZLIK", "CIDDI_CAKISMA"):
        final_score = float(np.clip(
            score_after_regime * verdict.score_adj, -1.0, 1.0
        ))
    else:
        final_score = float(np.clip(score_after_regime, -1.0, 1.0))

    # ── 10. Etiket ve Top5 ───────────────────────────────
    label = score_to_label(final_score)

    top5 = sorted(
        detail.items(),
        key=lambda x: abs(x[1]["contribution"]),
        reverse=True
    )[:5]

    return {
        # Temel
        "score":             round(final_score, 4),
        "raw_score":         round(raw_score, 4),
        "label":             label,
        "confidence":        round(final_confidence, 3),
        "base_confidence":   round(base_confidence, 3),
        "timeframe":         timeframe,
        "ts":                int(datetime.now().timestamp() * 1000),

        # Rejim
        "regime":            regime.regime,
        "regime_label":      regime.label,
        "regime_emoji":      regime.emoji,
        "regime_conf":       regime.confidence,

        # Judge
        "judge_verdict":     verdict.verdict,
        "judge_label":       verdict.verdict_label,
        "judge_emoji":       verdict.verdict_emoji,
        "judge_conflict":    verdict.conflict_count,
        "judge_bullish":     verdict.bullish_layers,
        "judge_bearish":     verdict.bearish_layers,
        "judge_reasoning":   verdict.reasoning,
        "judge_hint":        verdict.action_hint,
        "judge_penalty":     verdict.confidence_penalty,
        "layer_scores":      verdict.layer_scores,

        # Risk
        "vix_danger":        vix_danger,
        "n_signals":         n_signals,
        "stale_count":       stale_count,
        "error_count":       error_count,

        # Detay
        "top5": [{
            "name":         k,
            "contribution": round(v["contribution"], 4),
            "normalized":   v["normalized"],
            "stale":        v["stale"],
        } for k, v in top5],
        "detail": detail,
    }


def _empty(timeframe: str, regime) -> dict:
    return {
        "score": 0.0, "raw_score": 0.0,
        "label": "BEKLE", "confidence": 0.0,
        "base_confidence": 0.0, "timeframe": timeframe,
        "ts": int(datetime.now().timestamp() * 1000),
        "regime": regime.regime, "regime_label": regime.label,
        "regime_emoji": regime.emoji, "regime_conf": 0.0,
        "judge_verdict": "NORMAL", "judge_label": "Veri Yetersiz",
        "judge_emoji": "", "judge_conflict": 0,
        "judge_bullish": [], "judge_bearish": [],
        "judge_reasoning": "Yeterli veri yok",
        "judge_hint": "Veri beklenmeli",
        "judge_penalty": 0.0, "layer_scores": {},
        "vix_danger": False, "n_signals": 0,
        "stale_count": 0, "error_count": 0,
        "top5": [], "detail": {},
        "error": "Yeterli veri yok",
    }
