import logging
from typing import Set

logger = logging.getLogger(__name__)


class Deduplicator:
    """Cache mémoire des post_ids déjà traités dans la session courante.

    La vérification définitive (inter-sessions) est faite en DB via SupabaseClient.
    Ce cache local évite les requêtes DB répétées pour les posts déjà vus dans la session.
    """

    def __init__(self):
        self._seen: Set[str] = set()

    def is_known(self, post_id: str) -> bool:
        return post_id in self._seen

    def mark_known(self, post_id: str) -> None:
        self._seen.add(post_id)

    def preload(self, post_ids: list[str]) -> None:
        """Charge les post_ids existants en DB au démarrage."""
        self._seen.update(post_ids)
        logger.info(f"Déduplicateur initialisé avec {len(post_ids)} posts connus")

    def size(self) -> int:
        return len(self._seen)
