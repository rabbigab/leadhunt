"""Tests unitaires AccountManager — sans connexion Supabase réelle."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from scraper.accounts.manager import AccountManager, AccountRecord, BAN_DETECTION_THRESHOLD
from scraper.accounts.warmup import WarmupSequencer


def make_account(status="active", days_warming=0, groups=None) -> AccountRecord:
    return AccountRecord(
        id="test-id-001",
        label="Compte Test",
        fb_email="test@test.com",
        status=status,
        groups_assigned=groups or ["g1", "g2"],
        warming_started_at=datetime.now(timezone.utc) - timedelta(days=days_warming),
        activated_at=datetime.now(timezone.utc) if status == "active" else None,
    )


def make_manager(accounts: list[AccountRecord]) -> AccountManager:
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.in_.return_value.order.return_value.execute.return_value.data = []
    manager = AccountManager(mock_client)
    manager._accounts = accounts
    return manager


# --- Tests AccountManager ---

def test_active_accounts_filtered_correctly():
    mgr = make_manager([
        make_account(status="active"),
        make_account(status="warming"),
        make_account(status="banned"),
    ])
    assert len(mgr.active_accounts()) == 1
    assert len(mgr.warming_accounts()) == 1


def test_record_zero_cycle_increments_counter():
    acc = make_account()
    mgr = make_manager([acc])
    mgr._db.table.return_value.update.return_value.eq.return_value.execute.return_value = None

    result = mgr.record_zero_cycle(acc.id)
    assert acc.consecutive_zero_cycles == 1
    assert result is False  # Pas encore au seuil


def test_ban_detected_at_threshold():
    acc = make_account()
    acc.consecutive_zero_cycles = BAN_DETECTION_THRESHOLD - 1
    mgr = make_manager([acc])
    mgr._db.table.return_value.update.return_value.eq.return_value.execute.return_value = None

    result = mgr.record_zero_cycle(acc.id)
    assert result is True  # Ban détecté


def test_successful_cycle_resets_zero_counter():
    acc = make_account()
    acc.consecutive_zero_cycles = 2
    mgr = make_manager([acc])
    mgr._db.table.return_value.update.return_value.eq.return_value.execute.return_value = None

    mgr.record_successful_cycle(acc.id, leads_found=3)
    assert acc.consecutive_zero_cycles == 0
    assert acc.total_leads_found == 3


def test_promote_warming_takes_oldest():
    w1 = make_account(status="warming", days_warming=20)
    w2 = make_account(status="warming", days_warming=10)
    w1.id = "old-id"
    w2.id = "new-id"
    mgr = make_manager([w1, w2])
    mgr._db.table.return_value.update.return_value.eq.return_value.execute.return_value = None

    promoted = mgr.promote_warming_account(["g1"])
    assert promoted is not None
    assert promoted.id == "old-id"  # Le plus ancien en warming
    assert promoted.status == "active"


def test_promote_returns_none_when_no_warming():
    mgr = make_manager([make_account(status="active")])
    result = mgr.promote_warming_account(["g1"])
    assert result is None


# --- Tests WarmupSequencer ---

def test_warmup_phase1_before_day_7():
    acc = make_account(status="warming", days_warming=3)
    session_mock = MagicMock()
    seq = WarmupSequencer(session_mock, acc.id, acc.warming_started_at)
    assert seq.current_phase() == "phase1_feed_only"
    assert not seq.is_ready_for_production()


def test_warmup_phase2_day_8_to_14():
    acc = make_account(status="warming", days_warming=10)
    session_mock = MagicMock()
    seq = WarmupSequencer(session_mock, acc.id, acc.warming_started_at)
    assert seq.current_phase() == "phase2_join_groups"


def test_warmup_ready_after_day_22():
    acc = make_account(status="warming", days_warming=22)
    session_mock = MagicMock()
    seq = WarmupSequencer(session_mock, acc.id, acc.warming_started_at)
    assert seq.current_phase() == "ready"
    assert seq.is_ready_for_production()
