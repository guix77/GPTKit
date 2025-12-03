import os
import pytest

def parse_whois(raw: str, tld: str):
    if not raw:
        return {"statut": None, "creation_date": None, "registrar": None, "pendingDelete": False, "redemptionPeriod": False}
    raw_lines = [l.strip() for l in raw.splitlines() if l.strip()]
    statut = None
    creation_date = None
    registrar = None
    pendingDelete = False
    redemptionPeriod = False
    import re
    for line in raw_lines:
        l = line.lower()
        if registrar is None and l.startswith("registrar:") and not ("whois server" in l or "url" in l):
            parts = line.split(":", 1)
            if len(parts) == 2:
                registrar = parts[1].strip()
                continue
        if creation_date is None and ("creation date" in l or "created on" in l or "created:" in l or "creation:" in l or "registered on" in l):
            parts = line.split(":", 1)
            if len(parts) == 2:
                creation_date = parts[1].strip()
                continue
        if "status:" in l or l.startswith("domain status"):
            if statut is None:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    statut = parts[1].strip()
            if "pendingdelete" in l:
                pendingDelete = True
            if "redemptionperiod" in l:
                redemptionPeriod = True
            continue
    if registrar is None:
        m = re.search(r"registrar\s+([\w\-\. ]{3,})", raw, re.IGNORECASE)
        if m:
            registrar = m.group(1).strip()
    return {"statut": statut, "creation_date": creation_date, "registrar": registrar, "pendingDelete": pendingDelete, "redemptionPeriod": redemptionPeriod}

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
