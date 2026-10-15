
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
    "User-Agent": "Mozilla/5.0"
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
        raise Exception("Lineup non trovata")

    players = []
    current = heading.find_next()

    while current:
        if current.name in ["h2", "h3"] and current != heading:
            break

        for img in current.find_all("img") if hasattr(current, "find_all") else []:
            alt = img.get("alt", "")

            # Esempio FUT.GG:
            # "Vialli - 89 - Base Hero"
            match = re.match(r"(.+?) - (\d+) - (.+)", alt)

            if match:
                player = {
                    "name": match.group(1).strip(),
                    "rating": match.group(2).strip(),
                    "card": match.group(3).strip()
                }

                if player not in players:
                    players.append(player)

                if len(players) == 5:
                    return players

        current = current.find_next()

    if len(players) != 5:
        raise Exception(
            f"Trovati {len(players)} giocatori invece di 5"
        )

    return players


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": True
        },
        timeout=30
    )

    response.raise_for_status()


def player_text(player):
    return f"{player['name']} ({player['rating']})"


def main():

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            old_state = json.load(f)
    else:
        old_state = {}

    new_state = {}

    for category, url in PAGES.items():

        players = get_players(url)
        new_state[category] = players

        old_players = old_state.get(category)

        # Primo avvio: salva soltanto
        if old_players is None:
            continue

        old_set = {
            (p["name"], p["rating"], p["card"])
            for p in old_players
        }

        new_set = {
            (p["name"], p["rating"], p["card"])
            for p in players
        }

        if old_set != new_set:

            removed = [
                p for p in old_players
                if (p["name"], p["rating"], p["card"])
                not in new_set
            ]

            added = [
                p for p in players
                if (p["name"], p["rating"], p["card"])
                not in old_set
            ]

            message = f"🚨 FUT.GG {category} CAMBIATA!\n\n"

            for p in removed:
                message += f"❌ {player_text(p)}\n"

            for p in added:
                message += f"✅ {player_text(p)}\n"

            message += f"\n🔗 {url}"

            send_telegram(message)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            new_state,
            f,
            ensure_ascii=False,
            indent=2
        )


if __name__ == "__main__":
    main()
