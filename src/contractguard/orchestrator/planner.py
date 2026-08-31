"""Turn a pile of findings into an ordered edit plan a reviewer can walk down.

Two jobs. First, ordering: a reviewer negotiates the expensive terms while they
still have goodwill, so high-severity findings go to the top and the low-severity
wording quibbles go last. Second, and more important, honesty about coverage —
every finding that no source can answer stays in the plan with the reason it
could not be answered, instead of quietly vanishing from the output.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from contractguard.agents.base import Redline, RedlineSource, Rejection
from contractguard.clauses.segment import Clause
from contractguard.risk.rules import RiskFinding

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

NO_SOURCE = "no source offered replacement language for this rule"
ALL_REJECTED = "every candidate was itself flagged by the pattern library"


@dataclass(frozen=True)
class PlanStep:
    order: int
    rule: str
    severity: str
    clause_index: int
    clause_heading: str
    redline: Redline | None
    blocked_reason: str

    @property
    def actionable(self) -> bool:
        return self.redline is not None

    def as_dict(self) -> dict:
        return {
            "order": self.order,
            "rule": self.rule,
            "severity": self.severity,
            "clause_index": self.clause_index,
            "clause_heading": self.clause_heading,
            "redline": self.redline.as_dict() if self.redline else None,
            "blocked_reason": self.blocked_reason,
        }


class Planner:
    """Builds the ordered plan by asking each source in preference order."""

    def __init__(self, sources: list[RedlineSource]):
        self.sources = sources

    def plan(self, findings: list[RiskFinding], clauses: list[Clause]) -> list[PlanStep]:
        by_index = {c.index: c for c in clauses}
        seen: set[tuple[str, int]] = set()
        ordered = sorted(
            findings,
            key=lambda f: (SEVERITY_ORDER.get(f.severity, 3), f.clause_index < 0, f.clause_index),
        )
        steps: list[PlanStep] = []
        for finding in ordered:
            key = (finding.rule, finding.clause_index)
            if key in seen:
                continue
            seen.add(key)
            # clause_index -1 marks a missing-clause finding: nothing to replace,
            # the edit is an insertion.
            clause = by_index.get(finding.clause_index) if finding.clause_index >= 0 else None
            redline, reason = self._propose(finding, clause)
            steps.append(
                PlanStep(
                    order=len(steps) + 1,
                    rule=finding.rule,
                    severity=finding.severity,
                    clause_index=finding.clause_index,
                    clause_heading=finding.clause_heading,
                    redline=redline,
                    blocked_reason=reason,
                )
            )
        return steps

    def _propose(self, finding: RiskFinding, clause: Clause | None) -> tuple[Redline | None, str]:
        refused: list[Rejection] = []
        for source in self.sources:
            redline, rejected = source.propose_detailed(finding, clause)
            refused.extend(rejected)
            if redline is not None:
                # Carry forward everything earlier sources threw away, so the
                # citation the reviewer sees comes with the ones we passed over.
                return replace(redline, rejected=tuple(refused)), ""
        return None, (ALL_REJECTED if refused else NO_SOURCE)
