# Three Optional External Football Engines

This integration keeps the existing `footystats-betting-analyzer` pipeline as the source of truth and registers three external projects as optional evidence/model sources. Their code is **not copied into this repository**; each is maintained by its original author and should be checked for license, dependencies, and compatibility before execution.

## Registered projects

1. **ProphitBet Soccer Bets Predictor** — https://github.com/kochlisGit/ProphitBet-Soccer-Bets-Predictor  
   ML-based match predictions and evaluation. Its README describes FootyStats fixture parsing and historical training/evaluation. Python 3.10/3.11 are the tested versions described in its current README; use a separate virtual environment.

2. **FootyStats-Tools** — https://github.com/laubfall/footystats-tools  
   Soccer predictions from FootyStats CSV files. Treat CSV export/import as its initial integration boundary.

3. **Footstats Football Analysis App** — https://github.com/alokpurohit18/footstats  
   React/Flask football analysis app. Its output and prediction semantics must be inspected before using any values in model fusion.

## Local setup

Clone each project into a separate folder (do not place its dependencies into the main project's Python environment). Example paths:

- `vendor/external_engines/ProphitBet-Soccer-Bets-Predictor`
- `vendor/external_engines/footystats-tools`
- `vendor/external_engines/footstats`

Set environment variables to the actual local paths:

- `PROPHITBET_PATH`
- `FOOTYSTATS_TOOLS_PATH`
- `FOOTSTATS_APP_PATH`

Then inspect registration status:

```powershell
py -m app.external_engine_registry
```

The registry reports whether each path is configured and exists. It does **not** claim the external app has been installed, run, or validated.

## Required integration contract

Before any source can affect a prediction, its adapter must emit a normalized record with:

- `source`, `match_id` (or unambiguous home/away + kickoff identity)
- `market`, `selection`
- `probability` in [0, 1], only when explicitly supplied or calculated by a documented model
- `odds` only when sourced from a real timestamped price
- `observed_at`, `data_quality`, `raw_reference`

For HT/FT, the only accepted selection values are `1/1`, `1/X`, `1/2`, `X/1`, `X/X`, `X/2`, `2/1`, `2/X`, and `2/2`. If an external project does not produce HT/FT probabilities, it must not be converted into HT/FT advice by guesswork.

## Safety and validation gates

- A failed or unavailable source is neutral; it must not count as a vote for another outcome.
- Do not average probabilities until match identity, market, timestamp, and probability semantics match.
- Do not invent missing probabilities, odds, match results, or source confidence.
- Evaluate each source separately with time-ordered holdout data before allowing it to influence the ensemble.
- Record hit rate, multiclass Brier score/log loss, calibration, coverage, and (only with real odds) ROI.
- Preserve the current analyzer and coupon rules. No automatic betting or bet placement is introduced.
- Check each upstream project's license and security before running its code. Keep its dependencies isolated.

## Current integration stage

This commit adds a registry and integration contract only. It does not yet execute these external projects or claim that their predictions have been merged into the live model. The next stage is to implement and test a dedicated adapter for each project's actual input/output format.
