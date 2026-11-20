# CRM / Smart Navigation v4 integration — 20.11.2026

## Scope and baseline

Explicit owner request starts a separate integration stage and authorizes tested
integration-branch commits/pushes. No main merge/production rollout is authorized.
RAG baseline: local main 7eff20d, three documentation/evidence commits ahead of
origin/main 44763e0. App remains the published baseline. Candidate 3aa1f68 remains
isolated in manual-conversation-review and is NOT incorporated or declared GO.
KB B2 was already merged; use reviewed `knowledge_kb_b2_integrated_20261119`,
204 approved / 65 draft, 833 approved chunks, without reindexing.
CRM original: `C:/Users/Shira/Documents/ChatGPT/CRM_AI/bot_crm_smart`, main
7abb3b8, seven uncommitted client-WebApp edits retained there. Fetch advanced
origin/main to 338f1bb, already including Smart Navigation v4. Integration is
based on that current main, without merging old feature branches.

Integration checkouts:

- RAG: `C:/Users/Shira/.codex/worktrees/crm-rag-api/Rag`.
- CRM: `C:/Users/Shira/Documents/ChatGPT/CRM_AI/crm-rag-integration`.
- Both branches: `codex/crm-rag-integration-20261120`.

The managed-worktree API completed RAG creation. CRM creation stalled without an
operation/result; after cancelling that call, a normal Git linked checkout was
created from origin/main. Original dirty checkout remained untouched.

## Implementation checkpoint (not final acceptance)

`bot.py` and the CRM API share `app/support_turn.py`, which invokes the existing
Understanding, reducer, Coordinator, SourceFirst, Composer and grounding. No copy
of the RAG pipeline, no model-based router, no cart/order/payment tools.
Authenticated `/v1/support/reply` has typed versioned input, case/message keys,
optimistic revision, durable SQLite request/response receipts, replay/conflict
handling and a separate acknowledgement after durable CRM publication. State
stays server-side. Raw retrieval top-k is not confirmed source evidence.
Crash/timeout produces an explicit error; ambiguous paid generation is not
silently repeated. The API is a single process on persistent private SQLite.

CRM RagAIWorker reuses attempts, case revisions, native assistant messages and
the delivery outbox. It bypasses the legacy local KB/3-turn/lexical-confidence
gates only for the full RAG service, whose own grounding remains enforced.
Migration 0008 stores durable service requests/results/acks. Publication checks
both current case revision and worker lease under the chat lock. Human takeover
rejects stale answers. Acknowledgements recover after restart. Feature flag
defaults off. Safe display-only shop routes can leave an active support UI;
the existing case remains available for return. No purchase is executed by text.

## Negative attempts retained

1. First API startup loaded general .env without the manual SourceFirst process
   profile. HTTP200 contained `status=error`, NOT a successful AI reply. Separate
   service profile fixed configuration; original .env/worker were untouched.
2. First MySQL bootstrap used Windows default text encoding, failed before full
   schema creation; subsequent migration encountered missing referenced tables.
3. Second bootstrap lacked MySQL permission to create triggers with binary log.
   Both partial, isolated schemas were retained. Local container prerequisite
   `log_bin_trust_function_creators=1`, UTF-8 and a new empty schema completed
   66 tables / 4 triggers, followed by support migrations and 0008.
4. First broad MySQL suite shared a synthetic DB with the active demo worker.
   It consumed fixtures; early cleanup did not know the new receipt FK. That
   run is contaminated and is NOT regression evidence. Dedicated `crm_rag_ci`
   now has no service worker; `crm_rag_demo` is separate for LIVE/manual use.
5. An intermediate worker-helper extraction had an indentation error; collection
   caught it, it was corrected before final LIVE. A case-mode change raises
   AccessDenied as well as Conflict; the adapter now classifies both as stale.

## Checks so far

- Initial RAG full: 924 passed / 14 failed / 4 xfailed. Three environment/fixture
  issues fixed with UTF-8 and the existing ignored synthetic fixture; repeat
  927 / 11 / 4. Ten are known baseline ledger tests; eleventh was absent optional
  LangGraph target directory in the new checkout. Existing versioned dependency
  directory via PYTHONPATH makes that isolated test pass. Final repeat pending.
- Initial CRM unit: 386 / 5 failures. One new missing-attribute regression fixed;
  explicit offline dummy BOT_TOKEN fixes two import-only tests. Repeat 389 / 2
  failures: Windows chmod semantics and symlink privilege, not integration logic.
- New API offline boundary tests: 5 passed. New CRM routing/client tests: 11 passed.
- Real service call: HTTP200, `answered`, Hubris `openai/gpt-oss-20b`, 13.688s.
  General explanation has no approved citations and is labelled accordingly.
  This one reply does not establish general factual quality.

Exact LIVE replies, final test counts, process receipts and publication status
will be appended after the in-progress runs. Existing RAG production NO-GO,
Part A REVISE/A6 STOP remain. Full Telegram/MAX transport needs a confirmed
dedicated test token; no second polling process was launched.

## Final implementation and verification

The owner subsequently explicitly instructed using the same previous RAG bot
token for this combined pilot. That supersedes the initial separate-test-token
restriction for this local pilot only. With zero pending turns, both original
SQLite files were backed up and old worker3232/launcher13568 stopped. The full
CRM bot now reads that token directly from the unchanged original private env;
there is one polling loop. A local-only pilot guard uses the previous private
tester allowlist, synthetic equipment, and disabled checkout. It does not forge
registration/consent records. Native full-text delivery is enabled; local HTTP
WebApp links are omitted from Telegram/MAX buttons. `getMe`, `deleteWebhook`
and repeated `getUpdates` returned200. These are transport-startup checks;
owner-originated Telegram end-to-end replies are not inferred from empty polls.

Local API8091, CRM support8092, isolated MySQL3307 and existing Qdrant are real
running processes/services. Startup and current process evidence are recorded
separately below. Existing RAG main app37/37 source hashes still match its old
receipt; every legacy SQLite table matches the backup, including48 messages.
[Preservation check](legacy_preserved.json), [KB exact match](kb_and_legacy_backup.json).
The candidate remains isolated and unchanged. New API state and CRM history are
separate; historical manual dialogs were not silently imported into new cases.

### Results and practical limits

| Check | Result | Limit |
|---|---|---|
| Full RAG, UTF-8, original optional versioned dependencies/fixture | 931 passed / same10 known failed /4 xfailed | No new failure; not a green quality/production suite |
| API/security/replay/timeout/source contracts | 8 API tests pass; combined provider/network profile23 pass | Offline generation fixtures prove boundaries only |
| CRM Windows units, pilot included | 409 passed /2 unchanged platform failures;38 subtests | chmod bits and symlink privilege; neither test rewritten/hidden |
| Clean MySQL suite before last recovery extension |126 passed;10 subtests | Separate CI schema; no background worker |
| Additional post-publication crash + takeover recovery |5 targeted MySQL tests pass | Includes new crash regression and four prior boundary tests |
| Actual classifier, both platforms, empty catalog |20/20 expected routes | Honest empty-catalog choices, not proof of stock |
| Actual classifier after synthetic catalog seed |20/20 expected routes | Test equipment only; no real purchase/payment |
| CRM native HTTP six-turn LIVE |All6 inputs persisted; duplicate key reused same native message ID for every turn | Conversation quality below |
| Real client read-timeout |Client timed out; two409 in-progress; same stored HTTP200 reply after completion | No blind paid retry; greeting answer itself is deterministic |
| API restart replay |Earlier real response returned structurally identical JSON | Persisted state reused; no new model generation for that key |
| Independent technical LIVE on final source filter |answered; Hubris20B; exact_source_copy; exactly1 approved document | One useful result does not establish stability |
| Compose |`docker compose ... config --quiet` passes | Host deployment tested; container image build/server rollout not performed |

Final full MySQL repeat after the added crash recovery is recorded in the final
runtime/publication appendix. [Raw RAG summary](rag_full.txt),
[Windows units](crm_unit_windows.txt), [MySQL](crm_mysql.txt),
[routing before fix](routing_before_fix.json), [empty](routing_empty_catalog.json),
[seeded](routing_seeded_catalog.json).

Six-turn CRM answers are literal in [answers.md](answers.md) and
[live_crm.json](live_crm.json). Conceptual OFD answer10.250s is useful. The follow-up
«А чем он отличается от ФН?»10.375s incorrectly explains online cash register vs
FN: **quality FAIL**, despite `answered`. Initial technical20.890s starts with a
conditional branch «Если “Есть”» without establishing its prerequisite:
**PARTIAL/poor first step**. Memory turn12.344s asks about another source condition;
it does not establish useful continuation. Human request0.750s creates no AI
attempt and moves the same native case to queue. Unsafe archive request6.047s
returns a safe refusal and queue, no destructive instructions. No actual employee
acceptance/delivery is claimed.

Independent final phrasing returned:

> Перейдите в **личный кабинет оператора ОФД** и проверьте статус подписки. При необходимости обратитесь в службу поддержки ОФД.

with the approved Evotor7.3 source and a single confirmed document ID.
[Complete request/response](final_independent_live.json). A separate Platforma OFD
lookup [asked for sales/report/date clarification](final_source_live.json);
it was not relabelled as a useful procedure. Model-only factual safety remains
the preexisting open issue; this integration did not adopt the rejected candidate.

### Additional diagnosed/fixed integration issues

- The first source adapter exposed all approved retrieval candidates. That was
  overbroad attribution, not confirmation. Final output uses only selected/final
  cited approved documents and deduplicates by document ID. Regression and real
  independent source response verify this; old immutable receipts are retained.
- Empty-catalog read-only routing found «не отправляет» and «Нужен специалист»
  could become product search/clarification, and active support could swallow an
  empty-stock purchase request. Existing v3/v4 mechanisms were extended generally:
  negative transfer predicates, procedure questions, existing explicit-human
  detector, and safe catalog choices in active support. No phrase-specific LLM
  prompts or second router were added.
- An installed Qdrant client does not support context-manager syntax. A read-only
  check caught that mistake; explicit close replaced it, authenticated readyz200
  was then verified. API startup/runtime now refuse missing/empty collections
  rather than creating an unreviewed index.
- PTB forbids setting a custom HTTP request after builder timeouts. Startup
  construction caught it before the final poller; pilot/normal builder branches
  are now separate. Native endpoint/status-only telemetry avoids token URLs.
- One intermediate API process was observed no longer listening without a
  shutdown/error receipt. Cause is unproven; it was restarted, readiness and
  cached-response replay verified. No invented cause or uptime guarantee.
- Crash after native message commit, followed by human takeover, can make an
  attempt stale before final attempt bookkeeping. Reconciliation now finds the
  deterministic published origin, acknowledges it and avoids false discard or
  duplicate publication. The dedicated real-MySQL crash regression passes.

## Accepted decisions / remaining work

Local integration pilot is available for owner testing, with the same authorized
bot and isolated data. Overall production/quality remains **NO-GO**. No main
merge, force push, KB rewrite, real order/payment or real customer-case mutation.
Real specialist acceptance, MAX transport and broad useful dialogue remain open.
The next concrete step is the owner's fourteen-message test from
[CRM_INTEGRATION.md](../../docs/CRM_INTEGRATION.md), then evidence-based triage of
those outcomes; underlying OFD context/atomic Evotor checks remain separate
quality work. Full green gates are absent, so no ready PR is created or merged.


## Final test closeout

Final clean full MySQL after the recovery extension: **127 passed /10 subtests**.
Final CRM Windows: **409 passed /2 unchanged platform failures /38 subtests**.
Final full RAG: **931 passed /same10 failed /4 xfailed**. The two Windows failures
are unchanged tests from the CRM base, not skipped or rewritten. Native pilot
startup construction passes; repeated endpoint/status-only Telegram polling
receipts are real HTTP200. Ready PR/full production acceptance conditions are
not met because baseline quality/tests and specialist/MAX gates remain open.
[All MySQL](crm_mysql.txt), [crash recovery](crm_recovery.txt),
[Windows](crm_unit_windows.txt), [RAG](rag_full.txt).


## Published branches and final runtime identity

Both branches published with normal pushes; remote refs independently checked.
RAG application [4e16bcc](https://github.com/Shira-Artem/Support-RAG-Bot/commit/4e16bcc25f8637b413bc84f81df2ed3eeb904dd3).
CRM implementation [0edccec](https://github.com/qazya1/bot_crm_smart/commit/0edccec188b0fdb41bda10fe790140c8bd5c9097),
verified native-channel follow-up [d5f4c70](https://github.com/qazya1/bot_crm_smart/commit/d5f4c707c873b8ec217d27673ac5e6ff68509021).
Channel follow-up: legacy AI + RAG targeted MySQL15 passed; explicit native-channel
publication/recovery test1 passed. The final full MySQL127 and RAG931/same10/4
results remain distinct from these targeted follow-ups. All commits are on
`codex/crm-rag-integration-20261120`, not main. No PR: owner required a fully
passing suite/no blocking risks, and those conditions are not met.

[Final runtime receipt](runtime_final.json): API7560 on4e16bcc, CRM support18592
and single polling worker13840 on d5f4c70; all42 API /72 CRM source hashes match.
API authenticated readyz200, CRM health200, RAG and native delivery enabled.
Repeated getUpdates200 after start. Old RAG poller stopped. Owner input/sendMessage
was not observed in this captured receipt; manual Telegram acceptance remains
pending, not assumed successful. Same-token pilot is available at the familiar
bot; `/start` opens the CRM menu. Checkout disabled. Original main refs remain
RAG44763e0 remote (local main7eff20d), CRM338f1bb remote (original dirty local
main7abb3b8). Original seven dirty files and historical candidate remain intact.

The one-command launcher was executed and re-executed idempotently against the
prepared services. Code/docs whitespace check passes; verbatim answer/terminal
artifacts retain original trailing spaces. No secrets/private SQLite/env files
were staged; staged contents were checked against the actual private secret
values before publishing. [Changed files and local paths](changed_files.json).
This final evidence/documentation commit does not change runtime app code.


Prepared-workstation launcher also resumes the existing `rag-qdrant-1`, needed
following a workstation reboot; repeated execution leaves healthy processes
unchanged. Read-only financial-table check in the isolated demo found0 orders
and0 support_chat_payments. An initial diagnostic query used a nonexistent
`payments` table name and was corrected using information_schema; no schema/data
mutation or fictional successful result was inferred from that failed query.
