import os
from typing import Any

import requests

BASE_URL = "https://api.football-data.org/v4"


def _headers() -> dict[str, str]:
    token = os.environ.get("FOOTBALL_DATA_API_KEY")
    if not token:
        raise RuntimeError("FOOTBALL_DATA_API_KEY is not configured")
    return {"X-Auth-Token": token}


def get_matches(status: str = "SCHEDULED", limit: int = 20) -> dict[str, Any]:
    response = requests.get(
        f"{BASE_URL}/matches",
        headers=_headers(),
        params={"status": status, "limit": limit},
        timeout=20,
    )
    if not response.ok:
        # Never print the API token. The response body normally contains
        # the provider's useful error message (for example 401/403/quota).
        raise RuntimeError(
            f"Football Data API error: HTTP {response.status_code}: {response.text[:500]}"
        )
    return response.json()


if __name__ == "__main__":
    data = get_matches()
    matches = data.get("matches", [])
    print(f"API connection successful. Fetched {len(matches)} matches")
    for match in matches[:5]:
        home = match.get("homeTeam", {}).get("name", "?")
        away = match.get("awayTeam", {}).get("name", "?")
        print(f"- {home} vs {away}")
