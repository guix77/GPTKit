import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import logging
import os

logger = logging.getLogger(__name__)

class WhoisCache:
    def __init__(self, db_path: str = None):
        # Allow overriding DB path for tests or alternate deployments
        self.db_path = db_path or "data/whois_cache.db"
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        # Run lightweight migrations/backfill if needed (safe to call on every start)
        try:
            self._migrate_if_needed()
        except Exception:
            logger.exception("Migration failed during cache init. Continuing without migration.")

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # Create table with parsed fields. For older DBs, migration script will add missing columns.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS whois_cache (
                    domain TEXT PRIMARY KEY,
                    tld TEXT,
                    available BOOLEAN,
                    checked_at TEXT,
                    raw TEXT,
                    statut TEXT,
                    creation_date TEXT,
                    registrar TEXT,
                    pendingDelete BOOLEAN,
                    redemptionPeriod BOOLEAN
                )
            """)

    def get(self, domain: str) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM whois_cache WHERE domain = ?", (domain,))
                row = cursor.fetchone()
                if row:
                    logger.debug(f"Cache HIT for domain: {domain}")
                    return dict(row)
                else:
                    logger.debug(f"Cache MISS for domain: {domain}")
        except sqlite3.Error as e:
            logger.error(f"Cache error on get({domain}): {e}")
            return None
        return None
    def _ensure_bool(self, val):
        # SQLite stores booleans as 0/1 or NULL. Normalize to Python bool where appropriate.
        if val is None:
            return False
        try:
            return bool(int(val))
        except Exception:
            return bool(val)

    def set(self, domain: str, tld: str, available: bool, raw: str):
        checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        # parse raw to extract fields to persist
        try:
            from app.services.whois import parse_whois
            parsed = parse_whois(raw, tld)
        except Exception:
            parsed = {"statut": None, "creation_date": None, "registrar": None, "pendingDelete": False, "redemptionPeriod": False}

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO whois_cache
                    (domain, tld, available, checked_at, raw, statut, creation_date, registrar, pendingDelete, redemptionPeriod)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    domain,
                    tld,
                    int(bool(available)),
                    checked_at,
                    raw,
                    parsed.get("statut"),
                    parsed.get("creation_date"),
                    parsed.get("registrar"),
                    int(bool(parsed.get("pendingDelete"))),
                    int(bool(parsed.get("redemptionPeriod")))
                ))
            logger.debug(f"Cache SET for domain: {domain} (checked_at: {checked_at})")
        except sqlite3.Error as e:
            logger.error(f"Cache error on set({domain}): {e}")
    def _migrate_if_needed(self):
        """Detect missing expected columns, add them, and backfill parsed fields from raw."""
        EXPECTED = {
            "statut": "TEXT",
            "creation_date": "TEXT",
            "registrar": "TEXT",
            "pendingDelete": "BOOLEAN",
            "redemptionPeriod": "BOOLEAN",
        }

        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("PRAGMA table_info('whois_cache')")
                existing = {row[1] for row in cur.fetchall()}  # column names
                to_add = [(n, t) for n, t in EXPECTED.items() if n not in existing]
                if to_add:
                    logger.info(f"Cache migration: adding columns: {[n for n, _ in to_add]}")
                    for name, coltype in to_add:
                        try:
                            conn.execute(f"ALTER TABLE whois_cache ADD COLUMN {name} {coltype}")
                        except sqlite3.Error:
                            logger.exception(f"Failed to add column {name}; continuing")
                    conn.commit()

                # Backfill parsed fields for rows where raw is present and parsed columns are NULL/empty
                sel = "SELECT domain, raw, tld FROM whois_cache WHERE raw IS NOT NULL AND (statut IS NULL OR creation_date IS NULL OR registrar IS NULL OR pendingDelete IS NULL OR redemptionPeriod IS NULL)"
                rows = conn.execute(sel).fetchall()
                if rows:
                    logger.info(f"Cache migration: backfilling parsed fields for {len(rows)} rows")
                # Import parser locally to avoid circular issues
                try:
                    from app.services.whois import parse_whois
                except Exception:
                    logger.exception("Could not import parse_whois for migration; skipping backfill")
                    return

                upd = "UPDATE whois_cache SET statut = ?, creation_date = ?, registrar = ?, pendingDelete = ?, redemptionPeriod = ? WHERE domain = ?"
                updated = 0
                for domain, raw, tld in rows:
                    try:
                        parsed = parse_whois(raw, tld)
                        conn.execute(upd, (
                            parsed.get("statut"),
                            parsed.get("creation_date"),
                            parsed.get("registrar"),
                            int(bool(parsed.get("pendingDelete"))),
                            int(bool(parsed.get("redemptionPeriod"))),
                            domain,
                        ))
                        updated += 1
                    except Exception:
                        logger.exception(f"Failed to backfill domain {domain}; skipping")
                if updated:
                    conn.commit()
                    logger.info(f"Cache migration: backfilled {updated} rows")
        except sqlite3.Error:
            logger.exception("SQLite error during cache migration")
