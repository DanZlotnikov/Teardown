"""Extract the clean baseline provider calls from the initial shared validation log."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("results/raw-proxy-logs/openwebui-local-20260914.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("results/raw-proxy-logs/baseline-local-qwen.jsonl"))
    parser.add_argument("--expected-chat-calls", type=int, default=329)
    parser.add_argument("--expected-embedding-calls", type=int, default=20)
    args = parser.parse_args()
    entries = [json.loads(line) for line in args.source.read_text(encoding="utf-8").splitlines() if line.strip()]
    chats = [
        entry
        for entry in entries
        if entry.get("path") == "/api/chat"
        and isinstance(entry.get("request_body"), dict)
        and entry["request_body"].get("model") == "qwen2.5:14b-instruct"
    ]
    if len(chats) != args.expected_chat_calls:
        raise SystemExit(f"Expected {args.expected_chat_calls} qwen chat calls, found {len(chats)}; refusing ambiguous extraction")
    first_chat_timestamp = chats[0]["timestamp"]
    embeddings = [entry for entry in entries if entry.get("path") == "/api/embed" and entry.get("timestamp", "") >= first_chat_timestamp]
    if len(embeddings) != args.expected_embedding_calls:
        raise SystemExit(f"Expected {args.expected_embedding_calls} baseline embedding calls, found {len(embeddings)}; refusing ambiguous extraction")
    selected = sorted([*chats, *embeddings], key=lambda entry: entry["timestamp"])
    if args.output.exists():
        raise SystemExit(f"Output already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for entry in selected:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"chat_calls": len(chats), "embedding_calls": len(embeddings), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
