"""Segmentation, risk detection vs planted truth, obligations, API."""

from fastapi.testclient import TestClient

from contractguard.api.main import create_app
from contractguard.clauses.segment import segment
from contractguard.risk.rules import scan

RISKY = (
    "SERVICES AGREEMENT\n\n"
    "2. TERM\nThis agreement shall automatically renew for successive one year terms "
    "unless cancelled with 5 days notice before renewal.\n\n"
    "7. TERMINATION\nClient may terminate this agreement at any time, for any reason, "
    "in its sole discretion, without notice.\n\n"
    "9. LIABILITY\nVendor's liability shall not be capped or limited in any respect.\n\n"
    "3. PAYMENT TERMS\nClient shall pay all undisputed invoices within 30 days."
)


def test_segmentation_finds_headed_clauses():
    clauses = segment(RISKY)
    assert len(clauses) >= 4
    types = {c.clause_type for c in clauses}
    assert "termination" in types
    assert "payment" in types


def test_obligation_extraction_with_deadline():
    clauses = segment(RISKY)
    obligations = [o for c in clauses for o in c.obligations]
    pay = next(o for o in obligations if "pay" in o["action"])
    assert pay["party"] == "Client"
    assert pay["deadline_days"] == 30


def test_planted_risks_detected():
    findings = scan(segment(RISKY))
    rules = {f.rule for f in findings}
    assert {"unlimited_liability", "unilateral_termination", "auto_renewal_trap"} <= rules


def test_missing_clause_flagged():
    findings = scan(segment(RISKY))
    assert any(f.rule == "missing_confidentiality" for f in findings)


def test_corpus_recall_and_precision(contracts):
    caught = total_planted = false_on_clean = clean_total = 0
    for contract in contracts:
        findings = {f.rule for f in scan(segment(contract["text"]))}
        planted = set(contract["planted_risks"])
        total_planted += len(planted)
        caught += len(planted & findings)
        if not planted:
            clean_total += 1
            if any(
                f in findings
                for f in ("unlimited_liability", "unilateral_termination", "broad_indemnity")
            ):
                false_on_clean += 1
    recall = caught / max(total_planted, 1)
    assert recall >= 0.9, f"planted-risk recall {recall:.2f}"
    if clean_total:
        assert false_on_clean / clean_total <= 0.1


def test_api_review_roundtrip():
    client = TestClient(create_app())
    r = client.post("/review", json={"text": RISKY})
    assert r.status_code == 200
    body = r.json()
    assert body["findings"]
    assert "not legal advice" in body["disclaimer"]


def test_api_ask_with_fake(corpus_on_disk):
    client = TestClient(create_app())
    r = client.post(
        "/ask", json={"question": "Which contracts renew automatically?", "provider": "fake"}
    )
    assert r.status_code == 200
    assert r.json()["sources"]
