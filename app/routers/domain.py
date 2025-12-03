from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from app.services.cache import WhoisCache
from app.services.whois import WhoisService
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
    def parse_whois(raw: str, tld: str):
        """Extract statut, creation_date, registrar, pendingDelete, redemptionPeriod for all TLDs.

        This is heuristic: we search common WHOIS labels case-insensitively.
        Returns a dict with keys 'statut', 'creation_date', 'registrar', 'pendingDelete', 'redemptionPeriod'.
        """
        if not raw:
            return {
                "statut": None,
                "creation_date": None,
                "registrar": None,
                "pendingDelete": False,
                "redemptionPeriod": False,
            }

        raw_lines = [l.strip() for l in raw.splitlines() if l.strip()]
        lower = raw.lower()

        statut = None
        creation_date = None
        registrar = None
        pendingDelete = False
        redemptionPeriod = False

        import re

        # Common patterns (now generalized for all TLDs)
        for line in raw_lines:
            l = line.lower()
            # Registrar: (ignore Registrar WHOIS Server and Registrar URL)
            if registrar is None and l.startswith("registrar:") and not ("whois server" in l or "url" in l):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    registrar = parts[1].strip()
                    continue
            # Creation date
            if creation_date is None and ("creation date" in l or "created on" in l or "created:" in l or "creation:" in l or "registered on" in l):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    creation_date = parts[1].strip()
                    continue
            # Status lines (can have multiple)
            if "status:" in l or l.startswith("domain status"):
                if statut is None:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        statut = parts[1].strip()
                # Check for pendingDelete and redemptionPeriod in any status line
                if "pendingdelete" in l:
                    pendingDelete = True
                if "redemptionperiod" in l:
                    redemptionPeriod = True
                continue

        # Fallback regex for Registrar lines like 'Registrar Name' without colon
        if registrar is None:
            m = re.search(r"registrar\s+([\w\-\. ]{3,})", raw, re.IGNORECASE)
            if m:
                registrar = m.group(1).strip()

        return {
            "statut": statut,
            "creation_date": creation_date,
            "registrar": registrar,
            "pendingDelete": pendingDelete,
            "redemptionPeriod": redemptionPeriod,
        }

    if force != 1:
        cached_data = cache.get(domain)
        if cached_data:
            # enrich from raw before removing it
            parsed = parse_whois(cached_data.get("raw"), tld)
            # ne pas exposer le champ raw dans la réponse JSON
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
    # enrich from raw before removing it (comme pour le cache hit)
    parsed = parse_whois(cached_data.get("raw"), tld)
    cached_data.pop("raw", None)
    cached_data.update(parsed)
    # ensure coherence: if pendingDelete or redemptionPeriod, available must be False
    if cached_data.get("pendingDelete") or cached_data.get("redemptionPeriod"):
        cached_data["available"] = False
    return cached_data
    cached_data.update(parsed)
    return cached_data
