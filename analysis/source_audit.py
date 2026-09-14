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


HYPOTHESIS_EVIDENCE = {
    "H1_background_tasks_default_to_chat_model": {
        "finding": "supported",
        "already_fixed": False,
        "summary": "The task-model settings default empty, and the resolver begins with the selected chat model before applying an optional task-model override.",
        "evidence": [
            Evidence("backend/open_webui/config.py", "TASK_MODEL = os.getenv('TASK_MODEL', '')", "the local task-model override defaults empty"),
            Evidence("backend/open_webui/config.py", "TASK_MODEL_EXTERNAL = os.getenv('TASK_MODEL_EXTERNAL', '')", "the external task-model override defaults empty"),
            Evidence("backend/open_webui/utils/task.py", "task_model_id = default_model_id", "task routing begins with the selected chat model"),
        ],
    },
    "H2_some_task_calls_have_no_output_cap": {
        "finding": "supported_with_title_caveat",
        "already_fixed": False,
        "summary": "Follow-up, tag, and query handlers have no endpoint-level output cap when global task.model.params is empty. Title now receives a 1,000-token fallback cap.",
        "evidence": [
            Evidence("backend/open_webui/config.py", "task_model_params = JSONCodec.loads(os.getenv('TASK_MODEL_PARAMS', '{}'))", "global task parameters default to an empty dictionary"),
            Evidence("backend/open_webui/routers/tasks.py", "if not model or (not params and not payload.get('params')):", "empty task parameters leave the payload unchanged"),
            Evidence("backend/open_webui/routers/tasks.py", "'max_tokens': models[task_model_id].get('info', {}).get('params', {}).get('max_tokens', 1000)", "title alone receives a fallback cap in this router"),
        ],
    },
    "H3_title_resends_full_large_prompt": {
        "finding": "supported",
        "already_fixed": False,
        "summary": "The default title template includes the final two messages without a content filter, so a first-turn large user prompt is included in full along with its answer.",
        "evidence": [
            Evidence("backend/open_webui/config.py", "{{MESSAGES:END:2}}", "the stock title template selects the last two complete messages"),
            Evidence("backend/open_webui/utils/task.py", "selected = messages[-int(end_length) :]", "END selects message count rather than token count"),
            Evidence("backend/open_webui/utils/task.py", "template = replace_messages_variable(template, messages)", "title generation expands the selected messages into its prompt"),
        ],
    },
    "H4_no_builtin_context_trimmer": {
        "finding": "already_fixed_but_disabled_by_default",
        "already_fixed": True,
        "summary": "Native summarize-and-replace context compaction now exists. It defaults off with an 80,000-token threshold, so the default resend-cost consequence remains testable.",
        "evidence": [
            Evidence("backend/open_webui/config.py", "ENABLE_CONTEXT_COMPACTION = os.getenv('ENABLE_CONTEXT_COMPACTION', 'False')", "native context compaction exists and defaults off"),
            Evidence("backend/open_webui/config.py", "CONTEXT_COMPACTION_TOKEN_THRESHOLD = int(os.getenv('CONTEXT_COMPACTION_TOKEN_THRESHOLD', '80000'))", "the default trigger threshold is 80,000 tokens"),
            Evidence("backend/open_webui/utils/middleware.py", "await compact_messages_for_request(", "the chat middleware invokes native compaction"),
        ],
    },
    "H5_autocomplete_fires_on_every_keystroke": {
        "finding": "already_fixed",
        "already_fixed": True,
        "summary": "Autocomplete is off by default at server and user levels; when enabled, input is debounced by 1,000 ms and guarded against concurrent dispatch.",
        "evidence": [
            Evidence("backend/open_webui/config.py", "ENABLE_AUTOCOMPLETE_GENERATION = os.getenv('ENABLE_AUTOCOMPLETE_GENERATION', 'False')", "the server feature defaults off"),
            Evidence("src/lib/components/common/InterfaceSettings.svelte", "let promptAutocomplete = false;", "the user preference defaults off"),
            Evidence("src/lib/components/common/RichTextInput/AutoCompletion.js", "debounceTime: 1000", "enabled autocomplete waits one second after input"),
            Evidence("src/lib/components/common/RichTextInput/AutoCompletion.js", "if (loading) return true;", "the editor suppresses concurrent completion dispatch"),
        ],
    },
    "H6_rag_and_web_query_generation_may_duplicate": {
        "finding": "supported",
        "already_fixed": False,
        "summary": "The combined middleware can reuse web queries for later retrieval, but ENABLE_QUERIES_CACHE defaults false, leaving duplicate generation possible in stock configuration.",
        "evidence": [
            Evidence("backend/open_webui/env.py", "ENABLE_QUERIES_CACHE = os.getenv('ENABLE_QUERIES_CACHE', 'False')", "query reuse defaults off"),
            Evidence("backend/open_webui/utils/middleware.py", "request.state.cached_queries = queries", "the web handler stores queries when reuse is enabled"),
            Evidence("backend/open_webui/routers/tasks.py", "if getattr(request.state, 'cached_queries', None):", "the later query task checks the request cache"),
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

    project = Path(__file__).parents[1]
    brief = project / "teardown-01-openwebui-agent-prompt.md"
    expected_brief_hash = "694aabface63efab0ea13c5b46d09c5ba72f8369581e06d605e72d91cc0b8db6"
    if not brief.exists():
        raise AssertionError(f"Original brief is missing: {brief}")
    if sha256(brief) != expected_brief_hash:
        raise AssertionError("Original brief hash changed; reconcile the source audit before continuing")

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

    hypotheses = {}
    for hypothesis, specification in HYPOTHESIS_EVIDENCE.items():
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
        hypotheses[hypothesis] = {
            "finding": specification["finding"],
            "already_fixed": specification["already_fixed"],
            "summary": specification["summary"],
            "evidence": rows,
        }

    tasks = (upstream / "backend/open_webui/routers/tasks.py").read_text(encoding="utf-8")
    if tasks.count("payload = apply_task_model_params(payload, models, task_model_id, task_model_params)") < 6:
        raise AssertionError("Task parameter scope changed; repeat the L2 audit")

    task_boundaries = {
        "follow_up": ("@router.post('/follow_up/completions')", "@router.post('/tags/completions')"),
        "tags": ("@router.post('/tags/completions')", "@router.post('/image_prompt/completions')"),
        "queries": ("@router.post('/queries/completions')", "@router.post('/auto/completions')"),
    }
    for task, (start, end) in task_boundaries.items():
        body = tasks[tasks.index(start) : tasks.index(end)]
        if "max_tokens" in body:
            raise AssertionError(f"{task} acquired an endpoint output cap; repeat H2 audit")

    fixed_count = sum(1 for item in hypotheses.values() if item["already_fixed"])

    return {
        "schema_version": 2,
        "subject": {"repository": "https://github.com/open-webui/open-webui", "commit": commit, "version": package["version"]},
        "brief": {"path": brief.name, "sha256": expected_brief_hash},
        "status": "passed",
        "limits": [
            "Source existence does not replace an end-to-end experiment.",
            "Confirmed source behavior remains provisional until observed at the wire through the pinned runtime.",
        ],
        "hypotheses": hypotheses,
        "stop_rule": {
            "rule": "stop if more than two of the six hypotheses are already fixed",
            "already_fixed_count": fixed_count,
            "threshold_exceeded": fixed_count > 2,
            "decision": "stop_and_ask" if fixed_count > 2 else "continue",
        },
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
    print(json.dumps({"status": report["status"], "commit": report["subject"]["commit"], "hypotheses": len(report["hypotheses"]), "fixed": report["stop_rule"]["already_fixed_count"], "decision": report["stop_rule"]["decision"], "levers": len(report["levers"]), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
