# Isolated RAG vNext CLI

Run from the repository root with the existing `.venv` Python. LangGraph is kept in `.local/vnext-deps`; the Telegram worker's environment and project requirements are unchanged.

```powershell
.venv/Scripts/python.exe -m pip install --target .local/vnext-deps -r experiments/vnext/requirements.txt
.venv/Scripts/python.exe experiments/vnext/cli.py --preflight
.venv/Scripts/python.exe experiments/vnext/cli.py --max-groq-calls 30
```

`--interactive` uses one in-memory LangGraph thread until `/quit`. It reads `.env` for existing Groq, Qdrant and embedding settings but never writes it. The CLI refuses a Qdrant inventory or model mismatch and reads only approved Stage3 points. Its LangGraph checkpointer is in memory, so CLI conversations are not persisted. The scenario results are written after each completed turn to `results.json`; each record includes the client response, all retrieved candidates and applicability decisions, LLM calls, time, grounding rejections, and the retained conversation context.

`baseline.py` replays the same ordered scenario file through the current local algorithm with an isolated SQLite file under `.local`; it never opens production `data/conversations.sqlite3`. `retrieval_diagnostic.py` compares raw approved dense ranks with the existing hybrid retriever without Groq. `report.md` contains the human assessment and exact turn-by-turn comparison. The main suite's paid-period continuation is synthetic; `scenario-ofd-live-history.json` separately replays the exact preceding DirectBank user turns and live OFD turn.

Outcome: the prototype did not pass the client-usefulness criterion. It has no Telegram integration or planned production switch. See `report.md` and the appended `docs/PROJECT_STATE.md` record before considering changes.
