"""Clause segmentation + type classification.

Contracts are split on numbered/ALL-CAPS headings into clauses; each clause is
typed by a keyword profile (data, not code). Obligations ("shall ... within N
days") are extracted with their deadlines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CLAUSE_TYPES: dict[str, list[str]] = {
    "payment": ["payment", "fees", "invoice", "compensation"],
    "termination": ["termination", "terminate", "term and termination"],
    "confidentiality": ["confidential", "non-disclosure", "nda"],
    "limitation_of_liability": ["limitation of liability", "liable", "liability"],
    "indemnification": ["indemnify", "indemnification", "hold harmless"],
    "intellectual_property": ["intellectual property", "ip rights", "ownership of work"],
    "governing_law": ["governing law", "jurisdiction", "venue"],
    "warranty": ["warranty", "warrants", "as is"],
    "auto_renewal": ["automatically renew", "auto-renew", "renewal term"],
    "non_compete": ["non-compete", "not compete", "competitive business"],
}

HEADING = re.compile(r"^\s*(?:\d+\.|\bARTICLE\b|[A-Z][A-Z /&-]{6,})", re.MULTILINE)
OBLIGATION = re.compile(
    r"(?P<party>Vendor|Client|Supplier|Customer|Either party|Each party)\s+shall\s+"
    r"(?P<action>[^.;]{10,140}?)"
    r"(?:\s+within\s+(?P<days>\d{1,3})\s+(?:business\s+)?days)?[.;]",
    re.IGNORECASE,
)


@dataclass
class Clause:
    index: int
    heading: str
    text: str
    clause_type: str = "other"
    obligations: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        # dict(vars(...)) not vars(...): vars() hands back the live __dict__,
        # so a caller mutating the "serialised" clause was editing the Clause.
        return dict(vars(self))


def segment(contract_text: str) -> list[Clause]:
    matches = list(HEADING.finditer(contract_text))
    clauses: list[Clause] = []
    if not matches:
        clauses.append(Clause(0, "FULL TEXT", contract_text.strip()))
    else:
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(contract_text)
            block = contract_text[start:end].strip()
            heading_line = block.splitlines()[0].strip()
            clauses.append(Clause(i, heading_line[:80], block))

    for clause in clauses:
        clause.clause_type = classify(clause.text, clause.heading)
        clause.obligations = extract_obligations(clause.text)
    return clauses


# A keyword in the heading is worth more than the same word in the body: a
# heading is the drafter declaring what the clause IS, while the body routinely
# mentions neighbouring concepts in passing.
HEADING_WEIGHT = 3


def classify(text: str, heading: str | None = None) -> str:
    """Type a clause by weighted keyword profile, heading first.

    Body-only scoring ties constantly, and the old implementation broke those
    ties by CLAUSE_TYPES declaration order: a clause headed CONFIDENTIALITY that
    said "survives three years after termination" scored 1-1 and came back as
    `termination`, which both hid it from the missing-confidentiality check and
    made the document look like it had a termination clause when it did not.
    """
    body = text.lower()
    head = (
        heading if heading is not None else text.splitlines()[0] if text.strip() else ""
    ).lower()
    best, best_score = "other", 0
    for ctype, keywords in CLAUSE_TYPES.items():
        score = sum(
            HEADING_WEIGHT if kw in head else 1 for kw in keywords if kw in body or kw in head
        )
        if score > best_score:
            best, best_score = ctype, score
    return best


def extract_obligations(text: str) -> list[dict]:
    out = []
    for m in OBLIGATION.finditer(text):
        out.append(
            {
                "party": m.group("party"),
                "action": " ".join(m.group("action").split()),
                "deadline_days": int(m.group("days")) if m.group("days") else None,
            }
        )
    return out
