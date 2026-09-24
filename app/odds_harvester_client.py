"""Optional current-odds adapter using the MIT-licensed OddsHarvester project.

The adapter is deliberately defensive: scraper failures never crash the main
analysis pipeline. Results are cached for the current run to avoid repeated
browser launches.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CACHE: dict[str, list[dict[str, Any]]] = {}
TIMEOUT_SECONDS = 6 * 60


def _norm(value: str) -> str:
    import re
    value = re.sub(r"\b(fc|afc|cf|sc|calcio|club)\b", "", str(value), flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _parse_float(value: Any) -> float | None:
    try:
        x = float(str(value).replace(",", "."))
        return x if x > 1.0 else None
    except (ValueError, TypeError):
        return None


def _market_name(value: str) -> str | None:
    s = str(value or "").lower().replace("-", "_").replace(" ", "_")
    if "1x2" in s or s in {"match_result", "full_time_result"}:
        return "1x2"
    if "btts" in s or "both_teams_to_score" in s:
        return "btts"
    if "over_under" in s or "total_goals" in s or "goals_over_under" in s:
        return "ou"
    return None


def _outcome_name(value: Any) -> str | None:
    s = str(value or "").strip().lower()
    if s in {"1", "home", "home_win", "home team"}:
        return "home_win"
    if s in {"x", "draw", "tie"}:
        return "draw"
    if s in {"2", "away", "away_win", "away team"}:
        return "away_win"
    if s in {"yes", "btts_yes", "both teams to score yes"}:
        return "btts_yes"
    if s in {"no", "btts_no", "both teams to score no"}:
        return "btts_no"
    if "over" in s and ("2.5" in s or "2_5" in s):
        return "over_2_5"
    if "under" in s and ("2.5" in s or "2_5" in s):
        return "under_2_5"
    return None


def _extract_odds(record: dict[str, Any]) -> dict[str, float]:
    """Normalize OddsHarvester's market-specific schema to engine market keys."""
    result: dict[str, float] = {}

    def put(key: str, value: Any) -> None:
        price = _parse_float(value)
        if price:
            result[key] = max(result.get(key, 0.0), price)

    # Current OddsHarvester output uses fields such as 1x2_market,
    # btts_market and over_under_2_5_market.
    for field, rows in record.items():
        if not isinstance(field, str) or not field.endswith("_market"):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key, value in row.items():
                k = str(key).strip().lower()
                if field.startswith("1x2_"):
                    if k == "1":
                        put("home_win", value)
                    elif k == "x":
                        put("draw", value)
                    elif k == "2":
                        put("away_win", value)
                elif field.startswith("btts_"):
                    if k in {"btts_yes", "yes"}:
                        put("btts_yes", value)
                    elif k in {"btts_no", "no"}:
                        put("btts_no", value)
                elif field.startswith("over_under_2_5_"):
                    if k == "odds_over":
                        put("over_2_5", value)
                    elif k == "odds_under":
                        put("under_2_5", value)

    # Also support generic/community records.
    odds = record.get("odds")
    if isinstance(odds, dict):
        for key, value in odds.items():
            outcome = _outcome_name(key)
            put(outcome, value) if outcome else None
    elif isinstance(odds, list):
        for item in odds:
            if not isinstance(item, dict):
                continue
            outcome = _outcome_name(item.get("outcome") or item.get("name") or item.get("label"))
            if outcome:
                put(outcome, item.get("odds") or item.get("price") or item.get("value"))
    return result

def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("matches", "events", "data", "results", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        return [payload]
    return []


def _load_output(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _records(payload)


def _run_cli(day: str) -> list[dict[str, Any]]:
    output = Path(tempfile.gettempdir()) / f"footy_oddsharvester_{day}.json"
    if output.exists():
        output.unlink()
    # OddsHarvester expects YYYYMMDD; the engine uses ISO YYYY-MM-DD.
    cli_day = day.replace("-", "")
    cmd = [
        sys.executable, "-m", "oddsharvester",
        "upcoming", "-s", "football", "-d", cli_day,
        "-m", "1x2,btts,over_under",
        "--headless",
        "-f", "json", "-o", str(output),
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, env=env
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            if detail:
                print("[OddsHarvester] CLI failed: " + detail[-2500:])
            else:
                print(f"[OddsHarvester] CLI failed with exit code {completed.returncode}")
            return []
        if not output.exists():
            print("[OddsHarvester] CLI exited successfully but produced no JSON output")
            return []
        try:
            records = _load_output(output)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[OddsHarvester] Invalid JSON output: {type(exc).__name__}")
            return []
        print(f"[OddsHarvester] Retrieved {len(records)} records for {day}")
        return records
    except subprocess.TimeoutExpired:
        print(f"[OddsHarvester] Timeout after {TIMEOUT_SECONDS}s for {day}")
        return []
    except OSError as exc:
        print(f"[OddsHarvester] Process error: {exc}")
        return []


def collect_day(day: str) -> list[dict[str, Any]]:
    if day not in _CACHE:
        _CACHE[day] = _run_cli(day)
    return _CACHE[day]


def current_fixtures(day: str) -> list[dict[str, Any]]:
    """Return today's upcoming fixture metadata from the cached scrape."""
    out = []
    for record in collect_day(day):
        home = str(record.get("home_team") or "").strip()
        away = str(record.get("away_team") or "").strip()
        if not home or not away:
            continue
        kickoff = str(record.get("kickoff") or record.get("kickoff_text") or "")
        league = str(record.get("league") or record.get("league_name") or "OddsPortal")
        out.append({
            "home": home,
            "away": away,
            "league": league,
            "date": day,
            "time": kickoff,
            "finished": False,
            "source": "OddsHarvester/OddsPortal"
        })
    return out


def fixture_odds(home: str, away: str, day: str) -> dict[str, float]:
    hk, ak = _norm(home), _norm(away)
    found: dict[str, list[float]] = {
        "home_win": [], "draw": [], "away_win": [],
        "btts_yes": [], "btts_no": [], "over_2_5": [], "under_2_5": []
    }
    for record in collect_day(day):
        rh, ra = record.get("home_team"), record.get("away_team")
        if _norm(rh) != hk or _norm(ra) != ak:
            continue
        markets = record.get("markets")
        if isinstance(markets, list):
            for market in markets:
                if not isinstance(market, dict):
                    continue
                parsed = _extract_odds(market)
                for key, value in parsed.items():
                    found[key].append(value)
        parsed = _extract_odds(record)
        for key, value in parsed.items():
            found[key].append(value)
    return {key: max(values) for key, values in found.items() if values}


def status() -> dict[str, Any]:
    try:
        import oddsharvester  # noqa: F401
        return {"installed": True}
    except ImportError:
        return {"installed": False}
