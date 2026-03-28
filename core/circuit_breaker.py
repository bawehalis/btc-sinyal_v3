# ============================================================
#  core/circuit_breaker.py
#  API hata yonetimi — devre kesici deseni
# ============================================================

import time
import logging
from functools import wraps
from config import CIRCUIT_BREAKER as CB_CFG

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    Bir API kaynagi icin devre kesici.

    Durumlar:
      CLOSED   — Normal calisma
      OPEN     — Hata esigi asildi, istekler reddediliyor
      HALF_OPEN — Test istegi gonderiliyor
    """
    CLOSED    = "CLOSED"
    OPEN      = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, name: str):
        self.name         = name
        self.state        = self.CLOSED
        self.failures     = 0
        self.last_failure = 0.0
        self.last_success = 0.0
        self._max_failures    = CB_CFG["max_failures"]
        self._cooldown        = CB_CFG["cooldown_sec"]
        self._half_open_after = CB_CFG["half_open_after"]

    def can_call(self) -> bool:
        now = time.time()
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if now - self.last_failure >= self._half_open_after:
                self.state = self.HALF_OPEN
                logger.info(f"[CB:{self.name}] Yari acik — test istegi")
                return True
            return False
        if self.state == self.HALF_OPEN:
            return True
        return False

    def on_success(self):
        self.failures     = 0
        self.last_success = time.time()
        if self.state != self.CLOSED:
            logger.info(f"[CB:{self.name}] Devre kapandi — normal calismaya dondu")
        self.state = self.CLOSED

    def on_failure(self, exc: Exception):
        self.failures    += 1
        self.last_failure = time.time()
        if self.failures >= self._max_failures:
            self.state = self.OPEN
            logger.warning(
                f"[CB:{self.name}] Devre ACIK — "
                f"{self.failures} ardisik hata. "
                f"{self._cooldown}s bekleniyor. Son hata: {exc}"
            )
        elif self.state == self.HALF_OPEN:
            self.state = self.OPEN
            logger.warning(f"[CB:{self.name}] Yari acik test basarisiz, devre tekrar acildi")

    @property
    def is_open(self) -> bool:
        return self.state == self.OPEN

    def status(self) -> dict:
        return {
            "name":         self.name,
            "state":        self.state,
            "failures":     self.failures,
            "last_failure": self.last_failure,
        }


# ── GLOBAL DEVRE KESICILER ───────────────────────────────

_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name)
    return _breakers[name]


def all_statuses() -> list:
    return [b.status() for b in _breakers.values()]


# ── DECORATOR ────────────────────────────────────────────

def with_circuit_breaker(source_name: str, fallback=None):
    """
    Kullanim:
        @with_circuit_breaker("binance")
        async def fetch_price():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            breaker = get_breaker(source_name)
            if not breaker.can_call():
                logger.debug(f"[CB:{source_name}] Devre acik, istek reddedildi")
                return fallback
            try:
                result = await func(*args, **kwargs)
                breaker.on_success()
                return result
            except Exception as e:
                breaker.on_failure(e)
                return fallback
        return wrapper
    return decorator
