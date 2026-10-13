.PHONY: test check demo dashboard

test:
	python -m pytest -q

check:
	python -m compileall -q src tests eval app
	python -m pytest -q
	git diff --check

demo:
	python -m jarvis.cli --check-config
	python -m jarvis.cli --backend mock --demo-trace --trace-path traces/demo.jsonl
	python eval/run_eval.py --backend mock --output eval/reports/mock_v1.json

dashboard:
	python -m streamlit run app/dashboard.py
