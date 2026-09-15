# Interim optimization scorecard

> Superseded by `results/lever-scorecard.md`. The figures below are preserved as the auditable core-evidence milestone before repeatability runs.

## Decision summary

The first reliable deployment recommendation is to route Open WebUI background task calls to `gpt-5.6-terra` while leaving the main chat model unchanged. On the frozen 32-action hosted sample, Terra reduced measured task cost from **$0.098888 to $0.045848 (53.64%)**, produced structurally valid output on **32/32** actions, and passed the paired quality guard.

`gpt-5.6-luna` cut the same sample cost by **94.04%** and its blind semantic scores were statistically comparable to baseline, but one of 32 outputs was malformed. It is therefore not reliable enough as a blanket replacement without schema validation plus retry/fallback.

The global output-cap and context-pruning settings tested so far should not be deployed for savings. Their modest savings were coupled to broken task output or severe context loss.

## Results

| Lever and grade | Cost result | Performance result | Decision |
|---|---:|---|---|
| L1: Terra for task calls | **53.64% hosted saving** on 32 paired actions | 32/32 structurally valid. Blind judge mean delta vs Sol: -0.021/5; paired bootstrap 95% CI -0.156 to +0.104, inside the -0.25 noninferiority margin. | **Deploy candidate.** Keep Sol for main chat; use Terra for title, tags, follow-ups, search/retrieval queries, and autocomplete. |
| L1: Luna for task calls | **94.04% hosted saving** | Blind judge mean delta -0.010/5; CI -0.135 to +0.115. One malformed follow-up made structural validity 31/32 (96.875%). | Do not use as an unguarded blanket replacement. Consider endpoint-specific use only with JSON validation and Terra fallback. |
| L2: global cap 512 | 0.094% derived local saving | No measured objective loss. | Not worth the operational change. |
| L2: global cap 128 | 1.62% hosted saving on the 30 valid paired outputs; 0.51% in the full local projection | Only 3/10 hosted follow-ups were structurally valid; the first autocomplete returned HTTP 400 because the model could not finish. One action was left unattempted. | **Reject.** Open WebUI applies this cap to all task endpoints, so the autocomplete/follow-up failure cannot be isolated by configuration. |
| L2: global cap 32 | 5.29% derived local saving | Tag objective score fell from 1.00 to 0.70. Hosted run skipped after cap 128 was already disqualified. | **Reject.** Strictly more aggressive than a failed grade. |
| L4: last 10 turns | **0.57% cost increase** locally | Long-context objective fell from 1.00 to 0.95. | Reject. |
| L4: last 6 turns | 1.15% derived local saving | Long-context objective fell from 1.00 to 0.00. | **Reject.** |
| L4: last 3 turns | 3.66% derived local saving | Long-context objective fell from 1.00 to 0.00. | **Reject.** |
| L4: native compaction forced at 256 tokens | **120.64% targeted cost increase** because each request added a summary call | 20/20 compaction triggers verified; objective fell from 1.00 to 0.80. | Reject at this threshold/workload. Very long-chat break-even remains unmeasured. |
| L6: retrieval top-k 2 | Downstream hosted dollar saving not yet measured | Mean retrieval recall stayed 0.9583, equal to top-k 3. | Promising, but do not claim savings until downstream grounded-chat tokens are measured. |
| L6: retrieval top-k 1 | No saving represented in the current retrieval-only cost model | Mean recall fell from 0.9583 to 0.8167. | Reject. |
| L7: autocomplete off | 0.285% derived saving in the deliberate two-event workload | No main-answer quality path is affected, but the UX feature disappears. | Safe only where autocomplete is not wanted; savings scale directly with actual event frequency. |
| L5: query reuse | **33.33% fewer model calls** and **27.73% lower uncached Sol-priced projection** on eight combined web-plus-file requests | Objective mean was unchanged at 0.875. Query generation fell from 16 calls to 8 while all 8 final grounded-chat calls remained. | **Deploy candidate** for workloads that commonly combine web search and attached-file retrieval. |

## Quality method

The L1 result uses a frozen, model-independent sample of 10 follow-up, 6 title, 6 tag, 4 retrieval-query, 4 web-query, and 2 autocomplete actions. All outputs came through the pinned Open WebUI 0.11.3 HTTP paths. Cost uses recorded provider token usage and the frozen price snapshot.

The semantic check used 32 action-level, three-way blinded judgments with label order rotated by action ID. Each output was scored 1-5 for task compliance, topical relevance, and usefulness. A candidate passed only when the paired bootstrap lower bound was at least -0.25 on the five-point scale and every output passed deterministic schema validation.

Local dollar figures are counterfactual projections: recorded Ollama tokens priced at the frozen Sol rates. They screen levers but are not presented as provider bills. Nonstreaming calls do not expose TTFT.

## Evidence and spend

- Hosted model-tier costs and structures: `results/runs/l1-mid-hosted-paid-sample.json`, `results/runs/l1-small-hosted-paid-sample.json`
- Blinded L1 quality: `results/runs/l1-task-model-tier-judge.json`
- Stopped hosted cap-128 condition: `results/runs/paid-l2-cap-128-paid-sample.json`
- Real combined-path query reuse: `results/runs/l5-query-reuse-on.json`
- Local single-lever summaries: `results/runs/*.json`
- Raw provider captures and cached outputs: `results/raw-proxy-logs/`, `results/actions/`, `results/cache/`
- Measured project spend at this milestone: **$1.154566200**
- Effective exposure including unresolved worst-case reservations: **$1.187398200**
- Budget controls still active: **$23 soft stop, $30 hard stop**, plus phase caps.
