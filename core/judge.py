# ============================================================
#  core/judge.py
#  Basyargic — Katman bazli cakisma analizi
# ============================================================

import logging
import numpy as np
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── KATMAN TANIMLARI ─────────────────────────────────────
# hash_ribbon: proxy guvenilmez, ZINCIR katmanindan kaldirildi
# exchange_flow: proxy guvenilmez, ZINCIR katmanindan kaldirildi
SIGNAL_LAYERS = {
    "DEGER":    ["log_log_band", "mvrv", "nupl"],
    "ZINCIR":   ["miner_revenue", "whale_alert"],
    "KALDIRAC": ["funding_rate", "open_interest", "liquidations", "coinbase_premium"],
    "MAKRO":    ["m2", "dxy", "vix", "fear_greed"],
    "TEKNIK":   ["weekly_rsi", "technicals", "realized_vol", "altcoin_dominance"],
}

_IND_TO_LAYER = {
    ind: layer
    for layer, inds in SIGNAL_LAYERS.items()
    for ind in inds
}

CRITICAL_LAYERS = {"DEGER", "MAKRO"}

LAYER_WEIGHTS = {
    "DEGER":    1.4,
    "ZINCIR":   1.0,
    "KALDIRAC": 1.0,
    "MAKRO":    1.2,
    "TEKNIK":   0.9,
}

LAYER_TR = {
    "DEGER":    "Deger",
    "ZINCIR":   "Zincir Ustu",
    "KALDIRAC": "Kaldirac",
    "MAKRO":    "Makro",
    "TEKNIK":   "Teknik",
}


@dataclass
class JudgeVerdict:
    verdict:           str
    verdict_label:     str
    verdict_emoji:     str
    confidence_adj:    float
    confidence_penalty:float
    score_adj:         float
    layer_scores:      dict = field(default_factory=dict)
    bullish_layers:    list = field(default_factory=list)
    bearish_layers:    list = field(default_factory=list)
    conflict_count:    int  = 0
    reasoning:         str  = ""
    action_hint:       str  = ""


def judge(detail: dict, raw_score: float, base_confidence: float) -> JudgeVerdict:
    if not detail:
        return _neutral_verdict(raw_score, base_confidence)

    # ── 1. Katman skorlari ───────────────────────────────
    layer_signals: dict[str, list] = {k: [] for k in SIGNAL_LAYERS}

    for ind_name, ind_data in detail.items():
        norm = ind_data.get("normalized", 0)
        if norm == 0 or ind_data.get("_stale"):
            continue
        layer = _IND_TO_LAYER.get(ind_name)
        if layer:
            layer_signals[layer].append(norm)

    layer_scores = {}
    for layer, sigs in layer_signals.items():
        if len(sigs) >= 1:
            layer_scores[layer] = float(np.mean(sigs))

    # ── 2. Cakisma tespiti ───────────────────────────────
    # Esik 0.25 — cok hassas cakisma tespitini onlemek icin
    bullish = [l for l, s in layer_scores.items() if s > 0.25]
    bearish = [l for l, s in layer_scores.items() if s < -0.25]
    conflict_count = min(len(bullish), len(bearish))

    critical_conflict = bool(
        set(bullish) & CRITICAL_LAYERS and
        set(bearish) & CRITICAL_LAYERS
    )

    # ── 3. Agirlikli katman konsensus skoru ──────────────
    w_sum = 0.0
    w_tot = 0.0
    for layer, score in layer_scores.items():
        w = LAYER_WEIGHTS.get(layer, 1.0)
        w_sum += score * w
        w_tot += w
    layer_consensus = w_sum / w_tot if w_tot > 0 else 0

    # ── 4. Guven ve skor duzeltmesi ──────────────────────
    if conflict_count == 0:
        conf_adj  = 1.00
        conf_pen  = 0.00
        score_adj = 1.00
    elif conflict_count == 1:
        conf_adj  = 0.85
        conf_pen  = 0.15
        score_adj = 0.95
    elif conflict_count == 2:
        conf_adj  = 0.65
        conf_pen  = 0.35
        score_adj = 0.80
    else:
        conf_adj  = 0.45
        conf_pen  = 0.55
        score_adj = 0.60

    # Sadece kritik katman cakismasi varsa ek ceza
    if critical_conflict and conflict_count >= 2:
        conf_adj  = max(conf_adj  - 0.10, 0.25)
        conf_pen  = min(conf_pen  + 0.10, 0.70)
        score_adj = max(score_adj - 0.10, 0.50)

    # ── 5. Karar kategorisi ──────────────────────────────
    abs_score = abs(layer_consensus)

    if conflict_count == 0 and abs_score > 0.30:
        verdict       = "YUKSEK_KONSENSUS"
        verdict_label = "Yuksek Konsensus"
        verdict_emoji = "✅"
        reasoning     = "Tum katmanlar ayni yonu gosteriyor"
        action_hint   = "Sinyale guvenilir"

    elif conflict_count >= 3 or (conflict_count >= 2 and critical_conflict):
        verdict       = "YUKSEK_BELIRSIZLIK"
        verdict_label = "Yuksek Belirsizlik"
        verdict_emoji = "🚫"
        reasoning     = (
            f"Ciddi cakisma: "
            f"{_names(bullish)} yukselis, "
            f"{_names(bearish)} dusus diyeniyor"
        )
        action_hint   = "Net yon olusana kadar pozisyon alinmamali"

    elif conflict_count == 2:
        verdict       = "CIDDI_CAKISMA"
        verdict_label = "Ciddi Cakisma"
        verdict_emoji = "⚠️"
        reasoning     = (
            f"{_names(bullish)} yukselis vs "
            f"{_names(bearish)} dusus"
        )
        action_hint   = "Kucuk pozisyon veya bekleme"

    elif conflict_count == 1:
        verdict       = "HAFIF_CAKISMA"
        verdict_label = "Hafif Cakisma"
        verdict_emoji = "🔷"
        reasoning     = (
            f"Cogunluk uzlasiyor, "
            f"{_names(bearish if raw_score > 0 else bullish)} farkli yonde"
        )
        action_hint   = "Dikkatli ilerlenilebilir"

    else:
        verdict       = "NORMAL"
        verdict_label = "Normal"
        verdict_emoji = "➡️"
        reasoning     = "Katmanlar genel olarak uyumlu"
        action_hint   = "Normal takip"

    return JudgeVerdict(
        verdict            = verdict,
        verdict_label      = verdict_label,
        verdict_emoji      = verdict_emoji,
        confidence_adj     = round(conf_adj, 3),
        confidence_penalty = round(conf_pen, 3),
        score_adj          = round(score_adj, 3),
        layer_scores       = {k: round(v, 3) for k, v in layer_scores.items()},
        bullish_layers     = bullish,
        bearish_layers     = bearish,
        conflict_count     = conflict_count,
        reasoning          = reasoning,
        action_hint        = action_hint,
    )


def _names(layers: list) -> str:
    return ", ".join(LAYER_TR.get(l, l) for l in layers) if layers else "yok"


def _neutral_verdict(score: float, conf: float) -> JudgeVerdict:
    return JudgeVerdict(
        verdict            = "NORMAL",
        verdict_label      = "Veri Yetersiz",
        verdict_emoji      = "➡️",
        confidence_adj     = 1.0,
        confidence_penalty = 0.0,
        score_adj          = 1.0,
        reasoning          = "Yeterli indiktor yok",
        action_hint        = "Veri beklenmeli",
    )
