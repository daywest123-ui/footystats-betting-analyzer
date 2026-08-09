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
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    data = get_matches()
    print(f"Fetched {len(data.get('matches', []))} matches")
