# Open-source betting-analysis integrations

Reviewed on 2026-09-24.

Included:
- OddsQuant concepts: value edge, implied probability, fair odds and EV are implemented natively in app/value_engine.py.
- OddsHarvester: optional MIT package for upcoming and historical odds collection.
- FootStats Python package: optional MIT package. FootyStats account/access requirements are separate from the package license.
- Bet-helper: treated as a reference/integration source rather than copied code; its FootyStats scraping approach can connect to the existing local connector.

Important:
Free/open-source refers to the software license. It does not mean every upstream data source, bookmaker feed, proxy, website account, or API is free or unrestricted. Respect source terms and rate limits.

The core analyzer remains usable without these optional components.
