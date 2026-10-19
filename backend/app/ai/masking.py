"""Contact-pattern masking for research evidence and AI inputs (PRD T06 / A24).

Public bio or website text can incidentally contain an email address or phone
number. Before an operator approves fit we must not retain structured contact
details, so these patterns are replaced with placeholders in persisted evidence
and in every AI input. ``business_email``/``business_phone_number`` are left
unpopulated until an explicit contact-retrieval action.
"""

from __future__ import annotations

import re

EMAIL_PLACEHOLDER = "[email hidden]"
PHONE_PLACEHOLDER = "[phone hidden]"

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# A run of digits with common separators, bounded by non-digits.
_PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s().\-]{6,}\d)(?!\d)")


def normalize_bio(text: str) -> str:
    """Collapse noisy whitespace/newlines in captured bio text."""
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def mask_contact_patterns(text: str) -> str:
    """Replace email/phone patterns with placeholders.

    Phone masking is conservative: a bare 8-digit run (e.g. a date like
    ``2026-10-19``) is kept; only longer numbers or ``+``-prefixed numbers are
    treated as phones.
    """
    value = str(text or "")
    if not value:
        return value

    value = _EMAIL_RE.sub(EMAIL_PLACEHOLDER, value)

    def _phone(match: re.Match[str]) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 10 or (raw.lstrip().startswith("+") and len(digits) >= 8):
            return PHONE_PLACEHOLDER
        return raw

    return _PHONE_RE.sub(_phone, value)
