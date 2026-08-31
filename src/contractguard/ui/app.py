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

tab_review, tab_redline, tab_corpus, tab_ask = st.tabs(
    ["Review a contract", "Redline plan", "Corpus dashboard", "Ask the corpus"]
)

SAMPLE = """SERVICES AGREEMENT

2. TERM
This agreement shall automatically renew for successive one year terms unless cancelled with 5 days notice before renewal.

7. TERMINATION
Client may terminate this agreement at any time, for any reason, in its sole discretion.

9. LIABILITY
Vendor's liability shall not be capped or limited in any respect."""

with tab_review:
    text = st.text_area("Contract text", SAMPLE, height=200)
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

with tab_redline:
    st.caption(
        "Every proposal is re-scanned by the same rule library before it is offered, and the "
        "document is re-scanned after each edit — so an edit that fixes one finding and creates "
        "another shows up as a regression instead of a net-zero count."
    )
    rl_text = st.text_area("Contract text", SAMPLE, height=200, key="redline_text")
    if st.button("Build redline plan", type="primary") and len(rl_text) >= 50:
        rp = httpx.post(f"{API_URL}/redline", json={"text": rl_text}, timeout=120)
        if rp.status_code != 200:
            st.error(rp.json().get("detail", rp.text))
        else:
            plan = rp.json()
            ledger = plan["ledger"]["summary"]
            a, b, c, d = st.columns(4)
            a.metric(
                "Findings",
                plan["n_findings_after"],
                plan["n_findings_after"] - plan["n_findings_before"],
            )
            b.metric("Edits applied", ledger["n_edits"])
            c.metric("Candidates refused", plan["n_candidates_rejected"])
            d.metric("Regressions", ledger["n_regressions"])
            if ledger["n_regressions"]:
                st.warning(
                    "An edit created a finding that was not there before: "
                    + ", ".join(ledger["introduced_rules"])
                )
            for step in plan["steps"]:
                r = step["redline"]
                if r is None:
                    st.markdown(f"**{step['order']}. {step['rule']}** — no automated redline")
                    st.caption(step["blocked_reason"])
                    continue
                st.markdown(
                    f"**{step['order']}. {step['rule']}** · `{r['edit']}` · [{r['citation']}]"
                )
                st.caption(r["rationale"])
                if r["original"]:
                    st.code(r["original"][:400], language=None)
                st.code(r["replacement"][:400], language=None)
                for rej in r["rejected"]:
                    st.caption(
                        f"passed over [{rej['citation']}] — it trips `{rej['tripped']}` itself"
                    )
            if plan["needs_review"]:
                st.subheader("Left for a human")
                for item in plan["needs_review"]:
                    st.markdown(f"- **{item['rule']}** ({item['severity']}) — {item['reason']}")
            with st.expander("Redlined contract"):
                st.code(plan["redlined_text"], language=None)

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
