"""Lead input parsing and validation.

Accepts either a bare Instagram handle (with or without a leading ``@``) or an
Instagram profile URL, and produces a normalized handle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

MAX_USERNAME_LENGTH = 30

# Instagram usernames: letters, digits, periods and underscores.
_HANDLE_RE = re.compile(r"^[A-Za-z0-9._]+$")

# Path segments that are never profile usernames.
RESERVED_SEGMENTS = frozenset(
    {
        "accounts",
        "about",
        "api",
        "developer",
        "direct",
        "explore",
        "legal",
        "p",
        "privacy",
        "reel",
        "reels",
        "stories",
        "terms",
        "tv",
    }
)


class InvalidLeadInput(ValueError):
    """Raised when a submitted username/URL is not a valid Instagram profile."""


@dataclass(frozen=True)
class ParsedLeadInput:
    """A validated lead input."""

    username: str
    normalized: str
    profile_url: str


def _handle_from_url(value: str) -> str:
    candidate = value if value.lower().startswith(("http://", "https://")) else f"https://{value}"
    parsed = urlparse(candidate)
    host = (parsed.netloc or "").lower().rsplit("@", 1)[-1].split(":", 1)[0]
    host = host.removeprefix("www.")
    if host != "instagram.com" and not host.endswith(".instagram.com"):
        raise InvalidLeadInput("Only instagram.com profile URLs are accepted.")

    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        raise InvalidLeadInput("The Instagram URL does not contain a username.")
    return segments[0].lstrip("@")


def _looks_like_url(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered.startswith(("http://", "https://"))
        or "instagram.com" in lowered
        or "/" in value
    )


def validate_handle(handle: str) -> str:
    """Validate a bare handle (no ``@``), returning it unchanged."""
    if not handle:
        raise InvalidLeadInput("A username is required.")
    if len(handle) > MAX_USERNAME_LENGTH:
        raise InvalidLeadInput(
            f"Instagram usernames are at most {MAX_USERNAME_LENGTH} characters."
        )
    if handle.lower() in RESERVED_SEGMENTS:
        raise InvalidLeadInput(f"'{handle}' is not a profile username.")
    if not _HANDLE_RE.match(handle):
        raise InvalidLeadInput(
            "Usernames may contain only letters, numbers, periods and underscores."
        )
    if handle.startswith(".") or handle.endswith("."):
        raise InvalidLeadInput("A username cannot start or end with a period.")
    if ".." in handle:
        raise InvalidLeadInput("A username cannot contain consecutive periods.")
    return handle


def parse_lead_input(raw: str) -> ParsedLeadInput:
    """Parse and validate a username or Instagram profile URL."""
    value = (raw or "").strip()
    if not value:
        raise InvalidLeadInput("A username or Instagram profile URL is required.")

    handle = _handle_from_url(value) if _looks_like_url(value) else value.lstrip("@").strip()
    validate_handle(handle)

    normalized = handle.lower()
    return ParsedLeadInput(
        username=handle,
        normalized=normalized,
        profile_url=f"https://www.instagram.com/{normalized}/",
    )
