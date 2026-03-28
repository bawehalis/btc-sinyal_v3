# ============================================================
#  core/data_bus.py
#  Merkezi veri yoneticisi
#
#  Ozellikler:
#  - Her indikatör icin dinamik stale suresi
#  - Bot restart'ta SQLite'dan yukle
#  - Thread-safe (asyncio.Lock)
#  - Hata durumunu ayri tut, son gecerli veriyi koru
# ============================================================

import asyncio
import logging
import time
from typing import Any, Optional
from config import INDICATOR_MAX_AGE

logger = logging.getLogger(__name__)


class IndicatorEntry:
    __slots__ = ("data", "updated_at", "source", "is_error", "error_msg")

    def __init__(self, data: Any, updated_at: float,
                 source: str = "", is_error: bool = False,
                 error_msg: str = ""):
        self.data       = data
        self.updated_at = updated_at
        self.source     = source
        self.is_error   = is_error
        self.error_msg  = error_msg

    def is_stale(self, name: str) -> bool:
        max_age = INDICATOR_MAX_AGE.get(name, 4 * 3600)
        return (time.time() - self.updated_at) > max_age

    def age_seconds(self) -> float:
        return time.time() - self.updated_at


class DataBus:
    def __init__(self):
        self._store: dict[str, IndicatorEntry] = {}
        self._lock  = asyncio.Lock()

    # ── YAZMA ────────────────────────────────────────────

    async def set(self, name: str, data: Any,
                  source: str = "") -> None:
        async with self._lock:
            self._store[name] = IndicatorEntry(
                data=data,
                updated_at=time.time(),
                source=source,
                is_error=False,
            )

    async def set_error(self, name: str, error_msg: str) -> None:
        """
        Hata durumunda son gecerli veriyi koru,
        ancak is_error=True olarak isaretle.
        """
        async with self._lock:
            existing = self._store.get(name)
            if existing and not existing.is_error:
                # Son gecerli veriyi koru, sadece hata bayragi ekle
                self._store[name] = IndicatorEntry(
                    data=existing.data,
                    updated_at=existing.updated_at,
                    source=existing.source,
                    is_error=True,
                    error_msg=error_msg,
                )
            else:
                # Hic veri yoksa bos hata girisi olustur
                self._store[name] = IndicatorEntry(
                    data={"normalized": 0},
                    updated_at=0,
                    source="",
                    is_error=True,
                    error_msg=error_msg,
                )

    # ── OKUMA ────────────────────────────────────────────

    async def get(self, name: str) -> Optional[dict]:
        """
        Indikatoru al.
        Stale veya hata varsa normalized=0 ile dondur.
        """
        async with self._lock:
            entry = self._store.get(name)

        if entry is None:
            return None

        data = dict(entry.data) if isinstance(entry.data, dict) else {"normalized": 0}

        if entry.is_error:
            data["_error"]  = True
            data["_stale"]  = True
            data["_errmsg"] = entry.error_msg
            data["normalized"] = 0
        elif entry.is_stale(name):
            data["_stale"] = True
            # Stale veriyi notrople ama gondermekten vazgecme
            data["normalized"] = data.get("normalized", 0) * 0.5

        return data

    async def get_all(self) -> dict:
        """Tum indiktorleri al (sinyal motoruna gonder)."""
        result = {}
        async with self._lock:
            names = list(self._store.keys())

        for name in names:
            val = await self.get(name)
            if val is not None:
                result[name] = val
        return result

    # ── SAGLIK RAPORU ─────────────────────────────────────

    async def health_report(self) -> dict:
        async with self._lock:
            entries = dict(self._store)

        valid   = []
        stale   = []
        errors  = []

        for name, entry in entries.items():
            if entry.is_error:
                errors.append({
                    "name":  name,
                    "msg":   entry.error_msg,
                    "age_h": round(entry.age_seconds() / 3600, 1),
                })
            elif entry.is_stale(name):
                stale.append({
                    "name":  name,
                    "age_h": round(entry.age_seconds() / 3600, 1),
                })
            else:
                valid.append({
                    "name":  name,
                    "age_h": round(entry.age_seconds() / 3600, 1),
                })

        return {
            "valid":  valid,
            "stale":  stale,
            "errors": errors,
            "total":  len(entries),
        }

    # ── KALICILIK (SQLite ile senkronizasyon) ────────────

    async def persist_all(self):
        """Tum indiktorleri SQLite'a kaydet."""
        from db.database import save_indicator_snapshot
        async with self._lock:
            entries = dict(self._store)

        for name, entry in entries.items():
            try:
                await save_indicator_snapshot(
                    name=name,
                    value=entry.data if isinstance(entry.data, dict) else {"normalized": 0},
                    source=entry.source,
                    is_error=entry.is_error,
                )
            except Exception as e:
                logger.warning(f"DataBus persist hatasi [{name}]: {e}")

    async def restore_from_db(self):
        """Bot baslarken SQLite'dan son gecerli verileri yukle."""
        from db.database import load_indicator_snapshots
        try:
            snapshots = await load_indicator_snapshots()
            async with self._lock:
                for name, snap in snapshots.items():
                    self._store[name] = IndicatorEntry(
                        data=snap["data"],
                        updated_at=snap["updated_at"],
                        source="db_restore",
                        is_error=False,
                    )
            logger.info(f"DataBus: {len(snapshots)} indiktor veritabanindan yuklendi")
        except Exception as e:
            logger.warning(f"DataBus restore hatasi: {e}")


# Global instance
data_bus = DataBus()
