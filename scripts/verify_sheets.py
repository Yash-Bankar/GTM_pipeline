"""Integration check for the Google Sheets storage layer.

Verifies the configured spreadsheet's tabs and header rows, and (optionally)
appends a test row to `IG Leads` and reads it back. Requires real service
account credentials via ``GOOGLE_APPLICATION_CREDENTIALS`` and a
``GOOGLE_SHEETS_SPREADSHEET_ID``.

Credentials are never printed. Run from the repository root:

    .\\backend\\.venv\\Scripts\\python.exe scripts\\verify_sheets.py --check-only
    .\\backend\\.venv\\Scripts\\python.exe scripts\\verify_sheets.py --create-missing-tabs --extend-headers
    .\\backend\\.venv\\Scripts\\python.exe scripts\\verify_sheets.py --write-test-row
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.sheets import (  # noqa: E402
    SCHEMAS,
    LeadStore,
    SheetsError,
    normalize_username,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Google Sheets tabs and headers.")
    parser.add_argument(
        "--create-missing-tabs",
        action="store_true",
        help="Create any missing tabs with the canonical header row.",
    )
    parser.add_argument(
        "--extend-headers",
        action="store_true",
        help="Append missing headers to existing tabs (never overwrites cells).",
    )
    parser.add_argument(
        "--write-test-row",
        action="store_true",
        help="Create a test lead in IG Leads and read it back.",
    )
    parser.add_argument(
        "--test-username",
        default="synpo_inttest_creator",
        help="Username to use for the test row (normalized before use).",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only report tab/header status (default).",
    )
    return parser.parse_args()


def _mask_spreadsheet_id(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def main() -> int:
    args = parse_args()
    settings = get_settings()

    if not settings.google_sheets_spreadsheet_id:
        print("ERROR: GOOGLE_SHEETS_SPREADSHEET_ID is not set (see .env.example).")
        return 2
    if settings.credentials_path() is None:
        print("ERROR: GOOGLE_APPLICATION_CREDENTIALS is not set (see .env.example).")
        return 2

    print(f"Spreadsheet id: {_mask_spreadsheet_id(settings.google_sheets_spreadsheet_id)}")

    try:
        store = LeadStore.from_settings(settings)
        titles = store.list_tab_titles()
    except SheetsError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 1

    print(f"Tabs present ({len(titles)}): {', '.join(titles) if titles else '(none)'}")
    print()

    failures = 0
    for key, schema in SCHEMAS.items():
        known = store.tab_name(key)
        report = store.ensure_schema(
            key,
            create_missing=args.create_missing_tabs,
            extend_headers=args.extend_headers,
        )
        status = "OK" if report.ok else "NEEDS ATTENTION"
        detail = []
        if report.created:
            detail.append("created tab")
        if report.header_written:
            detail.append("wrote header row")
        if report.missing_headers:
            detail.append(f"missing: {', '.join(report.missing_headers)}")
        if report.extended_headers:
            detail.append(f"extended: {', '.join(report.extended_headers)}")
        suffix = f" ({'; '.join(detail)})" if detail else ""
        print(f"[{status}] schema={key} tab='{known}'{suffix}")
        if not report.ok:
            failures += 1

    print()

    if args.write_test_row:
        username = args.test_username
        normalized = normalize_username(username)
        print(f"Writing test row for '@{normalized}' ...")
        try:
            lead = store.create_lead(
                username,
                source="integration-test",
                on_duplicate="return",
            )
            print(f"  leadId: {lead.lead_id}  (existing row reused if already present)")
            found = store.find_by_username(normalized)
            if found is None:
                print("  ERROR: test row could not be read back.")
                return 1
            print(f"  read back OK: username={found.username} status={found.status}")
        except SheetsError as exc:
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            return 1

    if failures:
        print(f"{failures} tab(s) need attention. Re-run with --extend-headers / --create-missing-tabs.")
        return 1

    print("Sheets storage check complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
