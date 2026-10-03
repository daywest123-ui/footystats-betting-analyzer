"""Keyless OddsHarvester-compatible odds adapter.

The adapter is deliberately optional: tests and the core analyzer do not require
an external service.  When configured, it can consume JSON records produced by
OddsHarvester and expose normalized 1X2 / BTTS / O2.5 prices to the analyzer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

_CACHE: dict[str, list[dict[str, Any]]] = {}

_DEFAULT_PATHS = (
    Path("data/odds_harvester"),
    Path("data/odds-harvester"),
    Path("data/odds"),
)


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 1.0 else None


def _extract_odds(record: dict[str, Any]) -> dict[str, float]:
    """Normalize common OddsHarvester market schemas into project market names."""
    result: dict[str, float] = {}

    for row in record.get("1x2_market") or []:
        if not isinstance(row, dict):
            continue
        for source, target in (("1", "home_win"), ("X", "draw"), ("2", "away_win")):
            value = _as_float(row.get(source))
            if value is not None:
                result[target] = value
        if result:
            break

    for row in record.get("btts_market") or []:
        if not isinstance(row, dict):
            continue
        for source, target in (("btts_yes", "btts_yes"), ("btts_no", "btts_no")):
            value = _as_float(row.get(source))
            if value is not None:
                result[target] = value
        if "btts_yes" in result or "btts_no" in result:
            break

    for row in record.get("over_under_2_5_market") or []:
        if not isinstance(row, dict):
            continue
        for source, target in (("odds_over", "over_2_5"), ("odds_under", "under_2_5")):
            value = _as_float(row.get(source))
            if value is not None:
                result[target] = value
        if "over_2_5" in result or "under_2_5" in result:
            break

    # Also accept already-normalized records.
    for key in ("home_win", "draw", "away_win", "btts_yes", "btts_no", "over_2_5", "under_2_5"):
        value = _as_float(record.get(key))
        if value is not None:
            result[key] = value

    return result


def _normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").split())


def _load_json_file(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(payload, dict):
        for key in ("matches", "fixtures", "events", "data", "results"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def _load_local(date: str) -> list[dict[str, Any]]:
    candidates: list[Path] = []
    for directory in _DEFAULT_PATHS:
        candidates.extend(
            [
                directory / f"{date}.json",
                directory / f"odds_{date}.json",
                directory / f"fixtures_{date}.json",
            ]
        )
    for path in candidates:
        if path.exists():
            return _load_json_file(path)
    return []


def _fetch_remote(date: str) -> list[dict[str, Any]]:
    url = os.getenv("ODDS_HARVESTER_URL", "").strip()
    if not url:
        return []
    try:
        response = requests.get(
            url,
            params={"date": date, "sport": "football"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return []
    if isinstance(payload, dict):
        for key in ("matches", "fixtures", "events", "data", "results"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def _records(date: str) -> list[dict[str, Any]]:
    if date not in _CACHE:
        rows = _load_local(date)
        if not rows:
            rows = _fetch_remote(date)
        _CACHE[date] = rows
    return _CACHE[date]


def fixture_odds(home: str, away: str, date: str) -> dict[str, float]:
    """Return normalized odds for an exact fixture, or an empty dict."""
    h = _normalize(home)
    a = _normalize(away)
    for record in _records(date):
        rh = _normalize(record.get("home_team") or record.get("home"))
        ra = _normalize(record.get("away_team") or record.get("away"))
        if rh == h and ra == a:
            return _extract_odds(record)
    return {}


def current_fixtures(date: str) -> list[dict[str, Any]]:
    """Return cached/fetched fixtures in the analyzer's normalized shape."""
    rows: list[dict[str, Any]] = []
    for record in _records(date):
        home = record.get("home_team") or record.get("home")
        away = record.get("away_team") or record.get("away")
        if not home or not away:
            continue
        finished = record.get("finished")
        if finished is None:
            score = record.get("score") or record.get("final_score")
            finished = bool(score)
        rows.append(
            {
                "home": str(home),
                "away": str(away),
                "kickoff": record.get("kickoff") or record.get("start_time"),
                "league": record.get("league") or record.get("competition"),
                "finished": bool(finished),
                "source": record.get("source", "oddsharvester"),
            }
        )
    return rows
