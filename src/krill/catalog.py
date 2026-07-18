"""Catalog database — the machine-readable command option store.

Schema matches explainshell's parsed_manpages table so both sources
merge into a unified query interface.

SQLite file lives at $XDG_DATA_HOME/krill/catalog.db (or ~/.local/share/krill/catalog.db).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class Catalog:
    """SQLite catalog of command option schemas.

    Sources (in priority order, first match wins):
    1. explainshell man page DB (coreutils, POSIX, GNU)
    2. Sandbox agent `--help` extraction (everything else)
    3. User-defined overrides (~/.config/fish/completions/ equivalent)
    """

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            xdg_data = Path.home() / ".local" / "share" / "krill"
            xdg_data.mkdir(parents=True, exist_ok=True)
            db_path = xdg_data / "catalog.db"
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS help_catalog (
                command_path TEXT PRIMARY KEY,   -- e.g. "tar" or "aws.s3.ls"
                source       TEXT NOT NULL,      -- "man_page" or "help_output" or "override"
                source_hash  TEXT,               -- for invalidation detection
                options      TEXT NOT NULL,      -- JSON array of option objects
                subcommands  TEXT,               -- JSON array of subcommand objects
                synopsis     TEXT,               -- usage line
                extracted_at INTEGER NOT NULL   -- unix timestamp
            );

            CREATE INDEX IF NOT EXISTS idx_source ON help_catalog(source);
        """)

    def get_options(self, command_path: str) -> list[dict[str, Any]] | None:
        """Return parsed options for a command path, or None if not catalogued."""
        row = self.conn.execute(
            "SELECT options FROM help_catalog WHERE command_path = ?",
            (command_path,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["options"])

    def get_subcommands(self, command_path: str) -> list[dict[str, Any]]:
        """Return known subcommands, or empty list."""
        row = self.conn.execute(
            "SELECT subcommands FROM help_catalog WHERE command_path = ?",
            (command_path,),
        ).fetchone()
        if row is None or row["subcommands"] is None:
            return []
        return json.loads(row["subcommands"])

    def upsert(
        self,
        command_path: str,
        source: str,
        options: list[dict[str, Any]],
        *,
        subcommands: list[dict[str, Any]] | None = None,
        synopsis: str | None = None,
        source_hash: str | None = None,
    ) -> None:
        """Insert or update a command entry."""
        self.conn.execute(
            """INSERT OR REPLACE INTO help_catalog
               (command_path, source, source_hash, options, subcommands, synopsis, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                command_path,
                source,
                source_hash,
                json.dumps(options),
                json.dumps(subcommands) if subcommands else None,
                synopsis,
                int(time.time()),
            ),
        )
        self.conn.commit()

    def needs_extraction(self, command_path: str) -> bool:
        """Return True if command is not yet catalogued."""
        row = self.conn.execute(
            "SELECT 1 FROM help_catalog WHERE command_path = ?",
            (command_path,),
        ).fetchone()
        return row is None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None