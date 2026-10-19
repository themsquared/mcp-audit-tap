#!/usr/bin/env python3
"""mcp-audit-tap: a protocol-agnostic wiretap for a stdio MCP server.

Puts an MCP server behind this tap instead of running it directly. The tap
spawns the real server as a child process, relays every JSON-RPC message
between client and server unchanged, and in parallel writes a structured
audit line for every tools/call request and the result that comes back for
it, flagging content that matches a small set of PII patterns.

Usage:
    python3 audit_tap.py [--redact] [--log PATH] -- <server command...>

Example:
    python3 audit_tap.py --redact -- python3 demo_server.py

With --redact, flagged substrings in a tool result are replaced with
[REDACTED:<type>] before they reach the client. Without it (the default),
the tap only observes and logs; nothing it forwards is altered. That
distinction is the point: you can run this in audit-only mode to see what a
server actually sends before you decide anything should be blocked.
"""
import argparse
import json
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone

PII_PATTERNS = {
    "phone": re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def scan(text):
    flags = []
    for kind, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            flags.append(kind)
    return flags


def redact(text):
    for kind, pattern in PII_PATTERNS.items():
        text = pattern.sub(f"[REDACTED:{kind}]", text)
    return text


class AuditTap:
    def __init__(self, log_path, do_redact):
        self.log_path = log_path
        self.do_redact = do_redact
        self.pending_calls = {}  # id -> tool name, for matching responses to requests
        self.lock = threading.Lock()

    def write_log(self, entry):
        with self.lock, open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def on_client_to_server(self, msg):
        if msg.get("method") == "tools/call":
            params = msg.get("params", {})
            tool = params.get("name")
            args = params.get("arguments", {})
            with self.lock:
                self.pending_calls[msg.get("id")] = tool
            self.write_log({
                "ts": now(),
                "direction": "client->server",
                "event": "tools/call request",
                "tool": tool,
                "arguments": args,
            })
        return msg

    def on_server_to_client(self, msg):
        req_id = msg.get("id")
        with self.lock:
            tool = self.pending_calls.pop(req_id, None)
        result = msg.get("result")
        if tool and result and "content" in result:
            texts = [c.get("text", "") for c in result["content"] if c.get("type") == "text"]
            full_text = "\n".join(texts)
            flags = scan(full_text)
            self.write_log({
                "ts": now(),
                "direction": "server->client",
                "event": "tools/call result",
                "tool": tool,
                "flags": flags,
                "preview": full_text[:200],
            })
            if flags and self.do_redact:
                for c in result["content"]:
                    if c.get("type") == "text":
                        c["text"] = redact(c["text"])
                self.write_log({
                    "ts": now(),
                    "direction": "tap",
                    "event": "redacted before forwarding",
                    "tool": tool,
                    "flags": flags,
                })
        return msg


def pump(src, dst, on_line, line_sink):
    for raw in iter(src.readline, ""):
        if not raw:
            break
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            msg = json.loads(stripped)
        except json.JSONDecodeError:
            dst.write(raw)
            dst.flush()
            continue
        msg = on_line(msg)
        line_sink(json.dumps(msg) + "\n")
    dst.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--redact", action="store_true", help="rewrite flagged content before forwarding to the client")
    parser.add_argument("--log", default="audit.log", help="audit log path (default: audit.log)")
    parser.add_argument("server_cmd", nargs=argparse.REMAINDER, help="the real MCP server command, after --")
    args = parser.parse_args()

    cmd = args.server_cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        parser.error("no server command given (usage: audit_tap.py [--redact] -- <server command...>)")

    tap = AuditTap(args.log, args.redact)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def to_server(raw):
        proc.stdin.write(raw)
        proc.stdin.flush()

    def to_client(raw):
        sys.stdout.write(raw)
        sys.stdout.flush()

    t1 = threading.Thread(target=pump, args=(sys.stdin, proc.stdin, tap.on_client_to_server, to_server), daemon=True)
    t2 = threading.Thread(target=pump, args=(proc.stdout, sys.stdout, tap.on_server_to_client, to_client), daemon=True)
    t1.start()
    t2.start()
    proc.wait()
    t2.join(timeout=1)


if __name__ == "__main__":
    main()
