"""OddsQuant-inspired value and market math for the existing analyzer."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class ValueSignal:
    market: str
    selection: str
    odds: float
    model_probability: float
    implied_probability: float
    fair_odds: float
    ev: float
    edge: float
    decision: str

def implied_probability(odds: float) -> float:
    if odds <= 1:
        raise ValueError("Decimal odds must be > 1")
    return 1.0 / odds

def devig_proportional(odds: Iterable[float]) -> list[float]:
    probs = [implied_probability(o) for o in odds]
    total = sum(probs)
    if total <= 0:
        return []
    return [p / total for p in probs]

def value_signal(market: str, selection: str, odds: float,
                 model_probability: float, min_edge: float = 0.025,
                 min_ev: float = 0.03) -> ValueSignal:
    model_probability = max(0.0, min(1.0, model_probability))
    implied = implied_probability(odds)
    fair = 1.0 / model_probability if model_probability else float("inf")
    ev = model_probability * odds - 1.0
    edge = model_probability - implied
    decision = "VALUE" if edge >= min_edge and ev >= min_ev else "WATCH"
    return ValueSignal(market, selection, round(odds, 4),
        round(model_probability, 6), round(implied, 6),
        round(fair, 4) if fair != float("inf") else fair,
        round(ev, 6), round(edge, 6), decision)

def rank_value_signals(signals: Iterable[ValueSignal]) -> list[ValueSignal]:
    return sorted(signals, key=lambda s: (s.ev, s.edge), reverse=True)
