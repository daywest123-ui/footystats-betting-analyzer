"""Leakage-safe calibration and value-backtest utilities.

These functions are intentionally model-agnostic. They compare predicted
probabilities with realized binary outcomes and, when odds are available,
evaluate the exact value thresholds used by the production signal gate.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CalibrationPoint:
    predicted: float
    actual: int
    odds: float | None = None
    market_probability: float | None = None


def _rows(points: Iterable[CalibrationPoint]) -> list[CalibrationPoint]:
    return list(points)


def brier_score(points: Iterable[CalibrationPoint]) -> float:
    rows = _rows(points)
    if not rows:
        return float("nan")
    return sum((p.predicted - p.actual) ** 2 for p in rows) / len(rows)


def log_loss(points: Iterable[CalibrationPoint], eps: float = 1e-6) -> float:
    rows = _rows(points)
    if not rows:
        return float("nan")
    total = 0.0
    for p in rows:
        q = max(eps, min(1.0 - eps, p.predicted))
        total += -(p.actual * math.log(q) + (1 - p.actual) * math.log(1 - q))
    return total / len(rows)


def calibration_table(points: Iterable[CalibrationPoint], buckets: int = 10) -> list[dict]:
    if buckets < 2:
        raise ValueError("buckets must be >= 2")
    groups = defaultdict(list)
    for p in points:
        idx = min(buckets - 1, int(max(0.0, min(0.999999, p.predicted)) * buckets))
        groups[idx].append(p)

    out = []
    for idx in range(buckets):
        rows = groups.get(idx, [])
        if not rows:
            continue
        predicted = sum(x.predicted for x in rows) / len(rows)
        observed = sum(x.actual for x in rows) / len(rows)
        out.append({
            "bucket": f"{idx / buckets:.0%}-{(idx + 1) / buckets:.0%}",
            "count": len(rows),
            "mean_predicted": round(predicted, 4),
            "observed_rate": round(observed, 4),
            "absolute_gap": round(abs(predicted - observed), 4),
        })
    return out


def expected_calibration_error(points: Iterable[CalibrationPoint]) -> float:
    """Sample-weighted absolute calibration gap across occupied buckets."""
    rows = _rows(points)
    if not rows:
        return float("nan")
    table = calibration_table(rows)
    return sum(row["count"] * row["absolute_gap"] for row in table) / len(rows)


def value_backtest(
    points: Iterable[CalibrationPoint],
    min_probability_edge: float = 0.025,
    min_ev: float = 0.03,
) -> dict:
    rows = [p for p in points if p.odds and p.odds > 1]
    selected = []
    for p in rows:
        market_p = p.market_probability if p.market_probability is not None else (1.0 / p.odds)
        if not 0.0 < market_p < 1.0:
            continue
        if p.predicted - market_p >= min_probability_edge and p.predicted * p.odds - 1.0 >= min_ev:
            selected.append(p)
    if not selected:
        return {
            "opportunities": 0,
            "hit_rate": None,
            "roi": None,
            "profit_units": 0.0,
            "max_drawdown_units": 0.0,
            "thresholds": {
                "probability_edge": min_probability_edge,
                "ev": min_ev,
            },
        }

    balance = peak = drawdown = 0.0
    hits = 0
    for p in selected:
        profit = p.odds - 1.0 if p.actual else -1.0
        balance += profit
        peak = max(peak, balance)
        drawdown = max(drawdown, peak - balance)
        hits += int(p.actual)

    return {
        "opportunities": len(selected),
        "hit_rate": round(hits / len(selected), 4),
        "roi": round(balance / len(selected), 4),
        "profit_units": round(balance, 4),
        "max_drawdown_units": round(drawdown, 4),
        "thresholds": {
            "probability_edge": min_probability_edge,
            "ev": min_ev,
        },
    }


def summarize(points: Iterable[CalibrationPoint]) -> dict:
    rows = _rows(points)
    return {
        "samples": len(rows),
        "brier_score": None if not rows else round(brier_score(rows), 6),
        "log_loss": None if not rows else round(log_loss(rows), 6),
        "expected_calibration_error": (
            None if not rows else round(expected_calibration_error(rows), 6)
        ),
        "calibration": calibration_table(rows),
        "value_backtest": value_backtest(rows),
    }


def write_report(summary: dict, path: str = "reports/calibration_backtest.json") -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    print("Import this module and provide historical pre-match probability/odds observations.")
