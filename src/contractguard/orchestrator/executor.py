"""Run the redline pass: plan the edits, apply them one at a time, re-scan each time.

Applying every edit and scanning once at the end would tell you the net change
and nothing else. This applies them singly and re-scans between each, which is
what makes the ledger able to attribute a newly-introduced finding to the edit
that caused it.
"""

from __future__ import annotations

from contractguard.agents.base import RedlineSource
from contractguard.agents.contractguard_agents import build_sources
from contractguard.clauses.segment import segment
from contractguard.orchestrator.memory import RedlineLedger
from contractguard.orchestrator.planner import Planner, PlanStep
from contractguard.risk.rules import RiskFinding, scan


class RedlinePass:
    """Segment → scan → plan → apply edit-by-edit → re-scan → ledger."""

    def __init__(self, sources: list[RedlineSource] | None = None):
        self.sources = sources if sources is not None else build_sources()

    def plan(self, text: str) -> tuple[list[PlanStep], list[RiskFinding]]:
        clauses = segment(text)
        findings = scan(clauses)
        return Planner(self.sources).plan(findings, clauses), findings

    def run(self, text: str) -> dict:
        steps, findings = self.plan(text)
        ledger = RedlineLedger()
        document = text
        current = [f.rule for f in findings]

        for step in steps:
            if step.redline is None:
                continue
            edited = step.redline.apply_to(document)
            applied = edited != document
            document = edited
            after = [f.rule for f in scan(segment(document))] if applied else current
            ledger.record(
                order=step.order,
                rule=step.rule,
                edit=step.redline.edit,
                citation=step.redline.citation,
                applied=applied,
                before=current,
                after=after,
            )
            current = after

        blocked = [s for s in steps if s.redline is None]
        return {
            "n_findings_before": len(findings),
            "n_findings_after": len(current),
            "findings_before": sorted({f.rule for f in findings}),
            "findings_after": sorted(set(current)),
            "steps": [s.as_dict() for s in steps],
            "needs_review": [
                {
                    "rule": s.rule,
                    "severity": s.severity,
                    "clause_heading": s.clause_heading,
                    "reason": s.blocked_reason,
                }
                for s in blocked
            ],
            "ledger": ledger.as_dict(),
            "redlined_text": document,
            "n_candidates_rejected": sum(
                len(s.redline.rejected) for s in steps if s.redline is not None
            ),
        }
