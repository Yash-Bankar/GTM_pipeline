"""Email extraction from public profile text (bio).

Ported (regex-only) from the legacy reference project's contact extractor. No
website crawling happens here — that is a later phase.
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
# Digits with common separators; validated by digit count below.
PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s().\-]{6,}\d)(?!\d)")

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


def extract_phones(text: str) -> list[str]:
    """Return plausible publicly listed phone numbers found in ``text``.

    Conservative: an 8-digit run (e.g. a date) is not a phone; at least 10 digits
    are required, or 8+ digits with a leading ``+``.
    """
    if not text:
        return []
    found: set[str] = set()
    for raw in PHONE_RE.findall(text):
        value = re.sub(r"\s+", " ", raw).strip()
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 10 or (value.startswith("+") and len(digits) >= 8):
            found.add(value)
    return sorted(found)
