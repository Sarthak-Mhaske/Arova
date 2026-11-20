"""stdio MCP server: five tools and one resource.

Handles both protocol eras (the initialize handshake and server/discover).
stdout belongs to the protocol, so all logging goes to stderr.
"""
from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Dict, List, Optional

from deskmark import __version__, SCHEMA_ID
from deskmark import store
from deskmark.capture import capture
from deskmark.errors import DeskmarkError
from deskmark.packet import DEFAULT_BUDGET_CHARS, render, render_json
from deskmark.restore import plan as build_plan

SERVER_NAME = "deskmark"
SUPPORTED_VERSIONS = ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26"]
DEFAULT_VERSION = "2025-06-18"

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "resume_latest",
        "description": (
            "Read the most recent Deskmark resume point as a compact context packet. "
            "Call this at the start of a session, or whenever the user refers to "
            "'what I was doing', 'where we left off', or 'yesterday'. The packet "
            "contains the repo state, files in flight, tabs, shells, running agents, "
            "and the recorded why/next-step, with staleness marked."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "budget_chars": {"type": "integer", "minimum": 500, "maximum": 12000,
                                 "default": DEFAULT_BUDGET_CHARS},
            },
        },
    },
    {
        "name": "resume_point_save",
        "description": (
            "Save a resume point of the current working state before context is lost "
            "(end of session, context compaction, handoff to another agent). Captures "
            "git state, files, browser tabs, shells and running agents locally. "
            "Prefer naming points after the intent, e.g. 'checkout-idempotency'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "short intent-shaped name"},
                "cwd": {"type": "string", "description": "project directory (defaults to server cwd)"},
                "note": {"type": "string", "description": "human note: why this work exists"},
                "next_step": {"type": "string", "description": "the single next action"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "resume_points_list",
        "description": "List saved resume points, newest first, with age and staleness.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
        },
    },
    {
        "name": "resume_point_get",
        "description": "Fetch one resume point by id or name, as a packet (default) or raw JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "resume point id or name"},
                "format": {"type": "string", "enum": ["packet", "json"], "default": "packet"},
                "budget_chars": {"type": "integer", "minimum": 500, "maximum": 12000,
                                 "default": DEFAULT_BUDGET_CHARS},
            },
            "required": ["ref"],
        },
    },
    {
        "name": "resume_point_plan",
        "description": (
            "Show what restoring a resume point would open (editor, files, tabs, shells). "
            "Read-only: nothing is launched and no recorded command is ever executed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
    },
]


def _ok(msg_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _text(payload: str, is_error: bool = False) -> Dict[str, Any]:
    result: Dict[str, Any] = {"content": [{"type": "text", "text": payload}]}
    if is_error:
        result["isError"] = True
    return result


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if name == "resume_latest":
            entry = store.latest()
            if not entry:
                return _text("No resume points saved yet. Run `deskmark save <name>` first.", True)
            point = store.load(entry["id"])
            return _text(render(point, int(arguments.get("budget_chars", DEFAULT_BUDGET_CHARS))))

        if name == "resume_point_save":
            result = capture(
                name=str(arguments.get("name") or "untitled"),
                cwd=arguments.get("cwd") or None,
                note=str(arguments.get("note") or ""),
                next_step=str(arguments.get("next_step") or ""),
            )
            path = store.save(result.point)
            payload = {
                "saved": result.point.id,
                "name": result.point.name,
                "path": path,
                "size_bytes": result.point.size_bytes(),
                "summary": result.point.describe(),
                "warnings": result.warnings,
            }
            return _text(json.dumps(payload, indent=2))

        if name == "resume_points_list":
            limit = int(arguments.get("limit", 10))
            entries = store.list_points()[:limit]
            if not entries:
                return _text("No resume points saved yet.")
            lines = []
            for entry in entries:
                stale = " STALE" if entry.get("stale") else ""
                lines.append(
                    f"{entry['id']}  {entry['name']}  "
                    f"({int(entry.get('age_seconds', 0) // 60)}m old){stale}\n"
                    f"    {entry.get('summary', '')}"
                )
            return _text("\n".join(lines))

        if name == "resume_point_get":
            ref = str(arguments.get("ref") or "")
            point = store.load(ref)
            if arguments.get("format") == "json":
                return _text(render_json(point))
            return _text(render(point, int(arguments.get("budget_chars", DEFAULT_BUDGET_CHARS))))

        if name == "resume_point_plan":
            point = store.load(str(arguments.get("ref") or ""))
            plan_obj = build_plan(point)
            return _text(json.dumps(plan_obj.to_dict(), indent=2))

        return _text(f"Unknown tool: {name}", True)
    except Exception as exc:
        return _text(f"{name} failed: {exc}", True)


def handle(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle one JSON-RPC message. Returns None for notifications."""
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "initialize":
        requested = params.get("protocolVersion") or DEFAULT_VERSION
        return _ok(msg_id, {
            "protocolVersion": requested if requested in SUPPORTED_VERSIONS else DEFAULT_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "instructions": (
                "Deskmark stores local resume points of work in flight. Call resume_latest at "
                "session start; call resume_point_save before the session ends or context "
                "compacts. Never invent a resume point: if none exists, say so."
            ),
        })

    if method == "server/discover":
        return _ok(msg_id, {
            "resultType": "complete",
            "supportedVersions": SUPPORTED_VERSIONS,
            "capabilities": {"tools": {}, "resources": {}},
            "_meta": {"io.modelcontextprotocol/serverInfo": {"name": SERVER_NAME, "version": __version__}},
            "ttlMs": 3_600_000,
            "cacheScope": "private",
        })

    if method == "ping":
        return _ok(msg_id, {})

    if method == "tools/list":
        return _ok(msg_id, {"tools": TOOLS})

    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        return {"jsonrpc": "2.0", "id": msg_id, "result": call_tool(name, arguments)}

    if method == "resources/list":
        resources = []
        for entry in store.list_points()[:25]:
            resources.append({
                "uri": f"deskmark://resume/{entry['id']}",
                "name": entry.get("name", "resume point"),
                "description": entry.get("summary", ""),
                "mimeType": "text/markdown",
            })
        return _ok(msg_id, {"resources": resources})

    if method == "resources/read":
        uri = str(params.get("uri") or "")
        prefix = "deskmark://resume/"
        if uri.startswith(prefix):
            # a client can ask for anything, "../../etc/passwd" included.
            # whatever we can't resolve is a bad parameter, not an internal
            # error, and never a path.
            try:
                point = store.load(uri[len(prefix):])
            except DeskmarkError as exc:
                return _err(msg_id, -32602, f"unknown resource: {uri} ({exc.message})")
            return _ok(msg_id, {"contents": [{"uri": uri, "mimeType": "text/markdown",
                                              "text": render(point)}]})
        return _err(msg_id, -32602, f"unknown resource: {uri}")

    if method == "prompts/list":
        return _ok(msg_id, {"prompts": []})

    if msg_id is None:
        return None
    return _err(msg_id, -32601, f"method not found: {method}")


def serve(stdin=None, stdout=None) -> None:
    """Newline-delimited JSON-RPC over stdio. Nothing but protocol on stdout."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    log = lambda text: print(f"[deskmark-mcp] {text}", file=sys.stderr, flush=True)

    log(f"serving {SCHEMA_ID} v{__version__} ({len(TOOLS)} tools)")
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError as exc:
            stdout.write(json.dumps(_err(None, -32700, f"parse error: {exc}")) + "\n")
            stdout.flush()
            continue
        if isinstance(message, list):          # legacy batch
            replies = [r for r in (handle(m) for m in message) if r]
            if replies:
                stdout.write(json.dumps(replies) + "\n")
                stdout.flush()
            continue
        try:
            reply = handle(message)
        except Exception:                       # never die on a bad request
            log(traceback.format_exc())
            reply = _err(message.get("id"), -32603, "internal error")
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


if __name__ == "__main__":  # pragma: no cover
    serve()
