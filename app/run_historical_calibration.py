"""Run a leakage-safe walk-forward calibration/backtest on public CSV data.

The backtest deliberately trains only on matches dated before each test match.
It evaluates three simple markets: home win, BTTS yes and over 2.5.
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
                data = list(csv.DictReader(io.StringIO(r.content.decode("cp1252", errors="replace"))))
            except requests.RequestException:
                continue
            for row in data:
                try:
                    date = datetime.strptime(row["Date"], "%d/%m/%Y").date()
                except (KeyError, ValueError):
                    continue
                hg, ag = _float(row.get("FTHG")), _float(row.get("FTAG"))
                if hg is None or ag is None:
                    continue
                odds = _float(row.get("B365H"))
                rows.append({
                    "date": date,
                    "home": row.get("HomeTeam", "").strip(),
                    "away": row.get("AwayTeam", "").strip(),
                    "hg": int(hg), "ag": int(ag),
                    "league": name, "odds": odds,
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
    # Same shrinkage family as production stat component, with no future data.
    h_ppg = 3 * _rate(h["points"]) / 3
    a_ppg = 3 * _rate(a["points"]) / 3
    form_edge = max(-1, min(1, (h_ppg - a_ppg) / 3))
    gd_edge = max(-1, min(1, (_rate(h["gd"], 0) - _rate(a["gd"], 0)) / 3))
    home = max(0.05, min(0.95, 0.50 + 0.13 * form_edge + 0.09 * gd_edge + 0.03))
    btts_signal = (_rate(h["btts"]) + _rate(a["btts"])) / 2
    over_signal = (_rate(h["over"]) + _rate(a["over"])) / 2
    btts = max(0.05, min(0.95, 0.35 + 0.40 * btts_signal))
    over = max(0.05, min(0.95, 0.35 + 0.40 * over_signal))
    return home, btts, over


def run():
    history = load_history()
    states = defaultdict(_team_state)
    points = {"home_win": [], "btts_yes": [], "over_2_5": []}

    for row in history:
        h, a = states[row["home"]], states[row["away"]]
        if len(h["points"]) < 3 or len(a["points"]) < 3:
            # Still update state; don't test until both teams have enough history.
            pass
        else:
            home_p, btts_p, over_p = _probabilities(h, a)
            points["home_win"].append(CalibrationPoint(
                home_p, int(row["hg"] > row["ag"]), row["odds"]
            ))
            # No historical BTTS/OU odds are required for probability calibration.
            points["btts_yes"].append(CalibrationPoint(
                btts_p, int(row["hg"] > 0 and row["ag"] > 0)
            ))
            points["over_2_5"].append(CalibrationPoint(
                over_p, int(row["hg"] + row["ag"] >= 3)
            ))

        h["points"].append(3 if row["hg"] > row["ag"] else 1 if row["hg"] == row["ag"] else 0)
        a["points"].append(3 if row["ag"] > row["hg"] else 1 if row["hg"] == row["ag"] else 0)
        h["gd"].append(row["hg"] - row["ag"])
        a["gd"].append(row["ag"] - row["hg"])
        over = int(row["hg"] + row["ag"] >= 3)
        btts = int(row["hg"] > 0 and row["ag"] > 0)
        h["over"].append(over); a["over"].append(over)
        h["btts"].append(btts); a["btts"].append(btts)

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "seasons": list(SEASONS),
        "leagues": list(LEAGUES.values()),
        "leakage_control": "walk-forward: only matches before each test fixture update team state",
        "markets": {market: summarize(rows) for market, rows in points.items()},
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
