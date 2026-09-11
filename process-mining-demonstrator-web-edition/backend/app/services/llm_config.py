"""Single source of truth for *"which LLM should this request use?"*.

Precedence, highest first:

  1. the active connection's **own** LLM       — a per-connection override
  2. the global **default** (admin → Reporting) — the fallback for connections with none
  3. nothing configured                         — the caller surfaces "configure an LLM"

Everything is read **live** from the security store on each call, so editing a model
in the admin takes effect on the next request — no reconnect, no cached snapshot. Every
LLM consumer (the AI report today; chat / actions later) resolves through here so the
precedence lives in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import LLMServer
from ..store.security import store as security_store


@dataclass(frozen=True)
class ResolvedLLM:
    """The effective LLM for a request, plus where it came from (for UI display)."""

    url: str
    key: str
    model: str
    source: str  # "connection" | "global" | "none"
    label: str  # human-readable, e.g. "connection 'Sales Exasol'" or "global default"

    @property
    def configured(self) -> bool:
        return self.source != "none" and bool(self.url.strip())

    def as_server(self) -> LLMServer | None:
        """An `LLMServer` for the reachability probe, or None when nothing is set."""
        if not self.configured:
            return None
        return LLMServer(serverURL=self.url, apiKey=self.key, model=self.model)


def connection_llm_server(
    conn_id: str | None, *, with_secret: bool = True
) -> LLMServer | None:
    """The connection's **own** LLM (no global fallback), read fresh from the store.
    Returns None when the connection is unknown or carries no LLM URL."""
    if not conn_id:
        return None
    conn = security_store.get_connection(conn_id, with_secrets=with_secret)
    if conn is None or not (conn.llm_url or "").strip():
        return None
    return LLMServer(
        id=conn.id,
        name=conn.name,
        serverURL=conn.llm_url,
        apiKey=conn.llm_api_key if with_secret else "",
        model=conn.llm_model or "",
    )


def resolve_llm(db, *, with_secret: bool = True) -> ResolvedLLM:
    """The effective LLM for `db`'s active connection: per-connection override, else the
    global default, else none. `db` is a DatabaseManager; its `active_llm_server` already
    yields the connection's own LLM fresh (admin-connection *or* legacy-profile path)."""
    own = db.active_llm_server if db is not None else None
    if own is not None and own.serverURL.strip():
        return ResolvedLLM(
            url=own.serverURL,
            key=own.apiKey if with_secret else "",
            model=own.model or "",
            source="connection",
            label=f"connection {own.name!r}" if own.name else "connection LLM",
        )

    cfg = security_store.report_config(with_secret=with_secret)
    if (cfg.get("llmUrl") or "").strip():
        return ResolvedLLM(
            url=cfg["llmUrl"],
            key=cfg.get("llmKey", "") if with_secret else "",
            model=cfg.get("llmModel", "") or "",
            source="global",
            label="global default LLM",
        )

    return ResolvedLLM(url="", key="", model="", source="none", label="")
