# Offline user manual — build sources

This directory holds the **editable source** of the printed/offline user manual. The
generated PDF lives one level up at `docs/Process-Mining-Demonstrator-Manual.pdf`.

> **When a feature changes or is added, update the relevant chapter here and rebuild.**
> The PDF is a build artifact — never hand-edit it, and never edit `manual.html`
> (also generated). Edit the chapter fragments and, if the UI changed, recapture the
> affected screenshots, then run the assembler.

## Layout

| Path | What it is |
|---|---|
| `chapters/NN-slug.html` | One HTML **fragment** per chapter (24 of them). This is the content you edit. No `<!doctype>`/`<html>`/`<head>` — just a `<section class="chapter" …>`. |
| `manual.css` | The A4 print stylesheet: page size/margins, cover, part dividers, TOC, callouts, tables, figures, numbered-step markers, ligature-safe headings. |
| `assemble.py` | Builds the cover + front matter + contents + part dividers, resolves figures, and renders the PDF in **two passes** (discover page numbers → rewrite the TOC with them). |
| `screenshots/*.png` | The figure library. A chapter references one by key: `<figure data-fig="KEY"><figcaption>…</figcaption></figure>`. The assembler substitutes `screenshots/KEY.png`, numbers it `Figure C.n`, or **drops the figure if the PNG is missing** (no broken images). |
| `research/*.md` | Manual-grade notes taken from the source code, one per subsystem. The chapters were written from these; keep them as the reference when extending a chapter so you don't invent behaviour. |
| `capture*.py` | Playwright scripts that drove a throwaway demo instance to take the screenshots. Reference material for recapturing (see below). |

## Rebuild the PDF (content-only change, no new screenshots)

The build needs a Python venv with `playwright` (with the Chrome channel), `pypdf` and
`pymupdf`. Create it once anywhere (it is **not** committed):

```bash
python3.13 -m venv /tmp/manualvenv
/tmp/manualvenv/bin/pip install playwright pypdf pymupdf
/tmp/manualvenv/bin/playwright install chrome   # or: channel=chrome already installed
```

Then, after editing any `chapters/NN-*.html`:

```bash
/tmp/manualvenv/bin/python docs/manual/assemble.py
```

It writes `docs/manual/Process-Mining-Demonstrator-Manual.pdf`. Copy it up to
`docs/` to publish it:

```bash
cp docs/manual/*.pdf docs/Process-Mining-Demonstrator-Manual.pdf
```

> `assemble.py` uses absolute scratchpad paths from the session it was written in. If it
> errors on paths, update the `SP`/`MAN`/`SHOTS`/`LOGO` constants at the top to point at
> this `docs/manual/` directory and the repo `logo.svg`. (Chapters, `manual.css` and
> `screenshots/` are all here; `LOGO` is `frontend/web/public/logo.svg`.)

## Add or update a chapter

1. Copy the shape of an existing fragment: `<section class="chapter" id="ch-SLUG"
   data-title="TITLE" data-num="N"> … </section>`, opening with
   `<h1><span class="chnum">N</span> Title</h1>` and a `<p class="chintro">…</p>`.
   The assembler locates the chapter's page in the PDF by matching the heading **plus**
   the first words of the chintro, so keep both present and distinctive.
2. Use the pre-styled blocks: `.note`, `.tip`, `.warn`, `.role`, `<ol class="steps">`,
   `<table>`, `<pre><code>`, `<dl>`, and `<figure data-fig="KEY">`.
3. Register it in `assemble.py`'s `PARTS` list (the `range()` that a chapter number falls
   into decides which of the five parts it prints under, and its slot in the contents).
4. Rebuild.

## Recapture screenshots (UI changed)

Figures come from a **throwaway** instance, never production and never real credentials:

1. Start a second copy of the app on spare ports with its own temp data dir, e.g.
   `PMW_DATA_DIR=<tmp>/demo` on `18080/18090/18100`, seed a disposable admin, connect it
   to a local Exasol (the repo's `exanano`), provision the schema and generate demo data.
2. Mint per-surface session cookies (`pmw_session`/`pmw_admin`/`pmw_integration`) from
   that instance's store so Playwright can drive it headless — see `capture*.py`. Adapt
   the port numbers, the connection id and the source/source-type names to match the seed.
3. Save PNGs into `screenshots/` under the **exact `data-fig` key** a chapter uses.

The screenshots carry only the bundled demo datasets (Online Bookstore / Online Credit
Application), so they are safe to commit.

## Notes / gotchas learned building this

- **Ligatures**: Chrome's PDF text layer renders `fi`/`fl` as ligature glyphs. The
  page-number matcher in `assemble.py` normalises them (and curly quotes/dashes) — keep
  that `_norm()` if you touch it, or the TOC page numbers break.
- **Gradient headings**: `background-clip:text` leaks a hairline box in Chrome's print
  path, so the cover/part titles use a **solid** brand colour (`#4b74ef`). The gradient
  `.rule` bars are real filled divs and are fine.
- **Contents fits one page** at the current `.toc` spacing with 24 chapters + 5 parts.
  Adding chapters may push it over; tighten `.toc li` / `.toc-part` margins if so.
