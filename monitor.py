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
        raise Exception("Lineup non trovata")

    players = []
    current = heading.find_next()

    while current:

        # Se arriva alla sezione successiva, fermati
        if current.name in ["h2", "h3"] and current != heading:
            break

        if hasattr(current, "find_all"):
            for img in current.find_all("img"):

                alt = img.get("alt", "").strip()

                # Esempio:
                # Vialli - 89 - Base Hero
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

                    # IMPORTANTE:
                    # non eliminiamo i duplicati.
                    # FUT.GG può usare la stessa carta
                    # più volte nella lineup.
                    players.append(player)

                    if len(players) == 5:
                        return players

        current = current.find_next()

    raise Exception(
        f"Trovati {len(players)} giocatori invece di 5"
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
            "disable_web_page_preview": True
        },
        timeout=30
    )

    response.raise_for_status()


def player_text(player):
    return (
        f"{player['name']} "
        f"({player['rating']}) - {player['card']}"
    )


def main():

    # Carica la lineup precedente
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

        print(f"Controllo {category}...")

        players = get_players(url)

        print(
            "Giocatori trovati:",
            [player_text(p) for p in players]
        )

        new_state[category] = players

        old_players = old_state.get(category)

        # Primo avvio:
        # salva la lineup senza mandare notifiche
        if old_players is None:
            print(
                f"Prima scansione di {category}: "
                "salvo la lineup."
            )
            continue

        # Confrontiamo la LISTA completa.
        # In questo modo vengono considerati
        # anche eventuali giocatori duplicati.
        if old_players != players:

            removed = old_players.copy()
            added = players.copy()

            # Rimuove le carte rimaste uguali
            # per mostrare solo le differenze.
            for player in old_players:
                if player in added:
                    added.remove(player)
                    removed.remove(player)

            message = (
                f"🚨 FUT.GG {category} CAMBIATA!\n\n"
            )

            for player in removed:
                message += (
                    f"❌ {player_text(player)}\n"
                )

            for player in added:
                message += (
                    f"✅ {player_text(player)}\n"
                )

            message += f"\n🔗 {url}"

            send_telegram(message)

            print("Notifica Telegram inviata.")

        else:
            print("Nessun cambiamento.")

    # Salva la lineup attuale
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
