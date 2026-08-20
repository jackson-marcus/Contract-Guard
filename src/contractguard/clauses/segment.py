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
        return vars(self)


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
        clause.clause_type = classify(clause.text)
        clause.obligations = extract_obligations(clause.text)
    return clauses


def classify(text: str) -> str:
    lowered = text.lower()
    best, best_hits = "other", 0
    for ctype, keywords in CLAUSE_TYPES.items():
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits > best_hits:
            best, best_hits = ctype, hits
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
