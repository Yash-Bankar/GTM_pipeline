"""Allow ``python -m app.worker``."""

from __future__ import annotations

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
