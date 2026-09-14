from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from proxy.mock_provider import Handler as MockHandler
from proxy.server import Server as ProxyServer


PROJECT = Path(__file__).parents[1]


class MockPipelineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "results").mkdir()
        shutil.copy2(PROJECT / "config.yaml", self.root / "config.yaml")
        shutil.copy2(
            PROJECT / "results/historical-spend.json",
            self.root / "results/historical-spend.json",
        )
        (self.root / "results/spend-log.jsonl").write_text("", encoding="utf-8")
        self.servers = []

    def tearDown(self) -> None:
        for server, thread in reversed(self.servers):
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        self.temp.cleanup()

    def start(self, server):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        return server.server_address[1]

    @staticmethod
    def post(url: str, payload: dict, token: str = "test"):
        raw = json.dumps(payload).encode()
        request = urllib.request.Request(
            url,
            data=raw,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST",
        )
        # First use can populate tiktoken's local encoding cache on a clean machine.
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())

    def test_mock_provider_through_proxy_captures_redacted_nonstreaming_timing(self) -> None:
        mock_port = self.start(ThreadingHTTPServer(("127.0.0.1", 0), MockHandler))
        capture = self.root / "results/mock-capture.jsonl"
        proxy = ProxyServer(
            ("127.0.0.1", 0),
            self.root,
            f"http://127.0.0.1:{mock_port}",
            capture,
            False,
            "contingency",
            "mock",
            32,
            5,
        )
        proxy_port = self.start(proxy)
        secret = "sk-" + "proj-abcdefghijklmnopqrstuvwxyz"
        status, body = self.post(
            f"http://127.0.0.1:{proxy_port}/v1/chat/completions",
            {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": f"title {secret}"}],
                "stream": False,
            },
            token=secret,
        )
        self.assertEqual(status, 200)
        self.assertIn("usage", body)
        row = json.loads(capture.read_text(encoding="utf-8"))
        serialized = json.dumps(row)
        self.assertNotIn(secret, serialized)
        self.assertEqual(row["request_headers"]["Authorization"], "[REDACTED]")
        self.assertIsNone(row["ttft_ms"])
        self.assertFalse(row["ttft_observable"])
        self.assertGreaterEqual(row["completion_ms"], 0)
        self.assertEqual((self.root / "results/spend-log.jsonl").read_text(), "")

    def test_paid_proxy_blocker_returns_before_dispatch_or_reservation(self) -> None:
        (self.root / "results/PAID-CALLS-BLOCKED").write_text("blocked\n", encoding="utf-8")
        mock_port = self.start(ThreadingHTTPServer(("127.0.0.1", 0), MockHandler))
        proxy = ProxyServer(
            ("127.0.0.1", 0),
            self.root,
            f"http://127.0.0.1:{mock_port}",
            self.root / "results/paid-capture.jsonl",
            True,
            "baseline",
            "blocked-smoke",
            32,
            5,
        )
        proxy_port = self.start(proxy)
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.post(
                f"http://127.0.0.1:{proxy_port}/v1/chat/completions",
                {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "must not dispatch"}],
                    "stream": False,
                },
            )
        self.assertEqual(raised.exception.code, 402)
        self.assertEqual((self.root / "results/spend-log.jsonl").read_text(), "")
        self.assertFalse((self.root / "results/paid-capture.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
