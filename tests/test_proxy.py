from __future__ import annotations

import json
import unittest

from proxy.server import output_limit, parse_usage, scrub


class ProxyTestCase(unittest.TestCase):
    def test_scrub_redacts_headers_and_tokens_recursively(self) -> None:
        dummy = "sk-" + "abcdefghijklmnopqrstuvwxyz"
        value = {
            "Authorization": f"Bearer {dummy}",
            "nested": [f"prefix {dummy} suffix"],
            "safe": "keep me",
        }
        cleaned = scrub(value)
        self.assertEqual(cleaned["Authorization"], "[REDACTED]")
        self.assertNotIn("sk-", cleaned["nested"][0])
        self.assertEqual(cleaned["safe"], "keep me")

    def test_output_limit_injects_or_tightens_safety_ceiling(self) -> None:
        maximum, payload, mutations = output_limit({"model": "x"}, "/v1/chat/completions", 32)
        self.assertEqual(maximum, 32)
        self.assertEqual(payload["max_completion_tokens"], 32)
        self.assertTrue(mutations)
        maximum, payload, mutations = output_limit(
            {"model": "x", "max_tokens": 8}, "/v1/chat/completions", 32
        )
        self.assertEqual(maximum, 8)
        self.assertEqual(payload["max_tokens"], 8)
        self.assertFalse(mutations)

    def test_usage_parser_supports_chat_and_responses_shapes(self) -> None:
        chat = json.dumps(
            {
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "prompt_tokens_details": {"cached_tokens": 4},
                }
            }
        ).encode()
        responses = json.dumps(
            {"usage": {"input_tokens": 12, "output_tokens": 5}}
        ).encode()
        self.assertEqual(parse_usage(chat).__dict__, {"input_tokens": 10, "output_tokens": 3, "cached_input_tokens": 4})
        self.assertEqual(parse_usage(responses).__dict__, {"input_tokens": 12, "output_tokens": 5, "cached_input_tokens": 0})


if __name__ == "__main__":
    unittest.main()
