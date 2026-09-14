from __future__ import annotations

import asyncio
import unittest

from configs.optimized.context_turn_filter import Filter


class ContextTurnFilterTestCase(unittest.TestCase):
    def test_keeps_system_and_exact_number_of_user_turns(self) -> None:
        filter_ = Filter()
        filter_.valves.turns = 3
        messages = [{"role": "system", "content": "system"}]
        for index in range(1, 7):
            messages.extend(
                [
                    {"role": "user", "content": f"user-{index}"},
                    {"role": "assistant", "content": f"assistant-{index}"},
                ]
            )
        result = asyncio.run(filter_.inlet({"messages": messages}))
        self.assertEqual(result["messages"][0]["role"], "system")
        self.assertEqual(
            [row["content"] for row in result["messages"] if row["role"] == "user"],
            ["user-4", "user-5", "user-6"],
        )
        self.assertEqual(len(result["messages"]), 7)

    def test_task_payload_is_untouched(self) -> None:
        filter_ = Filter()
        body = {"messages": [{"role": "user", "content": "x"}]}
        result = asyncio.run(filter_.inlet(body, {"task": "title_generation"}))
        self.assertIs(result, body)


if __name__ == "__main__":
    unittest.main()
