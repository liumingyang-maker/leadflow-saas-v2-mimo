from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FACADE = ROOT / "app" / "integrations" / "browser" / "restricted_playwright_mcp.cjs"
FAKE_UPSTREAM = ROOT / "tests" / "browser" / "fixtures" / "fake_playwright_mcp.cjs"


class JsonRpcProcess:
    def __init__(self) -> None:
        node = shutil.which("node")
        if node is None:
            raise RuntimeError("Node.js is required for Browser MCP facade tests")
        self._process = subprocess.Popen(
            [str(node), str(FACADE), "--", str(node), str(FAKE_UPSTREAM)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._next_id = 1

    def request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("facade stdio is unavailable")
        request_id = self._next_id
        self._next_id += 1
        self._process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            + "\n"
        )
        self._process.stdin.flush()
        while True:
            line = self._process.stdout.readline()
            if not line:
                stderr = ""
                if self._process.stderr is not None:
                    stderr = self._process.stderr.read()
                raise RuntimeError(f"facade closed before response: {stderr}")
            response = json.loads(line)
            if response.get("id") == request_id:
                return response

    def notify(self, method: str, params: dict[str, object]) -> None:
        if self._process.stdin is None:
            raise RuntimeError("facade stdin is unavailable")
        self._process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n"
        )
        self._process.stdin.flush()

    def close(self) -> None:
        if self._process.stdin is not None:
            self._process.stdin.close()
        try:
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            self._process.wait(timeout=3)


@pytest.fixture
def facade() -> Generator[JsonRpcProcess, None, None]:
    process = JsonRpcProcess()
    try:
        initialized = process.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        assert "result" in initialized
        process.notify("notifications/initialized", {})
        yield process
    finally:
        process.close()


def test_facade_lists_exact_allowlist(facade: JsonRpcProcess) -> None:
    response = facade.request("tools/list", {})

    tools = response["result"]
    assert isinstance(tools, dict)
    names = {item["name"] for item in tools["tools"]}
    assert names == {
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_take_screenshot",
        "browser_close",
    }
    assert "browser_evaluate" not in names


def test_facade_normalizes_screenshot_and_rejects_unknown_tool(
    facade: JsonRpcProcess,
) -> None:
    filename = "a" * 64 + ".png"
    screenshot = facade.request(
        "tools/call",
        {"name": "browser_take_screenshot", "arguments": {"type": "png", "filename": filename}},
    )
    screenshot_content = screenshot["result"]
    assert isinstance(screenshot_content, dict)
    forwarded = json.loads(screenshot_content["content"][0]["text"])["receivedCalls"]
    assert forwarded == [
        {
            "name": "browser_take_screenshot",
            "arguments": {"type": "png", "filename": filename, "scale": "css"},
        }
    ]

    rejected = facade.request(
        "tools/call",
        {"name": "browser_evaluate", "arguments": {"function": "1 + 1"}},
    )
    assert rejected["error"]["code"] == -32601

    malformed = facade.request(
        "tools/call",
        {
            "name": "browser_take_screenshot",
            "arguments": {"type": "png", "filename": "not-content-addressed.png"},
        },
    )
    assert malformed["error"]["code"] == -32602

    snapshot = facade.request("tools/call", {"name": "browser_snapshot", "arguments": {}})
    snapshot_content = snapshot["result"]
    assert isinstance(snapshot_content, dict)
    all_forwarded = json.loads(snapshot_content["content"][0]["text"])["receivedCalls"]
    assert [call["name"] for call in all_forwarded] == [
        "browser_take_screenshot",
        "browser_snapshot",
    ]
