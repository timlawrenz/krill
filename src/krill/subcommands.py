"""Subcommand discovery from --help output.

Handles common subcommand listing patterns:
- pip: "Commands:\n  install  Install packages."
- npm:  "where <command> is one of: access, adduser, ..."
- git:  "These are common Git subcommands: add, branch, ..."
- docker: "Management Commands:\n  container  Manage containers"
"""

from __future__ import annotations

import re


def parse_subcommands(help_text: str) -> list[dict[str, str]]:
    """Extract subcommands from help text.

    Returns list of {name, description} dicts.
    """
    subcommands: list[dict[str, str]] = []

    # Pattern 1: pip-style "Commands:\n  name  Description"
    # Matches lines like: "  install                     Install packages."
    subs = _parse_indented_list(help_text, "Commands:")
    if subs:
        subcommands.extend(subs)

    # Pattern 2: npm-style "All commands:" followed by comma lists
    subs = _parse_comma_block(help_text, "All commands:")
    if subs:
        subcommands.extend(subs)

    # Pattern 3: npm-style "where <command> is one of: cmd1, cmd2, ..."
    subs = _parse_comma_list(help_text)
    if subs:
        subcommands.extend(subs)

    # Pattern 3: git-style "These are common subcommands:" or "Available subcommands:"
    for header in ["subcommands:", "Available commands:", "Management Commands:"]:
        subs = _parse_indented_list(help_text, header)
        if subs:
            subcommands.extend(subs)

    # Deduplicate by name
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for s in subcommands:
        if s["name"] not in seen:
            seen.add(s["name"])
            unique.append(s)

    return unique


def _parse_indented_list(text: str, header: str) -> list[dict[str, str]]:
    """Parse subcommands from a section like:

    Commands:
      install                     Install packages.
      download                    Download packages.

    Returns list of {name, description} dicts.
    """
    subcommands: list[dict[str, str]] = []
    lines = text.split("\n")
    in_section = False

    for line in lines:
        stripped_lower = line.strip().lower()

        # Detect section header
        if header.lower() in stripped_lower and (
            stripped_lower.startswith(header.lower())
            or ":" in stripped_lower
        ):
            in_section = True
            continue

        if not in_section:
            continue

        # Exit section on blank line or non-indented text
        if not line.strip():
            if subcommands:
                break  # blank line after subcommands — done
            continue
        if not line.startswith("  ") and not line.startswith("\t"):
            if subcommands:
                break  # non-indented line — done
            continue

        # Parse: "  name    Description"
        stripped = line.strip()
        # Match: name (possibly with commas for npm-style inline lists)
        match = re.match(r'^([a-zA-Z][-a-zA-Z0-9_]*)\s{2,}(.+)$', stripped)
        if match:
            subcommands.append({
                "name": match.group(1),
                "description": match.group(2).strip(),
            })
            continue

        # Match: just a name with no description
        match = re.match(r'^([a-zA-Z][-a-zA-Z0-9_]*)$', stripped)
        if match:
            subcommands.append({
                "name": match.group(1),
                "description": "",
            })

    return subcommands


def _parse_comma_list(text: str) -> list[dict[str, str]]:
    """Parse npm-style: "where <command> is one of: cmd1, cmd2, cmd3, ..."

    Also handles: "available commands: cmd1, cmd2"
    """
    subcommands: list[dict[str, str]] = []

    # Match: "is one of:" or "are:" followed by comma-separated names
    match = re.search(
        r'(?:is one of|are)\s*:\s*\n?\s*([a-zA-Z][-a-zA-Z0-9_, \n]+?)(?:\.|\n\n|\Z)',
        text,
        re.IGNORECASE,
    )
    if match:
        names_block = match.group(1)
        # Split on commas and whitespace
        names = re.split(r'[,\s]+', names_block.strip())
        for name in names:
            name = name.strip()
            if name and re.match(r'^[a-zA-Z][-a-zA-Z0-9_]*$', name):
                subcommands.append({"name": name, "description": ""})

    return subcommands


def _parse_comma_block(text: str, header: str) -> list[dict[str, str]]:
    """Parse npm-style comma-separated subcommand block after a header.

    Example:
        All commands:

            access, adduser, audit, bugs, cache,
            config, dedupe, ...

    Returns list of {name, description} dicts.
    """
    subcommands: list[dict[str, str]] = []
    lines = text.split("\n")
    in_section = False
    comma_lines: list[str] = []

    for line in lines:
        stripped_lower = line.strip().lower()

        if header.lower() in stripped_lower and ":" in stripped_lower:
            in_section = True
            continue

        if not in_section:
            continue

        # Collect comma-separated lines
        stripped = line.strip()
        if "," in stripped:
            comma_lines.append(stripped)
        elif not stripped and comma_lines:
            break  # blank line after comma block
        elif stripped and not stripped.startswith(",") and comma_lines:
            break  # non-comma, non-blank line — done

    # Parse all collected comma lines
    all_names = " ".join(comma_lines)
    for name in re.split(r'[,\s]+', all_names):
        name = name.strip().rstrip(".")
        if name and re.match(r'^[a-zA-Z][-a-zA-Z0-9_]*$', name):
            subcommands.append({"name": name, "description": ""})

    return subcommands
