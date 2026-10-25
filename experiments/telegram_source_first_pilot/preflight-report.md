# Pilot preflight report

Date: 2026-10-25. Status: **code smoke passed; not ready for manual conversations yet**. The dedicated bot/key are absent and the local Qdrant endpoint did not accept a connection.

## Provenance

- Repository HEAD observed: `86a86404ddd50efa88ba2b7ba69c8cc6fdef26a7` (unchanged at preflight).
- Model configured in code: `openai/gpt-oss-20b`.
- Qdrant collection pinned in the imported read-only retriever: `knowledge_stage3_retrieval_20261022`; embedding: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Worker: not started. Pilot Telegram token: absent. Pilot Groq key: absent. Allowlist entries: 0. Qdrant startup inventory remains unverified.
- Configuration preflight made zero Telegram, Qdrant, and LLM calls. A separate read-only inventory preflight attempted `http://127.0.0.1:6333` and failed with `ResponseHandlingException` / Windows `WinError 10061` (no listener). It performed no writes, no search, and no LLM call.
- Current SHA-256 receipt from `python -m experiments.telegram_source_first_pilot.pilot preflight`:

| File | SHA-256 |
|---|---|
| `experiments/telegram_source_first_pilot/__init__.py` | `f85705cfa6b005d46b26e6cbbe1d07f3709e448543a5da5f997483b2a2a2e291` |
| `experiments/telegram_source_first_pilot/pilot.py` | `73d68556f7926c0fc474c0766405587eb9261e6bf1ef7fd1a128a98991c992ec` |
| `app/dialogue_state.py` | `3d3255ced32534dcf687b8e4ab3e1997a4edd6938e8b8d0d13664c9007b2eeec` |
| `app/response_grounding.py` | `f2d4fa04cc6d0462d7df7ea129363d6fbde74369f56b821b2431dcdbaa135231` |
| `app/retrieval.py` | `9499dd9e665d1eedbc1672aa7d66f4f161beba83ed17312469b029c9335d0b27` |
| `app/embeddings.py` | `a4fedd688d2b08f02f0c0e7efe8c73ae7551f4da9659ecb956b72b9eff3474e6` |
| `experiments/evidence_first_vertical/planner.py` | `ed9829f01ef40a22ce75020cc09c1ecf7d51b94e9b22fb1c21981e5ad2da90ca` |
| `experiments/evidence_first_vertical/prototype.py` | `8808bb1096628c78f32e7c1bab11e47e43db2127def6e31a1ebc09a553ea5b86` |
| `experiments/vnext/stage3_retrieval.py` | `0ec753c308e62ed932c264123a08dc2cb0d9c2090fc093fd95258a39378e8ca1` |

## Local smoke checks

Passed: Python 3.14.3 bytecode compilation and module import; local approved-source index and section parsing; approved/SHA/scope applicability verifier plus altered-SHA rejection; high-risk phrase stop; email/phone/long numeric masking and export timestamp removal; Telegram message splitting; temporary SQLite conversation, message, and queue lifecycle; fail-closed escalation for simulated Qdrant errors and risky requests. Smoke used only a temporary directory and local knowledge files. No persistent pilot database was created by smoke.

## Not established yet

Bot token validity and exclusivity, allowlist behavior through Telegram, Qdrant reachability/inventory (current local endpoint is down), actual Groq responses/usage/error behavior, and task-level answer quality. No quality score is claimed. Before manual testing, start the already configured read-only Qdrant service at the pinned endpoint and rerun `preflight-qdrant`; then supply dedicated credentials and authorize live LLM calls.

The first smoke attempt hit Windows `WinError 32` because a SQLite connection remained open after its context block. The connection lifecycle was corrected, and the final smoke passed. No production DB was involved.

To bootstrap the allowlist without weakening the pilot check, `identify` mode was added. It runs a dedicated token-locked polling process with only `/id`; it does not initialize Qdrant or Groq. It must be stopped before the full pilot process starts.
