"""Minimal local MCP stdio server for integration tests; no network access."""

import json
import sys


MODE = next(
    (
        arg.removeprefix("--test-mode=")
        for arg in sys.argv[1:]
        if arg.startswith("--test-mode=")
    ),
    "normal",
)

PID_FILE = next(
    (
        arg.removeprefix("--pid-file=")
        for arg in sys.argv[1:]
        if arg.startswith("--pid-file=")
    ),
    None,
)

if PID_FILE:
    with open(PID_FILE, "w", encoding="utf-8") as pid_file:
        pid_file.write(str(__import__("os").getpid()))


def send(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def tool_result(request_id):
    send({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "branches": [
                            {
                                "name": "main",
                                "sha": "abc123",
                                "protected": True,
                            }
                        ]
                    }),
                }
            ],
            "isError": False,
        },
    })


def main():
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = message.get("method")
        request_id = message.get("id")

        if method == "notifications/initialized":
            continue

        if method == "initialize":
            if MODE == "hang-init":
                continue
            send({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "fake-github-mcp",
                        "version": "1.0.0",
                    },
                },
            })
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": request_id, "result": {}})
        elif method == "tools/list":
            send({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "list_branches",
                            "description": "List branches for a repository.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "owner": {"type": "string"},
                                    "repo": {"type": "string"},
                                },
                                "required": ["owner", "repo"],
                            },
                        }
                    ]
                },
            })
        elif method == "tools/call":
            if MODE == "hang-call":
                continue

            params = message.get("params", {})
            if params.get("name") != "list_branches":
                send({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": "Tool not found",
                    },
                })
            else:
                tool_result(request_id)
        elif request_id is not None:
            send({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": "Method not found",
                },
            })


if __name__ == "__main__":
    main()
