"""High-gloss AI report assembly.

The division of labour (per the product design):

  • the LLM does the **analysis** — it sees only the transition table and returns a
    structured JSON of findings (title, executive summary, sections);
  • Python does the **styling / layout / assembly** — it turns that JSON, plus the
    Python-computed Happy Path / Conformance sections and the process Sankey (whose SVG
    the app hands us), into one self-contained, print-ready HTML document.

The HTML is standalone (inline CSS, embedded SVG) so the app can show it in a frame and
the user can "Save as PDF" via the browser — which is exactly how the reference report was
produced (Chrome → PDF). No server-side PDF/chart libraries are required.
"""

from __future__ import annotations

import base64
import html
import json
import re
from datetime import datetime, timezone

# ── tiny, safe Markdown → HTML (no external dependency) ─────────────────────────
#
# We only support the subset the report needs: #/##/### headings, **bold**, *italic*,
# `code`, pipe tables, "- " bullet lists, "> " block-quotes and paragraphs. Everything is
# HTML-escaped first, so model- or data-supplied text can never inject markup.

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
_CODE = re.compile(r"`([^`]+?)`")


def md_inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = _CODE.sub(r"<code>\1</code>", out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _ITALIC.sub(r"<em>\1</em>", out)
    return out


def _table_html(lines: list[str]) -> str:
    def cells(row: str) -> list[str]:
        row = row.strip().strip("|")
        return [c.strip() for c in row.split("|")]

    header = cells(lines[0])
    body = [cells(r) for r in lines[2:]]  # lines[1] is the |---|---| separator
    thead = "".join(f"<th>{md_inline(h)}</th>" for h in header)
    rows = ""
    for r in body:
        tds = "".join(
            f"<td>{md_inline(c)}</td>" for c in (r + [""] * (len(header) - len(r)))[: len(header)]
        )
        rows += f"<tr>{tds}</tr>"
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{rows}</tbody></table>"


def md_to_html(md: str, *, allow_raw_html: bool = False) -> str:
    """Render a Markdown fragment to safe HTML. Everything is HTML-escaped via `md_inline`
    UNLESS `allow_raw_html=True`, which lets a raw <table>…</table> block through untouched —
    used ONLY for the app's own Python-built (already-escaped) tables. It must NEVER be set
    for LLM/model output, whose raw HTML would otherwise become a script-injection sink."""
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Pass-through for our own pre-built HTML tables (trusted callers only).
        if allow_raw_html and stripped.startswith("<table"):
            block = [line]
            i += 1
            while i < n and "</table>" not in lines[i]:
                block.append(lines[i])
                i += 1
            if i < n:
                block.append(lines[i])
                i += 1
            out.append("\n".join(block))
            continue

        # Headings.
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            level = min(len(m.group(1)) + 1, 5)  # never emit <h1> (the doc title owns it)
            out.append(f"<h{level}>{md_inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # Pipe tables (header row, separator row, body rows).
        if "|" in line and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            block = [lines[i], lines[i + 1]]
            i += 2
            while i < n and "|" in lines[i] and lines[i].strip():
                block.append(lines[i])
                i += 1
            out.append(_table_html(block))
            continue

        # Bullet lists.
        if re.match(r"^\s*[-*]\s+", line):
            items = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(f"<li>{md_inline(re.sub(r'^\s*[-*]\s+', '', lines[i]))}</li>")
                i += 1
            out.append(f"<ul>{''.join(items)}</ul>")
            continue

        # Block-quotes.
        if stripped.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(md_inline(re.sub(r"^\s*>\s?", "", lines[i])))
                i += 1
            out.append(f"<blockquote>{'<br>'.join(quote)}</blockquote>")
            continue

        # Paragraph (gather consecutive non-blank, non-structural lines).
        para = [line]
        i += 1
        while i < n and lines[i].strip() and not re.match(
            r"^\s*(#{1,4}\s|[-*]\s|>|\|)", lines[i]
        ) and not lines[i].strip().startswith("<table"):
            para.append(lines[i])
            i += 1
        out.append(f"<p>{md_inline(' '.join(s.strip() for s in para))}</p>")

    return "\n".join(out)


# ── LLM findings parsing ────────────────────────────────────────────────────────


def parse_findings(raw: str) -> dict | None:
    """Extract the findings JSON the analysis LLM returns. Tolerant of ```json fences and
    surrounding prose — grabs the first balanced {...} object. Returns None if unusable."""
    if not raw:
        return None
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        end = -1
        for j in range(start, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
        if end == -1:
            return None
        text = text[start:end]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


# ── report assembly ─────────────────────────────────────────────────────────────

_FINDINGS_SCHEMA = """{
  "title": "a concise report title",
  "subtitle": "one-line description of the analysis",
  "executive_summary": ["3-5 bullet strings; use **bold** for the key claim in each"],
  "sections": [
    {
      "heading": "section heading",
      "body": "one or more Markdown paragraphs; **bold**, *italic*, `code` and - bullets allowed",
      "table": { "columns": ["Col A", "Col B"], "rows": [["v1","v2"]], "note": "optional caption" }
    }
  ]
}"""


def build_analysis_prompt(project_title: str, instruction: str, transitions_md: str) -> str:
    """The ONLY thing sent to the LLM: the analysis instruction + the transition table,
    with a strict request for structured JSON so Python can lay the report out."""
    return (
        f"You are a process-mining analyst. Analyse the transition table for the project "
        f'"{project_title}".\n\n'
        f"TASK:\n{instruction}\n\n"
        "Respond with a SINGLE JSON object and nothing else — no prose, no code fence — "
        "matching exactly this shape:\n\n"
        f"{_FINDINGS_SCHEMA}\n\n"
        "Rules: 3-5 executive-summary bullets; 2-6 sections; put any tabular result in the "
        "section's `table` (omit `table` when not tabular); keep every claim grounded in the "
        "numbers below; do not invent columns that aren't in the data.\n\n"
        "## Transition table\n\n"
        f"{transitions_md}\n"
    )


def findings_parts(findings: dict) -> tuple[str, str, str, str]:
    """(title, subtitle, exec_summary_html, sections_html) from the parsed findings. The
    exec summary goes on the cover; the sections become the 'Analysis' chapter."""
    title = str(findings.get("title") or "Process Analysis").strip()
    subtitle = str(findings.get("subtitle") or "").strip()

    summary = findings.get("executive_summary") or []
    exec_html = ""
    if isinstance(summary, list) and summary:
        items = "".join(f"<li>{md_inline(str(s))}</li>" for s in summary)
        exec_html = f'<section class="callout"><h2>Executive summary</h2><ul>{items}</ul></section>'

    parts: list[str] = []
    sections = findings.get("sections") or []
    if isinstance(sections, list):
        for idx, sec in enumerate(sections, start=1):
            if not isinstance(sec, dict):
                continue
            heading = str(sec.get("heading") or "").strip()
            html_parts = []
            if heading:
                html_parts.append(f"<h2>{idx}. {md_inline(heading)}</h2>")
            if sec.get("body"):
                html_parts.append(md_to_html(str(sec["body"])))
            tbl = sec.get("table")
            if isinstance(tbl, dict) and tbl.get("columns") and tbl.get("rows"):
                cols = [str(c) for c in tbl["columns"]]
                thead = "".join(f"<th>{md_inline(c)}</th>" for c in cols)
                trs = ""
                for row in tbl["rows"]:
                    if not isinstance(row, list):
                        continue
                    cells = [str(c) for c in row]
                    cells = (cells + [""] * len(cols))[: len(cols)]
                    trs += "<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in cells) + "</tr>"
                html_parts.append(
                    f"<table><thead><tr>{thead}</tr></thead><tbody>{trs}</tbody></table>"
                )
                if tbl.get("note"):
                    html_parts.append(f'<p class="caption">{md_inline(str(tbl["note"]))}</p>')
            parts.append(f"<section>{''.join(html_parts)}</section>")

    return title, subtitle, exec_html, "\n".join(parts)


def strip_leading_heading(md: str) -> str:
    """Drop a leading ``## Heading`` line — the chapter title already carries it."""
    return re.sub(r"^\s*#{1,6}\s+.*\n", "", md.lstrip("\n"), count=1)


def sanitize_svg(svg: str) -> str:
    """Reduce an untrusted SVG string to a single <svg>…</svg> block with active content
    removed: <script> (paired or dangling), <foreignObject> (can carry XHTML), and every
    on*= event handler regardless of the character in front of it (`<svg onload=` AND the
    `<svg/onload=` separator trick). The result is additionally embedded via `svg_img` as an
    <img> data URI, which can't execute script at all — this is defence in depth."""
    if not svg:
        return ""
    m = re.search(r"<svg\b.*?</svg>", svg, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    block = m.group(0)
    # Paired then dangling <script>/<foreignObject>; then any leftover opening tags.
    block = re.sub(r"<script\b.*?</script>", "", block, flags=re.DOTALL | re.IGNORECASE)
    block = re.sub(r"<foreignObject\b.*?</foreignObject>", "", block, flags=re.DOTALL | re.IGNORECASE)
    block = re.sub(r"<(script|foreignObject)\b[^>]*>", "", block, flags=re.IGNORECASE)
    # Event handlers, separated from the tag/attr by whitespace OR a slash (both are valid
    # separators in a start tag). Keep a space so tokens don't fuse.
    block = re.sub(
        r"[\s/]on\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", " ", block, flags=re.IGNORECASE
    )
    return block


def svg_img(svg: str) -> str:
    """Embed the (sanitised) app SVG as an <img> data URI. An <img>-loaded SVG NEVER runs
    embedded scripts or event handlers, so this neutralises SVG-XSS irrespective of the
    sanitiser. Returns "" when there is no usable SVG."""
    clean = sanitize_svg(svg)
    if not clean:
        return ""
    b64 = base64.b64encode(clean.encode("utf-8")).decode("ascii")
    return f'<img class="diagram-svg" alt="Process flow diagram" src="data:image/svg+xml;base64,{b64}">'


_PAGE_CSS = """
:root{{--accent:{accent};--ink:#1a1a1a;--muted:#6b6b72;--hair:#e3e3e0;--soft:#f6f5fb;--good:#0ca30c;--bad:#d03b3b;}}
*{{box-sizing:border-box}}
html,body{{margin:0}}
body{{font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:#fff;}}
.report{{max-width:820px;margin:0 auto;padding:36px 44px 60px;}}
.rhead{{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;border-bottom:3px solid var(--accent);padding-bottom:14px;margin-bottom:8px;}}
.rhead .logo{{max-height:48px;max-width:190px}}
h1{{font-size:27px;line-height:1.15;margin:14px 0 4px;letter-spacing:-.01em}}
.subtitle{{color:var(--muted);font-size:15px;margin:0 0 6px}}
.meta{{color:var(--muted);font-size:11.5px;margin:0 0 22px}}
h2{{color:var(--accent);font-size:17px;margin:26px 0 8px}}
h3{{font-size:14.5px;margin:18px 0 6px}}
h4{{font-size:13px;margin:14px 0 6px}}
p{{margin:8px 0}}
ul{{margin:8px 0;padding-left:20px}}
li{{margin:3px 0}}
code{{background:var(--soft);border-radius:4px;padding:1px 5px;font-size:12.5px}}
blockquote{{border-left:3px solid var(--hair);margin:10px 0;padding:2px 12px;color:var(--muted)}}
.callout{{background:var(--soft);border:1px solid var(--hair);border-radius:12px;padding:6px 20px 14px;margin:18px 0}}
.callout h2{{margin-top:14px}}
.caption{{color:var(--muted);font-size:11.5px;margin-top:6px}}
table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:12.5px}}
th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--hair);vertical-align:top}}
th{{background:var(--soft);color:var(--accent);font-weight:650;white-space:nowrap}}
td:not(:first-child),th:not(:first-child){{text-align:right}}
.diagram{{border:1px solid var(--hair);border-radius:12px;padding:10px;margin:12px 0;background:#fcfcfb}}
.diagram svg,.diagram-svg{{width:100%;height:auto;display:block}}
.ltable td,.ltable th{{text-align:left}}
.toc{{margin:22px 0 8px;padding:12px 18px;border:1px solid var(--hair);border-radius:12px;background:#fcfcfb}}
.toc-title{{font-weight:650;color:var(--accent);font-size:12px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}}
.toc ol{{margin:0;padding-left:22px}}
.toc li{{margin:4px 0}}
.toc a{{color:var(--ink);text-decoration:none}}
.toc a:hover{{color:var(--accent);text-decoration:underline}}
.chapter{{break-before:page;padding-top:4px}}
.chapter-title{{font-size:23px;color:var(--accent);margin:0 0 16px;padding-bottom:9px;border-bottom:2px solid var(--accent);letter-spacing:-.01em}}
.foot{{margin-top:36px;padding-top:12px;border-top:1px solid var(--hair);color:var(--muted);font-size:11px}}
@page{{size:A4;margin:14mm}}
@media print{{.report{{max-width:none;padding:0}}h2,h3,.chapter-title{{break-after:avoid}}table,.diagram{{break-inside:avoid}}}}
"""


def render_report(
    *,
    meta: dict,
    style: dict,
    title: str,
    subtitle: str = "",
    exec_summary_html: str = "",
    chapters: list[dict],
) -> str:
    """Assemble the full standalone HTML report from a list of chapters, each
    ``{"id", "title", "html"}``. The cover carries the title, subtitle, letterhead and the
    executive summary, followed by a clickable table of contents; then every chapter begins
    on a fresh page under a large section title (the TOC links jump to it, on screen and in
    the printed PDF). ``meta`` = {user, source, generatedAt}; ``style`` = the admin theme."""
    # Re-validate the accent here even though it is validated on write: it is injected raw
    # into the CSS (`--accent:{accent}`), so a non-#rrggbb value (legacy/tampered data, or a
    # future caller) could otherwise break out of the <style> block. Fall back to the default.
    accent = str(style.get("accent") or "")
    if not re.match(r"^#[0-9a-fA-F]{6}$", accent):
        accent = "#4a3aa7"
    org = str(style.get("orgName") or "").strip()
    logo = style.get("logo") or ""
    logo_pos = "right" if str(style.get("logoPos") or "left").lower() == "right" else "left"

    # The cover letterhead is the logo image when one is configured, otherwise the
    # organisation name. It sits on the configured side of the header band. `logoScale`
    # (0.5–2.0) grows/shrinks it about the 48×190px base box while keeping its aspect ratio
    # (both bounds scale together, so the image is never distorted).
    try:
        logo_scale = min(2.0, max(0.5, float(style.get("logoScale") or 1.0)))
    except (TypeError, ValueError):
        logo_scale = 1.0
    logo_img = (
        f'<img class="logo" style="max-height:{48 * logo_scale:.0f}px;'
        f'max-width:{190 * logo_scale:.0f}px" src="{html.escape(logo, quote=True)}" alt="">'
        if logo.startswith("data:image/")
        else ""
    )
    org_div = f'<div class="org">{md_inline(org)}</div>' if org else ""
    # The logo sits on its configured side; the letterhead text fills the opposite slot so a
    # logo AND an organisation name can both appear. With no logo, the letterhead leads.
    if logo_img:
        left, right = (org_div, logo_img) if logo_pos == "right" else (logo_img, org_div)
    else:
        left, right = org_div, ""
    rhead = (
        f'<div class="rhead"><div class="brand">{left}</div>'
        f'<div class="brand" style="text-align:right">{right}</div></div>'
    )
    gen = str(meta.get("generatedAt") or datetime.now(timezone.utc).strftime("%d %b %Y"))
    # Footer credit names the LLM actually used (model · source), so the reader can see
    # which model produced the analysis — falls back to a generic line when unknown.
    llm_meta = str(meta.get("llm") or "").strip()
    llm_credit = f"analysis by {md_inline(llm_meta)}" if llm_meta else "analysis by the report LLM"
    metabits = [b for b in [
        f"Prepared for {md_inline(str(meta['user']))}" if meta.get("user") else "",
        gen,
        md_inline(str(meta.get("source") or "")),
    ] if b]

    toc = ""
    if chapters:
        items = "".join(
            f'<li><a href="#{html.escape(str(c["id"]), quote=True)}">{md_inline(str(c["title"]))}</a></li>'
            for c in chapters
        )
        toc = f'<nav class="toc"><div class="toc-title">Contents</div><ol>{items}</ol></nav>'

    chapters_html = "".join(
        f'<section class="chapter" id="{html.escape(str(c["id"]), quote=True)}">'
        f'<h1 class="chapter-title">{md_inline(str(c["title"]))}</h1>{c["html"]}</section>'
        for c in chapters
    )

    body = f"""<div class="report">
  {rhead}
  <h1>{md_inline(title)}</h1>
  {f'<p class="subtitle">{md_inline(subtitle)}</p>' if subtitle else ''}
  <p class="meta">{'  ·  '.join(metabits)}</p>
  {exec_summary_html}
  {toc}
  {chapters_html}
  <div class="foot">Generated by the Process Mining Demonstrator · {llm_credit} · layout assembled server-side.</div>
</div>"""

    css = _PAGE_CSS.format(accent=accent)
    # The report is a STATIC document — no <script>. It is rendered in a same-origin iframe
    # that is deliberately NOT granted `allow-scripts`, so even a sanitiser bypass in the
    # embedded content cannot execute. The host wires table-of-contents scrolling and printing
    # from the parent (it has same-origin access to the frame); the `href="#id"` anchors are
    # kept for the printed PDF's internal links.
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)}</title><style>{css}</style></head><body>{body}</body></html>"
    )
