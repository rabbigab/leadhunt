"""Gestionnaire multi-comptes Facebook.

Responsabilités :
- Charger les comptes depuis Supabase (statut, groupes assignés)
- Distribuer les groupes entre les comptes actifs
- Détecter les bans et basculer vers un compte de secours
- Déclencher l'activation d'un compte en warming quand nécessaire
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from supabase import Client

logger = logging.getLogger(__name__)

# Si un compte fait N cycles consécutifs avec 0 posts extraits → suspect banni
BAN_DETECTION_THRESHOLD = 3


@dataclass
class AccountRecord:
    id: str
    label: str
    fb_email: str
    status: str                      # 'warming' | 'active' | 'banned' | 'retired'
    groups_assigned: list[str]
    warming_started_at: Optional[datetime]
    activated_at: Optional[datetime]
    consecutive_zero_cycles: int = 0
    total_leads_found: int = 0


class AccountManager:
    def __init__(self, supabase: Client):
        self._db = supabase
        self._accounts: list[AccountRecord] = []

    def load(self) -> None:
        rows = (
            self._db.table("fb_accounts")
            .select("*")
            .in_("status", ["active", "warming"])
            .order("created_at")
            .execute()
            .data or []
        )
        self._accounts = [self._row_to_record(r) for r in rows]
        active = [a for a in self._accounts if a.status == "active"]
        warming = [a for a in self._accounts if a.status == "warming"]
        logger.info(f"Comptes chargés : {len(active)} actifs, {len(warming)} en warming")

    def active_accounts(self) -> list[AccountRecord]:
        return [a for a in self._accounts if a.status == "active"]

    def warming_accounts(self) -> list[AccountRecord]:
        return [a for a in self._accounts if a.status == "warming"]

    def record_zero_cycle(self, account_id: str) -> bool:
        """Incrémente le compteur de cycles vides. Retourne True si ban détecté."""
        acc = self._find(account_id)
        if not acc:
            return False
        acc.consecutive_zero_cycles += 1
        self._db.table("fb_accounts").update(
            {"consecutive_zero_cycles": acc.consecutive_zero_cycles,
             "last_scrape_at": _now()}
        ).eq("id", account_id).execute()

        if acc.consecutive_zero_cycles >= BAN_DETECTION_THRESHOLD:
            logger.warning(f"[{acc.label}] Ban probable détecté ({BAN_DETECTION_THRESHOLD} cycles vides)")
            return True
        return False

    def record_successful_cycle(self, account_id: str, leads_found: int = 0) -> None:
        acc = self._find(account_id)
        if not acc:
            return
        acc.consecutive_zero_cycles = 0
        acc.total_leads_found += leads_found
        self._db.table("fb_accounts").update({
            "consecutive_zero_cycles": 0,
            "total_leads_found": acc.total_leads_found,
            "last_scrape_at": _now(),
        }).eq("id", account_id).execute()

    def mark_banned(self, account_id: str) -> None:
        acc = self._find(account_id)
        if not acc:
            return
        acc.status = "banned"
        self._db.table("fb_accounts").update({
            "status": "banned",
            "banned_at": _now(),
        }).eq("id", account_id).execute()
        logger.error(f"[{acc.label}] Marqué comme banni")

    def promote_warming_account(self, groups: list[str]) -> Optional[AccountRecord]:
        """Prend le compte warming le plus avancé et le passe en actif."""
        candidates = sorted(
            [a for a in self._accounts if a.status == "warming" and a.warming_started_at],
            key=lambda a: a.warming_started_at,
        )
        if not candidates:
            logger.error("Aucun compte de secours disponible — intervention manuelle requise")
            return None

        acc = candidates[0]
        acc.status = "active"
        acc.groups_assigned = groups
        self._db.table("fb_accounts").update({
            "status": "active",
            "activated_at": _now(),
            "groups_assigned": groups,
            "consecutive_zero_cycles": 0,
        }).eq("id", acc.id).execute()
        logger.info(f"[{acc.label}] Promu en actif — {len(groups)} groupes assignés")
        return acc

    def log_health_event(self, account_id: str, event_type: str, details: str = "", group_id: str = "") -> None:
        try:
            self._db.table("health_events").insert({
                "account_id": account_id,
                "event_type": event_type,
                "group_id": group_id or None,
                "details": details or None,
            }).execute()
        except Exception as e:
            logger.warning(f"Impossible de logger l'événement de santé : {e}")

    def record_interaction(self, account_id: str, action: str, target_url: str = "", details: str = "") -> None:
        try:
            self._db.table("fb_interactions").insert({
                "account_id": account_id,
                "action": action,
                "target_url": target_url or None,
                "details": details or None,
            }).execute()
            self._db.table("fb_accounts").update(
                {"last_interaction_at": _now()}
            ).eq("id", account_id).execute()
        except Exception as e:
            logger.debug(f"Erreur log interaction : {e}")

    def _find(self, account_id: str) -> Optional[AccountRecord]:
        return next((a for a in self._accounts if a.id == account_id), None)

    @staticmethod
    def _row_to_record(row: dict) -> AccountRecord:
        return AccountRecord(
            id=row["id"],
            label=row["label"],
            fb_email=row["fb_email"],
            status=row["status"],
            groups_assigned=row.get("groups_assigned") or [],
            warming_started_at=_parse_dt(row.get("warming_started_at")),
            activated_at=_parse_dt(row.get("activated_at")),
            consecutive_zero_cycles=row.get("consecutive_zero_cycles", 0),
            total_leads_found=row.get("total_leads_found", 0),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(val) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None
