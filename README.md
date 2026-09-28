# FootyStats Betting Analyzer

FootyStats football match analysis and betting signal system.

## Project goal

Analyze football matches using statistical data and produce transparent signals for:

- Match result (1X2)
- Over/Under goals
- Both Teams To Score (BTTS)
- Team goals
- First-half markets
- Corners/cards when reliable data is available

The system is designed for analysis and paper/backtesting first. It does not place bets automatically.

## Architecture

1. Data ingestion
2. Data normalization
3. Feature engineering
4. Probability model
5. Value calculation
6. Signal scoring
7. Backtesting
8. Reporting / notifications

## Data source

FootyStats will be the primary statistical source. API credentials, if required by the chosen access method, must be stored in environment variables and never committed to Git.

## Signal categories

- BANKO: high model confidence and sufficient supporting data
- VALUE: model probability materially exceeds implied market probability
- SURPRISE: lower-confidence, higher-variance opportunity

No signal is guaranteed to win. Historical backtesting and calibration are required before relying on any model output.


## Open-source intelligence layer

The project now includes an optional **DataFC (Sofascore-backed)** intelligence layer. DataFC exposes structured match histories, pre-game form, H2H, pre-match odds, lineups, shots/xG, incidents and other football data as pandas DataFrames.

The new `app/open_source_intel.py` is deliberately separated from the core FootyStats fusion:

- historical HT/FT frequencies
- first-half draw / scoreless-half rates
- second-half 1+ and 2+ goal rates
- recent home/away HT/FT patterns
- H2H as a secondary, down-weighted signal
- fair-odds calculation from the historical model probability
- **no bookmaker price is invented**

The four-engine runner now writes these special opportunities to `reports/latest_four_engine_coupon.json` under `open_source_special_opportunities`. A high-odds scenario is only a **value candidate if the actual market odds exceed the calculated fair odds**.

This layer is intended to find the unusual markets we care about (especially HT/FT), rather than relabeling ordinary 1X2/BTTS/2.5 markets as opportunities.
