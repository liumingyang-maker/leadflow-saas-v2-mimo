"""Minimal stdio MCP client used only inside the isolated Browser worker."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from typing import Any


class McpClientError(RuntimeError):
    pass


class StdioMcpClient:
    """One short-lived MCP server process; never log its raw output."""

    def __init__(self, args: Sequence[str]) -> None:
        if not args:
            raise McpClientError("mcp command is required")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self._process = subprocess.Popen(
            list(args),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
        self._next_id = 1
        self._initialized = False

    def _request(self, method: str, params: dict[str, object]) -> dict[str, Any]:
        if self._process.stdin is None or self._process.stdout is None:
            raise McpClientError("mcp process pipes are unavailable")
        request_id = self._next_id
        self._next_id += 1
        self._process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
                separators=(",", ":"),
            )
            + "\n"
        )
        self._process.stdin.flush()
        while True:
            line = self._process.stdout.readline()
            if not line:
                raise McpClientError("mcp process closed unexpectedly")
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("id") != request_id:
                continue
            if "error" in payload:
                raise McpClientError("mcp request rejected")
            result = payload.get("result")
            if not isinstance(result, dict):
                raise McpClientError("mcp response was malformed")
            return result

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "leadflow-browser-gateway", "version": "1.0"},
            },
        )
        if self._process.stdin is None:
            raise McpClientError("mcp process stdin is unavailable")
        self._process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                separators=(",", ":"),
            )
            + "\n"
        )
        self._process.stdin.flush()
        self._initialized = True

    def list_tools(self) -> set[str]:
        self._ensure_initialized()
        result = self._request("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise McpClientError("mcp tool list was malformed")
        names = {item.get("name") for item in tools if isinstance(item, dict)}
        if not all(isinstance(name, str) for name in names):
            raise McpClientError("mcp tool list was malformed")
        return {name for name in names if isinstance(name, str)}

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self._ensure_initialized()
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        return result

    def close(self) -> None:
        process = self._process
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for pipe in (process.stdin, process.stdout):
            if pipe is not None:
                pipe.close()
