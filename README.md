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
