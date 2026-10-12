"""Pipeline stages executed by the worker.

Each stage is idempotent and returns a :class:`StageOutcome`. Stages never send
external messages; they only read/write Google Sheets through the repositories.

Phase 4 implements the profile-fetch stage using the HikerAPI provider.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from app import constants
from app.leads.validation import InvalidLeadInput
from app.providers.errors import (
    HikerAPIAuthError,
    HikerAPIConfigError,
    HikerAPIError,
    HikerAPINetworkError,
    HikerAPINotFoundError,
    HikerAPIQuotaError,
    HikerAPIRateLimitError,
    HikerAPIResponseError,
)
from app.providers.models import HikerProfile, to_lead_fields
from app.sheets.models import EnrichedLead, PipelineJob
from app.sheets.repository import LeadStore, SheetStore
from app.sheets.schemas import KEY_ENRICHED, KEY_IG_LEADS, normalize_username
from app.sheets.util import utc_now_iso

logger = logging.getLogger(__name__)

# Provider failures that are worth retrying with backoff.
_RETRYABLE_HIKER_ERRORS = (
    HikerAPIRateLimitError,
    HikerAPIQuotaError,
    HikerAPINetworkError,
    HikerAPIResponseError,
)


@dataclass
class StageOutcome:
    """Result of running one stage for one job."""

    ok: bool
    result: str = ""
    error: str = ""
    retryable: bool = False


class ProfileFetcher(Protocol):
    def fetch_profile(self, username: str) -> HikerProfile:
        ...


class Stage(Protocol):
    name: str

    def run(self, job: PipelineJob) -> StageOutcome:
        ...


class ProfileFetchStage:
    """Fetch a public Instagram profile and persist it (idempotent)."""

    name = constants.STAGE_PROFILE_FETCH

    def __init__(
        self,
        client: ProfileFetcher,
        lead_store: LeadStore,
        enriched_store: SheetStore,
    ) -> None:
        self._client = client
        self._lead_store = lead_store
        self._enriched_store = enriched_store

    def run(self, job: PipelineJob) -> StageOutcome:
        username = job.username_normalized or job.username
        try:
            profile = self._client.fetch_profile(username)
        except HikerAPINotFoundError as exc:
            self._mark_lead(job, constants.LEAD_STATUS_NOT_FOUND, str(exc))
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)
        except (HikerAPIAuthError, HikerAPIConfigError) as exc:
            # Configuration/credential problems affect every job; do not retry.
            return StageOutcome(ok=False, error=_error_text(exc), retryable=False)
        except InvalidLeadInput as exc:
            self._mark_lead(job, constants.LEAD_STATUS_ERROR, str(exc))
            return StageOutcome(ok=False, error=str(exc), retryable=False)
        except HikerAPIError as exc:
            retryable = isinstance(exc, _RETRYABLE_HIKER_ERRORS)
            return StageOutcome(ok=False, error=_error_text(exc), retryable=retryable)

        created_at = self._existing_enriched_created_at(job.lead_id)
        self._write_enriched(job, profile, created_at)
        self._update_lead(job, profile)
        logger.info(
            "Enriched lead %s (@%s): followers=%s emails=%s",
            job.lead_id,
            profile.username,
            profile.follower_count,
            len(profile.emails),
        )
        return StageOutcome(
            ok=True,
            result=json.dumps(
                {
                    "username": profile.username,
                    "followers": profile.follower_count,
                    "emails": len(profile.emails),
                    "externalUrl": profile.external_url,
                }
            ),
        )

    # -- persistence --------------------------------------------------------

    def _existing_enriched_created_at(self, lead_id: str) -> str:
        record = self._enriched_store.find_row(KEY_ENRICHED, lead_id, key_header="leadId")
        return record.values.get("createdAt", "") if record is not None else ""

    def _write_enriched(self, job: PipelineJob, profile: HikerProfile, created_at: str) -> None:
        now = utc_now_iso()
        fields = to_lead_fields(profile, scraped_at=now)
        enriched = EnrichedLead(
            leadId=job.lead_id,
            username=profile.username,
            usernameNormalized=normalize_username(profile.username) or job.username_normalized,
            fullName=fields["fullName"],
            instagramId=fields["instagramId"],
            followerCount=int(fields["followerCount"] or 0),
            followsCount=int(fields["followsCount"] or 0),
            businessCategoryName=fields["businessCategoryName"],
            bio=fields["bio"],
            businessEmail=fields["businessEmail"],
            businessPhoneNumber=fields["businessPhoneNumber"],
            profileUrl=fields["profileUrl"],
            externalUrl=fields["externalUrl"],
            allExternalUrls=fields["allExternalUrls"],
            profileStatus="done",
            profileScrapedAt=now,
            createdAt=created_at or now,
            updatedAt=now,
        )
        self._enriched_store.upsert_model(KEY_ENRICHED, enriched)

    def _update_lead(self, job: PipelineJob, profile: HikerProfile) -> None:
        fields = to_lead_fields(profile)
        self._lead_store.update_by_key(
            KEY_IG_LEADS,
            job.lead_id,
            {**fields, "status": constants.LEAD_STATUS_ENRICHED, "lastError": ""},
        )

    def _mark_lead(self, job: PipelineJob, status: str, error: str) -> None:
        self._lead_store.update_by_key(
            KEY_IG_LEADS,
            job.lead_id,
            {"status": status, "lastError": error[:500]},
        )


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:1000]
