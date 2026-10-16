import requests
import json

API_URL = "https://www.fut.gg/api/fut/players/v2/27/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.fut.gg/players/trending/",
}

PARAMS = {
    "sorts": "-pageviews",
    "count": 20,
}

response = requests.get(
    API_URL,
    headers=HEADERS,
    params=PARAMS,
    timeout=30
)

print("STATUS:", response.status_code)

response.raise_for_status()

data = response.json()

print("RESPONSE TYPE:", type(data).__name__)

if isinstance(data, list):
    print("PLAYERS RETURNED:", len(data))

    if data:
        first = data[0]

        print("\nFIRST PLAYER KEYS:")
        print(list(first.keys()))

        print("\nFIRST PLAYER:")
        print(json.dumps(first, indent=2, ensure_ascii=False))

elif isinstance(data, dict):
    print("\nTOP LEVEL KEYS:")
    print(list(data.keys()))

    # Print a shortened version so the GitHub log stays manageable
    print("\nDATA PREVIEW:")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:8000])
