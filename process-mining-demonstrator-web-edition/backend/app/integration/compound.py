"""Compound steps: derive the final STEP from several extracted fields.

A log line often encodes the real activity across more than one field — an action plus
an outcome. In an Apache log, ``"POST /shop/login…" 200`` is a *successful* login and
``… 500`` a *failed* one, but the path alone yields "login" for both.

A source type may therefore carry an optional list of **compound rules**. Each rule is
a set of conditions over the extracted field values plus the step name to use when they
all hold:

    {"step": "login successful",
     "when": [{"field": "step",   "op": "eq", "value": "login"},
              {"field": "status", "op": "eq", "value": "200"}]}

Rules are evaluated in order and the **first fully-matching rule wins**; if none match,
the plain ``step`` field's value is used unchanged. The feature is entirely optional —
a source type without rules behaves exactly as before.

String comparisons are case-insensitive (log casing is rarely dependable); ``regex`` is
the escape hatch when an exact pattern is needed.
"""

from __future__ import annotations

import re
from typing import Mapping

# Supported condition operators, as stored in the spec.
OPS = ("eq", "ne", "contains", "startswith", "endswith", "regex")

# A pathological user-supplied regex must not hang the import (the same reasoning as in
# extractors.py: CPython's `re` does not release the GIL).
try:  # pragma: no cover - depends on the environment
    import regex as _rx

    _MATCH_KW = {"timeout": 0.25}
except ImportError:  # pragma: no cover
    _rx = re
    _MATCH_KW = {}


class _Condition:
    __slots__ = ("field", "op", "value", "_lower", "_rx")

    def __init__(self, field: str, op: str, value: str) -> None:
        self.field = (field or "").strip()
        self.op = op if op in OPS else "eq"
        self.value = "" if value is None else str(value)
        self._lower = self.value.strip().lower()
        self._rx = None
        if self.op == "regex":
            try:
                self._rx = _rx.compile(self.value)
            except Exception:  # noqa: BLE001 — an invalid pattern simply never matches
                self._rx = None

    def matches(self, values: Mapping[str, str]) -> bool:
        raw = values.get(self.field)
        if raw is None:
            return False  # the field produced no value on this line
        if self.op == "regex":
            if self._rx is None:
                return False
            try:
                return self._rx.search(raw, **_MATCH_KW) is not None
            except TimeoutError:
                return False
        actual = raw.strip().lower()
        if self.op == "eq":
            return actual == self._lower
        if self.op == "ne":
            return actual != self._lower
        if self.op == "contains":
            return self._lower in actual
        if self.op == "startswith":
            return actual.startswith(self._lower)
        if self.op == "endswith":
            return actual.endswith(self._lower)
        return False


class _Rule:
    __slots__ = ("step", "conditions")

    def __init__(self, step: str, conditions: list[_Condition]) -> None:
        self.step = step
        self.conditions = conditions

    def matches(self, values: Mapping[str, str]) -> bool:
        # Every condition must hold (AND). A rule with no conditions never matches, so a
        # half-built rule in the wizard can't silently relabel every event.
        return bool(self.conditions) and all(c.matches(values) for c in self.conditions)


class CompoundRules:
    """Compiled compound rules for one source type. ``derive`` maps a line's extracted
    field values to the final step name (or None when no rule applies)."""

    def __init__(self, rules: list[dict] | None) -> None:
        self._rules: list[_Rule] = []
        for raw in rules or []:
            if not isinstance(raw, dict):
                continue
            step = str(raw.get("step") or "").strip()
            if not step:
                continue  # a rule with no resulting step is meaningless
            conditions = [
                _Condition(
                    str(c.get("field") or ""),
                    str(c.get("op") or "eq"),
                    c.get("value"),
                )
                for c in (raw.get("when") or [])
                if isinstance(c, dict) and str(c.get("field") or "").strip()
            ]
            if conditions:
                self._rules.append(_Rule(step, conditions))

    def __bool__(self) -> bool:
        return bool(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def derive(self, values: Mapping[str, str]) -> str | None:
        """The step name from the first matching rule, or None if none match."""
        for rule in self._rules:
            if rule.matches(values):
                return rule.step
        return None
