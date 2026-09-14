"""Build the controlled corpus and relevance judgments for L6."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
DOCUMENTS = [
    ("task-model", "Task model routing", "Open WebUI routes titles, tags, follow-up suggestions, retrieval queries, web-search queries, and autocomplete through the configured task model. Administrators can set a local or smaller task model without changing the main chat model."),
    ("task-cap", "Task output limits", "The task.model.params dictionary applies generation parameters across task endpoints. A max_tokens cap therefore reaches titles and autocomplete as well as tags, follow-ups, and queries; it is not a narrow tag-only control."),
    ("title-template", "Title history syntax", "Title prompt templates select messages with MESSAGES START, END, or MIDDLETRUNCATE counts. Optional start, end, and middletruncate filters limit characters within every selected message. These native limits do not count tokenizer tokens."),
    ("context-compaction", "Native context compaction", "Native context compaction defaults to disabled. Its default threshold is 80000 tokens and retention defaults to 40 percent. Tests must enable it on a saved chat and lower the threshold enough to prove a summary was generated."),
    ("query-cache", "Query reuse", "ENABLE_QUERIES_CACHE stores web-search queries on request state so later file retrieval in the same combined chat request can reuse them. Repeating the standalone query endpoint cannot exercise this optimization."),
    ("rag-top-k", "Retrieved chunk count", "The rag.top_k configuration defaults to three. Document and collection retrieval pass this value to vector or hybrid search unless a request-level k overrides it. Compare k values 3, 2, and 1 on one fixed indexed corpus."),
    ("autocomplete", "Autocomplete workload", "Autocomplete is disabled by default at the server and user preference levels. When enabled, the editor waits 1000 milliseconds after an input change and checks cursor and loading state, so requests are not sent on every keystroke."),
    ("budget", "Paid-call budget guard", "Before provider dispatch, acquire a cross-process lock and persist a worst-case reservation. Include the historical carry-forward and unresolved failures in exposure. Stop at 23 dollars softly and never reserve beyond 30 dollars."),
    ("resume-cache", "Paid output cache", "Cache every paid response under a stable key that binds condition, dataset hash, endpoint, and payload. Write the cache atomically before the append-only action manifest. On resume, a valid cache alone must prevent a repeated provider call."),
    ("wire-capture", "Proxy evidence", "Capture redacted provider request and response bodies, actual reported input, output, and cached tokens, completion latency, and all budget mutations. For nonstreaming task calls, mark time to first token unavailable rather than relabeling response time."),
    ("local-ollama", "Local Ollama condition", "A local model condition needs an exact installed model name, digest, quantization, Ollama version, and hardware record. A deployment smoke proves availability only; it does not establish equivalence to a hosted quality test."),
    ("quality", "Targeted quality evaluation", "Evaluate only call types affected by each lever. Use objective format, exact-fact, retrieval-overlap, and grounding metrics first. Use a cached non-reasoning judge only when objective comparisons are insufficient."),
]

QUERIES = [
    ("r01", "Which background features use the configured task model?", ["task-model"]),
    ("r02", "Does a global task max token limit affect autocomplete and titles?", ["task-cap"]),
    ("r03", "Are MESSAGES END limits measured in messages, characters, or tokens?", ["title-template"]),
    ("r04", "What must be changed so context compaction actually triggers?", ["context-compaction"]),
    ("r05", "Why is replaying a standalone query endpoint invalid for query reuse?", ["query-cache"]),
    ("r06", "What is the default retrieved chunk count and which levels should be compared?", ["rag-top-k"]),
    ("r07", "Is autocomplete enabled by default and does it fire every keystroke?", ["autocomplete"]),
    ("r08", "How should concurrent calls be prevented from overspending?", ["budget"]),
    ("r09", "What must a stable paid-response cache key bind?", ["resume-cache"]),
    ("r10", "How should latency be reported for a nonstreaming task endpoint?", ["wire-capture"]),
    ("r11", "What evidence identifies a deployable local model condition?", ["local-ollama"]),
    ("r12", "When should a model judge be used instead of objective scoring?", ["quality"]),
    ("r13", "How can task costs fall without changing the main chat model, and what cap has broad scope?", ["task-model", "task-cap"]),
    ("r14", "Contrast native title truncation with native context compaction units and defaults.", ["title-template", "context-compaction"]),
    ("r15", "Explain the valid middleware path for cached queries and the retrieval depth it feeds.", ["query-cache", "rag-top-k"]),
    ("r16", "Which two defaults make autocomplete opt-in and what timing behavior reduces calls?", ["autocomplete"]),
    ("r17", "How do atomic cache writes and pre-dispatch reservations address different crash risks?", ["resume-cache", "budget"]),
    ("r18", "Which capture fields support frozen-price arithmetic and honest latency reporting?", ["wire-capture", "budget"]),
    ("r19", "Why can a successful Ollama smoke not replace targeted hosted evaluation?", ["local-ollama", "quality"]),
    ("r20", "Design a safe L6 test with the real retrieval path and objective scoring.", ["rag-top-k", "quality", "wire-capture"]),
]


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    corpus = {
        "schema_version": 1,
        "collection_id": "teardown-fixed-corpus-v1",
        "kind": "controlled_operational_corpus",
        "documents": [{"id": doc_id, "title": title, "text": text} for doc_id, title, text in DOCUMENTS],
    }
    cases = {
        "schema_version": 1,
        "collection_id": corpus["collection_id"],
        "queries": [{"id": case_id, "query": query, "relevant_document_ids": relevant} for case_id, query, relevant in QUERIES],
    }
    corpus_path = ROOT / "scenario/retrieval-corpus.json"
    cases_path = ROOT / "scenario/retrieval-cases.json"
    write(corpus_path, corpus)
    write(cases_path, cases)
    print(json.dumps({"documents": len(DOCUMENTS), "queries": len(QUERIES), "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(), "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
