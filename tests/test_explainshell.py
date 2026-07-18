"""Integration tests for krill + explainshell DB.

Requires explainshell.db in the project root (downloaded separately).
Tests are skipped if the DB is absent.
"""

import pytest

from krill.catalog import Catalog

# Path to explainshell DB (optional — tests skip if missing)
EXPLAINSHELL_DB = str(
    __import__("pathlib").Path(__file__).resolve().parent.parent / "explainshell.db"
)


@pytest.fixture
def catalog():
    """Return a Catalog with explainshell fallback, or skip if DB missing."""
    from pathlib import Path
    if not Path(EXPLAINSHELL_DB).exists():
        pytest.skip("explainshell.db not found — download from https://github.com/idank/explainshell/releases/tag/db-latest")
    cat = Catalog(explainshell_db=EXPLAINSHELL_DB)
    yield cat
    cat.close()


class TestExplainshellIntegration:
    def test_tar_options(self, catalog):
        opts = catalog.get_options("tar")
        assert opts is not None
        assert len(opts) > 50  # tar has many options
        # Check standard options exist
        long_names = {o["long"] for o in opts}
        assert "--create" in long_names
        assert "--extract" in long_names
        assert "--file" in long_names

    def test_git_subcommands(self, catalog):
        subs = catalog.get_subcommands("git")
        assert len(subs) > 50
        names = {s["name"] for s in subs}
        assert "add" in names
        assert "commit" in names
        assert "push" in names

    def test_find_options(self, catalog):
        opts = catalog.get_options("find")
        assert opts is not None
        # GNU find uses single-dash options (-name, -type), not --long forms
        short_names = {o["short"] for o in opts}
        assert "-name" in short_names
        assert "-type" in short_names

    def test_unknown_command(self, catalog):
        assert catalog.get_options("nonexistent-cmd-xyz") is None
        assert catalog.get_subcommands("nonexistent-cmd-xyz") == []

    def test_list_all_commands(self, catalog):
        cmds = catalog.list_all_commands()
        assert len(cmds) > 50000
        assert "tar" in cmds
        assert "git" in cmds
        assert "grep" in cmds