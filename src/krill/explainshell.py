"""Explainshell database integration.

Queries the explainshell SQLite DB (parsed man pages) and translates
option schemas into krill's format for the Catalog.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


class ExplainshellDB:
    """Read-only access to explainshell's SQLite man page database.

    The DB is published as a GitHub release at:
        https://github.com/idank/explainshell/releases/tag/db-latest

    Schema:
        manpages        — raw man page text (blob)
        parsed_manpages — extracted options (JSON), synopsis, subcommands
        mappings        — command name → parsed_manpages.source
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Explainshell DB not found: {db_path}")
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def resolve_command(self, command_path: str) -> str | None:
        """Find the parsed_manpages source for a command path.

        Args:
            command_path: e.g., "tar", "git", "git commit", "aws s3 ls"

        Returns:
            parsed_manpages.source value, or None if not found.
        """
        row = self.conn.execute(
            "SELECT dst, score FROM mappings WHERE src = ? ORDER BY score DESC LIMIT 1",
            (command_path,),
        ).fetchone()
        return row["dst"] if row else None

    def get_options(self, command_path: str) -> list[dict[str, Any]] | None:
        """Get options for a command in krill-compatible format.

        Translates explainshell's option schema:
            {text, short: [...], long: [...], has_argument, ...}
        into krill's format:
            {short, long, type, description, ...}
        """
        source = self.resolve_command(command_path)
        if source is None:
            return None

        row = self.conn.execute(
            "SELECT options FROM parsed_manpages WHERE source = ?",
            (source,),
        ).fetchone()
        if row is None:
            return None

        raw_options = json.loads(row["options"])
        return [_translate_option(opt) for opt in raw_options]

    def get_subcommands(self, command_path: str) -> list[dict[str, Any]]:
        """Get subcommands for a command."""
        source = self.resolve_command(command_path)
        if source is None:
            return []

        row = self.conn.execute(
            "SELECT subcommands FROM parsed_manpages WHERE source = ?",
            (source,),
        ).fetchone()
        if row is None:
            return []

        raw_subs = json.loads(row["subcommands"])
        # Subcommands can be strings or dicts with 'name' and 'description'
        result = []
        for s in raw_subs:
            if isinstance(s, str):
                result.append({"name": s, "description": ""})
            elif isinstance(s, dict):
                result.append(s)
        return result

    def get_synopsis(self, command_path: str) -> str | None:
        """Get the synopsis line for a command."""
        source = self.resolve_command(command_path)
        if source is None:
            return None

        row = self.conn.execute(
            "SELECT synopsis FROM parsed_manpages WHERE source = ?",
            (source,),
        ).fetchone()
        return row["synopsis"] if row else None

    def list_commands(self, prefix: str = "") -> list[str]:
        """List all mapped command names, optionally filtered by prefix.

        Args:
            prefix: Optional prefix filter (e.g., "git" returns ["git", "git add", ...])

        Returns:
            Sorted list of command strings.
        """
        if prefix:
            rows = self.conn.execute(
                "SELECT DISTINCT src FROM mappings WHERE src LIKE ? ORDER BY src",
                (f"{prefix}%",),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT DISTINCT src FROM mappings ORDER BY src"
            ).fetchall()
        return [r["src"] for r in rows]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def _translate_option(raw: dict[str, Any]) -> dict[str, Any]:
    """Translate an explainshell option dict to krill format.

    Input (explainshell):
        {
            "text": "**-f**, **--file**=*ARCHIVE*\n\nUse archive file...",
            "short": ["-f"],
            "long": ["--file"],
            "has_argument": true,
            "positional": null,
            "nested_cmd": false,
            "meta": {"lines": [88, 93]}
        }

    Output (krill):
        {
            "short": "-f",
            "long": "--file",
            "type": "string",
            "description": "Use archive file or device",
            "required": false
        }
    """
    shorts = raw.get("short") or []
    longs = raw.get("long") or []
    text = raw.get("text", "")
    has_arg = raw.get("has_argument", False)

    # Clean up the markdown-formatted text to a plain description
    description = _clean_description(text)

    return {
        "short": shorts[0] if shorts else "",
        "long": longs[0] if longs else "",
        "type": "string" if has_arg else "boolean",
        "description": description,
        "required": False,
    }


def _clean_description(text: str) -> str:
    """Extract a plain-text description from explainshell's markdown option text.

    Input:  "**-f**, **--file**=*ARCHIVE*\n\nUse archive file or device.\nThe long form is..."
    Output: "Use archive file or device."
    """
    # Remove the flag header (first line with **flags**)
    lines = text.split("\n")
    desc_lines: list[str] = []
    found_desc = False

    for line in lines:
        stripped = line.strip()
        # Skip lines that are just flag syntax
        if stripped.startswith("**-") or stripped.startswith("*-"):
            continue
        # Skip empty lines before description starts
        if not stripped and not found_desc:
            continue
        if stripped:
            # Clean up markdown bold/italic
            cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', stripped)
            cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)
            cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
            desc_lines.append(cleaned)
            found_desc = True
        elif found_desc:
            # Empty line after description — stop
            break

    desc = " ".join(desc_lines)
    # Take first sentence if it's long
    if len(desc) > 120:
        first_sentence = re.match(r'^([^.]+\.)', desc)
        if first_sentence:
            desc = first_sentence.group(1)
    return desc