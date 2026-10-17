import os
import re
import json
import html
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup


# =========================
# FUT.GG FEEDS
# =========================

PAGES = {
    "🦸 HEROES": {
        "url": "https://www.fut.gg/fut-gallery/rarities/heroes/",
        "players": 5
    },

    "✨ HOLOGRAPHICS": {
        "url": "https://www.fut.gg/fut-gallery/rarities/holographics/",
        "players": 5
    },

    "🏆 SEASON 1": {
        "url": "https://www.fut.gg/fut-gallery/rarities/season-1/",
        "players": 10
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
}


# =========================
# GET FUT.GG PLAYERS
# =========================

def get_players(url, expected_players):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # Find the FUT.GG recommended lineup section
    heading = soup.find(
        lambda tag:
        tag.name in ["h2", "h3"]
        and "Cheapest grade" in tag.get_text()
        and "lineup" in tag.get_text()
    )

    if not heading:
        raise Exception(
            f"Feed lineup not found: {url}"
        )

    players = []

    current = heading.find_next()

    while current:

        # Stop when the next section begins
        if (
            current.name in ["h2", "h3"]
            and current != heading
        ):
            break

        if hasattr(current, "find_all"):

            for img in current.find_all("img"):

                alt = img.get("alt", "").strip()

                # Example:
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

    telegram_url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        telegram_url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=30
    )

    response.raise_for_status()

    print("Telegram notification sent successfully.")


def player_text(player):

    name = html.escape(player["name"])
    rating = html.escape(player["rating"])
    card = html.escape(player["card"])

    return (
        f"<b>{name}</b> — "
        f"{rating} — "
        f"{card}"
    )


# =========================
# MAIN MONITOR
# =========================

def main():

    # Load previous feeds
    if os.path.exists(STATE_FILE):

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            old_state = json.load(file)

    else:
        old_state = {}

    # Keep old data for categories that fail to load
    new_state = dict(old_state)

    results = []
    any_changes = False

    # Check every FUT.GG feed
    for category, config in PAGES.items():

        url = config["url"]
        expected_players = config["players"]

        print(
            f"Checking {category} "
            f"({expected_players} players)..."
        )

        try:
            players = get_players(
                url,
                expected_players
            )

        except Exception as error:

            print(
                f"{category}: ERROR {error}"
            )

            results.append({
                "category": category,
                "status": "error",
                "error": str(error)
            })

            continue

        print(
            f"Found {len(players)} players."
        )

        for player in players:
            print(
                f"- {player['name']} "
                f"{player['rating']} "
                f"{player['card']}"
            )

        new_state[category] = players

        old_players = old_state.get(category)

        # New category / first scan
        if old_players is None:

            print(
                f"First scan for {category}. "
                "Saving current feed."
            )

            results.append({
                "category": category,
                "status": "first_scan"
            })

            continue

        # =========================
        # CHECK FOR FEED CHANGES
        # =========================

        removed = old_players.copy()
        added = players.copy()

        # Remove players/cards that stayed the same.
        # This also handles duplicate cards correctly.
        for player in old_players:

            if player in added:
                added.remove(player)

                if player in removed:
                    removed.remove(player)

        # If the lists only changed order (or nothing
        # changed), there is nothing to report.
        if not removed and not added:

            print(
                f"{category}: No feed changes."
            )

            results.append({
                "category": category,
                "status": "unchanged"
            })

            continue

        any_changes = True

        results.append({
            "category": category,
            "status": "changed",
            "removed": removed,
            "added": added
        })

    # =========================
    # SAVE CURRENT FEEDS
    # =========================

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            new_state,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("Feed state saved successfully.")

    # =========================
    # BUILD TELEGRAM MESSAGE
    # (sent on every run)
    # =========================

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%d/%m/%Y %H:%M:%S UTC"
    )

    if any_changes:
        header = "⚡ <b>FUTFLEX FEED UPDATE</b>"
    else:
        header = "🤖 <b>FUTFLEX MONITOR</b>"

    parts = [
        header,
        "",
        "✅ Monitoring check completed",
        f"🕐 {now}",
        ""
    ]

    for result in results:

        category = html.escape(
            result["category"]
        )

        parts.append("━━━━━━━━━━━━━━")
        parts.append(f"<b>{category}</b>")

        status = result["status"]

        if status == "changed":

            for player in result["removed"]:
                parts.append(
                    "❌ <b>GONE</b> · "
                    f"{player_text(player)}"
                )

            for player in result["added"]:
                parts.append(
                    "🆕 <b>NEW</b> · "
                    f"{player_text(player)}"
                )

        elif status == "unchanged":
            parts.append("✓ No changes")

        elif status == "first_scan":
            parts.append("✓ Monitoring initialized")

        elif status == "error":
            parts.append("⚠️ <b>Feed check failed</b>")
            parts.append(
                html.escape(result["error"])
            )

        parts.append("")

    parts.append("━━━━━━━━━━━━━━")
    parts.append("⏱ Automatic monitoring · 5 min")

    send_telegram("\n".join(parts))


# =========================
# START
# =========================

if __name__ == "__main__":
    main()