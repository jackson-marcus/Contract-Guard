"""The two places replacement language can come from: precedent, and the playbook.

`LibrarySource` goes first. A clause the organisation has already signed in
another agreement is far easier to get across the table than boilerplate, and it
comes with a citation the counterparty can look up. But a library assembled from
executed contracts is not a library of *good* clauses — it contains every bad
one the organisation ever accepted, so most of what it offers gets thrown out by
the self-check in `RedlineSource.propose`.

`PlaybookSource` is the drafted fallback position, used when precedent has
nothing clean to offer. Every position here is vetted by
`tests/test_redline.py::test_every_playbook_position_survives_its_own_scanner`,
which runs the pattern library over the playbook itself.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Iterable

from contractguard.agents.base import Candidate, RedlineSource
from contractguard.clauses.segment import Clause, segment
from contractguard.risk.rules import RiskFinding
from contractguard.settings import get_config, resolve_path

# The clause type to search the library under for each rule. Also the type the
# replacement is expected to classify as, so that swapping a clause out does not
# silently create a missing-clause finding in its place — the one deliberate
# exception is non_compete_broad, whose playbook answer is a non-solicit and
# genuinely is not a non-compete any more.
RULE_CLAUSE_TYPE: dict[str, str] = {
    "unlimited_liability": "limitation_of_liability",
    "unilateral_termination": "termination",
    "auto_renewal_trap": "auto_renewal",
    "broad_indemnity": "indemnification",
    "ip_assignment": "intellectual_property",
    "non_compete_broad": "non_compete",
    "missing_limitation_of_liability": "limitation_of_liability",
    "missing_termination": "termination",
    "missing_confidentiality": "confidentiality",
}

PLAYBOOK: dict[str, tuple[str, str]] = {
    "unlimited_liability": (
        "9. LIMITATION OF LIABILITY\n"
        "Except for the carve-outs below, each party's aggregate liability under this "
        "agreement is capped at the fees paid and payable in the twelve months preceding "
        "the claim. The cap does not apply to gross negligence, willful misconduct, "
        "breach of confidentiality, or a party's indemnity obligations.",
        "Swap the uncapped exposure for a mutual cap tied to fees, keeping the "
        "carve-outs a counterparty will expect to see.",
    ),
    "unilateral_termination": (
        "7. TERMINATION\n"
        "Either party may terminate this agreement for material breach on thirty days "
        "written notice, provided the breaching party has failed to cure within that "
        "period. Either party may terminate for convenience on ninety days notice.",
        "Make the termination right mutual and give both sides a cure period rather "
        "than a discretionary exit for one of them.",
    ),
    "auto_renewal_trap": (
        "2. TERM\n"
        "The initial term runs twelve months. Any renewal term takes effect only if both "
        "parties confirm it in writing before the then-current term expires. Silence does "
        "not extend this agreement.",
        "Opt-in renewal removes the trap outright: no notice deadline to miss, because "
        "nothing happens unless both sides act.",
    ),
    "broad_indemnity": (
        "10. INDEMNIFICATION\n"
        "Each party shall indemnify the other against third-party claims to the extent "
        "they arise from the indemnifying party's breach of this agreement. Neither party "
        "is required to indemnify the other for the other party's own acts or omissions.",
        "Narrow the indemnity to third-party claims caused by the indemnifier and make "
        "it mutual, instead of covering the other side's own fault.",
    ),
    "ip_assignment": (
        "8. OWNERSHIP OF WORK PRODUCT\n"
        "Vendor assigns to Client the deliverables specifically identified in Exhibit A "
        "upon payment. Vendor retains ownership of its pre-existing and generally "
        "applicable materials, and grants Client a perpetual, non-exclusive licence to "
        "use them as embedded in the deliverables.",
        "Scope the assignment to the paid-for deliverables and licence the background "
        "materials, rather than assigning everything the vendor owns.",
    ),
    "non_compete_broad": (
        "11. NON-SOLICITATION\n"
        "During the term and for twelve months afterwards, neither party will directly "
        "solicit for employment any individual who worked on the engagement. General "
        "advertising and hiring of respondents to it are permitted.",
        "A restraint the counterparty can actually enforce: swap the market-wide "
        "restriction for a mutual non-solicit with a carve-out for general hiring.",
    ),
    "missing_termination": (
        "TERMINATION\n"
        "Either party may terminate this agreement for material breach on thirty days "
        "written notice if the breach is not cured within that period, and for "
        "convenience on ninety days written notice.",
        "The agreement is silent on how it ends; add a mutual termination right.",
    ),
    "missing_confidentiality": (
        "CONFIDENTIALITY\n"
        "Each party shall protect the other's confidential information with at least "
        "reasonable care, use it only to perform this agreement, and return or destroy it "
        "on request. The obligation survives for three years after termination.",
        "No confidentiality clause was found; add a mutual obligation with a survival period.",
    ),
}
PLAYBOOK["missing_limitation_of_liability"] = (
    PLAYBOOK["unlimited_liability"][0].replace("9. LIMITATION", "LIMITATION"),
    "The agreement caps nothing; add a mutual cap with the usual carve-outs.",
)

# Deliberately absent from the playbook: no_liability_carveout and
# payment_late_penalty. Both are surgical edits to wording the counterparty has
# already negotiated (a cap amount, an interest rate) — dropping in a whole
# replacement clause would quietly discard terms they agreed to. The pass
# reports them as needing a human instead of pretending to fix them.


class PlaybookSource(RedlineSource):
    """Drafted fallback positions, one per rule we are willing to auto-redline."""

    name = "playbook"

    def candidates(self, finding: RiskFinding, clause: Clause | None) -> Iterable[Candidate]:
        entry = PLAYBOOK.get(finding.rule)
        if entry is None:
            return []
        return [Candidate(text=entry[0], citation=f"playbook:{finding.rule}")]

    def rationale(self, finding: RiskFinding, candidate: Candidate) -> str:
        return PLAYBOOK[finding.rule][1]


@functools.lru_cache(maxsize=1)
def _library_clauses() -> tuple[tuple[str, str, str], ...]:
    """(clause_type, text, citation) for every clause in the corpus on disk.

    Empty when no corpus has been generated — the playbook alone still works.
    """
    path = resolve_path(get_config()["data"]["processed_dir"]) / "contracts.json"
    if not path.exists():
        return ()
    out: list[tuple[str, str, str]] = []
    for contract in json.loads(path.read_text(encoding="utf-8")):
        for clause in segment(contract["text"]):
            out.append(
                (
                    clause.clause_type,
                    clause.text,
                    f"contract-{contract['contract_id']} clause-{clause.index}",
                )
            )
    return tuple(out)


def invalidate_library() -> None:
    """Drop the cached corpus (tests point the corpus at a temp directory)."""
    _library_clauses.cache_clear()


class LibrarySource(RedlineSource):
    """Precedent: clauses of the same type from elsewhere in the corpus.

    Candidates are offered shortest-first — the terse version of a clause is the
    one that survived negotiation with the fewest bolted-on exceptions, and it is
    the easiest to justify. Most of them are still rejected upstream, because a
    library of signed agreements is full of the clauses this tool exists to flag.
    """

    name = "library"

    def __init__(self, clauses: tuple[tuple[str, str, str], ...] | None = None, limit: int = 12):
        self._clauses = _library_clauses() if clauses is None else clauses
        self._limit = limit

    def candidates(self, finding: RiskFinding, clause: Clause | None) -> Iterable[Candidate]:
        wanted = RULE_CLAUSE_TYPE.get(finding.rule)
        if wanted is None:
            return []
        origin = clause.text if clause is not None else None
        # Deduplicate by text: the same clause recurs across agreements, and
        # offering it eleven times would inflate the rejection count without
        # giving the reviewer another option.
        pool: dict[str, str] = {}
        for ctype, text, citation in self._clauses:
            if ctype == wanted and text != origin and text not in pool:
                pool[text] = citation
        ranked = sorted(pool.items(), key=lambda pair: (len(pair[0]), pair[1]))
        return [Candidate(text=t, citation=c) for t, c in ranked[: self._limit]]

    def rationale(self, finding: RiskFinding, candidate: Candidate) -> str:
        return (
            f"{finding.explanation} Precedent: this wording is already in force at "
            f"[{candidate.citation}]."
        )


def build_sources() -> list[RedlineSource]:
    """Precedent first, drafted position as the fallback."""
    return [LibrarySource(), PlaybookSource()]
