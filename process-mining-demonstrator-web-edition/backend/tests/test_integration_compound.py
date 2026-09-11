"""Compound steps: derive the final STEP from several extracted fields.

The motivating case is an Apache log where the activity is the path and the outcome is
the HTTP status: "login" + 200 is a successful login, "login" + 500 a failed one.
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

from app.integration.compound import CompoundRules

LOGIN_RULES = [
    {"step": "login successful",
     "when": [{"field": "step", "op": "eq", "value": "login"},
              {"field": "status", "op": "eq", "value": "200"}]},
    {"step": "login failed",
     "when": [{"field": "step", "op": "eq", "value": "login"},
              {"field": "status", "op": "eq", "value": "500"}]},
]


def test_derives_the_step_from_two_fields():
    rules = CompoundRules(LOGIN_RULES)
    assert rules.derive({"step": "login", "status": "200"}) == "login successful"
    assert rules.derive({"step": "login", "status": "500"}) == "login failed"
    # No rule matches → None, so the caller keeps the plain step value.
    assert rules.derive({"step": "login", "status": "404"}) is None
    assert rules.derive({"step": "basket", "status": "200"}) is None


def test_every_condition_must_hold_and_first_match_wins():
    rules = CompoundRules([
        {"step": "first", "when": [{"field": "a", "op": "eq", "value": "1"}]},
        {"step": "second", "when": [{"field": "a", "op": "eq", "value": "1"},
                                    {"field": "b", "op": "eq", "value": "2"}]},
    ])
    # Both rules match, but the earlier one wins.
    assert rules.derive({"a": "1", "b": "2"}) == "first"
    # A missing field can never satisfy a condition.
    assert CompoundRules([
        {"step": "x", "when": [{"field": "a", "op": "eq", "value": "1"},
                               {"field": "missing", "op": "eq", "value": "1"}]},
    ]).derive({"a": "1"}) is None


def test_operators_and_case_insensitivity():
    def one(op, value, actual):
        return CompoundRules(
            [{"step": "hit", "when": [{"field": "f", "op": op, "value": value}]}]
        ).derive({"f": actual})

    assert one("eq", "LOGIN", "login") == "hit"       # case-insensitive
    assert one("eq", "login", " login ") == "hit"     # trimmed
    assert one("ne", "logout", "login") == "hit"
    assert one("contains", "gi", "login") == "hit"
    assert one("startswith", "log", "login") == "hit"
    assert one("endswith", "gin", "login") == "hit"
    assert one("regex", r"^\d{3}$", "200") == "hit"
    assert one("regex", r"^\d{3}$", "20x") is None
    assert one("regex", "([", "anything") is None     # invalid pattern never matches


def test_incomplete_rules_are_ignored():
    """A half-built rule from the wizard must never relabel every event."""
    assert not CompoundRules([{"step": "x", "when": []}])          # no conditions
    assert not CompoundRules([{"step": "", "when": [{"field": "a"}]}])  # no step
    assert not CompoundRules(None)
    assert not CompoundRules([])
    # A condition without a field name is dropped, taking the rule with it.
    assert not CompoundRules([{"step": "x", "when": [{"field": "  ", "op": "eq", "value": "1"}]}])


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PMW_INTEGRATION_FILES_DIR", str(tmp_path / "files"))
    monkeypatch.delenv("PMW_INTEGRATION_ALLOW_ANY_PATH", raising=False)
    import app.config as config

    importlib.reload(config)
    import app.integration.files as files_mod

    importlib.reload(files_mod)
    import app.integration.extractors as extractors_mod

    importlib.reload(extractors_mod)
    from app.integration import AbstractionLayer, InMemoryIngestBackend

    return config, extractors_mod, AbstractionLayer, InMemoryIngestBackend


# The user's real demo-log format.
FIELDS = [
    {"name": "timestamp", "role": "timestamp",
     "regex": r"\[(\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4})\]"},
    {"name": "event_id", "role": "id", "regex": r"userId=(\d+)"},
    {"name": "step", "role": "step", "regex": r'"[A-Z]+ /shop/([a-z]+)'},
    # A helper field: matched on, but written to no column.
    {"name": "status", "role": "aux", "regex": r'HTTP/1\.1" (\d{3})'},
]


def _line(step: str, status: str, user: str = "20253471") -> str:
    return (
        f'10.185.248.71 - - [09/Jan/2015:19:12:06 +0000] 4213 '
        f'"POST /shop/{step}?userId={user} HTTP/1.1" {status} 512 "-" "UA"'
    )


def test_extractor_writes_the_compound_step(env):
    config, extractors_mod, AbstractionLayer, InMemoryIngestBackend = env
    (config.INTEGRATION_FILES_DIR / "a.log").write_text(
        "\n".join([_line("login", "200"), _line("login", "500"), _line("basket", "200")]) + "\n"
    )
    mem = InMemoryIngestBackend()
    ext = extractors_mod.FileExtractor(
        path="a.log", encoding="utf-8", fields=FIELDS, project_id="P", compound=LOGIN_RULES,
    )
    asyncio.run(AbstractionLayer().run(user="dev", extractor=ext, backend=mem, schema="S"))

    steps = [r["STEP"] for r in mem.tables["S"]["JOURNEYS"]["rows"]]
    assert steps == ["login successful", "login failed", "basket"]
    # The derived names are what get STEPS definitions created for them.
    assert {r["STEP"] for r in mem.tables["S"]["STEPS"]["rows"]} == {
        "login successful", "login failed", "basket",
    }
    # A helper (aux) field is NOT written to a META column.
    assert mem.tables["S"]["JOURNEYS"]["rows"][0]["META_1"] is None


def test_without_rules_the_plain_step_is_used(env):
    """Compound steps are optional — the same source type behaves as before without them."""
    config, extractors_mod, AbstractionLayer, InMemoryIngestBackend = env
    (config.INTEGRATION_FILES_DIR / "a.log").write_text(_line("login", "200") + "\n")
    mem = InMemoryIngestBackend()
    ext = extractors_mod.FileExtractor(
        path="a.log", encoding="utf-8", fields=FIELDS, project_id="P",
    )
    asyncio.run(AbstractionLayer().run(user="dev", extractor=ext, backend=mem, schema="S"))
    assert [r["STEP"] for r in mem.tables["S"]["JOURNEYS"]["rows"]] == ["login"]


def test_spec_round_trips_compound_rules_through_the_api(tmp_path, monkeypatch):
    """The wizard's rules survive save → load, and incomplete ones are dropped."""
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs  # noqa: F401 — reloaded transitively by security
    import app.store.security as security_mod

    importlib.reload(security_mod)
    import app.api.integration as integ_api

    importlib.reload(integ_api)

    body = integ_api.SourceTypeBody(
        name="Apache",
        sample="x",
        fields=[{"name": "step", "role": "step", "regex": "(a)"}],
        compound=[
            {"step": "login successful",
             "when": [{"field": "step", "op": "eq", "value": "login"},
                      {"field": "status", "op": "eq", "value": "200"}]},
            {"step": "", "when": [{"field": "step", "op": "eq", "value": "x"}]},  # no step
            {"step": "orphan", "when": []},                                       # no conditions
            {"step": "bad-op", "when": [{"field": "step", "op": "explode", "value": "x"}]},
        ],
    )
    created = security_mod.store.add_source_type(
        "dev", name=body.name, config=integ_api._spec_config(body)
    )
    spec = created.public()
    # Only the two complete rules survive; an unknown operator falls back to "eq".
    assert [r["step"] for r in spec["compound"]] == ["login successful", "bad-op"]
    assert spec["compound"][1]["when"][0]["op"] == "eq"
    assert spec["compound"][0]["when"][1] == {"field": "status", "op": "eq", "value": "200"}

    # And a source type without rules exposes an empty list, not a missing key.
    plain = security_mod.store.add_source_type(
        "dev", name="Plain",
        config=integ_api._spec_config(integ_api.SourceTypeBody(name="Plain", sample="", fields=[])),
    )
    assert plain.public()["compound"] == []
