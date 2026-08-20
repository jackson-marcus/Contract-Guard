"""Clause-library RAG: ask questions across the reviewed corpus with citations."""

from __future__ import annotations

import functools
import json
import re

import numpy as np
from rank_bm25 import BM25Okapi

from contractguard.clauses.segment import segment
from contractguard.llm.base import LLMProvider
from contractguard.llm.factory import get_provider
from contractguard.settings import get_config, resolve_path

SYSTEM = (
    "You answer questions about a contract corpus using only the provided clause "
    "excerpts, citing them as [contract-N clause-M]. This is workflow assistance "
    "for a reviewer, not legal advice — say so if asked for advice."
)

PROMPT = """Clause excerpts:
{context}

Question: {question}

Answer with citations:"""


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@functools.lru_cache(maxsize=1)
def _index():
    path = resolve_path(get_config()["data"]["processed_dir"]) / "contracts.json"
    if not path.exists():
        raise FileNotFoundError("No contracts; run scripts/make_contracts.py")
    contracts = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for contract in contracts:
        for clause in segment(contract["text"]):
            entries.append(
                {
                    "contract_id": contract["contract_id"],
                    "clause_index": clause.index,
                    "clause_type": clause.clause_type,
                    "text": clause.text,
                }
            )
    from fastembed import TextEmbedding

    model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    dense = np.array(
        [np.asarray(v, dtype=np.float32) for v in model.embed([e["text"] for e in entries])]
    )
    dense /= np.linalg.norm(dense, axis=1, keepdims=True) + 1e-12
    bm25 = BM25Okapi([_tokenize(e["text"]) for e in entries])
    return entries, dense, bm25, model


def invalidate() -> None:
    _index.cache_clear()


def retrieve(question: str, top_k: int | None = None) -> list[dict]:
    cfg = get_config()["rag"]
    top_k = top_k or cfg["top_k"]
    entries, dense, bm25, model = _index()
    q = np.asarray(next(iter(model.embed([question]))), dtype=np.float32)
    q /= np.linalg.norm(q) + 1e-12
    dense_rank = np.argsort(-(dense @ q))
    bm25_rank = np.argsort(-np.asarray(bm25.get_scores(_tokenize(question))))
    fused: dict[int, float] = {}
    for rank_list in (dense_rank[: top_k * 3], bm25_rank[: top_k * 3]):
        for rank, idx in enumerate(rank_list):
            fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (cfg["rrf_k"] + rank + 1)
    best = sorted(fused, key=fused.get, reverse=True)[:top_k]
    return [entries[i] for i in best]


def ask(question: str, provider: LLMProvider | None = None) -> dict:
    provider = provider or get_provider()
    hits = retrieve(question)
    context = "\n\n".join(
        f"--- [contract-{h['contract_id']} clause-{h['clause_index']}] ({h['clause_type']}) ---\n{h['text'][:600]}"
        for h in hits
    )
    answer = provider.complete(
        PROMPT.format(context=context, question=question),
        system=SYSTEM,
        max_tokens=get_config()["rag"]["max_answer_tokens"],
    )
    return {
        "answer": answer,
        "provider": provider.name,
        "sources": [
            {
                "contract_id": h["contract_id"],
                "clause_index": h["clause_index"],
                "clause_type": h["clause_type"],
            }
            for h in hits
        ],
    }
