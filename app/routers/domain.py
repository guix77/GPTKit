import logging
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

type AvailabilityStatus = Literal["ok", "invalid_domain", "rate_limited", "whois_error"]
type CachedData = dict[str, object]


class AvailabilityResult(BaseModel):
    domain: str
    available: bool | None = None
    checked_at: str = ""
    status: AvailabilityStatus


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
    response_model=AvailabilityResult,
)
async def get_availability(
    domain: str = Query(..., description="Full domain name including TLD"),
    refresh: int = Query(0, description="Force fresh lookup (1 to refresh)"),
    token: str | None = Depends(verify_token)
) -> AvailabilityResult:
    logger.info("get_availability called for domain=%s refresh=%s", domain, refresh)

    current_domain = _normalize_domain(domain)
    if not _is_valid_domain(current_domain):
        return _build_result(current_domain, status="invalid_domain")

    if refresh != 1:
        cached_data = cache.get(current_domain)
        if cached_data:
            return _build_cached_result(current_domain, cached_data)

    if rate_limiter.check_reason(current_domain) is not None:
        return _build_result(current_domain, status="rate_limited")

    rate_limiter.add(current_domain)

    try:
        raw_output = whois_service.lookup(current_domain)
    except Exception:
        logger.exception("WHOIS lookup failed for %s", current_domain)
        return _build_result(current_domain, status="whois_error")

    tld = current_domain.rsplit(".", 1)[-1]
    available = whois_service.is_available(raw_output, tld)
    cache.set(current_domain, tld, available, raw_output)
    cached_data = cache.get(current_domain)

    if cached_data:
        return _build_cached_result(current_domain, cached_data)

    return _build_result(
        current_domain,
        available=available,
        checked_at="",
        status="ok",
    )
