from scraper.detection.deduplication import Deduplicator


def test_new_post_not_known():
    d = Deduplicator()
    assert not d.is_known("abc123")


def test_mark_known_makes_it_known():
    d = Deduplicator()
    d.mark_known("abc123")
    assert d.is_known("abc123")


def test_preload_marks_all_known():
    d = Deduplicator()
    d.preload(["id1", "id2", "id3"])
    assert d.is_known("id1")
    assert d.is_known("id2")
    assert not d.is_known("id4")


def test_size_tracks_correctly():
    d = Deduplicator()
    assert d.size() == 0
    d.mark_known("x")
    d.mark_known("y")
    assert d.size() == 2
    d.mark_known("x")  # doublon
    assert d.size() == 2
