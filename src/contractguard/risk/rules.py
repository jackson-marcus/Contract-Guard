"""Risk rules: pattern library over segmented clauses + missing-clause checks.

Each finding carries severity, the triggering clause, and a plain-English
explanation a reviewer can act on."""

from __future__ import annotations

import re
from dataclasses import dataclass

from contractguard.clauses.segment import Clause
from contractguard.settings import get_config

PATTERNS: list[tuple[str, str, str, str]] = [
    # (rule_id, severity, regex, explanation)
    (
        "unlimited_liability",
        "high",
        r"(unlimited liability|liability .{0,40}shall not be (capped|limited)|no (cap|limit) on liability)",
        "Liability appears uncapped — negotiate a cap tied to fees paid.",
    ),
    (
        "unilateral_termination",
        "high",
        r"(terminate .{0,50}(at any time|for any reason|without cause).{0,60}(sole|its) discretion|sole discretion.{0,40}terminate)",
        "One-sided termination right — seek mutuality or a cure period.",
    ),
    (
        "auto_renewal_trap",
        "medium",
        r"(automatically renew|auto-?renews?).{0,80}(unless .{0,40}(\d{1,3})\s*days|without notice)",
        "Auto-renewal with a narrow opt-out window — calendar the notice deadline.",
    ),
    (
        "broad_indemnity",
        "high",
        r"indemnify.{0,80}(any and all|regardless of (cause|fault)|including .{0,30}negligence)",
        "Indemnity covers the other side's own negligence — narrow to third-party claims.",
    ),
    (
        "ip_assignment",
        "medium",
        r"(assigns? all right, title|work made for hire|all intellectual property .{0,40}(vendor|client))",
        "Blanket IP assignment — confirm scope matches the engagement.",
    ),
    (
        "non_compete_broad",
        "medium",
        r"non-?compete.{0,120}(\d+)\s*(year|month)",
        "Non-compete with a fixed period — check enforceability and scope.",
    ),
    (
        "payment_late_penalty",
        "low",
        r"(late (fee|charge)|interest .{0,30}(\d+(\.\d+)?)\s*%\s*(per month|monthly))",
        "Late-payment interest specified — verify the rate is lawful and mutual.",
    ),
    (
        "no_liability_carveout",
        "low",
        r"limitation of liability(?![\s\S]{0,400}(gross negligence|willful misconduct))",
        "Liability cap without the customary carve-outs for gross negligence.",
    ),
]

# DOTALL: clause text is multi-line; patterns must cross line breaks.
_COMPILED = [
    (rid, sev, re.compile(rx, re.IGNORECASE | re.DOTALL), why) for rid, sev, rx, why in PATTERNS
]


@dataclass
class RiskFinding:
    rule: str
    severity: str
    clause_index: int
    clause_heading: str
    excerpt: str
    explanation: str

    def as_dict(self) -> dict:
        return vars(self)


def scan(clauses: list[Clause]) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    for clause in clauses:
        for rule_id, severity, pattern, why in _COMPILED:
            m = pattern.search(clause.text)
            if m:
                start = max(m.start() - 40, 0)
                findings.append(
                    RiskFinding(
                        rule=rule_id,
                        severity=severity,
                        clause_index=clause.index,
                        clause_heading=clause.heading,
                        excerpt=" ".join(clause.text[start : m.end() + 40].split()),
                        explanation=why,
                    )
                )

    present = {c.clause_type for c in clauses}
    for required in get_config()["risk"]["flag_missing_clauses"]:
        if required not in present:
            findings.append(
                RiskFinding(
                    rule=f"missing_{required}",
                    severity="medium",
                    clause_index=-1,
                    clause_heading="(absent)",
                    excerpt="",
                    explanation=f"No {required.replace('_', ' ')} clause found — confirm intentional.",
                )
            )
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order[f.severity])
    return findings
