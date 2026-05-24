"""Binance REST API — résolution de symboles + klines polling.

Cache exchangeInfo en mémoire (TTL 1 h). Pas de clé API requise.
"""
import logging
import time
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

_BASE = "https://api.binance.com"
_QUOTE_PRIORITY = ("USDT", "USDC", "BUSD", "BTC", "ETH", "BNB")
_CACHE_TTL = 3600.0

_symbol_set: set[str] = set()
_cache_ts: float = 0.0


async def _ensure_cache(session: aiohttp.ClientSession) -> None:
    global _symbol_set, _cache_ts
    if _symbol_set and (time.monotonic() - _cache_ts) < _CACHE_TTL:
        return
    try:
        async with session.get(
            f"{_BASE}/api/v3/exchangeInfo",
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            data = await r.json()
            _symbol_set = {
                s["symbol"]
                for s in data.get("symbols", [])
                if s.get("status") == "TRADING"
            }
            _cache_ts = time.monotonic()
            log.info("Cache Binance : %d symboles TRADING.", len(_symbol_set))
    except Exception as exc:
        log.error("Erreur refresh exchangeInfo : %s", exc)


async def resolve_symbol(asset: str, session: aiohttp.ClientSession) -> Optional[str]:
    """Retourne la première paire Binance trouvée (ex: JUPUSDT), ou None."""
    await _ensure_cache(session)
    asset = asset.upper().strip()
    for quote in _QUOTE_PRIORITY:
        candidate = f"{asset}{quote}"
        if candidate in _symbol_set:
            return candidate
    return None


async def get_klines(
    symbol: str,
    session: aiohttp.ClientSession,
    interval: str = "1m",
    limit: int = 10,
) -> list[dict]:
    """Retourne les N dernières bougies {open_time, open, high, low, close}."""
    try:
        async with session.get(
            f"{_BASE}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": str(limit)},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            data = await r.json()
            if isinstance(data, list):
                return [
                    {
                        "open_time": row[0],
                        "open":  float(row[1]),
                        "high":  float(row[2]),
                        "low":   float(row[3]),
                        "close": float(row[4]),
                    }
                    for row in data
                ]
    except Exception as exc:
        log.error("Erreur klines %s : %s", symbol, exc)
    return []


async def get_current_price(
    symbol: str, session: aiohttp.ClientSession
) -> Optional[float]:
    klines = await get_klines(symbol, session, interval="1m", limit=1)
    return klines[-1]["close"] if klines else None
