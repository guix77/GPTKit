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
