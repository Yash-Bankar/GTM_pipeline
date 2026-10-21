"""Bio text normalization.

V2 policy change (V2-01): blanket pre-shortlist contact masking is withdrawn.
Public business contact details present in a captured bio or researched page are
retained and shown to authenticated operators. Credentials, private data, and
unrelated page content remain excluded from capture.

Only whitespace normalization lives here; no contact values are removed.
"""

from __future__ import annotations

import re

__all__ = ["normalize_bio"]


def normalize_bio(text: str) -> str:
    """Collapse noisy whitespace/newlines in captured bio text."""
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()
