.PHONY: synth test lint

BACKEND := cd backend &&

synth:  ## generate synthetic invoices + ground truth into data/synth/
	$(BACKEND) uv run python -m ledgerpilot.synth --out ../data/synth --seed 42

test:
	$(BACKEND) uv run pytest -q

lint:
	$(BACKEND) uv run ruff check . && uv run ruff format --check .
