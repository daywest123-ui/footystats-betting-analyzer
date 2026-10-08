"""Optional GitHub Actions -> Coda synchronization for MATCH ANALYZER X.

The sync is intentionally opt-in: when CODA_API_TOKEN is not configured,
the command exits successfully without touching Coda.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

CODA_API_ROOT = "https://coda.io/apis/v1"


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _best_market(match: dict[str, Any]) -> dict[str, Any] | None:
    markets = match.get("market_analysis") or []
    eligible = [m for m in markets if m.get("decision") == "ANALYZE"]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda m: (
            _f(m.get("value_edge_pct")) or -999.0,
            _f(m.get("model_probability_pct")) or 0.0,
        ),
    )


def _status(match: dict[str, Any], market: dict[str, Any] | None) -> str:
    if market and market.get("decision") == "ANALYZE":
        return "Uygun"
    if str((match.get("signal") or {}).get("category", "")).upper() == "WATCH":
        return "Takipte"
    return "Pas"


def _row(match: dict[str, Any]) -> dict[str, Any]:
    dc = match.get("dixon_coles") or {}
    market = _best_market(match)

    fair = _f(market.get("fair_odds")) if market else None
    if fair is None:
        prob = _f(market.get("model_probability")) if market else None
        fair = round(1.0 / prob, 2) if prob and prob > 0 else None

    market_odds = _f(market.get("odds")) if market else None
    value_edge = _f(market.get("value_edge_pct")) if market else 0.0
    confidence = _f(market.get("confidence_10")) if market else None

    return {
        "cells": [
            {"column": "c-aTYcZmz8ds", "value": match.get("fixture_date")},
            {"column": "c-77uMdPcN4i", "value": match.get("league")},
            {"column": "c-J_Dufyk-74", "value": match.get("home")},
            {"column": "c-UBL_j-RVP0", "value": match.get("away")},
            {"column": "c-ASfxiE1Vse", "value": round((_f(dc.get("home_win")) or 0.0), 4)},
            {"column": "c-CmJ8h-TvY-", "value": round((_f(dc.get("draw")) or 0.0), 4)},
            {"column": "c-J49MhNae2d", "value": round((_f(dc.get("away_win")) or 0.0), 4)},
            {"column": "c-5TDyHXcDAC", "value": market.get("market") if market else ""},
            {"column": "c-EjkuYlvuOk", "value": fair},
            {"column": "c-KCZ9wdYyHj", "value": market_odds},
            {"column": "c-NS2mCqL-sl", "value": value_edge},
            {"column": "c-kxMPYGoi0M", "value": round(confidence or 0)},
            {"column": "c-fdHqmrsDcb", "value": _status(match, market)},
            {"column": "c-cKccLmSq9J", "value": match.get("fixture_id")},
        ]
    }


def sync() -> int:
    token = os.getenv("CODA_API_TOKEN", "").strip()
    if not token:
        print("CODA_API_TOKEN not configured; Coda sync skipped.")
        return 0

    doc_id = os.getenv("CODA_DOC_ID", "ogctvyxHt8").strip()
    table_id = os.getenv("CODA_MATCH_TABLE_ID", "grid-s-1V_SzZ68").strip()
    report_path = Path(os.getenv("REPORT_PATH", "reports/latest_auto_analysis.json"))

    if not report_path.exists():
        print(f"Report not found: {report_path}", file=sys.stderr)
        return 1

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    matches = payload.get("all_scanned") or []

    rows = [_row(m) for m in matches if m.get("fixture_id")]
    if not rows:
        print("No scanned fixtures to sync.")
        return 0

    url = f"{CODA_API_ROOT}/docs/{doc_id}/tables/{table_id}/rows"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {"rows": rows, "keyColumns": ["c-cKccLmSq9J"]}

    response = requests.post(url, headers=headers, json=body, timeout=45)
    response.raise_for_status()
    data = response.json()

    print(
        f"Coda sync queued: {len(rows)} fixture rows; "
        f"requestId={data.get('requestId', 'unknown')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(sync())
