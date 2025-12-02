from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.services.cache import WhoisCache
from app.services.whois import WhoisService
from app.services.rate_limiter import RateLimiter

router = APIRouter(prefix="/domain", tags=["domain"])

# Initialize services
# In a larger app, we might use dependency injection, but this is fine for now
cache = WhoisCache()
whois_service = WhoisService()
rate_limiter = RateLimiter()

class WhoisResponse(BaseModel):
    domain: str
    tld: str
    available: bool
    checked_at: str
    raw: str

@router.get("/whois", response_model=WhoisResponse)
async def get_whois(
    domain: str = Query(..., description="Domain name to check"),
    force: int = Query(0, description="Force fresh lookup (1 to force)")
):
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
    if force != 1:
        cached_data = cache.get(domain)
        if cached_data:
            return cached_data

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
         
    return cached_data
