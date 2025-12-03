import subprocess
import logging

logger = logging.getLogger(__name__)

class WhoisService:
    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    def lookup(self, domain: str) -> str:
        try:
            # Using -H to suppress legal disclaimers if possible, but standard whois usually just works
            result = subprocess.run(
                ["whois", "-h", "whois.verisign-grs.com", domain],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            if result.returncode != 0:
                # Some whois clients return 1 if not found, so we check stderr/stdout
                if not result.stdout and result.stderr:
                     logger.error(f"Whois command failed: {result.stderr}")
                     raise Exception("Whois command failed")
            
            return result.stdout
        except subprocess.TimeoutExpired:
            raise Exception("Whois lookup timed out")
        except Exception as e:
            logger.error(f"Whois lookup error: {e}")
            raise

    def is_available(self, raw_output: str, tld: str) -> bool:
        if not raw_output:
            return False
            
        raw_lower = raw_output.lower()
        
        # Patterns indicating availability
        # These are heuristic and might need refinement per TLD
        not_found_patterns = [
            "no match",
            "not found",
            "no entries found",
            "status: free",
            "nothing found",
            "no data found",
            "domain not found",
            "is available for registration"
        ]
        
        for pattern in not_found_patterns:
            if pattern in raw_lower:
                return True
                
        return False


def parse_whois(raw: str, tld: str):
    """Extract statut, creation_date, registrar, pendingDelete, redemptionPeriod for all TLDs.

    Heuristic parser reused across the app and migration scripts.
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

    # Common patterns (generalized for many TLDs)
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
