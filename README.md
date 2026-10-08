# FootyStats Betting Analyzer

FootyStats football match analysis and betting signal system.

## Project goal

Analyze football matches using statistical data and produce transparent signals for:

- Match result (1X2)
- Over/Under goals
- Both Teams To Score (BTTS)
- Team goals
- First-half markets
- HT/FT 9-outcome matrix
- Corners/cards when reliable data is available

The system is designed for analysis and paper/backtesting first. It does not place bets automatically.

## Architecture

1. Data ingestion
2. Data normalization
3. Feature engineering
4. Multi-engine probability model
5. HT/FT venue-aware model
6. Value calculation
7. Risk / NO BET gating
8. Backtesting and calibration
9. Persistent learning
10. Reporting / notifications
11. Optional Coda synchronization

## Data source

FootyStats will be the primary statistical source. The keyless open-data layer uses public football datasets and DataFC/Sofascore where available. API credentials, if required by the chosen access method, must be stored in environment variables and never committed to Git.

## Signal categories

- BANKO: high model confidence and sufficient supporting data
- VALUE: model probability materially exceeds implied market probability
- SURPRISE: lower-confidence, higher-variance opportunity
- NO BET: insufficient data, excessive risk, missing market price, or weak evidence

No signal is guaranteed to win. Historical backtesting and calibration are required before relying on any model output.

## Open-source intelligence layer

The project includes an optional DataFC (Sofascore-backed) intelligence layer for:

- historical HT/FT frequencies
- first-half draw / scoreless-half rates
- second-half 1+ and 2+ goal rates
- recent home/away HT/FT patterns
- H2H as a secondary, down-weighted signal
- fair-odds calculation from model probability
- no bookmaker price is invented

The venue-aware HT/FT engine evaluates exactly nine outcomes:

1/1, 1/X, 1/2, X/1, X/X, X/2, 2/1, 2/X, 2/2

Home-team home history and away-team away history are the primary evidence; H2H is secondary and capped at 10%.

## Coda dashboard

A matching Coda workspace is maintained as the analysis control center:

- Match table
- Market table
- HT/FT matrix
- Model weights
- Learning / backtest log
- Data-source register
- Top Confidence and Value candidate views

Optional GitHub Actions to Coda synchronization is available through app/coda_sync.py.

To enable it, create a Coda API token and add it to the repository as CODA_API_TOKEN.

The workflow uses the existing Coda document and match-table IDs configured in .github/workflows/daily-football-scan.yml.

## Mobile design

A Figma mobile dashboard was created for the MATCH ANALYZER X interface, including:

- overview dashboard
- match detail
- 1X2 probability cards
- HT/FT 9-outcome matrix
- fair/value gate
- mobile-first layout

## Automation

The GitHub Actions scanner runs on a six-hour schedule, can be started manually, installs dependencies, runs unit tests, executes the automatic fixture scan, runs the downstream analysis stages, publishes a summary, saves the report artifact, and can optionally sync scanned fixtures into Coda.

## Testing

Changes to the HT/FT engine include regression tests in app/test_htft_matrix.py.

The CI pipeline must pass unit tests before downstream analysis stages are trusted.