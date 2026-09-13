from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_ML_SCRIPT = FIXTURES / "fake_ml" / "guitarista_ml_fake.py"
FAKE_ML_CMD = f"{sys.executable} {FAKE_ML_SCRIPT}"

# Every Settings() built in tests drives the stdlib fake sidecar instead of `uv run ../ml`,
# unless a test overrides ``ml_cmd`` explicitly (the ``ml``-marked real-sidecar test does).
os.environ.setdefault("GUITARISTA_ML_CMD", FAKE_ML_CMD)


@pytest.fixture(scope="session")
def fake_ml_cmd() -> str:
    return FAKE_ML_CMD


@pytest.fixture(scope="session")
def twinkle_path() -> Path:
    return FIXTURES / "scores" / "twinkle.musicxml"


@pytest.fixture(scope="session")
def twinkle_bytes(twinkle_path: Path) -> bytes:
    return twinkle_path.read_bytes()


@pytest.fixture(scope="session")
def twinkle_mscz_bytes() -> bytes:
    """Same music as ``twinkle_bytes``, saved by MuseScore 4 (used by the ``musescore`` marker)."""
    return (FIXTURES / "scores" / "twinkle.mscz").read_bytes()


@pytest.fixture(scope="session")
def twinkle_midi_bytes() -> bytes:
    return (FIXTURES / "scores" / "twinkle.mid").read_bytes()


SONGSTERR_FIXTURES = FIXTURES / "songsterr"


@pytest.fixture(scope="session")
def songsterr_fixtures() -> dict[str, object]:
    import json

    return {
        "search": json.loads((SONGSTERR_FIXTURES / "songs_search.json").read_text()),
        "meta": json.loads((SONGSTERR_FIXTURES / "meta_2.json").read_text()),
        "track_3": json.loads((SONGSTERR_FIXTURES / "track_2_3.json").read_text()),
        "track_6": json.loads((SONGSTERR_FIXTURES / "track_2_6.json").read_text()),
    }
