"""Local FootyStats browser-session connector.

This connector never asks for or stores an email/password. It attaches only to a
Chrome instance that the user has already opened with remote debugging enabled,
then exports data visible to that authenticated browser session.

Use only with pages/data your account is authorized to access.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

def collect(port: int, output: str) -> None:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.debugger_address = f"127.0.0.1:{port}"
    driver = webdriver.Chrome(options=options)

    payload = driver.execute_script("""
        const tables = [...document.querySelectorAll('table')].map(t => ({
          text: (t.innerText || '').trim()
        })).filter(x => x.text);
        return {
          url: location.href,
          title: document.title,
          body_text: (document.body.innerText || '').trim(),
          tables: tables
        };
    """)

    payload["collected_at_utc"] = datetime.now(timezone.utc).isoformat()
    payload["source"] = "footystats_local_browser_session"

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Collected FootyStats snapshot: {path.resolve()}")
    print(f"Page: {payload['title']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--output", default="data/footystats_snapshot.json")
    args = parser.parse_args()
    collect(args.port, args.output)
