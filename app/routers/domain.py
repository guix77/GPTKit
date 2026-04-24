from fastapi import APIRouter, Query, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from app.services.cache import WhoisCache
from app.services.whois import WhoisService, parse_whois
from app.services.rate_limiter import RateLimiter
from app.auth import verify_token
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/domain", tags=["domain"])

# Initialize services
# In a larger app, we might use dependency injection, but this is fine for now
cache = WhoisCache()
whois_service = WhoisService()
rate_limiter = RateLimiter()

class WhoisResponse(BaseModel):
    """Format stable pour les outils GPT, avec des types toujours identiques."""
    domain: str
    available: bool
    created_at: str = ""
    checked_at: str = ""
    tld: str = ""
    pending_delete: bool = False
    redemption_period: bool = False
    statut: str = ""
    registrar: str = ""
    raw: str = ""

class ErrorResponse(BaseModel):
    error: str
    message: str

def _normalize_text(value: Optional[str]) -> str:
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
        content=ErrorResponse(error=error, message=message).dict()
    )

def _prepare_cached_data(cached_data: dict, fallback_tld: str) -> dict:
    # Prefer parsed fields persisted in DB. Only fallback to parsing raw if fields are missing.
    # Support both old and new column names for migration compatibility.
    parsed = {
        "statut": cached_data.get("statut"),
        "created_at": cached_data.get("created_at") or cached_data.get("creation_date"),
        "registrar": cached_data.get("registrar"),
        "pending_delete": cached_data.get("pending_delete") if cached_data.get("pending_delete") is not None else cached_data.get("pendingDelete"),
        "redemption_period": cached_data.get("redemption_period") if cached_data.get("redemption_period") is not None else cached_data.get("redemptionPeriod"),
    }
    if not any(v is not None for v in parsed.values()):
        parsed = parse_whois(cached_data.get("raw"), fallback_tld)
    else:
        parsed["pending_delete"] = _normalize_bool(parsed.get("pending_delete"))
        parsed["redemption_period"] = _normalize_bool(parsed.get("redemption_period"))

    normalized = dict(cached_data)
    normalized.update(parsed)
    normalized["available"] = _normalize_bool(normalized.get("available"))
    normalized["pending_delete"] = _normalize_bool(normalized.get("pending_delete"))
    normalized["redemption_period"] = _normalize_bool(normalized.get("redemption_period"))
    normalized["created_at"] = _normalize_text(normalized.get("created_at"))
    normalized["checked_at"] = _normalize_text(normalized.get("checked_at"))
    normalized["tld"] = _normalize_text(normalized.get("tld")) or fallback_tld
    normalized["statut"] = _normalize_text(normalized.get("statut"))
    normalized["registrar"] = _normalize_text(normalized.get("registrar"))
    normalized["raw"] = normalized.get("raw") if isinstance(normalized.get("raw"), str) else ""

    # ensure coherence: if pending_delete or redemption_period, available must be False
    if normalized["pending_delete"] or normalized["redemption_period"]:
        normalized["available"] = False

    return normalized

def _build_response(cached_data: dict, fallback_tld: str, details: int) -> WhoisResponse:
    normalized = _prepare_cached_data(cached_data, fallback_tld)
    return WhoisResponse(
        domain=_normalize_text(normalized.get("domain")),
        available=normalized["available"],
        created_at=normalized["created_at"],
        checked_at=normalized["checked_at"],
        tld=normalized["tld"],
        pending_delete=normalized["pending_delete"],
        redemption_period=normalized["redemption_period"],
        statut=normalized["statut"],
        registrar=normalized["registrar"],
        raw=normalized["raw"] if details == 1 else "",
    )

@router.get(
    "/whois",
    response_model=WhoisResponse,
    responses={
        400: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_whois(
    domain: str = Query(..., description="Domain name to check"),
    refresh: int = Query(0, description="Force fresh lookup (1 to refresh)"),
    details: int = Query(0, description="Return detailed format with all keys including raw (1 for details)"),
    token: str = Depends(verify_token)
):
    logger.info(f"get_whois called for domain={domain}, refresh={refresh}, details={details}")
    # 1. Validation
    if "." not in domain:
        return _error_response(
            status_code=400,
            error="invalid_domain",
            message="Domain must include a TLD (example: site.com).",
        )
    
    # Simple TLD extraction (last part after dot)
    parts = domain.split(".")
    tld = parts[-1]
    
    # 2. Cache
    # parser is provided by app.services.whois.parse_whois

    if refresh != 1:
        cached_data = cache.get(domain)
        if cached_data:
            return _build_response(cached_data, tld, details)

    logger.debug(f"Cache miss or refresh=1, performing lookup for {domain}")

    # 3. Rate Limiting
    if not rate_limiter.check(domain):
        return _error_response(
            status_code=429,
            error="rate_limited",
            message="WHOIS rate limit exceeded.",
        )
    
    rate_limiter.add(domain)

    # 4. Execution
    try:
        raw_output = whois_service.lookup(domain)
    except Exception:
        return _error_response(
            status_code=500,
            error="whois_error",
            message="WHOIS lookup failed or timed out.",
        )

    # 5. Availability
    available = whois_service.is_available(raw_output, tld)

    # 6. Update Cache
    cache.set(domain, tld, available, raw_output)
    
    # Fetch back to ensure we return exactly what's in the cache (including timestamp)
    cached_data = cache.get(domain)
    if not cached_data:
        return _error_response(
            status_code=500,
            error="cache_error",
            message="Failed to retrieve data from cache after save.",
        )

    return _build_response(cached_data, tld, details)
