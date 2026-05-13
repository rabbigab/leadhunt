"""LeadHunt — runner principal multi-comptes.

Architecture :
- 1 worker asyncio par compte Facebook actif (4 max)
- Chaque worker scrape ses groupes assignés en boucle
- InteractionBot tourne à chaque session pour simuler un humain
- HealthMonitor surveille les bans et déclenche les basculements
- WarmupSequencer gère les comptes en période de chauffe
"""

import asyncio
import logging
import logging.handlers
import random
import sys

from scraper.accounts.health_monitor import HealthMonitor
from scraper.accounts.manager import AccountManager, AccountRecord
from scraper.accounts.warmup import WarmupSequencer
from scraper.config.settings import settings, load_config
from scraper.database.client import SupabaseClient
from scraper.detection.deduplication import Deduplicator
from scraper.detection.keyword_engine import KeywordEngine
from scraper.facebook.group_reader import GroupReader
from scraper.facebook.interaction_bot import InteractionBot
from scraper.facebook.session import FacebookSession
from scraper.notifications.telegram import TelegramNotifier


def setup_logging() -> None:
    settings.LOGS_DIR.mkdir(exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    fh = logging.handlers.RotatingFileHandler(
        settings.LOGS_DIR / "scraper.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


logger = logging.getLogger(__name__)


def is_in_no_scrape_window(config: dict) -> bool:
    no_scrape = config.get("scraping", {}).get("no_scrape_hours", {})
    if not no_scrape:
        return False
    start = no_scrape.get("start", 1)
    end = no_scrape.get("end", 7)
    hour = __import__("datetime").datetime.now().hour
    return start <= hour < end if start <= end else (hour >= start or hour < end)


async def run_account_cycle(
    account: AccountRecord,
    config: dict,
    db: SupabaseClient,
    dedup: Deduplicator,
    keyword_engine: KeywordEngine,
    notifier: TelegramNotifier,
    account_manager: AccountManager,
) -> tuple[int, int, int, list[str]]:
    """Cycle de scraping complet pour un compte. Retourne (groups, posts, leads, errors)."""
    scraping_cfg = config.get("scraping", {})
    delay_min = scraping_cfg.get("delay_min_seconds", 3)
    delay_max = scraping_cfg.get("delay_max_seconds", 10)
    posts_per_group = scraping_cfg.get("posts_per_group", 25)

    proxy = settings.get_next_proxy()
    fb_session = FacebookSession(proxy_url=proxy, account_id=account.id)
    await fb_session.start()

    if not await fb_session.login():
        logger.error(f"[{account.label}] Impossible de se connecter — cycle ignoré")
        account_manager.log_health_event(account.id, "login_fail")
        await fb_session.close()
        return 0, 0, 0, ["login_fail"]

    interaction_bot = InteractionBot(fb_session, account.id)

    # Warmup feed au début de chaque session (comportement humain)
    interactions = await interaction_bot.run_feed_warmup()
    logger.debug(f"[{account.label}] {interactions} interactions feed")

    reader = GroupReader(fb_session)
    groups_scraped = posts_checked = leads_found = 0
    errors: list[str] = []

    # Groupes assignés à ce compte + groupes actifs dans config
    config_groups = {g["id"]: g for g in config.get("groups", []) if g.get("active")}
    my_groups = [config_groups[gid] for gid in account.groups_assigned if gid in config_groups]

    for group in my_groups:
        try:
            posts = await reader.fetch_recent_posts(
                group["id"], group["name"], group["url"], limit=posts_per_group
            )
            groups_scraped += 1
            posts_checked += len(posts)

            for post in posts:
                if dedup.is_known(post.fb_post_id):
                    continue
                if db.post_id_exists(post.fb_post_id):
                    dedup.mark_known(post.fb_post_id)
                    continue

                match = keyword_engine.match(post.content)
                dedup.mark_known(post.fb_post_id)

                if match is None:
                    continue

                logger.info(
                    f"[{account.label}] Lead [{match.category}] "
                    f"confiance {int(match.confidence * 100)}% — '{post.content[:60]}'"
                )
                db.save_lead(post, match)
                notified = await notifier.send(post, match)
                if notified:
                    db.mark_notified(post.fb_post_id)
                    account_manager.record_interaction(account.id, "like", post.post_url, "lead_detected")
                leads_found += 1

            # Interaction occasionnelle dans le groupe (anti-ban)
            await interaction_bot.maybe_interact_in_group(fb_session.page, group["id"])

        except Exception as e:
            err = f"{group['name']}: {e}"
            logger.error(f"[{account.label}] {err}")
            errors.append(err)

        # Pause humaine entre groupes
        await asyncio.sleep(random.uniform(delay_min, delay_max))

    await fb_session.close()
    return groups_scraped, posts_checked, leads_found, errors


async def run_warming_sessions(
    account_manager: AccountManager,
    config: dict,
    notifier: TelegramNotifier,
) -> None:
    """Lance les sessions de warming pour les comptes en phase de chauffe."""
    target_group_ids = [g["id"] for g in config.get("groups", []) if g.get("active")]

    for acc in account_manager.warming_accounts():
        if acc.warming_started_at is None:
            continue
        try:
            fb_session = FacebookSession(account_id=acc.id)
            await fb_session.start()
            if await fb_session.login():
                sequencer = WarmupSequencer(fb_session, acc.id, acc.warming_started_at)
                await sequencer.run_daily_warming_session(target_group_ids)
            await fb_session.close()
        except Exception as e:
            logger.error(f"[{acc.label}] Erreur session warming : {e}")


async def worker(
    account: AccountRecord,
    config: dict,
    db: SupabaseClient,
    dedup: Deduplicator,
    keyword_engine: KeywordEngine,
    notifier: TelegramNotifier,
    account_manager: AccountManager,
    health_monitor: HealthMonitor,
    stop_event: asyncio.Event,
) -> None:
    """Worker dédié à un compte Facebook. Tourne jusqu'à stop_event."""
    interval_minutes = config.get("scraping", {}).get("interval_minutes", 15)
    jitter_minutes = config.get("scraping", {}).get("cycle_jitter_minutes", 5)
    label = account.label

    logger.info(f"[{label}] Worker démarré — {len(account.groups_assigned)} groupes")

    while not stop_event.is_set():
        if is_in_no_scrape_window(config):
            logger.debug(f"[{label}] Pause nocturne active")
            await asyncio.sleep(300)
            continue

        # Recharger le statut du compte depuis DB (peut avoir changé si banni)
        account_manager.load()
        updated = next((a for a in account_manager.active_accounts() if a.id == account.id), None)
        if updated is None:
            logger.warning(f"[{label}] Compte retiré des actifs — worker arrêté")
            break
        account = updated

        logger.info(f"[{label}] Début du cycle")
        start = asyncio.get_event_loop().time()

        groups, posts, leads, errors = await run_account_cycle(
            account, config, db, dedup, keyword_engine, notifier, account_manager
        )

        elapsed = asyncio.get_event_loop().time() - start
        logger.info(f"[{label}] Cycle OK en {elapsed:.0f}s — {groups} groupes, {posts} posts, {leads} leads")

        await health_monitor.check_after_cycle(account, posts, leads, errors)
        db.save_scrape_session(groups, posts, leads, errors)

        # Attendre le prochain cycle avec jitter
        jitter = random.uniform(0, jitter_minutes * 60)
        wait = max(0, interval_minutes * 60 - elapsed) + jitter
        logger.info(f"[{label}] Prochain cycle dans {wait / 60:.1f} min")
        await asyncio.sleep(wait)


async def main() -> None:
    setup_logging()
    logger.info("=== LeadHunt démarrage ===")

    config = load_config()
    db = SupabaseClient()
    notifier = TelegramNotifier()

    # Charger les mots-clés depuis DB
    keyword_rows = db.get_keyword_categories()
    negative_patterns = config.get("keywords", {}).get("negative_patterns", [])
    keyword_engine = KeywordEngine.from_db_rows(keyword_rows, negative_patterns)
    logger.info(f"Moteur de mots-clés : {len(keyword_rows)} catégories")

    # Déduplicateur partagé entre tous les workers
    dedup = Deduplicator()
    dedup.preload(db.get_recent_post_ids(limit=5000))

    # Charger les comptes
    account_manager = AccountManager(db._client)
    account_manager.load()

    active_accounts = account_manager.active_accounts()
    if not active_accounts:
        logger.critical(
            "Aucun compte Facebook actif trouvé dans Supabase.\n"
            "Insère au moins 1 ligne dans fb_accounts avec status='active' "
            "et groups_assigned contenant les IDs de groupes à surveiller."
        )
        sys.exit(1)

    health_monitor = HealthMonitor(account_manager, notifier)

    notifier.set_db(db)
    notifier.start_callback_listener()
    await notifier.send_startup_message()
    logger.info(
        f"Démarrage de {len(active_accounts)} worker(s) + "
        f"{len(account_manager.warming_accounts())} compte(s) en warming"
    )

    stop_event = asyncio.Event()

    # Lancer 1 worker par compte actif en parallèle
    worker_tasks = [
        asyncio.create_task(
            worker(acc, config, db, dedup, keyword_engine, notifier, account_manager, health_monitor, stop_event)
        )
        for acc in active_accounts
    ]

    # Tâche de warming (tourne 1x par heure, sessions courtes)
    async def warming_loop():
        while not stop_event.is_set():
            await asyncio.sleep(3600)  # 1 fois par heure
            if not is_in_no_scrape_window(config):
                await run_warming_sessions(account_manager, config, notifier)
                await health_monitor.check_warming_promotions()

    warming_task = asyncio.create_task(warming_loop())

    try:
        await asyncio.gather(*worker_tasks, warming_task)
    except KeyboardInterrupt:
        logger.info("Arrêt demandé (Ctrl+C)")
        stop_event.set()
    except Exception as e:
        logger.critical(f"Erreur fatale : {e}", exc_info=True)
        await notifier.send_error_alert(f"💥 Erreur fatale LeadHunt : {e}")
        stop_event.set()

    logger.info("LeadHunt arrêté")


if __name__ == "__main__":
    asyncio.run(main())
