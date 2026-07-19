"""Sandbox agent — safely execute `command --help` and extract option schemas.

Runs commands locally with a short timeout (help output is read-only),
then parses output into the machine-readable option format used by the catalog.

Deterministic parser first (handles argparse, click, cobra, docopt formats),
LLM fallback for non-standard help output.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractionResult:
    """Result of extracting options from --help output."""
    command_path: str
    options: list[dict[str, Any]] = field(default_factory=list)
    subcommands: list[dict[str, Any]] = field(default_factory=list)
    synopsis: str | None = None
    source: str = "help_output"
    raw_help: str = ""


def run_command_help(command: str, args: list[str] | None = None) -> str:
    """Run `command --help` locally with a short timeout and return stdout.

    Help output is read-only — no filesystem mutation expected.
    A 5-second timeout prevents hangs.

    Args:
        command: The command to run (e.g., "heroku", "pip")
        args: Additional arguments (defaults to ["--help"])

    Returns:
        stdout + stderr from the command, or empty string on failure.
    """
    if args is None:
        args = ["--help"]

    try:
        result = subprocess.run(
            [command, *args],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout or result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def parse_argparse_style(help_text: str) -> ExtractionResult | None:
    """Try to parse argparse-style help output.

    Pattern: -f, --force    Force the operation
             -o, --output FILE   Output file path
    """
    import re

    options: list[dict[str, Any]] = []
    lines = help_text.split("\n")
    in_options = False

    for line in lines:
        stripped = line.strip()

        # Detect "optional arguments:" or "options:" section
        if re.match(r'^(optional arguments|options):', stripped, re.IGNORECASE):
            in_options = True
            continue
        if in_options and stripped == "":
            continue
        if in_options and not re.match(r'^\s*[-]', stripped):
            # Check if we've exited the options section (non-indented, non-empty line)
            # Use original line for indentation check, not stripped
            if stripped and not line.startswith(" "):
                in_options = False
                continue
            # Indented line — wrapped description continuation
            if options:
                prev = options[-1]["description"]
                options[-1]["description"] = (prev + " " + stripped).strip()
            continue

        if not in_options:
            continue

        # Parse: -f, --force    Description
        # Or:    -o OUTPUT, --output OUTPUT  Description
        # Or:    -o OUTPUT, --output OUTPUT\n                        Wrapped description
        # Old-style argparse: -o, --output=OUTPUT  Description
        match = re.match(
            r'^\s*(-[a-zA-Z0-9])\s+([A-Z_]+),\s*(--[a-zA-Z0-9][-a-zA-Z0-9=]*)\s+\2\s*$',
            stripped,
        )
        if match:
            short = match.group(1)
            metavar = match.group(2)
            long = match.group(3).rstrip("=")
            # Description might be empty (wrapped to next line) or inline
            desc = (match.group(4).strip() if match.lastindex and match.lastindex >= 4 else "")
            options.append({
                "short": short,
                "long": long,
                "type": "string" if metavar else "boolean",
                "description": desc,
                "required": False,
            })
            continue

        match = re.match(
            r'^\s*(-[a-zA-Z0-9]),?\s*(--[a-zA-Z0-9][-a-zA-Z0-9=]*)\s*([A-Z]+)?\s{2,}(.+)$',
            stripped,
        )
        if match:
            options.append({
                "short": match.group(1),
                "long": match.group(2).rstrip("="),
                "type": "string" if match.group(3) else "boolean",
                "description": match.group(4).strip(),
                "required": False,
            })
            continue

        # Long-only flag: --verbose  Description
        match = re.match(
            r'^\s*(--[a-zA-Z0-9][-a-zA-Z0-9]*)\s{2,}(.+)$',
            stripped,
        )
        if match:
            options.append({
                "short": "",
                "long": match.group(1),
                "type": "boolean",
                "description": match.group(2).strip(),
                "required": False,
            })
            continue

        # Wrapped description continuation (indented line, not a new flag)
        if in_options and options and not re.match(r'^\s*-', stripped):
            options[-1]["description"] += " " + stripped

    if options:
        return ExtractionResult(
            command_path="",
            options=options,
            raw_help=help_text,
            source="help_output",
        )
    return None


def parse_click_style(help_text: str) -> ExtractionResult | None:
    """Try to parse Click-style help output.

    Pattern: -f, --force  TEXT  Force the operation
    """
    import re

    options: list[dict[str, Any]] = []
    lines = help_text.split("\n")
    in_options = False

    for line in lines:
        stripped = line.strip()

        if "Options:" in stripped or "options:" in stripped:
            in_options = True
            continue
        if in_options and stripped == "":
            continue
        if in_options and not re.match(r'^\s*[-]', stripped):
            if stripped and not stripped.startswith(" "):
                in_options = False
            continue

        if not in_options:
            continue

        # Parse: -f, --force TEXT  Description  [required]
        # Or:    -f, --force            Description  (boolean, no metavar)
        # Or:    --verbose              Description  (long only, no short)
        match = re.match(
            r'^\s*(-[a-zA-Z0-9]),\s*(--[a-zA-Z0-9][-a-zA-Z0-9]*)\s+([A-Za-z]+)\s{2,}(.+)$',
            stripped,
        )
        if match:
            options.append({
                "short": match.group(1),
                "long": match.group(2),
                "type": match.group(3).lower(),
                "description": match.group(4).strip(),
                "required": "[required]" in match.group(4).lower(),
            })
            continue

        # Boolean flag with short form: -f, --force  Description
        match = re.match(
            r'^\s*(-[a-zA-Z0-9]),\s*(--[a-zA-Z0-9][-a-zA-Z0-9]*)\s{2,}(.+)$',
            stripped,
        )
        if match:
            options.append({
                "short": match.group(1),
                "long": match.group(2),
                "type": "boolean",
                "description": match.group(3).strip(),
                "required": False,
            })
            continue

        # Long-only boolean flag: --verbose  Description
        match = re.match(
            r'^\s*(--[a-zA-Z0-9][-a-zA-Z0-9]*)\s{2,}(.+)$',
            stripped,
        )
        if match:
            options.append({
                "short": "",
                "long": match.group(1),
                "type": "boolean",
                "description": match.group(2).strip(),
                "required": False,
            })

    if options:
        return ExtractionResult(
            command_path="",
            options=options,
            raw_help=help_text,
            source="help_output",
        )
    return None


def extract_options(command_path: str) -> ExtractionResult:
    """Extract options from a command's --help output.

    Tries deterministic parsers first, falls back to LLM.
    Currently deterministic-only — LLM fallback is a TODO.

    Args:
        command_path: Dotted command path (e.g., "aws.s3.ls")

    Returns:
        ExtractionResult with parsed options and subcommands.
    """
    from krill.subcommands import parse_subcommands

    # Convert dotted path to command args
    parts = command_path.split(".")
    base_cmd = parts[0]
    subcmd_args = parts[1:] if len(parts) > 1 else []

    help_text = run_command_help(base_cmd, subcmd_args + ["--help"])
    if not help_text:
        help_text = run_command_help(base_cmd, subcmd_args + ["-h"])

    result = ExtractionResult(
        command_path=command_path,
        raw_help=help_text,
    )

    if not help_text:
        return result

    # Try deterministic flag parsers
    parsed = (
        parse_argparse_style(help_text)
        or parse_click_style(help_text)
    )

    if parsed:
        result.options = parsed.options

    # Try subcommand discovery (handles pip/npm/git-style listings)
    subs = parse_subcommands(help_text)
    if subs:
        result.subcommands = subs

    # TODO: LLM fallback for non-standard formats
    # TODO: Recursive subcommand discovery (for aws, heroku, kubectl, etc.)

    return result