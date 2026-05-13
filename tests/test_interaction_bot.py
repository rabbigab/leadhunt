"""Tests unitaires InteractionBot — sans connexion réelle à Facebook."""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scraper.facebook.interaction_bot import (
    InteractionBot,
    LIKE_PROBABILITY,
    COMMENT_PROBABILITY,
    COMMENT_POOL,
)


def make_bot() -> tuple[InteractionBot, MagicMock]:
    session = MagicMock()
    session.page = AsyncMock()
    session.random_human_pause = AsyncMock()
    bot = InteractionBot(session=session, account_id="test-account")
    return bot, session


def test_can_comment_first_time():
    bot, _ = make_bot()
    assert bot._can_comment_today() is True


def test_cannot_comment_twice_in_same_week():
    bot, _ = make_bot()
    bot._last_comment_date = datetime.now(timezone.utc) - timedelta(days=2)
    assert bot._can_comment_today() is False


def test_can_comment_after_one_week():
    bot, _ = make_bot()
    bot._last_comment_date = datetime.now(timezone.utc) - timedelta(days=8)
    assert bot._can_comment_today() is True


def test_comment_pool_not_empty():
    assert len(COMMENT_POOL) >= 5
    for comment in COMMENT_POOL:
        assert len(comment) > 5


def test_like_probability_in_range():
    assert 0.05 <= LIKE_PROBABILITY <= 0.30


def test_comment_probability_very_low():
    # On veut que la proba de commenter soit très basse pour l'anti-ban
    assert COMMENT_PROBABILITY <= 0.02


@pytest.mark.asyncio
async def test_try_like_returns_false_when_no_buttons():
    bot, session = make_bot()
    session.page.query_selector_all = AsyncMock(return_value=[])
    result = await bot._try_like_random_post(session.page)
    assert result is False


@pytest.mark.asyncio
async def test_try_like_skips_already_liked():
    bot, session = make_bot()
    btn = AsyncMock()
    btn.get_attribute = AsyncMock(return_value="true")  # déjà liké
    session.page.query_selector_all = AsyncMock(return_value=[btn])
    result = await bot._try_like_random_post(session.page)
    assert result is False


@pytest.mark.asyncio
async def test_maybe_interact_skips_most_of_the_time():
    """5% de chance d'interagir → la plupart du temps, rien ne se passe."""
    bot, session = make_bot()
    session.page.evaluate = AsyncMock()
    session.page.query_selector_all = AsyncMock(return_value=[])

    interaction_count = 0
    with patch("random.random", return_value=0.99):  # > 0.05, donc skip
        for _ in range(10):
            await bot.maybe_interact_in_group(session.page, "group123")

    # evaluate ne doit pas avoir été appelé (skip total)
    session.page.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_run_feed_warmup_navigates_to_feed():
    bot, session = make_bot()
    session.page.goto = AsyncMock()
    session.page.evaluate = AsyncMock()
    session.page.query_selector_all = AsyncMock(return_value=[])

    await bot.run_feed_warmup()

    # Vérifie que la navigation vers m.facebook.com est bien effectuée
    session.page.goto.assert_called_once()
    call_url = session.page.goto.call_args[0][0]
    assert "m.facebook.com" in call_url
