"""Idempotently install the controlled corpus through Open WebUI's real APIs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DOC_ID = re.compile(r"\[DOC_ID:([^\]]+)\]")


def request_json(method: str, url: str, token: str | None = None, payload: dict | None = None, timeout: int = 300):
    headers = {}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def extract_doc_ids(value: Any) -> list[str]:
    found = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key == "name" and isinstance(child, str) and child.startswith("teardown:"):
                    found.append(child.split(":", 1)[1])
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            found.extend(DOC_ID.findall(item))

    visit(value)
    return list(dict.fromkeys(found))


def list_knowledge(base: str, token: str, timeout: int) -> list[dict]:
    response = request_json("GET", base + "/api/v1/knowledge/?limit=100", token, timeout=timeout)
    return response.get("items", []) if isinstance(response, dict) else response or []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--corpus", type=Path, default=Path("scenario/retrieval-corpus.json"))
    parser.add_argument("--cases", type=Path, default=Path("scenario/retrieval-cases.json"))
    parser.add_argument("--state", type=Path, default=Path("results/corpus-install.json"))
    parser.add_argument("--email", default="admin@localhost")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    corpus_bytes = args.corpus.read_bytes()
    corpus_sha = hashlib.sha256(corpus_bytes).hexdigest()
    corpus = json.loads(corpus_bytes)
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    token = request_json("POST", base + "/api/v1/auths/signin", payload={"email": args.email, "password": args.password}, timeout=args.timeout)["token"]
    existing = None
    if args.state.exists():
        state = json.loads(args.state.read_text(encoding="utf-8"))
        if state.get("base_url") != base or state.get("corpus_sha256") != corpus_sha:
            raise SystemExit("Existing corpus state belongs to a different runtime or corpus; refusing to overwrite it")
        if state.get("inflight_document_id"):
            raise SystemExit("Prior corpus install stopped with an in-flight document; reconcile or reset the controlled collection before resuming")
        existing = next((item for item in list_knowledge(base, token, args.timeout) if item.get("id") == state.get("collection_id")), None)
        if existing is None:
            raise SystemExit("Recorded controlled collection no longer exists; preserve the state and investigate before rebuilding")
    else:
        name = f"Teardown Fixed Corpus v1 {corpus_sha[:8]}"
        matches = [item for item in list_knowledge(base, token, args.timeout) if item.get("name") == name]
        if matches:
            raise SystemExit("Matching controlled collection exists without a local state file; refusing possible duplicate indexing")
        existing = request_json("POST", base + "/api/v1/knowledge/create", token, {"name": name, "description": f"Controlled teardown retrieval corpus sha256={corpus_sha}", "access_grants": []}, args.timeout)
        state = {"schema_version": 1, "base_url": base, "corpus_sha256": corpus_sha, "collection_id": existing["id"], "completed_document_ids": [], "inflight_document_id": None, "created_at": datetime.now(timezone.utc).isoformat(), "verification": None}
        atomic_json(args.state, state)

    completed = set(state.get("completed_document_ids", []))
    for document in corpus["documents"]:
        if document["id"] in completed:
            continue
        state["inflight_document_id"] = document["id"]
        atomic_json(args.state, state)
        content = f"[DOC_ID:{document['id']}] {document['title']}\n\n{document['text']}"
        request_json("POST", base + "/api/v1/retrieval/process/text", token, {"name": f"teardown:{document['id']}", "content": content, "collection_name": state["collection_id"]}, args.timeout)
        state["completed_document_ids"].append(document["id"])
        state["inflight_document_id"] = None
        atomic_json(args.state, state)

    verification = []
    for case in cases["queries"]:
        response = request_json("POST", base + "/api/v1/retrieval/query/collection", token, {"collection_names": [state["collection_id"]], "query": case["query"], "k": 3}, args.timeout)
        retrieved = extract_doc_ids(response)
        verification.append({"case_id": case["id"], "retrieved_document_ids": retrieved[:3], "relevant_document_ids": case["relevant_document_ids"]})
    state["verification"] = {"run_at": datetime.now(timezone.utc).isoformat(), "top_k": 3, "cases": verification}
    atomic_json(args.state, state)
    print(json.dumps({"status": "passed", "collection_id": state["collection_id"], "documents": len(state["completed_document_ids"]), "verification_cases": len(verification), "state": str(args.state)}, sort_keys=True))


if __name__ == "__main__":
    main()
