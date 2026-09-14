# Pre-spend source audit: Open WebUI 0.11.3

Pinned upstream commit: `0a7c15832fb30b1903753e83f81dc7d27e5b0944`.
This audit checks that the proposed intervention really exists in the pinned
application before a paid sweep. Existence is distinct from baseline defaults.

| Lever | Finding | Source and consequence |
|---|---|---|
| L1 task model tier | Supported | `backend/open_webui/routers/tasks.py` reads `task.model.default` / `task.model.external`; title, tag, query, follow-up and auto-generation endpoints select the configured task model. Local Ollama is conditional on an installed, smoke-tested model. |
| L2 task output cap | Supported, broader than specified | `task.model.params` flows through `apply_task_model_params` on all of those task endpoints, including title and autocomplete. Report the broader effect; a narrow tag/query-only native knob is not present. |
| L3 title input truncation at N tokens | Unsupported natively | `backend/open_webui/utils/task.py`'s `MESSAGES:START/END` chooses message counts. Its `start:N` and `end:N` truncate per-message *characters*, not tokens. Do not substitute a 200-character setting and claim to have tested 200 tokens. Drop this native token sweep unless an explicitly custom extension is introduced and labeled. |
| L4 context policy | Supported by extension and native compaction | A global filter can implement 10/6/3-turn windows; `backend/open_webui/utils/context_compaction.py` exposes native summarize-and-replace. Unlike other levers, this affects main-chat answers. |
| L5 query reuse | Supported only in middleware | `ENABLE_QUERIES_CACHE` caches generated query results on request state in `backend/open_webui/utils/middleware.py`; the query task endpoint returns that cached value. A standalone repeated `/tasks/queries/completions` call is not a valid test. |
| L6 retrieved chunk count | Supported | `rag.top_k` defaults to three in `backend/open_webui/config.py`; `backend/open_webui/routers/retrieval.py` passes it to collection and document searches. Test 3, 2 and 1 on one frozen corpus. |
| L7 autocomplete | Supported, stock default off | `task.autocomplete.enable` gates `/tasks/auto/completions`. The frontend defaults to a 1000-ms debounce. The study's baseline deliberately enables it and must not present it as stock behavior. |

The exact six hypotheses and stop rule from the recovered brief are reconciled
in `findings/hypothesis-audit.md`. No paid sweep is authorized by either audit.
The missing historical ledger and runtime gate are separate blockers in
`results/BUDGET-STATUS.md`.
