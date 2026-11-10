import asyncio
from playwright.async_api import async_playwright
M = "HQUk9fNaMUn3jPGsbBKdbmWBF2D1JCc3VaoP5GGhpump"; B = "http://127.0.0.1:8799/web/index.html"
VIEWS = {"home": "__desk.go('home')", "agents": "__desk.go('agents')", "auditor": f"__desk.go('agents',{{agent:'auditor',mint:'{M}'}})",
         "coin": f"__desk.go('home',{{coin:'{M}'}})", "account": "__desk.go('account')", "activity": "__desk.go('activity')"}
async def go():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        for v, js in VIEWS.items():
            for kind, src in (("", "/fx/full"), ("_empty", "/fx/empty"), ("_error", "/fx/missing")):
                await pg.goto(f"{B}?src={src}"); await pg.wait_for_timeout(500)
                await pg.evaluate(f"window.__desk && {js}"); await pg.wait_for_timeout(3200 if v == "auditor" else 900)
                await pg.screenshot(path=f"/workspace/shots/{v}{kind}.png", full_page=True); print(v + kind)
        await b.close()
asyncio.run(go())
