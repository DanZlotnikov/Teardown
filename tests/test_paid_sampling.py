from __future__ import annotations

import json

import pytest

from scenario.run import Action, action_id, sample_ids


def test_action_id_is_model_independent() -> None:
    first = Action("case", "title", "/endpoint", {"model": "gpt-5.6-sol", "messages": []})
    second = Action("case", "title", "/endpoint", {"model": "gpt-5.6-luna", "messages": []})
    assert action_id(first) == action_id(second)


def test_sample_manifest_rejects_duplicate_ids(tmp_path) -> None:
    value = "a" * 64
    path = tmp_path / "sample.json"
    path.write_text(json.dumps({"actions": [value, value]}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        sample_ids(path)
