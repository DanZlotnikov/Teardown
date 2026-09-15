# Open WebUI optimization lever scorecard

## Bottom line

Two settings have evidence strong enough to recommend:

1. Route background task calls to `gpt-5.6-terra`, while leaving the main chat model on `gpt-5.6-sol`.
2. Enable `ENABLE_QUERIES_CACHE` when requests commonly combine web search with attached-file retrieval.

Terra is the strongest general result. Across three repetitions of the identical 32-action hosted sample, task-call cost fell from **$0.296664 to $0.136608**, a **53.95% reduction**. The three individual savings were 53.64%, 54.33%, and 53.89% (population SD 0.29 percentage points). All **96/96** Terra outputs passed deterministic schema checks. On the fully judged first repetition, mean quality moved from 4.417/5 to 4.396/5; the paired delta was -0.021 with a bootstrap 95% CI of -0.156 to +0.104. This passes the preregistered -0.25 noninferiority margin.

Query reuse cut model calls from 24 to 16 across eight real combined web-plus-file requests. Query-generation calls fell from 16 to 8, objective answer quality remained 0.875, and the uncached Sol-priced local projection fell **27.73%**. The main chat calls themselves were not removed or rerouted.

## Grade rubric

- **A:** At least 10% relevant-path savings, quality passes the declared guard, no unresolved structural failure, and the effect is confirmed beyond a single incidental output.
- **B:** Positive and usable, but workload-specific, based on derived rather than hosted dollars, small in the measured workload, or explicitly exchanges a UX feature for cost.
- **C:** Potentially useful only with a guard/fallback, or quality is preserved but dollar savings have not been established.
- **D:** Reject at the tested grade because savings are negligible/negative or observed quality/reliability loss is material.

“Savings per quality point” divides cost reduction by percentage points of measured quality lost, with a 0.1-point denominator floor. It is descriptive, not part of the grade. For the five-point judge scale, score deltas are converted to percentage points by dividing by five. A negative latency delta is faster.

## Ranked results

| Rank | Lever and best tested grade | Cost result | Completion latency | Quality / reliability result | Savings per quality point | Main-chat risk | Grade |
|---:|---|---:|---:|---|---:|:---:|:---:|
| 1 | L1: Terra for background tasks | **53.95% hosted task-call saving**, three-run aggregate | p50 **-18.24%**, p95 **-22.85%** | 96/96 structurally valid; judged delta -0.021/5, CI [-0.156, +0.104], quality guard pass | 129.5 | No | **A** |
| 2 | L5: query reuse on | **33.33% fewer model calls**; **27.73% derived cost saving** on the eight-case combined path | p50 -35.96%; p95 +3.70% | Objective mean 0.875 both off and on | 277.3 | No | **B** |
| 3 | L7: autocomplete off | 0.285% derived full-workload saving with two deliberate events | p50 +0.07%; p95 +0.02% across the whole run | Main answers unchanged; autocomplete UX is removed | n/a: UX tradeoff | No | **B** |
| 4 | L6: retrieval top-k 2 | Downstream dollar saving not measured | No change in current retrieval-only run | Recall 0.9583, identical to top-k 3 | n/a | Yes | **C** |
| 5 | L1: Luna for background tasks | **94.04% hosted task-call saving** | p50 about -23.6%; p95 about -25.7% | Semantic score comparable, but only 31/32 structurally valid | 451.4 semantically; structural guard failed | No | **C** |
| 6 | L2: global task cap 512 | 0.094% derived saving | p50 -6.47%; p95 +0.92% | No objective loss locally | 0.94 | No | **D** |
| 7 | L4: last 10 turns | **0.57% cost increase** | p50 unchanged; p95 +4.44% | Long-context objective 1.00 to 0.95 | negative | **Yes** | **D** |
| 8 | L2: global task cap 128 | 0.51% derived locally; 1.62% hosted on valid subset only | Hosted p50 about -2.8%; p95 about +5.4% | Hosted structure 23/30; only 3/10 follow-ups valid; autocomplete hit HTTP 400 | 0.07 using structural loss | No | **D** |
| 9 | L4: last 6 turns | 1.15% derived saving | p50 unchanged; p95 +2.34% | Long-context objective 1.00 to 0.00 | 0.01 | **Yes** | **D** |
| 10 | L4: last 3 turns | 3.66% derived saving | p50 unchanged; p95 +2.87% | Long-context objective 1.00 to 0.00 | 0.04 | **Yes** | **D** |
| 11 | L2: global task cap 32 | 5.29% derived saving | p50 -55.46%; p95 unchanged | Tag objective 1.00 to 0.70; hosted sweep skipped after cap 128 failed | 0.18 | No | **D** |
| 12 | L6: retrieval top-k 1 | Dollar saving not represented in the current retrieval-only run | No change in current run | Recall 0.9583 to 0.8167 | n/a | **Yes** | **D** |
| 13 | L4: native compaction forced at 256 tokens | **120.64% targeted cost increase** | Combined p50 2346 ms; p95 2614 ms | Triggered 20/20; objective 1.00 to 0.80 | negative | **Yes** | **D** |

The local `qwen2.5:14b-instruct` Q4_K_M condition passed a four-call deployability smoke on Ollama 0.33.3. It is not graded as equivalent to a hosted model because no hosted-quality comparison was run. L3 native title input truncation is not in the table because the proposed token-level control does not exist in the pinned build; the native template counts messages and characters.

## Magnitude curves and knees

| Lever | Increasing optimization magnitude | Observed curve | Knee |
|---|---|---|---|
| L1 model tier | Sol → Terra → Luna | Cost saving 0% → 53.95% → 94.04%. Judged mean remains close, but structural validity changes 100% → 100% → 96.875%. | **Terra.** Luna crosses the reliability boundary. |
| L2 global output cap | none → 512 → 128 → 32 | Derived saving 0% → 0.094% → 0.508% → 5.291%. Local tag score 1.00 → 1.00 → 0.95 → 0.70; hosted cap 128 breaks follow-ups and autocomplete. | **No useful knee.** 512 saves almost nothing; 128 is already unsafe. |
| L4 sliding window | none → 10 → 6 → 3 turns | Saving 0% → -0.574% → 1.145% → 3.656%. Long-context score 1.00 → 0.95 → 0.00 → 0.00. | **None.** The quality cliff arrives before useful savings. |
| L4 native compaction | off → forced at 256 tokens | Targeted saving 0% → -120.64%; objective 1.00 → 0.80. | **Do not force at short-chat thresholds.** Long-chat break-even is unmeasured. |
| L6 retrieval depth | top-k 3 → 2 → 1 | Recall 0.9583 → 0.9583 → 0.8167. Downstream dollars were not measured. | **top-k 2 for a guarded pilot**, not yet a cost claim. |
| L7 autocomplete | on → off | Derived saving 0% → 0.285% in this workload; answer path unchanged; feature removed. | Product decision, not a quality-free optimization. |

## Cost-quality Pareto frontier

- **Conservative:** Query reuse. It has an exact call-count reduction and zero observed objective loss in the tested combined path. Its dollar figure is a local frozen-price projection, so deploy it first where combined web-plus-file requests are common and monitor production call counts.
- **Balanced:** Terra task routing. It delivers the largest well-validated hosted saving, improves measured completion latency, leaves the main-chat model untouched, and passes the semantic guard. This is the recommended default.
- **Aggressive:** Luna behind strict per-endpoint JSON/schema validation with one retry on Terra. The unguarded Luna condition is not on the deployable frontier because it produced a malformed follow-up.
- **Conditional:** Disable autocomplete only if users do not value it. It is a direct request-count saving, not a performance-preserving substitute for the feature.

No combined point is presented as measured. Terra and query reuse affect overlapping query-generation calls, so their percentages must not be added.

## Factorial status

The eight-cell top-three factorial was not run. Only two levers passed a performance-preserving acceptance rule. The next apparent candidate is either autocomplete-off, which removes a UX feature, or retrieval top-k 2, whose downstream dollar effect is unmeasured. Calling either a third “best-scoring” optimization would manufacture a premise the data does not support. In addition, Terra dollars were measured on the hosted task sample while query reuse was isolated on the local combined middleware path. An interaction number from those incompatible denominators would not be reproducible evidence.

The next valid factorial should begin only after a single combined workload can exercise Terra routing, query reuse, and a genuinely accepted third lever under the same provider and pricing path. Until then, deploy the two accepted settings independently and measure production overlap.

## Do not do this

- Do not set a global `max_tokens: 128` or lower for every task endpoint. Reasoning tokens consumed the cap, leaving empty/truncated follow-ups and an autocomplete HTTP 400.
- Do not use Luna across all task endpoints without schema validation and a Terra fallback. Semantic quality was fine, but one malformed response is enough to break UI behavior.
- Do not impose a six- or three-turn window globally. Both erased the early-turn facts in the controlled long-chat checks.
- Do not force native compaction at a short threshold. It added a summary model call to every tested request and more than doubled targeted cost.
- Do not reduce retrieval to top-k 1. Recall fell by 14.17 percentage points.
- Do not add independent savings percentages. Query reuse and task-model routing overlap on query-generation calls.

## Evidence map

- Terra three-run aggregate: `results/runs/l1-mid-hosted-three-repetition-aggregate.json`
- Hosted Sol/Terra/Luna judge: `results/runs/l1-task-model-tier-judge.json`
- Query reuse: `results/runs/l5-query-reuse-on.json`
- Unsafe hosted cap: `results/runs/paid-l2-cap-128-paid-sample.json`
- Local magnitude levels: `results/runs/l2-*.json`, `results/runs/l4-*.json`, `results/runs/l6-*.json`, and `results/runs/l7-autocomplete-off.json`
- Redacted wire captures: `results/raw-proxy-logs/`

Hosted figures are actual provider-token arithmetic at the frozen 2026-09-14 prices. Local figures are wire-observed Ollama tokens repriced at the frozen Sol rates and are explicitly derived, not provider billing. All task endpoints were nonstreaming, so TTFT is unavailable rather than inferred from time to first byte.
