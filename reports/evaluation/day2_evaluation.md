# Day 2 Evaluation Integrity Audit

Generated (UTC): `2026-10-18T14:43:00.118742+00:00`

This report audits retained Day 1 case records; it does not rerun either backend.

## Dataset

- Dataset: `tasks_v1` (v1) — **synthetic, hand-labeled**, 50 cases.
- SHA-256: `735492bacaffcfdd8bbef6a92b60e77290e9ae9bf95df74c5e880ea1f56399a7`.
- Results are exact-label agreement and do not establish real-world accuracy.

## Recomputed backend metrics

| Backend | Cases | Correct | Incorrect choices | Errors | Accuracy | Actual fallbacks | Would escalate (estimate) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local_hf | 50 | 41 | 9 | 0 | 82.0% | 0 | 27 (54.0%) |
| mock | 50 | 18 | 32 | 0 | 36.0% | 0 | 0 (0.0%) |

### Latency audit

- **local_hf:** n=50; mean 295.691 ms; p50 108.882 ms; p95 126.547 ms; max 9374.305 ms (T001); stored summary match: true.
- **mock:** n=50; mean 0.004 ms; p50 0.003 ms; p95 0.005 ms; max 0.054 ms (T001); stored summary match: true.

Percentiles use nearest rank: `sorted[ceil(p*n)-1]`. The retained local result's 9,374.305 ms T001 outlier explains why its mean exceeds p95. The Day 1 timer included request construction and `backend.decide`; lazy model loading inside the call was therefore included.

## Method and limitations

Actual fallback calls are zero because the Day 1 runner evaluates primary backends directly. “Would escalate” is a threshold-derived estimate, not an observed fallback count. The report is generated from retained JSON case records; the local model genuinely ran in the retained Day 1 run, but no fresh model inference was performed for this audit.

Model confidence is not shown to be calibrated. The dataset is small and synthetic, labels were not independently reviewed here, and latency is machine- and run-dependent. Mock results are a deterministic baseline, not evidence of model quality.

Reliability behavior has focused automated coverage for valid action flow, malformed outputs, confidence boundaries and unknown values, bounded fallback, fallback failures, trace redaction/status, and paid-backend construction guards.

## Reproduction

This audit does not rerun model inference. Regenerate it using the retained Day 1 artifact and new output paths (the writer refuses to replace existing files):

```bash
./.venv/bin/python eval/audit_day1.py \
  --json-output /tmp/jarvis-day2-results.json \
  --markdown-output /tmp/jarvis-day2-evaluation.md
```

The original Day 1 backend runs can be repeated separately with offline flags for the local model only when its weights are already cached; doing so produces new timing observations and does not reproduce this historical audit.
