"""Independent Dixon-Coles style football probability engine.

Inspired by the public implementations of Dixon-Coles football models. This
module is deliberately self-contained: it needs only historical match results
already supplied by the repository's open-data loader.

It produces a full scoreline matrix, 1X2, BTTS and O/U 2.5 probabilities.
"""
from __future__ import annotations

import math
from typing import Any


def _norm(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def _poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _elo_ratings(matches: list[dict[str, Any]], before: str) -> dict[str, float]:
    ratings: dict[str, float] = {}
    for m in sorted(
        (x for x in matches if x.get("finished") and x.get("date", "") < before),
        key=lambda x: x.get("date", ""),
    ):
        h, a = _norm(m["home"]), _norm(m["away"])
        ratings.setdefault(h, 1500.0)
        ratings.setdefault(a, 1500.0)
        hg, ag = int(m["home_goals"]), int(m["away_goals"])
        expected = 1.0 / (1.0 + 10 ** ((ratings[a] - ratings[h] - 55.0) / 400.0))
        actual = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        margin = max(1.0, min(2.5, 1.0 + abs(hg - ag) * 0.35))
        k = 18.0 * margin
        ratings[h] += k * (actual - expected)
        ratings[a] += k * ((1.0 - actual) - (1.0 - expected))
    return ratings


def predict(
    matches: list[dict[str, Any]],
    home: str,
    away: str,
    before: str,
    max_goals: int = 8,
    rho: float = -0.13,
) -> dict[str, Any]:
    """Return Dixon-Coles-corrected score and market probabilities."""
    hkey, akey = _norm(home), _norm(away)
    prior_h = [m for m in matches if m.get("finished") and m.get("date", "") < before and
               (_norm(m.get("home", "")) == hkey or _norm(m.get("away", "")) == hkey)]
    prior_a = [m for m in matches if m.get("finished") and m.get("date", "") < before and
               (_norm(m.get("home", "")) == akey or _norm(m.get("away", "")) == akey)]

    def team_rates(rows: list[dict[str, Any]], key: str) -> tuple[float, float]:
        if not rows:
            return 1.25, 1.25
        rows = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)[:12]
        weights = [math.exp(-0.045 * i) for i in range(len(rows))]
        sw = sum(weights)
        gf = ga = 0.0
        for w, m in zip(weights, rows):
            hg, ag = float(m["home_goals"]), float(m["away_goals"])
            if _norm(m["home"]) == key:
                gf += w * hg; ga += w * ag
            else:
                gf += w * ag; ga += w * hg
        return gf / sw, ga / sw

    hgf, hga = team_rates(prior_h, hkey)
    agf, aga = team_rates(prior_a, akey)

    # League-average shrinkage makes sparse teams less extreme.
    h_n, a_n = min(len(prior_h), 12), min(len(prior_a), 12)
    h_w, a_w = h_n / 12.0, a_n / 12.0
    hgf = 1.30 * (1 - h_w) + hgf * h_w
    hga = 1.30 * (1 - h_w) + hga * h_w
    agf = 1.20 * (1 - a_w) + agf * a_w
    aga = 1.20 * (1 - a_w) + aga * a_w

    elo = _elo_ratings(matches, before)
    he = elo.get(hkey, 1500.0)
    ae = elo.get(akey, 1500.0)
    elo_edge = max(-250.0, min(250.0, he - ae))
    elo_factor_h = 1.0 + elo_edge / 1800.0
    elo_factor_a = 1.0 - elo_edge / 2200.0

    lam_h = max(0.25, min(3.5, (0.58 * hgf + 0.42 * aga + 0.12) * elo_factor_h))
    lam_a = max(0.20, min(3.2, (0.58 * agf + 0.42 * hga - 0.04) * elo_factor_a))

    matrix: list[list[float]] = []
    for i in range(max_goals + 1):
        row = []
        for j in range(max_goals + 1):
            p = _poisson(i, lam_h) * _poisson(j, lam_a)
            if i == 0 and j == 0:
                tau = 1.0 - lam_h * lam_a * rho
            elif i == 0 and j == 1:
                tau = 1.0 + lam_h * rho
            elif i == 1 and j == 0:
                tau = 1.0 + lam_a * rho
            elif i == 1 and j == 1:
                tau = 1.0 - rho
            else:
                tau = 1.0
            row.append(max(0.0, p * tau))
        matrix.append(row)

    total = sum(sum(r) for r in matrix)
    matrix = [[p / total for p in row] for row in matrix]

    home_win = draw = away_win = btts = over25 = 0.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            home_win += p if i > j else 0.0
            draw += p if i == j else 0.0
            away_win += p if i < j else 0.0
            btts += p if i > 0 and j > 0 else 0.0
            over25 += p if i + j >= 3 else 0.0

    return {
        "home_win": home_win,
        "draw": draw,
        "away_win": away_win,
        "btts_yes": btts,
        "btts_no": 1.0 - btts,
        "over_2_5": over25,
        "under_2_5": 1.0 - over25,
        "lambda_home": lam_h,
        "lambda_away": lam_a,
        "elo_home": he,
        "elo_away": ae,
        "rho": rho,
        "score_matrix": matrix,
    }
