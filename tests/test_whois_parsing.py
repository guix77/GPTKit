import os
import pytest
from app.services.whois import parse_whois

def test_parse_whois_cadeaux_com():
    path = os.path.join(os.path.dirname(__file__), "data", "whois-cadeaux.com")
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    tld = "com"
    result = parse_whois(raw, tld)
    assert result["statut"] is not None, f"statut should not be None, got {result['statut']}"
    assert result["creation_date"] == "2002-05-13T18:12:06Z"
    assert result["registrar"] == "OVH sas"
    assert result["pendingDelete"] == False
    assert result["redemptionPeriod"] == False

def test_parse_whois_assiste_com():
    path = os.path.join(os.path.dirname(__file__), "data", "whois-assiste.com")
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    tld = "com"
    result = parse_whois(raw, tld)
    assert result["statut"] is not None, f"statut should not be None, got {result['statut']}"
    assert result["creation_date"] == "2003-09-15T11:32:57Z"
    assert result["registrar"] == "Gandi SAS"
    assert result["pendingDelete"] == True, f"pendingDelete should be True, got {result['pendingDelete']}"
    assert result["redemptionPeriod"] == False
