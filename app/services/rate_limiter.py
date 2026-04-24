from collections import defaultdict, deque
import time
from typing import Literal

type RateLimitReason = Literal["global_limit", "domain_limit"]


class RateLimiter:
    def __init__(self, global_limit: int = 60, domain_limit: int = 5):
        self.global_limit = global_limit  # per minute
        self.domain_limit = domain_limit  # per minute
        self.global_hits: deque[float] = deque()
        self.domain_hits: defaultdict[str, deque[float]] = defaultdict(deque)

    def _cleanup(self, hits: deque[float], window: int = 60) -> None:
        now = time.time()
        while hits and hits[0] < now - window:
            hits.popleft()

    def check(self, domain: str) -> bool:
        return self.check_reason(domain) is None

    def check_reason(self, domain: str) -> RateLimitReason | None:
        # Cleanup first
        self._cleanup(self.global_hits)
        self._cleanup(self.domain_hits[domain])

        if len(self.global_hits) >= self.global_limit:
            return "global_limit"

        if len(self.domain_hits[domain]) >= self.domain_limit:
            return "domain_limit"

        return None

    def add(self, domain: str) -> None:
        now = time.time()
        self.global_hits.append(now)
        self.domain_hits[domain].append(now)
