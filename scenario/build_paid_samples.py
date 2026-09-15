"""Build the frozen, model-independent paid sample manifests."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from scenario.run import action_id, build_actions


ROOT = Path(__file__).parents[1]
SCENARIO = ROOT / "scenario" / "cases.json"

TASK_SPECS = [
    *(('short-01', 'follow_up', ordinal) for ordinal in (0, 1)),
    ('short-08', 'follow_up', 1),
    *(('long-09', 'follow_up', ordinal) for ordinal in (0, 4, 9)),
    *(('long-10', 'follow_up', ordinal) for ordinal in (0, 4, 9)),
    ('long-11', 'follow_up', 4),
    *((conversation, 'title', 0) for conversation in ('short-01', 'short-04', 'short-08', 'long-09', 'long-10', 'long-11')),
    *((conversation, 'tags', 0) for conversation in ('short-01', 'short-04', 'short-08', 'long-09', 'long-10', 'long-11')),
    *((conversation, 'retrieval_query', 0) for conversation in ('case-20', 'case-21', 'case-22', 'case-23')),
    *((conversation, 'web_query', 0) for conversation in ('case-24', 'case-25', 'case-26', 'case-27')),
    *(('case-29', 'autocomplete', ordinal) for ordinal in (0, 1)),
]

CONTEXT_SPECS = [
    *(('long-09', 'main', ordinal) for ordinal in (2, 5, 9)),
    *(('long-10', 'main', ordinal) for ordinal in (2, 5, 9)),
    *(('long-11', 'main', ordinal) for ordinal in (2, 5)),
]


def entries(actions, specs):
    grouped = defaultdict(list)
    for action in actions:
        grouped[(action.conversation_id, action.call_type)].append(action)
    rows = []
    for conversation_id, call_type, ordinal in specs:
        action = grouped[(conversation_id, call_type)][ordinal]
        rows.append({
            "action_id": action_id(action),
            "conversation_id": conversation_id,
            "call_type": call_type,
            "ordinal_within_conversation_and_type": ordinal,
            "endpoint": action.endpoint,
        })
    if len({row["action_id"] for row in rows}) != len(rows):
        raise RuntimeError("sample selection contains duplicate actions")
    return rows


def write(name: str, purpose: str, rows: list[dict], scenario_sha256: str) -> None:
    target = ROOT / "scenario" / name
    value = {
        "schema_version": 1,
        "purpose": purpose,
        "scenario_sha256": scenario_sha256,
        "selection_frozen_before_comparison_runs": True,
        "actions": rows,
    }
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{target.relative_to(ROOT).as_posix()} actions={len(rows)}")


def main() -> None:
    raw = SCENARIO.read_bytes()
    data = json.loads(raw)
    actions = build_actions(data, "MODEL-PLACEHOLDER", "baseline")
    digest = hashlib.sha256(raw).hexdigest()
    write("paid-sample-task-32.json", "Paired L1/L2 task-call comparison", entries(actions, TASK_SPECS), digest)
    write("paid-sample-context-8.json", "Paired L4 long-context main-chat comparison", entries(actions, CONTEXT_SPECS), digest)


if __name__ == "__main__":
    main()
