"""Registry and availability checks for optional external football engines.

The engines remain isolated projects. This module does not import their dependencies,
run their web scrapers, or treat missing output as a negative prediction.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ExternalEngine:
    key: str
    display_name: str
    repository: str
    env_var: str
    expected_outputs: tuple[str, ...]
    integration_mode: str
    notes: str


ENGINES: tuple[ExternalEngine, ...] = (
    ExternalEngine(
        key="prophitbet",
        display_name="ProphitBet Soccer Bets Predictor",
        repository="https://github.com/kochlisGit/ProphitBet-Soccer-Bets-Predictor",
        env_var="PROPHITBET_PATH",
        expected_outputs=("match_result_probabilities", "evaluation_metrics"),
        integration_mode="isolated_cli_or_export",
        notes="ML predictions; supports FootyStats fixture parsing and historical evaluation.",
    ),
    ExternalEngine(
        key="footystats_tools",
        display_name="FootyStats-Tools",
        repository="https://github.com/laubfall/footystats-tools",
        env_var="FOOTYSTATS_TOOLS_PATH",
        expected_outputs=("match_predictions",),
        integration_mode="csv_import",
        notes="Predictions from FootyStats CSV files; keep its environment isolated.",
    ),
    ExternalEngine(
        key="footstats_app",
        display_name="Footstats Football Analysis App",
        repository="https://github.com/alokpurohit18/footstats",
        env_var="FOOTSTATS_APP_PATH",
        expected_outputs=("team_player_analysis", "model_predictions_if_available"),
        integration_mode="isolated_cli_or_export",
        notes="React/Flask analysis app; prediction contract must be verified before fusion.",
    ),
)


def get_engine(key: str) -> ExternalEngine:
    """Return an engine by key or raise KeyError for unknown keys."""
    for engine in ENGINES:
        if engine.key == key:
            return engine
    raise KeyError(f"Unknown external engine: {key}")


def engine_path(engine: ExternalEngine) -> Path | None:
    """Resolve the optional local checkout configured through its environment variable."""
    raw = os.getenv(engine.env_var, "").strip()
    return Path(raw).expanduser().resolve() if raw else None


def engine_status(engine: ExternalEngine) -> dict[str, object]:
    """Report configuration only; never claims an engine is installed or working without checks."""
    path = engine_path(engine)
    return {
        "key": engine.key,
        "name": engine.display_name,
        "repository": engine.repository,
        "configured": path is not None,
        "path": str(path) if path else None,
        "path_exists": path.is_dir() if path else False,
        "integration_mode": engine.integration_mode,
        "status": (
            "configured_path_exists" if path and path.is_dir()
            else "configured_path_missing" if path
            else "not_configured"
        ),
    }


def registry_status(engines: Iterable[ExternalEngine] = ENGINES) -> list[dict[str, object]]:
    """Return machine-readable status for all registered external engines."""
    return [engine_status(engine) for engine in engines]


if __name__ == "__main__":
    import json
    print(json.dumps(registry_status(), ensure_ascii=False, indent=2))
