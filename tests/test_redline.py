"""The redline pass: proposals must survive the same scanner as the draft they replace."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from contractguard.agents.base import Candidate, RedlineSource, self_check
from contractguard.agents.contractguard_agents import (
    PLAYBOOK,
    LibrarySource,
    PlaybookSource,
    invalidate_library,
)
from contractguard.api.main import create_app
from contractguard.clauses.segment import classify, segment
from contractguard.orchestrator.executor import RedlinePass
from contractguard.orchestrator.memory import RedlineLedger
from contractguard.orchestrator.planner import ALL_REJECTED, NO_SOURCE, Planner
from contractguard.risk.rules import RiskFinding, scan, scan_patterns

UNCAPPED = (
    "SERVICES AGREEMENT\n\n"
    "3. PAYMENT TERMS\nClient shall pay all undisputed invoices within 30 days.\n\n"
    "5. CONFIDENTIALITY\nEach party shall protect the other's confidential information.\n\n"
    "7. TERMINATION\nEither party may terminate for material breach with 30 days notice.\n\n"
    "9. LIABILITY\nVendor's liability shall not be capped or limited in any respect."
)

NO_CAP_AT_ALL = (
    "SERVICES AGREEMENT\n\n"
    "3. PAYMENT TERMS\nClient shall pay all undisputed invoices within 30 days.\n\n"
    "5. CONFIDENTIALITY\nEach party shall protect the other's confidential information.\n\n"
    "7. TERMINATION\nEither party may terminate for material breach with 30 days notice."
)

RISKY_LIABILITY = "9. LIABILITY\nVendor's liability shall not be capped or limited in any respect."
SAFE_LIABILITY = (
    "9. LIMITATION OF LIABILITY\nLiability is capped at fees paid in the prior twelve "
    "months, except for gross negligence or willful misconduct."
)


@pytest.fixture()
def offline_library(monkeypatch):
    """Two liability precedents, the risky one ranked first (it is shorter)."""
    invalidate_library()
    yield LibrarySource(
        clauses=(
            ("limitation_of_liability", RISKY_LIABILITY, "contract-3 clause-3"),
            ("limitation_of_liability", SAFE_LIABILITY, "contract-1 clause-7"),
        )
    )
    invalidate_library()


# --- the self-check -------------------------------------------------------


def test_every_playbook_position_survives_its_own_scanner():
    """A drafted fallback that trips our own rules would redline in a new problem."""
    tripped = {rule: self_check(text) for rule, (text, _) in PLAYBOOK.items()}
    assert {r: t for r, t in tripped.items() if t} == {}


def test_playbook_replacement_keeps_the_clause_type_it_replaces():
    """Swapping a clause for one the classifier types differently invents a
    missing-clause finding out of nowhere."""
    for rule in ("unlimited_liability", "unilateral_termination", "missing_confidentiality"):
        text = PLAYBOOK[rule][0]
        expected = rule.removeprefix("missing_") if rule.startswith("missing_") else None
        got = classify(text)
        if expected:
            assert got == expected, f"{rule} insert types as {got}"
        else:
            assert got != "other", f"{rule} replacement types as other"


def test_risky_precedent_is_refused_and_the_clean_one_used(offline_library):
    """Shortest-first ranks the uncapped clause ahead of the capped one; without
    the self-check the pass would answer "no liability cap" by pasting in a
    clause that says liability is uncapped."""
    finding = RiskFinding(
        rule="missing_limitation_of_liability",
        severity="medium",
        clause_index=-1,
        clause_heading="(absent)",
        excerpt="",
        explanation="",
    )
    redline, rejected = offline_library.propose_detailed(finding, None)
    assert redline is not None
    assert redline.citation == "contract-1 clause-7"
    assert [r.tripped for r in rejected] == ["unlimited_liability"]


def test_disabling_the_self_check_lets_the_risky_precedent_through(offline_library):
    offline_library.vet = False
    finding = RiskFinding(
        rule="missing_limitation_of_liability",
        severity="medium",
        clause_index=-1,
        clause_heading="(absent)",
        excerpt="",
        explanation="",
    )
    redline, rejected = offline_library.propose_detailed(finding, None)
    assert rejected == []
    assert redline.citation == "contract-3 clause-3"
    assert self_check(redline.replacement) == "unlimited_liability"


# --- planning -------------------------------------------------------------


def test_plan_is_ordered_high_severity_first():
    pipeline = RedlinePass([PlaybookSource()])
    steps, _ = pipeline.plan(UNCAPPED)
    severities = [s.severity for s in steps]
    assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s])
    assert steps[0].rule == "unlimited_liability"


def test_finding_with_no_fallback_is_reported_not_dropped():
    """no_liability_carveout is deliberately outside the playbook: fixing it means
    editing the counterparty's cap, not replacing their clause wholesale."""
    text = (
        "SERVICES AGREEMENT\n\n"
        "3. PAYMENT TERMS\nClient shall pay all undisputed invoices within 30 days.\n\n"
        "5. CONFIDENTIALITY\nEach party shall protect the other's confidential information.\n\n"
        "7. TERMINATION\nEither party may terminate for material breach with 30 days notice.\n\n"
        "9. LIMITATION OF LIABILITY\nLiability is capped at the fees paid in the prior year."
    )
    assert "no_liability_carveout" in {f.rule for f in scan(segment(text))}
    report = RedlinePass([PlaybookSource()]).run(text)
    blocked = {item["rule"]: item["reason"] for item in report["needs_review"]}
    assert blocked["no_liability_carveout"] == NO_SOURCE


def test_all_candidates_rejected_is_distinguished_from_none_offered():
    class OnlyBadOnes(RedlineSource):
        name = "bad"

        def candidates(self, finding, clause):
            return [Candidate(text=RISKY_LIABILITY, citation="bad-1")]

    finding = RiskFinding("unlimited_liability", "high", 0, "9. LIABILITY", "", "")
    _, reason = Planner([OnlyBadOnes()])._propose(finding, None)
    assert reason == ALL_REJECTED
    _, reason = Planner([PlaybookSource()])._propose(
        RiskFinding("payment_late_penalty", "low", 0, "3. PAYMENT", "", ""), None
    )
    assert reason == NO_SOURCE


# --- applying and the ledger ---------------------------------------------


def test_pass_removes_the_findings_it_targets():
    before = {f.rule for f in scan(segment(UNCAPPED))}
    assert "unlimited_liability" in before
    report = RedlinePass([PlaybookSource()]).run(UNCAPPED)
    assert "unlimited_liability" not in report["findings_after"]
    assert report["n_findings_after"] < report["n_findings_before"]


def test_insert_satisfies_the_missing_clause_it_answers():
    report = RedlinePass([PlaybookSource()]).run(NO_CAP_AT_ALL)
    assert "missing_limitation_of_liability" in report["findings_before"]
    assert "missing_limitation_of_liability" not in report["findings_after"]
    inserted = [e for e in report["ledger"]["entries"] if e["edit"] == "insert"]
    assert inserted and all(e["applied"] and e["resolved"] for e in inserted)


def test_pass_is_a_fixed_point_on_its_own_output():
    """Rerunning on the redlined text must not find more to do — if it does, the
    replacement language is itself getting flagged."""
    first = RedlinePass([PlaybookSource()]).run(UNCAPPED)
    second = RedlinePass([PlaybookSource()]).run(first["redlined_text"])
    assert second["n_findings_before"] == first["n_findings_after"]
    assert [e for e in second["ledger"]["entries"] if e["applied"]] == []


def test_ledger_attributes_an_introduced_finding_to_the_edit_that_caused_it():
    """The whole reason the pass re-scans between edits instead of once at the end."""

    class CarelessDrafter(RedlineSource):
        name = "careless"
        vet = False  # ship the first candidate whatever it says

        def candidates(self, finding, clause):
            return [Candidate(text=RISKY_LIABILITY, citation="careless-1")]

    report = RedlinePass([CarelessDrafter()]).run(NO_CAP_AT_ALL)
    entries = [e for e in report["ledger"]["entries"] if e["rule"].startswith("missing_")]
    culprit = next(e for e in entries if e["introduced"])
    assert culprit["resolved"] is True
    assert "unlimited_liability" in culprit["introduced"]
    assert report["ledger"]["summary"]["n_regressions"] >= 1


def test_ledger_counts_a_swap_as_a_regression_not_as_net_zero():
    ledger = RedlineLedger()
    entry = ledger.record(
        order=1,
        rule="missing_limitation_of_liability",
        edit="insert",
        citation="x",
        applied=True,
        before=["missing_limitation_of_liability"],
        after=["unlimited_liability"],
    )
    assert entry.n_before == entry.n_after == 1
    assert entry.resolved and entry.regressed
    assert ledger.summary()["n_regressions"] == 1


# --- corpus-wide + API ----------------------------------------------------


def test_precedent_is_preferred_over_the_playbook_when_it_is_clean(corpus_on_disk):
    invalidate_library()
    report = RedlinePass().run(UNCAPPED)
    step = next(s for s in report["steps"] if s["rule"] == "unlimited_liability")
    assert not step["redline"]["citation"].startswith("playbook:")
    assert self_check(step["redline"]["replacement"]) == ""
    invalidate_library()


def test_library_has_clean_precedent_for_only_some_risk_categories(corpus_on_disk):
    """An organisation's own agreements only contain a good version of a clause if
    it ever managed to negotiate one. Four of the six risky categories in the
    corpus have exactly one wording in circulation, and it is the bad one."""
    invalidate_library()
    from contractguard.agents.contractguard_agents import RULE_CLAUSE_TYPE, _library_clauses

    library = _library_clauses()
    clean = set()
    for rule, ctype in RULE_CLAUSE_TYPE.items():
        if rule.startswith("missing_"):
            continue
        if any(not scan_patterns(segment(t)) for c, t, _ in library if c == ctype):
            clean.add(rule)
    assert clean == {"unlimited_liability", "unilateral_termination"}
    invalidate_library()


def test_api_redline_applies_edits_and_reports_the_ledger():
    client = TestClient(create_app())
    r = client.post("/redline", json={"text": UNCAPPED})
    assert r.status_code == 200
    body = r.json()
    assert body["n_findings_after"] < body["n_findings_before"]
    assert body["ledger"]["summary"]["n_edits"] == len([s for s in body["steps"] if s["redline"]])
    assert body["redlined_text"] != UNCAPPED


def test_api_redline_plan_only_leaves_the_text_alone():
    client = TestClient(create_app())
    r = client.post("/redline", json={"text": UNCAPPED, "apply": False})
    assert r.status_code == 200
    assert "redlined_text" not in r.json()
    assert r.json()["steps"]


def test_api_redline_rejects_a_stub_document():
    client = TestClient(create_app())
    assert client.post("/redline", json={"text": "too short"}).status_code == 422
