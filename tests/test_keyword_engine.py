import pytest
from scraper.detection.keyword_engine import KeywordEngine, normalize


def make_engine() -> KeywordEngine:
    return KeywordEngine(
        categories={
            "plomberie": ["plombier", "fuite d'eau", "chauffe-eau"],
            "electricite": ["électricien", "disjoncteur"],
        },
        negative_patterns=["je suis plombier", "offre emploi"],
    )


def test_normalize_strips_accents():
    assert normalize("électricien") == "electricien"
    assert normalize("Ostéopathe") == "osteopathe"
    assert normalize("déménageur") == "demenageur"


def test_match_simple_keyword():
    engine = make_engine()
    result = engine.match("Bonjour, je cherche un plombier urgent")
    assert result is not None
    assert result.category == "plomberie"
    assert "plombier" in result.keywords_found


def test_match_with_accents_in_text():
    engine = make_engine()
    result = engine.match("Besoin d'un électricien pour mon appartement")
    assert result is not None
    assert result.category == "electricite"


def test_match_keyword_without_accent_in_text():
    engine = make_engine()
    result = engine.match("cherche electricien disponible ce soir")
    assert result is not None
    assert result.category == "electricite"


def test_no_match_returns_none():
    engine = make_engine()
    result = engine.match("Quelqu'un connaît un bon restaurant à Tel Aviv ?")
    assert result is None


def test_negative_pattern_blocks_match():
    engine = make_engine()
    result = engine.match("Je suis plombier et je cherche des clients")
    assert result is None


def test_confidence_increases_with_more_keywords():
    engine = make_engine()
    single = engine.match("cherche plombier")
    multi = engine.match("cherche plombier urgent, fuite d'eau dans la cuisine")
    assert multi is not None
    assert single is not None
    assert multi.confidence >= single.confidence


def test_best_category_wins():
    engine = make_engine()
    # Post avec 2 mots-clés plomberie vs 1 électricité → plomberie gagne
    result = engine.match("problème de plombier et chauffe-eau mais aussi disjoncteur")
    assert result is not None
    assert result.category == "plomberie"
