"""MCP server — JSON-RPC dispatch, auth guardrails and the read-only tool wiring.

The module lives outside the `app` package (mcp/server.py, a sibling surface), so it is
loaded by path. Auth and DB access are exercised with monkeypatched store methods — no
Authentik and no Exasol needed.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_PATH = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
_spec = importlib.util.spec_from_file_location("mcp_server", _PATH)
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)


def _run(coro):
    return asyncio.run(coro)


class _Req:
    """Minimal stand-in for a Starlette Request (only what _authenticate reads)."""

    def __init__(self, headers=None):
        self.headers = headers or {}
        self.base_url = "https://host:8493/"


USER = SimpleNamespace(username="alice", is_enabled=True)


# ── JSON-RPC dispatch (no user/DB needed) ─────────────────────────────────────


def test_initialize_reports_capabilities_and_server_info():
    out = _run(mcp._dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, USER))
    assert out["result"]["serverInfo"]["name"] == "process-mining"
    assert "tools" in out["result"]["capabilities"]


def test_tools_list_exposes_the_read_only_tools():
    out = _run(mcp._dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, USER))
    names = {t["name"] for t in out["result"]["tools"]}
    assert {"list_connections", "get_process_map", "get_variants", "get_metadata"} <= names
    # Every tool advertises an object input schema.
    assert all(t["inputSchema"]["type"] == "object" for t in out["result"]["tools"])


def test_notification_returns_no_response():
    assert _run(mcp._dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}, USER)) is None


def test_unknown_method_and_unknown_tool_are_errors():
    m = _run(mcp._dispatch({"jsonrpc": "2.0", "id": 3, "method": "does/not/exist"}, USER))
    assert m["error"]["code"] == -32601
    t = _run(mcp._dispatch(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}}, USER))
    assert t["error"]["code"] == -32602


def test_tools_call_list_connections(monkeypatch):
    conns = [SimpleNamespace(id="c1", name="Prod", schema="PM", comment="")]
    monkeypatch.setattr(mcp.store, "connections_for_user", lambda username: conns)
    out = _run(mcp._dispatch(
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "list_connections", "arguments": {}}}, USER))
    assert out["result"]["isError"] is False
    import json
    payload = json.loads(out["result"]["content"][0]["text"])
    assert payload == [{"id": "c1", "name": "Prod", "schema": "PM", "comment": ""}]


# ── filter helpers ────────────────────────────────────────────────────────────


def test_filter_spec_builds_from_arguments():
    spec = mcp._filter_spec({"sampleSet": "SAMPLE_1", "includedSteps": ["A"], "meta1": "x"})
    assert spec.sampleSet.value == "SAMPLE_1"
    assert spec.includedSteps == ["A"] and spec.meta1 == "x"


def test_bad_sample_set_is_a_tool_error():
    with pytest.raises(mcp.ToolError):
        mcp._sample_of({"sampleSet": "BOGUS"})


# ── authentication guardrails ─────────────────────────────────────────────────


def test_auth_requires_configured_oauth(monkeypatch):
    monkeypatch.setattr(mcp.store, "mcp_settings", lambda: {
        "issuer": "", "jwksUri": "", "audience": "", "requiredGroup": "", "usernameClaim": "preferred_username"})
    with pytest.raises(mcp.AuthError) as ei:
        _run(mcp._authenticate(_Req()))
    assert ei.value.status == 503


def test_auth_challenges_when_no_bearer(monkeypatch):
    monkeypatch.setattr(mcp.store, "mcp_settings", lambda: {
        "issuer": "https://a/", "jwksUri": "https://a/jwks", "audience": "",
        "requiredGroup": "", "usernameClaim": "preferred_username"})
    with pytest.raises(mcp.AuthError) as ei:
        _run(mcp._authenticate(_Req(headers={})))
    assert ei.value.status == 401 and ei.value.challenge is True
