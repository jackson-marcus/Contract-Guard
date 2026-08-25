"""AST Visitor Architecture — Clause Abstract Syntax Tree + Visitors.

Contracts are parsed into a typed abstract syntax tree of clause nodes.
Multiple independent Visitors traverse the tree to extract different signals:

  - RiskDetectionVisitor  → flags clauses with high-risk language patterns
  - ObligationVisitor     → extracts structured obligation records
  - ComplianceVisitor     → checks GDPR/CCPA/SOX clause presence

The Visitor pattern separates tree structure from analysis logic.
Adding a new analysis (e.g., a penalty clause extractor) requires only a
new Visitor subclass — the AST nodes never change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# AST Node Hierarchy
# ---------------------------------------------------------------------------


@dataclass
class ClauseNode:
    """A parsed contract clause with its type and child structure."""

    index: int
    heading: str
    text: str
    clause_type: str
    obligations: list[dict[str, Any]] = field(default_factory=list)
    children: list[ClauseNode] = field(default_factory=list)

    def accept(self, visitor: ClauseVisitor) -> Any:
        """Double-dispatch entry point — calls the correct visitor method."""
        return visitor.visit(self)


@dataclass
class ContractAST:
    """Root of the contract abstract syntax tree."""

    title: str
    clauses: list[ClauseNode] = field(default_factory=list)

    def accept(self, visitor: ClauseVisitor) -> list[Any]:
        """Walk all clauses and collect visitor results."""
        results = []
        for clause in self.clauses:
            result = clause.accept(visitor)
            if result is not None:
                results.append(result)
        return results


# ---------------------------------------------------------------------------
# Visitor ABC
# ---------------------------------------------------------------------------


class ClauseVisitor(ABC):
    """Abstract visitor over a ContractAST."""

    @abstractmethod
    def visit(self, node: ClauseNode) -> Any:
        """Visit a single clause node and return an analysis result."""


# ---------------------------------------------------------------------------
# Visitor: RiskDetectionVisitor
# ---------------------------------------------------------------------------

_RISK_PATTERNS: dict[str, list[str]] = {
    "uncapped_liability": ["unlimited liability", "without limitation", "no cap on liability"],
    "unilateral_termination": [
        "terminate at any time",
        "terminate without cause",
        "terminate for any reason",
        "terminate immediately",
    ],
    "auto_renewal_trap": [
        "automatically renew",
        "auto-renew",
        "renewal unless cancelled",
        "automatically extends",
    ],
    "broad_ip_assignment": [
        "all intellectual property",
        "all ip rights",
        "assigns all rights",
        "work for hire",
    ],
    "penalty_clause": [
        "liquidated damages",
        "penalty",
        "forfeit",
        "damages not less than",
    ],
    "non_compete_broad": [
        "non-compete",
        "not compete",
        "competitive activities",
        "competitive business",
    ],
}


@dataclass
class RiskFlag:
    clause_index: int
    clause_heading: str
    risk_category: str
    matched_phrase: str
    severity: str  # "high" | "medium" | "low"


class RiskDetectionVisitor(ClauseVisitor):
    """Traverses clause nodes and flags high-risk language patterns."""

    _SEVERITY: dict[str, str] = {
        "uncapped_liability": "high",
        "unilateral_termination": "high",
        "auto_renewal_trap": "medium",
        "broad_ip_assignment": "high",
        "penalty_clause": "medium",
        "non_compete_broad": "medium",
    }

    def visit(self, node: ClauseNode) -> list[RiskFlag]:
        flags: list[RiskFlag] = []
        text_lower = node.text.lower()
        for category, phrases in _RISK_PATTERNS.items():
            for phrase in phrases:
                if phrase in text_lower:
                    flags.append(
                        RiskFlag(
                            clause_index=node.index,
                            clause_heading=node.heading,
                            risk_category=category,
                            matched_phrase=phrase,
                            severity=self._SEVERITY.get(category, "low"),
                        )
                    )
                    break  # one flag per category per clause
        return flags


# ---------------------------------------------------------------------------
# Visitor: ObligationVisitor
# ---------------------------------------------------------------------------


@dataclass
class ObligationRecord:
    clause_index: int
    clause_type: str
    party: str
    action: str
    deadline_days: int | None


class ObligationVisitor(ClauseVisitor):
    """Collects structured obligations from each clause's pre-extracted list."""

    def visit(self, node: ClauseNode) -> list[ObligationRecord]:
        records = []
        for obl in node.obligations:
            records.append(
                ObligationRecord(
                    clause_index=node.index,
                    clause_type=node.clause_type,
                    party=obl.get("party", "Unknown"),
                    action=obl.get("action", ""),
                    deadline_days=obl.get("deadline_days"),
                )
            )
        return records


# ---------------------------------------------------------------------------
# Visitor: ComplianceVisitor
# ---------------------------------------------------------------------------

_COMPLIANCE_CHECKS: dict[str, list[str]] = {
    "GDPR_data_processing": [
        "data processing agreement",
        "lawful basis",
        "data subject rights",
        "right to erasure",
    ],
    "CCPA_consumer_rights": [
        "right to know",
        "right to delete",
        "opt-out",
        "do not sell",
    ],
    "SOX_audit_trail": [
        "audit trail",
        "record retention",
        "financial records",
        "internal controls",
    ],
    "data_breach_notification": [
        "breach notification",
        "notify within",
        "security incident",
        "data breach",
    ],
}


@dataclass
class ComplianceResult:
    clause_index: int
    clause_heading: str
    requirement: str
    satisfied: bool
    evidence: str


class ComplianceVisitor(ClauseVisitor):
    """Checks each clause for regulatory compliance indicators."""

    def __init__(self, requirements: list[str] | None = None) -> None:
        # Default: check all known requirements
        self._requirements = requirements or list(_COMPLIANCE_CHECKS.keys())

    def visit(self, node: ClauseNode) -> list[ComplianceResult]:
        results = []
        text_lower = node.text.lower()
        for req in self._requirements:
            phrases = _COMPLIANCE_CHECKS.get(req, [])
            matched = next((p for p in phrases if p in text_lower), None)
            results.append(
                ComplianceResult(
                    clause_index=node.index,
                    clause_heading=node.heading,
                    requirement=req,
                    satisfied=matched is not None,
                    evidence=matched or "",
                )
            )
        return results


# ---------------------------------------------------------------------------
# AST Builder (bridges clause segmentation → AST)
# ---------------------------------------------------------------------------


def build_ast(title: str, clauses: list[Any]) -> ContractAST:
    """Convert a list of raw Clause objects into a ContractAST.

    Accepts both ``Clause`` dataclass instances (from segment.py) and plain
    dicts with the same fields so callers don't import segment.py directly.
    """

    def _to_node(c: Any, idx: int) -> ClauseNode:
        if isinstance(c, dict):
            return ClauseNode(
                index=idx,
                heading=c.get("heading", ""),
                text=c.get("text", ""),
                clause_type=c.get("clause_type", "other"),
                obligations=c.get("obligations", []),
            )
        # Assumes Clause dataclass or similar object
        return ClauseNode(
            index=idx,
            heading=getattr(c, "heading", ""),
            text=getattr(c, "text", ""),
            clause_type=getattr(c, "clause_type", "other"),
            obligations=getattr(c, "obligations", []),
        )

    return ContractAST(
        title=title,
        clauses=[_to_node(c, i) for i, c in enumerate(clauses)],
    )
