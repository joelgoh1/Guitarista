"""Ultimate Guitar adapter: search/page client, embedded-store parser, tab/chord conversion."""

from guitarista_api.adapters.ultimate_guitar.client import UGBlockedError, UGClient, UGError
from guitarista_api.adapters.ultimate_guitar.parse import (
    UGResult,
    UGTabPage,
    extract_store,
    parse_search_results,
    parse_tab_page,
)

__all__ = [
    "UGBlockedError",
    "UGClient",
    "UGError",
    "UGResult",
    "UGTabPage",
    "extract_store",
    "parse_search_results",
    "parse_tab_page",
]
