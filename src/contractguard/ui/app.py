"""Streamlit demo: paste a contract for review; corpus dashboard; clause Q&A."""

from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.environ.get("CONTRACTGUARD_API_URL", "http://localhost:8160")

st.set_page_config(page_title="contractguard", page_icon="📜", layout="wide")
st.title("📜 contractguard")
st.caption(
    "Clause segmentation, risk patterns, obligations, clause-library Q&A — reviewer assistance, not legal advice"
)


def _ok() -> bool:
    try:
        return httpx.get(f"{API_URL}/health", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


if not _ok():
    st.error(f"API not reachable at {API_URL}. Start it with `make api`.")
    st.stop()

tab_review, tab_corpus, tab_ask = st.tabs(
    ["Review a contract", "Corpus dashboard", "Ask the corpus"]
)

with tab_review:
    text = st.text_area(
        "Contract text",
        "SERVICES AGREEMENT\n\n2. TERM\nThis agreement shall automatically renew for successive one year terms unless cancelled with 5 days notice before renewal.\n\n7. TERMINATION\nClient may terminate this agreement at any time, for any reason, in its sole discretion.\n\n9. LIABILITY\nVendor's liability shall not be capped or limited in any respect.",
        height=200,
    )
    if st.button("Review", type="primary") and len(text) >= 50:
        r = httpx.post(f"{API_URL}/review", json={"text": text}, timeout=60)
        body = r.json()
        sev_icon = {"high": "🔴", "medium": "🟠", "low": "🟡"}
        st.subheader(f"{len(body['findings'])} finding(s) across {body['n_clauses']} clauses")
        for f in body["findings"]:
            st.markdown(f"{sev_icon[f['severity']]} **{f['rule']}** ({f['clause_heading']})")
            st.caption(f"{f['explanation']}")
            if f["excerpt"]:
                st.code(f["excerpt"][:220])
        with st.expander("Clauses + obligations"):
            for c in body["clauses"]:
                st.markdown(f"**{c['heading']}** · type: `{c['clause_type']}`")
                for o in c["obligations"]:
                    deadline = f" (within {o['deadline_days']} days)" if o["deadline_days"] else ""
                    st.caption(f"→ {o['party']} shall {o['action']}{deadline}")

with tab_corpus:
    r = httpx.get(f"{API_URL}/corpus", timeout=120)
    if r.status_code != 200:
        st.warning(r.json().get("detail", r.text))
    else:
        st.dataframe(pd.DataFrame(r.json()), use_container_width=True, hide_index=True)

with tab_ask:
    provider = st.radio("Provider", ["ollama", "claude", "fake"], horizontal=True)
    q = st.text_input("Question", placeholder="Which contracts allow termination without cause?")
    if q and len(q) >= 5:
        with st.spinner(f"Asking {provider}…"):
            r = httpx.post(
                f"{API_URL}/ask", json={"question": q, "provider": provider}, timeout=300
            )
        if r.status_code != 200:
            st.error(r.json().get("detail", r.text))
        else:
            body = r.json()
            st.markdown(body["answer"])
            st.caption(
                "sources: "
                + ", ".join(
                    f"contract-{s['contract_id']}/clause-{s['clause_index']}"
                    for s in body["sources"]
                )
            )
