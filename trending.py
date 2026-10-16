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
    timeout=30
)

response.raise_for_status()

data = response.json()
players = data.get("data", [])[:20]

trending = []

for player in players:
    club = player.get("uniqueClub") or player.get("club") or {}
    league = player.get("league") or {}

    player_url = player.get("url") or ""

    trending.append({
        "name": player.get("cardName") or player.get("commonName") or "",
        "rating": player.get("overall"),
        "position": player.get("position") or "",
        "rarity": player.get("rarityName") or "",
        "club": club.get
