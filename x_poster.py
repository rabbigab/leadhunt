"""x_poster.py — Posting automatique sur X (Twitter) via tweepy OAuth 1.0a."""
import asyncio
import logging
import os
import re
from typing import Optional

import anthropic
import tweepy

log = logging.getLogger(__name__)

_X_API_KEY             = os.environ.get("X_API_KEY", "")
_X_API_SECRET          = os.environ.get("X_API_SECRET", "")
_X_ACCESS_TOKEN        = os.environ.get("X_ACCESS_TOKEN", "")
_X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET", "")
TELEGRAM_CHANNEL_URL   = os.environ.get("TELEGRAM_CHANNEL_URL", "")

_ENABLED = all([_X_API_KEY, _X_API_SECRET, _X_ACCESS_TOKEN, _X_ACCESS_TOKEN_SECRET])

_SUFFIX  = f"\n👉 {TELEGRAM_CHANNEL_URL}" if TELEGRAM_CHANNEL_URL else ""
_MAX_BODY = 240

_TEASER_SYS = """\
Tu es un copywriter crypto francophone pour X (Twitter).
Condense le message suivant en un teaser percutant en français, maximum 240 caractères.
Inclus les informations clés : actif, direction, niveaux principaux (entrée, TP, SL si signal).
Pas de hashtags. Pas de mention de source. Style direct et impactant.
Retourne UNIQUEMENT le teaser, sans guillemets ni explication.\
"""

_client: Optional[tweepy.Client] = None


def _get_client() -> Optional[tweepy.Client]:
    global _client
    if not _ENABLED:
        return None
    if _client is None:
        _client = tweepy.Client(
            consumer_key=_X_API_KEY,
            consumer_secret=_X_API_SECRET,
            access_token=_X_ACCESS_TOKEN,
            access_token_secret=_X_ACCESS_TOKEN_SECRET,
        )
    return _client


def _scrub(text: str, blocklist: list[str]) -> str:
    for term in blocklist:
        text = re.sub(re.escape(term), "", text, flags=re.IGNORECASE)
    return re.sub(r" {2,}", " ", text).strip()


def _fit(body: str) -> str:
    """Tronque body à _MAX_BODY car., ajoute le suffix, vérifie ≤280."""
    if len(body) > _MAX_BODY:
        body = body[:_MAX_BODY - 1] + "…"
    tweet = body + _SUFFIX
    if len(tweet) > 280:
        max_body = 280 - len(_SUFFIX) - 1
        tweet = body[:max_body] + "…" + _SUFFIX
    return tweet


async def post_to_x(
    full_text: str,
    claude_client: anthropic.AsyncAnthropic,
    blocklist: list[str],
) -> None:
    """Condense full_text via Claude et poste sur X. Fire-and-forget : n'élève pas d'exception."""
    if not _ENABLED:
        return

    client = _get_client()
    if not client:
        return

    try:
        resp = await claude_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=120,
            system=_TEASER_SYS,
            messages=[{"role": "user", "content": full_text}],
        )
        teaser = resp.content[0].text.strip()

        if blocklist:
            teaser = _scrub(teaser, blocklist)

        tweet = _fit(teaser)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: client.create_tweet(text=tweet))
        log.info("Posté sur X (%d car.).", len(tweet))

    except tweepy.errors.Forbidden as exc:
        log.warning("X — tweet refusé (doublon ou interdit) : %s", exc)
    except tweepy.errors.TweepyException as exc:
        log.error("X — erreur API tweepy : %s", exc)
    except anthropic.APIError as exc:
        log.error("X — erreur Claude API : %s", exc)
    except Exception as exc:
        log.error("X — erreur inattendue : %s", exc)


async def post_weekly_summary_to_x(
    counted: list[dict],
    gains: list[float],
    losses: list[float],
) -> None:
    """Poste un résumé hebdomadaire condensé sur X. Fire-and-forget."""
    if not _ENABLED:
        return

    client = _get_client()
    if not client:
        return

    try:
        if not counted:
            body = "Aucun trade clôturé cette semaine."
        else:
            win_rate   = len(gains) / len(counted) * 100
            avg_gain   = f"+{sum(gains)/len(gains):.1f}%" if gains else "—"
            avg_loss   = f"{sum(losses)/len(losses):.1f}%" if losses else "—"
            body = (
                f"📊 Semaine | {len(counted)} trades | "
                f"Win {win_rate:.0f}% | "
                f"Gain moy {avg_gain} | Perte moy {avg_loss}"
            )

        tweet = _fit(body)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: client.create_tweet(text=tweet))
        log.info("Résumé hebdo posté sur X.")

    except tweepy.errors.Forbidden as exc:
        log.warning("X hebdo — tweet refusé : %s", exc)
    except tweepy.errors.TweepyException as exc:
        log.error("X hebdo — erreur API tweepy : %s", exc)
    except Exception as exc:
        log.error("X hebdo — erreur inattendue : %s", exc)
