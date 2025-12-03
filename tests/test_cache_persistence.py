import os
import pytest
from app.services.cache import WhoisCache


def test_cache_persistence(tmp_path):
    # Use a temporary DB for isolation
    db_file = tmp_path / "whois_cache.db"
    cache = WhoisCache(db_path=str(db_file))

    # sample data from tests/data
    domain = "cadeaux.com"
    tld = "com"
    path = os.path.join(os.path.dirname(__file__), "data", "whois-cadeaux.com")
    with open(path, encoding="utf-8") as f:
        raw = f.read()

    # Ensure set() stores parsed fields
    cache.set(domain, tld, available=False, raw=raw)
    entry = cache.get(domain)
    assert entry is not None
    # parsed fields should be present and match expectations
    assert entry.get("registrar") == "OVH sas"
    assert entry.get("creation_date") == "2002-05-13T18:12:06Z"
    assert entry.get("pendingDelete") in (0, 1, False, True)
    # Normalize to boolean check
    assert bool(int(entry.get("pendingDelete"))) is False
