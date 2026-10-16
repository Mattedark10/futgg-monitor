import json
import os
import time
from datetime import datetime, timezone, timedelta

import requests


PLAYERS_API = "https://www.fut.gg/api/fut/players/v2/27/"
PRICE_API = "https://www.fut.gg/api/fut/player-prices/27"

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


def get_player_price(ea_id):
    """
    Recupera prezzo corrente + storico della singola carta.
    """

    url = f"{PRICE_API}/{ea_id}/"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    return data


def extract_current_price(data):
    """
    Gestisce le possibili strutture della risposta.
    """

    candidates = [
        data.get("price"),
        data.get("currentPrice"),
    ]

    if isinstance(data.get("data"), dict):
        candidates.extend([
            data["data"].get("price"),
            data["data"].get("currentPrice"),
        ])

    for value in candidates:
        if value is None:
            continue

        try:
            value = int(value)

            if value > 0:
                return value

        except (TypeError, ValueError):
            pass

    return None


def extract_api_history(data):
    """
    Estrae la history già disponibile nell'API.
    """

    history = []

    possible_histories = [
        data.get("history"),
    ]

    if isinstance(data.get("data"), dict):
        possible_histories.append(
            data["data"].get("history")
        )

    raw_history = None

    for candidate in possible_histories:
        if isinstance(candidate, list):
            raw_history = candidate
            break

    if not raw_history:
        return history

    for point in raw_history:

        if not isinstance(point, dict):
            continue

        date_value = (
            point.get("date")
            or point.get("timestamp")
            or point.get("datetime")
        )

        price_value = point.get("price")

        if not date_value or price_value is None:
            continue

        try:
            price_value = int(price_value)

            if price_value <= 0:
                continue

        except (TypeError, ValueError):
            continue

        try:
            parsed_date = datetime.fromisoformat(
                str(date_value).replace("Z", "+00:00")
            )

            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(
                    tzinfo=timezone.utc
                )

            timestamp = parsed_date.astimezone(
                timezone.utc
            ).isoformat().replace("+00:00", "Z")

        except Exception:
            continue

        history.append(
            {
                "timestamp": timestamp,
                "price": price_value,
            }
        )

    return history


def add_point(history, ea_id, timestamp, price):
    key = str(ea_id)

    if key not in history:
        history[key] = {
            "points": []
        }

    points = history[key].get("points", [])

    points.append(
        {
            "timestamp": timestamp,
            "price": price,
        }
    )

    # Rimuove duplicati dello stesso timestamp
    unique = {}

    for point in points:
        unique[point["timestamp"]] = point

    history[key]["points"] = list(
        unique.values()
    )


def clean_history(history, now):
    cutoff = now - timedelta(
        hours=HISTORY_HOURS
    )

    cleaned = {}

    for ea_id, data in history.items():

        points = []

        for point in data.get("points", []):

            try:
                timestamp = datetime.fromisoformat(
                    point["timestamp"].replace(
                        "Z",
                        "+00:00"
                    )
                )

                price = int(point["price"])

                if (
                    timestamp >= cutoff
                    and price > 0
                ):
                    points.append(
                        {
                            "timestamp": point["timestamp"],
                            "price": price,
                        }
                    )

            except Exception:
                continue

        points.sort(
            key=lambda x: x["timestamp"]
        )

        if points:
            cleaned[ea_id] = {
                "points": points
            }

    return cleaned


def main():

    os.makedirs(
        DOCS_DIR,
        exist_ok=True
    )

    now = datetime.now(timezone.utc)

    print("Getting trending players...")

    players = get_trending_players()

    print(
        f"Found {len(players)} trending players."
    )

    history = load_json(
        HISTORY_FILE,
        {}
    )

    trending = []

    for index, player in enumerate(
        players,
        start=1
    ):

        ea_id = player.get("eaId")

        print(
            f"[{index}/{len(players)}] "
            f"{player.get('cardName') or player.get('commonName')}"
        )

        current_price = None
        api_history = []

        if ea_id is not None:

            try:

                price_data = get_player_price(
                    ea_id
                )

                current_price = extract_current_price(
                    price_data
                )

                api_history = extract_api_history(
                    price_data
                )

                print(
                    f"  Price: {current_price}"
                )

                print(
                    f"  API history: "
                    f"{len(api_history)} points"
                )

            except Exception as error:

                print(
                    f"  Price error: {error}"
                )

        # Importiamo la history disponibile
        # nell'API come base iniziale.
        if ea_id is not None:

            for point in api_history:

                add_point(
                    history,
                    ea_id,
                    point["timestamp"],
                    point["price"]
                )

            # Aggiungiamo il nostro rilevamento
            # corrente.
            if current_price is not None:

                add_point(
                    history,
                    ea_id,
                    now.isoformat().replace(
                        "+00:00",
                        "Z"
                    ),
                    current_price
                )

        club = (
            player.get("uniqueClub")
            or player.get("club")
            or {}
        )

        league = (
            player.get("league")
            or {}
        )

        player_url = (
            player.get("url")
            or ""
        )

        trending.append(
            {
                "name": (
                    player.get("cardName")
                    or player.get("commonName")
                    or ""
                ),
                "rating": player.get(
                    "overall"
                ),
                "position": (
                    player.get("position")
                    or ""
                ),
                "rarity": (
                    player.get("rarityName")
                    or ""
                ),
                "club": (
                    club.get("name")
                    or ""
                ),
                "league": (
                    league.get("name")
                    or ""
                ),
                "img": (
                    player.get(
                        "cardImageUrl"
                    )
                    or ""
                ),
                "url": (
                    SITE_URL + player_url
                    if player_url.startswith("/")
                    else player_url
                ),
                "eaId": ea_id,
                "slug": (
                    player.get("slug")
                    or ""
                ),
                "price": current_price,
            }
        )

        # Piccola pausa per evitare richieste
        # troppo ravvicinate.
        time.sleep(0.2)

    history = clean_history(
        history,
        now
    )

    save_json(
        TRENDING_FILE,
        trending
    )

    save_json(
        HISTORY_FILE,
        history
    )

    print()
    print(
        f"Saved {len(trending)} trending players."
    )

    print(
        f"Saved history for "
        f"{len(history)} players."
    )

    print()

    for index, player in enumerate(
        trending,
        start=1
    ):

        print(
            f"{index}. "
            f"{player['name']} "
            f"{player['rating']} "
            f"{player['position']} "
            f"price={player['price']}"
        )


if __name__ == "__main__":
    main()
