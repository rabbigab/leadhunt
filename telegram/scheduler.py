"""Rapport hebdomadaire posté tous les lundis à 09:00 UTC sur les deux canaux."""
import asyncio
import json
import logging
from datetime import datetime, timedelta

import aiohttp

import binance_api
import db

log = logging.getLogger(__name__)

_EXCLUDED_REASONS = {"timeout_no_tp", "timeout_no_entry"}


def _seconds_until_next_monday_9am() -> float:
    now        = datetime.utcnow()
    days_ahead = (7 - now.weekday()) % 7     # lundi = 0
    if days_ahead == 0 and now.hour >= 9:
        days_ahead = 7
    next_run = (now + timedelta(days=days_ahead)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    return max(0.0, (next_run - now).total_seconds())


async def _build_report(session: aiohttp.ClientSession) -> str:
    since       = datetime.utcnow() - timedelta(days=7)
    closed      = await db.get_closed_trades_since(since)
    open_trades = await db.get_open_trades()

    lines: list[str] = ["📊 *Rapport hebdomadaire — Trades suivis*\n"]

    # ── Clôturés ──────────────────────────────────────────────────────────────
    counted = [t for t in closed if t["close_reason"] not in _EXCLUDED_REASONS]
    if counted:
        lines.append("*✅ Clôturés cette semaine*")
        for t in counted:
            d   = "L" if t["direction"] == "long" else "S"
            pnl = t["pnl_pct"]
            pnl_str = f"{pnl:+.2f}%" if pnl is not None else "—"
            reason = {
                "all_tp":       f"TP{t['highest_tp_index']}",
                "sl":           "SL",
                "timeout_gain": f"TP{t['highest_tp_index']} (délai)",
            }.get(t["close_reason"] or "", t["close_reason"] or "?")
            lines.append(f"• *{t['asset']}* {d} | {reason} | {pnl_str}")

    hors_delai = [t for t in closed if t["close_reason"] == "timeout_no_tp"]
    if hors_delai:
        lines.append(f"\n⏰ Hors délai (exclus des stats) : {len(hors_delai)}")

    # ── En cours ──────────────────────────────────────────────────────────────
    if open_trades:
        lines.append("\n*⏳ En cours*")
        for t in open_trades:
            d  = "L" if t["direction"] == "long" else "S"
            ep = t["entry_price"]
            if not ep:
                lines.append(f"• *{t['asset']}* {d} — En attente d'entrée")
                continue
            ep      = float(ep)
            current = await binance_api.get_current_price(t["symbol"], session)
            if current:
                latent = (
                    (current - ep) / ep * 100
                    if t["direction"] == "long"
                    else (ep - current) / ep * 100
                )
                lines.append(
                    f"• *{t['asset']}* {d} | Entrée {ep} | Cours {current} | Latent {latent:+.2f}%"
                )
            else:
                lines.append(f"• *{t['asset']}* {d} | Entrée {ep}")

    # ── Statistiques ──────────────────────────────────────────────────────────
    if counted:
        gains  = [t["pnl_pct"] for t in counted if t["pnl_pct"] is not None and t["pnl_pct"] >= 0]
        losses = [t["pnl_pct"] for t in counted if t["pnl_pct"] is not None and t["pnl_pct"] < 0]
        lines.append("\n*📈 Statistiques*")
        lines.append(f"Win rate : {len(gains) / len(counted) * 100:.0f}%")
        if gains:
            lines.append(f"Gain moyen : +{sum(gains) / len(gains):.2f}%")
        if losses:
            lines.append(f"Perte moyenne : {sum(losses) / len(losses):.2f}%")
        lines.append(f"Trades comptabilisés : {len(counted)}")
    else:
        lines.append("\n_Aucun trade clôturé cette semaine._")

    lines.append("\n_Suivi automatique sur paires Binance — pas un conseil en investissement_")
    return "\n".join(lines)


async def run_weekly_scheduler(
    bot, channels: list[int], session: aiohttp.ClientSession
) -> None:
    delay = _seconds_until_next_monday_9am()
    log.info("Prochain rapport hebdomadaire dans %.1f h.", delay / 3600)
    await asyncio.sleep(delay)
    while True:
        try:
            report = await _build_report(session)
            for ch in channels:
                await bot.send_message(ch, report, parse_mode="md")
            log.info("Rapport hebdomadaire posté.")
        except Exception as exc:
            log.error("Erreur rapport hebdomadaire : %s", exc)
        await asyncio.sleep(7 * 24 * 3600)
