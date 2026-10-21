"""Email and phone extraction from public profile/page text.

Ported (regex-only) from the legacy reference project's contact extractor. No
website crawling happens here - that is a later phase.

Both extractors are deliberately **conservative**: a false positive (a fabricated
contact) is worse than a missed one (PRD 4.4 - never guess addresses).
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
# A phone candidate is a run of digits and phone separators (space, dash, dot,
# parentheses). Runs are matched whole so a 30-digit tracking code is never
# partially matched as a shorter "phone".
PHONE_TOKEN_RE = re.compile(r"[\+()\d][\d\s().\-]*[\d)]|\+")
# Strict shape: an optional country code or first group (optionally in
# parentheses) followed by further groups separated by a single space, dash or
# dot. No empty groups, no repeated separators.
PHONE_SHAPE_RE = re.compile(
    r"^\+?(?:\(\d{2,4}\)|\d{1,4})(?:[ \-.]?(?:\(\d{2,4}\)|\d{2,6}))*$"
)
# Pure E.164 form: "+" followed by 7-15 digits.
E164_RE = re.compile(r"^\+\d{7,15}$")
# Date-like values (2026-10-19, 19.10.2026, 10/19/2026) are not phone numbers.
DATE_LIKE_RE = re.compile(
    r"^\d{4}[-./ ]\d{1,2}[-./ ]\d{1,2}$|^\d{1,2}[-./ ]\d{1,2}[-./ ]\d{4}$"
)

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
# Retina/image filename emails, e.g. "logo@2x.png" or "hero@3x.jpg".
IMAGE_FILENAME_EMAIL_RE = re.compile(
    r"@\d+x\.(?:png|jpe?g|gif|webp|svg|avif)$", re.IGNORECASE
)
# Machine/transactional senders that are never a creator's contact.
BAD_EMAIL_LOCALS = (
    "noreply",
    "no-reply",
    "no_reply",
    "donotreply",
    "do-not-reply",
    "mailer-daemon",
    "postmaster",
)

# E.164 allows at most 15 digits. The legacy extractor required 10 digits (or
# 8 with a country code); keeping that floor rejects short numeric noise such
# as CSS values ("1000 1000", "11.03 11.68") without losing real numbers.
PHONE_MIN_DIGITS = 10
PHONE_MIN_DIGITS_E164 = 8
PHONE_MAX_DIGITS = 15
PHONE_MAX_GROUPS = 6


def clean_email(email: str) -> str:
    return email.strip(" .,:;()[]{}<>").lower()


def _is_plausible_email(email: str) -> bool:
    local, _, domain = email.partition("@")
    if not local or not domain:
        return False
    if any(bad in email for bad in BAD_EMAIL_PARTS):
        return False
    if email.endswith(BAD_EMAIL_SUFFIXES):
        return False
    if IMAGE_FILENAME_EMAIL_RE.search(email):
        return False
    if local in BAD_EMAIL_LOCALS:
        return False
    if email.startswith(("cropped-", "logo-", "image-", "icon-")):
        return False
    if "u003e" in email or "u003c" in email:
        return False
    return True


def extract_emails(text: str) -> list[str]:
    """Return sorted, de-duplicated, plausible emails found in ``text``."""
    if not text:
        return []
    found: list[str] = []
    for raw in EMAIL_RE.findall(text):
        email = clean_email(raw)
        if _is_plausible_email(email):
            found.append(email)
    return sorted(set(found))


def _digit_groups(value: str) -> list[str]:
    return re.findall(r"\d+", value)


def is_plausible_phone(value: str) -> bool:
    """Strictly validate one phone candidate (E.164-shaped).

    A candidate is accepted only when ALL of these hold:
    1. the text is a strict phone shape - optional country code, then groups
       separated by single spaces/dashes/dots, optionally parenthesised;
    2. at least 10 digits in total (8 with a leading ``+``) and never more
       than 15, the E.164 maximum;
    3. it is not a date (2026-10-19, 19.10.2026);
    4. group sizes: with a leading ``+`` the first group is a 1-3 digit country
       code; without it the first group is 2-4 digits; every other group is
       2-4 digits, so spaced decimals such as "3.99 4.27" are rejected;
    5. at most 6 groups;
    6. the digits are not all identical (0000000000).

    This rejects tracking codes ("35771933781168458101792575716"), CSS
    dimension lists ("0 2.17-.01 2.444-.046 ...") and decimal prices while
    keeping standard formats: "+1 (415) 555-0199", "415-555-0199",
    "020 7946 0958", "01 23 45 67 89", "+14155550199".
    """
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if not value:
        return False
    if not PHONE_SHAPE_RE.match(value):
        return False
    if DATE_LIKE_RE.match(value):
        return False

    groups = _digit_groups(value)
    if not groups:
        return False
    digits = "".join(groups)
    has_plus = value.startswith("+")
    min_digits = PHONE_MIN_DIGITS_E164 if has_plus else PHONE_MIN_DIGITS
    if not min_digits <= len(digits) <= PHONE_MAX_DIGITS:
        return False
    if len(set(digits)) == 1:  # 0000000000 / 1111111111
        return False

    if len(groups) == 1:
        # A bare contiguous run (ID, hash, timestamp) is unverifiable; only the
        # pure E.164 form "+<digits>" is accepted.
        return bool(E164_RE.match(value))

    if len(groups) > PHONE_MAX_GROUPS:
        return False

    first, rest = groups[0], groups[1:]
    if has_plus:
        if not 1 <= len(first) <= 3:
            return False
    elif not 2 <= len(first) <= 4:
        return False
    return all(2 <= len(group) <= 4 for group in rest)


def extract_phones(text: str) -> list[str]:
    """Return plausible publicly listed phone numbers found in ``text``."""
    if not text:
        return []
    found: set[str] = set()
    for raw in PHONE_TOKEN_RE.findall(text):
        value = re.sub(r"\s+", " ", raw).strip().strip("-,.")
        if is_plausible_phone(value):
            found.add(value)
    return sorted(found)
