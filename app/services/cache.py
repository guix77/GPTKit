import logging
import os
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

type CacheRow = dict[str, object]


class WhoisCache:
    def __init__(self, db_path: str | None = None):
        # Allow overriding DB path for tests or alternate deployments
        self.db_path = db_path or "data/whois_cache.db"
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        # Run lightweight migrations/backfill if needed (safe to call on every start)
        try:
            self._migrate_if_needed()
        except Exception:
            logger.exception("Migration failed during cache init. Continuing without migration.")

    def _init_db(self) -> None:
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
                    created_at TEXT,
                    registrar TEXT,
                    pending_delete BOOLEAN,
                    redemption_period BOOLEAN
                )
            """)

    def get(self, domain: str) -> CacheRow | None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM whois_cache WHERE domain = ?", (domain,))
                row = cursor.fetchone()
                if row:
                    logger.debug("Cache HIT for domain: %s", domain)
                    return dict(row)
                logger.debug("Cache MISS for domain: %s", domain)
        except sqlite3.Error as e:
            logger.error("Cache error on get(%s): %s", domain, e)
            return None
        return None

    def set(self, domain: str, tld: str, available: bool, raw: str) -> None:
        checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        # parse raw to extract fields to persist
        try:
            from app.services.whois import parse_whois
            parsed = parse_whois(raw, tld)
        except Exception:
            parsed = {"statut": None, "created_at": None, "registrar": None, "pending_delete": False, "redemption_period": False}

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO whois_cache
                    (domain, tld, available, checked_at, raw, statut, created_at, registrar, pending_delete, redemption_period)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    domain,
                    tld,
                    int(bool(available)),
                    checked_at,
                    raw,
                    parsed.get("statut"),
                    parsed.get("created_at"),
                    parsed.get("registrar"),
                    int(bool(parsed.get("pending_delete"))),
                    int(bool(parsed.get("redemption_period")))
                ))
            logger.debug("Cache SET for domain: %s (checked_at: %s)", domain, checked_at)
        except sqlite3.Error as e:
            logger.error("Cache error on set(%s): %s", domain, e)

    def _migrate_if_needed(self) -> None:
        """Detect missing expected columns, add them, migrate old column names to new ones, and backfill parsed fields from raw."""
        EXPECTED = {
            "statut": "TEXT",
            "created_at": "TEXT",
            "registrar": "TEXT",
            "pending_delete": "BOOLEAN",
            "redemption_period": "BOOLEAN",
        }

        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("PRAGMA table_info('whois_cache')")
                existing = {row[1] for row in cur.fetchall()}  # column names
                
                # Add new columns if they don't exist
                to_add = [(n, t) for n, t in EXPECTED.items() if n not in existing]
                if to_add:
                    logger.info("Cache migration: adding columns: %s", [n for n, _ in to_add])
                    for name, coltype in to_add:
                        try:
                            conn.execute(f"ALTER TABLE whois_cache ADD COLUMN {name} {coltype}")
                        except sqlite3.Error:
                            logger.exception(f"Failed to add column {name}; continuing")
                    conn.commit()

                # Migrate old column names to new ones if old columns exist
                old_to_new = {
                    "creation_date": "created_at",
                    "pendingDelete": "pending_delete",
                    "redemptionPeriod": "redemption_period",
                }
                
                for old_col, new_col in old_to_new.items():
                    if old_col in existing and new_col in existing:
                        # Copy data from old column to new column where new column is NULL
                        try:
                            result = conn.execute(f"""
                                UPDATE whois_cache 
                                SET {new_col} = {old_col} 
                                WHERE {new_col} IS NULL AND {old_col} IS NOT NULL
                            """)
                            if result.rowcount > 0:
                                logger.info("Cache migration: migrated %s rows from %s to %s", result.rowcount, old_col, new_col)
                                conn.commit()
                        except sqlite3.Error:
                            logger.exception(f"Failed to migrate {old_col} to {new_col}; continuing")

                # Backfill parsed fields for rows where raw is present and parsed columns are NULL/empty
                sel = "SELECT domain, raw, tld FROM whois_cache WHERE raw IS NOT NULL AND (statut IS NULL OR created_at IS NULL OR registrar IS NULL OR pending_delete IS NULL OR redemption_period IS NULL)"
                rows = conn.execute(sel).fetchall()
                if rows:
                    logger.info("Cache migration: backfilling parsed fields for %s rows", len(rows))
                # Import parser locally to avoid circular issues
                try:
                    from app.services.whois import parse_whois
                except Exception:
                    logger.exception("Could not import parse_whois for migration; skipping backfill")
                    return

                upd = "UPDATE whois_cache SET statut = ?, created_at = ?, registrar = ?, pending_delete = ?, redemption_period = ? WHERE domain = ?"
                updated = 0
                for domain, raw, tld in rows:
                    try:
                        parsed = parse_whois(raw, tld)
                        conn.execute(upd, (
                            parsed.get("statut"),
                            parsed.get("created_at"),
                            parsed.get("registrar"),
                            int(bool(parsed.get("pending_delete"))),
                            int(bool(parsed.get("redemption_period"))),
                            domain,
                        ))
                        updated += 1
                    except Exception:
                        logger.exception(f"Failed to backfill domain {domain}; skipping")
                if updated:
                    conn.commit()
                    logger.info("Cache migration: backfilled %s rows", updated)
        except sqlite3.Error:
            logger.exception("SQLite error during cache migration")
