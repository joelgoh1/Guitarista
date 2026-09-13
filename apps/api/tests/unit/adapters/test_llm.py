from __future__ import annotations

import json

import httpx
import pytest
import respx

from guitarista_api.adapters.llm import LLMClient, NullLLM, OpenRouterLLM, parse_json_reply
from guitarista_api.domain.song import Song, SongCandidate

URL = "https://openrouter.ai/api/v1/chat/completions"
SONG = Song(id="s", title="Wonderwall", artist="Oasis")
CANDS = [
    SongCandidate(
        song=Song(id="c:1", title="Wonderwall (live)", artist="Oasis"), score=0.8, source="x"
    ),
    SongCandidate(song=Song(id="c:2", title="Wonderwall", artist="Oasis"), score=0.79, source="x"),
]


def _reply(content: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})


@pytest.fixture
async def llm():
    async with httpx.AsyncClient() as http:
        yield OpenRouterLLM(http, "key", model="test/model", timeout=5)


def test_protocol_conformance() -> None:
    assert isinstance(NullLLM(), LLMClient)


def test_parse_json_reply_tolerates_fences_and_prose() -> None:
    assert parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_reply('Sure! {"a": [1, 2]} hope that helps') == {"a": [1, 2]}
    with pytest.raises(json.JSONDecodeError):
        parse_json_reply("no json here")


@respx.mock
async def test_rank_candidates_json_schema_success(llm: OpenRouterLLM) -> None:
    route = respx.post(URL).mock(
        return_value=_reply(
            json.dumps({"ranking": [{"index": 1, "score": 0.95}, {"index": 0, "score": 0.3}]})
        )
    )
    ranked = await llm.rank_candidates(SONG, CANDS)
    assert [c.song.id for c in ranked] == ["c:2", "c:1"]
    assert ranked[0].score == 0.95 and llm.last_error is None
    req = route.calls[0].request
    assert req.headers["Authorization"] == "Bearer key"
    assert req.headers["HTTP-Referer"] == "https://github.com/joel/guitarista"
    assert req.headers["X-Title"] == "Guitarista"
    body = json.loads(req.content)
    assert body["model"] == "test/model"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert llm.supports_json_schema is True


@respx.mock
async def test_400_on_response_format_falls_back_to_plain_json(llm: OpenRouterLLM) -> None:
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(400, json={"error": {"message": "response_format not supported"}}),
            _reply('```json\n{"query": "oasis wonderwall"}\n```'),
        ]
    )
    query = await llm.rewrite_query(SONG, ["oasis wonderwall official video"])
    assert query == "oasis wonderwall" and llm.last_error is None
    assert route.call_count == 2
    first, second = (json.loads(c.request.content) for c in route.calls)
    assert "response_format" in first and "response_format" not in second
    assert "ONLY a JSON document" in second["messages"][1]["content"]
    assert llm.supports_json_schema is False
    # later calls skip straight to the plain prompt
    route.mock(return_value=_reply('{"query": "wonderwall"}'))
    assert await llm.rewrite_query(SONG, ["x"]) == "wonderwall"
    assert route.call_count == 3


@respx.mock
async def test_garbage_replies_decline_gracefully(llm: OpenRouterLLM) -> None:
    respx.post(URL).mock(return_value=_reply("I cannot help with that."))
    assert await llm.rank_candidates(SONG, CANDS) == CANDS
    assert llm.last_error and "JSONDecodeError" in llm.last_error
    assert await llm.rewrite_query(SONG, ["q"]) is None and llm.last_error
    assert await llm.extract_tab_text("e|--3--|", [64, 59, 55, 50, 45, 40]) is None

    respx.post(URL).mock(return_value=httpx.Response(500, text="boom"))
    assert await llm.rank_candidates(SONG, CANDS) == CANDS and "500" in (llm.last_error or "")
    respx.post(URL).mock(side_effect=httpx.ConnectError("down"))
    assert await llm.rewrite_query(SONG, ["q"]) is None


@respx.mock
async def test_rewrite_query_rejects_repeats(llm: OpenRouterLLM) -> None:
    respx.post(URL).mock(return_value=_reply('{"query": "Oasis Wonderwall"}'))
    assert await llm.rewrite_query(SONG, ["oasis wonderwall"]) is None


@respx.mock
async def test_extract_tab_text_validates_and_fills_pitches(llm: OpenRouterLLM) -> None:
    tuning = [64, 59, 55, 50, 45, 40]
    good = {
        "title": "Riff",
        "tracks": [
            {
                "tuning": tuning,
                "measures": [
                    {
                        "number": 1,
                        "voices": [
                            {
                                "beats": [
                                    {
                                        "duration": {"num": 1, "den": 8},
                                        "notes": [{"string": 1, "fret": 3}],
                                    }
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
    }
    respx.post(URL).mock(return_value=_reply(json.dumps(good)))
    tab = await llm.extract_tab_text("e|-3-|", tuning)
    assert tab is not None and tab.confidence == 0.4
    assert tab.tracks[0].measures[0].voices[0].beats[0].notes[0].pitch_midi == 67
    assert any("LLM" in w for w in tab.warnings)

    bad = json.loads(json.dumps(good))
    bad["tracks"][0]["measures"][0]["voices"][0]["beats"][0]["notes"][0]["pitch_midi"] = 10
    respx.post(URL).mock(return_value=_reply(json.dumps(bad)))
    assert await llm.extract_tab_text("e|-3-|", tuning) is None
    assert "validation" in (llm.last_error or "")
    respx.post(URL).mock(return_value=_reply('{"title": "empty", "tracks": []}'))
    assert await llm.extract_tab_text("x", tuning) is None
