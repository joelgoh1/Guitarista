from __future__ import annotations

from guitarista_api.domain.song import Song, SongCandidate
from guitarista_api.services.normalize import normalize_title, normalized_query
from guitarista_api.services.ranking import is_ambiguous, rank_candidates, score_candidate


def cand(sid: str, title: str, artist: str) -> SongCandidate:
    return SongCandidate(song=Song(id=sid, title=title, artist=artist), score=0, source="t")


def test_normalize_title_strips_noise() -> None:
    assert normalize_title("Wonderwall - Remastered 2014") == "Wonderwall"
    assert normalize_title("Wonderwall (feat. Someone)") == "Wonderwall"
    assert normalize_title("Wonderwall [Live at Knebworth]") == "Wonderwall"
    assert normalize_title("Don't Look Back in Anger") == "Don't Look Back in Anger"
    assert (
        normalize_title("(What's the Story) Morning Glory?") == "(What's the Story) Morning Glory?"
    )
    assert normalized_query("Wonderwall - Remastered", "Oasis") == "oasis wonderwall"


def test_rank_exact_match_first_and_deterministic() -> None:
    song = Song(id="s", title="Wonderwall", artist="Oasis")
    cands = [
        cand("a", "Wonderwall (Acoustic Cover)", "Some Guy"),
        cand("b", "Wonderwall", "Oasis"),
        cand("c", "Champagne Supernova", "Oasis"),
    ]
    ranked = rank_candidates(song, cands)
    assert [c.song.id for c in ranked] == ["b", "a", "c"]
    assert ranked[0].score == 1.0
    assert rank_candidates(song, cands) == ranked
    assert not is_ambiguous(ranked)


def test_raw_query_without_artist_matches_full_string() -> None:
    song = Song(id="s", title="oasis wonderwall", artist="")
    ranked = rank_candidates(
        song, [cand("x", "Wonderwall", "Oasis"), cand("y", "Wonderwall", "Ryan Adams")]
    )
    assert ranked[0].song.id == "x" and ranked[0].score >= 0.95
    assert ranked[1].score < ranked[0].score


def test_ambiguity_detection() -> None:
    song = Song(id="s", title="Yesterday", artist="")
    low = rank_candidates(song, [cand("a", "Tomorrow", "Nobody")])
    assert low[0].score < 0.75 and is_ambiguous(low)
    close = [cand("a", "Yesterday", "The Beatles"), cand("b", "Yesterday", "Beatles")]
    assert is_ambiguous(rank_candidates(song, close))
    assert score_candidate(song, Song(id="z", title="Yesterday", artist="")) == 1.0
