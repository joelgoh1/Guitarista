from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from guitarista_api.adapters import ytdlp
from guitarista_api.adapters.ytdlp import (
    YtdlpError,
    YtdlpMissing,
    search_candidates,
    search_target,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "ytdlp" / "search_wonderwall.jsonl"


class FakeProc:
    """Stands in for an asyncio subprocess: canned stdout/stderr and exit code."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self._stdout, self._stderr = stdout, stderr
        self.returncode: int | None = returncode
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout.encode(), self._stderr.encode()

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return self.returncode or 0


@pytest.fixture
def fake_exec(monkeypatch: pytest.MonkeyPatch):
    """Patch out `which` and subprocess creation; returns a recorder for the argv used."""
    recorded: dict[str, list[str]] = {}

    def install(proc: FakeProc) -> dict[str, list[str]]:
        monkeypatch.setattr(ytdlp.shutil, "which", lambda name: f"/usr/bin/{name}")

        async def fake_create(*argv: str, **_: object) -> FakeProc:
            recorded["argv"] = list(argv)
            return proc

        monkeypatch.setattr(ytdlp.asyncio, "create_subprocess_exec", fake_create)
        return recorded

    return install


def test_search_target_passes_urls_through_and_quotes_queries() -> None:
    assert search_target("https://youtu.be/abc") == "https://youtu.be/abc"
    assert search_target("  oasis wonderwall ") == 'ytsearch1:"oasis wonderwall"'


@pytest.mark.asyncio
async def test_search_candidates_parses_real_payload(fake_exec) -> None:
    recorded = fake_exec(FakeProc(stdout=FIXTURE.read_text()))
    cands = await search_candidates("oasis wonderwall", limit=5)
    assert [c.video_id for c in cands] == [
        "bx1Bh8ZvH84",
        "8LaTzWMbShY",
        "FVdjZYfDuLE",
        "6hzrDeceEKc",
        "ajHr7fEmfms",
    ]
    first = cands[0]
    assert first.title == "Oasis - Wonderwall (Official Video)"
    assert first.uploader == "Oasis"
    assert first.duration_s == 278.0
    assert first.url == "https://www.youtube.com/watch?v=bx1Bh8ZvH84"
    assert not first.is_live
    assert "ytsearch5:oasis wonderwall" in recorded["argv"]
    assert "--flat-playlist" in recorded["argv"]


@pytest.mark.asyncio
async def test_search_candidates_skips_malformed_lines(fake_exec) -> None:
    stdout = "\n".join(
        [
            '{"id": "a", "title": "One", "duration": 100}',
            "not json at all",
            "",
            '{"no_id": true}',
            "[1, 2, 3]",
            '{"id": "b", "title": "Two", "duration": null, "live_status": "is_live"}',
        ]
    )
    fake_exec(FakeProc(stdout=stdout))
    cands = await search_candidates("q")
    assert [c.video_id for c in cands] == ["a", "b"]
    assert cands[0].duration_s == 100.0
    # Missing duration stays None rather than becoming 0, which would fake an exact mismatch.
    assert cands[1].duration_s is None
    assert cands[1].is_live
    # No url in the entry -> synthesized watch URL.
    assert cands[1].url == "https://www.youtube.com/watch?v=b"


@pytest.mark.asyncio
async def test_search_candidates_empty_query_skips_subprocess(monkeypatch) -> None:
    def boom(*_: object, **__: object) -> None:
        raise AssertionError("should not shell out for an empty query")

    monkeypatch.setattr(ytdlp.asyncio, "create_subprocess_exec", boom)
    assert await search_candidates("   ") == []


@pytest.mark.asyncio
async def test_search_candidates_reports_missing_binary(monkeypatch) -> None:
    monkeypatch.setattr(ytdlp.shutil, "which", lambda _: None)
    with pytest.raises(YtdlpMissing):
        await search_candidates("oasis wonderwall")


@pytest.mark.asyncio
async def test_nonzero_exit_raises_with_stderr(fake_exec) -> None:
    fake_exec(FakeProc(stderr="ERROR: Video unavailable", returncode=1))
    with pytest.raises(YtdlpError, match="Video unavailable"):
        await search_candidates("oasis wonderwall")


@pytest.mark.asyncio
async def test_timeout_kills_the_process(monkeypatch) -> None:
    # A process that is still running reports returncode None -- that is what triggers the kill.
    proc = FakeProc()
    proc.returncode = None

    async def never(*_: object, **__: object) -> tuple[bytes, bytes]:
        await asyncio.sleep(10)
        raise AssertionError("unreachable")

    proc.communicate = never  # type: ignore[method-assign]
    monkeypatch.setattr(ytdlp.shutil, "which", lambda name: f"/usr/bin/{name}")

    async def fake_create(*_: str, **__: object) -> FakeProc:
        return proc

    monkeypatch.setattr(ytdlp.asyncio, "create_subprocess_exec", fake_create)
    with pytest.raises(TimeoutError):
        await search_candidates("oasis wonderwall", timeout_s=0.01)
    assert proc.killed
