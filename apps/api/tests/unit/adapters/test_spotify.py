from __future__ import annotations

import httpx
import pytest
import respx

from guitarista_api.adapters.spotify import SpotifyClient, SpotifyError, parse_spotify_track_id

TRACK_ID = "1qPbGZqppFwLwcBC1JQ6Vr"
TRACK_JSON = {
    "id": TRACK_ID,
    "name": "Wonderwall - Remastered",
    "artists": [{"name": "Oasis"}],
    "album": {"name": "(What's The Story) Morning Glory?", "images": [{"url": "http://img"}]},
    "duration_ms": 258000,
    "external_ids": {"isrc": "GBAAA9500123"},
}


@pytest.mark.parametrize(
    "text",
    [
        f"https://open.spotify.com/track/{TRACK_ID}?si=abc",
        f"https://open.spotify.com/intl-de/track/{TRACK_ID}",
        f"spotify:track:{TRACK_ID}",
        f"  https://open.spotify.com/track/{TRACK_ID}  ",
    ],
)
def test_parse_track_id(text: str) -> None:
    assert parse_spotify_track_id(text) == TRACK_ID


def test_parse_track_id_rejects_other_input() -> None:
    assert parse_spotify_track_id("oasis wonderwall") is None
    assert parse_spotify_track_id("https://open.spotify.com/album/abc") is None
    assert parse_spotify_track_id(None) is None


@respx.mock
async def test_token_cached_and_track_lookup() -> None:
    token_route = respx.post("https://accounts.spotify.com/api/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )
    track_route = respx.get(f"https://api.spotify.com/v1/tracks/{TRACK_ID}").mock(
        return_value=httpx.Response(200, json=TRACK_JSON)
    )
    async with httpx.AsyncClient() as http:
        client = SpotifyClient(http, "id", "secret")
        t1 = await client.track(TRACK_ID)
        t2 = await client.track(TRACK_ID)
    assert token_route.call_count == 1 and track_route.call_count == 2
    assert track_route.calls[0].request.headers["Authorization"] == "Bearer tok"
    song = t1.to_song()
    assert song.title == "Wonderwall" and song.artist == "Oasis"
    assert song.spotify_id == TRACK_ID and song.isrc == "GBAAA9500123"
    assert song.duration_s == 258.0 and song.artwork_url == "http://img"
    assert song.normalized_query == "oasis wonderwall"
    assert t2.id == TRACK_ID


@respx.mock
async def test_search_and_errors() -> None:
    respx.post("https://accounts.spotify.com/api/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )
    search = respx.get("https://api.spotify.com/v1/search").mock(
        return_value=httpx.Response(200, json={"tracks": {"items": [TRACK_JSON]}})
    )
    respx.get("https://api.spotify.com/v1/tracks/nope").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as http:
        client = SpotifyClient(http, "id", "secret")
        hits = await client.search("Wonderwall", "Oasis")
        assert len(hits) == 1
        assert search.calls[0].request.url.params["q"] == "track:Wonderwall artist:Oasis"
        with pytest.raises(SpotifyError) as exc:
            await client.track("nope")
        assert exc.value.status == 404


@respx.mock
async def test_bad_credentials() -> None:
    respx.post("https://accounts.spotify.com/api/token").mock(return_value=httpx.Response(400))
    async with httpx.AsyncClient() as http:
        with pytest.raises(SpotifyError):
            await SpotifyClient(http, "id", "bad").track(TRACK_ID)
