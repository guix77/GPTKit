import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import logging
import os

logger = logging.getLogger(__name__)

class WhoisCache:
    def __init__(self):
        self.db_path = "data/whois_cache.db"
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS whois_cache (
                    domain TEXT PRIMARY KEY,
                    tld TEXT,
                    available BOOLEAN,
                    checked_at TEXT,
                    raw TEXT
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

    def set(self, domain: str, tld: str, available: bool, raw: str):
        checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO whois_cache (domain, tld, available, checked_at, raw)
                    VALUES (?, ?, ?, ?, ?)
                """, (domain, tld, available, checked_at, raw))
            logger.debug(f"Cache SET for domain: {domain} (checked_at: {checked_at})")
        except sqlite3.Error as e:
            logger.error(f"Cache error on set({domain}): {e}")
