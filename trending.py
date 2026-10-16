import json
import os
from datetime import datetime, timezone, timedelta

import requests


# =========================
# FUT.GG PLAYER DATA
# =========================

PLAYERS_API = "https://www.fut.gg/api/fut/players/v2/27/"

# =========================
# PUBLIC FC27 MARKET API
# =========================

MARKET_API = "https://fc27-market.val.run/latest"

SITE_URL = "https://www.fut.gg"

# =========================
# FILES
# =========================

DOCS_DIR = "docs"

TRENDING_FILE = os.path.join(
    DOCS_DIR,
    "trending.json"
)

HISTORY_FILE = os.path.join(
    DOCS_DIR,
    "price_history.json"
)

# Keep 72 hours
HISTORY_HOURS = 72


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.fut.gg/",
}


# =========================
# JSON HELPERS
# =========================

def load_json(path, default):

    if not os.path.exists(path):
        return default

    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception:

        return default


def save_json(path, data):

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


# =========================
# TRENDING
# =========================

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

    return data.get(
        "data",
        []
    )[:20]


# =========================
# MARKET
# =========================

def get_market_prices():

    print("Getting public FC27 market feed...")

    response = requests.get(
        MARKET_API,
        headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "application/json",
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    prices = {}

    groups = data.get(
        "groups",
        {}
    )

    for group_players in groups.values():

        if not isinstance(
            group_players,
            list
        ):
            continue

        for player in group_players:

            ea_id = player.get(
                "eaId"
            )

            price = player.get(
                "price"
            )

            if ea_id is None:
                continue

            if price is None:
                continue

            try:

                price = int(price)

            except (
                TypeError,
                ValueError
            ):

                continue

            if price <= 0:
                continue

            prices[str(ea_id)] = price

    print(
        f"Received prices for "
        f"{len(prices)} players."
    )

    return prices


# =========================
# HISTORY
# =========================

def add_history_point(
    history,
    ea_id,
    timestamp,
    price
):

    key = str(ea_id)

    if key not in history:

        history[key] = {
            "points": []
        }

    points = history[key].get(
        "points",
        []
    )

    points.append(
        {
            "timestamp": timestamp,
            "price": price
        }
    )


def clean_history(
    history,
    now
):

    cutoff = (
        now
        - timedelta(
            hours=HISTORY_HOURS
        )
    )

    cleaned = {}

    for ea_id, player_data in history.items():

        points = []

        for point in player_data.get(
            "points",
            []
        ):

            try:

                timestamp = datetime.fromisoformat(
                    point["timestamp"].replace(
                        "Z",
                        "+00:00"
                    )
                )

                price = int(
                    point["price"]
                )

            except Exception:

                continue

            if timestamp < cutoff:
                continue

            if price <= 0:
                continue

            points.append(
                {
                    "timestamp": point["timestamp"],
                    "price": price
                }
            )

        # Sort chronologically
        points.sort(
            key=lambda x: x["timestamp"]
        )

        # Remove duplicate timestamps
        unique = {}

        for point in points:

            unique[
                point["timestamp"]
            ] = point

        points = list(
            unique.values()
        )

        if points:

            cleaned[ea_id] = {
                "points": points
            }

    return cleaned


# =========================
# MAIN
# =========================

def main():

    os.makedirs(
        DOCS_DIR,
        exist_ok=True
    )

    now = datetime.now(
        timezone.utc
    )

    timestamp = (
        now.isoformat()
        .replace(
            "+00:00",
            "Z"
        )
    )

    print()
    print(
        "Getting trending players..."
    )

    players = get_trending_players()

    print(
        f"Found {len(players)} "
        f"trending players."
    )

    print()

    # =========================
    # GET PRICES
    # =========================

    prices = get_market_prices()

    # =========================
    # LOAD OLD HISTORY
    # =========================

    history = load_json(
        HISTORY_FILE,
        {}
    )

    trending = []

    # =========================
    # BUILD TRENDING
    # =========================

    for index, player in enumerate(
        players,
        start=1
    ):

        ea_id = player.get(
            "eaId"
        )

        name = (
            player.get("cardName")
            or player.get("commonName")
            or ""
        )

        price = None

        if ea_id is not None:

            price = prices.get(
                str(ea_id)
            )

        print(
            f"[{index}/{len(players)}] "
            f"{name}"
        )

        print(
            f"  EA ID: {ea_id}"
        )

        print(
            f"  Price: {price}"
        )

        # =========================
        # SAVE CURRENT PRICE
        # =========================

        if (
            ea_id is not None
            and price is not None
        ):

            add_history_point(
                history,
                ea_id,
                timestamp,
                price
            )

        # =========================
        # PLAYER DATA
        # =========================

        club = (
            player.get(
                "uniqueClub"
            )
            or player.get(
                "club"
            )
            or {}
        )

        league = (
            player.get(
                "league"
            )
            or {}
        )

        player_url = (
            player.get("url")
            or ""
        )

        trending.append(
            {
                "name": name,

                "rating": player.get(
                    "overall"
                ),

                "position": (
                    player.get(
                        "position"
                    )
                    or ""
                ),

                "rarity": (
                    player.get(
                        "rarityName"
                    )
                    or ""
                ),

                "club": (
                    club.get(
                        "name"
                    )
                    or ""
                ),

                "league": (
                    league.get(
                        "name"
                    )
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
                    player.get(
                        "slug"
                    )
                    or ""
                ),

                "price": price,
            }
        )

    # =========================
    # CLEAN HISTORY
    # =========================

    history = clean_history(
        history,
        now
    )

    # =========================
    # SAVE FILES
    # =========================

    save_json(
        TRENDING_FILE,
        trending
    )

    save_json(
        HISTORY_FILE,
        history
    )

    # =========================
    # SUMMARY
    # =========================

    print()
    print(
        "================================"
    )

    print(
        f"Saved {len(trending)} "
        f"trending players."
    )

    print(
        f"Saved history for "
        f"{len(history)} players."
    )

    print(
        "================================"
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
