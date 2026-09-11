"""Refinement pass: dialogs, wizards, login page and better-framed process maps."""
import json
import pathlib

from playwright.sync_api import sync_playwright

SP = pathlib.Path(
    "/private/tmp/claude-501/-Users-dirk-Work-Process-Mining-Web/"
    "28f7ad15-bb21-4cf5-a328-7709f32029cf/scratchpad"
)
OUT = SP / "screenshots"
TOK = json.loads((SP / "demo_tokens.json").read_text())
COOKIES = [
    {"name": n, "value": TOK[a], "domain": "127.0.0.1", "path": "/"}
    for n, a in (
        ("pmw_session", "app"),
        ("pmw_admin", "admin"),
        ("pmw_integration", "integration"),
    )
]
APP = "http://127.0.0.1:18080/"
INTEG = "http://127.0.0.1:18100/"
ok, bad = [], []


def shot(page, name, wait=900, full=False):
    page.wait_for_timeout(wait)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    ok.append(name)
    print(f"  OK  {name}", flush=True)


def step(label):
    def deco(fn):
        try:
            fn()
        except Exception as exc:
            bad.append((label, str(exc).splitlines()[0][:110]))
            print(f"  ERR {label}: {str(exc).splitlines()[0][:110]}", flush=True)

    return deco


def gate(page):
    page.wait_for_timeout(1200)
    if "Legal Disclaimer" in page.inner_text("body"):
        page.evaluate(
            "()=>document.querySelectorAll('*').forEach(e=>"
            "{if(e.scrollHeight>e.clientHeight+20)e.scrollTop=e.scrollHeight})"
        )
        page.wait_for_timeout(400)
        cb = page.locator("input[type=checkbox]")
        for i in range(cb.count()):
            try:
                cb.nth(i).check()
            except Exception:
                pass
        btn = page.get_by_role("button", name="Accept", exact=False).first
        if btn.count() and btn.is_enabled():
            btn.click()
        page.wait_for_timeout(2200)


def expand(page, title):
    """Expand a section only if it is not already expanded (the header toggles)."""
    hdr = page.locator("button").filter(has_text=title).first
    if "›" in hdr.inner_text():
        hdr.click()
        page.wait_for_timeout(900)


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome")

    # ── 1. Login page (no cookies) ───────────────────────────────────────────
    anon = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                               ignore_https_errors=True)
    p0 = anon.new_page()
    p0.goto(APP, wait_until="networkidle")
    shot(p0, "app-login", wait=2000)
    anon.close()

    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                              ignore_https_errors=True)
    ctx.add_cookies(COOKIES)
    conns = ctx.request.get(APP + "api/connections").json()
    ctx.request.post(f"{APP}api/connections/{conns[0]['id']}/connect")
    page = ctx.new_page()

    # ── 2. App: connection editor + legal gate figure ────────────────────────
    print("APP", flush=True)
    page.goto(APP, wait_until="networkidle")
    page.wait_for_timeout(1200)
    if "Legal Disclaimer" in page.inner_text("body"):
        shot(page, "app-00-legal-gate", wait=600)
    gate(page)
    page.wait_for_timeout(2500)

    @step("connection-editor")
    def _():
        expand(page, "CONNECTIONS")
        page.get_by_title("Edit connection").first.click()
        shot(page, "app-09-connection-editor", wait=2000, full=True)
        page.keyboard.press("Escape")
        page.wait_for_timeout(900)

    # Load a project, widen the date window to the whole range, fit the map.
    @step("project+fit")
    def _():
        expand(page, "PROJECTS")
        page.wait_for_timeout(2000)
        page.locator(".card").filter(has_text="Bookstore").first.click()
        page.wait_for_timeout(11000)
        # Drag the left slider handle to the far left so all journeys are in range.
        handles = page.locator("input[type=range], [role=slider]")
        if handles.count():
            for i in range(handles.count()):
                try:
                    handles.nth(i).focus()
                    for _ in range(40):
                        page.keyboard.press("Home")
                    break
                except Exception:
                    pass
        page.wait_for_timeout(4000)
        # Fit / reset zoom control (bottom-right of the canvas)
        for t in ("Fit view", "Fit", "Reset view", "Zoom to fit"):
            b = page.get_by_title(t)
            if b.count():
                b.first.click()
                break
        page.wait_for_timeout(2500)
        shot(page, "app-03-achart", wait=2000)

    # ── 3. Integration console: wizards and dialogs ──────────────────────────
    print("INTEGRATION", flush=True)
    page.goto(INTEG, wait_until="networkidle")
    gate(page)
    page.wait_for_timeout(3000)

    @step("source-type-wizard")
    def _():
        expand(page, "SOURCE TYPES")
        page.wait_for_timeout(800)
        page.locator(".card").filter(has_text="Apache").first.click()
        page.wait_for_timeout(2500)
        shot(page, "integ-04-source-type-wizard", wait=1200, full=True)
        # STEPS tab holds the compound rules
        for label in ("STEPS", "Steps"):
            t = page.get_by_text(label, exact=True)
            if t.count():
                t.first.click()
                page.wait_for_timeout(1400)
                shot(page, "integ-05-compound-steps", wait=1000, full=True)
                break
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

    @step("source-wizard")
    def _():
        expand(page, "SOURCES")
        page.wait_for_timeout(800)
        page.locator(".card").filter(has_text="Shop access log").first.click()
        page.wait_for_timeout(3000)
        shot(page, "integ-06-source-wizard", wait=1500, full=True)
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

    @step("run-dialog")
    def _():
        expand(page, "SOURCES")
        page.wait_for_timeout(600)
        for t in ("Run", "Run source", "▷"):
            b = page.get_by_title(t)
            if b.count():
                b.first.click()
                break
        else:
            page.locator("button").filter(has_text="▷").first.click()
        page.wait_for_timeout(3500)
        shot(page, "integ-07-run-dialog", wait=1500, full=True)

    browser.close()

print("\nOK:", len(ok), "| FAILED:", len(bad))
for n, e in bad:
    print("  -", n, "|", e)
