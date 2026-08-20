"""API routes: /review (paste a contract), /corpus, /ask, /health."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from contractguard.clauses.segment import segment
from contractguard.llm.factory import get_provider
from contractguard.rag.qa import ask
from contractguard.risk.rules import scan
from contractguard.settings import get_config, resolve_path

logger = logging.getLogger(__name__)
router = APIRouter()

DISCLAIMER = "Workflow assistance for contract reviewers; not legal advice."


class ReviewRequest(BaseModel):
    text: str = Field(min_length=50, max_length=200_000)


class AskRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    provider: str | None = None


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/review")
def review(request: ReviewRequest) -> dict:
    clauses = segment(request.text)
    findings = scan(clauses)
    return {
        "n_clauses": len(clauses),
        "clauses": [c.as_dict() for c in clauses],
        "findings": [f.as_dict() for f in findings],
        "disclaimer": DISCLAIMER,
    }


@router.get("/corpus")
def corpus() -> list[dict]:
    path = resolve_path(get_config()["data"]["processed_dir"]) / "contracts.json"
    if not path.exists():
        raise HTTPException(status_code=503, detail="No corpus; run scripts/make_contracts.py")
    contracts = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for contract in contracts:
        findings = scan(segment(contract["text"]))
        out.append(
            {
                "contract_id": contract["contract_id"],
                "planted_risks": contract["planted_risks"],
                "n_findings": len(findings),
                "high": sum(1 for f in findings if f.severity == "high"),
            }
        )
    return out


@router.post("/ask")
def ask_endpoint(request: AskRequest) -> dict:
    try:
        provider = get_provider(request.provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return ask(request.question, provider=provider)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
