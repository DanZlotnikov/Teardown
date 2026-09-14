# Budget and recovery status

Paid calls are blocked in `analysis/budget.py` until this recovery is resolved.

## Last independently verified state

The previous turn read `results/spend-total.txt` and reconciled the then-existing
324-record ledger at **$0.067766300**. By phase: baseline 320 successful calls,
$0.066599100; optimized 2 calls, $0.000368400; quality evaluation 2 calls,
$0.000798800. The baseline count comprised 2 smoke calls and 318 additional
paid POSTs. This is the last verified accounting observation, **not** a newly
computed value and not an estimate.

On 2026-09-13 a workspace cleanup restored the project to Git checkpoint
`084e389`. The current `spend-log.jsonl` contains zero records, and the current
`spend-total.txt` misleadingly reads $0.000000000. Those current files do not
represent total task spending. Paid-call captures and 324 individual usage
records could not be found in the surviving workspace, Git history, or local
checkpoint archive. They must not be silently reconstructed or represented as
an auditable per-call log.

## Status

- Actual cumulative spend already incurred: **$0.067766300**, verified before
  loss, including pilot calls.
- $23 soft stop and $30 hard stop still apply to the **entire task**, including
  this historical spend.
- No new paid requests are allowed while accounting is unreconciled.
- Existing pilot data is no longer available for the ablation and cannot be
  reused in the scorecard.
- The reproducibility failure and lost-data limitation must be disclosed in any
  final Method section.
- A fresh complete run is needed after the fixed scenario, temperature setting,
  proxy capture, and smoke gates are frozen and tested.

## Recommended recovery

1. Establish a genuinely persistent, accessible destination for files; local
   Git in this transient workspace did **not** survive the full cleanup.
2. Restore historical records from a user-held backup if one exists. Otherwise
   record the verified $0.067766300 as a clearly labeled pre-ablation aggregate
   carried forward, with explicit user acceptance that individual logs are lost.
3. Reconcile the guard against that carry-forward, run all mock tests, and
   perform a tiny paid smoke test before another batch.

Nothing remaining justifies running blind or spending for its own sake.
