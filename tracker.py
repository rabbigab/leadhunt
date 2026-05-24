"""Trade tracker — détection TP/SL via klines Binance, polling toutes les 5 min.

Logique de prix :
  LONG  : entrée déclenchée par Low <= entry ; TP par High >= target ; SL par Low <= sl
  SHORT : entrée déclenchée par High >= entry ; TP par Low <= target ; SL par High >= sl

Targets supposées ordonnées (TP1 < TP2 < TP3 pour un long, inversé pour un short).
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

import aiohttp

import binance_api
import db

log = logging.getLogger(__name__)

POLL_INTERVAL = 300   # secondes
KLINES_LIMIT  = 10   # bougies 1m ≈ 10 min de marché


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _pnl(direction: str, entry: float, exit_price: float) -> float:
    if direction == "long":
        return (exit_price - entry) / entry * 100
    return (entry - exit_price) / entry * 100


async def _send(bot, channels: list[int], text: str) -> None:
    for ch in channels:
        try:
            await bot.send_message(ch, text, parse_mode="md")
        except Exception as exc:
            log.error("Envoi canal %d : %s", ch, exc)


# ──────────────────────────────────────────────────────────────────────────────
# Core trade check
# ──────────────────────────────────────────────────────────────────────────────

async def _check_trade(
    trade: dict,
    session: aiohttp.ClientSession,
    bot,
    channels: list[int],
) -> None:
    tid        = trade["id"]
    asset      = trade["asset"]
    symbol     = trade["symbol"]
    direction  = trade["direction"]
    targets    = json.loads(trade["targets"])
    entry1     = float(trade["entry1"])
    entry2     = float(trade["entry2"]) if trade["entry2"] else None
    stop_loss  = float(trade["stop_loss"])
    sl_level   = float(trade["sl_level"]) if trade["sl_level"] else stop_loss
    status     = trade["status"]
    hit_e1     = bool(trade["hit_entry1"])
    hit_e2     = bool(trade["hit_entry2"])
    highest_tp = int(trade["highest_tp_index"])
    entry_price: Optional[float] = float(trade["entry_price"]) if trade["entry_price"] else None
    expires_at = datetime.fromisoformat(trade["expires_at"])

    now           = datetime.utcnow()
    updates: dict = {"last_checked_at": now.isoformat()}
    notes: list[str] = []

    # ── Expiry ────────────────────────────────────────────────────────────────
    if now >= expires_at:
        if status == "waiting":
            updates.update(status="closed", close_reason="timeout_no_entry",
                           closed_at=now.isoformat())
        elif highest_tp >= 1 and entry_price:
            ep  = targets[highest_tp - 1]
            pnl = _pnl(direction, entry_price, ep)
            updates.update(status="closed", close_reason="timeout_gain",
                           pnl_pct=round(pnl, 2), closed_at=now.isoformat())
            notes.append(
                f"⏰ *{asset}* — Délai expiré\n"
                f"Clôture sur TP{highest_tp} ({ep}) | P&L : *{pnl:+.2f}%*\n"
                f"_Clôturé automatiquement (2 mois)_"
            )
        else:
            updates.update(status="closed", close_reason="timeout_no_tp",
                           closed_at=now.isoformat())
            if status == "active":
                notes.append(
                    f"⏰ *{asset}* — Délai expiré sans TP atteint\n"
                    f"_Trade exclu des statistiques_"
                )
        await db.update_trade(tid, **updates)
        for msg in notes:
            await _send(bot, channels, msg)
        return

    # ── Klines ────────────────────────────────────────────────────────────────
    klines = await binance_api.get_klines(symbol, session, interval="1m", limit=KLINES_LIMIT)
    if not klines:
        await db.update_trade(tid, **updates)
        return

    lo = min(k["low"]  for k in klines)
    hi = max(k["high"] for k in klines)

    # ── Entrée 1 ──────────────────────────────────────────────────────────────
    if status == "waiting":
        e1_hit = (direction == "long"  and lo <= entry1) or \
                 (direction == "short" and hi >= entry1)
        if e1_hit:
            hit_e1      = True
            status      = "active"
            entry_price = entry1
            sl_level    = stop_loss
            updates.update(hit_entry1=1, status="active",
                           entry_price=entry_price, sl_level=sl_level)

    if status == "active" and entry_price is not None:

        # ── Entrée 2 (seulement si TP1 pas encore touché) ────────────────────
        if entry2 and not hit_e2 and highest_tp == 0:
            e2_hit = (direction == "long"  and lo <= entry2) or \
                     (direction == "short" and hi >= entry2)
            if e2_hit:
                hit_e2      = True
                entry_price = (entry1 + entry2) / 2
                updates.update(hit_entry2=1, entry_price=entry_price)

        # ── TP checks (ordre croissant pour long, décroissant pour short) ─────
        for i, tp in enumerate(targets):
            tp_idx = i + 1
            if tp_idx <= highest_tp:
                continue
            tp_hit = (direction == "long"  and hi >= tp) or \
                     (direction == "short" and lo <= tp)
            if not tp_hit:
                break   # targets ordonnées → inutile de continuer

            highest_tp = tp_idx
            updates["highest_tp_index"] = highest_tp
            await db.add_tp_hit(tid, tp_idx, tp)

            if tp_idx == 1:
                sl_level         = entry_price   # breakeven
                updates["sl_level"] = sl_level
                notes.append(
                    f"🎯 *{asset}* — TP1 atteint ✅ ({tp})\n"
                    f"Déplacez votre SL au point d'entrée : *{entry_price}*"
                )
            else:
                notes.append(f"🎯 *{asset}* — TP{tp_idx} atteint ✅ ({tp})")

        # ── Tous les TP atteints ──────────────────────────────────────────────
        if highest_tp == len(targets):
            pnl = _pnl(direction, entry_price, targets[-1])
            updates.update(status="closed", close_reason="all_tp",
                           pnl_pct=round(pnl, 2), closed_at=now.isoformat())
            notes.append(
                f"🏆 *{asset}* — Tous les TP atteints ✅\nP&L final : *{pnl:+.2f}%*"
            )

        else:
            # ── SL check ─────────────────────────────────────────────────────
            sl_hit = (direction == "long"  and lo <= sl_level) or \
                     (direction == "short" and hi >= sl_level)
            if sl_hit:
                pnl     = _pnl(direction, entry_price, sl_level)
                is_be   = highest_tp >= 1
                updates.update(status="closed", close_reason="sl",
                               pnl_pct=round(pnl, 2), closed_at=now.isoformat())
                label = "Breakeven ➡️ ~0%" if is_be else f"SL touché ❌ | P&L : *{pnl:+.2f}%*"
                notes.append(f"🛑 *{asset}* — {label}")

    await db.update_trade(tid, **updates)
    for msg in notes:
        await _send(bot, channels, msg)


# ──────────────────────────────────────────────────────────────────────────────
# Polling loop
# ──────────────────────────────────────────────────────────────────────────────

async def run_polling_loop(
    bot, channels: list[int], session: aiohttp.ClientSession
) -> None:
    """Vérifie tous les trades actifs toutes les POLL_INTERVAL secondes."""
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        trades = await db.get_active_trades()
        if not trades:
            continue
        log.info("Polling %d trade(s) actif(s)…", len(trades))
        for trade in trades:
            try:
                await _check_trade(trade, session, bot, channels)
            except Exception as exc:
                log.error("Erreur check trade #%d : %s", trade["id"], exc)
