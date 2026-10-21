"""Parse a stored ``leads.profile_snapshot`` into lead fields (PRD T06).

The extension capture stores a sanitized JSON snapshot. This module turns it into
``leads`` column values so ``profile_fetch`` can complete without HikerAPI. Bio
text is normalized and contact patterns are masked so structured contact fields
stay unpopulated before manual fit approval.
"""

from __future__ import annotations

import json

from app.ai.masking import normalize_bio

__all__ = ["parse_snapshot", "snapshot_has_data", "snapshot_to_lead_fields"]


def parse_snapshot(raw: str) -> dict:
    """Best-effort parse of the stored snapshot JSON (never raises)."""
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _count_value(observation: object) -> int | None:
    if isinstance(observation, dict):
        value = observation.get("value")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def snapshot_has_data(snapshot: dict) -> bool:
    """True when the snapshot carries usable profile evidence.

    Requires at least one of bio, external URLs, or a known follower count — the
    same signals the capture flow treats as meaningful (PRD §5.1).
    """
    if not snapshot:
        return False
    if str(snapshot.get("bio") or "").strip():
        return True
    if snapshot.get("external_urls"):
        return True
    return _count_value(snapshot.get("followers")) is not None


def snapshot_to_lead_fields(snapshot: dict) -> dict[str, object]:
    """Map a snapshot to ``leads`` columns (contact fields deliberately omitted)."""
    fields: dict[str, object] = {}

    display_name = str(snapshot.get("display_name") or "").strip()
    if display_name:
        fields["full_name"] = display_name

    # V2-01 policy: public business contacts are retained (no blanket masking).
    bio = normalize_bio(snapshot.get("bio") or "")
    if bio:
        fields["bio"] = bio

    urls = [
        str(url).strip()
        for url in snapshot.get("external_urls") or []
        if isinstance(url, str) and url.strip()
    ]
    if urls:
        fields["external_url"] = urls[0]
        fields["all_external_urls"] = ",".join(urls)

    followers = _count_value(snapshot.get("followers"))
    if followers is not None:
        fields["follower_count"] = followers

    following = _count_value(snapshot.get("following"))
    if following is not None:
        fields["follows_count"] = following

    source_url = str(snapshot.get("source_url") or "").strip()
    if source_url:
        fields["profile_url"] = source_url

    captured_at = str(snapshot.get("captured_at") or "").strip()
    if captured_at:
        fields["scraped_at"] = captured_at

    return fields
