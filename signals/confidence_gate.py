# ============================================================
#  signals/confidence_gate.py
#  Guven filtresi — dusuk kaliteli sinyalleri sustur
# ============================================================

import logging
from config import CONFIDENCE_GATE, THRESHOLDS

logger = logging.getLogger(__name__)


def should_send(result: dict) -> tuple[bool, str]:
    """
    Sinyalin gonderilip gonderilmeyecegini belirle.

    Returns:
        (should_send: bool, reason: str)
    """
    score      = result.get("score", 0)
    confidence = result.get("confidence", 0)
    verdict    = result.get("judge_verdict", "NORMAL")
    n_signals  = result.get("n_signals", 0)
    stale_count= result.get("stale_count", 0)
    vix_danger = result.get("vix_danger", False)

    # Guven esigi
    if confidence < CONFIDENCE_GATE:
        reason = f"Guven dusuk (%{int(confidence*100)} < %{int(CONFIDENCE_GATE*100)})"
        logger.info(f"Sinyal susturuldu: {reason}")
        return False, reason

    # Yeterli sinyal yok
    if n_signals < 3:
        reason = f"Yetersiz sinyal ({n_signals} < 3)"
        logger.info(f"Sinyal susturuldu: {reason}")
        return False, reason

    # Verilerin cogunu stale ise sustur
    if n_signals > 0 and stale_count / n_signals > 0.6:
        reason = f"Veriler eski (%{int(stale_count/n_signals*100)} stale)"
        logger.info(f"Sinyal susturuldu: {reason}")
        return False, reason

    # VIX tehlike + BEKLE sinyali — anlamsiz
    if vix_danger and abs(score) < THRESHOLDS["buy"]:
        reason = "VIX tehlike + zayif sinyal — gonderilmiyor"
        logger.info(f"Sinyal susturuldu: {reason}")
        return False, reason

    # Yuksek belirsizlik + zayif skor
    if verdict == "YUKSEK_BELIRSIZLIK" and abs(score) < THRESHOLDS["strong_buy"]:
        reason = "Yuksek belirsizlik + yetersiz skor"
        logger.info(f"Sinyal susturuldu: {reason}")
        return False, reason

    return True, "OK"


def is_alert_worthy(result: dict, last_alert_score: float = 0.0) -> tuple[bool, str]:
    """
    Anlik uyari gonderilmeli mi?
    Normal 4h sinyalinden ayri, acil uyari icin.
    """
    from config import ALERT_SCORE_MIN, ALERT_CONF_MIN

    score      = result.get("score", 0)
    confidence = result.get("confidence", 0)
    verdict    = result.get("judge_verdict", "NORMAL")

    if abs(score) < ALERT_SCORE_MIN:
        return False, "Skor esigi altinda"

    if confidence < ALERT_CONF_MIN:
        return False, "Guven esigi altinda"

    if verdict in ("YUKSEK_BELIRSIZLIK",):
        return False, "Cok fazla cakisma var"

    # Yön değişimi kontrolü
    if last_alert_score != 0:
        if (score > 0) == (last_alert_score > 0):
            return False, "Ayni yon, tekrar uyari gonderilmiyor"

    return True, "OK"
