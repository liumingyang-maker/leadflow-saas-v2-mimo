# Browser MCP Facade Design

## Decision

Keep the pinned `@playwright/mcp@0.0.78` process inside the isolated Browser Worker, but place a
local stdio facade between it and the Python gateway. The facade is the only MCP process invoked by
the gateway. It exposes exactly five tools and rejects every other tool name before forwarding a
request to Playwright MCP.

## Boundary

```text
Python BrowserGateway
  -> restricted_playwright_mcp.cjs
    -> @playwright/mcp@0.0.78
      -> Chromium -> resolving egress proxy -> public HTTPS
```

The facade has no network listener, no application credentials, no database access, no policy
decision logic, and no model-facing configuration. It operates over stdin/stdout only and starts the
pinned Playwright process with a fixed argv produced in Python.

## Contract

`tools/list` returns exactly this set:

```text
browser_navigate
browser_snapshot
browser_click
browser_take_screenshot
browser_close
```

`tools/call` accepts only the following public argument shapes:

| Tool | Accepted arguments | Forwarded arguments |
| --- | --- | --- |
| `browser_navigate` | `url: string` | unchanged |
| `browser_snapshot` | `{}` | `{}` |
| `browser_click` | `target: string` | `{target}` |
| `browser_take_screenshot` | `type: "png", filename: safe relative `.png` name` | adds `scale: "css"` |
| `browser_close` | `{}` | `{}` |

Any unknown JSON-RPC method, unknown tool, unexpected key, wrong type, unsafe filename, or malformed
upstream response returns a JSON-RPC error and is not forwarded. The existing Python gateway remains
responsible for URL/DNS policy, snapshot sanitization, element-reference checks, budgets, result URL
validation, artifact hashing, and process cleanup.

## Validation and release state

Tests run the facade against a deterministic fake upstream server to prove tool filtering,
argument normalization, and rejection before forwarding. Docker validation then starts only the
Browser Redis, proxy, and Worker and proves that the actual pinned upstream is observed as exactly
five tools through the facade. No public navigation is part of that check.

Passing this gate changes the smoke script from its intentional exit code `2` to `0`; it does not
enable `BROWSER_RESEARCH_ENABLED`, add UI/Acquisition/Radar consumers, or authorize live browsing.
