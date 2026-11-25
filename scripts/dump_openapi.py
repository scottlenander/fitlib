"""Print the API's OpenAPI description as JSON, for generating the web app's types.

    uv run python scripts/dump_openapi.py > web/openapi.json

Builds the app without opening any library, so it needs no config. Routes offered only
under some settings (``POST /api/app/quit``) are included, so the web app has their types.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fitlib.api import create_app
from fitlib.config import Config


def main() -> None:
    """Write the OpenAPI JSON to stdout, with stable key order."""
    app = create_app(Config(library=Path("unused")), allow_quit=True)
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
