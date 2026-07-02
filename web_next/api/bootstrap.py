from __future__ import annotations

import os
import sys


def ensure_imports() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("USE_PLAYWRIGHT_FLIGHTS", "false")
    os.environ.setdefault("SEARCH_WORKERS", "4")
