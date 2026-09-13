"""Write the canonical Tab JSON schema: ``python -m guitarista_api.export_schema <path>``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from guitarista_api.domain.tab import Tab


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m guitarista_api.export_schema <output-path>", file=sys.stderr)
        return 2
    out = Path(args[0])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(Tab.model_json_schema(), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
