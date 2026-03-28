# ============================================================
#  core/weights.py
#  Dinamik agirlik hesaplama
# ============================================================

import logging
from config import BASE_WEIGHTS, TIMEFRAME_ACTIVE

logger = logging.getLogger(__name__)


def get_weights(timeframe: str,
                regime_multipliers: dict,
                active_override: set = None) -> dict:
    """
    Zaman dilimi ve rejime gore normalize edilmis agirliklar.

    1. Sadece aktif indiktorleri al
    2. Rejim carpanlarini uygula
    3. Toplam = 1.0 olacak sekilde normalize et
    """
    active_set = active_override or TIMEFRAME_ACTIVE.get(timeframe, set(BASE_WEIGHTS.keys()))

    raw = {}
    for name in active_set:
        base_w = BASE_WEIGHTS.get(name)
        if base_w is None:
            continue
        mult   = regime_multipliers.get(name, 1.0)
        raw[name] = base_w * mult

    # Normalize
    total = sum(raw.values())
    if total == 0:
        logger.warning(f"Agirlik toplami 0 — {timeframe} icin bos donuyor")
        return {}

    normalized = {k: round(v / total, 6) for k, v in raw.items()}

    logger.debug(
        f"Agirliklar [{timeframe}]: {len(normalized)} indiktor, "
        f"toplam={sum(normalized.values()):.4f}"
    )
    return normalized
