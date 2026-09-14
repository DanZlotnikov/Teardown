"""Build the frozen targeted evaluation set without model calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def first_exchange(conversation: dict) -> list[dict]:
    return conversation["messages"][:2]


def main() -> None:
    scenario_path = ROOT / "scenario/cases.json"
    retrieval_corpus_path = ROOT / "scenario/retrieval-corpus.json"
    retrieval_path = ROOT / "scenario/retrieval-cases.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
    conversations = scenario["conversations"]
    cases = []
    for index, conversation in enumerate(conversations[:25], start=1):
        cases.append({"id": f"title-{index:02d}", "call_type": "title", "input": {"messages": first_exchange(conversation)}, "source_url": conversation["source_url"], "scoring": ["json_shape", "conciseness", "agreement"]})
    for index, conversation in enumerate(conversations[5:25], start=1):
        cases.append({"id": f"tags-{index:02d}", "call_type": "tags", "input": {"messages": first_exchange(conversation)}, "source_url": conversation["source_url"], "scoring": ["json_shape", "agreement"]})
    for index, conversation in enumerate(conversations[10:30], start=1):
        cases.append({"id": f"query-{index:02d}", "call_type": "retrieval_query" if index % 2 else "web_query", "input": {"messages": first_exchange(conversation)}, "source_url": conversation["source_url"], "scoring": ["json_shape", "agreement"]})
    for index in range(1, 21):
        project = f"Project Kestrel-{index:02d}"
        code = f"OWUI-{7300 + index}"
        region = ["La Paz", "Helsinki", "Osaka", "Nairobi"][index % 4]
        messages = [{"role": "user", "content": f"Remember for later: {project} uses incident code {code} and its recovery region is {region}."}, {"role": "assistant", "content": "Understood."}]
        for turn in range(1, 8):
            messages.extend([{"role": "user", "content": f"Unrelated diagnostic turn {turn}: discuss generic logging and deployment checks without repeating the project facts."}, {"role": "assistant", "content": f"Generic diagnostic response {turn}."}])
        messages.append({"role": "user", "content": "What were the exact project name, incident code, and recovery region from the first turn?"})
        cases.append({"id": f"context-{index:02d}", "call_type": "main_chat_context", "input": {"messages": messages}, "expected": {"required_phrases": [project, code, region]}, "scoring": ["required_phrase_recall"]})
    for row in retrieval["queries"]:
        cases.append({"id": f"retrieval-{row['id']}", "call_type": "retrieval", "input": {"collection_id": retrieval["collection_id"], "query": row["query"]}, "expected": {"relevant_document_ids": row["relevant_document_ids"]}, "scoring": ["retrieval_recall_at_k", "grounding"]})
    prefixes = [
        "To reduce background task cost, configure", "Native context compaction should trigger when", "A safe paid-call ledger must", "For retrieval top-k testing, keep", "Autocomplete requests are reduced by", "A local Ollama condition records", "Nonstreaming task latency should report", "A stable paid-output cache key includes", "Query reuse only works when", "Title template truncation counts",
    ]
    for index, prefix in enumerate(prefixes, start=1):
        cases.append({"id": f"autocomplete-{index:02d}", "call_type": "autocomplete", "input": {"prompt": prefix}, "scoring": ["request_count", "completion_latency", "acceptance_ux_not_answer_quality"]})
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate eval case IDs")
    output = {"schema_version": 1, "temperature": 0, "cases": cases}
    output_path = ROOT / "eval/cases.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    files = [scenario_path, retrieval_corpus_path, retrieval_path, output_path]
    manifest = {"schema_version": 1, "frozen": True, "counts": {kind: sum(case["call_type"] == kind for case in cases) for kind in sorted({case["call_type"] for case in cases})}, "total_cases": len(cases), "sha256": {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}
    (ROOT / "eval/manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"total_cases": len(cases), "counts": manifest["counts"], "eval_sha256": manifest["sha256"]["eval/cases.json"]}, sort_keys=True))


if __name__ == "__main__":
    main()
