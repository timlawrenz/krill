# Krill

**What fish eat. Tiny, fast, powers the shell.**

Krill is the completion engine fish shell deserves — a pipeline that generates machine-readable command catalogs from man pages, `--help` output, and user feedback, then outputs fish completion files that the shell loads natively.

## Why

Fish shell already parses man pages for completions via `create_manpage_completions.py`. It covers ~70% of what explainshell does. But it has two gaps:

1. **No coverage for commands without man pages** — `pip`, `npm`, `cargo`, `heroku`, `aws`, `kubectl`, and every modern CLI tool that ships `--help` instead of a man page.
2. **No personalization** — everyone gets the same completions, regardless of how they actually use the tools.

Krill fills both gaps by replacing fish's man page parser with a catalog pipeline that:

- Queries explainshell's man page database for core GNU/Linux utilities
- Runs a sandbox agent to execute `unknown-command --help` and extract option schemas for everything else
- Validates completions against ground truth (paths exist, flags match schema, subcommands are known)
- Collects feedback `[prefix, suggestions, chosen, actual_command, exit_code]` for personalization

Zero shell modifications. Krill outputs standard fish completion files to `~/.cache/fish/generated_completions/` — fish loads them as if nothing changed.

## Architecture

```
fish shell (completion engine, ghost text, pager) — untouched
         │
         ▼
~/.cache/fish/generated_completions/   ← krill outputs here
         │
         ├── explainshell man page DB   ← coreutils, POSIX, GNU
         ├── sandbox agent catalog      ← pip, npm, aws, heroku...
         └── personalization weights    ← user feedback → ranking
```

## Status

Experimental. Not yet functional.

## Prior art

- [explainshell](https://github.com/idank/explainshell) — man page parsing and option extraction (the gold standard)
- [fish-shell](https://github.com/fish-shell/fish-shell) — `create_manpage_completions.py` (the hook point)
- [NL2SH-ALFA](https://huggingface.co/datasets/westenfelder/NL2SH-ALFA) — 40K natural language → bash command pairs
- [thefuck](https://github.com/nvbn/thefuck) — error → correction rule patterns