"""Measure the redline pass over the whole synthetic corpus.

Usage:
    uv run python scripts/make_contracts.py
    uv run python scripts/redline_bench.py

Everything printed is derived from the corpus described by configs/config.yaml,
so regenerating with a different seed changes the numbers.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contractguard.agents.base import self_check
from contractguard.agents.contractguard_agents import (
    RULE_CLAUSE_TYPE,
    LibrarySource,
    PlaybookSource,
    _library_clauses,
)
from contractguard.orchestrator.executor import RedlinePass
from contractguard.risk.rules import scan_patterns
from contractguard.settings import get_config, resolve_path


def load_corpus() -> list[dict]:
    path = resolve_path(get_config()["data"]["processed_dir"]) / "contracts.json"
    if not path.exists():
        raise SystemExit("No corpus. Run: uv run python scripts/make_contracts.py")
    return json.loads(path.read_text(encoding="utf-8"))


def clean_precedent_coverage() -> dict[str, tuple[int, int]]:
    """Per risk category: (distinct clauses of that type, how many scan clean)."""
    library = _library_clauses()
    out: dict[str, tuple[int, int]] = {}
    for rule, ctype in RULE_CLAUSE_TYPE.items():
        if rule.startswith("missing_"):
            continue
        texts = {text for t, text, _ in library if t == ctype}
        out[rule] = (len(texts), sum(1 for t in texts if not self_check(t)))
    return out


def detector_overlap(corpus: list[dict]) -> Counter[str]:
    """Where the regex library and the AST phrase visitor agree, per clause."""
    from contractguard.ast import RiskDetectionVisitor, build_ast
    from contractguard.clauses.segment import segment

    tally: Counter[str] = Counter({"both": 0, "regex only": 0, "phrase only": 0, "neither": 0})
    for contract in corpus:
        clauses = segment(contract["text"])
        ast = build_ast(f"contract-{contract['contract_id']}", clauses)
        phrase = {n.index: bool(n.accept(RiskDetectionVisitor())) for n in ast.clauses}
        for clause in clauses:
            regex = bool(scan_patterns([clause]))
            tally[
                "both"
                if regex and phrase[clause.index]
                else "regex only"
                if regex
                else "phrase only"
                if phrase[clause.index]
                else "neither"
            ] += 1
    return tally


def main() -> None:
    corpus = load_corpus()

    overlap = detector_overlap(corpus)
    print("per-clause agreement, risk/rules.py regexes vs ast RiskDetectionVisitor phrases")
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(overlap.items())))
    print()

    coverage = clean_precedent_coverage()
    print("clean precedent available in the clause library")
    print(f"{'risk rule':<26}{'distinct clauses':>18}{'scan clean':>12}")
    for rule, (n, clean) in sorted(coverage.items()):
        print(f"{rule:<26}{n:>18}{clean:>12}")
    have = sum(1 for _, clean in coverage.values() if clean)
    print(f"-> library can answer {have}/{len(coverage)} risk categories from precedent\n")

    for label, vet in (("self-check ON", True), ("self-check OFF", False)):
        sources = [LibrarySource(), PlaybookSource()]
        for source in sources:
            source.vet = vet
        pipeline = RedlinePass(sources)
        before = after = edits = rejected = regressions = 0
        by_source: Counter[str] = Counter()
        tripped: Counter[str] = Counter()
        introduced: Counter[str] = Counter()
        unresolved = 0
        needs_review: Counter[str] = Counter()
        for contract in corpus:
            report = pipeline.run(contract["text"])
            before += report["n_findings_before"]
            after += report["n_findings_after"]
            rejected += report["n_candidates_rejected"]
            for step in report["steps"]:
                if step["redline"]:
                    citation = step["redline"]["citation"]
                    by_source["playbook" if citation.startswith("playbook:") else "precedent"] += 1
                    for r in step["redline"]["rejected"]:
                        tripped[r["tripped"]] += 1
                else:
                    needs_review[step["rule"]] += 1
            for entry in report["ledger"]["entries"]:
                edits += entry["applied"]
                unresolved += entry["applied"] and not entry["resolved"]
                if entry["introduced"]:
                    regressions += 1
                    for r in entry["introduced"]:
                        introduced[r] += 1

        print(f"--- {label} | {len(corpus)} contracts ---")
        print(f"findings {before} -> {after}   edits applied: {edits}")
        print(f"replacement drawn from: {dict(by_source)}")
        print(f"candidates refused by the self-check: {rejected} {dict(tripped)}")
        print(f"edits that introduced a new finding: {regressions} {dict(introduced)}")
        print(f"edits that left their own target standing: {unresolved}")
        print(f"findings handed back to a human: {dict(needs_review)}\n")


if __name__ == "__main__":
    main()
