"""Email extraction from public profile text (bio).

Ported (regex-only) from the legacy reference project's contact extractor. No
website crawling happens here — that is a later phase.
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)

BAD_EMAIL_PARTS = (
    "example.com",
    "domain.com",
    "email.com",
    "sentry.io",
    "wixpress.com",
    "schema.org",
)
BAD_EMAIL_SUFFIXES = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".avif",
)


def clean_email(email: str) -> str:
    return email.strip(" .,:;()[]{}<>").lower()


def extract_emails(text: str) -> list[str]:
    """Return sorted, de-duplicated, plausible emails found in ``text``."""
    if not text:
        return []
    found: list[str] = []
    for raw in EMAIL_RE.findall(text):
        email = clean_email(raw)
        if (
            not any(bad in email for bad in BAD_EMAIL_PARTS)
            and not email.endswith(BAD_EMAIL_SUFFIXES)
            and not email.startswith(("cropped-", "logo-", "image-", "icon-"))
            and "u003e" not in email
            and "u003c" not in email
        ):
            found.append(email)
    return sorted(set(found))
