"""LLM assist boundary.

The tab pipeline is deterministic first; an LLM is consulted only for narrow, single-shot tasks
(re-ranking ambiguous search candidates, rewriting a failed query, pulling a tab out of messy
text). ``LLMClient`` is the protocol, ``NullLLM`` never answers, and ``OpenRouterLLM`` talks to
any OpenAI-compatible ``/chat/completions`` endpoint (OpenRouter by default).

Every method is best-effort: on any failure it returns "no opinion" (``None`` or the input
unchanged) and records why in ``last_error`` so tier logs can report ``llm_used`` honestly.
Structured output uses ``response_format={"type": "json_schema", ...}``; models/providers that
reject it (HTTP 400) get a plain "reply with only JSON" prompt and tolerant parsing instead.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol, runtime_checkable

import httpx
import structlog
from pydantic import ValidationError

from guitarista_api.domain.song import Song, SongCandidate
from guitarista_api.domain.tab import Tab
from guitarista_api.domain.validate import validate_tab

log = structlog.get_logger(__name__)


@runtime_checkable
class LLMClient(Protocol):
    """Every method may return ``None`` meaning "no opinion"; callers must keep a fallback."""

    last_error: str | None
    """Why the most recent call declined (``None`` after a successful call)."""

    async def rank_candidates(
        self, song: Song, candidates: list[SongCandidate]
    ) -> list[SongCandidate] | None:
        """Return the candidates re-ordered best-first (scores may be adjusted), or ``None``."""
        ...

    async def rewrite_query(self, song: Song, failed_queries: list[str]) -> str | None:
        """Return a different search query worth trying after ``failed_queries``, or ``None``."""
        ...

    async def extract_tab_text(self, text: str, tuning: list[int]) -> Tab | None:
        """Return a validated canonical ``Tab`` extracted from messy tab text, or ``None``."""
        ...


class NullLLM:
    """Stand-in used when no LLM is configured; every call declines."""

    last_error: str | None = "no LLM configured"

    async def rank_candidates(
        self, song: Song, candidates: list[SongCandidate]
    ) -> list[SongCandidate] | None:
        return None

    async def rewrite_query(self, song: Song, failed_queries: list[str]) -> str | None:
        return None

    async def extract_tab_text(self, text: str, tuning: list[int]) -> Tab | None:
        return None


# --------------------------------------------------------------------------- OpenRouter

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "qwen/qwen3.8-flash"
REFERER = "https://github.com/joel/guitarista"
APP_TITLE = "Guitarista"
MAX_TAB_TEXT_CHARS = 12000

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)

_RANK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ranking": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "score": {"type": "number"},
                },
                "required": ["index", "score"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ranking"],
    "additionalProperties": False,
}
_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": False,
}
_TAB_EXCLUDED_FIELDS = ("id", "created_at", "song_id", "source", "source_ref", "confidence")


def tab_llm_schema() -> dict[str, Any]:
    """``Tab.model_json_schema()`` minus ids/dates/provenance the model must not invent."""
    schema = Tab.model_json_schema()
    props = schema.get("properties", {})
    for name in _TAB_EXCLUDED_FIELDS:
        props.pop(name, None)
    schema["required"] = [r for r in schema.get("required", []) if r in props]
    schema.pop("title", None)
    return schema


def parse_json_reply(content: str) -> Any:
    """``json.loads`` that tolerates ``\\`\\`\\`json`` fences and prose around the object."""
    text = _FENCE_RE.sub("", content.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        if start < 0:
            raise
        end = max(text.rfind("}"), text.rfind("]"))
        return json.loads(text[start : end + 1])


class OpenRouterLLM:
    """OpenAI-compatible chat-completions client with JSON-schema output + plain-JSON fallback."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 30.0,
    ) -> None:
        self.http = http
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.last_error: str | None = None
        self.supports_json_schema: bool | None = None
        """Learned per process: ``False`` after the first 400 on ``response_format``."""

    # ------------------------------------------------------------------ public API

    async def rank_candidates(
        self, song: Song, candidates: list[SongCandidate]
    ) -> list[SongCandidate] | None:
        self.last_error = None
        if len(candidates) < 2:
            return candidates
        listing = "\n".join(
            f"{i}. {c.song.artist} - {c.song.title} (source score {c.score:.2f})"
            for i, c in enumerate(candidates)
        )
        system = (
            "You match a requested song to search results from a guitar tab site. Consider "
            "artist, title, remixes/covers/live versions (prefer the original studio version) "
            "and obvious typos. Return every index exactly once, best match first, each with "
            "a confidence score between 0 and 1."
        )
        user = (
            f"Requested song: {song.artist or '(unknown artist)'} - {song.title}\n"
            f"Original query: {song.normalized_query}\n\nCandidates:\n{listing}"
        )
        try:
            data = await self._complete_json(system, user, _RANK_SCHEMA, "candidate_ranking")
            ranking = data["ranking"] if isinstance(data, dict) else None
            if not isinstance(ranking, list) or not ranking:
                raise ValueError("ranking missing")
            ordered: list[SongCandidate] = []
            seen: set[int] = set()
            for item in ranking:
                idx = int(item["index"])
                if idx in seen or not 0 <= idx < len(candidates):
                    continue
                seen.add(idx)
                score = max(0.0, min(1.0, float(item.get("score", candidates[idx].score))))
                ordered.append(candidates[idx].model_copy(update={"score": round(score, 4)}))
            if not ordered:
                raise ValueError("ranking had no valid indices")
            ordered.extend(c for i, c in enumerate(candidates) if i not in seen)
            return ordered
        except Exception as exc:  # any failure -> deterministic order stands
            self._fail("rank_candidates", exc)
            return candidates

    async def rewrite_query(self, song: Song, failed_queries: list[str]) -> str | None:
        self.last_error = None
        system = (
            "You help search a guitar tab website. Given the song and queries that returned no "
            "results, suggest ONE different, shorter search query: fix typos, drop noise like "
            "'official video', 'lyrics', 'remastered', feat. credits and years; use the most "
            "common spelling of artist and title."
        )
        user = (
            f"Song: {song.artist or '(unknown artist)'} - {song.title}\n"
            f"Failed queries: {json.dumps(failed_queries)}"
        )
        try:
            data = await self._complete_json(system, user, _QUERY_SCHEMA, "search_query")
            query = str(data["query"]).strip() if isinstance(data, dict) else ""
            if not query or query.lower() in {q.lower().strip() for q in failed_queries}:
                raise ValueError("no new query suggested")
            return query[:200]
        except Exception as exc:
            self._fail("rewrite_query", exc)
            return None

    async def extract_tab_text(self, text: str, tuning: list[int]) -> Tab | None:
        self.last_error = None
        schema = tab_llm_schema()
        system = (
            "You convert guitar tablature or chord sheets written as plain text into a strict "
            "JSON tab document. Conventions: 'string' is 1-based and string 1 is the HIGHEST "
            "pitched (thinnest) string, which is the TOP line of ASCII tab; 'fret' is 0..24; "
            "'pitch_midi' may be omitted; durations are fractions of a whole note "
            "({num:1, den:8} = eighth). When rhythm is unknown use eighths and put 8 beats per "
            "measure. Put chord symbols in 'chord_name'. Ignore lyrics, comments and ads. "
            "Return only the JSON document."
        )
        user = f"Tuning (MIDI, string 1 first): {tuning}\n\nTab text:\n{text[:MAX_TAB_TEXT_CHARS]}"
        try:
            data = await self._complete_json(system, user, schema, "guitar_tab")
            if not isinstance(data, dict):
                raise ValueError("reply is not an object")
            for name in _TAB_EXCLUDED_FIELDS:
                data.pop(name, None)
            tab = Tab.model_validate(data)
            tab.confidence = 0.4
            tab.warnings.append("tab structure extracted by LLM from page text; verify carefully")
            _fill_pitches(tab, tuning)
            errors = validate_tab(tab)
            if errors:
                raise ValueError(f"tab failed validation: {errors[:3]}")
            if not any(
                n
                for t in tab.tracks
                for m in t.measures
                for v in m.voices
                for b in v.beats
                for n in b.notes
            ):
                raise ValueError("tab has no notes")
            return tab
        except (ValidationError, ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
            self._fail("extract_tab_text", exc)
            return None
        except Exception as exc:
            self._fail("extract_tab_text", exc)
            return None

    # ------------------------------------------------------------------ transport

    async def _complete_json(
        self, system: str, user: str, schema: dict[str, Any], name: str
    ) -> Any:
        """Chat completion returning parsed JSON; tries ``json_schema`` first, then plain JSON."""
        if self.supports_json_schema is not False:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": schema},
            }
            response = await self._post(system, user, response_format=response_format)
            if response.status_code == 400:
                log.info("llm.json_schema_unsupported", model=self.model, body=response.text[:200])
                self.supports_json_schema = False
            else:
                response.raise_for_status()
                self.supports_json_schema = True
                return parse_json_reply(_content(response.json()))
        plain_user = (
            f"{user}\n\nReply with ONLY a JSON document (no prose, no code fences) matching this "
            f"JSON schema:\n{json.dumps(schema)}"
        )
        response = await self._post(system, plain_user)
        response.raise_for_status()
        return parse_json_reply(_content(response.json()))

    async def _post(
        self, system: str, user: str, *, response_format: dict[str, Any] | None = None
    ) -> httpx.Response:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        if response_format is not None:
            body["response_format"] = response_format
        return await self.http.post(
            f"{self.base_url}/chat/completions",
            json=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": REFERER,
                "X-Title": APP_TITLE,
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )

    def _fail(self, method: str, exc: BaseException) -> None:
        self.last_error = f"{type(exc).__name__}: {exc}"[:300]
        log.warning("llm.declined", method=method, model=self.model, error=self.last_error)


def _content(payload: Any) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("completion has no message content") from exc
    if isinstance(content, list):  # some providers return content parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("completion content is empty")
    return content


def _fill_pitches(tab: Tab, tuning: list[int]) -> None:
    for track in tab.tracks:
        if not track.tuning or len(track.tuning) != len(tuning):
            track.tuning = list(tuning)
        for measure in track.measures:
            for voice in measure.voices:
                for beat in voice.beats:
                    for note in beat.notes:
                        if (
                            note.pitch_midi is None
                            and not note.dead
                            and note.string <= len(track.tuning)
                        ):
                            note.pitch_midi = track.tuning[note.string - 1] + track.capo + note.fret
