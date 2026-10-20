# mcp-audit-tap

> 📖 **Read the write-up:** [MCP Audit Tap: See What a Third-Party Server Actually Sends](https://webofmike.com/mcp-audit-tap/)

A minimal, protocol-agnostic wiretap for a stdio MCP server. Run any MCP
server behind it instead of running the server directly, and get a
structured audit log of every `tools/call` request and result, with
PII-pattern flags, before you decide whether to trust what the server sends.

## Why

On 2026-10-19 a [Show HN post](https://news.ycombinator.com/item?id=50145715)
for a "WhatsApp MCP server running free on Cloudflare" hit 124 points and 69
comments in under 16 hours. The thread spent most of its length arguing about
whether the tool is actually free, whether using it risks a WhatsApp account
ban, and whether decrypting end-to-end-encrypted messages and uploading them
to an LLM is a privacy problem. Those are all real questions. None of them is
answerable by reading the thread, because none of the commenters had a way to
see what the tool actually sends. The same day, a [separate HN thread](https://news.ycombinator.com/item?id=50145507) asking
"if you don't run your own LLM proxy, how do you know what's going on"
collected 213 points and 154 comments arguing the same gap from the
infrastructure side.

The common failure in both threads: people evaluate a third-party MCP server
by reading its README and its star count, not by watching what crosses the
wire. `mcp-audit-tap` is the smallest possible version of watching the wire.
It does not block anything by default. It gives you a log.

## What it is not

This is not a production MCP gateway. It does not do authentication,
rate limiting, or policy enforcement with CEL expressions. For that, see
[agentgateway](https://agentgateway.dev)'s MCP guardrails, which run inside a
real gateway and can reject or mask a `tools/call` before the tool executes.
This repo is the step before that decision: see what a server sends, before
you decide it needs a policy.

## Architecture

```
MCP client  <-- stdio -->  audit_tap.py  <-- stdio -->  the real MCP server
                                |
                                v
                            audit.log (JSONL)
```

`audit_tap.py` spawns the real MCP server as a child process and relays
every line between your client and the server unchanged. In parallel, it
parses each JSON-RPC message:

- A `tools/call` request (client to server) is logged with the tool name and
  arguments.
- The matching result (server to client, matched by JSON-RPC `id`) is scanned
  against a small set of regex patterns (phone numbers, email addresses so
  far; extend `PII_PATTERNS` in `audit_tap.py` for more) and logged with
  whatever flags matched.
- With `--redact`, a flagged result is rewritten in place (`[REDACTED:phone]`,
  `[REDACTED:email]`) before it reaches the client, and the tap logs that it
  did so. Without `--redact` (the default), nothing forwarded is changed;
  the tap only observes.

That `--redact` flag is the entire distance between "audit tool" and
"policy enforcement point". It's one `if` statement in `audit_tap.py`. The
point of this repo is that the hard part was never the redaction, it was
noticing there was content worth redacting in the first place.

## Quickstart

Requires Python 3.9+, no third-party dependencies.

```bash
git clone https://github.com/themsquared/mcp-audit-tap.git
cd mcp-audit-tap
```

Run the toy MCP server directly first, to see what it returns with nothing
watching:

```bash
python3 test_harness.py -- python3 demo_server.py
```

The `tools/call` result includes a phone number and an email address in
plain text, standing in for the kind of personal content a real messaging
MCP server would forward to whatever LLM is calling it.

Now run the same call through the tap, audit-only:

```bash
python3 test_harness.py -- python3 audit_tap.py --log audit.log -- python3 demo_server.py
cat audit.log
```

The response the client receives is identical. `audit.log` now has a record
of the call and a `flags` field naming what it found:

```json
{"ts": "...", "direction": "client->server", "event": "tools/call request", "tool": "read_latest_messages", "arguments": {}}
{"ts": "...", "direction": "server->client", "event": "tools/call result", "tool": "read_latest_messages", "flags": ["phone", "email"], "preview": "Jordan: Running late, call me at 555-867-5309 if plans change..."}
```

Now turn the same tap into an enforcement point:

```bash
python3 test_harness.py -- python3 audit_tap.py --redact --log audit.log -- python3 demo_server.py
```

The `tools/call` result the client receives now reads `call me at
[REDACTED:phone]`, and `audit.log` has a third line recording that the tap
redacted it before forwarding.

### Pointing it at a real MCP server

Replace `python3 demo_server.py` with the real server's launch command. If
your MCP client config currently runs:

```json
{"command": "python3", "args": ["-m", "some_mcp_server"]}
```

point it at the tap instead:

```json
{"command": "python3", "args": ["audit_tap.py", "--log", "audit.log", "--", "python3", "-m", "some_mcp_server"]}
```

Everything the client sends and the server returns still flows through
unchanged (unless you pass `--redact`); you just get `audit.log` as a side
effect.

## Extending the PII patterns

`PII_PATTERNS` in `audit_tap.py` is a plain dict of `name -> compiled regex`.
Add entries for whatever your threat model cares about (SSNs, API key
shapes, internal hostnames). Each match adds its name to the result's
`flags` list and, with `--redact`, gets substituted with `[REDACTED:<name>]`.

## License

Apache-2.0. See `LICENSE`.

## Topics

`mcp` `model-context-protocol` `ai-agents` `ai-security` `observability`
