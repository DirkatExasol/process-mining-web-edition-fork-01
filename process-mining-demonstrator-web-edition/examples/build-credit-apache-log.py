#!/usr/bin/env python3
"""Turn the "Online Credit Application" demo process into an Apache access log.

Each *event* of a credit-application journey (from the finance demo generator)
becomes one line of an Apache **Combined Log Format** access log:

    %h %l %u %t "%r" %>s %b "%{Referer}i" "%{User-agent}i"

The case id and the activity are carried in the request path, so a process
mining import (e.g. the Integration Console "unstructured / Text" extractor)
can recover them with a single regex:

    /api/v1/applications/(?P<case>CRA-\\d+)/(?P<activity>[a-z-]+)

  * case      -> the CRA-###### segment
  * activity  -> the last path segment (intake, register, check, ...)
  * timestamp -> the Apache [dd/Mon/yyyy:HH:MM:SS +ZZZZ] field
  * channel / income / amount -> query string on the intake line (case metas)

Lines are emitted in strict chronological order, exactly like a real web
server log: journeys interleave, so the importer must group by case and sort
by time. The process structure itself is untouched — this only re-encodes the
demo journeys as HTTP traffic.

Rebuild:  python3 examples/build-credit-apache-log.py [--count N] [--seed S] [--out PATH]
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import timedelta
from pathlib import Path

# Reuse the real finance journey generator so the process stays faithful.
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_BACKEND))

from app.db.demo_data import (  # noqa: E402
    _FIN_CHANNELS,
    _FIN_INCOME,
    _FIN_SCORE_BANDS,
    _generate_finance_journey,
    _pick_sum,
    _rand_start,
    _weighted_choice,
)

HOST = "https://credit.example-bank.com"

# activity name -> (url endpoint, http method, status code)
ENDPOINT: dict[str, tuple[str, str, int]] = {
    "Bank": ("intake", "POST", 201),
    "Affiliate": ("intake", "POST", 201),
    "Application Received": ("register", "POST", 200),
    "Application Checked": ("check", "POST", 200),
    "Additional Information Requested": ("request-info", "POST", 200),
    "Credit Assessment": ("assessment", "POST", 200),
    "Credit Check": ("credit-check", "POST", 200),
    "Agent Review": ("agent-review", "POST", 200),
    "Senior Agent Approval": ("senior-approval", "POST", 200),
    "Accepted": ("accept", "POST", 200),
    "Rejected": ("reject", "POST", 200),
    "Payment to Applicant": ("disburse", "POST", 202),
    "Payment": ("payment", "POST", 200),
}

# A small pool of plausible user agents; one is stuck to each case (a "session").
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
]

_ORIGIN = {
    "Bank": "https://portal.example-bank.com/apply",
    "Affiliate": "https://partner-shop.example.com/checkout",
}

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _apache_time(dt) -> str:
    """[dd/Mon/yyyy:HH:MM:SS +0100] with a fixed Central-European offset."""
    return "%02d/%s/%d:%02d:%02d:%02d +0100" % (
        dt.day, _MONTHS[dt.month - 1], dt.year, dt.hour, dt.minute, dt.second,
    )


def _client_ip(rng: random.Random) -> str:
    """A plausible public-ish IPv4, sticky per case."""
    return "%d.%d.%d.%d" % (
        rng.choice([31, 46, 77, 84, 91, 134, 178, 195, 203, 217]),
        rng.randint(0, 255), rng.randint(0, 255), rng.randint(1, 254),
    )


def build_lines(count: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    # (event_time, line) so we can emit in real chronological order.
    entries: list[tuple[object, str]] = []

    for i in range(count):
        case = "CRA-%06d" % (i + 1)
        sum_label, sum_amount = _pick_sum(rng)
        channel = _weighted_choice(_FIN_CHANNELS, rng)
        income = _weighted_choice(_FIN_INCOME, rng)
        score = _weighted_choice(_FIN_SCORE_BANDS, rng)

        rows = _generate_finance_journey(
            case, _rand_start(rng), channel, income, sum_label, sum_amount, score, rng,
        )

        ip = _client_ip(rng)
        ua = rng.choice(_USER_AGENTS)
        referer = _ORIGIN[channel]

        for idx, ev in enumerate(rows):
            endpoint, method, status = ENDPOINT[ev.step]
            path = "/api/v1/applications/%s/%s" % (case, endpoint)
            if idx == 0:
                # Intake line carries the case-level attributes as a query string.
                path += "?channel=%s&income=%s&amount=%d" % (channel, income, sum_amount)
            # Realistic response size; the intake/decision payloads are a bit larger.
            nbytes = rng.randint(180, 900) + (900 if endpoint in ("intake", "assessment", "credit-check") else 0)
            line = '%s - - [%s] "%s %s HTTP/1.1" %d %d "%s" "%s"' % (
                ip, _apache_time(ev.event_time), method, path, status, nbytes, referer, ua,
            )
            entries.append((ev.event_time, line))
            referer = HOST + path  # next step is referred by this one

    # Strict chronological order — an authentic access log interleaves cases.
    entries.sort(key=lambda e: e[0])
    return [line for _, line in entries]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=250, help="number of credit applications (default 250)")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible output (default 42)")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "credit-application-access.log",
                    help="output log file")
    args = ap.parse_args()

    lines = build_lines(args.count, args.seed)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("WROTE %s — %d applications, %d log lines" % (args.out, args.count, len(lines)))


if __name__ == "__main__":
    main()
