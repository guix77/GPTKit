import subprocess
import logging

logger = logging.getLogger(__name__)

class WhoisService:
    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    def lookup(self, domain: str) -> str:
        try:
            # Extract TLD to determine the appropriate WHOIS server
            parts = domain.split(".")
            tld = parts[-1].lower() if parts else ""
            
            # Use appropriate WHOIS server based on TLD
            if tld == "fr":
                whois_server = "whois.afnic.fr"
            else:
                # Default to Verisign for .com, .net, and other common TLDs
                whois_server = "whois.verisign-grs.com"
            
            result = subprocess.run(
                ["whois", "-h", whois_server, domain],
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
            "%% not found",  # AFNIC format for .fr domains
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
    """Extract statut, created_at, registrar, pending_delete, redemption_period for all TLDs.

    Heuristic parser reused across the app and migration scripts.
    """
    if not raw:
        return {
            "statut": None,
            "created_at": None,
            "registrar": None,
            "pending_delete": False,
            "redemption_period": False,
        }

    raw_lines = [l.strip() for l in raw.splitlines() if l.strip()]
    lower = raw.lower()

    statut = None
    created_at = None
    registrar = None
    pending_delete = False
    redemption_period = False

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
        if created_at is None and ("creation date" in l or "created on" in l or "created:" in l or "creation:" in l or "registered on" in l):
            parts = line.split(":", 1)
            if len(parts) == 2:
                created_at = parts[1].strip()
                continue
        # Status lines (can have multiple)
        if "status:" in l or l.startswith("domain status"):
            if statut is None:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    statut = parts[1].strip()
            # Check for pending_delete and redemption_period in any status line
            if "pendingdelete" in l:
                pending_delete = True
            if "redemptionperiod" in l:
                redemption_period = True
            continue

    # Fallback regex for Registrar lines like 'Registrar Name' without colon
    if registrar is None:
        m = re.search(r"registrar\s+([\w\-\. ]{3,})", raw, re.IGNORECASE)
        if m:
            registrar = m.group(1).strip()

    return {
        "statut": statut,
        "created_at": created_at,
        "registrar": registrar,
        "pending_delete": pending_delete,
        "redemption_period": redemption_period,
    }
