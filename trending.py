import json
import os
from datetime import datetime, timezone, timedelta

import requests


PLAYERS_API = "https://www.fut.gg/api/fut/players/v2/27/"
PRICES_API = "https://www.fut.gg/api/fut/player-prices/27/"

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

DOCS_DIR = "docs"
TRENDING_FILE = os.path.join(DOCS_DIR, "trending.json")
HISTORY_FILE = os.path.join(DOCS_DIR, "price_history.json")

HISTORY_HOURS = 72


def load_json(path, default):
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def get_trending_players():
    response = requests.get(
        PLAYERS_API,
        headers=HEADERS,
        params={
            "sorts": "-pageviews",
            "count": 20,
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()
    return data.get("data", [])[:20]


def get_prices(ea_ids):
    """
    Recupera i prezzi correnti dei giocatori.
    L'endpoint restituisce:
        data -> [
            {
                "eaId": ...,
                "price": ...
            }
        ]
    """

    if not ea_ids:
        return {}

    ids = ",".join(str(ea_id) for ea_id in ea_ids)

    response = requests.get(
        PRICES_API,
        headers=HEADERS,
        params={
            "ids": ids,
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    prices = {}

    for item in data.get("data", []):
        ea_id = item.get("eaId")
        price = item.get("price")

        if ea_id is None:
            continue

        try:
            if price is not None:
                price = int(price)
        except (TypeError, ValueError):
            price = None

        prices[str(ea_id)] = price

    return prices


def update_history(history, players, now):
    cutoff = now - timedelta(hours=HISTORY_HOURS)

    for player in players:
        ea_id = player.get("eaId")
        price = player.get("price")

        if ea_id is None:
            continue

        key = str(ea_id)

        if key not in history:
            history[key] = {
                "points": []
            }

        points = history[key].get("points", [])

        # Manteniamo solamente dati validi
        cleaned_points = []

        for point in points:
            try:
                timestamp = datetime.fromisoformat(
                    point["timestamp"].replace("Z", "+00:00")
                )

                if timestamp >= cutoff and point.get("price") is not None:
                    cleaned_points.append(
                        {
                            "timestamp": point["timestamp"],
                            "price": point["price"],
                        }
                    )
            except Exception:
                continue

        # Aggiungiamo il nuovo punto solamente se abbiamo un prezzo valido
        if price is not None and price >= 0:
            cleaned_points.append(
                {
                    "timestamp": now.isoformat().replace("+00:00", "Z"),
                    "price": price,
                }
            )

        # Evita duplicati praticamente identici
        unique_points = {}

        for point in cleaned_points:
            unique_points[point["timestamp"]] = point

        history[key]["points"] = list(unique_points.values())[-1000:]

    return history


def main():
    os.makedirs(DOCS_DIR, exist_ok=True)

    print("Getting trending players...")

    players = get_trending_players()

    print(f"Found {len(players)} trending players.")

    ea_ids = [
        player.get("eaId")
        for player in players
        if player.get("eaId") is not None
    ]

    print("Getting prices...")

    prices = get_prices(ea_ids)

    print(f"Received {len(prices)} prices.")

    trending = []

    for player in players:
        club = player.get("uniqueClub") or player.get("club") or {}
        league = player.get("league") or {}

        ea_id = player.get("eaId")

        price = prices.get(str(ea_id))

        player_url = player.get("url") or ""

        trending.append(
            {
                "name": (
                    player.get("cardName")
                    or player.get("commonName")
                    or ""
                ),
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
                "eaId": ea_id,
                "slug": player.get("slug") or "",
                "price": price,
            }
        )

    now = datetime.now(timezone.utc)

    history = load_json(HISTORY_FILE, {})

    history = update_history(
        history,
        trending,
        now,
    )

    save_json(
        TRENDING_FILE,
        trending,
    )

    save_json(
        HISTORY_FILE,
        history,
    )

    print()
    print(f"Saved {len(trending)} trending players.")
    print(f"Saved price history for {len(history)} players.")
    print()

    for index, player in enumerate(trending, start=1):
        print(
            f"{index}. "
            f"{player['name']} "
            f"{player['rating']} "
            f"{player['position']} "
            f"price={player['price']}"
        )


if __name__ == "__main__":
    main()
