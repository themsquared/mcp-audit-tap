#!/usr/bin/env python3
"""Acts as a minimal MCP client so the demo runs end to end with no external
agent host. Spawns the given command (normally the tap, wrapping the demo
server), sends initialize, tools/list, and a tools/call, and prints what
comes back.

Usage:
    python3 test_harness.py -- python3 audit_tap.py --redact -- python3 demo_server.py
"""
import json
import subprocess
import sys


def send(proc, msg):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()


def recv(proc):
    line = proc.stdout.readline()
    return json.loads(line) if line.strip() else None


def main():
    cmd = sys.argv[1:]
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("usage: test_harness.py -- <command to run as the MCP endpoint>", file=sys.stderr)
        sys.exit(1)

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    print("initialize ->", recv(proc))

    send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    print("tools/list ->", recv(proc))

    send(proc, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "read_latest_messages", "arguments": {}},
    })
    print("tools/call ->", json.dumps(recv(proc), indent=2))

    proc.stdin.close()
    proc.wait(timeout=5)


if __name__ == "__main__":
    main()
