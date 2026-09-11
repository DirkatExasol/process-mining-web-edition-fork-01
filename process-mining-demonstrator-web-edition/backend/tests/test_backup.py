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


def test_restore_never_writes_secret_keys(memory_store):
    """A crafted backup cannot inject secret settings (conn_pw_/llm_api_key_)
    into the settings store — the restore mirrors the export/patch key filter."""
    from app.db.manager import DatabaseManager

    db = DatabaseManager()
    payload = {
        "version": 1,
        "appSettings": {},
        "connections": [],
        "stringDefaults": {
            "conn_pw_PROF-1": "injected-password",     # must be ignored
            "llm_api_key_PROF-1": "sk-injected",        # must be ignored
            "llm_prompt_P1": "legit-value",             # normal key restored
        },
        "dataDefaults": {},
    }
    backup.restore(db, payload, {})

    assert memory_store.get("conn_pw_PROF-1") is None
    assert memory_store.get("llm_api_key_PROF-1") is None
    assert memory_store.get("llm_prompt_P1") == "legit-value"  # non-secret still restored


def test_restore_only_writes_allowlisted_keys(memory_store):
    """Restore is a positive allowlist: secret keys, legacy connection metadata and
    arbitrary keys are ignored; only export's own prefixes are written."""
    from app.db.manager import DatabaseManager

    db = DatabaseManager()
    payload = {
        "version": 1,
        "appSettings": {},
        "connections": [],
        "stringDefaults": {
            "conn_pw_X": "secret",           # secret → skipped
            "llm_api_key_X": "sk-x",         # secret → skipped
            "database_servers": "junk",      # legacy metadata → skipped
            "active_profile_id": "evil",     # arbitrary → skipped
            "llm_prompt_P1": "legit-prompt", # allowlisted (rides with appSettings)
            "norms_metric_P1": "7",          # allowlisted (norms)
        },
        "dataDefaults": {"random_unknown_key": "junk"},  # not allowlisted → skipped
    }
    # connections off so _restore_connections doesn't legitimately touch those keys;
    # this isolates the settings-key allowlist.
    backup.restore(db, payload, {"connections": False})

    for skipped in (
        "conn_pw_X", "llm_api_key_X", "database_servers",
        "active_profile_id", "random_unknown_key",
    ):
        assert memory_store.get(skipped) is None, skipped
    assert memory_store.get("llm_prompt_P1") == "legit-prompt"
    assert memory_store.get("norms_metric_P1") == "7"


def test_restore_gates_llm_prompt_behind_app_settings(memory_store):
    from app.db.manager import DatabaseManager

    db = DatabaseManager()
    payload = {"stringDefaults": {"llm_prompt_P1": "injected"}}
    backup.restore(db, payload, {"appSettings": False})  # app settings unchecked
    assert memory_store.get("llm_prompt_P1") is None


def test_settings_store_enables_wal(tmp_path):
    from app.store.settings import SettingsStore

    s = SettingsStore(path=tmp_path / "s.sqlite3")
    mode = s._conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_backup_roundtrips_per_user_namespaced_settings(memory_store):
    """Backup is global: it captures per-user (`u:<user>:...`) keys and restores
    each back into the owning user's namespace."""
    from app.db.manager import DatabaseManager

    db = DatabaseManager()
    memory_store.set("u:alice:llm_prompt_P1", "alice-prompt")
    memory_store.set("u:alice:layout_P1", {"n": 1})
    memory_store.set("u:bob:norms_metric_P1", "9")

    payload = backup.export_payload(
        db, include_passwords=False, include_username=True, include_llm_api_key=False
    )
    assert payload["stringDefaults"].get("u:alice:llm_prompt_P1") == "alice-prompt"
    assert payload["stringDefaults"].get("u:bob:norms_metric_P1") == "9"
    assert "u:alice:layout_P1" in payload["dataDefaults"]

    memory_store.kv.clear()
    backup.restore(db, payload, {})
    assert memory_store.get("u:alice:llm_prompt_P1") == "alice-prompt"
    assert memory_store.get("u:alice:layout_P1") == {"n": 1}
    assert memory_store.get("u:bob:norms_metric_P1") == "9"


def test_user_settings_namespace_is_colon_safe(tmp_path):
    """A username containing ':' must not prefix-collide with another user's
    per-user namespace (which is matched as `u:<user>:`)."""
    from app.store.settings import SettingsStore

    s = SettingsStore(path=tmp_path / "s.sqlite3")
    s.set_user("alice", "kpi.order", "ALICE")
    s.set_user("alice:x", "kpi.order", "ATTACKER")

    assert s.all_user("alice") == {"kpi.order": "ALICE"}        # no leak of alice:x
    assert s.all_user("alice:x") == {"kpi.order": "ATTACKER"}
    # alice cannot write into alice:x's namespace via a crafted key
    s.set_user("alice", "x:injected", "X")
    assert "injected" not in s.all_user("alice:x")
