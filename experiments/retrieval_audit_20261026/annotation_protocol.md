# Retrieval audit — annotation protocol

## Dataset

The sanitized archive contains 67 client turns, of which 54 retrieval-eligible message turns were retained after excluding short button/clarification-only inputs and the initial account question that had no confirmed service and therefore should clarify before retrieval. Four short but meaningful Эвотор ФН diagnostic requests (codes 234, 235, and 999) were retained. The 54 rows contain repeated turns from separate real conversations and 45 distinct exact utterances. This is fewer than the requested 60–80, so no synthetic questions were added. The questions were not generated from articles.

## Gold labels

Gold document and answer-bearing section were manually assigned from the approved Stage3 source/section content and sanitized user text before query embeddings or retrieval. A source is gold only when it supports the requested answer at its stated specificity. If approved evidence does not support it, the label is `no_approved_evidence`; that is a knowledge-coverage outcome, not a retrieval miss. Context-bearing follow-ups use the archived state snapshot or deterministic offline replay of archived user/assistant turns. No answer text is added to the query.

A source section may be gold for a documented boundary (for example, FN not confirmed as a direct receipt filter); it does not authorize unsupported steps.

## Retrieval boundary

Pre-filter recall uses current hybrid retrieval over approved points and its existing exact identifier/model guards. The post-filter result is current `RetrievalPipeline` candidate selection over the same candidate pool. Experimental soft ranking changes task-category/operation/unlabeled scores only; it retains approved status and hard-rejects explicit service/manufacturer/model conflicts, exact code/version conflicts, procedure-scope conflicts, and unsafe requests.

No Groq or remote LLM calls are made. Embeddings use the local configured sentence-transformer in Hugging Face offline mode. Qdrant calls are get/count/scroll/query only; no writes or reindexing.
