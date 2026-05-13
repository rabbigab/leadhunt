import unicodedata
import re
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    matched: bool
    category: str
    keywords_found: List[str]
    confidence: float


def normalize(text: str) -> str:
    """Supprime les accents et met en minuscules pour matching robuste."""
    nfkd = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


class KeywordEngine:
    def __init__(self, categories: dict[str, List[str]], negative_patterns: List[str] = None):
        """
        categories : {'plomberie': ['plombier', 'fuite d'eau', ...], ...}
        negative_patterns : ['je suis plombier', 'offre emploi', ...]
        """
        self._categories = {
            cat: [normalize(kw) for kw in keywords]
            for cat, keywords in categories.items()
        }
        self._negative = [normalize(p) for p in (negative_patterns or [])]

    def match(self, text: str) -> Optional[MatchResult]:
        norm_text = normalize(text)

        # Filtre négatif avant tout
        for neg in self._negative:
            if neg in norm_text:
                logger.debug(f"Post filtré par pattern négatif : '{neg}'")
                return None

        best: Optional[MatchResult] = None

        for category, keywords in self._categories.items():
            found = [kw for kw in keywords if kw in norm_text]
            if not found:
                continue

            confidence = min(1.0, 0.6 + len(found) * 0.2)
            result = MatchResult(
                matched=True,
                category=category,
                keywords_found=found,
                confidence=confidence,
            )
            # Garder le meilleur match (le plus de mots-clés trouvés)
            if best is None or len(found) > len(best.keywords_found):
                best = result

        return best

    @classmethod
    def from_db_rows(cls, rows: List[dict], negative_patterns: List[str] = None) -> "KeywordEngine":
        """Construit le moteur depuis les lignes Supabase keyword_categories."""
        categories = {row["name"]: row["keywords"] for row in rows if row.get("is_active")}
        return cls(categories, negative_patterns)
