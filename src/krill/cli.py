"""CLI entry point for krill.

Usage:
    krill update              Refresh completions from catalog
    krill extract <command>   Extract options via sandbox agent
    krill catalog             Show catalog statistics
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from krill.catalog import Catalog
from krill.generator import write_completion_files
from krill.sandbox import extract_options


def cmd_update(args: argparse.Namespace) -> int:
    """Refresh all completion files from the catalog."""
    output_dir = Path(args.output_dir)
    catalog = Catalog(explainshell_db=args.explainshell_db)

    written = write_completion_files(
        catalog, output_dir,
        overwrite=args.force,
        commands=args.commands if args.commands else None,
    )

    if written:
        print(f"Generated {len(written)} completion files in {output_dir}")
        for f in written:
            print(f"  {f.name}")
    else:
        msg = "No new completions generated"
        if not args.force:
            msg += " (all files already exist, use --force to overwrite)"
        print(msg, file=sys.stderr)

    catalog.close()
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    """Extract options from a command's --help output."""
    command = args.command
    catalog = Catalog()

    print(f"Extracting options for '{command}'...")

    result = extract_options(command)

    if result.options:
        catalog.upsert(
            command_path=command,
            source=result.source,
            options=result.options,
            subcommands=result.subcommands,
            synopsis=result.synopsis,
        )
        print(f"Extracted {len(result.options)} options for '{command}'")
        for opt in result.options:
            flag = opt.get("long") or opt.get("short") or "(unnamed)"
            print(f"  {flag}: {opt.get('description', '')}")
    else:
        print(f"No options extracted from '{command} --help'", file=sys.stderr)
        if result.raw_help:
            print(f"\nRaw help output:\n{result.raw_help[:500]}...", file=sys.stderr)

    catalog.close()
    return 0 if result.options else 1


def cmd_catalog(args: argparse.Namespace) -> int:
    """Show catalog statistics."""
    catalog = Catalog()

    rows = catalog.conn.execute(
        "SELECT command_path, source, extracted_at FROM help_catalog ORDER BY command_path"
    ).fetchall()

    if not rows:
        print("Catalog is empty. Run 'krill extract <command>' to populate.")
        catalog.close()
        return 0

    print(f"Catalog: {len(rows)} commands\n")
    for row in rows:
        print(f"  {row['command_path']:<30} [{row['source']}]")

    catalog.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="krill",
        description="Fish shell completion engine",
    )
    sub = parser.add_subparsers(dest="command")

    # krill update
    update = sub.add_parser("update", help="Refresh all completion files")
    update.add_argument(
        "-o", "--output-dir",
        default=str(Path.home() / ".config" / "fish" / "completions"),
        help="Output directory for .fish files (default: ~/.config/fish/completions/)",
    )
    update.add_argument(
        "--explainshell-db",
        default=None,
        help="Path to explainshell SQLite DB (optional)",
    )
    update.add_argument(
        "-f", "--force",
        action="store_true",
        help="Overwrite existing completion files",
    )
    update.add_argument(
        "commands", nargs="*",
        help="Specific commands to generate (default: all)",
    )
    update.set_defaults(func=cmd_update)

    # krill extract
    extract = sub.add_parser("extract", help="Extract options from --help output")
    extract.add_argument("command", help="Command name (e.g., 'heroku' or 'aws.s3.ls')")
    extract.set_defaults(func=cmd_extract)

    # krill catalog
    catalog = sub.add_parser("catalog", help="Show catalog statistics")
    catalog.set_defaults(func=cmd_catalog)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()