import os
import re
import json
import html
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# =========================
# FUT.GG FEEDS
# "distinguish": True -> distingue BASE / HOLOGRAPHIC / PRISTINE HOLOGRAPHIC
# =========================
PAGES = {
    "🦸 HEROES": {
        "url": "https://www.fut.gg/fut-gallery/rarities/heroes/",
        "players": 5,
        "distinguish": True,
    },
    "🌈 HOLOGRAPHICS": {
        "url": "https://www.fut.gg/fut-gallery/rarities/holographics/",
        "players": 5,
        "distinguish": False,
    },
}

# =========================
# TELEGRAM
# =========================
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# =========================
# SETTINGS
# =========================
STATE_FILE = "players.json"
SITE = "https://www.fut.gg"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
}


# =========================
# BASE / HOLO CHECK
# =========================
def get_version(item_url):
    """
    Apre la pagina della singola carta e legge il titolo (h1):
    - "Cucurella - Destined for Glory 88 OVR"                    -> Base
    - "Cucurella - Destined for Glory Pristine Holographic 88 OVR" -> Pristine Holographic
    Si guarda SOLO l'h1, perché nel resto della pagina compare sempre
    il selettore "Standard / Pristine Holographic".
    """
    response = requests.get(item_url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    h1 = soup.find("h1")

    if not h1:
        raise Exception(f"Titolo carta non trovato: {item_url}")

    title = h1.get_text(" ", strip=True)

    if re.search(r"pristine\s+holographic", title, re.I):
        return "Pristine Holographic"
    if re.search(r"holographic", title, re.I):
        return "Holographic"
    return "Base"


def find_card_link(img, soup, item_id):
    """
    Cerca il link alla pagina della carta (/players/.../27-ID/):
    1) tra i genitori dell'immagine
    2) dentro i contenitori vicini all'immagine
    3) in qualsiasi punto della pagina
    Accetta solo link che contengono lo stesso ID della carta.
    """
    pattern = re.compile(rf"/players/.*27-{item_id}")

    parent = img
    for _ in range(6):
        parent = parent.parent
        if parent is None:
            break
        if parent.name == "a" and pattern.search(parent.get("href", "")):
            return parent["href"]
        link = parent.find("a", href=pattern)
        if link:
            return link["href"]

    link = soup.find("a", href=pattern)
    return link["href"] if link else None


# =========================
# GET FUT.GG PLAYERS
# =========================
def get_players(url, expected_players, distinguish=False, known_versions=None):
    known_versions = known_versions or {}

    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Find the FUT.GG recommended lineup section
    heading = soup.find(
        lambda tag:
        tag.name in ["h2", "h3"]
        and "Cheapest grade" in tag.get_text()
        and "lineup" in tag.get_text()
    )

    if not heading:
        raise Exception(f"Feed lineup not found: {url}")

    players = []
    current = heading.find_next()

    while current:
        # Stop when the next section begins
        if current.name in ["h2", "h3"] and current != heading:
            break

        if hasattr(current, "find_all"):
            for img in current.find_all("img"):
                alt = img.get("alt", "").strip()

                # Example:
                # Vialli - 89 - Base Hero
                match = re.match(r"(.+?)\s*-\s*(\d+)\s*-\s*(.+)", alt)

                if match:
                    player = {
                        "name": match.group(1).strip(),
                        "rating": match.group(2).strip(),
                        "card": match.group(3).strip(),
                    }

                    if distinguish:
                        src = img.get("src", "")

                        # ID unico della carta (es. 27-67335170):
                        # la versione base e quella olografica
                        # hanno ID diversi
                        id_match = re.search(r"27-(\d+)", src)

                        if not id_match:
                            raise Exception(
                                f"ID carta non trovato per '{alt}' | "
                                f"src='{src}'"
                            )

                        item_id = id_match.group(1)
                        player["item_id"] = item_id

                        if item_id in known_versions:
                            # Già conosciuta: non riapro la pagina
                            player["version"] = known_versions[item_id]
                        else:
                            href = find_card_link(img, soup, item_id)

                            if href:
                                player["version"] = get_version(
                                    urljoin(SITE, href)
                                )
                            else:
                                # Link non trovato: non blocco il bot
                                print(
                                    f"ATTENZIONE: link non trovato per "
                                    f"'{alt}' (ID {item_id})"
                                )
                                print(
                                    "DEBUG PARENT:",
                                    str(img.parent)[:600]
                                )
                                print(
                                    "DEBUG PARENT2:",
                                    str(img.parent.parent)[:900]
                                )
                                player["version"] = "?"

                    # Do NOT remove duplicates.
                    # The same card can appear more than once.
                    players.append(player)

                    if len(players) == expected_players:
                        return players

        current = current.find_next()

    raise Exception(
        f"Found {len(players)} players instead of "
        f"{expected_players} on {url}"
    )


# =========================
# TELEGRAM MESSAGE
# =========================
def send_telegram(message):
    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        telegram_url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    response.raise_for_status()


def player_text(player):
    tag = ""
    version = player.get("version")

    if version == "Base":
        tag = "⚪ <b>BASE</b> · "
    elif version and version != "?":
        tag = f"🌈 <b>{html.escape(version.upper())}</b> · "

    name = html.escape(player["name"])
    rating = html.escape(player["rating"])
    card = html.escape(player["card"])

    return f"{tag}<b>{name}</b> — {rating} — {card}"


# =========================
# MAIN MONITOR
# =========================
def main():
    # Load previous feeds
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            old_state = json.load(file)
    else:
        old_state = {}

    new_state = {}

    # Check every FUT.GG feed
    for category, config in PAGES.items():
        url = config["url"]
        expected_players = config["players"]
        distinguish = config.get("distinguish", False)

        print(f"Checking {category} ({expected_players} players)...")

        old_players = old_state.get(category)

        # Versioni già note (item_id -> Base/Holographic/...)
        known_versions = {}
        if old_players and distinguish:
            for p in old_players:
                if "item_id" in p and p.get("version") not in (None, "?"):
                    known_versions[p["item_id"]] = p["version"]

        players = get_players(
            url, expected_players, distinguish, known_versions
        )

        print(f"Found {len(players)} players.")
        for player in players:
            version = f" [{player['version']}]" if "version" in player else ""
            print(
                f"- {player['name']} "
                f"{player['rating']} "
                f"{player['card']}{version}"
            )

        new_state[category] = players

        # New category / first scan:
        # save it without sending an alert
        if old_players is None:
            print(f"First scan for {category}. Saving current feed.")
            continue

        # Dati vecchi senza item_id/version: li aggiorno senza notifica
        if distinguish and (
            any("version" not in p for p in old_players)
            or any(p["version"] == "?" for p in old_players)
            or any(p["version"] == "?" for p in players)
        ):
            print(f"{category}: versioni incomplete, nessuna notifica.")
            continue

        # =========================
        # CHECK FOR FEED CHANGES
        # =========================
        if old_players != players:
            removed = old_players.copy()
            added = players.copy()

            # Remove players/cards that stayed the same.
            # This also handles duplicate cards correctly.
            for player in old_players:
                if player in added:
                    added.remove(player)
                    if player in removed:
                        removed.remove(player)

            # If the lists only changed order,
            # don't send a false notification.
            if not removed and not added:
                print(f"{category}: player order changed only.")
                continue

            # =========================
            # BUILD TELEGRAM ALERT
            # =========================
            message = (
                "🚨 <b>FUT.GG FEED UPDATE</b>\n\n"
                f"{category} <b>FEED</b>\n"
                "The best team has been updated.\n\n"
                "🔄 <b>FEED CHANGES</b>\n"
            )

            for player in removed:
                message += f"🔴 <b>OUT</b> · {player_text(player)}\n"

            for player in added:
                message += f"🟢 <b>IN</b> · {player_text(player)}\n"

            safe_url = html.escape(url, quote=True)

            message += (
                "\n🕐 Change detected automatically\n"
                f'🔗 <a href="{safe_url}">View Feed on FUT.GG</a>'
            )

            send_telegram(message)
            print(f"{category}: Telegram notification sent.")

        else:
            print(f"{category}: No feed changes.")

    # =========================
    # SAVE CURRENT FEEDS
    # =========================
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(new_state, file, ensure_ascii=False, indent=2)

    print("Feed state saved successfully.")


# =========================
# START
# =========================
if __name__ == "__main__":
    main()
