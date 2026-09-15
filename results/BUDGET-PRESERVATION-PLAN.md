# Budget-preservation plan

## Position at the redesign stop

- Measured total including historical carry-forward: `$0.913586300`.
- Unknown-usage worst-case reservations retained: `$0.026148000`.
- Effective exposure: `$0.939734300`.
- Paid baseline evidence frozen: 108 valid cached Open WebUI action results across 43 main-chat, 43 follow-up, 11 title, and 11 tag calls.
- One additional successful provider response settled after the runner was stopped and is not yet represented in the action manifest. It must be recovered or excluded; it must not be silently repurchased.

## Enforced preservation gate

Until `results/CORE-EVIDENCE-COMPLETE` exists, `BudgetGuard` rejects any request whose reservation could take effective exposure above `$3.00`. The marker may be created only after an interim table documents at least three useful single-lever conclusions with cost and quality evidence.

This leaves at least `$17.00` below the hard cap when the core decision evidence is complete. The existing `$15.00` soft stop remains independently active.

## Reduced paid design

1. Do not complete the 329-call hosted baseline. Use the already-cached baseline plus only the ten missing actions in the frozen task sample.
2. Use `scenario/paid-sample-task-32.json` for paired task comparisons:
   - 10 follow-up calls;
   - 6 title calls;
   - 6 tag calls;
   - 4 retrieval-query calls;
   - 4 web-query calls;
   - 2 autocomplete calls.
3. Test only the two informative L2 output caps (`128` and `32`) on that sample. The local matrix already supplies the `512` curve point.
4. Test L1 only at Terra and Luna on the same sample. Local Qwen is already measured without API spend.
5. Use `scenario/paid-sample-context-8.json` only for the best local L4 context setting, not every hosted L4 level.
6. Complete L5, L6, and L7 primarily through real local Open WebUI paths. L7-off requires no replacement model calls and L6 retrieval is local.
7. Produce the interim ranking before authorizing more provider work. Spend afterward only on targeted repeats, ambiguous quality judging, and a reduced factorial of the actual top three levers.

## Stop conditions

- Stop a condition when its paired sample cannot change the practical recommendation.
- Do not buy more baseline calls merely to fill the original workload.
- Do not create `CORE-EVIDENCE-COMPLETE` from derived cost alone; at least one hosted paired comparison and the real local affected-path evaluations must be present.
- Reconcile and secrets-scan before every paid checkpoint push.
