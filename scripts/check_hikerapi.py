"""Manual HikerAPI check: fetch one approved public profile.

Requires ``HIKERAPI_KEY`` in the environment / `.env`. The key is never printed.
Run from the repository root:

    .\\backend\\.venv\\Scripts\\python.exe scripts\\check_hikerapi.py
    .\\backend\\.venv\\Scripts\\python.exe scripts\\check_hikerapi.py --username natgeo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.leads.validation import InvalidLeadInput  # noqa: E402
from app.providers import HikerAPIClient, HikerAPIError  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch one Instagram profile via HikerAPI.")
    parser.add_argument(
        "--username",
        default="instagram",
        help="Approved public profile to fetch (handle or URL).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()

    if not settings.hikerapi_key.strip():
        print("ERROR: HIKERAPI_KEY is not set (see .env.example).")
        return 2

    print(f"Base URL: {settings.hikerapi_base_url}")
    try:
        with HikerAPIClient.from_settings(settings) as client:
            profile = client.fetch_profile(args.username)
    except InvalidLeadInput as exc:
        print(f"ERROR: invalid username/URL: {exc}")
        return 2
    except HikerAPIError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 1

    print(f"@{profile.username}")
    print(f"  instagramId:   {profile.instagram_id}")
    print(f"  fullName:      {profile.full_name}")
    print(f"  followers:     {profile.follower_count}")
    print(f"  following:     {profile.following_count}")
    print(f"  posts:         {profile.media_count}")
    print(f"  category:      {profile.category}")
    print(f"  verified:      {profile.is_verified}  business: {profile.is_business}")
    print(f"  externalUrl:   {profile.external_url}")
    print(f"  bioLinks:      {len(profile.bio_links)}")
    print(f"  phone:         {profile.phone or '(none)'}")
    print(f"  emails:        {', '.join(profile.emails) or '(none)'}")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
