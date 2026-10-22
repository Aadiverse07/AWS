# Two-Minute Guided Demo

## Start

From the repository root:

```bash
./.venv/bin/python -m streamlit run app/dashboard.py --server.address 127.0.0.1 --server.port 8501
```

Open `http://127.0.0.1:8501`. The landing page introduces Arnova Decider with the statement “Every decision has a path. Make yours explainable.” It shows the branching workflow graphic and identifies the execution mode as `DETERMINISTIC MOCK · LOCAL ONLY`. Scroll to the interactive demo for its three scenario choices and synthetic evaluation evidence. No AWS request is made.

## Walkthrough

1. Choose **Standard mock**, enter a task, and click **Run Guided Demo**. The real mock backend selects the first supplied route at confidence `1.00`. The tree shows that value meeting the `D1` threshold `0.60`, so the primary route reaches `TaskRoutingAction`.
2. Choose **Low-confidence fallback fixture** and run it. This deterministic fixture returns `0.20`; the real engine compares it with `0.60` and calls its `MockBackend` fallback once. The selected branch, final route, and trace agree. This is a fixture, not a model response.
3. Choose **Backend error fixture** and run it. The tree shows the primary backend error and safe stop. No threshold result or successful route is available, and `TaskRoutingAction` is not executed.
4. Expand **Inspect trace evidence** for the event associated with the run. The run trace CSV is available in that panel.
5. Optionally open **Evaluation Lab** for the checked-in synthetic reports and their CSV exports, then **Audit Trail** for the separate historical trace.
6. The lower architecture section separates implemented local behavior, the present-but-unverified Bedrock adapter, and planned Figma / Claude tools.

## Explain the boundary

The mock always chooses the first supplied option and does not interpret task meaning. The fallback and error examples are deterministic fixtures that exercise engine branches covered by tests. The routing action returns a structured local outcome; it does not execute task content. Evaluation data is synthetic. Live AWS inference remains unverified.
