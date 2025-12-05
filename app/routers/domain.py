from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional, Union
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

class WhoisResponseMinimal(BaseModel):
    """Format minimaliste par défaut - seulement les champs essentiels."""
    domain: str
    available: bool
    created_at: Optional[str] = None

class WhoisResponseDetailed(BaseModel):
    """Format détaillé avec toutes les clés développées incluant raw."""
    domain: str
    checked_at: str
    tld: str
    available: bool
    pending_delete: bool = False
    redemption_period: bool = False
    statut: Optional[str] = None
    created_at: Optional[str] = None
    registrar: Optional[str] = None
    raw: str  # raw WHOIS data (inclus seulement avec details=1)

@router.get("/whois", response_model=Union[WhoisResponseMinimal, WhoisResponseDetailed])
async def get_whois(
    domain: str = Query(..., description="Domain name to check"),
    refresh: int = Query(0, description="Force fresh lookup (1 to refresh)"),
    details: int = Query(0, description="Return detailed format with all keys including raw (1 for details)"),
    token: str = Depends(verify_token)
):
    logger.info(f"get_whois called for domain={domain}, refresh={refresh}, details={details}")
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

    if refresh != 1:
        cached_data = cache.get(domain)
        if cached_data:
            # Prefer parsed fields persisted in DB. Only fallback to parsing raw if fields are missing.
            # Support both old and new column names for migration compatibility
            parsed = {
                "statut": cached_data.get("statut"),
                "created_at": cached_data.get("created_at") or cached_data.get("creation_date"),
                "registrar": cached_data.get("registrar"),
                "pending_delete": cached_data.get("pending_delete") or cached_data.get("pendingDelete"),
                "redemption_period": cached_data.get("redemption_period") or cached_data.get("redemptionPeriod"),
            }
            # If any key is missing/None, parse raw as fallback
            if not any(v is not None for v in parsed.values()):
                parsed = parse_whois(cached_data.get("raw"), tld)
            else:
                # ensure booleans normalized (could be stored as 0/1)
                try:
                    parsed["pending_delete"] = bool(int(parsed["pending_delete"])) if parsed["pending_delete"] is not None else False
                except Exception:
                    parsed["pending_delete"] = bool(parsed.get("pending_delete"))
                try:
                    parsed["redemption_period"] = bool(int(parsed["redemption_period"])) if parsed["redemption_period"] is not None else False
                except Exception:
                    parsed["redemption_period"] = bool(parsed.get("redemption_period"))
            # inject parsed fields so response_model includes them
            cached_data.update(parsed)
            # ensure coherence: if pending_delete or redemption_period, available must be False
            if cached_data.get("pending_delete") or cached_data.get("redemption_period"):
                cached_data["available"] = False
            
            # Projection dynamique selon details
            if details != 1:
                # Format minimaliste - seulement domain, available, created_at
                return WhoisResponseMinimal(
                    domain=cached_data["domain"],
                    available=cached_data["available"],
                    created_at=cached_data.get("created_at")
                )
            else:
                # Format détaillé avec raw
                return WhoisResponseDetailed(
                    domain=cached_data["domain"],
                    checked_at=cached_data["checked_at"],
                    tld=cached_data["tld"],
                    available=cached_data["available"],
                    pending_delete=cached_data.get("pending_delete", False),
                    redemption_period=cached_data.get("redemption_period", False),
                    statut=cached_data.get("statut"),
                    created_at=cached_data.get("created_at"),
                    registrar=cached_data.get("registrar"),
                    raw=cached_data.get("raw", "")
                )

    logger.debug(f"Cache miss or refresh=1, performing lookup for {domain}")

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
    # Support both old and new column names for migration compatibility
    parsed = {
        "statut": cached_data.get("statut"),
        "created_at": cached_data.get("created_at") or cached_data.get("creation_date"),
        "registrar": cached_data.get("registrar"),
        "pending_delete": cached_data.get("pending_delete") or cached_data.get("pendingDelete"),
        "redemption_period": cached_data.get("redemption_period") or cached_data.get("redemptionPeriod"),
    }
    if not any(v is not None for v in parsed.values()):
        parsed = parse_whois(cached_data.get("raw"), tld)
    else:
        try:
            parsed["pending_delete"] = bool(int(parsed["pending_delete"])) if parsed["pending_delete"] is not None else False
        except Exception:
            parsed["pending_delete"] = bool(parsed.get("pending_delete"))
        try:
            parsed["redemption_period"] = bool(int(parsed["redemption_period"])) if parsed["redemption_period"] is not None else False
        except Exception:
            parsed["redemption_period"] = bool(parsed.get("redemption_period"))
    cached_data.update(parsed)
    # ensure coherence: if pending_delete or redemption_period, available must be False
    if cached_data.get("pending_delete") or cached_data.get("redemption_period"):
        cached_data["available"] = False
    
    # Projection dynamique selon details
    if details != 1:
        # Format minimaliste - seulement domain, available, created_at
        return WhoisResponseMinimal(
            domain=cached_data["domain"],
            available=cached_data["available"],
            created_at=cached_data.get("created_at")
        )
    else:
        # Format détaillé avec raw
        return WhoisResponseDetailed(
            domain=cached_data["domain"],
            checked_at=cached_data["checked_at"],
            tld=cached_data["tld"],
            available=cached_data["available"],
            pending_delete=cached_data.get("pending_delete", False),
            redemption_period=cached_data.get("redemption_period", False),
            statut=cached_data.get("statut"),
            created_at=cached_data.get("created_at"),
            registrar=cached_data.get("registrar"),
            raw=cached_data.get("raw", "")
        )
