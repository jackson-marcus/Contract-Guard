"""Unit tests for the AST Visitor Architecture in ContractGuard."""

from __future__ import annotations

import pytest

from contractguard.ast.visitors import (
    ClauseNode,
    ComplianceVisitor,
    ContractAST,
    ObligationRecord,
    ObligationVisitor,
    RiskDetectionVisitor,
    RiskFlag,
    build_ast,
)


# ---------------------------------------------------------------------------
# Sample clause nodes
# ---------------------------------------------------------------------------

TERMINATION_CLAUSE = ClauseNode(
    index=0,
    heading="TERMINATION",
    text="Either party may terminate at any time without cause and without notice.",
    clause_type="termination",
    obligations=[],
)

PAYMENT_CLAUSE = ClauseNode(
    index=1,
    heading="PAYMENT TERMS",
    text="Client shall submit invoices within 30 days of service delivery.",
    clause_type="payment",
    obligations=[{"party": "Client", "action": "submit invoices", "deadline_days": 30}],
)

IP_CLAUSE = ClauseNode(
    index=2,
    heading="INTELLECTUAL PROPERTY",
    text="Supplier assigns all rights, title, and interest including all ip rights to Client.",
    clause_type="intellectual_property",
    obligations=[],
)

GDPR_CLAUSE = ClauseNode(
    index=3,
    heading="DATA PROCESSING",
    text="This agreement constitutes a data processing agreement. The lawful basis for processing"
         " is contractual necessity. Data subject rights shall be honored within 72 hours.",
    clause_type="other",
    obligations=[],
)

CLEAN_CLAUSE = ClauseNode(
    index=4,
    heading="DEFINITIONS",
    text="This section defines terms used throughout the agreement.",
    clause_type="other",
    obligations=[],
)


# ---------------------------------------------------------------------------
# RiskDetectionVisitor
# ---------------------------------------------------------------------------


def test_risk_visitor_detects_unilateral_termination():
    visitor = RiskDetectionVisitor()
    flags = TERMINATION_CLAUSE.accept(visitor)
    assert any(f.risk_category == "unilateral_termination" for f in flags)


def test_risk_visitor_detects_ip_assignment():
    visitor = RiskDetectionVisitor()
    flags = IP_CLAUSE.accept(visitor)
    assert any(f.risk_category == "broad_ip_assignment" for f in flags)


def test_risk_visitor_clean_clause_no_flags():
    visitor = RiskDetectionVisitor()
    flags = CLEAN_CLAUSE.accept(visitor)
    assert flags == []


def test_risk_visitor_returns_risk_flag_objects():
    visitor = RiskDetectionVisitor()
    flags = TERMINATION_CLAUSE.accept(visitor)
    assert all(isinstance(f, RiskFlag) for f in flags)


def test_risk_visitor_high_severity_unilateral():
    visitor = RiskDetectionVisitor()
    flags = TERMINATION_CLAUSE.accept(visitor)
    termination_flag = next(f for f in flags if f.risk_category == "unilateral_termination")
    assert termination_flag.severity == "high"


# ---------------------------------------------------------------------------
# ObligationVisitor
# ---------------------------------------------------------------------------


def test_obligation_visitor_extracts_records():
    visitor = ObligationVisitor()
    records = PAYMENT_CLAUSE.accept(visitor)
    assert len(records) == 1
    assert records[0].party == "Client"
    assert records[0].deadline_days == 30


def test_obligation_visitor_no_obligations():
    visitor = ObligationVisitor()
    records = TERMINATION_CLAUSE.accept(visitor)
    assert records == []


def test_obligation_visitor_returns_obligation_records():
    visitor = ObligationVisitor()
    records = PAYMENT_CLAUSE.accept(visitor)
    assert all(isinstance(r, ObligationRecord) for r in records)


# ---------------------------------------------------------------------------
# ComplianceVisitor
# ---------------------------------------------------------------------------


def test_compliance_visitor_detects_gdpr():
    visitor = ComplianceVisitor()
    results = GDPR_CLAUSE.accept(visitor)
    gdpr_result = next(r for r in results if r.requirement == "GDPR_data_processing")
    assert gdpr_result.satisfied


def test_compliance_visitor_unsatisfied_on_clean_clause():
    visitor = ComplianceVisitor()
    results = CLEAN_CLAUSE.accept(visitor)
    assert all(not r.satisfied for r in results)


def test_compliance_visitor_scoped_requirements():
    visitor = ComplianceVisitor(requirements=["GDPR_data_processing"])
    results = GDPR_CLAUSE.accept(visitor)
    assert len(results) == 1
    assert results[0].requirement == "GDPR_data_processing"


# ---------------------------------------------------------------------------
# ContractAST (multi-clause traversal)
# ---------------------------------------------------------------------------


def test_contract_ast_collects_all_risk_flags():
    ast = ContractAST(
        title="Test Contract",
        clauses=[TERMINATION_CLAUSE, IP_CLAUSE, CLEAN_CLAUSE],
    )
    visitor = RiskDetectionVisitor()
    all_flags = ast.accept(visitor)
    # Each clause returns a list; ast.accept collects non-empty results
    flat_flags = [f for flags in all_flags for f in flags]
    categories = {f.risk_category for f in flat_flags}
    assert "unilateral_termination" in categories
    assert "broad_ip_assignment" in categories


def test_contract_ast_obligation_aggregation():
    ast = ContractAST(
        title="Test Contract",
        clauses=[PAYMENT_CLAUSE, TERMINATION_CLAUSE],
    )
    visitor = ObligationVisitor()
    results = ast.accept(visitor)
    # Only PAYMENT_CLAUSE has obligations
    flat = [r for recs in results for r in recs]
    assert len(flat) == 1


# ---------------------------------------------------------------------------
# build_ast factory
# ---------------------------------------------------------------------------


def test_build_ast_from_dicts():
    raw_clauses = [
        {
            "heading": "PAYMENT",
            "text": "Client shall pay within 30 days.",
            "clause_type": "payment",
            "obligations": [{"party": "Client", "action": "pay", "deadline_days": 30}],
        },
        {
            "heading": "TERMINATION",
            "text": "Either party may terminate at any time without cause.",
            "clause_type": "termination",
            "obligations": [],
        },
    ]
    ast = build_ast("Sample Agreement", raw_clauses)
    assert len(ast.clauses) == 2
    assert ast.title == "Sample Agreement"
    assert ast.clauses[0].clause_type == "payment"


def test_build_ast_visitor_integration():
    """build_ast output should work with all visitors end-to-end."""
    raw = [
        {
            "heading": "AUTO RENEWAL",
            "text": "The agreement will automatically renew unless cancelled 30 days before term end.",
            "clause_type": "auto_renewal",
            "obligations": [],
        }
    ]
    ast = build_ast("Auto-Renewal Agreement", raw)
    visitor = RiskDetectionVisitor()
    results = ast.accept(visitor)
    flat = [f for flags in results for f in flags]
    assert any(f.risk_category == "auto_renewal_trap" for f in flat)
