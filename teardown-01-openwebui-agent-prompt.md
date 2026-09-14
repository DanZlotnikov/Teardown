# AGENT TASK: LLM Cost Teardown #1 — Open WebUI

## 1. WHO THIS IS FOR

I run a consultancy that finds and removes wasted spend in companies' LLM API
bills. The work is: model routing, prompt caching, request/response structuring,
context management, and proving quality doesn't degrade after the changes.

I have no clients yet and no case studies. This teardown IS the case study. It is
a public artifact whose job is to make a CTO at an AI product company read it and
think "that is exactly what our codebase looks like." It is not a blog post about
AI in general and it is not marketing copy.

Subject: **Open WebUI** (https://github.com/open-webui/open-webui) — Python/FastAPI
backend, SvelteKit frontend, MIT-ish licensed, very large install base.

## 2. WHAT SUCCESS LOOKS LIKE

A public GitHub repo containing a reproducible measurement of Open WebUI's
default-configuration token cost, 4–6 specific findings with before/after numbers,
a quality evaluation proving the cheap configuration still works, and a 1,500–2,500
word writeup. Everything must be re-runnable by a skeptical reader.

**The single most important property: every number must be reproducible from
scripts in the repo.** A reader who disagrees with my assumptions must be able to
change one config value and re-derive the whole table. No number appears in the
writeup that isn't produced by committed code.

## 3. NON-NEGOTIABLE CONSTRAINTS

- **Never invent a number.** If you cannot measure something, say so explicitly in
  the writeup and mark it as an estimate with the reasoning shown.
- **Never state a price from memory.** Fetch current API pricing from provider
  pricing pages at run time, record the fetch date, and store it in a config file.
  Prices change; the writeup must be dated and must name the pricing snapshot used.
- **Tokenize, don't estimate.** Use the actual tokenizer for the model being priced
  (tiktoken for OpenAI, the Anthropic token-counting endpoint for Claude). Never use
  "~4 chars per token."
- **Measure at the wire.** Do not reason about cost by reading source code alone.
  Run Open WebUI and capture real outbound requests through a proxy. Code reading
  tells you where to look; the proxy tells you what actually happened.
- **Report losses.** The quality section must include cases where the cheap
  configuration performed worse. A teardown with no losses reads as marketing and
  destroys the credibility of everything else.
- **Tone: never accusatory.** The Open WebUI maintainers document several of these
  behaviors and ship mitigations. Frame every finding as "here is what the default
  costs and here is the measured delta from changing it," never as "they made a
  mistake." Assume maintainers will read it. Assume they may comment publicly.
- **Do not open a PR** without checking with me first.

## 4. WHAT I ALREADY KNOW — VERIFY, DON'T TRUST

I researched these before assigning the task. Treat every one as a hypothesis to
confirm or kill against the current version of the code. Some may be stale.

1. **Background task models default to the chat model.** Open WebUI runs several
   background tasks — title generation, tag generation, RAG query generation, web
   search query generation, autocomplete — and by default they use the same model
   you're chatting with. On an expensive frontier model this materially increases
   cost. There is a configurable Task Model setting that most deployments never
   touch.
2. **Some task calls ship with no output limit.** Tag, follow-up, and search query
   generation reportedly send no `max_tokens` cap unless set under Task Model
   Parameters. On a reasoning model this means paying for thinking tokens to
   produce a three-word chat title.
3. **Title generation resends the full prompt.** A reported case: a 10k-token
   prompt produced two 10k+ token requests — one to answer, one to title — roughly
   doubling the cost of the first message in a chat, when the title only needed the
   opening ~200 tokens.
4. **There is no built-in context trimmer.** The docs state this is deliberate:
   every deployment wants a different truncation policy, so they expose a filter
   hook (`inlet()`) instead of choosing one. The consequence is that by default the
   entire conversation history is resent on every turn, and cost grows quadratically
   with conversation length.
5. **Autocomplete fires on every keystroke** when enabled.
6. **RAG and web-search query generation may duplicate.** There is a toggle to
   reuse the web-search-generated query for RAG within the same turn; without it,
   two LLM calls do overlapping work on one user message.

Confirm each against the code you actually clone. If one is no longer true, say so
in the writeup — "this was fixed in vX.Y" is a credible, useful finding.

## 5. EXECUTION PLAN

### Phase 0 — Setup (~1 hour)
- Clone Open WebUI. Record the exact commit SHA and version tag; both go in the
  writeup and in `config.yaml`.
- Deploy locally via Docker with a persistent volume.
- Stand up a logging proxy between Open WebUI and the model provider so every
  outbound request/response is captured with full bodies and token counts. LiteLLM
  proxy with logging, or a small custom mitm-style HTTP logger, both work. This is
  the measurement instrument — get it right before anything else.
- Verify the instrument: send one message, confirm you captured every request.
- Fetch current pricing for the models you'll price. Save to `config.yaml` with the
  fetch date and source URL.

### Phase 1 — Map the call graph (~2 hours)
- Locate every code path that issues an LLM call. Start with the task/middleware
  utilities and the prompt template constants in config.
- Produce `findings/call-graph.md`: for each call site, the trigger, the model used,
  whether a token cap is applied, what payload is sent, and whether it is
  user-visible.
- Cross-check against the proxy log. Any call in the log not in your map means you
  missed a code path.

### Phase 2 — Baseline measurement (~3 hours)
Define a **scripted usage scenario** and run it end to end through the proxy. Put
the scenario in the repo as a script so it is reproducible.

Scenario: a mixed workload of at least 30 conversations covering
- short chats (2 turns)
- long chats (10+ turns) — this exposes the history-resend cost
- one chat with a large pasted document (~10k tokens) in the first message
- several chats with a knowledge-base/RAG attachment
- several with web search enabled
- with autocomplete on and off

For each: total tokens in/out, per-call-type breakdown, cost at current prices, and
wall-clock latency. Store the raw proxy log in the repo (scrub anything sensitive).

Output `results/baseline.json` and a per-call-type cost attribution table. **The key
deliverable of this phase is the share of total spend that goes to calls the user
never sees.** That number is the hook of the entire piece.

### Phase 3 — The optimized configuration (~2 hours)
Build a config that changes only settings and filters — no forking, no custom
patches. This matters: the fix must be something a reader can apply on Monday.

Expected levers (confirm each exists):
- Task Model set to a cheap small model
- `max_tokens` caps on task model parameters
- A context-management filter function implementing sliding-window or
  summarize-and-replace truncation
- Title generation given a truncated input rather than the full prompt
- The RAG/web-search query reuse toggle
- Autocomplete off (measure separately — it's a UX tradeoff, not a free win)

Document each lever: exactly where it is set, what it does, what it costs in UX.

### Phase 4 — Re-measure (~1 hour)
Re-run the identical scenario against the optimized config. Same script, same
inputs. Produce `results/optimized.json` and the delta table.

### Phase 5 — Quality evaluation (~4 hours) — **THE MOST IMPORTANT PHASE**
Cost reduction without a quality proof is worthless. Every reader's first objection
is "the cheap model will be worse."

Build an eval set of at least 50 real cases covering each affected call type:
titles, tags, RAG query generation, and web search query generation. Source inputs
from real usage patterns, not synthetic toy examples — the project's own docs,
issues, and discussions are good raw material.

For each case, run both configurations and score:
- **Titles/tags:** LLM-as-judge pairwise preference, plus your own manual review of
  a sample. Report the judge model and the judging prompt in the repo.
- **Query generation:** does the generated query retrieve the same documents?
  Measure retrieval overlap, which is objective and much stronger than a judge.
- **Main chat answers:** confirm these are untouched — if the optimization changed
  main-model behavior, that is a finding and must be flagged loudly.

Report agreement rate per call type. **Enumerate the specific failures.** For each
failure, say whether you'd route that case back to the expensive model, and what the
routing rule would be. A "when to route back" section is the single most valuable
thing in the piece — it's the actual expertise.

Separately: measure the context-truncation lever's effect on long-conversation
answer quality. This is the one with real risk of degradation and it deserves its
own honest treatment.

### Phase 6 — Write it (~3 hours)
See structure below.

### Phase 7 — Ship (~1 hour)
- Public GitHub repo, clean README, MIT license, one-command reproduction.
- Writeup published to dev.to or Substack, linking to the repo.
- Draft (do not post) a Hacker News submission and an r/LocalLLaMA post for me to
  review.

## 6. REPO STRUCTURE

```
openwebui-cost-teardown/
├── README.md                 # summary + headline table + how to reproduce
├── TEARDOWN.md               # the full writeup
├── config.yaml               # model prices w/ fetch date, commit SHA, scenario params
├── scenario/                 # scripted usage workload
├── proxy/                    # logging proxy setup
├── analysis/                 # tokenization, cost attribution, table generation
├── eval/
│   ├── cases.jsonl           # the 50+ eval cases
│   ├── run_eval.py
│   └── results/              # including failures, verbatim
├── configs/
│   ├── baseline/             # stock defaults
│   └── optimized/            # settings + filter functions
├── results/
│   ├── baseline.json
│   ├── optimized.json
│   └── raw-proxy-logs/
└── findings/
    └── call-graph.md
```

## 7. WRITEUP STRUCTURE (TEARDOWN.md)

1. **Headline** — one sentence with the number. What the default config costs per
   month at the stated usage level, and what it costs after.
2. **Why this codebase** — it's popular, self-hosted, and its cost patterns are the
   same ones that appear in commercial AI products.
3. **Method and assumptions** — version SHA, pricing snapshot with date, the usage
   scenario, how tokens were counted, how to re-run. Visible assumptions block. Be
   explicit that a reader can substitute their own numbers.
4. **Where the money goes** — the baseline attribution table and chart. Lead with
   the invisible-calls share.
5. **Findings** — 4–6, each identically structured: the pattern → the code that
   causes it → measured cost → the fix → measured cost after. Include an actual
   config diff or filter function for each.
6. **Quality evaluation** — methodology, agreement rates per call type, the failure
   cases enumerated, and the routing rules for when to send work back to the
   expensive model.
7. **Summary table** — cost per conversation, monthly cost at stated volume, p50
   latency, eval agreement. Before / after / delta.
8. **What generalizes** — which of these patterns show up in commercial products
   that aren't Open WebUI. This is the section that converts readers into leads.
9. **Limitations** — what you didn't test, where the numbers are soft.
10. **One closing paragraph** — plain statement that I do this work for companies,
    with an email address. No hard pitch, no CTA stack.

Style: written for a senior engineer. Short sentences. Real code, not pseudocode.
No em-dash-heavy prose, no "in today's fast-moving AI landscape," no hype.

## 8. STOP AND ASK ME IF

- More than two of the six hypotheses in section 4 turn out to be already fixed
  (the piece may need a different angle, or a different subject).
- Total measured savings come in under 25% (not a compelling story — let's discuss
  before you write it up).
- The quality eval shows major degradation on the main chat path (that's a
  different, more interesting article, and I want to steer it).
- Anything requires spending more than $50 in API credits.
- You're tempted to fork the code to achieve a saving (breaks the "apply this on
  Monday" property).

## 9. DELIVERABLES CHECKLIST

- [ ] Public repo, reproducible in one command
- [ ] `findings/call-graph.md` — every LLM call site mapped and confirmed at the wire
- [ ] Baseline and optimized measurements from an identical scripted scenario
- [ ] Eval set of 50+ cases with results, failures included verbatim
- [ ] Routing rules: when to send a case back to the expensive model
- [ ] TEARDOWN.md, 1,500–2,500 words, structured as section 7
- [ ] Published post linking to the repo
- [ ] Draft HN and Reddit submissions for my review (do not post)
- [ ] A short list of what to measure differently in teardown #2


## 10. COST CONTROL — HARD BUDGET: $20

Total API spend for this entire task must not exceed **$20 USD**. This is a hard
cap, not a target. Treat it as a constraint on the design of every phase, not
something to check at the end.

### 10.1 Track spend from the first call

Before making any API call, create `results/spend-log.jsonl`. Every API call
appends one line: timestamp, phase, model, input tokens, output tokens, computed
cost, running total.

Compute cost from the pricing in `config.yaml` — the same snapshot used for the
teardown's headline numbers. Never estimate.

Maintain a running total in `results/spend-total.txt` after every call.

### 10.2 Kill switches

These are mandatory and must be enforced in code, not by your own judgment:

- **$15 soft stop.** At $15 cumulative, halt all API calls, write a status report
  to `results/BUDGET-STATUS.md` describing what is done, what remains, and your
  recommended plan for the remaining $5. Do not resume without my go-ahead.
- **$20 hard stop.** Under no circumstances continue past $20. Halt, write up
  whatever is complete, and report.
- **Per-phase caps.** Baseline $3, optimized $1, quality eval $12, judge $2,
  contingency $2. Exceeding any phase cap by more than 50% requires stopping and
  reporting before continuing.
- **Retry limit.** Maximum 3 retries per failed call, with exponential backoff.
  After 3 failures on the same call, log it and move on. A retry loop is the most
  likely way this budget gets destroyed — cap it in code.
- **No unattended long runs.** Any script issuing more than 50 calls must print
  the running spend total every 10 calls and abort on cap breach.

### 10.3 Measure cheap, price expensive

This is the core technique and it removes most of the bill.

Cost attribution needs accurate **token counts**, not frontier-model outputs. So:

1. Run the baseline and optimized scenarios against a cheap small model.
2. Capture the full request/response payloads at the proxy as normal.
3. Tokenize the captured payloads and compute cost at whatever provider rates are
   in `config.yaml`.

The cost tables are then derived arithmetic, not observed billing. Because pricing
lives in config, a reader can re-derive every number at their own rates.

**State this method explicitly in the writeup's Method section.** Also state the
caveat: tokenizers differ between model families, so counts carry a small error
when priced against a different family. Quantify that error if you can — tokenize
a sample of payloads with two tokenizers and report the spread.

Where token counts might legitimately differ between configurations — e.g. output
length varies by model — measure that specific case directly rather than assuming.

### 10.4 Use local models for the cheap side

Open WebUI supports Ollama natively. Run the optimized configuration's task model
locally where possible. That side of the comparison should cost approximately zero.

Do not use a local model for anything whose quality is being evaluated against a
hosted model unless the local model is genuinely one a reader would deploy — say
which model it is either way.

### 10.5 Do not economize on the quality evaluation

The eval is the only section that cannot be faked, and it is where the budget
should go. Real calls, both configurations, for every eval case.

But keep it cheap by design:
- The affected call types produce tiny outputs (titles, tags, search queries).
  400 small calls is a few dollars, not tens.
- **Never use a reasoning model as judge.** It bills thinking tokens for a binary
  preference. Use a fast mid-tier non-reasoning model and say which.
- Prefer objective metrics over judge calls where available. Retrieval overlap for
  query generation costs nothing beyond the retrieval itself and is stronger
  evidence than a judge.
- Cache eval outputs to disk. If a later phase needs them, read the file — never
  re-run a call you have already paid for.

### 10.6 Free resources — use them

Docker, GitHub, dev.to, tokenizer libraries, and your own VM are free. Web search
APIs (Serper, Brave, Tavily) have free tiers that cover this volume — use a free
tier key and do not exceed it.

### 10.7 Report actual spend

The writeup's Method section must state what this analysis actually cost to
produce, taken from `spend-log.jsonl`. A cost teardown that reports its own cost is
more credible than one that doesn't, and it demonstrates the discipline I'm selling.

