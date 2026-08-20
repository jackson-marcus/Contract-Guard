"""Synthetic contract corpus with planted risk patterns (ground truth recorded).

Usage:
    uv run python scripts/make_contracts.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from contractguard.settings import get_config, resolve_path

SAFE_CLAUSES = {
    "payment": "3. PAYMENT TERMS\nClient shall pay all undisputed invoices within 30 days. Vendor shall submit invoices monthly.",
    "termination": "7. TERMINATION\nEither party may terminate for material breach with 30 days written notice and opportunity to cure.",
    "confidentiality": "5. CONFIDENTIALITY\nEach party shall protect the other's confidential information with reasonable care for three years.",
    "limitation_of_liability": "9. LIMITATION OF LIABILITY\nLiability is capped at fees paid in the prior twelve months, except for gross negligence or willful misconduct.",
    "governing_law": "12. GOVERNING LAW\nThis agreement is governed by the laws of the State of Delaware.",
    "warranty": "6. WARRANTY\nVendor warrants services will be performed in a professional and workmanlike manner.",
}

RISKY_CLAUSES = {
    "unlimited_liability": "9. LIABILITY\nVendor's liability shall not be capped or limited in any respect, and shall extend to all losses.",
    "unilateral_termination": "7. TERMINATION\nClient may terminate this agreement at any time, for any reason, in its sole discretion, without notice or cure period.",
    "auto_renewal_trap": "2. TERM\nThis agreement shall automatically renew for successive one year terms unless cancelled with 5 days notice before renewal.",
    "broad_indemnity": "10. INDEMNIFICATION\nVendor shall indemnify Client against any and all claims regardless of cause, including Client's own negligence.",
    "ip_assignment": "8. INTELLECTUAL PROPERTY\nVendor assigns all right, title and interest in any work product, treated as work made for hire.",
    "non_compete_broad": "11. NON-COMPETE\nVendor shall not compete with Client in any market for a period of 3 years after termination.",
}

PREAMBLE = "SERVICES AGREEMENT\nThis agreement is entered between Client and Vendor.\n\n1. SERVICES\nVendor shall provide the services described in Exhibit A. Vendor shall deliver reports within 15 days of each quarter end.\n"


def generate(n_contracts: int, seed: int = 42):
    rng = np.random.default_rng(seed)
    contracts = []
    for i in range(1, n_contracts + 1):
        planted = [risk for risk in RISKY_CLAUSES if rng.random() < 0.35]
        parts = [PREAMBLE]
        used_types = {"payment", "confidentiality", "governing_law"}
        for t in sorted(used_types):
            parts.append(SAFE_CLAUSES[t])
        if "unlimited_liability" not in planted and rng.random() < 0.8:
            parts.append(SAFE_CLAUSES["limitation_of_liability"])
        if "unilateral_termination" not in planted and rng.random() < 0.85:
            parts.append(SAFE_CLAUSES["termination"])
        for risk in planted:
            parts.append(RISKY_CLAUSES[risk])
        order = rng.permutation(len(parts) - 1) + 1
        text = parts[0] + "\n\n" + "\n\n".join(parts[j] for j in order)
        contracts.append({"contract_id": i, "text": text, "planted_risks": planted})
    return contracts


def main() -> None:
    cfg = get_config()["data"]
    contracts = generate(cfg["n_contracts"], cfg["seed"])
    out = resolve_path(cfg["processed_dir"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "contracts.json").write_text(json.dumps(contracts, indent=1), encoding="utf-8")
    n_risky = sum(1 for c in contracts if c["planted_risks"])
    print(f"Wrote {len(contracts)} contracts ({n_risky} with planted risks) -> {out}")


if __name__ == "__main__":
    main()
