# Runtime validation status

## Verified

- Pinned upstream checkout: Open WebUI 0.11.3 at `0a7c15832fb30b1903753e83f81dc7d27e5b0944` (detached HEAD).
- Docker client/daemon: 29.1.3, available after local startup.
- Local mock provider → capture proxy integration: passed.
- Ollama 0.33.3 with `qwen2.5:14b-instruct`: four task-shaped local calls passed at $0; see `local-model-smoke.json`.

## Pinned Open WebUI container build: incomplete

Two bounded builds used the exact source checkout, `USE_SLIM=true`, and build hash `0a7c15832fb30b1903753e83f81dc7d27e5b0944`:

| BuildKit ID | Duration | Result | Progress |
|---|---:|---|---|
| `w1icgmo1s4lkfr6brvi1f8nrn` | 31m 30s | canceled after command timeout | 23/30 steps |
| `zyuww0hakfxt6153ztx9xjlaj` | 15m 12s | canceled after final bounded retry | 23/30 steps, 47% cached |

Both reached Dockerfile step 23, the backend dependency layer. The second history log shows PyTorch installed and `uv` resolving 337 packages; it was still downloading large wheels such as OpenCV, PyArrow, llvmlite, and ONNX Runtime when canceled. No source/compiler error was reported, but no `teardown-openwebui:0.11.3-pinned` image was produced. Only the verified orphaned build client processes were terminated; Docker Desktop and the pre-existing Postgres container were left running.

Therefore the full mock path through a live pinned Open WebUI runtime, controlled-corpus indexing, and end-to-end scenario replay is **not passed** and remains a paid-smoke blocker. No third build retry was attempted.
