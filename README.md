# VULCAN — Agentic Engineering Foundry

**JANUS-10 Entry 09 · Nebius × NVIDIA Global AI Hackathon**

VULCAN treats software engineering as a governed tournament rather than a single-shot code generation event. An engineering objective becomes candidate implementations; candidates are tested, scored, repaired when possible, ranked, independently verified, and only then promoted. Every tournament ends with a machine-readable proof receipt.

> Generate options. Break them. Repair them. Promote only what survives evidence.

## Canonical demo

The objective is to implement a robust `safe_ratio(total, count)` helper. VULCAN evaluates three independently modeled candidates against an executable test suite. One candidate fails zero-count handling, enters the repair loop, and is re-evaluated. The verified winner is promoted only after all mandatory tests pass.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
uvicorn vulcan.app:app --reload
```

`VULCAN_MODE=demo` is deterministic. `NEBIUS_API_KEY` / `NEBIUS_MODEL` are reserved for the live sponsor-generation adapter; the hosted demo does not claim sponsor inference without credentials.
