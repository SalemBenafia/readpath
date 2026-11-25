.PHONY: setup test run

setup:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
	.venv/bin/pip install -r requirements.txt

test:
	.venv/bin/python -m pytest -q

run:
	.venv/bin/streamlit run app.py
