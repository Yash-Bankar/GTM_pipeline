"""One-off cleanup: delete garbage phone rows from the ``contacts`` table.

Removes ``type='phone'`` rows that the strict extractor in
``app.providers.emails`` would never produce - tracking codes, CSS dimension
lists, decimal prices and other numeric noise that V2-05 stored as contacts.

A row is deleted when it fails the same validation used at extraction time,
or when it clearly matches the historic failure modes:

  * more than 15 digits (E.164 maximum) - e.g. 30-digit tracking codes;
  * contains a decimal price ("3.99", "4.27");
  * contains single-digit groups - e.g. "4 4 0 0 0 3.99 4.27";
  * is not a strict, plausible phone shape.

Requires DATABASE_URL (see .env.example). Run from the repository root:

    .\\backend\\.venv\\Scripts\\python.exe scripts\\clean_garbage_phones.py

Add --dry-run to report what would be deleted without changing anything.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import sqlalchemy as sa  # noqa: E402

from app.db.database import get_engine, get_session_factory  # noqa: E402
from app.providers.emails import is_plausible_phone  # noqa: E402

DECIMAL_RE = re.compile(r"\d\.\d")
# A group of a single digit between separators ("4 4 0 0 0", "01 2.39.046").
SINGLE_DIGIT_GROUP_RE = re.compile(r"(?<![\d])\d(?![\d])")


def is_garbage_phone(value: str) -> bool:
    """True when ``value`` is not a legitimate, extractable phone number."""
    if not value:
        return True
    digits = re.sub(r"\D", "", value)
    if len(digits) > 15:  # E.164 maximum - tracking codes / long ids
        return True
    if DECIMAL_RE.search(value):  # decimal price
        return True
    if SINGLE_DIGIT_GROUP_RE.search(value):  # spaced decimals / CSS values
        return True
    return not is_plausible_phone(value)


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    engine = get_engine()
    with get_session_factory()() as session:
        rows = session.execute(
            sa.text("SELECT contact_id, value FROM contacts WHERE type = 'phone'")
        ).all()
        garbage = [(cid, value) for cid, value in rows if is_garbage_phone(value)]
        kept = len(rows) - len(garbage)
        print(f"Phone rows: {len(rows)} | keep: {kept} | garbage: {len(garbage)}")
        for cid, value in garbage[:20]:
            print(f"  - {value!r}")
        if len(garbage) > 20:
            print(f"  ... and {len(garbage) - 20} more")
        if dry_run:
            print("DRY RUN: nothing deleted.")
            return 0
        if not garbage:
            print("Nothing to delete.")
            return 0
        ids = [cid for cid, _ in garbage]
        deleted = session.execute(
            sa.text("DELETE FROM contacts WHERE contact_id = ANY(:ids)"),
            {"ids": ids},
        ).rowcount
        session.commit()
        print(f"Deleted {deleted} garbage phone rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
