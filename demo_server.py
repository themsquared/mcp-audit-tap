#!/usr/bin/env python3
"""A toy stdio MCP server. Simulates a personal-messaging tool (the shape of a
"free WhatsApp MCP server") so mcp-audit-tap has something realistic to watch.

Not a real WhatsApp integration. The returned messages are hardcoded fixtures
that happen to contain a phone number and an email address, standing in for
the kind of personal content a real messaging MCP server would forward.

Speaks JSON-RPC 2.0 over stdio, one message per line (no Content-Length
framing), which is the minimal shape this demo needs to exercise a tap.
"""
import json
import sys

TOOLS = [
    {
        "name": "read_latest_messages",
        "description": "Read the latest messages from the connected account.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    }
]

FIXTURE_MESSAGES = [
    {"from": "Jordan", "text": "Running late, call me at 555-867-5309 if plans change"},
    {"from": "Sam", "text": "Sent you the invoice, reply to sam.price@example.com"},
    {"from": "Riley", "text": "See you at 7"},
]


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(req):
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2025-06-18",
                "serverInfo": {"name": "demo-messaging-server", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = req.get("params", {})
        if params.get("name") == "read_latest_messages":
            lines = [f'{m["from"]}: {m["text"]}' for m in FIXTURE_MESSAGES]
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": "\n".join(lines)}]},
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": "unknown tool"}], "isError": True},
        }

    if req_id is not None:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"unknown method {method}"}}
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            send(resp)


if __name__ == "__main__":
    main()
