from __future__ import annotations

import stat
from pathlib import Path

import pytest

from guitarista_api.adapters.musescore import (
    MuseScoreError,
    MuseScoreMissing,
    musescore_available,
    resolve_mscore,
    to_musicxml,
)


def _fake_bin(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture(autouse=True)
def _clear_cache():
    resolve_mscore.cache_clear()
    yield
    resolve_mscore.cache_clear()


def test_resolve_is_none_when_nothing_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", ())
    monkeypatch.setenv("PATH", "")
    assert resolve_mscore("definitely-not-a-real-binary") is None
    assert musescore_available("definitely-not-a-real-binary") is False


def test_an_explicit_binary_disables_the_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pointing GUITARISTA_MSCORE_BIN at nothing is how you switch the feature off."""
    installed = _fake_bin(tmp_path / "mscore-installed", "exit 0")
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", (str(installed),))
    assert resolve_mscore("mscore") == str(installed)  # default hint -> auto-detect
    resolve_mscore.cache_clear()
    assert resolve_mscore("/nonexistent/mscore") is None  # explicit hint wins


def test_resolve_honours_an_explicit_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", ())
    fake = _fake_bin(tmp_path / "my-mscore", "exit 0")
    assert resolve_mscore(str(fake)) == str(fake)


def test_resolve_falls_back_to_a_known_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake_bin(tmp_path / "mscore-alt", "exit 0")
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", (str(fake),))
    monkeypatch.setenv("PATH", "")
    # the default hint is not on PATH, so the well-known locations are consulted
    assert resolve_mscore("mscore") == str(fake)


async def test_missing_binary_raises_with_an_install_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", ())
    monkeypatch.setenv("PATH", "")
    with pytest.raises(MuseScoreMissing) as exc:
        await to_musicxml(tmp_path / "in.mscz", tmp_path / "out.musicxml", mscore_bin="nope")
    assert "musescore.org" in str(exc.value)


async def test_nonzero_exit_reports_the_real_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake_bin(
        tmp_path / "mscore",
        'echo "qt.qml.typeregistration: noise" >&2\necho "cannot read file" >&2\nexit 1',
    )
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", ())
    with pytest.raises(MuseScoreError) as exc:
        await to_musicxml(tmp_path / "in.mscz", tmp_path / "out.musicxml", mscore_bin=str(fake))
    # the Qt chatter is filtered out; the actionable line survives
    assert "cannot read file" in str(exc.value)
    assert "typeregistration" not in str(exc.value)


async def test_exit_zero_without_output_is_still_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MuseScore exits 0 while writing nothing for some inputs -- the file is the success signal."""
    fake = _fake_bin(tmp_path / "mscore", "exit 0")
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", ())
    with pytest.raises(MuseScoreError):
        await to_musicxml(tmp_path / "in.mscz", tmp_path / "out.musicxml", mscore_bin=str(fake))


async def test_empty_output_is_cleaned_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dst = tmp_path / "out.musicxml"
    fake = _fake_bin(tmp_path / "mscore", f'touch "{dst}"\nexit 0')
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", ())
    with pytest.raises(MuseScoreError):
        await to_musicxml(tmp_path / "in.mscz", dst, mscore_bin=str(fake))
    assert not dst.exists()


async def test_timeout_kills_the_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_bin(tmp_path / "mscore", "sleep 10")
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", ())
    with pytest.raises(MuseScoreError, match="timed out"):
        await to_musicxml(
            tmp_path / "in.mscz", tmp_path / "out.musicxml", mscore_bin=str(fake), timeout_s=0.3
        )


async def test_success_returns_the_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dst = tmp_path / "nested" / "out.musicxml"
    fake = _fake_bin(tmp_path / "mscore", f'mkdir -p "{dst.parent}"\necho "<score/>" > "{dst}"')
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", ())
    assert await to_musicxml(tmp_path / "in.mscz", dst, mscore_bin=str(fake)) == dst
    assert dst.read_text().strip() == "<score/>"


async def test_offscreen_platform_only_on_linux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Headless Linux needs ``offscreen``; macOS only ships ``cocoa`` and fails to start with it."""
    dst = tmp_path / "out.musicxml"
    fake = _fake_bin(tmp_path / "mscore", f'echo "[$QT_QPA_PLATFORM]" > "{dst}"')
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", ())
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)

    monkeypatch.setattr("guitarista_api.adapters.musescore.sys.platform", "linux")
    await to_musicxml(tmp_path / "in.mscz", dst, mscore_bin=str(fake))
    assert dst.read_text().strip() == "[offscreen]"

    monkeypatch.setattr("guitarista_api.adapters.musescore.sys.platform", "darwin")
    await to_musicxml(tmp_path / "in.mscz", dst, mscore_bin=str(fake))
    assert dst.read_text().strip() == "[]"


async def test_explicit_qt_platform_is_respected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dst = tmp_path / "out.musicxml"
    fake = _fake_bin(tmp_path / "mscore", f'echo "$QT_QPA_PLATFORM" > "{dst}"')
    monkeypatch.setattr("guitarista_api.adapters.musescore.FALLBACK_BINARIES", ())
    monkeypatch.setattr("guitarista_api.adapters.musescore.sys.platform", "linux")
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")
    await to_musicxml(tmp_path / "in.mscz", dst, mscore_bin=str(fake))
    assert dst.read_text().strip() == "wayland"
