"""Preflight diagnostics for the 20-minute coupon engine."""
from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Istanbul")


def check(label, fn):
    try:
        value = fn()
        print(f"[PASS] {label}: {value}")
        return True
    except Exception as exc:
        print(f"[FAIL] {label}: {type(exc).__name__}: {exc}")
        return False


def main():
    print("=== 20-MIN ENGINE PREFLIGHT ===")
    now = datetime.now(timezone.utc)
    print(f"UTC: {now.isoformat()}")
    print(f"Local: {now.astimezone(LOCAL_TZ).isoformat()}")
    ok = True
    ok &= check("Python >= 3.12", lambda: sys.version.split()[0] if sys.version_info >= (3, 12) else (_ for _ in ()).throw(RuntimeError(sys.version)))
    ok &= check("OddsHarvester import", lambda: importlib.import_module("oddsharvester").__name__)
    ok &= check("Playwright import", lambda: importlib.import_module("playwright").__name__)
    ok &= check("Chromium executable", lambda: _chromium())
    ok &= check("OddsHarvester CLI", lambda: _cli_help())
    ok &= check("Engine imports", lambda: _engine_imports())
    ok &= check("Fixture source", lambda: _fixture_probe())
    print("PREFLIGHT_RESULT=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def _chromium():
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    try:
        path = p.chromium.executable_path
        if not os.path.exists(path):
            raise RuntimeError(path)
        return path
    finally:
        p.stop()


def _cli_help():
    exe = shutil.which("oddsharvester")
    if not exe:
        raise RuntimeError("oddsharvester executable not found")
    r = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout)[-1000:])
    return "ok"


def _engine_imports():
    import app.run_20min_coupon
    import app.odds_harvester_client
    import app.football_data_client
    return "ok"


def _fixture_probe():
    from app.football_data_client import load_openfootball
    rows = load_openfootball()
    local_day = datetime.now(timezone.utc).astimezone(LOCAL_TZ).date().isoformat()
    today_rows = [r for r in rows if r.get("date") == local_day and not r.get("finished")]
    return f"total={len(rows)}, local_day={local_day}, today_unfinished={len(today_rows)}"


if __name__ == "__main__":
    raise SystemExit(main())
