"""Evidence versioning, recency, and safe snapshot merging (V2-02).

Pure helpers used by the lead intake service:

- capture payload hashing (request-id conflict detection)
- deterministic recency from the server receipt time, clamping future client clocks
- field-level merge that never erases known values and lets only newer evidence
  update known fields
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

__all__ = [
    "changed_snapshot_fields",
    "field_provenance",
    "is_contact_only_change",
    "material_change_reasons",
    "merge_snapshot",
    "payload_hash",
    "recency",
    "strip_contacts",
]

_STRING_FIELDS = ("display_name", "bio", "source_url", "captured_at", "parser_version")
_COUNT_FIELDS = ("followers", "following", "post_count")
_MATERIAL_FIELDS = (
    "display_name",
    "bio",
    "is_verified",
    "external_urls",
    "followers",
    "following",
    "post_count",
)
# Client clocks further than this ahead of the server receipt are not trusted.
_CLOCK_SKEW_TOLERANCE = timedelta(seconds=300)

# Contact details inside free text. A bio that only gains or loses a contact
# is a *contact-only* change and is not material (PRD V15).
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().\-]{6,}\d(?!\w)")
# A handle must not start inside an email address or a URL.
_HANDLE_RE = re.compile(r"(?<![\w.+-])@\w[\w.]*")


def strip_contacts(text: str) -> str:
    """Return ``text`` with contact details removed.

    Used to tell a *contact-only* bio change (a new email or handle) apart
    from a real content change. The PRD treats the former as non-material: it
    must not force a shortlist back into "Review needed".
    """
    if not text:
        return ""
    cleaned = _EMAIL_RE.sub(" ", text)
    cleaned = _URL_RE.sub(" ", cleaned)
    cleaned = _PHONE_RE.sub(" ", cleaned)
    cleaned = _HANDLE_RE.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _contact_tokens(text: str) -> set[str]:
    """Return the contact tokens (emails, links, handles, phones) in ``text``."""
    if not text:
        return set()
    tokens: set[str] = set()
    tokens.update(match.group(0).lower().strip(".,;") for match in _EMAIL_RE.finditer(text))
    tokens.update(match.group(0).lower().strip(".,;") for match in _URL_RE.finditer(text))
    tokens.update(match.group(0).lower().strip(".,;") for match in _HANDLE_RE.finditer(text))
    tokens.update(
        re.sub(r"\s+", "", match.group(0)) for match in _PHONE_RE.finditer(text)
    )
    return {token for token in tokens if token}


def is_contact_only_change(before: str, after: str) -> bool:
    """True when the only difference between two bios is contact detail.

    A bio that gains or loses an email, link, handle or phone is a
    *contact-only* change and is not material (PRD V15). Text that changed in
    any other way - including surrounding words such as "Reach me at" - is
    still a real change.
    """
    before = (before or "").strip()
    after = (after or "").strip()
    if before == after:
        return True
    if not before or not after:
        return False

    # The contact sets must differ (otherwise this is not a contact change).
    if _contact_tokens(before) == _contact_tokens(after):
        return False

    # Remove the contact tokens and the connective words that introduce them,
    # then compare what is left.
    left = _strip_connective(strip_contacts(before))
    right = _strip_connective(strip_contacts(after))
    if left == right:
        return True

    # One side may be empty once the contacts (and their lead-in) are removed.
    return not left or not right


# Words that introduce a contact and carry no meaning of their own.
_CONTACT_LEAD_IN = re.compile(
    r"\b(reach me at|contact me at|email me at|write to|write me at|"
    r"dm me at|message me at|my (?:email|handle|contact|number) is|"
    r"email:?|contact:?|phone:?|handle:?|telegram:?|whatsapp:?)\b",
    re.IGNORECASE,
)


def _strip_connective(text: str) -> str:
    """Remove contact lead-in phrases and the punctuation around them."""
    cleaned = _CONTACT_LEAD_IN.sub(" ", text)
    cleaned = re.sub(r"[:\-–—]+", " ", cleaned)
    # Drop trailing and leading punctuation left behind by the removal.
    cleaned = re.sub(r"[.!?,;:]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def recency(snapshot: dict, received_at: str) -> tuple[datetime, datetime]:
    """Return ``(effective_captured_at, received_at)`` for ordering evidence.

    The server receipt time is authoritative. A missing or future client
    ``captured_at`` is clamped to the receipt time so a manipulated clock cannot
    jump ahead; an older ``captured_at`` makes the capture stale.
    """
    received = _parse_iso(received_at) or datetime.now(timezone.utc)
    captured = _parse_iso((snapshot or {}).get("captured_at"))
    if captured is None or captured > received + _CLOCK_SKEW_TOLERANCE:
        captured = received
    return captured, received


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return not value
    return False


def _count_value(observation: object) -> int | None:
    if isinstance(observation, dict):
        value = observation.get("value")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _missing_fields(snapshot: dict) -> list[str]:
    missing: set[str] = set()
    if not str(snapshot.get("display_name") or "").strip():
        missing.add("display_name")
    if not str(snapshot.get("bio") or "").strip():
        missing.add("bio")
    if not snapshot.get("external_urls"):
        missing.add("external_urls")
    for key in _COUNT_FIELDS:
        if _count_value(snapshot.get(key)) is None:
            missing.add(key)
    return sorted(missing)


def merge_snapshot(existing: dict, incoming: dict, *, incoming_newer: bool) -> dict:
    """Merge snapshots without erasing known values.

    Newer evidence may update known non-empty fields; stale evidence only fills
    empty ones. Counts are merged field-wise and unknown never replaces known.
    """
    merged = dict(existing or {})
    incoming = incoming or {}

    # Keep a stable snapshot shape even when a field is unknown.
    merged.setdefault("display_name", "")
    merged.setdefault("bio", "")
    merged.setdefault("external_urls", [])
    merged.setdefault("followers", None)
    merged.setdefault("following", None)
    merged.setdefault("post_count", None)
    merged.setdefault("source_url", "")
    merged.setdefault("captured_at", "")
    merged.setdefault("parser_version", "")
    merged.setdefault("is_verified", False)

    for key in _STRING_FIELDS:
        value = incoming.get(key)
        if isinstance(value, str) and value.strip():
            if incoming_newer or _is_empty(merged.get(key)):
                merged[key] = value

    if incoming_newer:
        merged["is_verified"] = bool(incoming.get("is_verified"))

    urls = list(merged.get("external_urls") or [])
    for url in incoming.get("external_urls") or []:
        if isinstance(url, str) and url.strip() and url not in urls:
            urls.append(url)
    merged["external_urls"] = urls

    for key in _COUNT_FIELDS:
        incoming_obs = incoming.get(key)
        if not isinstance(incoming_obs, dict):
            continue
        existing_obs = merged.get(key)
        if incoming_newer:
            if _count_value(incoming_obs) is not None or existing_obs is None:
                merged[key] = incoming_obs
        elif existing_obs is None or _count_value(existing_obs) is None:
            merged[key] = incoming_obs

    merged["missing_fields"] = _missing_fields(merged)
    return merged


def _canonical(value: object) -> object:
    if isinstance(value, dict):
        return (
            value.get("value"),
            str(value.get("display") or "").strip(),
            str(value.get("precision") or "").strip(),
        )
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, str):
        return value.strip()
    return value


def changed_snapshot_fields(before: dict, after: dict) -> list[str]:
    """Fields whose usable value changed between two snapshot states."""
    before = before or {}
    after = after or {}
    changed: list[str] = []
    for key in _MATERIAL_FIELDS:
        new = after.get(key)
        if key in _COUNT_FIELDS:
            if _count_value(new) is None:
                continue
        elif key == "external_urls":
            if not new:
                continue
        elif key == "is_verified":
            pass
        elif _is_empty(new):
            continue
        if _canonical(before.get(key)) != _canonical(new):
            changed.append(key)
    return changed


def field_provenance(snapshot: dict) -> dict[str, str]:
    """Map captured fields to their source for provenance."""
    provenance: dict[str, str] = {}
    for key in (
        "display_name",
        "bio",
        "is_verified",
        "external_urls",
        "followers",
        "following",
        "post_count",
        "source_url",
        "captured_at",
        "parser_version",
    ):
        value = snapshot.get(key)
        if key in _COUNT_FIELDS:
            if _count_value(value) is not None:
                provenance[key] = "snapshot"
        elif key == "external_urls":
            if value:
                provenance[key] = "snapshot"
        elif key == "is_verified":
            provenance[key] = "snapshot"
        elif not _is_empty(value):
            provenance[key] = "snapshot"
    return provenance


def payload_hash(username: str, source: str, snapshot: dict | None) -> str:
    """Stable hash of a capture payload for request-id conflict detection."""
    payload = {"username": username, "source": source or "", "snapshot": snapshot}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _domain(url: object) -> str:
    if not isinstance(url, str):
        return ""
    try:
        host = urlparse(url.strip()).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""
    return host


def external_domains(snapshot: dict) -> set[str]:
    return {
        domain
        for domain in (_domain(url) for url in (snapshot or {}).get("external_urls") or [])
        if domain
    }


def _in_range(value: int, minimum: int, maximum: int) -> bool:
    if minimum and value < minimum:
        return False
    if maximum and value > maximum:
        return False
    return True


def material_change_reasons(
    before: dict,
    after: dict,
    *,
    follower_min: int = 0,
    follower_max: int = 0,
) -> list[str]:
    """Deterministic material-change classification (V2-03).

    Only bio changes, external-domain changes, and follower counts crossing an
    explicitly configured campaign threshold are material. Timestamp-only or
    display-only recaptures are not.

    A **contact-only** bio change - one that only adds or removes an email,
    phone, handle or link - is not material (PRD V15): it must not push a
    current shortlist back into "Review needed".
    """
    before = before or {}
    after = after or {}
    reasons: list[str] = []

    before_bio = str(before.get("bio") or "").strip()
    after_bio = str(after.get("bio") or "").strip()
    if before_bio != after_bio and not is_contact_only_change(before_bio, after_bio):
        reasons.append("Bio changed")

    if external_domains(before) != external_domains(after):
        reasons.append("External domain changed")

    previous = _count_value(before.get("followers"))
    current = _count_value(after.get("followers"))
    if (
        previous is not None
        and current is not None
        and (follower_min or follower_max)
        and _in_range(previous, follower_min, follower_max)
        != _in_range(current, follower_min, follower_max)
    ):
        reasons.append("Follower count crossed the campaign threshold")

    return reasons
