from scraper.facebook.post_parser import extract_post_id_from_url, clean_text


def test_extract_post_id_from_posts_url():
    url = "https://www.facebook.com/groups/123456/posts/987654321"
    assert extract_post_id_from_url(url) == "987654321"


def test_extract_post_id_from_story_fbid():
    url = "https://www.facebook.com/groups/xxx?story_fbid=111222333"
    assert extract_post_id_from_url(url) == "111222333"


def test_extract_post_id_from_permalink():
    url = "https://www.facebook.com/permalink/444555666"
    assert extract_post_id_from_url(url) == "444555666"


def test_extract_post_id_returns_none_for_unknown():
    url = "https://www.facebook.com/groups/123456/"
    assert extract_post_id_from_url(url) is None


def test_clean_text_collapses_whitespace():
    assert clean_text("hello   world\n\nfoo") == "hello world foo"


def test_clean_text_strips():
    assert clean_text("  bonjour  ") == "bonjour"
