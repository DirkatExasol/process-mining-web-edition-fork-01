#!/usr/bin/env python3
"""Single source for the MCP tool reference (one worked example per tool).

The same reference appears in four places; edit the TOOLS list below, then run

    python3 docs/mcp_tool_reference.py

to rewrite the marked blocks in README.md, MCP-SERVER.md and the manual chapter
docs/manual/chapters/27-mcp-server.html. The HTML guide builder
(docs/15-build-mcp-install-guide.py) imports ``render_html`` directly. Afterwards rebuild
the guide and the manual PDF (see docs/manual/BUILD.md).

Facts (parameters, defaults, limits, role gating) mirror mcp/server.py — keep in sync.
"""

from __future__ import annotations

import html
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

EVERYONE, WRITE, POWER = "Everyone", "Everyone — write", "Power users & admins"

# (name, group, access, purpose, parameters, question, arguments, response excerpt)
TOOLS: list[dict] = [
    dict(name="list_connections", group="Discover", access=EVERYONE,
         purpose="The database connections you may query.",
         params="none",
         question="Which Process Mining connections can I use?",
         args={},
         result='[{"id": "7e31de50-…", "name": "02 - Air Travel", "schema": "PM_AIR", "comment": ""},\n'
                ' {"id": "38891b38-…", "name": "03 - Finance", "schema": "PM_FIN", "comment": ""}]'),
    dict(name="list_projects", group="Discover", access=EVERYONE,
         purpose="Projects on one connection — or, with connectionId omitted, on every connection "
                 "you may query; includeCounts adds a journey count per project.",
         params="connectionId?, includeCounts?, sampleSet?",
         question="Which process has the most journeys?",
         args={"includeCounts": True},
         result='[{"connectionName": "02 - Air Travel", "projectId": 2,\n'
                '  "title": "Airport Passenger Flow", "journeyCount": 148187},\n'
                ' {"connectionName": "03 - Finance", "projectId": 1,\n'
                '  "title": "Online Credit Application", "journeyCount": 20000}, …]'),
    dict(name="get_metadata", group="Discover", access=EVERYONE,
         purpose="Meta-attribute titles, step names, each step's definition (stepDetails: "
                 "description, score, belongsTo group, endOfProcess, shape) and the event date range.",
         params="connectionId, projectId",
         question="Show me all steps of the flight booking process.",
         args={"connectionId": "7e31de50-…", "projectId": 5},
         result='{"metaTitles": {"meta1": "Journey Type", "meta2": "Airline", "meta3": "Payment Method"},\n'
                ' "steps": ["Add Services", "Confirm Booking", …],\n'
                ' "stepDetails": [{"step": "Confirm Booking", "description": "Booking confirmed and ticket issued",\n'
                '                  "score": 15, "belongsTo": "Payment", "endOfProcess": true, "shape": "stadium"}, …],\n'
                ' "dateRange": {"from": "2024-01-01T00:02:11", "to": "2024-12-31T23:51:40"}}'),
    dict(name="get_attribute_values", group="Discover", access=EVERYONE,
         purpose="The values each meta attribute takes, with journey counts, most frequent first — "
                 "so you know what to pass as meta1/meta2/meta3.",
         params="connectionId, projectId, meta? (meta1|meta2|meta3|all), limit? (50), filter",
         question="Which payment methods occur in the bookstore?",
         args={"connectionId": "64254f7e-…", "projectId": 1, "meta": "meta1"},
         result='{"attributes": [{"meta": "meta1", "title": "Payment Method", "distinctValues": 3,\n'
                '   "values": [{"value": "Credit Card", "journeys": 9120},\n'
                '              {"value": "PayPal", "journeys": 6874},\n'
                '              {"value": "Bank Transfer", "journeys": 4006}], "truncated": false}],\n'
                ' "filterHint": "… case-insensitive and also matches substrings."}'),
    dict(name="get_process_map", group="Analyse", access=EVERYONE,
         purpose="The directly-follows map: steps (nodes) and transitions (edges) with counts and timing.",
         params="connectionId, projectId, filter",
         question="Draw the process map of the airport passenger flow.",
         args={"connectionId": "7e31de50-…", "projectId": 2},
         result='{"steps": {"ENTER Check-In": {"description": "Passenger checks in at the desk", "score": 0, …}, …},\n'
                ' "transitions": [{"fromStep": "ENTER Check-In", "toStep": "LEAVE Check-In",\n'
                '                  "occurrences": 44295, "avgSecs": 507.8, "medianSecs": 480.0, …}, …]}'),
    dict(name="get_transition_metrics", group="Analyse", access=EVERYONE,
         purpose="Per step pair: count and average/median/min/max/stddev transition time (seconds).",
         params="connectionId, projectId, filter",
         question="How long does security take for passengers in 2024?",
         args={"connectionId": "7e31de50-…", "projectId": 2, "fromDate": "2024-01-01",
               "toDate": "2024-12-31", "includedSteps": ["ENTER Security Check"]},
         result='[{"fromStep": "ENTER Security Check", "toStep": "LEAVE Security Check",\n'
                '  "occurrences": 145198, "avgSecs": 1020.0, "medianSecs": 1020.0,\n'
                '  "minSecs": 240.0, "maxSecs": 1800.0, "stdDevSecs": 466.7}, …]'),
    dict(name="get_variants", group="Analyse", access=EVERYONE,
         purpose="Distinct journey paths and how often each occurs, most frequent first.",
         params="connectionId, projectId, filter, limit?",
         question="What are the three most common credit-application paths?",
         args={"connectionId": "38891b38-…", "projectId": 1, "limit": 3},
         result='[{"path": "Bank -> Application Received -> Application Checked -> Credit Check -> Accepted -> …",\n'
                '  "journeyCount": 4210, "stepCount": 7, "totalScore": 25}, …]'),
    dict(name="get_statistics", group="Analyse", access=EVERYONE,
         purpose="Journey count, journey-duration statistics and the process-goodness score.",
         params="connectionId, projectId, filter",
         question="How long do affiliate credit applications take?",
         args={"connectionId": "38891b38-…", "projectId": 1, "meta3": "Affiliate"},
         result='{"journeyCount": 9870,\n'
                ' "durations": {"minSecs": 1804.0, "avgSecs": 201544.0, "medianSecs": 172800.0, …},\n'
                ' "processGoodness": 3.41}'),
    dict(name="get_journey", group="Cases", access=EVERYONE,
         purpose="One case's ordered events, by business case id or stored hash, with its meta "
                 "values, start/end and total duration.",
         params="connectionId, projectId, eventId, sampleSet?",
         question="Show me credit application CRA-000123.",
         args={"connectionId": "38891b38-…", "projectId": 1, "eventId": "CRA-000123"},
         result='{"eventId": "CRA-000123", "storedEventId": "5e05bf5d94a6fb2c78e7722c3ec4b07b",\n'
                ' "startDate": "2024-06-12T09:59:28", "endDate": "2024-06-12T11:01:11", "durationSecs": 3703.0,\n'
                ' "meta": {"Applied Credit Sum": "> 25.000 EUR", "Income Class": "Low", "Channel": "Affiliate"},\n'
                ' "events": [{"step": "Affiliate", "eventTime": "2024-06-12T09:59:28"}, …,\n'
                '            {"step": "Rejected", "eventTime": "2024-06-12T11:01:11"}]}'),
    dict(name="find_journey", group="Cases", access=EVERYONE,
         purpose="Which project(s) hold a case id — searches every project on every connection you "
                 "may query (or one connectionId), ready for get_journey.",
         params="eventId, connectionId?, sampleSet?",
         question="Where is case FLT-000124?",
         args={"eventId": "FLT-000124"},
         result='{"eventId": "FLT-000124", "storedEventId": "69ab1ef5…",\n'
                ' "matches": [{"connectionName": "02 - Air Travel", "projectId": 5,\n'
                '              "title": "Flight Booking & Management", "startDate": "2024-10-30T23:22:09",\n'
                '              "durationSecs": 1380.0, "stepCount": 14}],\n'
                ' "searched": {"connections": 5, "projects": 8}}'),
    dict(name="find_journeys", group="Cases", access=EVERYONE,
         purpose="The individual cases behind an aggregate — slowest, longest or by step — with "
                 "optional full path. Returned eventIds feed get_journey.",
         params="connectionId, projectId, filter, orderBy?, limit? (20), min/maxDurationSecs?, "
                "min/maxSteps?, includePath?",
         question="The five slowest orders that hit Payment Failed, with their paths.",
         args={"connectionId": "64254f7e-…", "projectId": 1, "limit": 5,
               "includedSteps": ["Payment Failed"], "includePath": True},
         result='[{"eventId": "8c46773b…", "startDate": "2024-04-21T04:36:09", "durationSecs": 1134.0,\n'
                '  "stepCount": 17, "meta": {"Payment Method": "Bank Transfer", …},\n'
                '  "path": "Login -> Browse Catalog -> … -> Payment Failed -> Payment Retry -> …"}, …]'),
    dict(name="get_notes", group="Notes", access=EVERYONE,
         purpose="The notes on a project's steps and transitions — filter by severity, status and "
                 "scope, optionally grouped; with a summary of counts. Times are local (Admin "
                 "Console display zone) with the UTC offset.",
         params="connectionId, projectId, severity?, status?, scope?, groupBy?",
         question="Show all closed notes, then all open notes, as separate groups.",
         args={"connectionId": "7e31de50-…", "projectId": 2, "groupBy": "status"},
         result='{"total": 1, "summary": {"byStatus": {"open": 0, "resolved": 1}, …},\n'
                ' "groupBy": "status",\n'
                ' "groups": [{"key": "resolved", "count": 1, "notes": [{"id": "E422E185-…",\n'
                '   "title": "A Note for testing", "severity": "URGENT", "status": "resolved",\n'
                '   "scope": "shared", "author": "dirk.beerbohm", "target": "ENTER Check-In",\n'
                '   "createdAt": "2026-09-23T12:34:45+02:00", "editedAt": "2026-09-23T12:36:42+02:00"}]}]}'),
    dict(name="create_note", group="Notes", access=WRITE,
         purpose="Create a note on a step (step) or a transition (fromStep + toStep). You become "
                 "the author; id and time are set by the server. text required (≤ 4000), title "
                 "≤ 200, severity default NORMAL, scope default personal. Rate-limited per user, "
                 "and capped at a maximum number of notes you may own per project.",
         params="connectionId, projectId, step | fromStep + toStep, text, title?, severity?, scope?",
         question="Add a shared, important note on the security transition.",
         args={"connectionId": "7e31de50-…", "projectId": 2, "fromStep": "ENTER Security Check",
               "toStep": "LEAVE Security Check", "title": "Security wait",
               "text": "Median 17 min; peaks before 07:00.", "severity": "IMPORTANT",
               "scope": "shared"},
         result='{"created": true,\n'
                ' "note": {"id": "9B1C…", "title": "Security wait", "severity": "IMPORTANT",\n'
                '          "status": "open", "scope": "shared", "author": "dirk.beerbohm",\n'
                '          "target": "ENTER Security Check → LEAVE Security Check", "targetType": "edge",\n'
                '          "createdAt": "2026-09-24T08:15:02+02:00", "editedAt": null}}'),
    dict(name="update_note", group="Notes", access=WRITE,
         purpose="On a note you can see: add a comment (prepended to the thread, with an optional "
                 "title), set status open/resolved; the author alone may change severity or scope. "
                 "Existing text is never rewritten; a full thread (100,000 characters) takes no "
                 "more comments. Rate-limited per user.",
         params="connectionId, projectId, noteId, comment?, title?, status?, severity?, scope?",
         question="Resolve the test note and say why.",
         args={"connectionId": "7e31de50-…", "projectId": 2,
               "noteId": "E422E185-0557-4E22-8DB2-BC62B30DA426",
               "comment": "Test complete.", "status": "resolved"},
         result='{"updated": true, "changes": ["comment", "status"],\n'
                ' "note": {"id": "E422E185-…", "status": "resolved", "lastEditedBy": "dirk.beerbohm",\n'
                '          "editedAt": "2026-09-24T08:16:40+02:00", …}}'),
    dict(name="compare_segments", group="Power analysis", access=POWER,
         purpose="Two slices of one project side by side: each segment's count, durations, goodness "
                 "and end steps, then the biggest differences (B minus A) in end-step shares, "
                 "transition times, transition frequency, and transitions found in only one segment.",
         params="connectionId, projectId, segmentA, segmentB (filter objects + label), limit? (10), "
                "minOccurrences? (30), sampleSet?",
         question="How do Bank Transfer orders differ from PayPal orders?",
         args={"connectionId": "64254f7e-…", "projectId": 1,
               "segmentA": {"meta1": "Bank Transfer", "label": "Bank Transfer"},
               "segmentB": {"meta1": "PayPal", "label": "PayPal"}},
         result='{"segments": [{"label": "Bank Transfer", "journeyCount": 4006, …},\n'
                '              {"label": "PayPal", "journeyCount": 6874, …}],\n'
                ' "differences": {\n'
                '   "endSteps": [{"step": "Payment Failed", "shareA": 0.12, "shareB": 0.03, "deltaPoints": -9.0}, …],\n'
                '   "transitionTime": [{"fromStep": "Payment Processing", "toStep": "Payment Confirmed",\n'
                '                       "avgSecsA": 5400.0, "avgSecsB": 45.0, "deltaSecs": -5355.0}, …],\n'
                '   "transitionFrequency": […], "onlyInA": […], "onlyInB": […]}}'),
    dict(name="get_bottlenecks", group="Power analysis", access=POWER,
         purpose="Where time is lost: transitions by total waiting time (occurrences × average), "
                 "the slowest typical transitions (median), rework (steps repeated in a journey) "
                 "and self-loops.",
         params="connectionId, projectId, filter, limit? (10), minOccurrences? (30)",
         question="Where do credit applications lose the most time?",
         args={"connectionId": "38891b38-…", "projectId": 1},
         result='{"totalWaitSecs": 3.1e9,\n'
                ' "byTotalWaitTime": [{"fromStep": "Credit Check", "toStep": "Senior Agent Approval",\n'
                '   "occurrences": 6120, "avgSecs": 87942.0, "totalWaitSecs": 538205040.0,\n'
                '   "shareOfWaitTime": 0.17}, …],\n'
                ' "slowestTypicalTransitions": […],\n'
                ' "rework": [{"step": "Application Checked", "journeys": 5230, "extraVisits": 5890}, …],\n'
                ' "selfLoops": […]}'),
    dict(name="get_trend", group="Power analysis", access=POWER,
         purpose="The process over time: per day, week or month (by journey start) the journey "
                 "count, average and median duration, and — with outcomeSteps — the reach rate of "
                 "those steps.",
         params="connectionId, projectId, filter, granularity? (day|week|month), outcomeSteps?, limit?",
         question="Is the denied-boarding rate changing month by month?",
         args={"connectionId": "7e31de50-…", "projectId": 2, "granularity": "month",
               "outcomeSteps": ["DENIED Boarding Dom", "DENIED Boarding Int"]},
         result='{"granularity": "month",\n'
                ' "periods": [{"period": "2024-01-01", "journeys": 12530, "avgDurationSecs": 4210.0,\n'
                '              "medianDurationSecs": 4080.0, "outcomeJourneys": 598, "outcomeRate": 0.0477}, …]}'),
    dict(name="get_outcome_drivers", group="Power analysis", access=POWER,
         purpose="Why an outcome happens: the overall rate of reaching outcomeSteps, and the meta "
                 "values and visited steps that raise or lower it (rate with / without, delta in "
                 "percentage points, lift). Association, not cause.",
         params="connectionId, projectId, filter, outcomeSteps, minSupport? (30), limit? (10)",
         question="What makes a credit application end in Rejected?",
         args={"connectionId": "38891b38-…", "projectId": 1, "outcomeSteps": ["Rejected"]},
         result='{"journeys": 20000, "outcomeJourneys": 5400, "outcomeRate": 0.27,\n'
                ' "raisesOutcome": {"attributes": [{"title": "Income Class", "value": "Low",\n'
                '     "outcomeRate": 0.61, "rateWithout": 0.16, "deltaPoints": 34.0, "lift": 2.26}, …],\n'
                '   "steps": […]},\n'
                ' "lowersOutcome": {"attributes": […], "steps": […]}}'),
    dict(name="check_conformance", group="Power analysis", access=POWER,
         purpose="Test journeys against up to 10 rules — requires {step, ifStep?}, forbidden "
                 "{step}, precedes {before, after}, max_duration {maxSecs}, max_gap {fromStep, "
                 "toStep, maxSecs} — and count violations with example case ids.",
         params="connectionId, projectId, filter, rules, examples? (5)",
         question="Is payment always processed before a booking is confirmed, within 5 minutes?",
         args={"connectionId": "7e31de50-…", "projectId": 5, "rules": [
             {"type": "precedes", "before": "Process Payment", "after": "Confirm Booking"},
             {"type": "max_gap", "fromStep": "Process Payment", "toStep": "Confirm Booking",
              "maxSecs": 300}]},
         result='{"journeysChecked": 20000,\n'
                ' "rules": [{"type": "precedes", "rule": "\'Process Payment\' must happen before \'Confirm Booking\'",\n'
                '            "violations": 0, "violationRate": 0.0, "conformanceRate": 1.0, "exampleEventIds": []},\n'
                '           {"type": "max_gap", "violations": 0, …}]}'),
]

GROUP_INTRO = {
    "Discover": "What exists: connections, projects, steps and attribute values.",
    "Analyse": "Aggregates over many journeys; every one takes the common filter.",
    "Cases": "Individual journeys — find them, then open one.",
    "Notes": "The human layer on the process. The two note-writing tools are the only writes "
             "on the MCP surface.",
    "Power analysis": "Deeper analysis, reserved for users with the power-user role (and "
                      "administrators). Anyone else gets a polite refusal naming the role.",
}
FILTER_NOTE = ("The common filter: sampleSet (ORIGINAL | SAMPLE_1..3), fromDate / toDate (ISO "
               "dates), includedSteps (journeys visiting all of them), excludedSteps (journeys "
               "visiting none of them) — up to 200 step names each — and meta1 / meta2 / meta3 "
               "(up to 256 characters; case-insensitive substring match — see "
               "get_attribute_values). The per-journey power tools (bottleneck rework, trend, "
               "outcome drivers, conformance, end steps) keep whole journeys that are active "
               "in the date window rather than cutting them at its edges.")


def _groups():
    seen: list[str] = []
    for t in TOOLS:
        if t["group"] not in seen:
            seen.append(t["group"])
    return [(g, [t for t in TOOLS if t["group"] == g]) for g in seen]


def _call_json(t) -> str:
    return json.dumps({"name": t["name"], "arguments": t["args"]}, ensure_ascii=False, indent=2)


# ── Markdown (README.md, MCP-SERVER.md) ────────────────────────────────────────


def render_markdown(heading: str = "###") -> str:
    out = [f"{heading} Tool reference — {len(TOOLS)} tools, one example each", "",
           "| Tool | Who | Returns |", "|---|---|---|"]
    for t in TOOLS:
        out.append(f"| `{t['name']}` | {t['access']} | {t['purpose']} |")
    out += ["", f"> {FILTER_NOTE}", ""]
    for group, tools in _groups():
        out += [f"{heading}# {group}", "", GROUP_INTRO[group], ""]
        for t in tools:
            out += [f"**`{t['name']}`** — *{t['access']}.* Parameters: {t['params']}.", "",
                    f"*“{t['question']}”*", "", "```jsonc", "// call", _call_json(t),
                    "// result (excerpt; illustrative values)", t["result"], "```", ""]
    return "\n".join(out).rstrip() + "\n"


# ── HTML (manual chapter, HTML guide) ─────────────────────────────────────────


def render_html(*, table_class: str = "", code_class: str = "") -> str:
    tc = f' class="{table_class}"' if table_class else ""
    cc = f' class="{code_class}"' if code_class else ""
    e = html.escape
    out = [f"<table{tc}>",
           "<tr><th>Tool</th><th>Who</th><th>Returns</th></tr>"]
    for t in TOOLS:
        out.append(f"<tr><td style=\"white-space:nowrap\"><code style=\"word-break:normal\">"
                   f"{e(t['name'])}</code></td><td>{e(t['access'])}</td>"
                   f"<td>{e(t['purpose'])}</td></tr>")
    out += ["</table>", f"<p>{e(FILTER_NOTE)}</p>"]
    for group, tools in _groups():
        out += [f"<h3>{e(group)}</h3>", f"<p>{e(GROUP_INTRO[group])}</p>"]
        for t in tools:
            out += [f"<h4><code>{e(t['name'])}</code> <small>&middot; {e(t['access'])}</small></h4>",
                    f"<p>{e(t['purpose'])} <em>Parameters:</em> <code>{e(t['params'])}</code></p>",
                    f"<p><em>&ldquo;{e(t['question'])}&rdquo;</em></p>",
                    f"<pre{cc}><code>// call\n{e(_call_json(t))}\n// result (excerpt; illustrative values)\n{e(t['result'])}</code></pre>"]
    return "\n".join(out) + "\n"


# ── write the marked blocks ────────────────────────────────────────────────────

BEGIN, END = "MCP-TOOL-REFERENCE:BEGIN", "MCP-TOOL-REFERENCE:END"


def _replace_block(path: pathlib.Path, body: str, comment=("<!-- ", " -->")) -> None:
    text = path.read_text(encoding="utf-8")
    open_c, close_c = comment
    start, end = f"{open_c}{BEGIN}{close_c}", f"{open_c}{END}{close_c}"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise SystemExit(f"{path}: markers {start} … {end} not found")
    new = pattern.sub(lambda _m: f"{start}\n{body}{end}", text)
    path.write_text(new, encoding="utf-8")
    print(f"updated {path.relative_to(ROOT)}")


def main() -> None:
    _replace_block(ROOT / "README.md", render_markdown("####"))
    _replace_block(ROOT / "MCP-SERVER.md", render_markdown("###"))
    _replace_block(ROOT / "docs" / "manual" / "chapters" / "27-mcp-server.html", render_html())


if __name__ == "__main__":
    main()
