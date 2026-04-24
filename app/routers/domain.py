import logging
import time
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import verify_token
from app.services.cache import WhoisCache
from app.services.rate_limiter import RateLimiter
from app.services.whois import WhoisService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/domain", tags=["domain"])

# Initialize services
# In a larger app, we might use dependency injection, but this is fine for now
cache = WhoisCache()
whois_service = WhoisService()
rate_limiter = RateLimiter()

MAX_DOMAINS_PER_REQUEST = 10
MAX_LIVE_LOOKUPS_PER_REQUEST = 3
LIVE_LOOKUP_BUDGET_SECONDS = 8.0

type AvailabilityStatus = Literal["ok", "invalid_domain", "rate_limited", "whois_error", "skipped_budget"]
type CachedData = dict[str, object]


class AvailabilityResult(BaseModel):
    domain: str
    available: bool | None = None
    checked_at: str = ""
    status: AvailabilityStatus


class AvailabilityResponse(BaseModel):
    results: list[AvailabilityResult]


class ErrorResponse(BaseModel):
    error: str
    message: str


def _normalize_text(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_bool(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)

def _error_response(status_code: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error, message=message).model_dump()
    )


def _normalize_domain(domain: str) -> str:
    return _normalize_text(domain).lower()


def _is_valid_domain(domain: str) -> bool:
    if "." not in domain:
        return False
    labels = domain.split(".")
    return all(label.strip() for label in labels)


def _build_result(
    domain: str,
    status: AvailabilityStatus,
    available: bool | None = None,
    checked_at: str = "",
) -> AvailabilityResult:
    return AvailabilityResult(
        domain=_normalize_domain(domain),
        available=available,
        checked_at=_normalize_text(checked_at),
        status=status,
    )


def _build_cached_result(domain: str, cached_data: CachedData) -> AvailabilityResult:
    return _build_result(
        domain=domain,
        available=_normalize_bool(cached_data.get("available")),
        checked_at=_normalize_text(cached_data.get("checked_at")),
        status="ok",
    )


@router.get(
    "/availability",
    response_model=AvailabilityResponse,
    responses={
        400: {"model": ErrorResponse},
    },
)
async def get_availability(
    domain: list[str] | None = Query(None, description="One or more domain names to check"),
    refresh: int = Query(0, description="Force fresh lookup (1 to refresh)"),
    token: str | None = Depends(verify_token)
) -> AvailabilityResponse:
    logger.info("get_availability called for domains=%s refresh=%s", domain, refresh)

    normalized_domains = []
    seen = set()
    for raw_domain in domain or []:
        normalized_domain = _normalize_domain(raw_domain)
        if normalized_domain not in seen:
            seen.add(normalized_domain)
            normalized_domains.append(normalized_domain)

    if not normalized_domains:
        return _error_response(
            status_code=400,
            error="invalid_request",
            message="At least one domain is required.",
        )

    if len(normalized_domains) > MAX_DOMAINS_PER_REQUEST:
        return _error_response(
            status_code=400,
            error="too_many_domains",
            message=f"Maximum {MAX_DOMAINS_PER_REQUEST} domains per request.",
        )

    results: list[AvailabilityResult | None] = [None] * len(normalized_domains)
    live_candidates = []

    for index, current_domain in enumerate(normalized_domains):
        if not _is_valid_domain(current_domain):
            results[index] = _build_result(current_domain, status="invalid_domain")
            continue

        if refresh != 1:
            cached_data = cache.get(current_domain)
            if cached_data:
                results[index] = _build_cached_result(current_domain, cached_data)
                continue

        live_candidates.append((index, current_domain))

    live_lookup_count = 0
    live_lookup_started_at = time.monotonic()

    for live_index, (result_index, current_domain) in enumerate(live_candidates):
        if live_lookup_count >= MAX_LIVE_LOOKUPS_PER_REQUEST:
            results[result_index] = _build_result(current_domain, status="skipped_budget")
            continue

        if time.monotonic() - live_lookup_started_at >= LIVE_LOOKUP_BUDGET_SECONDS:
            results[result_index] = _build_result(current_domain, status="skipped_budget")
            continue

        rate_limit_reason = rate_limiter.check_reason(current_domain)
        if rate_limit_reason == "global_limit":
            results[result_index] = _build_result(current_domain, status="rate_limited")
            for pending_result_index, pending_domain in live_candidates[live_index + 1:]:
                if results[pending_result_index] is None:
                    results[pending_result_index] = _build_result(pending_domain, status="rate_limited")
            break

        if rate_limit_reason is not None:
            results[result_index] = _build_result(current_domain, status="rate_limited")
            continue

        rate_limiter.add(current_domain)
        live_lookup_count += 1

        try:
            raw_output = whois_service.lookup(current_domain)
        except Exception:
            logger.exception("WHOIS lookup failed for %s", current_domain)
            results[result_index] = _build_result(current_domain, status="whois_error")
            continue

        tld = current_domain.rsplit(".", 1)[-1]
        available = whois_service.is_available(raw_output, tld)
        cache.set(current_domain, tld, available, raw_output)
        cached_data = cache.get(current_domain)

        if cached_data:
            results[result_index] = _build_cached_result(current_domain, cached_data)
        else:
            results[result_index] = _build_result(
                current_domain,
                available=available,
                checked_at="",
                status="ok",
            )

    finalized_results = [
        result if result is not None else _build_result(normalized_domains[index], status="skipped_budget")
        for index, result in enumerate(results)
    ]
    return AvailabilityResponse(results=finalized_results)
