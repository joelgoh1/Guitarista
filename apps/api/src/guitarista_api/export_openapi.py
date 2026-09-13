"""Write the OpenAPI document: ``python -m guitarista_api.export_openapi <path>``."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m guitarista_api.export_openapi <output-path>", file=sys.stderr)
        return 2
    from guitarista_api.main import create_app

    out = Path(args[0])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
