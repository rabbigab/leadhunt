"""HealthMonitor — détecte les pannes et envoie des alertes Telegram.

Surveille :
- Bans de compte (N cycles consécutifs à 0 posts)
- Breakage DOM Facebook (posts_checked > 0 mais 0 leads sur longue période — normal)
  vs posts_checked = 0 (DOM cassé ou ban)
- Compte warming prêt à être promu
"""

import logging
from datetime import datetime, timezone, timedelta

from scraper.accounts.manager import AccountManager, AccountRecord
from scraper.notifications.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class HealthMonitor:
    def __init__(self, account_manager: AccountManager, notifier: TelegramNotifier):
        self._accounts = account_manager
        self._notifier = notifier

    async def check_after_cycle(
        self,
        account: AccountRecord,
        posts_checked: int,
        leads_found: int,
        errors: list[str],
    ) -> None:
        """Appelé après chaque cycle de scraping pour un compte."""

        if posts_checked == 0:
            ban_likely = self._accounts.record_zero_cycle(account.id)
            self._accounts.log_health_event(
                account.id, "zero_posts",
                f"0 posts extraits (cycle #{account.consecutive_zero_cycles})"
            )

            if ban_likely:
                await self._handle_likely_ban(account)
        else:
            self._accounts.record_successful_cycle(account.id, leads_found)

        # Erreurs réseau répétées
        if len(errors) >= 3:
            self._accounts.log_health_event(
                account.id, "network_error",
                f"{len(errors)} erreurs : {'; '.join(errors[:2])}"
            )
            await self._notifier.send_error_alert(
                f"⚠️ *{account.label}* — {len(errors)} erreurs réseau dans ce cycle"
            )

    async def check_warming_promotions(self) -> None:
        """Vérifie si un compte en warming est prêt à être activé."""
        for acc in self._accounts.warming_accounts():
            if acc.warming_started_at is None:
                continue
            days = (datetime.now(timezone.utc) - acc.warming_started_at).days
            if days >= 22:
                await self._notifier.send_error_alert(
                    f"✅ *{acc.label}* est prêt à être activé (J{days} de warming)\n"
                    f"Assigne-lui des groupes dans Supabase et mets son statut à `active`."
                )
                logger.info(f"[{acc.label}] Warming terminé (J{days}) — prêt pour activation")

    async def _handle_likely_ban(self, account: AccountRecord) -> None:
        """Gère un ban probable : marque le compte, tente de basculer vers un backup."""
        self._accounts.mark_banned(account.id)
        self._accounts.log_health_event(account.id, "ban_detected", "Ban détecté automatiquement")

        await self._notifier.send_error_alert(
            f"🚨 *BAN DÉTECTÉ — {account.label}*\n\n"
            f"Le compte `{account.fb_email}` ne répond plus depuis "
            f"{account.consecutive_zero_cycles} cycles consécutifs.\n\n"
            f"Groupes affectés : {len(account.groups_assigned)}\n"
            f"Action requise : vérifier le compte FB + préparer un remplaçant."
        )

        # Tenter de promouvoir un compte de secours
        backup = self._accounts.promote_warming_account(account.groups_assigned)
        if backup:
            await self._notifier.send_error_alert(
                f"♻️ *Basculement automatique* vers *{backup.label}*\n"
                f"{len(account.groups_assigned)} groupes transférés.\n"
                f"⚠️ Le nouveau compte n'est peut-être pas encore complètement chauffé — surveille les prochains cycles."
            )
        else:
            await self._notifier.send_error_alert(
                f"❌ *Aucun compte de secours disponible*\n"
                f"Les {len(account.groups_assigned)} groupes de *{account.label}* ne sont plus surveillés.\n"
                f"Action immédiate requise : créer et configurer un compte de remplacement."
            )
