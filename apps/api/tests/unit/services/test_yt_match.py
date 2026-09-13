from __future__ import annotations

import json
from pathlib import Path

from guitarista_api.adapters.ytdlp import YtCandidate
from guitarista_api.domain.song import Song
from guitarista_api.services.yt_match import (
    clean_uploader,
    clean_yt_title,
    pick_best,
    rejection_message,
    score_yt_candidate,
)

SONG = Song(id="s", title="Wonderwall", artist="Oasis", duration_s=258.0)
FIXTURE = Path(__file__).parents[2] / "fixtures" / "ytdlp" / "search_wonderwall.jsonl"


def yt(
    vid: str,
    title: str,
    uploader: str = "OasisVEVO",
    duration_s: float | None = 258.0,
    *,
    is_live: bool = False,
) -> YtCandidate:
    return YtCandidate(
        video_id=vid,
        url=f"https://www.youtube.com/watch?v={vid}",
        title=title,
        uploader=uploader,
        duration_s=duration_s,
        is_live=is_live,
    )


def test_clean_yt_title_strips_packaging() -> None:
    assert clean_yt_title("Wonderwall (Official Video)") == "Wonderwall"
    assert clean_yt_title("Wonderwall [HD]") == "Wonderwall"
    assert clean_yt_title("Oasis - Wonderwall (Official Music Video)") == "Oasis - Wonderwall"
    # Release noise handling still comes from normalize_title.
    assert clean_yt_title("Wonderwall - Remastered 2014") == "Wonderwall"


def test_clean_uploader_strips_channel_suffixes() -> None:
    assert clean_uploader("OasisVEVO") == "Oasis"
    assert clean_uploader("Oasis - Topic") == "Oasis"
    assert clean_uploader("Oasis Official") == "Oasis"
    assert clean_uploader("Some Guy") == "Some Guy"


def test_studio_match_beats_live_version() -> None:
    studio = yt("a", "Oasis - Wonderwall (Official Video)")
    live = yt("b", "Wonderwall (Live at Knebworth)", duration_s=271.0, is_live=True)
    best, breakdowns = pick_best(SONG, [live, studio])
    assert best is not None
    assert best.video_id == "a"
    assert breakdowns[0]["chosen"] is True
    assert breakdowns[0]["video_id"] == "a"


def test_cover_loses_to_the_real_thing() -> None:
    cover = yt("c", "Wonderwall (Acoustic Cover)", uploader="Some Guy")
    real = yt("a", "Oasis - Wonderwall")
    best, _ = pick_best(SONG, [cover, real])
    assert best is not None
    assert best.video_id == "a"


def test_ten_hour_loop_is_rejected_on_duration() -> None:
    loop = yt("loop", "Wonderwall - Oasis [10 HOURS]", duration_s=36000.0)
    score, breakdown = score_yt_candidate(SONG, loop)
    assert "rejected" in breakdown
    best, _ = pick_best(SONG, [loop])
    assert best is None


def test_short_clip_is_rejected_on_duration() -> None:
    clip = yt("clip", "Oasis - Wonderwall", duration_s=40.0)
    _, breakdown = score_yt_candidate(SONG, clip)
    assert "rejected" in breakdown
    assert pick_best(SONG, [clip])[0] is None


def test_near_exact_duration_scores_full_marks() -> None:
    _, breakdown = score_yt_candidate(SONG, yt("a", "Oasis - Wonderwall", duration_s=259.0))
    assert breakdown["duration_score"] == 1.0
    assert breakdown["duration_delta_s"] == 1.0


def test_pick_best_returns_none_when_everything_is_weak() -> None:
    junk = [
        yt("x", "Totally Different Song", uploader="Nobody", duration_s=258.0),
        yt("y", "Another Unrelated Track", uploader="Nobody", duration_s=257.0),
    ]
    best, breakdowns = pick_best(SONG, junk)
    assert best is None
    assert len(breakdowns) == 2
    assert "closest was" in rejection_message(SONG, breakdowns)


def test_exact_duration_cannot_rescue_an_unrelated_title() -> None:
    """Plenty of unrelated tracks run 4:18; duration must corroborate, never substitute."""
    imposter = yt("x", "Totally Different Song", uploader="Nobody", duration_s=258.0)
    _, breakdown = score_yt_candidate(SONG, imposter)
    assert breakdown["duration_score"] == 1.0
    assert "title does not match" in breakdown["rejected"]
    assert pick_best(SONG, [imposter])[0] is None


def test_unknown_duration_falls_back_to_text_only() -> None:
    """No Spotify creds -> no duration_s; text similarity alone must carry the decision."""
    song = Song(id="s", title="Wonderwall", artist="Oasis")
    exact = yt("a", "Oasis - Wonderwall", duration_s=None)
    weak = yt("b", "Wunderwal by someone else", uploader="Nobody", duration_s=None)
    best, breakdowns = pick_best(song, [weak, exact])
    assert best is not None
    assert best.video_id == "a"
    assert breakdowns[0]["duration_score"] is None
    # The weak one on its own must not clear the stricter text-only bar.
    assert pick_best(song, [weak])[0] is None


def test_live_flag_penalized_unless_song_is_live() -> None:
    live = yt("b", "Wonderwall", duration_s=258.0, is_live=True)
    penalized, _ = score_yt_candidate(SONG, live)
    live_song = Song(id="s2", title="Wonderwall (Live)", artist="Oasis", duration_s=258.0)
    allowed, _ = score_yt_candidate(live_song, live)
    assert allowed > penalized


def test_keyword_penalty_applies_to_variants() -> None:
    _, breakdown = score_yt_candidate(SONG, yt("k", "Wonderwall karaoke instrumental"))
    assert set(breakdown["keywords"]) == {"karaoke", "instrumental"}
    assert breakdown["penalty"] > 0


def test_rejection_message_with_no_results() -> None:
    assert "no YouTube results" in rejection_message(SONG, [])


def test_real_search_results_pick_the_album_cut() -> None:
    """Recorded `ytsearch5:oasis wonderwall` output; Spotify's Wonderwall is 258.9s.

    The official video (278s) has a video intro, and the Dublin 2025 upload is duration-perfect
    but is a live performance -- the remastered album cut should win both.
    """
    entries = [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]
    candidates = [
        YtCandidate(
            video_id=e["id"],
            url=e["url"],
            title=e["title"],
            uploader=e.get("uploader") or "",
            duration_s=float(e["duration"]),
        )
        for e in entries
    ]
    best, breakdowns = pick_best(SONG, candidates)
    assert best is not None
    assert best.video_id == "FVdjZYfDuLE"
    assert best.duration_s == 259.0
    # The (Lyrics) re-upload is the same length and title; the artist's own channel breaks the tie.
    reupload = next(b for b in breakdowns if b["video_id"] == "8LaTzWMbShY")
    chosen = next(b for b in breakdowns if b["video_id"] == "FVdjZYfDuLE")
    assert chosen["score"] == reupload["score"]
    assert chosen["channel_match"] > reupload["channel_match"]
    live = next(b for b in breakdowns if b["video_id"] == "ajHr7fEmfms")
    assert "live" in live["keywords"]
    # The official video is not rejected outright -- a ~19s intro is not a different recording.
    official = next(b for b in breakdowns if b["video_id"] == "bx1Bh8ZvH84")
    assert "rejected" not in official
