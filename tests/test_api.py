import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.cache import WhoisCache
import tempfile
import shutil

# Mock the cache to use a temporary database for tests
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
    # Disable authentication for tests
    monkeypatch.setenv("GPTKIT_DISABLE_AUTH", "1")
    
    # Mock the cache instance
    from app.routers import domain
    original_cache = domain.cache
    domain.cache = temp_cache
    
    client = TestClient(app)
    yield client
    
    # Restore original cache
    domain.cache = original_cache

@pytest.fixture
def client_with_auth(temp_cache, monkeypatch):
    """Create a test client with authentication enabled."""
    monkeypatch.setenv("GPTKIT_BEARER_TOKEN", "test-token-123")
    monkeypatch.delenv("GPTKIT_DISABLE_AUTH", raising=False)
    
    # Mock the cache instance
    from app.routers import domain
    original_cache = domain.cache
    domain.cache = temp_cache
    
    client = TestClient(app)
    yield client
    
    # Restore original cache
    domain.cache = original_cache

def test_root_endpoint(client):
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "GPTKit is running"}

def test_whois_invalid_domain(client):
    """Test WHOIS endpoint with invalid domain."""
    response = client.get("/domain/whois?domain=invalid")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_domain"
    assert "message" in response.json()

def test_whois_authentication_required(client_with_auth):
    """Test that authentication is required when token is set."""
    # Request without token
    response = client_with_auth.get("/domain/whois?domain=example.com")
    assert response.status_code == 401
    assert "detail" in response.json()
    
    # Request with invalid token
    response = client_with_auth.get(
        "/domain/whois?domain=example.com",
        headers={"Authorization": "Bearer wrong-token"}
    )
    assert response.status_code == 401
    
    # Request with valid token
    response = client_with_auth.get(
        "/domain/whois?domain=example.com",
        headers={"Authorization": "Bearer test-token-123"}
    )
    # Should not be 401 (might be 500 if whois lookup fails, but auth should pass)
    assert response.status_code != 401

def test_whois_minimal_format(client, monkeypatch):
    """Test WHOIS endpoint returns a stable format by default."""
    # Mock whois lookup to avoid actual network calls
    from app.services.whois import WhoisService
    from app.routers import domain
    
    class MockWhoisService:
        def lookup(self, domain):
            return "Domain Name: example.com\nCreation Date: 2020-01-01T00:00:00Z\nRegistrar: Test Registrar"
        
        def is_available(self, raw, tld):
            return False
    
    original_service = domain.whois_service
    domain.whois_service = MockWhoisService()
    
    try:
        response = client.get("/domain/whois?domain=example.com")
        assert response.status_code == 200
        data = response.json()
        
        # Check stable format structure
        assert "domain" in data
        assert "available" in data
        assert "created_at" in data
        assert "tld" in data
        assert "checked_at" in data
        assert "raw" in data
        assert "registrar" in data
        assert "pending_delete" in data
        assert "redemption_period" in data
        assert "statut" in data
        assert data["raw"] == ""
        assert data["created_at"] == "2020-01-01T00:00:00Z"
    finally:
        domain.whois_service = original_service

def test_whois_detailed_format(client, monkeypatch):
    """Test WHOIS endpoint includes raw output with details=1."""
    # Mock whois lookup
    from app.services.whois import WhoisService
    from app.routers import domain
    
    class MockWhoisService:
        def lookup(self, domain):
            return "Domain Name: example.com\nCreation Date: 2020-01-01T00:00:00Z\nRegistrar: Test Registrar"
        
        def is_available(self, raw, tld):
            return False
    
    original_service = domain.whois_service
    domain.whois_service = MockWhoisService()
    
    try:
        response = client.get("/domain/whois?domain=example.com&details=1")
        assert response.status_code == 200
        data = response.json()
        
        # Check detailed format structure
        assert "domain" in data
        assert "available" in data
        assert "created_at" in data
        assert "tld" in data
        assert "checked_at" in data
        assert "raw" in data
        assert "registrar" in data
        assert "pending_delete" in data
        assert "redemption_period" in data
        assert "example.com" in data["raw"]
    finally:
        domain.whois_service = original_service

def test_whois_refresh_parameter(client, monkeypatch):
    """Test that refresh=1 forces a fresh lookup."""
    from app.services.whois import WhoisService
    from app.routers import domain
    
    lookup_called = []
    
    class MockWhoisService:
        def lookup(self, domain):
            lookup_called.append(domain)
            return "Domain Name: example.com\nCreation Date: 2020-01-01T00:00:00Z"
        
        def is_available(self, raw, tld):
            return False
    
    original_service = domain.whois_service
    domain.whois_service = MockWhoisService()
    
    try:
        # First request - should cache
        response1 = client.get("/domain/whois?domain=example.com")
        assert response1.status_code == 200
        assert len(lookup_called) == 1
        
        # Second request - should use cache
        response2 = client.get("/domain/whois?domain=example.com")
        assert response2.status_code == 200
        assert len(lookup_called) == 1  # Still 1, cache used
        
        # Third request with refresh=1 - should force lookup
        response3 = client.get("/domain/whois?domain=example.com&refresh=1")
        assert response3.status_code == 200
        assert len(lookup_called) == 2  # Now 2, fresh lookup
    finally:
        domain.whois_service = original_service

def test_whois_cache_hit_format(client, monkeypatch):
    """Test that cached data returns the stable default format."""
    from app.routers import domain
    
    # Pre-populate cache
    domain.cache.set(
        "cached.com",
        "com",
        False,
        "Domain Name: cached.com\nCreation Date: 2021-01-01T00:00:00Z\nRegistrar: Test"
    )
    
    # Request should use cache
    response = client.get("/domain/whois?domain=cached.com")
    assert response.status_code == 200
    data = response.json()
    
    # Should be stable default format
    assert "domain" in data
    assert "available" in data
    assert "created_at" in data
    assert "tld" in data
    assert "checked_at" in data
    assert "raw" in data
    assert data["domain"] == "cached.com"
    assert data["available"] == False
    assert data["raw"] == ""

def test_whois_cache_hit_detailed_format(client, monkeypatch):
    """Test that cached data returns detailed format with details=1."""
    from app.routers import domain
    
    # Pre-populate cache
    domain.cache.set(
        "cached.com",
        "com",
        False,
        "Domain Name: cached.com\nCreation Date: 2021-01-01T00:00:00Z\nRegistrar: Test"
    )
    
    # Request should use cache with details=1
    response = client.get("/domain/whois?domain=cached.com&details=1")
    assert response.status_code == 200
    data = response.json()
    
    # Should be detailed format
    assert "domain" in data
    assert "available" in data
    assert "raw" in data
    assert "tld" in data
    assert data["domain"] == "cached.com"
    assert data["tld"] == "com"
    assert "cached.com" in data["raw"]

def test_whois_missing_created_at_returns_empty_string(client, monkeypatch):
    """Test that text fields stay strings even when WHOIS data is incomplete."""
    from app.routers import domain

    class MockWhoisService:
        def lookup(self, domain):
            return "Domain Name: example.com\nRegistrar: Test Registrar"

        def is_available(self, raw, tld):
            return False

    original_service = domain.whois_service
    domain.whois_service = MockWhoisService()

    try:
        response = client.get("/domain/whois?domain=example.com")
        assert response.status_code == 200
        data = response.json()
        assert data["created_at"] == ""
        assert data["registrar"] == "Test Registrar"
        assert data["raw"] == ""
    finally:
        domain.whois_service = original_service
