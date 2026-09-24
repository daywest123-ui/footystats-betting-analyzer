"""Run a leakage-safe walk-forward calibration/backtest on public CSV data.

Only matches dated before each test fixture are allowed to influence the
team state. The report evaluates the statistical baseline and a
production-like stat+prediction probability variant.
"""
from __future__ import annotations

import csv
import io
import json
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from statistics import mean

import requests

from app.calibration_backtest import CalibrationPoint, summarize

UA = "Mozilla/5.0 (compatible; FootballAnalyzerCalibration/1.0)"
TIMEOUT = 20
SEASONS = ("2526", "2425", "2324")
LEAGUES = {
    "E0": "England Premier League",
    "D1": "Germany Bundesliga",
    "SP1": "Spain La Liga",
    "I1": "Italy Serie A",
    "F1": "France Ligue 1",
    "T1": "Turkey Super Lig",
}
BASE = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"


def _float(v):
    try:
        return float(v) if v not in ("", None) else None
    except (TypeError, ValueError):
        return None


def _parse_date(value: str):
    value = (value or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def load_history():
    rows = []
    for season in SEASONS:
        for league, name in LEAGUES.items():
            try:
                r = requests.get(
                    BASE.format(season=season, league=league),
                    headers={"User-Agent": UA},
                    timeout=TIMEOUT,
                )
                r.raise_for_status()
                data = list(csv.DictReader(
                    io.StringIO(r.content.decode("cp1252", errors="replace"))
                ))
            except requests.RequestException:
                continue

            for row in data:
                date = _parse_date(row.get("Date", ""))
                hg, ag = _float(row.get("FTHG")), _float(row.get("FTAG"))
                home, away = row.get("HomeTeam", "").strip(), row.get("AwayTeam", "").strip()
                if date is None or hg is None or ag is None or not home or not away:
                    continue
                rows.append({
                    "date": date,
                    "home": home,
                    "away": away,
                    "hg": int(hg),
                    "ag": int(ag),
                    "league": name,
                    "odds": _float(row.get("B365H")),
                })
    return sorted(rows, key=lambda x: (x["date"], x["league"], x["home"], x["away"]))


def _team_state():
    return {
        "points": deque(maxlen=8),
        "gd": deque(maxlen=8),
        "over": deque(maxlen=8),
        "btts": deque(maxlen=8),
    }


def _rate(values, default=0.5):
    return mean(values) if values else default


def _probabilities(h, a):
    h_ppg = _rate(h["points"])
    a_ppg = _rate(a["points"])
    form_edge = max(-1, min(1, (h_ppg - a_ppg) / 3))
    gd_edge = max(-1, min(1, (_rate(h["gd"], 0) - _rate(a["gd"], 0)) / 3))

    stat_home = max(0.05, min(0.95, 0.50 + 0.13 * form_edge + 0.09 * gd_edge + 0.03))
    pred_home = max(0.05, min(0.95, 0.50 + 0.10 * form_edge + 0.05 * gd_edge + 0.02))

    btts_signal = (_rate(h["btts"]) + _rate(a["btts"])) / 2
    over_signal = (_rate(h["over"]) + _rate(a["over"])) / 2
    stat_btts = max(0.05, min(0.95, 0.35 + 0.40 * btts_signal))
    pred_btts = max(0.05, min(0.95, 0.40 + 0.32 * btts_signal))
    stat_over = max(0.05, min(0.95, 0.35 + 0.40 * over_signal))
    pred_over = max(0.05, min(0.95, 0.40 + 0.32 * over_signal))

    # Same weights as the production consensus when current market probability
    # is unavailable; intelligence is neutral at 0.50 rather than invented.
    home_prod = stat_home * 0.45 + pred_home * 0.35 + 0.50 * 0.20
    btts_prod = stat_btts * 0.45 + pred_btts * 0.35 + 0.50 * 0.20
    over_prod = stat_over * 0.45 + pred_over * 0.35 + 0.50 * 0.20

    return {
        "home_win": (stat_home, home_prod),
        "btts_yes": (stat_btts, btts_prod),
        "over_2_5": (stat_over, over_prod),
    }


def run():
    history = load_history()
    states = defaultdict(_team_state)
    points = {
        "home_win": {"statistical_baseline": [], "production_like": []},
        "btts_yes": {"statistical_baseline": [], "production_like": []},
        "over_2_5": {"statistical_baseline": [], "production_like": []},
    }
    tested = 0

    for row in history:
        h, a = states[row["home"]], states[row["away"]]
        if len(h["points"]) >= 3 and len(a["points"]) >= 3:
            probs = _probabilities(h, a)
            actuals = {
                "home_win": int(row["hg"] > row["ag"]),
                "btts_yes": int(row["hg"] > 0 and row["ag"] > 0),
                "over_2_5": int(row["hg"] + row["ag"] >= 3),
            }
            for market, actual in actuals.items():
                stat_p, prod_p = probs[market]
                odds = row["odds"] if market == "home_win" else None
                points[market]["statistical_baseline"].append(
                    CalibrationPoint(stat_p, actual, odds)
                )
                points[market]["production_like"].append(
                    CalibrationPoint(prod_p, actual, odds)
                )
            tested += 1

        # State is updated only after the test prediction above.
        h["points"].append(3 if row["hg"] > row["ag"] else 1 if row["hg"] == row["ag"] else 0)
        a["points"].append(3 if row["ag"] > row["hg"] else 1 if row["hg"] == row["ag"] else 0)
        h["gd"].append(row["hg"] - row["ag"])
        a["gd"].append(row["ag"] - row["hg"])
        over = int(row["hg"] + row["ag"] >= 3)
        btts = int(row["hg"] > 0 and row["ag"] > 0)
        h["over"].append(over)
        a["over"].append(over)
        h["btts"].append(btts)
        a["btts"].append(btts)

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "seasons": list(SEASONS),
        "leagues": list(LEAGUES.values()),
        "tested_fixtures": tested,
        "leakage_control": (
            "walk-forward: prediction is generated before the current match "
            "is added to either team's state"
        ),
        "markets": {
            market: {
                variant: summarize(rows)
                for variant, rows in variants.items()
            }
            for market, variants in points.items()
        },
    }
    out = Path("reports")
    out.mkdir(exist_ok=True)
    (out / "historical_calibration_backtest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    run()
