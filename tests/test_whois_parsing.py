import os
import pytest
from app.services.whois import parse_whois, WhoisService

def test_parse_whois_cadeaux_com():
    path = os.path.join(os.path.dirname(__file__), "data", "whois-cadeaux.com")
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    tld = "com"
    result = parse_whois(raw, tld)
    assert result["statut"] is not None, f"statut should not be None, got {result['statut']}"
    assert result["created_at"] == "2002-05-13T18:12:06Z"
    assert result["registrar"] == "OVH sas"
    assert result["pending_delete"] == False
    assert result["redemption_period"] == False

def test_parse_whois_assiste_com():
    path = os.path.join(os.path.dirname(__file__), "data", "whois-assiste.com")
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    tld = "com"
    result = parse_whois(raw, tld)
    assert result["statut"] is not None, f"statut should not be None, got {result['statut']}"
    assert result["created_at"] == "2003-09-15T11:32:57Z"
    assert result["registrar"] == "Gandi SAS"
    assert result["pending_delete"] == True, f"pending_delete should be True, got {result['pending_delete']}"
    assert result["redemption_period"] == False

def test_parse_whois_argent_fr():
    path = os.path.join(os.path.dirname(__file__), "data", "whois-argent.fr")
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    tld = "fr"
    result = parse_whois(raw, tld)
    assert result["statut"] == "ACTIVE", f"statut should be ACTIVE, got {result['statut']}"
    assert result["created_at"] == "2000-07-10T22:00:00Z"
    assert result["registrar"] == "OVH"
    assert result["pending_delete"] == False
    assert result["redemption_period"] == False

def test_is_available_nodomain_fr():
    """Test that nodomain.fr is detected as available (NOT FOUND)."""
    path = os.path.join(os.path.dirname(__file__), "data", "whois-nodomain.fr")
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    service = WhoisService()
    assert service.is_available(raw, "fr") == True, "nodomain.fr should be detected as available"

def test_is_available_argent_fr():
    """Test that argent.fr is detected as not available (exists)."""
    path = os.path.join(os.path.dirname(__file__), "data", "whois-argent.fr")
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    service = WhoisService()
    assert service.is_available(raw, "fr") == False, "argent.fr should be detected as not available"
