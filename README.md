# LedgerPilot

An AI agent that turns invoices into bookkeeping entries, with a human in the loop.

> **Demo project.** Not tax or accounting advice. All invoices in this repository are synthetic.

Status: under construction, built milestone by milestone. See [`docs/PLAN.md`](docs/PLAN.md) for
the architecture and the roadmap.

## Quick start (so far)

```bash
cp .env.example .env   # add a free Gemini API key (Google AI Studio)
cd backend && uv sync && cd ..
make synth             # 60 synthetic invoice PDFs + ground truth into data/synth/
make test              # offline: uses a scripted fake LLM
make eval-extract      # per-field extraction accuracy; MODEL=gemini/... LIMIT=20 to override
```

Latest extraction results: [`eval/reports/extraction/comparison.md`](eval/reports/extraction/comparison.md).
