# Six-hypothesis source audit

Subject: Open WebUI 0.11.3 at commit `0a7c15832fb30b1903753e83f81dc7d27e5b0944`.
Brief: `teardown-01-openwebui-agent-prompt.md`, SHA-256 `694aabface63efab0ea13c5b46d09c5ba72f8369581e06d605e72d91cc0b8db6`.

This is a source audit, not wire validation. `analysis/source_audit.py` regenerates
the line-level evidence in `results/source-audit.json` and fails if the pinned
source or brief changes unexpectedly.

| # | Original hypothesis | Source result | Consequence for the study |
|---|---|---|---|
| 1 | Background task models default to the chat model | Supported | Empty task-model overrides leave the selected chat model in place. Keep the task-tier experiment. |
| 2 | Some task calls have no output cap | Supported, with a title caveat | Follow-up, tag, and query payloads have no endpoint cap when global task parameters are empty. Title now has a 1,000-token fallback cap. |
| 3 | Title generation resends the full large prompt | Supported | The stock title template selects the final two complete messages, so a first-turn large user prompt and answer are included without content truncation. |
| 4 | There is no built-in context trimmer | Already fixed, but disabled by default | Native summarize-and-replace compaction exists. Its stock setting is off and its default threshold is 80,000 tokens, so default history-resend cost remains measurable. |
| 5 | Autocomplete fires on every keystroke when enabled | Already fixed | Server and user defaults are off. When enabled, dispatch is debounced by 1,000 ms and concurrent requests are suppressed. Do not describe this as a stock-default cost. |
| 6 | RAG and web-search query generation may duplicate | Supported | Query reuse exists, but `ENABLE_QUERIES_CACHE` defaults false. The experiment must exercise web and file retrieval in the same middleware request. |

## Stop-rule decision

Four hypotheses remain supported and two are already fixed or materially changed.
The brief requires stopping only if **more than two** are already fixed. The count
is exactly two, so that stop condition is not triggered.

The remaining stop conditions cannot be evaluated until measurements exist:
savings below 25%, major main-chat degradation, projected spend above $50, or a
need to fork Open WebUI. Section 10's stricter $20 hard budget applies regardless.
