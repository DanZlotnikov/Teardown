# Open WebUI AI-cost teardown

Reproducible controlled-ablation study of Open WebUI 0.11.3, pinned to commit `0a7c15832fb30b1903753e83f81dc7d27e5b0944`.

## Current status

- Durable working branch: `recovery/checkpoint-and-safeguards`.
- Historical pre-ablation pilot spend carried forward: **$0.067766300 across 324 successful calls**. Per-call rows and captures were lost and are not reconstructible.
- Fresh paid benchmarking is authorized by `results/authorization/historical-ledger-rerun-approved.json`, subject to every guard in `config.yaml`.
- Frozen workload: 30 conversations / 129 user turns / 349 actions including 20 real retrieval-endpoint actions.
- Frozen targeted eval set: 115 cases. See `eval/manifest.json` for hashes and counts.
- Original ten-section brief: preserved at `teardown-01-openwebui-agent-prompt.md` and bound by SHA-256 in `config.yaml`.
- Hypothesis audit: 4/6 supported; 2/6 already fixed or materially changed. The brief's stop threshold is **more than two**, so it is not triggered.
- Lever audit: 7/7 proposed ablation levers checked against the pinned checkout; native L3 token truncation is unsupported.
- The complete local single-lever screen has run through the real pinned Open WebUI runtime, including 20/20 saved-chat native-compaction triggers.
- The frozen hosted task baseline sample is complete at 32/32 paired actions; the historical aggregate remains a budget debit only, never benchmark evidence.
- Frozen generative eval mock: 95 cases execute and resume entirely from cache; this validates the harness, not model quality.
- Pinned Docker runtime build: incomplete at backend dependency step 23/30 after two bounded attempts. See `results/runtime-validation.md`.

## Safety invariants

The budget guard counts the historical aggregate in total and per-phase exposure. Every provider attempt must first persist a cross-process-locked worst-case reservation. Unknown-usage failures retain their reservation. The user-confirmed policy has a $23 soft stop and $30 hard stop, with phase caps baseline $4, optimized $1, quality eval $18, judge $3, and contingency $4. Until `results/CORE-EVIDENCE-COMPLETE` exists, no reservation may take effective exposure above $3. Continuing after the soft stop requires the auditable `results/POST-SOFT-STOP-AUTHORIZED` marker. Paid results use stable cache keys bound to condition, fixture hash, endpoint, and payload.

The API key must remain outside this repository, supplied through a local environment variable such as `OPENAI_API_KEY`. Never add a key file here.

## No-cost validation

From PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m analysis.source_audit --upstream ..\openwebui-upstream
.\.venv\Scripts\python.exe -m scenario.build_retrieval_fixture
.\.venv\Scripts\python.exe -m eval.build_cases
.\scripts\validate_no_cost.ps1
```

Re-running either fixture builder must leave the tracked files byte-identical. The pinned upstream checkout must be at `..\openwebui-upstream` or passed explicitly.

Once a disposable pinned Open WebUI runtime is available, install the controlled corpus through its real APIs. The installer refuses implicit replacement, duplicate indexing without state, and ambiguous crash recovery:

```powershell
.\.venv\Scripts\python.exe -m scenario.install_corpus --base-url http://127.0.0.1:8088
```

Pass the resulting `collection_id` to `scenario.run --retrieval-collection-id ...`; the symbolic fixture ID is never presented as an already-indexed native collection.

## Evidence map

- `config.yaml`: frozen pricing and budget policy.
- `results/historical-spend.json`: disclosed aggregate carry-forward.
- `results/source-audit.json` and `results/source-call-graph.md`: pinned source evidence.
- `findings/hypothesis-audit.md`: exact six-hypothesis reconciliation and stop-rule decision.
- `scenario/`: deterministic chat fixture and controlled retrieval corpus.
- `eval/cases.json` and `eval/manifest.json`: targeted evaluation inputs and hashes.
- `configs/conditions.yaml`: one-variable condition matrix.
- `proxy/`: redacted capture proxy and deterministic mock provider.
- `analysis/budget.py`: locked reservation/ledger enforcement.
- `tests/`: no-cost safeguards and fixture checks.

## Before any paid phase

Use the external `.env` key only through the local paid runtime, scan the repository for the exact secret value, reconcile the reservation ledger, and run at most two distinct smoke calls. A passing phase-specific marker is required before a batch. Checkpoint captures, action manifests, caches, and ledger rows at least every ten purchased calls and after every completed condition.
