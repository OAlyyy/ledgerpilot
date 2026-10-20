# LedgerPilot

An AI agent that turns invoices into bookkeeping entries, with a human in the loop.

> **Demo project.** Not tax or accounting advice. All invoices in this repository are synthetic.

Status: under construction, built milestone by milestone. See [`docs/PLAN.md`](docs/PLAN.md) for
the architecture and the roadmap.

## Quick start (so far)

```bash
cd backend && uv sync
make synth        # generate ~60 synthetic invoice PDFs + ground truth into data/synth/
make test
```
