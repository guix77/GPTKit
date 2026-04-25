import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.cache import WhoisCache
from app.services.rate_limiter import RateLimiter


@pytest.fixture
def temp_cache():
    """Create a temporary cache database for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_whois_cache.db")
    cache = WhoisCache(db_path=db_path)
    yield cache
    shutil.rmtree(temp_dir)


@pytest.fixture
def client(temp_cache, monkeypatch):
    """Create a test client with mocked cache and disabled auth."""
    monkeypatch.setenv("GPTKIT_DISABLE_AUTH", "1")

    from app.routers import domain

    original_cache = domain.cache
    original_rate_limiter = domain.rate_limiter
    domain.cache = temp_cache
    domain.rate_limiter = RateLimiter()

    client = TestClient(app)
    yield client

    domain.cache = original_cache
    domain.rate_limiter = original_rate_limiter


@pytest.fixture
def client_with_auth(temp_cache, monkeypatch):
    """Create a test client with authentication enabled."""
    monkeypatch.setenv("GPTKIT_BEARER_TOKEN", "test-token-123")
    monkeypatch.delenv("GPTKIT_DISABLE_AUTH", raising=False)

    from app.routers import domain

    original_cache = domain.cache
    original_rate_limiter = domain.rate_limiter
    domain.cache = temp_cache
    domain.rate_limiter = RateLimiter()

    client = TestClient(app)
    yield client

    domain.cache = original_cache
    domain.rate_limiter = original_rate_limiter


class MockWhoisService:
    def __init__(self):
        self.lookup_calls = []

    def lookup(self, domain):
        self.lookup_calls.append(domain)
        return (
            f"Domain Name: {domain}\n"
            "Creation Date: 2020-01-01T00:00:00Z\n"
            "Registrar: Test Registrar"
        )

    def is_available(self, raw, tld):
        return "available" in raw.lower()


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "GPTKit is running"}


def test_availability_requires_at_least_one_domain(client):
    response = client.get("/domain/availability")
    assert response.status_code == 422


def test_availability_authentication_required(client_with_auth):
    response = client_with_auth.get("/domain/availability?domain=example.com")
    assert response.status_code == 401
    assert "detail" in response.json()

    response = client_with_auth.get(
        "/domain/availability?domain=example.com",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401

    response = client_with_auth.get(
        "/domain/availability?domain=example.com",
        headers={"Authorization": "Bearer test-token-123"},
    )
    assert response.status_code != 401


def test_availability_single_domain_success(client):
    from app.routers import domain

    original_service = domain.whois_service
    domain.whois_service = MockWhoisService()

    try:
        response = client.get("/domain/availability?domain=example.com")
        assert response.status_code == 200
        result = response.json()
        assert result["domain"] == "example.com"
        assert result["available"] is False
        assert result["status"] == "ok"
        assert result["checked_at"]
    finally:
        domain.whois_service = original_service


def test_availability_cache_hit_skips_live_lookup(client):
    from app.routers import domain

    domain.cache.set(
        "cached.com",
        "com",
        False,
        "Domain Name: cached.com\nCreation Date: 2021-01-01T00:00:00Z\nRegistrar: Test",
    )

    original_service = domain.whois_service
    mock_service = MockWhoisService()
    domain.whois_service = mock_service

    try:
        response = client.get("/domain/availability?domain=cached.com")
        assert response.status_code == 200

        result = response.json()
        assert result["domain"] == "cached.com"
        assert result["available"] is False
        assert result["status"] == "ok"
        assert result["checked_at"]
        assert mock_service.lookup_calls == []
    finally:
        domain.whois_service = original_service


def test_availability_invalid_domain_returns_stable_result(client):
    from app.routers import domain

    original_service = domain.whois_service
    mock_service = MockWhoisService()
    domain.whois_service = mock_service

    try:
        response = client.get("/domain/availability?domain=invalid")
        assert response.status_code == 200

        assert response.json() == {
            "domain": "invalid",
            "available": None,
            "checked_at": "",
            "status": "invalid_domain",
        }
        assert mock_service.lookup_calls == []
    finally:
        domain.whois_service = original_service


def test_availability_rate_limited_returns_stable_result(client):
    from app.routers import domain

    original_service = domain.whois_service
    original_rate_limiter = domain.rate_limiter
    mock_service = MockWhoisService()
    domain.whois_service = mock_service
    domain.rate_limiter = RateLimiter(global_limit=1, domain_limit=5)
    domain.rate_limiter.add("already-counted.com")

    try:
        response = client.get("/domain/availability?domain=one.com")
        assert response.status_code == 200

        assert response.json() == {
            "domain": "one.com",
            "available": None,
            "checked_at": "",
            "status": "rate_limited",
        }
    finally:
        domain.whois_service = original_service
        domain.rate_limiter = original_rate_limiter


def test_availability_response_does_not_expose_whois_details(client):
    from app.routers import domain

    original_service = domain.whois_service
    domain.whois_service = MockWhoisService()

    try:
        response = client.get("/domain/availability?domain=example.com")
        assert response.status_code == 200

        result = response.json()
        assert set(result.keys()) == {"domain", "available", "checked_at", "status"}
        assert "raw" not in result
        assert "created_at" not in result
        assert "registrar" not in result
        assert "statut" not in result
        assert "pending_delete" not in result
        assert "redemption_period" not in result
    finally:
        domain.whois_service = original_service


def test_openapi_exposes_availability_endpoint_only(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert "/domain/availability" in schema["paths"]
    assert "/domain/whois" not in schema["paths"]

    parameters = schema["paths"]["/domain/availability"]["get"]["parameters"]
    assert {parameter["name"] for parameter in parameters} == {"domain"}
    domain_parameter = next(parameter for parameter in parameters if parameter["name"] == "domain")
    assert domain_parameter["required"] is True
    assert domain_parameter["schema"]["type"] == "string"
