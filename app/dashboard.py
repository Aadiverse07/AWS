"""Read-only local dashboard for Jarvis Decider."""
import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(page_title="Jarvis Decider", layout="wide")
st.title("Jarvis Decider")
st.caption("Local prototype · synthetic evaluation · no actions executed here")

reports = [
    ROOT / "eval/reports/mock_v1.json",
    ROOT / "eval/reports/local_hf_v1.json",
]

st.header("Evaluation reports")
cols = st.columns(len(reports))
for col, path in zip(cols, reports):
    with col:
        st.subheader(path.stem)
        if not path.exists():
            st.info("Report not found. Run the relevant evaluation first.")
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            st.error("Report could not be read as valid JSON.")
            continue

        st.metric("Tasks", report.get("total_tasks", 0))
        st.metric(
            "Accuracy (all tasks)",
            f"{100 * report.get('accuracy_over_all_tasks', 0):.1f}%",
        )
        policy = report.get("escalation_policy", {})
        st.metric(
            "Would escalate",
            f"{100 * policy.get('rate_over_all_tasks', 0):.1f}%",
        )
        latency = report.get("latency_ms", {})
        st.write("Latency (ms)", {
            "mean": latency.get("mean"),
            "p50": latency.get("p50"),
            "p95": latency.get("p95"),
        })
        st.caption(
            "Synthetic prototype results, not a claim of real-world accuracy."
        )

st.header("Decision trace")
trace_path = ROOT / "traces/demo.jsonl"
if not trace_path.exists():
    st.info("No demo trace yet. Run make demo first.")
else:
    events = []
    errors = []
    for line_number, line in enumerate(
        trace_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
            else:
                errors.append(f"Line {line_number}: expected a JSON object.")
        except json.JSONDecodeError:
            errors.append(f"Line {line_number}: invalid JSON.")

    for error in errors:
        st.warning(error)

    if events:
        st.dataframe(events, use_container_width=True, hide_index=True)
        escalations = sum(e.get("escalated") is True for e in events)
        failures = sum(e.get("status") == "error" for e in events)
        c1, c2, c3 = st.columns(3)
        c1.metric("Trace events", len(events))
        c2.metric("Escalations", escalations)
        c3.metric("Error events", failures)
    else:
        st.info("No valid trace events found yet.")
