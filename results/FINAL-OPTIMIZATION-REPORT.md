# Final optimization decision report

## Recommended configuration

Deploy these two changes first:

1. Set Open WebUI's task model to `gpt-5.6-terra`; retain `gpt-5.6-sol` for the main chat path.
2. Set `ENABLE_QUERIES_CACHE=True` for deployments that commonly combine web search and attached-file retrieval.

The Terra result is reliable: **53.95% lower background-task cost** over three identical hosted repetitions, only 0.29 percentage points of run-to-run saving variation, **96/96 valid outputs**, and a blinded quality result that passes the predeclared noninferiority guard. Completion latency improved from 3679 ms to 3008 ms at p50 and from 5618 ms to 4334 ms at p95 in the pooled paired samples.

Query reuse is narrower but clean: **33.33% fewer model calls**, **50% fewer query-generation calls**, and **27.73% lower derived cost** on eight combined web-plus-file requests, with the same 0.875 objective answer score. Its p50 request completion improved 35.96%; p95 was 3.70% slower because of one tail case.

Do not add the two saving percentages. Both can affect query-generation cost, and their combined interaction has not been measured on one common hosted workload.

## Expected practical impact

In the frozen 30-conversation baseline, background generation represented $0.727924 of the $2.214320 Sol-priced projection, or 32.87%. Applying the measured Terra task-call reduction to that component gives a **derived**, not directly billed, whole-workload projection of $1.821591 instead of $2.214320: **17.74% lower overall** and $0.06072 instead of $0.07381 per conversation. Production impact will depend on how often titles, tags, follow-ups, queries, and autocomplete run.

Query reuse adds workload-specific savings when both web search and file retrieval are active in the same turn. It has no effect on chats that do not exercise that combined path.

Autocomplete-off is safe for answer quality but removes autocomplete itself. In this scenario it saved only 0.285%, so it should be a product preference, not a default cost recommendation.

## Rejected settings

- Global task output caps: 512 saved almost nothing. At 128, hosted structural validity fell to 23/30 and autocomplete returned HTTP 400. At 32, the local tag score fell from 1.00 to 0.70.
- Short sliding context windows: 10 turns increased cost slightly and reduced the long-context score; 6 and 3 turns drove that score to zero.
- Aggressive native compaction: at the forced 256-token threshold it triggered 20/20 times, raised targeted cost 120.64%, and reduced objective score from 1.00 to 0.80.
- Retrieval top-k 1: mean recall fell from 0.9583 to 0.8167.
- Unguarded Luna task routing: cost fell 94.04% and semantic quality was comparable, but one of 32 responses was malformed. Use only with schema validation and Terra fallback.

Retrieval top-k 2 preserved recall at 0.9583, but downstream hosted dollar savings were not measured, so it remains a monitored pilot rather than a saving claim.

## Evidence strength and limits

The frozen paid task sample contains 10 follow-up, 6 title, 6 tag, 4 retrieval-query, 4 web-query, and 2 autocomplete actions. Terra ran three times on these same 32 actions. The first repetition received 32 action-level blinded judgments from `gpt-4o-2024-11-20`; the two later repetitions establish cost, output-structure, and latency repeatability. Semantic judging was not repeated for runs 2 and 3.

The query-reuse test used the real pinned Open WebUI combined middleware route. File retrieval and final grounded answers executed normally. The web-search handler generated its query, but the external search engine was intentionally unconfigured, so the result isolates duplicate model-call removal rather than search-provider behavior.

The local matrix used `qwen2.5:14b-instruct` Q4_K_M through Ollama 0.33.3. Local token totals priced at Sol rates are counterfactual cost projections. They are useful for lever screening but are not hosted bills. Nonstreaming task calls do not expose TTFT; the report gives completion latency only.

The original top-three eight-cell factorial was not run because only two levers met the performance-preserving acceptance rule, and those two currently use different hosted/local measurement paths. The detailed scorecard explains why inventing a third accepted lever or an interaction number would be misleading.

## Spend audit

- Historical pre-ablation carry-forward: **$0.067766300**, 324 successful calls. Its individual rows were lost and it is a budget debit only, not benchmark evidence.
- Reconciled measured total: **$1.245326200**.
- Fresh measured spend represented in the current ledger: **$1.177559900**.
- Successful fresh calls: **309**.
- Conservative effective exposure: **$1.278158200**.
- Unresolved worst-case reservations: **$0.032832000** across three disclosed unknown-usage failures.
- Active limits at completion: **$23 soft stop; $30 hard stop**. No limit was approached.

The full graded table, magnitude curves, Pareto recommendations, failure modes, and evidence paths are in `results/lever-scorecard.md`.
