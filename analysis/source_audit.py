"""Verify cost-lever claims against an exact Open WebUI checkout."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


PINNED_COMMIT = "0a7c15832fb30b1903753e83f81dc7d27e5b0944"
PINNED_VERSION = "0.11.3"


@dataclass(frozen=True)
class Evidence:
    path: str
    needle: str
    meaning: str


LEVER_EVIDENCE = {
    "L1_task_model_tier": {
        "finding": "supported",
        "evidence": [
            Evidence("backend/open_webui/routers/tasks.py", "'task.model.default'", "task-model config is loaded"),
            Evidence("backend/open_webui/routers/tasks.py", "@router.post('/title/completions')", "title task endpoint"),
            Evidence("backend/open_webui/routers/tasks.py", "@router.post('/tags/completions')", "tag task endpoint"),
            Evidence("backend/open_webui/routers/tasks.py", "@router.post('/queries/completions')", "RAG/web query endpoint"),
            Evidence("backend/open_webui/routers/tasks.py", "@router.post('/auto/completions')", "autocomplete endpoint"),
        ],
    },
    "L2_task_output_cap": {
        "finding": "supported_broader_than_proposed",
        "evidence": [
            Evidence("backend/open_webui/routers/tasks.py", "'task.model.params'", "one global task-parameter dictionary"),
            Evidence("backend/open_webui/routers/tasks.py", "payload = apply_task_model_params(payload, models, task_model_id, task_model_params)", "same helper is called by title through autocomplete endpoints"),
        ],
    },
    "L3_title_input_token_truncation": {
        "finding": "unsupported_natively",
        "evidence": [
            Evidence("backend/open_webui/utils/task.py", "def truncate_content(content: str, max_chars: int", "content limit is explicitly characters"),
            Evidence("backend/open_webui/utils/task.py", "selected = messages[-int(end_length) :]", "END selector counts messages"),
            Evidence("backend/open_webui/utils/task.py", "new_msg['content'] = truncate_content", "character filter is applied per message"),
        ],
    },
    "L4_context_management": {
        "finding": "supported_native_compaction_and_extension_windows",
        "evidence": [
            Evidence("backend/open_webui/config.py", "ENABLE_CONTEXT_COMPACTION = os.getenv('ENABLE_CONTEXT_COMPACTION', 'False')", "native compaction defaults off"),
            Evidence("backend/open_webui/config.py", "CONTEXT_COMPACTION_TOKEN_THRESHOLD = int(os.getenv('CONTEXT_COMPACTION_TOKEN_THRESHOLD', '80000'))", "default threshold is 80k tokens"),
            Evidence("backend/open_webui/utils/middleware.py", "await compact_messages_for_request(", "combined chat middleware invokes compaction"),
            Evidence("backend/open_webui/utils/context_compaction.py", "if not _exceeds_token_threshold", "compaction requires threshold crossing"),
        ],
    },
    "L5_query_reuse": {
        "finding": "supported_only_in_combined_middleware_path",
        "evidence": [
            Evidence("backend/open_webui/utils/middleware.py", "request.state.cached_queries = queries", "web handler stores queries on request state"),
            Evidence("backend/open_webui/routers/tasks.py", "if getattr(request.state, 'cached_queries', None):", "query endpoint reuses request-state cache"),
            Evidence("backend/open_webui/utils/middleware.py", "form_data = await chat_web_search_handler", "web generation occurs in combined chat middleware"),
            Evidence("backend/open_webui/utils/middleware.py", "await chat_completion_files_handler(request", "retrieval follows on the same request"),
        ],
    },
    "L6_retrieved_chunk_count": {
        "finding": "supported",
        "evidence": [
            Evidence("backend/open_webui/config.py", "RAG_TOP_K = int(os.getenv('RAG_TOP_K', '3'))", "default retrieved chunk count is three"),
            Evidence("backend/open_webui/routers/retrieval.py", "k=form_data.k if form_data.k else config.TOP_K", "document and collection retrieval use configured top-k"),
        ],
    },
    "L7_autocomplete": {
        "finding": "supported_stock_off_and_debounced",
        "evidence": [
            Evidence("backend/open_webui/config.py", "ENABLE_AUTOCOMPLETE_GENERATION = os.getenv('ENABLE_AUTOCOMPLETE_GENERATION', 'False')", "server feature defaults off"),
            Evidence("src/lib/components/common/InterfaceSettings.svelte", "let promptAutocomplete = false;", "per-user preference defaults off"),
            Evidence("src/lib/components/common/RichTextInput/AutoCompletion.js", "debounceTime: 1000", "input changes are debounced by one second"),
        ],
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locate(path: Path, needle: str) -> tuple[int, str]:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            return number, line.strip()
    raise AssertionError(f"Expected source evidence not found in {path}: {needle!r}")


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def audit(upstream: Path) -> dict:
    commit = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != PINNED_COMMIT:
        raise AssertionError(f"Expected {PINNED_COMMIT}, found {commit}")
    package = json.loads((upstream / "package.json").read_text(encoding="utf-8"))
    if package["version"] != PINNED_VERSION:
        raise AssertionError(f"Expected version {PINNED_VERSION}, found {package['version']}")

    file_hashes = {}
    levers = {}
    for lever, specification in LEVER_EVIDENCE.items():
        rows = []
        for expected in specification["evidence"]:
            source = upstream / expected.path
            number, excerpt = locate(source, expected.needle)
            file_hashes[expected.path] = sha256(source)
            rows.append(
                {
                    "path": expected.path,
                    "line": number,
                    "excerpt": excerpt,
                    "meaning": expected.meaning,
                    "permalink": f"https://github.com/open-webui/open-webui/blob/{commit}/{expected.path}#L{number}",
                }
            )
        levers[lever] = {"finding": specification["finding"], "evidence": rows}

    tasks = (upstream / "backend/open_webui/routers/tasks.py").read_text(encoding="utf-8")
    if tasks.count("payload = apply_task_model_params(payload, models, task_model_id, task_model_params)") < 6:
        raise AssertionError("Task parameter scope changed; repeat the L2 audit")

    return {
        "schema_version": 1,
        "subject": {"repository": "https://github.com/open-webui/open-webui", "commit": commit, "version": package["version"]},
        "status": "passed",
        "limits": [
            "The original Sections 1-9 brief is absent, so its exact six-hypothesis stop rule has not been evaluated.",
            "Source existence does not replace an end-to-end experiment.",
        ],
        "levers": levers,
        "source_file_sha256": dict(sorted(file_hashes.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, default=Path(__file__).parents[2] / "openwebui-upstream")
    parser.add_argument("--output", type=Path, default=Path("results/source-audit.json"))
    args = parser.parse_args()
    report = audit(args.upstream.resolve())
    atomic_json(args.output, report)
    print(json.dumps({"status": report["status"], "commit": report["subject"]["commit"], "levers": len(report["levers"]), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
