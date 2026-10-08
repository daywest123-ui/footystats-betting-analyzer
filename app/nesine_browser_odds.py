"""Browser-backed Nesine bulletin snapshot for GitHub Actions.

The browser is used only to obtain the public read-only JSON feed with the same
cookies/session a normal visitor gets. No login, betting action, or account
access is performed.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright

PAGE_URL = "https://www.nesine.com/iddaa/futbol"
API_URL = "https://bulten.nesine.com/api/bulten/getprebultenfull"


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="tr-TR",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)
        payload = await page.evaluate(
            """async ({url, cachebuster}) => {
                const response = await fetch(url + "?_=" + cachebuster, {
                    credentials: "include",
                    cache: "no-store",
                    headers: {"Accept": "application/json,text/plain,*/*"}
                });
                if (!response.ok) throw new Error("Nesine API HTTP " + response.status);
                return await response.json();
            }""",
            {"url": API_URL, "cachebuster": time.time_ns()},
        )
        await browser.close()

    path = Path("reports/nesine_prebulten.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    events = len((payload.get("sg") or {}).get("EA") or [])
    print(f"[NesineBrowser] Saved public bulletin snapshot: {events} events")


if __name__ == "__main__":
    asyncio.run(main())
