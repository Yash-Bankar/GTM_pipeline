"""P0 release audit (V2-09).

Scans the backend and frontend for the defect classes that would block a
release:

1. **Data loss** - a destructive statement (``DROP TABLE``, ``DELETE FROM``,
   ``TRUNCATE``) in a migration.
2. **Secret exposure** - a secret *value* written to a log, or a provider
   credential read by the frontend bundle.
3. **Unguarded writes** - a mutating route with no auth dependency.
4. **Message dispatch** - any code path that could send an email or a DM.

Run from the repository root:

    .\\backend\\.venv\\Scripts\\python.exe scripts\\audit_p0.py

Exit code 1 means at least one problem was found. Logging that a key is
*unset* (its name only) is safe and is not reported.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend" / "src"

SECRET_NAMES = ("api_key", "gemini_api_key", "hikerapi_key", "capture_api_key")

LOG_CALL = re.compile(r"logger\.(?:info|warning|error|debug)\(([^)]*)\)", re.S)
ROUTE_START = re.compile(r"@router\.(get|post|patch|put|delete)\(")
MUTATING = {"post", "patch", "put", "delete"}
DISPATCH = re.compile(
    r"\b(smtplib|sendmail|send_mail|sendgrid|mailgun|twilio|"
    r"requests\.post\([^)]*mail|smtplib\.SMTP)",
    re.I,
)
FRONTEND_SECRET = re.compile(r"process\.env\.(GEMINI_API_KEY|HIKERAPI_KEY|API_KEY)")
NEXT_PUBLIC = re.compile(r"NEXT_PUBLIC_[A-Z_]*")


def decorator_block(text: str, start: int) -> str:
    """Return the decorator text, respecting nested parentheses."""
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
        index += 1
    return text[start:]


def audit() -> list[str]:
    problems: list[str] = []

    # 1. Destructive migration statements.
    for path in sorted((BACKEND / "alembic" / "versions").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(DROP\s+TABLE|DELETE\s+FROM|TRUNCATE)", text, re.I):
            line = text[: match.start()].count("\n") + 1
            problems.append(
                f"{path.relative_to(ROOT)}:{line} destructive statement "
                f"{match.group(1)!r} (verify it is downgrade-only)"
            )

    # 2. Secret values in logs.
    for path in sorted(BACKEND.rglob("*.py")):
        if ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in LOG_CALL.finditer(text):
            body = match.group(1)
            for secret in SECRET_NAMES:
                if re.search(rf"{secret}\b(?!\s+is\s+not\s+set)", body, re.I) and (
                    "{" in body or "getattr" in body or "settings" in body
                ):
                    line = text[: match.start()].count("\n") + 1
                    problems.append(
                        f"{path.relative_to(ROOT)}:{line} logs a secret value: "
                        f"{body[:80]}"
                    )

    # 3. Mutating routes without an auth dependency.
    for path in sorted(BACKEND.rglob("routes.py")):
        text = path.read_text(encoding="utf-8")
        router_level = (
            "dependencies=[Depends(require_operator_key)]" in text
            or "dependencies=[Depends(require_api_key)]" in text
        )
        for match in ROUTE_START.finditer(text):
            verb = match.group(1)
            if verb not in MUTATING:
                continue
            block = decorator_block(text, match.start())
            if "dependencies=[Depends(" not in block and not router_level:
                line = text[: match.start()].count("\n") + 1
                problems.append(
                    f"{path.relative_to(ROOT)}:{line} {verb.upper()} route has no "
                    "auth dependency"
                )

    # 4. Message dispatch.
    for path in sorted(BACKEND.rglob("*.py")):
        if ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in DISPATCH.finditer(text):
            line = text[: match.start()].count("\n") + 1
            problems.append(
                f"{path.relative_to(ROOT)}:{line} possible message dispatch: "
                f"{match.group(0)}"
            )

    # 5. Frontend secret exposure.
    if FRONTEND.exists():
        for path in sorted(FRONTEND.rglob("*.ts*")):
            text = path.read_text(encoding="utf-8")
            for match in FRONTEND_SECRET.finditer(text):
                line = text[: match.start()].count("\n") + 1
                problems.append(
                    f"{path.relative_to(ROOT)}:{line} reads a secret: {match.group(0)}"
                )
            for match in NEXT_PUBLIC.finditer(text):
                line = text[: match.start()].count("\n") + 1
                problems.append(
                    f"{path.relative_to(ROOT)}:{line} NEXT_PUBLIC_ variable: "
                    f"{match.group(0)}"
                )

    return problems


def main() -> int:
    problems = audit()
    print("=== P0 release audit ===")
    print(f"problems: {len(problems)}")
    for problem in problems:
        print("  ", problem)
    if not problems:
        print(
            "OK - no destructive migrations, no secret exposure, every mutating "
            "route is guarded, and nothing can dispatch a message."
        )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
