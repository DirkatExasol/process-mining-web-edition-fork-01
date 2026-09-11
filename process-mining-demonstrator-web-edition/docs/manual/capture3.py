"""Third pass: connection editor, compound-steps tab, admin sub-tabs, watchdog."""
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
    for n, a in (("pmw_session", "app"), ("pmw_admin", "admin"), ("pmw_integration", "integration"))
]
APP, ADMIN, INTEG = "http://127.0.0.1:18080/", "http://127.0.0.1:18090/", "http://127.0.0.1:18100/"
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
        page.evaluate("()=>document.querySelectorAll('*').forEach(e=>"
                      "{if(e.scrollHeight>e.clientHeight+20)e.scrollTop=e.scrollHeight})")
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
    hdr = page.locator("button").filter(has_text=title).first
    if "›" in hdr.inner_text():
        hdr.click()
        page.wait_for_timeout(900)


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome")
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                              ignore_https_errors=True)
    ctx.add_cookies(COOKIES)
    conns = ctx.request.get(APP + "api/connections").json()
    ctx.request.post(f"{APP}api/connections/{conns[0]['id']}/connect")
    page = ctx.new_page()

    # ── App: connection editor ───────────────────────────────────────────────
    print("APP", flush=True)
    page.goto(APP, wait_until="networkidle")
    gate(page)
    page.wait_for_timeout(2500)

    @step("connection-editor")
    def _():
        expand(page, "CONNECTIONS")
        page.wait_for_timeout(700)
        btns = page.locator("button").filter(has_text="✎")
        print("   pencil buttons:", btns.count(), flush=True)
        btns.first.click()
        page.wait_for_timeout(2500)
        shot(page, "app-09-connection-editor", wait=1200, full=True)
        page.keyboard.press("Escape")
        page.wait_for_timeout(900)

    # ── Integration: compound steps tab + watchdog ───────────────────────────
    print("INTEGRATION", flush=True)
    page.goto(INTEG, wait_until="networkidle")
    gate(page)
    page.wait_for_timeout(3000)

    @step("compound-steps")
    def _():
        expand(page, "SOURCE TYPES")
        page.wait_for_timeout(800)
        page.locator(".card").filter(has_text="Apache").first.click()
        page.wait_for_timeout(3000)
        txt = page.inner_text("body")
        print("   wizard text sample:", " | ".join(txt.split("\n")[:26]), flush=True)
        for lbl in ("STEPS", "Steps", "COMPOUND", "Compound"):
            t = page.get_by_text(lbl, exact=True)
            if t.count():
                print("   clicking tab:", lbl, flush=True)
                t.first.click()
                page.wait_for_timeout(1800)
                shot(page, "integ-05-compound-steps", wait=1000, full=True)
                break
        else:
            print("   no STEPS tab found", flush=True)
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

    @step("watchdog")
    def _():
        expand(page, "SOURCES")
        page.wait_for_timeout(700)
        page.locator(".card").filter(has_text="Shop access log").first.click()
        page.wait_for_timeout(3000)
        cb = page.locator("input[type=checkbox]")
        print("   checkboxes in source wizard:", cb.count(), flush=True)
        for i in range(cb.count()):
            try:
                cb.nth(i).check()
                page.wait_for_timeout(900)
            except Exception:
                pass
        shot(page, "integ-08-watchdog", wait=1500, full=True)
        page.keyboard.press("Escape")
        page.wait_for_timeout(900)

    # ── Admin: Database Connections sub-tabs ─────────────────────────────────
    print("ADMIN", flush=True)
    page.goto(ADMIN, wait_until="networkidle")
    page.wait_for_timeout(2200)

    @step("admin-subtabs")
    def _():
        page.get_by_role("button", name="Database Connections", exact=True).first.click()
        page.wait_for_timeout(2000)
        for i, sub in enumerate(("Database", "LLM", "Projects"), start=1):
            b = page.get_by_role("button", name=sub, exact=True)
            print(f"   sub-tab {sub}: {b.count()}", flush=True)
            if b.count():
                b.first.click()
                page.wait_for_timeout(2200)
                shot(page, f"admin-05{chr(96+i)}-connections-{sub.lower()}", wait=1200, full=True)

    browser.close()

print("\nOK:", len(ok), "| FAILED:", len(bad))
for n, e in bad:
    print("  -", n, "|", e)
