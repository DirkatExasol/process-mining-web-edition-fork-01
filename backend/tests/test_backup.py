"""Backup / restore tests — the AES-256-GCM envelope, summary, and the
connection-splitting logic. Interchangeable with the macOS app's backups.

Restore is tested against a temporary settings store so the developer's real
`data/settings.sqlite3` is never touched.
"""

from __future__ import annotations

import json

import pytest

from app.services import backup


# ── Crypto envelope ───────────────────────────────────────────────────────────


def test_encrypt_decrypt_round_trip():
    payload = backup.encode({"version": 1, "connections": [], "dataDefaults": {}})
    envelope = backup.encrypt(payload, "hunter2")
    assert backup.is_encrypted(envelope)
    assert json.loads(backup.decrypt(envelope, "hunter2")) == json.loads(payload)


def test_decrypt_with_wrong_password_raises():
    envelope = backup.encrypt(backup.encode({"version": 1}), "correct")
    with pytest.raises(backup.BackupError):
        backup.decrypt(envelope, "wrong")


def test_is_encrypted_detects_plain_json():
    assert backup.is_encrypted(backup.encode({"version": 1})) is False


def test_invalid_envelope_raises():
    with pytest.raises(backup.BackupError):
        backup.decrypt(b"{not json", "pw")


# ── Summary ───────────────────────────────────────────────────────────────────


def test_summarize_reports_contents():
    payload = {
        "createdAt": "2024-01-01T00:00:00",
        "includesPasswords": True,
        "includesUsername": True,
        "includesLlmApiKey": False,
        "connections": [{"name": "Prod"}, {"name": "Dev"}],
        "stringDefaults": {"norms_metric_P1": "Count", "llm_prompt_P2": "..."},
        "dataDefaults": {
            "layout_P1_A-Chart": "e30=",
            "norms_P1": "e30=",
            "happyPaths_P1": "e30=",
            "filterGroups_P2": "e30=",
        },
    }
    summary = backup.summarize(payload)
    assert summary["connectionCount"] == 2
    assert summary["projectCount"] == 2  # P1 and P2
    assert summary["hasLayouts"] is True
    assert summary["hasNorms"] is True
    assert summary["hasHappyPaths"] is True
    assert summary["hasFilterGroups"] is True
    assert summary["connectionNames"] == ["Prod", "Dev"]


# ── Connection splitting on restore ──────────────────────────────────────────


class _MemoryStore:
    """Minimal in-memory stand-in for the SQLite settings store."""

    def __init__(self):
        self.kv: dict[str, object] = {}
        self.secrets: dict[str, str] = {}

    def get(self, key, default=None):
        return self.kv.get(key, default)

    def set(self, key, value):
        self.kv[key] = value

    def delete(self, key):
        self.kv.pop(key, None)

    def all(self):
        return dict(self.kv)

    def get_secret(self, key):
        return self.secrets.get(key, "")

    def set_secret(self, key, value):
        self.secrets[key] = value

    def delete_secret(self, key):
        self.secrets.pop(key, None)


@pytest.fixture
def memory_store(monkeypatch):
    store = _MemoryStore()
    # Redirect every module that reached for the global store.
    import app.db.manager as manager_mod
    import app.services.backup as backup_mod

    monkeypatch.setattr(manager_mod, "store", store)
    monkeypatch.setattr(backup_mod, "store", store)
    return store


def test_restore_splits_flat_connection_into_servers_and_pairing(memory_store):
    from app.db.manager import DatabaseManager, _pw_key

    db = DatabaseManager()
    payload = {
        "version": 1,
        "includesUsername": True,
        "includesPasswords": True,
        "includesLlmApiKey": True,
        "appSettings": {},
        "connections": [
            {
                "id": "PROF-1",
                "name": "Prod",
                "host": "db.example.com",
                "port": 8563,
                "username": "sys",
                "schema": "PM",
                "useTLS": True,
                "certModeRaw": "verify",
                "fingerprint": "",
                "minRSAKeySizeBits": 2048,
                "llmServerURL": "http://localhost:1234/v1",
                "llmModel": "qwen3",
                "llmApiKey": "sk-test",
                "password": "secret",
            }
        ],
        "activeProfileId": "PROF-1",
        "stringDefaults": {"llm_prompt_P1": "Analyse."},
        "dataDefaults": {},
    }

    backup.restore(db, payload, {})

    servers = db.database_servers
    assert len(servers) == 1
    assert servers[0].id == "PROF-1"  # id preserved so the password key matches
    assert servers[0].host == "db.example.com"
    assert servers[0].username == "sys"

    profiles = db.profiles
    assert profiles[0].databaseServerId == "PROF-1"
    assert profiles[0].llmServerId is not None

    llm = db.llm_servers
    assert llm[0].serverURL == "http://localhost:1234/v1"
    assert llm[0].model == "qwen3"
    assert llm[0].apiKey == "sk-test"

    # Password stored in the encrypted vault under the preserved id.
    assert memory_store.get_secret(_pw_key("PROF-1")) == "secret"
    # A per-project string default came across too.
    assert memory_store.get("llm_prompt_P1") == "Analyse."


def test_restore_without_llm_creates_no_llm_server(memory_store):
    from app.db.manager import DatabaseManager

    db = DatabaseManager()
    payload = {
        "version": 1,
        "includesUsername": True,
        "includesPasswords": False,
        "includesLlmApiKey": False,
        "appSettings": {},
        "connections": [
            {
                "id": "PROF-2",
                "name": "DB only",
                "host": "db.example.com",
                "port": 8563,
                "schema": "",
                "useTLS": False,
                "certModeRaw": "verify",
                "fingerprint": "",
                "minRSAKeySizeBits": 2048,
                "llmServerURL": "",
                "llmModel": "",
            }
        ],
        "activeProfileId": None,
        "stringDefaults": {},
        "dataDefaults": {},
    }
    backup.restore(db, payload, {})
    assert db.llm_servers == []
    assert db.profiles[0].llmServerId is None
    assert db.profiles[0].databaseServerId == "PROF-2"
