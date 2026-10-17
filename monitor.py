import os
import re
import json
import requests
from bs4 import BeautifulSoup

PAGES = {
    "🦸 HEROES": "https://www.fut.gg/fut-gallery/rarities/heroes/",
    "🌈 HOLOGRAPHICS": "https://www.fut.gg/fut-gallery/rarities/holographics/",
}

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "players.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
}


def get_players(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    heading = soup.find(
        lambda tag: tag.name in ["h2", "h3"]
        and "Cheapest grade" in tag.get_text()
        and "lineup" in tag.get_text()
    )

    if not heading:
        raise Exception("Lineup not found")

    players = []
    current = heading.find_next()

    while current:

        if current.name in ["h2", "h3"] and current != heading:
            break

        if hasattr(current, "find_all"):
            for img in current.find_all("img"):

                alt = img.get("alt", "").strip()

                match = re.match(
                    r"(.+?)\s*-\s*(\d+)\s*-\s*(.+)",
                    alt
                )

                if match:
                    player = {
                        "name": match.group(1).strip(),
                        "rating": match.group(2).strip(),
                        "card": match.group(3).strip()
                    }

                    # Duplicates are allowed in the feed
                    players.append(player)

                    if len(players) == 5:
                        return players

        current = current.find_next()

    raise Exception(
        f"Found {len(players)} players instead of 5"
    )


def send_telegram(message):
    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=30
    )

    response.raise_for_status()


def player_text(player):
    return (
        f"<b>{player['name']}</b> — "
        f"{player['rating']} — "
        f"{player['card']}"
    )


def main():

    if os.path.exists(STATE_FILE):
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            old_state = json.load(f)
    else:
        old_state = {}

    new_state = {}

    for category, url in PAGES.items():

        print(f"Checking {category}...")

        players = get_players(url)

        new_state[category] = players

        old_players = old_state.get(category)

        # First scan: save current feed only
        if old_players is None:
            print(f"Saving initial {category} feed.")
            continue

        # Compare the full feed
        if old_players != players:

            removed = old_players.copy()
            added = players.copy()

            # Keep only actual changes
            for player in old_players:
                if player in added:
                    added.remove(player)
                    removed.remove(player)

            message = (
                "🚨 <b>FUT.GG FEED UPDATE</b>\n\n"
                f"{category} <b>FEED</b>\n"
                "The best team has been updated.\n\n"
                "🔄 <b>FEED CHANGES</b>\n"
            )

            for player in removed:
                message += (
                    f"🔴 <b>OUT</b> · "
                    f"{player_text(player)}\n"
                )

            for player in added:
                message += (
                    f"🟢 <b>IN</b> · "
                    f"{player_text(player)}\n"
                )

            message += (
                "\n🕐 Change detected automatically\n"
                f'🔗 <a href="{url}">'
                "View Feed on FUT.GG</a>"
            )

            send_telegram(message)

            print("Telegram notification sent.")

        else:
            print("No feed changes.")

    # Save current feed
    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            new_state,
            f,
            ensure_ascii=False,
            indent=2
        )


if __name__ == "__main__":
    main()
