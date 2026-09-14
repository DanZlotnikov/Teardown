# Open WebUI cost-bearing call graph

Pinned source: Open WebUI 0.11.3 at commit [`0a7c158`](https://github.com/open-webui/open-webui/tree/0a7c15832fb30b1903753e83f81dc7d27e5b0944). Line-level evidence is machine-checked in `results/source-audit.json`.

## Main chat and background tasks

```text
browser chat input
  ├─ main chat ──> combined chat middleware ──> provider completion
  │                  ├─ optional web-query generation (task model)
  │                  ├─ optional file/RAG-query generation (task model)
  │                  ├─ retrieval (rag.top_k chunks)
  │                  └─ native context compaction (optional summary call)
  └─ background task endpoints
                     ├─ title
                     ├─ tags
                     ├─ follow-ups
                     ├─ RAG/web queries
                     └─ autocomplete
                          └─ all select task.model.* and apply task.model.params
```

The task router loads `task.model.default`, `task.model.external`, and the single global `task.model.params` dictionary, then applies those parameters to title, follow-up, tag, query, and autocomplete payloads. Consequently L2 is not a narrow tag/query-only switch.

## Lever-specific paths

- **L1 task tier:** task endpoints select the configured task model before calling the same provider-generation path. Local Ollama is a genuinely distinct deployment condition, not hosted-model evidence.
- **L2 task output cap:** `task.model.params` reaches title and autocomplete as well as follow-ups, tags, and queries.
- **L3 title truncation:** `MESSAGES:START/END:N` selects a number of messages; the optional `start/end/middletruncate:N` content filter limits characters in each message. There is no native token-count title sweep.
- **L4 context:** combined chat middleware invokes native context compaction only for saved chats with message IDs. It defaults disabled with an 80,000-token threshold, so an experiment must lower the threshold enough to prove it triggered. Sliding turn windows remain an installable filter condition.
- **L5 query reuse:** the legacy combined chat path performs web search before file/RAG handling on the same request. With `ENABLE_QUERIES_CACHE`, web-generated queries are stored on `request.state.cached_queries`; the query task router returns them to the later retrieval path. Standalone endpoint replay cannot exercise this reuse.
- **L6 chunks:** `rag.top_k` defaults to 3 and is passed to document and collection retrieval unless a request-level `k` overrides it. A valid experiment needs one fixed indexed corpus and the real retrieval endpoints.
- **L7 autocomplete:** server feature default off + user preference default off. When both are enabled, the editor waits 1,000 ms after input and checks cursor/loading state before dispatch; it is not a call on every keystroke.

## Latency interpretation

The inspected task endpoints construct `stream: false` payloads. For those calls, the proxy records completion latency and marks time to first token unavailable. Any separate streaming calibration must remain clearly distinct from task-endpoint TTFT.

## Source-gate result

The original brief is now preserved and hashed. Its six hypotheses were audited: four remain supported and two are already fixed or materially changed. Because the stop rule triggers only when more than two are fixed, source inspection permits the study to continue. These are source findings only; wire validation remains mandatory.

