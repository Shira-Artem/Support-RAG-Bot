# Retrieval pipeline

`app.retrieval_pipeline.RetrievalPipeline` is the task-aware search and evidence gate. It accepts a `DialogueState` and a bounded query, asks a candidate source for hybrid search results, checks the selected entities and task family, checks the operation, ranks only eligible articles, expands useful sections, and returns a `RetrievalResult` with context and diagnostics.

The component does not depend on Telegram, SQLite, or the LLM provider. Its candidate source follows this small interface:

```python
class CandidateSource(Protocol):
    def search(self, query: str, top_k: int = 5) -> list[SearchResult]: ...
```

An optional `article(document_id)` method supplies sibling chunks after the document passes service and task checks. Each chunk keeps its own source, section, status, and retrieval score. Sibling chunks have no borrowed score. The pipeline caps output at five articles and 7,000 context characters.

The Qdrant adapter normalizes current front-matter fields at read time into `service`, `task_category`, `operation`, `manufacturer`, `model`, and `status`. This view is derived from existing payload fields and source paths; it does not change the collection. Manufacturer, model, cloud service, and OFD remain separate state dimensions. If an entity or operation is not supported by a candidate's metadata or text, that candidate is excluded from the evidence context.

`RetrievalResult.sufficient` is a relevance gate, not proof that the answer is correct. It requires an eligible candidate in the requested task family and operation with an adequate relevance score. Unsupported technical requests are stopped before generation with `insufficient_evidence`. The answer validator remains a separate layer.

## Current index policy

The configured local `knowledge_demo` collection contains draft documents. Demo mode continues to allow drafts; every diagnostic lists the source status. Non-demo `Retriever` behavior continues to require `approved`. No production collection is created or rewritten by this pipeline. Metadata changes that require indexing should be tested later in a separate collection and promoted only by an operator.

## Telegram diagnostics

The complete `Answer` diagnostic is already persisted with each assistant message, including the structured task, confirmed entities, RAG query, candidate and rejection lists, selected context, raw model response, and validation result. After manually testing the Telegram bot, view recent turns with:

```powershell
python scripts/show_last_conversation.py
python scripts/show_last_conversation.py --turns 5 --context
```

The viewer opens `data/conversations.sqlite3` in read-only mode. Use `--conversation ID` to select a particular chat. No separate test UI or LLM call is involved.

## Future CRM integration

The CRM can construct or receive a `DialogueState`, call `build_rag_query(state)`, and pass both to `RetrieverRAGAdapter.search_for_state(state, query)`. It can supply another `CandidateSource` implementation over its preferred vector database and persistence layer. Keep conversation writes, authorization, tenant isolation, and provider calls in the host application; this component only ranks and returns evidence. Before production, replace broad read-time metadata derivation with reviewed metadata at ingestion and validate calibrated sufficiency thresholds against approved knowledge sources.
