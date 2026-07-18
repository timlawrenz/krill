"""Feedback loop data collection.

Captures [prefix, suggestions, chosen, actual_command, exit_code]
tuples for downstream personalization (DPO fine-tuning / reranker training).

Data is stored as JSONL in $XDG_DATA_HOME/krill/feedback.jsonl.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class FeedbackRecord:
    """A single completion interaction."""
    prefix: str                        # what user typed before accepting
    suggestions: list[str]             # ranked suggestions shown
    chosen_index: int | None           # which suggestion was accepted (None = ignored all)
    actual_command: str               # the full command that actually ran
    exit_code: int | None = None      # 0 = success, non-zero = failure
    cwd: str = ""                     # working directory at time of completion
    git_branch: str | None = None     # contextual signal
    history_window: list[str] = field(default_factory=list)  # last N commands
    timestamp: float = field(default_factory=time.time)

    @property
    def chosen(self) -> str | None:
        """The suggestion the user picked, if any."""
        if self.chosen_index is not None and 0 <= self.chosen_index < len(self.suggestions):
            return self.suggestions[self.chosen_index]
        return None

    @property
    def rejected(self) -> list[str]:
        """Suggestions the user did NOT pick."""
        if self.chosen_index is not None:
            return [s for i, s in enumerate(self.suggestions) if i != self.chosen_index]
        return list(self.suggestions)


class FeedbackStore:
    """Append-only JSONL store for completion feedback."""

    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            data_dir = Path.home() / ".local" / "share" / "krill"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.data_dir / "feedback.jsonl"

    def record(self, record: FeedbackRecord) -> None:
        """Append a feedback record."""
        with open(self._path, "a") as f:
            f.write(json.dumps(asdict(record)) + "\n")

    def iter_records(self) -> list[FeedbackRecord]:
        """Read all records (for training)."""
        if not self._path.exists():
            return []
        records = []
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    records.append(FeedbackRecord(**data))
        return records

    def dpo_pairs(self) -> list[dict]:
        """Extract DPO training pairs: {chosen: str, rejected: str}.

        Only returns records where the user made a clear choice
        (accepted one suggestion, rejected others).
        """
        pairs = []
        for rec in self.iter_records():
            if rec.chosen and rec.rejected:
                for rejected in rec.rejected:
                    pairs.append({
                        "prompt": rec.prefix,
                        "chosen": rec.chosen,
                        "rejected": rejected,
                    })
        return pairs