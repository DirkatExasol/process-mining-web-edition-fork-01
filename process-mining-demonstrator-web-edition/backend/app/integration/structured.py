"""Value resolvers for semi-structured source files (JSON + XML).

Unstructured text sources capture each field with a **regex** (see ``parsing.py`` and
``extractors.py``). Semi-structured sources — JSON and XML — instead locate a field by
its *position* in the document, so this module provides the two selectors the extractor
uses in place of a regex:

* :func:`json_path` — a small JSONPath subset (``a.b[0].c``; leading ``$.`` optional).
* :func:`xml_value` — a small XPath subset (``a/b@attr``, ``@attr``, ``.``).

Plus the record iterators and the flatteners the wizard uses to *suggest* paths.

**Security:** all XML is parsed through :mod:`defusedxml` — never bare
``xml.etree.ElementTree`` — so a user file can't trigger external-entity resolution, DTD
retrieval or billion-laughs expansion. JSON/XML paths are pure *data selectors*: they are
walked structurally, never compiled or ``eval``'d.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

# ── JSON key paths ────────────────────────────────────────────────────────────

# A dot-path key that needs no bracket quoting: identifier-ish, no dots/brackets/spaces.
_PLAIN_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*")


def _json_tokens(path: str) -> list[str | int]:
    """Tokenise a JSON path into a list of dict keys (str) and list indices (int).

    Accepts ``a.b``, ``a[0]``, ``a["weird.key"]`` and a leading ``$``/``$.``. Raises
    ``ValueError`` on a malformed path (unbalanced bracket, non-integer index)."""
    p = (path or "").strip()
    if p[:1] == "$":
        p = p[1:]
    toks: list[str | int] = []
    pos, n = 0, len(p)
    while pos < n:
        c = p[pos]
        if c == ".":
            pos += 1
            continue
        if c == "[":
            end = p.find("]", pos)
            if end == -1:
                raise ValueError("unbalanced '[' in path")
            inner = p[pos + 1 : end].strip()
            if len(inner) >= 2 and inner[0] in "\"'" and inner[-1] == inner[0]:
                toks.append(inner[1:-1])
            else:
                toks.append(int(inner))  # ValueError → caught by caller
            pos = end + 1
        else:
            j = pos
            while j < n and p[j] not in ".[":
                j += 1
            toks.append(p[pos:j])
            pos = j
    return toks


def json_path(obj: Any, path: str) -> Any:
    """Resolve ``path`` against a parsed JSON value; ``None`` if any step is missing.

    Supports dot keys and ``[index]`` / ``["key"]``; a leading ``$`` is optional. An
    empty path (or ``$``/``.``) returns ``obj`` itself. Negative list indices work.
    """
    stripped = (path or "").strip().lstrip("$")
    if stripped in ("", "."):
        return obj
    try:
        tokens = _json_tokens(path)
    except ValueError:
        return None
    cur = obj
    for tok in tokens:
        if isinstance(tok, int):
            if isinstance(cur, list) and -len(cur) <= tok < len(cur):
                cur = cur[tok]
            else:
                return None
        else:
            if isinstance(cur, dict) and tok in cur:
                cur = cur[tok]
            else:
                return None
    return cur


def scalar(value: Any) -> str | None:
    """Render a resolved JSON/XML value as the string the extractor stores.

    Scalars become their natural text (``True`` → ``"true"`` to match JSON, numbers via
    ``str``); ``None`` and *containers* (a dict/list a path landed on) yield ``None`` —
    a field must resolve to a single value, not a subtree.
    """
    if value is None or isinstance(value, (dict, list)):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return str(value)


def _join_json(prefix: str, key: str) -> str:
    """Append a dict key to a JSON path, bracket-quoting keys that aren't plain."""
    if _PLAIN_KEY.fullmatch(key):
        return f"{prefix}.{key}" if prefix else key
    token = f"[{json.dumps(key)}]"
    return f"{prefix}{token}" if prefix else token


def flatten_json(obj: Any, prefix: str = "", *, out: list | None = None,
                 depth: int = 0, max_depth: int = 6) -> list[tuple[str, Any]]:
    """Every scalar leaf of ``obj`` as ``(json_path, value)`` — for path suggestions."""
    if out is None:
        out = []
    if depth > max_depth:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten_json(v, _join_json(prefix, str(k)), out=out, depth=depth + 1, max_depth=max_depth)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flatten_json(v, f"{prefix}[{i}]", out=out, depth=depth + 1, max_depth=max_depth)
    else:
        out.append((prefix or "$", obj))
    return out


# ── XML element/attribute paths ───────────────────────────────────────────────


def parse_xml(data: bytes | str):
    """Parse XML into an ElementTree root — XXE-safe (external entities/DTDs refused).

    Raises ``ValueError`` on malformed or unsafe XML (defusedxml turns entity/DTD attacks
    into a parse error rather than fetching anything).
    """
    from defusedxml.ElementTree import fromstring
    from defusedxml.common import DefusedXmlException
    from xml.etree.ElementTree import ParseError

    try:
        return fromstring(data)
    except (DefusedXmlException, ParseError) as exc:
        raise ValueError(f"could not parse XML: {exc}") from exc


def _strip_ns(tag: str) -> str:
    """Drop an ``{namespace}`` prefix from an element tag for display/suggestions."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def xml_value(elem, spec: str) -> str | None:
    """Resolve an XPath-subset ``spec`` against ``elem``; ``None`` if not found.

    Forms: ``.`` (the element's own text), ``@attr`` (an attribute), ``child`` /
    ``child/grandchild`` (a descendant's text), ``child@attr`` (a descendant's attribute).
    Only find/attrib navigation — no predicates, wildcards or functions.
    """
    s = (spec or "").strip()
    if not s:
        return None
    attr: str | None = None
    if "@" in s:
        s, attr = s.rsplit("@", 1)
        s, attr = s.strip(), attr.strip()
    if s in ("", ".", "./"):
        target = elem
    else:
        try:
            target = elem.find(s)
        except SyntaxError:
            return None
        if target is None:
            return None
    if attr:
        return target.get(attr)
    text = target.text
    if text is None:
        return None
    stripped = text.strip()
    return stripped or None


def iter_xml_records(root, record_path: str) -> list:
    """The record elements under ``root`` selected by ``record_path`` (relative to root).

    An empty/``.`` path treats each direct child of the root as a record.
    """
    rp = (record_path or "").strip()
    if not rp or rp in (".", "./"):
        return list(root)
    try:
        return root.findall(rp)
    except SyntaxError:
        return []


def suggest_record_path(root) -> str:
    """Guess which repeating child element of ``root`` is one record: the most common
    direct-child tag (ties → document order). Empty when the root has no children."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for child in root:
        tag = _strip_ns(child.tag)
        if tag not in counts:
            order.append(tag)
        counts[tag] = counts.get(tag, 0) + 1
    if not order:
        return ""
    return max(order, key=lambda t: (counts[t], -order.index(t)))


def flatten_xml(elem, prefix: str = "", *, out: list | None = None,
                depth: int = 0, max_depth: int = 4) -> list[tuple[str, str]]:
    """Every attribute/text leaf of ``elem`` as ``(xml_path, value)`` — for suggestions.

    Paths are relative to ``elem`` and use the same subset :func:`xml_value` resolves:
    ``@attr`` on the record element, ``child`` for a child's text, ``child@attr`` for a
    child's attribute, nested via ``child/grandchild``.
    """
    if out is None:
        out = []
    for name, val in elem.attrib.items():
        p = f"{prefix}@{name}" if prefix else f"@{name}"
        out.append((p, val))
    children = list(elem)
    text = (elem.text or "").strip()
    if text and not children:
        out.append((prefix or ".", text))
    if depth < max_depth:
        for child in children:
            cp = f"{prefix}/{_strip_ns(child.tag)}" if prefix else _strip_ns(child.tag)
            flatten_xml(child, cp, out=out, depth=depth + 1, max_depth=max_depth)
    return out


def iter_json_from_text(text: str) -> Iterator[Any]:
    """Yield JSON records from either a top-level array ``[{…}]`` or JSONL/NDJSON.

    A leading ``[`` (ignoring whitespace) is parsed as one array; otherwise each non-blank
    line is parsed on its own (NDJSON). A single top-level object yields that one object.
    Malformed JSONL lines are skipped. Raises ``ValueError`` if an array can't be parsed.
    """
    head = text.lstrip()
    if head[:1] == "[":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"could not parse JSON array: {exc}") from exc
        if isinstance(data, list):
            yield from data
        return
    if head[:1] == "{" and "\n" not in head.strip():
        # A single object on its own is one record.
        try:
            yield json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"could not parse JSON: {exc}") from exc
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue
