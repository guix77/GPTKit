from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from app.services.cache import WhoisCache
from app.services.whois import WhoisService, parse_whois
from app.services.rate_limiter import RateLimiter
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/domain", tags=["domain"])

# Initialize services
# In a larger app, we might use dependency injection, but this is fine for now
cache = WhoisCache()
whois_service = WhoisService()
rate_limiter = RateLimiter()

class WhoisResponse(BaseModel):
    domain: str
    checked_at: str
    tld: str
    available: bool
    pendingDelete: bool = False
    redemptionPeriod: bool = False
    statut: Optional[str] = None
    creation_date: Optional[str] = None
    registrar: Optional[str] = None
    # raw is intentionally omitted from the public response

@router.get("/whois", response_model=WhoisResponse)
async def get_whois(
    domain: str = Query(..., description="Domain name to check"),
    force: int = Query(0, description="Force fresh lookup (1 to force)")
):
    logger.info(f"get_whois called for domain={domain}, force={force}")
    # 1. Validation
    if "." not in domain:
        raise HTTPException(
            status_code=400, 
            detail={"error": "invalid_domain", "message": "Domain must include a TLD (example: site.com)."}
        )
    
    # Simple TLD extraction (last part after dot)
    parts = domain.split(".")
    tld = parts[-1]
    
    # 2. Cache
    # parser is provided by app.services.whois.parse_whois

    if force != 1:
        cached_data = cache.get(domain)
        if cached_data:
            # Prefer parsed fields persisted in DB. Only fallback to parsing raw if fields are missing.
            parsed = {
                "statut": cached_data.get("statut"),
                "creation_date": cached_data.get("creation_date"),
                "registrar": cached_data.get("registrar"),
                "pendingDelete": cached_data.get("pendingDelete"),
                "redemptionPeriod": cached_data.get("redemptionPeriod"),
            }
            # If any key is missing/None, parse raw as fallback
            if not any(v is not None for v in parsed.values()):
                parsed = parse_whois(cached_data.get("raw"), tld)
            else:
                # ensure booleans normalized (could be stored as 0/1)
                try:
                    parsed["pendingDelete"] = bool(int(parsed["pendingDelete"])) if parsed["pendingDelete"] is not None else False
                except Exception:
                    parsed["pendingDelete"] = bool(parsed.get("pendingDelete"))
                try:
                    parsed["redemptionPeriod"] = bool(int(parsed["redemptionPeriod"])) if parsed["redemptionPeriod"] is not None else False
                except Exception:
                    parsed["redemptionPeriod"] = bool(parsed.get("redemptionPeriod"))
            # do not expose raw in responses
            cached_data.pop("raw", None)
            # inject parsed fields so response_model includes them
            cached_data.update(parsed)
            # ensure coherence: if pendingDelete or redemptionPeriod, available must be False
            if cached_data.get("pendingDelete") or cached_data.get("redemptionPeriod"):
                cached_data["available"] = False
            return cached_data

    logger.debug(f"Cache miss or force=1, performing lookup for {domain}")

    # 3. Rate Limiting
    if not rate_limiter.check(domain):
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "message": "WHOIS rate limit exceeded."}
        )
    
    rate_limiter.add(domain)

    # 4. Execution
    try:
        raw_output = whois_service.lookup(domain)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={"error": "whois_error", "message": "WHOIS lookup failed or timed out."}
        )

    # 5. Availability
    available = whois_service.is_available(raw_output, tld)

    # 6. Update Cache
    cache.set(domain, tld, available, raw_output)
    
    # Fetch back to ensure we return exactly what's in the cache (including timestamp)
    cached_data = cache.get(domain)
    if not cached_data:
        raise HTTPException(status_code=500, detail="Failed to retrieve data from cache after save")
    # Prefer parsed fields persisted in DB. Only fallback to parsing raw if fields are missing.
    parsed = {
        "statut": cached_data.get("statut"),
        "creation_date": cached_data.get("creation_date"),
        "registrar": cached_data.get("registrar"),
        "pendingDelete": cached_data.get("pendingDelete"),
        "redemptionPeriod": cached_data.get("redemptionPeriod"),
    }
    if not any(v is not None for v in parsed.values()):
        parsed = parse_whois(cached_data.get("raw"), tld)
    else:
        try:
            parsed["pendingDelete"] = bool(int(parsed["pendingDelete"])) if parsed["pendingDelete"] is not None else False
        except Exception:
            parsed["pendingDelete"] = bool(parsed.get("pendingDelete"))
        try:
            parsed["redemptionPeriod"] = bool(int(parsed["redemptionPeriod"])) if parsed["redemptionPeriod"] is not None else False
        except Exception:
            parsed["redemptionPeriod"] = bool(parsed.get("redemptionPeriod"))
    cached_data.pop("raw", None)
    cached_data.update(parsed)
    # ensure coherence: if pendingDelete or redemptionPeriod, available must be False
    if cached_data.get("pendingDelete") or cached_data.get("redemptionPeriod"):
        cached_data["available"] = False
    return cached_data
    cached_data.update(parsed)
    return cached_data
