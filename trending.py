import json
import os
import requests

API_URL = "https://www.fut.gg/api/fut/players/v2/27/"
SITE_URL = "https://www.fut.gg"

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
    timeout=30,
)

response.raise_for_status()

data = response.json()
players = data.get("data", [])[:20]

trending = []

for player in players:
    club = player.get("uniqueClub") or player.get("club") or {}
    league = player.get("league") or {}

    player_url = player.get("url") or ""

    trending.append(
        {
            "name": player.get("cardName") or player.get("commonName") or "",
            "rating": player.get("overall"),
            "position": player.get("position") or "",
            "rarity": player.get("rarityName") or "",
            "club": club.get("name") or "",
            "league": league.get("name") or "",
            "img": player.get("cardImageUrl") or "",
            "url": (
                SITE_URL + player_url
                if player_url.startswith("/")
                else player_url
            ),
            "eaId": player.get("eaId"),
            "slug": player.get("slug") or "",
        }
    )

os.makedirs("docs", exist_ok=True)

with open("docs/trending.json", "w", encoding="utf-8") as file:
    json.dump(
        trending,
        file,
        ensure_ascii=False,
        indent=2,
    )

print(f"Saved {len(trending)} trending players.")
print()

for index, player in enumerate(trending, start=1):
    print(
        f"{index}. "
        f"{player['name']} "
        f"{player['rating']} "
        f"{player['position']}"
    )
