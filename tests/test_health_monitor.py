"""Tests unitaires HealthMonitor."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta

from scraper.accounts.health_monitor import HealthMonitor
from scraper.accounts.manager import AccountRecord, BAN_DETECTION_THRESHOLD


def make_account(label="Compte A", consecutive_zeros=0, groups=None) -> AccountRecord:
    return AccountRecord(
        id="acc-001",
        label=label,
        fb_email="test@test.com",
        status="active",
        groups_assigned=groups or ["g1", "g2", "g3"],
        warming_started_at=None,
        activated_at=datetime.now(timezone.utc),
        consecutive_zero_cycles=consecutive_zeros,
    )


def make_monitor():
    account_manager = MagicMock()
    notifier = MagicMock()
    notifier.send_error_alert = AsyncMock()
    monitor = HealthMonitor(account_manager, notifier)
    return monitor, account_manager, notifier


@pytest.mark.asyncio
async def test_successful_cycle_records_success():
    monitor, mgr, notifier = make_monitor()
    mgr.record_successful_cycle = MagicMock()
    acc = make_account()

    await monitor.check_after_cycle(acc, posts_checked=42, leads_found=3, errors=[])

    mgr.record_successful_cycle.assert_called_once_with(acc.id, 3)
    notifier.send_error_alert.assert_not_called()


@pytest.mark.asyncio
async def test_zero_posts_increments_counter():
    monitor, mgr, notifier = make_monitor()
    mgr.record_zero_cycle = MagicMock(return_value=False)  # pas encore au seuil
    acc = make_account(consecutive_zeros=1)

    await monitor.check_after_cycle(acc, posts_checked=0, leads_found=0, errors=[])

    mgr.record_zero_cycle.assert_called_once_with(acc.id)


@pytest.mark.asyncio
async def test_ban_detected_triggers_alert_and_promotion():
    monitor, mgr, notifier = make_monitor()
    mgr.record_zero_cycle = MagicMock(return_value=True)  # ban détecté
    mgr.mark_banned = MagicMock()
    mgr.log_health_event = MagicMock()

    backup = AccountRecord(
        id="acc-002", label="Compte B", fb_email="b@b.com",
        status="active", groups_assigned=["g1", "g2", "g3"],
        warming_started_at=datetime.now(timezone.utc) - timedelta(days=25),
        activated_at=None,
    )
    mgr.promote_warming_account = MagicMock(return_value=backup)

    acc = make_account(consecutive_zeros=BAN_DETECTION_THRESHOLD)
    await monitor.check_after_cycle(acc, posts_checked=0, leads_found=0, errors=[])

    mgr.mark_banned.assert_called_once_with(acc.id)
    assert notifier.send_error_alert.call_count >= 1
    # L'alerte de ban et l'alerte de basculement
    alert_texts = [str(call) for call in notifier.send_error_alert.call_args_list]
    assert any("BAN" in t or "ban" in t.lower() for t in alert_texts)


@pytest.mark.asyncio
async def test_ban_no_backup_sends_critical_alert():
    monitor, mgr, notifier = make_monitor()
    mgr.record_zero_cycle = MagicMock(return_value=True)
    mgr.mark_banned = MagicMock()
    mgr.log_health_event = MagicMock()
    mgr.promote_warming_account = MagicMock(return_value=None)  # pas de backup

    acc = make_account()
    await monitor.check_after_cycle(acc, posts_checked=0, leads_found=0, errors=[])

    # Doit envoyer au moins 2 alertes : ban + pas de backup
    assert notifier.send_error_alert.call_count >= 2


@pytest.mark.asyncio
async def test_many_errors_triggers_alert():
    monitor, mgr, notifier = make_monitor()
    mgr.record_successful_cycle = MagicMock()
    mgr.log_health_event = MagicMock()
    acc = make_account()

    await monitor.check_after_cycle(
        acc, posts_checked=5, leads_found=0,
        errors=["err1", "err2", "err3"]
    )

    notifier.send_error_alert.assert_called_once()


@pytest.mark.asyncio
async def test_warming_ready_sends_notification():
    monitor, mgr, notifier = make_monitor()

    ready_acc = AccountRecord(
        id="w-001", label="Compte E", fb_email="e@e.com",
        status="warming",
        groups_assigned=[],
        warming_started_at=datetime.now(timezone.utc) - timedelta(days=23),
        activated_at=None,
    )
    not_ready_acc = AccountRecord(
        id="w-002", label="Compte F", fb_email="f@f.com",
        status="warming",
        groups_assigned=[],
        warming_started_at=datetime.now(timezone.utc) - timedelta(days=10),
        activated_at=None,
    )
    mgr.warming_accounts = MagicMock(return_value=[ready_acc, not_ready_acc])

    await monitor.check_warming_promotions()

    # Seulement le compte à J23 doit déclencher une alerte
    assert notifier.send_error_alert.call_count == 1
    alert_text = str(notifier.send_error_alert.call_args)
    assert "Compte E" in alert_text
