import time
from collections import defaultdict

class RateLimiter:
    def __init__(self, global_limit: int = 60, domain_limit: int = 5):
        self.global_limit = global_limit # per minute
        self.domain_limit = domain_limit # per minute
        self.global_hits = []
        self.domain_hits = defaultdict(list)

    def _cleanup(self, hits: list, window: int = 60):
        now = time.time()
        while hits and hits[0] < now - window:
            hits.pop(0)

    def check(self, domain: str) -> bool:
        return self.check_reason(domain) is None

    def check_reason(self, domain: str):
        # Cleanup first
        self._cleanup(self.global_hits)
        self._cleanup(self.domain_hits[domain])

        if len(self.global_hits) >= self.global_limit:
            return "global_limit"

        if len(self.domain_hits[domain]) >= self.domain_limit:
            return "domain_limit"

        return None

    def add(self, domain: str):
        now = time.time()
        self.global_hits.append(now)
        self.domain_hits[domain].append(now)
