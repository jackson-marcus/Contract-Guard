"""Fixtures: planted-risk contracts + stub embedder."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from make_contracts import generate

import contractguard.rag.qa as qa_mod
from contractguard.settings import get_config


class StubEmbedder:
    def embed(self, texts):
        for text in texts:
            vec = np.zeros(96, dtype=np.float32)
            for token in re.findall(r"[a-z0-9]+", str(text).lower()):
                vec[int(hashlib.md5(token.encode()).hexdigest(), 16) % 96] += 1.0
            yield vec


@pytest.fixture(scope="session")
def contracts():
    return generate(n_contracts=25, seed=8)


@pytest.fixture()
def corpus_on_disk(contracts, tmp_path, monkeypatch):
    import fastembed

    cfg = get_config()
    original = cfg["data"]["processed_dir"]
    proc = tmp_path / "processed"
    proc.mkdir()
    (proc / "contracts.json").write_text(json.dumps(contracts), encoding="utf-8")
    cfg["data"]["processed_dir"] = str(proc)
    monkeypatch.setattr(fastembed, "TextEmbedding", lambda *a, **k: StubEmbedder())
    qa_mod.invalidate()
    yield
    cfg["data"]["processed_dir"] = original
    qa_mod.invalidate()
