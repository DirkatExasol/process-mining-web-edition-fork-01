"""Backup / restore — wire-compatible with BackupManager.swift.

A backup taken from the macOS app can be restored here and vice versa:
same JSON payload shape, same envelope, same crypto
(PBKDF2-HMAC-SHA256 · 100 000 iterations · 32-byte key · 16-byte salt,
AES-256-GCM with the 12-byte nonce prepended to ciphertext + 16-byte tag).
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..db.manager import (
    KEY_ACTIVE_PROFILE,
    KEY_DB_SERVERS,
    KEY_LLM_SERVERS,
    KEY_PROFILES,
    DatabaseManager,
    _pw_key,
)
from ..models import ConnectionProfile, DatabaseServer, LLMServer, new_id
from ..store.settings import store

PBKDF2_ROUNDS = 100_000
SALT_BYTES = 16
NONCE_BYTES = 12

BACKUP_VERSION = 1

# UserDefaults key prefixes whose values were Strings / Data in the Swift app.
STRING_PREFIXES = ("norms_metric_", "llm_prompt_")
DATA_PREFIXES = (
    "layout_",
    "graph.collapsedGroups_",
    "norms_",
    "happyPaths_",
    "filterGroups_",
)

_SETTINGS_KEYS = {
    "appTheme": ("app.theme", "system"),
    "graphStartMode": ("graph.startMode", "expanded"),
    "sliderMode": ("slider.mode", "Range"),
    "showGrouping": ("processmap.showGrouping", True),
    "showNodeDescriptions": ("processmap.showNodeDescriptions", True),
    "kpiExpanded": ("processmap.kpiExpanded", True),
    "valveOpen": ("abComparison.valveOpen", True),
    "sidebarProjectsExpanded": ("sidebar.projectsExpanded", True),
    "sidebarFiltersExpanded": ("sidebar.filtersExpanded", True),
    "sidebarFiltersDateExpanded": ("sidebar.filtersDateExpanded", True),
    "sidebarFiltersMetaExpanded": ("sidebar.filtersMetaExpanded", False),
    "sidebarFiltersIncludeExpanded": ("sidebar.filtersIncludeExpanded", False),
    "sidebarFiltersExcludeExpanded": ("sidebar.filtersExcludeExpanded", False),
    "sidebarFiltersStepsExpanded": ("sidebar.filtersStepsExpanded", False),
    "sidebarFiltersJourneyTimeExpanded": ("sidebar.filtersJourneyTimeExpanded", False),
    "sidebarFiltersScoreExpanded": ("sidebar.filtersScoreExpanded", False),
    "sidebarMetricsExpanded": ("sidebar.metricsExpanded", True),
    "sidebarConfigExpanded": ("sidebar.configExpanded", True),
    "sidebarConfigStepsExpanded": ("sidebar.configStepsExpanded", True),
}


class BackupError(RuntimeError):
    pass


# ── crypto ───────────────────────────────────────────────────────────────────


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ROUNDS,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt(payload: bytes, password: str) -> bytes:
    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(_derive_key(password, salt)).encrypt(nonce, payload, None)
    envelope = {
        "encrypted": True,
        "salt": base64.b64encode(salt).decode("ascii"),
        # CryptoKit's `combined` representation: nonce ‖ ciphertext ‖ tag
        "ciphertext": base64.b64encode(nonce + ciphertext).decode("ascii"),
    }
    return json.dumps(envelope, indent=2, sort_keys=True).encode("utf-8")


def decrypt(data: bytes, password: str) -> bytes:
    try:
        envelope = json.loads(data)
        salt = base64.b64decode(envelope["salt"])
        combined = base64.b64decode(envelope["ciphertext"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise BackupError("The backup file format is invalid or corrupted.") from exc

    nonce, ciphertext = combined[:NONCE_BYTES], combined[NONCE_BYTES:]
    try:
        return AESGCM(_derive_key(password, salt)).decrypt(nonce, ciphertext, None)
    except Exception as exc:  # noqa: BLE001
        raise BackupError(
            "Incorrect password — the backup could not be decrypted."
        ) from exc


def is_encrypted(data: bytes) -> bool:
    try:
        return json.loads(data).get("encrypted") is True
    except (json.JSONDecodeError, AttributeError):
        return False


# ── export ───────────────────────────────────────────────────────────────────


def export_payload(
    db: DatabaseManager,
    *,
    include_passwords: bool,
    include_username: bool,
    include_llm_api_key: bool,
) -> dict[str, Any]:
    string_defaults: dict[str, str] = {}
    data_defaults: dict[str, str] = {}

    for key, value in store.all().items():
        if key.startswith(STRING_PREFIXES):
            if isinstance(value, str):
                string_defaults[key] = value
        elif key.startswith(DATA_PREFIXES) and not key.startswith("norms_metric_"):
            # The Swift side stored these as JSON-encoded Data; base64 keeps the
            # backup byte-identical in shape.
            raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
            data_defaults[key] = base64.b64encode(raw).decode("ascii")

    connections = []
    for profile in db.profiles:
        db_server = db.database_server(profile)
        llm_server = db.llm_server(profile)
        connections.append(
            {
                "id": profile.id,
                "name": profile.name,
                "comment": profile.comment or None,
                "host": db_server.host if db_server else "",
                "port": db_server.port if db_server else 8563,
                "username": (db_server.username if db_server else "")
                if include_username
                else None,
                "schema": db_server.schema_ if db_server else "",
                "useTLS": db_server.useTLS if db_server else False,
                "certModeRaw": db_server.certModeRaw if db_server else "verify",
                "fingerprint": db_server.fingerprint if db_server else "",
                "minRSAKeySizeBits": db_server.minRSAKeySizeBits if db_server else 2048,
                "llmServerURL": llm_server.serverURL if llm_server else "",
                "llmApiKey": (llm_server.apiKey if llm_server else "")
                if include_llm_api_key
                else None,
                "llmModel": llm_server.model if llm_server else "",
                "password": db.password(db_server.id if db_server else profile.id)
                if include_passwords
                else None,
            }
        )

    app_settings = {
        field: store.get(key, default) for field, (key, default) in _SETTINGS_KEYS.items()
    }

    return {
        "version": BACKUP_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "includesPasswords": include_passwords,
        "includesUsername": include_username,
        "includesLlmApiKey": include_llm_api_key,
        "appSettings": app_settings,
        "connections": connections,
        "activeProfileId": db.active_profile_id,
        "stringDefaults": string_defaults,
        "dataDefaults": data_defaults,
    }


def encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    string_keys = payload.get("stringDefaults", {}).keys()
    data_keys = payload.get("dataDefaults", {}).keys()

    project_ids: set[str] = set()
    for key in string_keys:
        if key.startswith("norms_metric_"):
            project_ids.add(key[len("norms_metric_") :])
        elif key.startswith("llm_prompt_"):
            project_ids.add(key[len("llm_prompt_") :])
    for key in data_keys:
        if key.startswith("norms_"):
            project_ids.add(key[len("norms_") :])

    return {
        "createdAt": payload.get("createdAt"),
        "includesPasswords": payload.get("includesPasswords", False),
        "includesUsername": payload.get("includesUsername", False),
        "includesLlmApiKey": payload.get("includesLlmApiKey", False),
        "connectionCount": len(payload.get("connections", [])),
        "projectCount": len(project_ids),
        "hasLayouts": any(k.startswith("layout_") for k in data_keys),
        "hasNorms": any(k.startswith("norms_") for k in data_keys),
        "hasHappyPaths": any(k.startswith("happyPaths_") for k in data_keys),
        "hasFilterGroups": any(k.startswith("filterGroups_") for k in data_keys),
        "connectionNames": [
            c.get("name", "") for c in payload.get("connections", [])
        ],
    }


# ── restore ──────────────────────────────────────────────────────────────────

DEFAULT_RESTORE_OPTIONS = {
    "appSettings": True,
    "connections": True,
    "username": True,
    "llmApiKey": True,
    "passwords": True,
    "layouts": True,
    "norms": True,
    "happyPaths": True,
    "filterPresets": True,
}


# Secret settings keys are managed only through the dedicated (encrypted) paths;
# a restored backup must never be able to inject them into the settings store.
_SECRET_KEY_PREFIXES = ("conn_pw_", "llm_api_key_")


def _is_secret_key(key: str) -> bool:
    return key.startswith(_SECRET_KEY_PREFIXES)


def restore(
    db: DatabaseManager, payload: dict[str, Any], options: dict[str, bool]
) -> None:
    opts = {**DEFAULT_RESTORE_OPTIONS, **options}

    if opts["appSettings"]:
        settings = payload.get("appSettings") or {}
        for field, (key, default) in _SETTINGS_KEYS.items():
            store.set(key, settings.get(field, default))

    if opts["connections"]:
        _restore_connections(db, payload, opts)

    for key, value in (payload.get("stringDefaults") or {}).items():
        if _is_secret_key(key):  # never restore secrets through the settings channel
            continue
        if key.startswith("norms_metric_") and not opts["norms"]:
            continue
        store.set(key, value)

    for key, encoded in (payload.get("dataDefaults") or {}).items():
        if _is_secret_key(key):
            continue
        if key.startswith("layout_") or key.startswith("graph.collapsedGroups_"):
            if not opts["layouts"]:
                continue
        elif key.startswith("norms_") and not opts["norms"]:
            continue
        elif key.startswith("happyPaths_") and not opts["happyPaths"]:
            continue
        elif key.startswith("filterGroups_") and not opts["filterPresets"]:
            continue
        try:
            store.set(key, json.loads(base64.b64decode(encoded)))
        except (ValueError, json.JSONDecodeError):
            continue


def _restore_connections(
    db: DatabaseManager, payload: dict[str, Any], opts: dict[str, bool]
) -> None:
    """Split each flat backup record back into DB server + LLM server + pairing,
    preserving ids so stored passwords and `activeProfileId` keep matching."""
    include_username = payload.get("includesUsername", False) and opts["username"]
    include_api_key = payload.get("includesLlmApiKey", False) and opts["llmApiKey"]
    include_passwords = payload.get("includesPasswords", False) and opts["passwords"]

    db_servers = {s.id: s for s in db.database_servers}
    llm_servers = {s.id: s for s in db.llm_servers}
    profiles = {p.id: p for p in db.profiles}

    for record in payload.get("connections", []):
        pid = record.get("id") or new_id()

        server = DatabaseServer(
            id=pid,
            name=record.get("name") or record.get("host", ""),
            comment=record.get("comment") or "",
            host=record.get("host", ""),
            port=record.get("port", 8563),
            username=record.get("username") or "" if include_username else "",
            useTLS=record.get("useTLS", False),
            certModeRaw=record.get("certModeRaw", "verify"),
            fingerprint=record.get("fingerprint", ""),
            minRSAKeySizeBits=record.get("minRSAKeySizeBits") or 2048,
            **{"schema": record.get("schema", "")},
        )
        if not include_username and pid in db_servers:
            server.username = db_servers[pid].username
        db_servers[pid] = server

        if include_passwords and record.get("password"):
            store.set_secret(_pw_key(pid), record["password"])

        llm_id: str | None = None
        if record.get("llmServerURL"):
            existing = next(
                (s for s in llm_servers.values() if s.serverURL == record["llmServerURL"]),
                None,
            )
            llm = existing or LLMServer(name=f"{record.get('name', 'LLM')} LLM")
            llm.serverURL = record["llmServerURL"]
            llm.model = record.get("llmModel", "")
            if include_api_key and record.get("llmApiKey"):
                llm.apiKey = record["llmApiKey"]
            llm_servers[llm.id] = llm
            llm_id = llm.id

        profiles[pid] = ConnectionProfile(
            id=pid,
            name=record.get("name", ""),
            comment=record.get("comment") or "",
            databaseServerId=pid,
            llmServerId=llm_id,
        )

    db.database_servers = list(db_servers.values())
    db.llm_servers = list(llm_servers.values())
    db.profiles = list(profiles.values())

    if active := payload.get("activeProfileId"):
        store.set(KEY_ACTIVE_PROFILE, active)


__all__ = [
    "BackupError",
    "encrypt",
    "decrypt",
    "is_encrypted",
    "export_payload",
    "encode",
    "summarize",
    "restore",
    "KEY_DB_SERVERS",
    "KEY_LLM_SERVERS",
    "KEY_PROFILES",
]
