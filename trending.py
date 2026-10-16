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

print("REQUEST URL:", response.url)
print("STATUS:", response.status_code)
print("CONTENT TYPE:", response.headers.get("content-type"))
print()

print("RESPONSE:")
print("=========")

try:
    data = response.json()

    print("JSON TYPE:", type(data).__name__)

    if isinstance(data, list):
        print("PLAYERS RETURNED:", len(data))
        print()
        print(json.dumps(data[:3], indent=2, ensure_ascii=False))

    elif isinstance(data, dict):
        print("TOP-LEVEL KEYS:", list(data.keys()))
        print()
        print(json.dumps(data, indent=2, ensure_ascii=False)[:15000])

    else:
        print(data)

except Exception:
    print("Response is not JSON.")
    print(response.text[:5000])
