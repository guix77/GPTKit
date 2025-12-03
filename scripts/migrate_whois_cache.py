#!/usr/bin/env python3
"""
Migration script for whois_cache SQLite DB.
- Adds missing columns (statut, creation_date, registrar, pendingDelete, redemptionPeriod)
- Backfills parsed fields from existing raw values using app.services.whois.parse_whois

Usage:
    ./scripts/migrate_whois_cache.py

It will operate on data/whois_cache.db relative to the repository root.
"""
import sqlite3
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "whois_cache.db"

EXPECTED_COLUMNS = {
    "statut": "TEXT",
    "creation_date": "TEXT",
    "registrar": "TEXT",
    "pendingDelete": "BOOLEAN",
    "redemptionPeriod": "BOOLEAN",
}


def get_existing_columns(conn):
    cur = conn.execute("PRAGMA table_info('whois_cache')")
    return {row[1]: row for row in cur.fetchall()}  # name -> row


def add_column(conn, name, coltype):
    print(f"Adding column {name} {coltype}")
    conn.execute(f"ALTER TABLE whois_cache ADD COLUMN {name} {coltype}")


def main():
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}, nothing to migrate.\nYou can run the app and it will create a fresh DB with the new schema.")
        return

    import importlib
    sys.path.insert(0, str(REPO_ROOT))
    try:
        whois_mod = importlib.import_module("app.services.whois")
    except Exception as e:
        print(f"Failed to import app.services.whois: {e}")
        raise

    parse_whois = getattr(whois_mod, "parse_whois", None)
    if parse_whois is None:
        print("parse_whois not found in app.services.whois; aborting")
        return

    conn = sqlite3.connect(str(DB_PATH))
    try:
        existing = get_existing_columns(conn)
        to_add = [ (n,t) for n,t in EXPECTED_COLUMNS.items() if n not in existing ]
        if not to_add:
            print("No columns to add.")
        else:
            for name, coltype in to_add:
                add_column(conn, name, coltype)
            conn.commit()
            print(f"Added {len(to_add)} columns.")

        # Backfill parsed values for rows that have raw
        cur = conn.execute("SELECT domain, raw, tld FROM whois_cache WHERE raw IS NOT NULL")
        rows = cur.fetchall()
        print(f"Found {len(rows)} rows with raw to backfill.")
        updated = 0
        for domain, raw, tld in rows:
            parsed = parse_whois(raw, tld)
            conn.execute(
                "UPDATE whois_cache SET statut = ?, creation_date = ?, registrar = ?, pendingDelete = ?, redemptionPeriod = ? WHERE domain = ?",
                (
                    parsed.get("statut"),
                    parsed.get("creation_date"),
                    parsed.get("registrar"),
                    int(bool(parsed.get("pendingDelete"))),
                    int(bool(parsed.get("redemptionPeriod"))),
                    domain,
                )
            )
            updated += 1
        conn.commit()
        print(f"Backfilled parsed fields for {updated} rows.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
