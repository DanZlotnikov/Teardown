# 11. Experimental method — controlled ablation

This is not a single bundled before/after. Every lever must be measured
independently at multiple magnitudes against one frozen scenario, with cost,
latency, quality, and main-path risk reported separately. The final result is a
graded lever scale, not one headline saving.

## 11.1 Controls

- Commit one scripted workload and run byte-identical inputs in the same order
  for each condition. If the fixture changes, rerun all earlier conditions.
- Set task and eval temperature to 0 where supported; run a nondeterministic
  condition three times and report its mean and spread.
- Change exactly one variable per single-lever run; retain the same model family
  except when model tier itself is the lever.
- Save `results/runs/<condition-id>.json` with the complete diff from baseline,
  raw proxy request/response capture, token counts, cost computed from frozen
  pricing, wall-clock p50/p95 time to first token and completion, and affected
  eval results.
- Record the same Open WebUI commit, pricing snapshot, and eval-set hashes in
  every run.

## 11.2 Single-lever sweeps

Confirm each lever exists in the pinned Open WebUI version before building its
sweep; if unsupported, state why and drop it.

| Lever | Baseline and levels | Affected calls |
|---|---|---|
| L1 task tier | Chat model / mid-tier hosted / small hosted / local via Ollama | Title, tag, RAG query, web query, autocomplete |
| L2 task output cap | None / 512 / 128 / 32 max tokens | Tag, follow-up, search query; check actual configuration scope |
| L3 title input truncation | Full / first 2000 / 500 / 200 tokens | Title only |
| L4 context policy | None / sliding 10 / 6 / 3 turns / summarize-and-replace | Main-model multi-turn chat |
| L5 query reuse | Off / on | RAG and web-query generation |
| L6 retrieved chunks | Default / two smaller settings | Main-model grounding and input |
| L7 autocomplete | On / off | Autocomplete UX and cost |

That is approximately twenty single-lever conditions plus the baseline,
subject to the source-existence audit.

## 11.3 Interactions

Rank single levers by measured savings. Take the top three at their best-scoring
settings and run all eight full-factorial combinations. Report the interaction
term: sum of individual savings minus measured combined saving. If its absolute
gap exceeds 15% of predicted savings, investigate the overlapping payload
mechanism. Do not run a 128-condition all-lever factorial.

## 11.4 Metrics and grading

For every condition: total scenario cost, cost per conversation at `config.yaml`
rates, p50/p95 time to first token and completion, quality agreement versus
baseline on affected call types, and a separate yes/no main-chat-path risk flag.

Savings per quality point lost is percent cost reduction divided by percentage
points of agreement lost, with the denominator floored at 0.1. State the A–D
grading rubric explicitly so readers can re-grade from the raw numbers.

## 11.5 Affordable targeted evaluation

- L1/L2: real short title, tag, and query outputs; exact metrics or a fast
  non-reasoning judge. L3: title-only eval.
- L5/L6: objective retrieval overlap and grounding; no judge where avoidable.
- L4: dedicated long multi-turn answer eval requiring early-turn facts. This
  main-chat risk receives the largest eval allocation.
- L7: no answer-quality eval; report the UX tradeoff explicitly.
- Token-count scenario payloads with cheap models and price arithmetically at
  the pinned rate snapshot. Cache all paid eval outputs. Smoke test before bulk
  requests. Apply the continuation-instruction override to section 10: a $23
  soft stop and $30 hard stop, with the phase caps frozen in `config.yaml`.

## 11.6 Deliverable: `results/lever-scorecard.md`

Include a ranked row for each lever at its best setting: saving, latency delta,
quality delta, savings per quality point, main-path risk, and A–D grade. Plot
the magnitude curve for every supported lever and identify its knee. Compute a
cost/quality Pareto frontier and recommend conservative (zero measured loss),
balanced, and aggressive configurations. Add specific “do not do this” settings
with their observed failure modes.

## 11.7 Writeup and uncertainty

The findings section becomes ablation results, and its summary becomes the
scorecard. Add magnitude curves as figures. Disclose run counts, controls,
repeat variance, methodological limits, unsupported levels, and what was not
isolated. If an effect is within run-to-run noise, say so.

## Source audit before payment

In Open WebUI 0.11.3, L3's built-in prompt syntax counts characters and
messages, not tokens. The proposed token-based L3 levels are therefore
unsupported without a custom extension and cannot be presented as native
settings. L5 query reuse operates in combined chat middleware, not in an
isolated task-endpoint replay. L2's global task parameters also affect titles
and autocomplete, beyond the narrower proposed call list. L7 is off in stock
Open WebUI; its on baseline is an explicit experimental choice.
