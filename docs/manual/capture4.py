"""Fourth pass: wizard steps, run dialog, populated pipeline, admin sub-tabs, conn editor."""
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


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome")
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                              ignore_https_errors=True)
    ctx.add_cookies(COOKIES)

    # ── Run a real import so KPIs and the pipeline show live data ────────────
    srcs = ctx.request.get(INTEG + "api/integration/sources").json()
    conns = ctx.request.get(INTEG + "api/connections").json()
    print("sources:", [(s["id"][:8], s["name"]) for s in srcs], flush=True)
    if srcs and conns:
        r = ctx.request.post(
            f"{INTEG}api/integration/sources/{srcs[0]['id']}/run",
            data={"projectId": "SHOP-LOG", "connectionId": conns[0]["id"], "delta": True},
        )
        print("import:", r.status, r.text()[:220], flush=True)

    page = ctx.new_page()

    # ── Integration: populated console + wizard steps + run dialog ───────────
    print("INTEGRATION", flush=True)
    page.goto(INTEG, wait_until="networkidle")
    gate(page)
    page.wait_for_timeout(3500)
    shot(page, "integ-01-console", wait=1500)
    page.screenshot(path=str(OUT / "integ-01-console-full.png"), full_page=True)
    shot(page, "integ-09-kpis-pipeline", wait=300)

    @step("sourcetype-wizard-steps")
    def _():
        page.locator("button").filter(has_text="SOURCE TYPES").first.click()
        page.wait_for_timeout(900)
        page.locator(".card").filter(has_text="Apache").first.click()
        page.wait_for_timeout(2500)
        shot(page, "integ-04-source-type-wizard", wait=1000, full=True)
        for i in (2, 3):
            nxt = page.get_by_role("button", name="Next", exact=False)
            if not nxt.count():
                print(f"   no Next for step {i}", flush=True)
                break
            nxt.first.click()
            page.wait_for_timeout(2200)
            shot(page, f"integ-04{chr(96+i)}-source-type-step{i}", wait=900, full=True)
        body = page.inner_text("body")
        print("   step3 text:", " | ".join(body.split("\n")[18:46]), flush=True)
        page.keyboard.press("Escape")
        page.wait_for_timeout(1200)

    @step("run-dialog")
    def _():
        page.locator("button").filter(has_text="SOURCES").first.click()
        page.wait_for_timeout(1000)
        btns = page.locator("button")
        labels = [(i, (btns.nth(i).get_attribute("title") or "").strip(),
                   btns.nth(i).inner_text().strip()[:18]) for i in range(btns.count())]
        print("   buttons:", [x for x in labels if x[1] or x[2]][:26], flush=True)
        target = None
        for i, title, text in labels:
            if "run" in (title or "").lower() or "▷" in text:
                target = i
                break
        if target is None:
            raise RuntimeError("no run button found")
        btns.nth(target).click()
        page.wait_for_timeout(3500)
        shot(page, "integ-07-run-dialog", wait=1200, full=True)
        page.keyboard.press("Escape")
        page.wait_for_timeout(900)

    # ── App: connection editor ───────────────────────────────────────────────
    print("APP", flush=True)
    page.goto(APP, wait_until="networkidle")
    gate(page)
    page.wait_for_timeout(4000)
    shot(page, "app-08-connections", wait=800)

    @step("connection-editor")
    def _():
        btns = page.locator("aside button")
        info = [(i, (btns.nth(i).get_attribute("title") or ""), btns.nth(i).inner_text().strip()[:16])
                for i in range(btns.count())]
        print("   sidebar buttons:", info[:20], flush=True)
        idx = next((i for i, t, x in info if "edit" in (t or "").lower() or "✎" in x), None)
        if idx is None:
            raise RuntimeError("no edit control in sidebar")
        btns.nth(idx).click()
        page.wait_for_timeout(2500)
        shot(page, "app-09-connection-editor", wait=1200, full=True)
        page.keyboard.press("Escape")

    # ── Admin: Database Connections sub-tabs ─────────────────────────────────
    print("ADMIN", flush=True)
    page.goto(ADMIN, wait_until="networkidle")
    page.wait_for_timeout(2200)

    @step("admin-subtabs")
    def _():
        page.get_by_role("button", name="Database Connections", exact=True).first.click()
        page.wait_for_timeout(2500)
        page.locator(".card, .conn-row, tr").first.click(timeout=5000)
        page.wait_for_timeout(2000)
        shot(page, "admin-05b-connection-detail", wait=1000, full=True)
        body = page.inner_text("body")
        print("   detail text:", " | ".join(body.split("\n")[:40]), flush=True)

    browser.close()

print("\nOK:", len(ok), "| FAILED:", len(bad))
for n, e in bad:
    print("  -", n, "|", e)
