from __future__ import annotations

from pathlib import Path

import pytest

from guitarista_api.adapters.ultimate_guitar.convert import parse_ascii_tab
from guitarista_api.adapters.ultimate_guitar.parse import (
    UGBlockedError,
    UGParseError,
    extract_store,
    is_blocked,
    parse_search_results,
    parse_tab_page,
)
from guitarista_api.sources.base import SourceError

FIXTURES = Path(__file__).parents[2] / "fixtures" / "ug"

CLOUDFLARE_HTML = """<!DOCTYPE html><html><head><title>Just a moment...</title></head>
<body><div id="cf-challenge" class="cf-browser-verification">Checking your browser</div>
</body></html>"""


@pytest.fixture(scope="module")
def search_html() -> str:
    return (FIXTURES / "search.html").read_text()


@pytest.fixture(scope="module")
def chords_html() -> str:
    return (FIXTURES / "tab_chords_6125.html").read_text()


@pytest.fixture(scope="module")
def tabs_html() -> str:
    return (FIXTURES / "tab_tabs.html").read_text()


def test_extract_store_on_all_fixtures(search_html: str, chords_html: str, tabs_html: str) -> None:
    for html in (search_html, chords_html, tabs_html):
        store = extract_store(html)
        assert isinstance(store["page"]["data"], dict)
    assert len(extract_store(search_html)["page"]["data"]["results"]) == 52


def test_extract_store_legacy_ugapp() -> None:
    html = '<script>window.UGAPP.store.page = {"data": {"results": []}};\n</script>'
    assert extract_store(html) == {"page": {"data": {"results": []}}}
    with pytest.raises(UGParseError):
        extract_store("<html><body>nothing here</body></html>")


def test_cloudflare_interstitial_is_a_source_error() -> None:
    assert is_blocked(CLOUDFLARE_HTML)
    with pytest.raises(SourceError) as exc:
        extract_store(CLOUDFLARE_HTML)
    assert isinstance(exc.value, UGBlockedError)
    assert exc.value.user_message == "Ultimate Guitar blocked the request"


def test_search_results_skip_official_and_pro_rows(search_html: str) -> None:
    results = parse_search_results(extract_store(search_html))
    assert len(results) == 50  # 52 rows minus the two id: null official/pro entries
    assert all(r.id and r.tab_url.startswith("https://tabs.ultimate-guitar.com/") for r in results)
    types = {r.type for r in results}
    assert {"Chords", "Tabs"} <= types and None not in types
    top = next(r for r in results if r.id == 6125)
    assert top.type == "Chords" and top.artist_name == "Oasis" and top.song_name == "Wonderwall"
    assert top.rating and top.rating > 4.5 and top.votes == 2497


def test_chords_page_metadata_and_sequence(chords_html: str) -> None:
    page = parse_tab_page(extract_store(chords_html))
    assert page.id == 6125 and page.is_chords
    assert page.tonality == "F#m" and page.capo is None
    assert page.tuning_value == "E A D G B E" and page.tuning_name == "Standard"
    import re

    chords = re.findall(r"\[ch\](.*?)\[/ch\]", page.content)
    assert chords[:4] == ["F#m7", "A", "Esus4", "B7sus4"]


def test_tabs_page_ascii_parse_first_chord(tabs_html: str) -> None:
    page = parse_tab_page(extract_store(tabs_html))
    assert page.type == "Tabs" and page.capo == 2 and page.tonality == "F#m"
    parsed = parse_ascii_tab(page.content)
    assert parsed.systems == 4 and parsed.note_count > 100
    first = {n.string: n.fret for n in parsed.beats[0].notes}
    assert first == {1: 3, 2: 3, 3: 0, 4: 2, 5: 2, 6: 0}  # Em7-shaped intro chord
    assert any("no rhythm" in w for w in parsed.warnings)
