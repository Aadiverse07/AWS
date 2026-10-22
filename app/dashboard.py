"""Interactive, read-only dashboard for the local Arnova Decider demo."""

from __future__ import annotations

import json
import html
from pathlib import Path

import streamlit as st
from app.dashboard_data import (
    CSV_MIME_TYPE,
    csv_filename,
    load_evaluation_report,
    load_trace_events,
    records_to_csv_bytes,
)
from app.demo_workflow import (
    SCENARIOS,
    DemoRun,
    run_demo_decision,
    threshold_explanation,
    workflow_tree_state,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS = (
    ROOT / "eval/reports/mock_v1.json",
    ROOT / "eval/reports/local_hf_v1.json",
)
TRACE_PATH = ROOT / "traces/demo.jsonl"
PAGES = ("Guided Demo", "Evaluation Lab", "Audit Trail")

st.set_page_config(page_title="Arnova Decider", page_icon="A", layout="wide")
st.markdown(
    """
    <style>
    :root { color-scheme: dark; }
    :root { color-scheme: dark; --ink: #e8e6e1; --muted: #aaa9a3; --quiet: #777a79; --line: #343b3a; --surface: #111514; --accent: #c3ef71; --accent-ink: #15200c; }
    html { scroll-behavior: smooth; }
    .stApp { background: #0b0e0d; color: var(--ink); }
    [data-testid="stHeader"] { background: rgba(11,14,13,.94); }
    [data-testid="stSidebar"] { background: #101413; border-right: 1px solid var(--line); }
    [data-testid="stSidebar"] > div { padding-top: 1.2rem; }
    .block-container { max-width: 1450px; padding-top: .8rem; padding-bottom: 3rem; }
    h1, h2, h3 { color: var(--ink); letter-spacing: -.04em; }
    h1 { font-size: 2.25rem !important; }
    p, label, [data-testid="stMarkdownContainer"] { color: #c3c4be; }
    [data-testid="stMetric"] { background: #111514; border: 1px solid var(--line); padding: 15px 17px; border-radius: 3px; }
    [data-testid="stMetricLabel"] { color: var(--muted); }
    [data-testid="stMetricValue"] { color: var(--ink); }
    div[data-testid="stRadio"] > div { gap: .45rem; }
    div[data-testid="stRadio"] label { background: #111514; border: 1px solid var(--line); padding: .48rem .85rem; border-radius: 3px; transition: border-color .22s, background-color .22s; }
    div[data-testid="stRadio"] label:has(input:checked) { border-color: #9ac84f; background: #1b2414; }
    .stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] button { border-radius: 3px; border: 1px solid var(--accent) !important; background: var(--accent) !important; color: var(--accent-ink) !important; font-weight: 700; min-height: 2.7rem; transition: transform .2s, background .2s; }
    .stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stFormSubmitButton"] button:hover { background: #d2f791 !important; transform: translateY(-2px); }
    input[type="radio"] { accent-color: var(--accent); }
    input, textarea, [data-baseweb="select"] > div { background: #111514 !important; border-color: var(--line) !important; }
    [data-testid="stDataFrame"], .stTable { border: 1px solid var(--line); border-radius: 3px; }
    .stTable { display:block; overflow-x:auto; white-space:nowrap; }
    :focus-visible { outline:2px solid var(--accent)!important; outline-offset:3px; }
    .brandbar { display:flex; align-items:center; justify-content:space-between; padding:.6rem 0 .95rem; border-bottom:1px solid var(--line); margin-bottom:1.4rem; }
    .brandmark { color:var(--ink); font-size:.78rem; letter-spacing:.15em; font-weight:800; }
    .brandmark span { color:var(--accent); }
    .brandmeta { color:var(--muted); font-size:.72rem; letter-spacing:.06em; text-transform:uppercase; }
    .hero { min-height: 510px; display:grid; grid-template-columns:1.03fr .97fr; align-items:center; gap:3rem; padding:3.5rem 0 4.2rem; border-bottom:1px solid var(--line); }
    .hero-copy { animation: rise-in .78s cubic-bezier(.2,.75,.25,1) both; }
    .hero-kicker, .section-label { color:var(--accent); text-transform:uppercase; font-size:.7rem; letter-spacing:.14em; font-weight:750; }
    .hero h1 { font-size:clamp(3.25rem,5.8vw,6rem) !important; line-height:.98; max-width:850px; margin:1.15rem 0 1.35rem; font-family: Georgia, 'Times New Roman', serif; font-weight:500; letter-spacing:-.065em; }
    .hero h1 em { color:var(--accent); font-weight:500; }
    .hero p { max-width:610px; margin-bottom:1.5rem; color:#b8bbb4; font-size:1.08rem; line-height:1.65; animation: rise-in .8s .15s both; }
    .hero-actions { display:flex; gap:.7rem; flex-wrap:wrap; animation: rise-in .8s .25s both; }
    .cta { display:inline-flex; padding:.78rem 1.1rem; border:1px solid var(--accent); background:var(--accent); color:#16200e!important; text-decoration:none!important; font-weight:750; font-size:.83rem; transition:transform .2s, background .2s; }
    .cta:hover { transform:translateY(-2px); background:#d2f791; }
    .cta.secondary { color:var(--ink)!important; background:transparent; border-color:#5b625d; }
    .cta.secondary:hover { border-color:var(--accent); color:var(--accent)!important; }
    .hero-art { min-height:370px; display:flex; align-items:center; justify-content:center; position:relative; border-left:1px solid #242b27; animation: fade-in 1.1s .15s both; }
    .hero-art svg { width:min(100%,560px); height:auto; overflow:visible; }
    .hero-art .wire { fill:none; stroke:#526054; stroke-width:1.4; }
    .hero-art .wire.on { stroke:var(--accent); stroke-width:2; stroke-dasharray:400; stroke-dashoffset:400; animation: draw-line 1.4s .6s ease forwards; }
    .hero-art .node { fill:#101512; stroke:#566054; stroke-width:1.4; }
    .hero-art .node.on { stroke:var(--accent); fill:#20291a; }
    .hero-art text { fill:#c6c9c2; font:12px system-ui,sans-serif; }
    .hero-art text.hot { fill:var(--accent); }
    .mode-pill { display:inline-flex; align-items:center; gap:.48rem; color:#d1f19e; border:1px solid #46543a; background:#151c12; padding:.38rem .62rem; font-size:.69rem; font-weight:750; letter-spacing:.08em; }
    .mode-dot { width:.42rem; height:.42rem; border-radius:100%; background:var(--accent); }
    .section-head { padding:4rem 0 1.5rem; border-bottom:1px solid var(--line); margin-bottom:1.7rem; }
    .section-head h2 { font-family:Georgia,'Times New Roman',serif; font-size:clamp(2.1rem,4.4vw,4.2rem); font-weight:500; letter-spacing:-.055em; margin:.4rem 0 .6rem; }
    .section-head p { color:var(--muted); max-width:700px; line-height:1.6; }
    .numbered { color:#707871; font-size:.68rem; letter-spacing:.12em; text-transform:uppercase; }
    .surface { background: #111514; border: 1px solid var(--line); border-radius: 3px; padding: 1rem 1.1rem; height: 100%; }
    .surface h3 { font-size: 1rem; margin: .1rem 0 .55rem; }
    .surface p { margin: 0; font-size: .9rem; line-height: 1.52; }
    .muted { color: #91a1b2; font-size: .84rem; }
    .tree { max-width: 1050px; margin: .9rem auto 1.15rem; }
    .tree-card { background: #111514; border: 1px solid #414943; border-radius: 3px; padding: .85rem 1rem; color: var(--ink); min-height: 68px; }
    .tree-card.active { border: 1.5px solid #acd95f; background: #182014; }
    .tree-card.fallback-active { border: 1.5px solid #e6bd6a; background: #211d13; }
    .tree-card.error { border: 1.5px solid #d77b78; background: #241716; }
    .tree-card.dim { opacity: .55; border-style: dashed; }
    .tree-card .eyebrow { color: var(--accent); font-size: .68rem; font-weight: 750; letter-spacing: .1em; text-transform: uppercase; }
    .tree-card h4 { margin: .32rem 0 .22rem; color: #f2f6fb; font-size: .96rem; }
    .tree-card p { margin: 0; font-size: .82rem; line-height: 1.42; color: #b6c4d2; overflow-wrap: anywhere; }
    .tree-main { max-width: 600px; margin-inline: auto; }
    .tree-arrow { color: #6f8599; text-align: center; height: 32px; line-height: 30px; font-size: 1.25rem; }
    .tree-arrow.active { color: var(--accent); }
    .tree-gate { text-align: center; max-width: 430px; margin: 0 auto; padding: .75rem 1rem; border: 1px solid #526778; border-radius: 12px; background: #141f2a; }
    .tree-gate strong { color: #eff5fb; display: block; }
    .tree-gate small { color: #b5c4d2; }
    .tree-branches { display: grid; grid-template-columns: 1fr 1fr; gap: 1.2rem; }
    .tree-branch { min-width: 0; }
    .branch-label { text-align: center; color: #9eb0c2; font-size: .75rem; min-height: 25px; padding-top: .2rem; }
    .branch-label.selected { color: var(--accent); font-weight: 700; }
    .branch-label.fallback-selected { color: #f2c66f; font-weight: 700; }
    .branch-svg { height: 56px; display: block; width: 100%; }
    .branch-svg path { fill: none; stroke: #526778; stroke-width: 2.3; }
    .branch-svg path.selected { stroke: var(--accent); }
    .branch-svg path.fallback-selected { stroke: #e7b254; }
    .branch-svg marker path { fill: #778a9c; stroke: none; }
    .tree-outcomes { display: grid; grid-template-columns: 1fr 1fr; gap: 1.2rem; }
    .tree-evidence { margin-top:.8rem; border-left:2px solid #91bf51; padding:.65rem .9rem; color:#b7beb3; font-size:.8rem; background:#111514; }
    .workflow-intro { display:grid; grid-template-columns:.8fr 1.2fr; gap:2rem; align-items:start; margin:1rem 0 2rem; }
    .workflow-intro h3 { font-family:Georgia,'Times New Roman',serif; font-weight:500; font-size:2rem; }
    .stage-list { display:grid; grid-template-columns:repeat(4,1fr); border-top:1px solid var(--line); border-bottom:1px solid var(--line); }
    .stage { padding:.85rem .9rem .85rem 0; color:#c5c9c2; font-size:.8rem; border-right:1px solid var(--line); }
    .stage:last-child { border-right:0; }
    .stage b { display:block; color:var(--accent); font-size:.65rem; letter-spacing:.1em; margin-bottom:.35rem; }
    .architecture { display:grid; grid-template-columns:repeat(3,1fr); gap:.8rem; margin:1.2rem 0 3rem; }
    .architecture .surface { min-height:130px; }
    .status-label { color:var(--accent); text-transform:uppercase; font-size:.65rem; letter-spacing:.12em; }
    .planned .status-label { color:#b1b5af; }
    .footer { border-top:1px solid var(--line); padding:1.5rem 0 2rem; margin-top:3rem; display:flex; justify-content:space-between; color:#858a83; font-size:.75rem; }
    @keyframes rise-in { from { opacity:0; transform:translateY(20px); clip-path:inset(0 0 100% 0); } to { opacity:1; transform:translateY(0); clip-path:inset(0); } }
    @keyframes fade-in { from { opacity:0; } to { opacity:1; } }
    @keyframes draw-line { to { stroke-dashoffset:0; } }
    @media (prefers-reduced-motion: reduce) { *,*::before,*::after { scroll-behavior:auto!important; animation-duration:.01ms!important; animation-iteration-count:1!important; transition-duration:.01ms!important; } }
    @media (max-width: 800px) { .hero { grid-template-columns:1fr; gap:1rem; min-height:0; padding:2.5rem 0; } .hero-art { min-height:240px; border-left:0; border-top:1px solid var(--line); } .workflow-intro { grid-template-columns:1fr; gap:.5rem; } .tree-branches, .tree-outcomes { grid-template-columns:1fr; gap:.65rem; } .tree { margin-inline:0; } }
    @media (max-width: 560px) { .stage-list { grid-template-columns:repeat(2,1fr); } .stage:nth-child(2) { border-right:0; } .stage:nth-child(-n+2) { border-bottom:1px solid var(--line); } .architecture { grid-template-columns:1fr; } .footer { flex-direction:column; gap:.4rem; } .hero h1 { font-size:3.3rem!important; } }
    </style>
    """,
    unsafe_allow_html=True,
)

if st.session_state.get("dashboard_page") not in PAGES:
    st.session_state.dashboard_page = "Guided Demo"
if "last_demo_run" not in st.session_state:
    st.session_state.last_demo_run = None

st.markdown(
    '<div class="brandbar"><div class="brandmark"><span>ARNOVA</span> DECIDER</div>'
    '<div class="brandmeta">An explainable AI decision engine &nbsp;·&nbsp; Local prototype</div></div>',
    unsafe_allow_html=True,
)
st.write("")
page = st.radio("Navigation", PAGES, horizontal=True, key="dashboard_page", label_visibility="collapsed")


def tree_card(kind: str, eyebrow: str, title: str, body: str) -> str:
    return (
        f'<div class="tree-card {kind}"><div class="eyebrow">{html.escape(eyebrow)}</div>'
        f'<h4>{html.escape(title)}</h4><p>{html.escape(body)}</p></div>'
    )


def show_workflow(run: DemoRun) -> None:
    """Draw a branch diagram from the actual workflow outcome and trace event."""
    event = run.trace_events[-1] if run.trace_events else {}
    state = workflow_tree_state(run)
    task = tree_card("active", "Incoming task", "Request received", run.request.question)
    validated = tree_card("active", "Request validation", "Allowed options checked", "DecisionRequest accepted; routing allowlist passed.")
    backend = state.get("backend") or "Not available in this trace"

    if state["stopped"]:
        primary = tree_card("error", "Primary decision", f"Stopped · {backend}", f"{run.error_type or 'Decision error'}; no successful choice was returned.")
        stopped = tree_card("error", "Safe stop", "Routing action not executed", "The trace records an error. Confidence and threshold are not available in this trace.")
        graph = (
            '<div class="tree"><div class="tree-main">' + task
            + '<div class="tree-arrow active">↓</div>' + validated
            + '<div class="tree-arrow active">↓</div>' + primary
            + '<div class="tree-arrow">↘</div>' + stopped + '</div></div>'
        )
        explanation = "The primary backend failed before returning a decision. The workflow stopped before threshold evaluation, fallback, and TaskRoutingAction."
    else:
        primary_choice = state.get("primary_choice") or "Not available in this trace"
        selected_route = state.get("selected_route") or "Not available in this trace"
        confidence = state.get("confidence")
        threshold = state.get("threshold")
        conf_text = f"{confidence:.2f}" if confidence is not None else "Not available in this trace"
        threshold_text = f"{threshold:.2f}" if threshold is not None else "Not available in this trace"
        primary_kind = "active" if state["primary_branch_state"] == "selected" else "dim"
        fallback_kind = "fallback-active" if state["fallback_branch_state"] == "selected" else "dim"
        primary_label = "Selected branch" if state["primary_branch_state"] == "selected" else "Not selected"
        fallback_label = "Selected branch" if state["fallback_branch_state"] == "selected" else "Not selected"
        gate = (
            '<div class="tree-gate"><div class="eyebrow">DecisionEngine condition</div>'
            f'<strong>{html.escape(state["condition"])}</strong>'
            f'<small>Confidence {conf_text} · threshold {threshold_text}</small></div>'
        )
        primary_card = tree_card(primary_kind, primary_label, "Accept primary result", f"Primary choice: {primary_choice}")
        fallback_body = (
            f"Fallback choice: {selected_route} · final source: {state.get('final_source') or 'Not available in this trace'}"
            if state["escalated"] else "Fallback not invoked; primary result met the threshold."
        )
        fallback_card = tree_card(fallback_kind, fallback_label, "Invoke fallback once", fallback_body)
        primary_action = tree_card(
            "active" if state["primary_branch_state"] == "selected" else "dim",
            "Final action" if state["primary_branch_state"] == "selected" else "Not reached",
            "TaskRoutingAction",
            f"{run.outcome.action.destination} · {run.outcome.action.status}" if state["primary_branch_state"] == "selected" else "This branch was not selected.",
        )
        fallback_action = tree_card(
            "fallback-active" if state["fallback_branch_state"] == "selected" else "dim",
            "Final action" if state["fallback_branch_state"] == "selected" else "Not reached",
            "TaskRoutingAction",
            f"{run.outcome.action.destination} · {run.outcome.action.status}" if state["fallback_branch_state"] == "selected" else "Fallback was not invoked.",
        )
        arrow_primary = "selected" if state["primary_branch_state"] == "selected" else ""
        arrow_fallback = "fallback-selected" if state["fallback_branch_state"] == "selected" else ""
        graph = (
            '<div class="tree"><div class="tree-main">' + task
            + '<div class="tree-arrow active">↓</div>' + validated
            + '<div class="tree-arrow active">↓</div>'
            + tree_card("active", f"Primary backend · {backend}", "Primary decision", f"Proposed route: {primary_choice}")
            + '<div class="tree-arrow active">↓</div>' + gate
            + '</div><svg class="branch-svg" viewBox="0 0 1000 70" role="img" aria-label="Threshold branches to primary acceptance or fallback">'
            + '<defs><marker id="treeArrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" /></marker></defs>'
            + f'<path class="{arrow_primary}" d="M500 0 V20 H250 V64" marker-end="url(#treeArrow)" />'
            + f'<path class="{arrow_fallback}" d="M500 0 V20 H750 V64" marker-end="url(#treeArrow)" />'
            + '</svg><div class="tree-branches"><div class="tree-branch">'
            + f'<div class="branch-label {"selected" if state["primary_branch_state"] == "selected" else ""}">Confidence ≥ threshold</div>'
            + primary_card + '<div class="tree-arrow ' + arrow_primary + '">↓</div>' + primary_action
            + '</div><div class="tree-branch">'
            + f'<div class="branch-label {"fallback-selected" if state["fallback_branch_state"] == "selected" else ""}">Confidence below / unavailable</div>'
            + fallback_card + '<div class="tree-arrow ' + arrow_fallback + '">↓</div>' + fallback_action
            + '</div></div></div>'
        )
        explanation, evidence_kind = threshold_explanation(event)

    st.markdown(graph, unsafe_allow_html=True)
    st.markdown(
        f'<div class="surface"><div class="section-label">Branch explanation · {html.escape(evidence_kind) if not state["stopped"] else "Recorded error path"}</div>'
        f'<p>{html.escape(explanation)}</p></div>',
        unsafe_allow_html=True,
    )
    trace_id = event.get("trace_id")
    evidence_detail = (
        f"Trace event {trace_id} · run {run.request.run_id} · status {event.get('status', 'unknown')}"
        if event else f"No event was emitted · run {run.request.run_id}"
    )
    st.markdown(f'<div class="tree-evidence">Evidence: {html.escape(evidence_detail)}. Expand the trace below for recorded fields.</div>', unsafe_allow_html=True)


if page == "Guided Demo":
    st.markdown(
        '<section class="hero" id="top"><div class="hero-copy">'
        '<div class="hero-kicker">An explainable AI decision engine</div>'
        '<h1>Every decision has a path.<br><em>Make yours explainable.</em></h1>'
        '<p>Arnova evaluates tasks, follows controlled decision paths, handles fallback scenarios, and preserves the evidence behind every decision.</p>'
        '<div class="hero-actions"><a class="cta" href="#how-arnova-decides">Explore the Decision Engine&nbsp; ↘</a>'
        '<a class="cta secondary" href="#interactive-demo">Run Interactive Demo&nbsp; ↓</a></div>'
        '<div style="margin-top:1.25rem"><span class="mode-pill"><span class="mode-dot"></span>DETERMINISTIC MOCK · LOCAL ONLY</span></div>'
        '</div><div class="hero-art" aria-label="Decision path branching from task validation through a confidence gate to execution or fallback">'
        '<svg viewBox="0 0 560 390" role="img" aria-labelledby="decision-graph-title">'
        '<title id="decision-graph-title">A task moves through validation, decision evaluation, and selected execution branches</title>'
        '<path class="wire on" d="M280 56 V112 M280 163 V214 M280 268 V274 H130 V284 M280 274 H430 V284 M130 336 V355 M430 336 V355"/>'
        '<rect class="node on" x="174" y="18" width="212" height="48"/><text x="280" y="47" text-anchor="middle" class="hot">INCOMING TASK</text>'
        '<rect class="node" x="174" y="112" width="212" height="52"/><text x="280" y="143" text-anchor="middle">INPUT VALIDATION</text>'
        '<rect class="node on" x="174" y="214" width="212" height="54"/><text x="280" y="238" text-anchor="middle" class="hot">DECISION EVALUATION</text><text x="280" y="255" text-anchor="middle">confidence gate</text>'
        '<rect class="node on" x="36" y="284" width="188" height="52"/><text x="130" y="315" text-anchor="middle" class="hot">NORMAL EXECUTION</text>'
        '<rect class="node" x="336" y="284" width="188" height="52"/><text x="430" y="315" text-anchor="middle">FALLBACK / SAFE STOP</text>'
        '<text x="130" y="377" text-anchor="middle">result + audit evidence</text><text x="430" y="377" text-anchor="middle">trace remains inspectable</text>'
        '</svg></div></section>', unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-head" id="how-arnova-decides"><div class="numbered">01 / How Arnova decides</div>'
        '<h2>Control at every branch.</h2><p>Requests are validated before a backend proposes a route. The engine compares recorded confidence with policy, then accepts, falls back once, or stops safely.</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="workflow-intro"><div><div class="section-label">Decision sequence</div>'
        '<h3>Evidence travels with the outcome.</h3><p class="muted">The highlighted workflow below is drawn from the run result and its trace fields.</p></div>'
        '<div class="stage-list"><div class="stage"><b>01 · RECEIVE</b>Incoming task</div><div class="stage"><b>02 · VALIDATE</b>Contract & allowlist</div>'
        '<div class="stage"><b>03 · EVALUATE</b>Threshold policy</div><div class="stage"><b>04 · RECORD</b>Result & audit evidence</div></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-head" id="interactive-demo"><div class="numbered">02 / Interactive demo</div>'
        '<h2>Run the decision workflow.</h2><p>Choose a deterministic scenario. Inspect the actual branch, the recorded evidence, and whether a routing action ran.</p></div>',
        unsafe_allow_html=True,
    )
    st.caption("The local task-routing demonstration records a destination; it does not execute the task content.")
    input_col, evidence_col = st.columns([1.5, .9], gap="large")
    with input_col:
        scenario = st.radio("Choose a scenario", tuple(SCENARIOS), horizontal=False, key="demo_scenario")
        st.caption(SCENARIOS[scenario])
        question = st.text_area("Incoming task", value="Review the project evaluation and summarize the key findings.", max_chars=500, height=85, key="demo_question")
        preferred_route = st.selectbox("First route option", ("research", "developer", "documentation"), help="The standard mock chooses the first supplied option.", key="demo_route")
        if st.button("Run Guided Demo", type="primary", use_container_width=True):
            if not question.strip():
                st.error("Enter a task description before running the decision.")
            else:
                with st.spinner("Running the local deterministic workflow…"):
                    st.session_state.last_demo_run = run_demo_decision(
                        scenario=scenario, question=question, preferred_route=preferred_route
                    )
    with evidence_col:
        st.markdown('<div class="surface"><div class="section-label">Evaluation evidence · synthetic</div><h3>Historical exact-label agreement</h3><p>50 hand-labeled tasks per benchmark. These figures describe the checked-in synthetic dataset, not live model performance.</p></div>', unsafe_allow_html=True)
        try:
            mock_report = load_evaluation_report(REPORTS[0])
            local_report = load_evaluation_report(REPORTS[1])
            metric_cols = st.columns(2)
            metric_cols[0].metric("Mock benchmark", f"{100 * mock_report['accuracy_over_all_tasks']:.0f}%")
            metric_cols[1].metric("Local model report", f"{100 * local_report['accuracy_over_all_tasks']:.0f}%")
            st.caption("Exact-choice match only · synthetic data")
        except ValueError as exc:
            st.warning(f"Evaluation summary unavailable: {exc}")

    run = st.session_state.last_demo_run
    if run is not None:
        st.markdown(f'<div class="section-label">Live workflow · {html.escape(run.scenario)}</div>', unsafe_allow_html=True)
        st.markdown(f"### Decision path · {run.scenario}")
        st.caption(f"Last run · ID `{run.request.run_id}` · decision `{run.request.decision_id}`")
        show_workflow(run)
        if run.outcome:
            a, b, c, d = st.columns(4)
            a.metric("Final route", run.outcome.selected)
            b.metric("Backend", run.outcome.primary_backend)
            c.metric("Escalated", "Yes" if run.outcome.escalated else "No")
            d.metric("Action status", run.outcome.action.status)
        else:
            st.error(f"Workflow stopped ({run.error_type or 'decision error'}). No successful routing action was produced.")
        if run.trace_events:
            with st.expander(f"Inspect trace evidence · {len(run.trace_events)} event(s)", expanded=False):
                st.json(run.trace_events, expanded=False)
                st.download_button(
                    "Download this run's trace CSV",
                    data=records_to_csv_bytes(run.trace_events),
                    file_name=csv_filename("interactive_demo", suffix="trace"),
                    mime=CSV_MIME_TYPE,
                    key="download_interactive_trace",
                )
        else:
            st.warning("No trace event is available for this run.")

    st.markdown(
        '<div class="section-head" id="architecture"><div class="numbered">03 / Architecture & future vision</div>'
        '<h2>Clear boundaries. Auditable choices.</h2><p>Arnova separates policy, decision backends, and task actions so each stage can be inspected and governed.</p></div>'
        '<div class="architecture">'
        '<div class="surface"><div class="status-label">Implemented · local</div><h3>Decision runtime</h3><p>Contracts, confidence thresholds, one-step fallback, safe routing action, and JSONL trace evidence.</p></div>'
        '<div class="surface"><div class="status-label">Adapter present · live use unverified</div><h3>AWS Bedrock</h3><p>An opt-in backend adapter exists in the repository. This demo does not call AWS; credentials, quota, and live behavior are not verified here.</p></div>'
        '<div class="surface planned"><div class="status-label">Planned · not connected</div><h3>External tools</h3><p>Figma and Claude could become governed tools behind explicit permissions, approvals, and traceable actions. No live connection is claimed.</p></div>'
        '</div><div class="footer"><div>ARNOVA DECIDER &nbsp;·&nbsp; An Explainable AI Decision Engine</div><div>Local deterministic demo · Synthetic evaluation data</div></div>',
        unsafe_allow_html=True,
    )

elif page == "Evaluation Lab":
    st.markdown('<div class="section-head"><div class="numbered">04 / Evaluation</div><h2>Evaluation Lab.</h2><p>Historical synthetic benchmark reports with their source records and downloadable CSVs.</p></div>', unsafe_allow_html=True)
    st.caption("Historical synthetic benchmark reports · hand-labeled exact-choice tasks · not live model performance")
    report_cols = st.columns(2, gap="large")
    for col, path in zip(report_cols, REPORTS):
        with col:
            try:
                report = load_evaluation_report(path)
            except ValueError as exc:
                st.error(str(exc))
                continue
            st.markdown(f"#### {path.stem}")
            st.caption("Synthetic benchmark report · checked-in data")
            c1, c2, c3 = st.columns(3)
            c1.metric("Tasks", report["total_tasks"])
            c2.metric("Exact-label accuracy", f"{100 * report.get('accuracy_over_all_tasks', 0):.1f}%")
            policy = report.get("escalation_policy", {})
            c3.metric("Estimated escalation", f"{100 * policy.get('rate_over_all_tasks', 0):.1f}%")
            latency = report.get("latency_ms", {})
            st.markdown('<div class="surface"><div class="section-label">What these numbers mean</div><p>Accuracy measures exact choice-label agreement across this synthetic dataset. Escalation is estimated from confidence and threshold; the report does not represent an observed fallback call. Latency summarizes the recorded benchmark runs.</p></div>', unsafe_allow_html=True)
            st.caption("Latency (ms): " + " · ".join(f"{key} {latency.get(key, 'not available')}" for key in ("mean", "p50", "p95")))
            records = report["records"]
            if records:
                st.download_button(
                    f"Download {path.stem} evaluation CSV · {len(records)} rows",
                    data=records_to_csv_bytes(records),
                    file_name=csv_filename(path.stem, suffix="evaluation"),
                    mime=CSV_MIME_TYPE,
                    key=f"download_{path.stem}_evaluation_csv",
                )
                with st.expander(f"Inspect {len(records)} task records"):
                    st.dataframe(records, use_container_width=True, hide_index=True)
            else:
                st.info("No evaluation records are available.")

else:
    st.markdown('<div class="section-head"><div class="numbered">05 / Audit evidence</div><h2>Audit Trail.</h2><p>Historical decision events, searchable and available as a source-aligned CSV export.</p></div>', unsafe_allow_html=True)
    st.caption("Checked-in historical trace events are separate from interactive runs. Guided Demo run traces are shown with their result and can be downloaded separately.")
    try:
        events, errors = load_trace_events(TRACE_PATH)
    except ValueError as exc:
        st.error(str(exc))
    else:
        for error in errors:
            st.warning(error)
        if events:
            escalations = sum(event.get("escalated") is True for event in events)
            failures = sum(event.get("status") in {"error", "rejected"} for event in events)
            m1, m2, m3 = st.columns(3)
            m1.metric("Historical events", len(events))
            m2.metric("Escalations", escalations)
            m3.metric("Errors / rejections", failures)
            trace_filter = st.text_input("Search trace events", placeholder="Run ID, backend, status…").strip().casefold()
            visible = [event for event in events if trace_filter in json.dumps(event, ensure_ascii=False).casefold()] if trace_filter else events
            st.caption(f"Showing {len(visible)} of {len(events)} events")
            if visible:
                timeline_fields = (
                    "timestamp", "event_type", "backend", "chosen", "confidence",
                    "threshold", "escalated", "final_choice", "status",
                )
                st.table([{field: event.get(field) for field in timeline_fields} for event in visible])
                with st.expander("Inspect an event"):
                    selected = st.selectbox("Trace event", range(len(visible)), format_func=lambda i: f"{visible[i].get('timestamp', 'unknown time')} · {visible[i].get('status', 'unknown')} · {visible[i].get('backend', 'unknown backend')}")
                    st.json(visible[selected], expanded=True)
            else:
                st.info("No trace events match this search.")
            st.download_button(
                f"Download historical trace CSV · {len(events)} rows",
                data=records_to_csv_bytes(events),
                file_name=csv_filename(TRACE_PATH.name, suffix="trace"),
                mime=CSV_MIME_TYPE,
                key="download_historical_trace_csv",
            )
        else:
            st.info("No historical trace events are available.")
