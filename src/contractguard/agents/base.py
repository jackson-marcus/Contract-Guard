"""Redline proposals, and the contract every source of replacement language obeys.

Flagging a clause is only half a contract review. The reviewer's next move is to
propose the words that go in its place — and that proposal has to survive the
same scrutiny as the clause it replaces. A "safe" termination clause lifted from
another executed agreement is worthless if it happens to be the unilateral one.

So a :class:`RedlineSource` never returns its first candidate blindly. It offers
candidates in preference order and :meth:`propose` vets each one through the
pattern library, keeping the first that comes back clean and recording every
rejection so the pass can report what it threw away and why.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field

from contractguard.clauses.segment import Clause, segment
from contractguard.risk.rules import RiskFinding, scan_patterns

# Edit kinds. A finding is either "this clause says the wrong thing" (replace)
# or "this contract is silent where it should not be" (insert).
REPLACE = "replace"
INSERT = "insert"


@dataclass(frozen=True)
class Candidate:
    """One piece of proposed replacement language, before vetting."""

    text: str
    citation: str


@dataclass(frozen=True)
class Rejection:
    """A candidate the self-check refused.

    `tripped` is the rule the *proposal* fired, not the finding it was answering
    — the interesting case is proposing an uncapped-liability clause to fix a
    missing liability cap.
    """

    citation: str
    tripped: str

    def as_dict(self) -> dict:
        return dict(vars(self))


@dataclass(frozen=True)
class Redline:
    """A vetted edit: what to take out, what to put in, and on whose authority."""

    rule: str
    edit: str
    clause_index: int
    clause_heading: str
    original: str
    replacement: str
    citation: str
    rationale: str
    rejected: tuple[Rejection, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        d = dict(vars(self))
        d["rejected"] = [r.as_dict() for r in self.rejected]
        return d

    def apply_to(self, document: str) -> str:
        """Return `document` with this edit made, or unchanged if it does not fit.

        Replacement is a single literal substitution of the clause block, which is
        exactly the substring `segment()` carved out, so it always matches unless
        an earlier edit already rewrote it. Insertion appends at the end of the
        document, where a missing clause conventionally gets added.
        """
        if self.edit == INSERT:
            return document.rstrip() + "\n\n" + self.replacement.strip() + "\n"
        if self.original and self.original in document:
            return document.replace(self.original, self.replacement, 1)
        return document


class RedlineSource(ABC):
    """Something that can supply replacement language for a finding."""

    name: str
    #: Set False to skip the self-check. Only scripts/redline_bench.py does this,
    #: to measure what the check is actually buying.
    vet: bool = True

    @abstractmethod
    def candidates(self, finding: RiskFinding, clause: Clause | None) -> Iterable[Candidate]:
        """Yield replacement language in preference order. May be empty."""

    def rationale(self, finding: RiskFinding, candidate: Candidate) -> str:
        return finding.explanation

    def propose(self, finding: RiskFinding, clause: Clause | None) -> Redline | None:
        """First candidate that does not itself trip the pattern library."""
        return self.propose_detailed(finding, clause)[0]

    def propose_detailed(
        self, finding: RiskFinding, clause: Clause | None
    ) -> tuple[Redline | None, list[Rejection]]:
        """As :meth:`propose`, but also hands back the candidates that were refused.

        The planner needs the rejections even when nothing survives, so that a
        finding blocked by an all-risky candidate pool is distinguishable from
        one nobody had any language for at all.
        """
        rejected: list[Rejection] = []
        for candidate in self.candidates(finding, clause):
            tripped = self_check(candidate.text) if self.vet else ""
            if tripped:
                rejected.append(Rejection(citation=candidate.citation, tripped=tripped))
                continue
            edit = INSERT if clause is None else REPLACE
            return Redline(
                rule=finding.rule,
                edit=edit,
                clause_index=-1 if clause is None else clause.index,
                clause_heading="(inserted)" if clause is None else clause.heading,
                original="" if clause is None else clause.text,
                replacement=candidate.text.strip(),
                citation=candidate.citation,
                rationale=self.rationale(finding, candidate),
                rejected=tuple(rejected),
            ), rejected
        return None, rejected


def self_check(text: str) -> str:
    """Return the id of the first risk rule the proposed language trips, else "".

    Runs the same pattern library used on the counterparty's draft. Anything we
    would flag if they wrote it, we refuse to write ourselves.
    """
    clauses = segment(text)
    if not clauses:
        return ""
    findings = scan_patterns(clauses)
    return findings[0].rule if findings else ""
