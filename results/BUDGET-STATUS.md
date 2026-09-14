# Budget and recovery status

Paid calls remain blocked by `results/PAID-CALLS-BLOCKED`.

## Reconciled accounting

- Verified pre-ablation pilot carry-forward: **$0.067766300 across 324 successful calls**.
- Baseline: 320 calls / **$0.066599100** (2 smoke calls plus 318 subsequent pilot calls).
- Optimized: 2 calls / **$0.000368400**.
- Quality evaluation: 2 calls / **$0.000798800**.
- New calls after recovery: **0**.
- Current measured total and effective exposure: **$0.067766300**.

The aggregate is recorded in `results/historical-spend.json` and is always included by the budget guard in total and phase exposure. `results/spend-total.txt` now reflects it. `results/spend-log.jsonl` intentionally remains empty because no individual historical rows were reconstructed.

The 324 original usage rows and proxy captures were lost during workspace cleanup. This aggregate is the last independently reconciled observation, not per-call evidence and not valid ablation data. The limitation must appear in the final Method section.

## Safeguards verified without paid calls

- Cross-thread and cross-process lock wraps cap checks plus pre-dispatch reservation persistence.
- Unknown-usage failures retain worst-case exposure; retries are capped at three with exponential backoff.
- Historical amounts count toward the $15 soft stop, $20 hard stop, and 150% phase stops.
- Continuing after $15 requires `results/POST-SOFT-STOP-AUTHORIZED`; an environment variable cannot bypass the stop.
- Section 10 phase caps are enforced exactly: baseline $3, optimized $1, quality eval $12, judge $2, and contingency $2.
- Paid cache keys bind condition, scenario hash, endpoint, and payload; a valid atomic cache prevents a repeat even if its action-manifest append was interrupted.
- Proxy request/response capture recursively redacts credentials and records completion latency while marking nonstreaming TTFT unavailable.
- The paid proxy returns HTTP 402 before reservation or upstream dispatch while the blocker exists.
- Pinned-source audit passed for all seven proposed levers.
- Deterministic mock-provider/proxy integration passed.
- Local Ollama deployability smoke passed at $0 for 4 task-shaped calls.
- Frozen workload and targeted 115-case eval fixtures have committed hashes in `eval/manifest.json`.

## Gates still closed

1. The user must explicitly accept use of the aggregate carry-forward while acknowledging that the pilot cannot be audited per call.
2. The full mock path through a pinned Open WebUI runtime, including corpus indexing and cache/resume artifact inspection, must pass.
3. The six-hypothesis source audit found four supported and two already fixed/materially changed. The "more than two fixed" stop rule is not triggered, but wire validation is still outstanding.
4. At most two tiny paid smoke calls may run only after the prior gates and an explicit paid-call go-ahead. The blocker must not be removed merely to test it.

No paid experiment or smoke is currently authorized.
