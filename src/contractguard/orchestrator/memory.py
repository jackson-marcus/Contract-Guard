"""The ledger: what each redline actually did to the document, edit by edit.

Redlines are not independent. Swapping one clause changes the text the scanner
sees and the set of clause types the document contains, so an edit can resolve
the finding it targeted while creating another one somewhere else — the classic
example being a liability cap dropped in without carve-outs, which trades
`unlimited_liability` for `no_liability_carveout`.

A single before/after finding count hides that completely. The ledger re-scans
after every edit and records the delta as two multisets, so an edit that removes
one finding and introduces another shows up as a regression rather than as
"net zero, nothing happened".
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LedgerEntry:
    """One applied edit and its measured effect on the whole document."""

    order: int
    rule: str
    edit: str
    citation: str
    applied: bool
    resolved: bool
    removed: tuple[str, ...]
    introduced: tuple[str, ...]
    n_before: int
    n_after: int

    @property
    def regressed(self) -> bool:
        return bool(self.introduced)

    def as_dict(self) -> dict:
        d = dict(vars(self))
        d["regressed"] = self.regressed
        return d


@dataclass
class RedlineLedger:
    entries: list[LedgerEntry] = field(default_factory=list)

    def record(
        self,
        *,
        order: int,
        rule: str,
        edit: str,
        citation: str,
        applied: bool,
        before: list[str],
        after: list[str],
    ) -> LedgerEntry:
        """Diff the finding multisets around one edit and file the result."""
        before_counts, after_counts = Counter(before), Counter(after)
        removed = tuple(sorted(r for r in before_counts if after_counts[r] < before_counts[r]))
        introduced = tuple(
            sorted(r for r in after_counts if after_counts[r] > before_counts.get(r, 0))
        )
        entry = LedgerEntry(
            order=order,
            rule=rule,
            edit=edit,
            citation=citation,
            applied=applied,
            resolved=after_counts[rule] < before_counts[rule],
            removed=removed,
            introduced=introduced,
            n_before=len(before),
            n_after=len(after),
        )
        self.entries.append(entry)
        return entry

    @property
    def regressions(self) -> list[LedgerEntry]:
        """Edits that created a finding that was not there before."""
        return [e for e in self.entries if e.regressed]

    @property
    def unresolved(self) -> list[LedgerEntry]:
        """Edits that were applied but left their own target finding standing."""
        return [e for e in self.entries if e.applied and not e.resolved]

    def summary(self) -> dict:
        first = self.entries[0].n_before if self.entries else 0
        last = self.entries[-1].n_after if self.entries else 0
        return {
            "n_edits": sum(1 for e in self.entries if e.applied),
            "findings_before": first,
            "findings_after": last,
            "n_regressions": len(self.regressions),
            "n_unresolved": len(self.unresolved),
            "introduced_rules": sorted({r for e in self.entries for r in e.introduced}),
        }

    def as_dict(self) -> dict:
        return {"summary": self.summary(), "entries": [e.as_dict() for e in self.entries]}
