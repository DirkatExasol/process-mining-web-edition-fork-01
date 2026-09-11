"""Capture the manual's figures from the throwaway demo instance (ports 18080/18090/18100)."""
import json
import pathlib

from playwright.sync_api import sync_playwright

SP = pathlib.Path(
    "/private/tmp/claude-501/-Users-dirk-Work-Process-Mining-Web/"
    "28f7ad15-bb21-4cf5-a328-7709f32029cf/scratchpad"
)
OUT = SP / "screenshots"
OUT.mkdir(exist_ok=True)
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
ADMIN = "http://127.0.0.1:18090/"
INTEG = "http://127.0.0.1:18100/"

ok: list[str] = []
bad: list[tuple[str, str]] = []


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
            bad.append((label, str(exc).splitlines()[0][:100]))
            print(f"  ERR {label}: {str(exc).splitlines()[0][:100]}", flush=True)

    return deco


def gate(page):
    """Accept the legal disclaimer (fresh browser profile each run)."""
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


def sect(page, title):
    page.locator("button").filter(has_text=title).first.click()
    page.wait_for_timeout(800)


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome")
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        device_scale_factor=2,
        ignore_https_errors=True,
    )
    ctx.add_cookies(COOKIES)

    # Establish the DB connection server-side first — the UI click is flaky on the
    # first TLS handshake, and connection state lives on the server anyway.
    conns = ctx.request.get(APP + "api/connections").json()
    cid = conns[0]["id"]
    print("connecting:", ctx.request.post(f"{APP}api/connections/{cid}/connect").json(), flush=True)

    page = ctx.new_page()

    # ── APP ──────────────────────────────────────────────────────────────────
    print("APP", flush=True)
    page.goto(APP, wait_until="networkidle")
    gate(page)
    page.wait_for_timeout(2500)
    shot(page, "app-01-shell")

    @step("projects")
    def _():
        sect(page, "PROJECTS")
        page.wait_for_timeout(2500)
        shot(page, "app-02-projects")
        page.locator(".card").filter(has_text="Bookstore").first.click()
        page.wait_for_timeout(11000)

    shot(page, "app-03-achart", wait=3500)
    shot(page, "app-03b-achart-full", wait=500, full=True)

    for _n, _l in [
        ("app-04-metrics", "METRICS"),
        ("app-05-filters", "FILTERS"),
        ("app-06-sampling", "SAMPLING"),
        ("app-07-configuration", "CONFIGURATION"),
        ("app-08-connections", "CONNECTIONS"),
    ]:

        @step(_n)
        def _(n=_n, ll=_l):
            sect(page, ll)
            shot(page, n)

    @step("connection-editor")
    def _():
        sect(page, "CONNECTIONS")
        page.wait_for_timeout(600)
        page.get_by_title("Edit connection").first.click()
        shot(page, "app-09-connection-editor", wait=1800)
        page.keyboard.press("Escape")
        page.wait_for_timeout(900)

    MODES = [
        "B-Chart",
        "A/B Comparison",
        "Individual Journey",
        "AI supported Documentation",
        "Statistics",
        "Conformance Check",
        "Happy Path",
        "Notes",
        "Simulation",
    ]
    for _i, _mode in enumerate(MODES, start=10):

        @step(f"mode:{_mode}")
        def _(m=_mode, idx=_i):
            page.get_by_title("Switch view").first.click()
            page.wait_for_timeout(800)
            page.get_by_text(m, exact=True).first.click()
            page.wait_for_timeout(5500)
            slug = m.lower().replace(" ", "-").replace("/", "-")
            shot(page, f"app-{idx}-{slug}", wait=2500)

    @step("help")
    def _():
        page.get_by_title("Help").first.click()
        shot(page, "app-19-help", wait=2000)
        page.keyboard.press("Escape")

    # ── ADMIN ────────────────────────────────────────────────────────────────
    print("ADMIN", flush=True)
    page.goto(ADMIN, wait_until="networkidle")
    page.wait_for_timeout(2200)
    shot(page, "admin-01-overview")
    TABS = [
        "App Control",
        "TLS / SSL",
        "Users",
        "Database Connections",
        "Directory (LDAP)",
        "Logging",
        "Backup",
        "Customize",
        "Integration",
    ]
    for _i, _tab in enumerate(TABS, start=2):

        @step(f"admin:{_tab}")
        def _(t=_tab, idx=_i):
            page.get_by_role("button", name=t, exact=True).first.click()
            page.wait_for_timeout(1800)
            slug = (
                t.lower().replace(" / ", "-").replace(" ", "-").replace("(", "").replace(")", "")
            )
            shot(page, f"admin-{idx:02d}-{slug}", wait=1200)
            page.screenshot(path=str(OUT / f"admin-{idx:02d}-{slug}-full.png"), full_page=True)

    # ── INTEGRATION ──────────────────────────────────────────────────────────
    print("INTEGRATION", flush=True)
    page.goto(INTEG, wait_until="networkidle")
    gate(page)
    page.wait_for_timeout(3000)
    shot(page, "integ-01-console")
    page.screenshot(path=str(OUT / "integ-01-console-full.png"), full_page=True)

    @step("integ:sources")
    def _():
        page.locator("button").filter(has_text="SOURCES").first.click()
        page.wait_for_timeout(900)
        shot(page, "integ-02-sources")

    @step("integ:sourcetypes")
    def _():
        page.locator("button").filter(has_text="SOURCE TYPES").first.click()
        page.wait_for_timeout(900)
        shot(page, "integ-03-source-types")

    browser.close()

print("\nOK:", len(ok), "| FAILED:", len(bad))
for _n, _e in bad:
    print("  -", _n, "|", _e)
