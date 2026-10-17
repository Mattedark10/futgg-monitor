import os
import re
import json
import html
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# =========================
# FUT.GG FEEDS
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
    response = requests.get(
        item_url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    h1 = soup.find("h1")

    if not h1:
        raise Exception(
            f"Titolo carta non trovato: {item_url}"
        )

    title = h1.get_text(
        " ",
        strip=True
    )

    if re.search(
        r"pristine\s+holographic",
        title,
        re.I
    ):
        return "Pristine Holographic"

    if re.search(
        r"holographic",
        title,
        re.I
    ):
        return "Holographic"

    return "Base"


# =========================
# FIND CARD LINK
# =========================
def find_card_link(img, soup, item_id):
    pattern = re.compile(
        rf"/players/.*27-{item_id}"
    )

    parent = img

    for _ in range(6):
        parent = parent.parent

        if parent is None:
            break

        if (
            parent.name == "a"
            and pattern.search(
                parent.get("href", "")
            )
        ):
            return parent["href"]

        link = parent.find(
            "a",
            href=pattern
        )

        if link:
            return link["href"]

    link = soup.find(
        "a",
        href=pattern
    )

    return (
        link["href"]
        if link
        else None
    )


# =========================
# GET FUT.GG PLAYERS
# =========================
def get_players(
    url,
    expected_players,
    distinguish=False,
    known_versions=None
):
    known_versions = (
        known_versions or {}
    )

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

        if (
            current.name in ["h2", "h3"]
            and current != heading
        ):
            break

        if hasattr(
            current,
            "find_all"
        ):

            for img in current.find_all(
                "img"
            ):

                alt = img.get(
                    "alt",
                    ""
                ).strip()

                match = re.match(
                    r"(.+?)\s*-\s*(\d+)\s*-\s*(.+)",
                    alt
                )

                if not match:
                    continue

                player = {
                    "name": match.group(1).strip(),
                    "rating": match.group(2).strip(),
                    "card": match.group(3).strip(),
                }

                if distinguish:

                    src = img.get(
                        "src",
                        ""
                    )

                    id_match = re.search(
                        r"27-(\d+)",
                        src
                    )

                    if not id_match:
                        raise Exception(
                            f"ID carta non trovato "
                            f"per '{alt}' | "
                            f"src='{src}'"
                        )

                    item_id = (
                        id_match.group(1)
                    )

                    player["item_id"] = (
                        item_id
                    )

                    if item_id in known_versions:

                        player["version"] = (
                            known_versions[
                                item_id
                            ]
                        )

                    else:

                        href = find_card_link(
                            img,
                            soup,
                            item_id
                        )

                        if href:

                            player["version"] = (
                                get_version(
                                    urljoin(
                                        SITE,
                                        href
                                    )
                                )
                            )

                        else:

                            print(
                                "ATTENZIONE: "
                                f"link non trovato "
                                f"per '{alt}' "
                                f"(ID {item_id})"
                            )

                            player[
                                "version"
                            ] = "?"

                players.append(
                    player
                )

                if len(players) == expected_players:
                    return players

        current = current.find_next()

    raise Exception(
        f"Found {len(players)} players "
        f"instead of {expected_players} "
        f"on {url}"
    )


# =========================
# TELEGRAM
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
            "disable_web_page_preview": True,
        },
        timeout=30,
    )

    response.raise_for_status()


# =========================
# PLAYER TEXT
# =========================
def player_text(player):

    tag = ""

    version = player.get(
        "version"
    )

    if version == "Base":

        tag = (
            "⚪ <b>BASE</b> · "
        )

    elif version and version != "?":

        tag = (
            f"🌈 <b>"
            f"{html.escape(version.upper())}"
            f"</b> · "
        )

    name = html.escape(
        player["name"]
    )

    rating = html.escape(
        player["rating"]
    )

    card = html.escape(
        player["card"]
    )

    return (
        f"{tag}"
        f"<b>{name}</b> — "
        f"{rating} — "
        f"{card}"
    )


# =========================
# FEED CHANGE CHECK
# =========================
def calculate_changes(
    old_players,
    new_players
):

    removed = old_players.copy()
    added = new_players.copy()

    for player in old_players:

        if player in added:

            added.remove(
                player
            )

            if player in removed:
                removed.remove(
                    player
                )

    return removed, added


# =========================
# MAIN
# =========================
def main():

    check_time = datetime.now(
        timezone.utc
    ).astimezone()

    formatted_time = (
        check_time.strftime(
            "%d/%m/%Y %H:%M:%S"
        )
    )

    print()
    print("=" * 50)
    print("FutFlex FUT.GG MONITOR")
    print("=" * 50)

    print(
        f"Check time: {formatted_time}"
    )

    # =========================
    # LOAD PREVIOUS STATE
    # =========================
    if os.path.exists(
        STATE_FILE
    ):

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            old_state = json.load(
                file
            )

    else:

        old_state = {}

    new_state = {}

    # Salviamo qui il risultato
    # di ogni feed per Telegram.
    feed_results = []

    # =========================
    # CHECK EVERY FEED
    # =========================
    for category, config in PAGES.items():

        url = config["url"]

        expected_players = (
            config["players"]
        )

        distinguish = config.get(
            "distinguish",
            False
        )

        print()
        print(
            f"Checking {category} "
            f"({expected_players} players)..."
        )

        old_players = old_state.get(
            category
        )

        known_versions = {}

        if (
            old_players
            and distinguish
        ):

            for player in old_players:

                if (
                    "item_id" in player
                    and player.get(
                        "version"
                    ) not in (
                        None,
                        "?"
                    )
                ):

                    known_versions[
                        player["item_id"]
                    ] = player[
                        "version"
                    ]

        # =========================
        # DOWNLOAD FEED
        # =========================
        try:

            players = get_players(
                url,
                expected_players,
                distinguish,
                known_versions
            )

        except Exception as exc:

            print(
                f"ERROR checking "
                f"{category}: {exc}"
            )

            feed_results.append({
                "category": category,
                "status": "error",
                "error": str(exc),
            })

            # Non blocchiamo tutto il monitor
            continue

        print(
            f"Found {len(players)} players."
        )

        for player in players:

            version = ""

            if "version" in player:
                version = (
                    f" [{player['version']}]"
                )

            print(
                f"- {player['name']} "
                f"{player['rating']} "
                f"{player['card']}"
                f"{version}"
            )

        new_state[
            category
        ] = players

        # =========================
        # FIRST SCAN
        # =========================
        if old_players is None:

            print(
                f"First scan for "
                f"{category}."
            )

            feed_results.append({
                "category": category,
                "status": "first_scan",
                "added": [],
                "removed": [],
            })

            continue

        # =========================
        # INCOMPLETE VERSION DATA
        # =========================
        if distinguish and (
            any(
                "version" not in p
                for p in old_players
            )
            or any(
                p.get("version") == "?"
                for p in old_players
            )
            or any(
                p.get("version") == "?"
                for p in players
            )
        ):

            print(
                f"{category}: "
                "versioni incomplete."
            )

            feed_results.append({
                "category": category,
                "status": "incomplete",
                "added": [],
                "removed": [],
            })

            continue

        # =========================
        # CHECK CHANGES
        # =========================
        if old_players != players:

            removed, added = (
                calculate_changes(
                    old_players,
                    players
                )
            )

            if not removed and not added:

                print(
                    f"{category}: "
                    "player order changed only."
                )

                feed_results.append({
                    "category": category,
                    "status": "unchanged",
                    "added": [],
                    "removed": [],
                })

                continue

            print(
                f"{category}: "
                f"CHANGED "
                f"(+{len(added)} / "
                f"-{len(removed)})"
            )

            feed_results.append({
                "category": category,
                "status": "changed",
                "added": added,
                "removed": removed,
            })

        else:

            print(
                f"{category}: "
                "No feed changes."
            )

            feed_results.append({
                "category": category,
                "status": "unchanged",
                "added": [],
                "removed": [],
            })

    # =========================
    # SAVE CURRENT STATE
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

    print(
        "Feed state saved successfully."
    )

    # =========================
    # BUILD ALWAYS-ON TELEGRAM
    # =========================
    message = (
        "🤖 <b>FUTFLEX MONITOR</b>\n\n"
        "✅ <b>Controllo completato</b>\n"
        f"🕐 {formatted_time}\n\n"
    )

    for result in feed_results:

        category = result[
            "category"
        ]

        status = result[
            "status"
        ]

        if status == "changed":

            added = result[
                "added"
            ]

            removed = result[
                "removed"
            ]

            message += (
                f"🚨 <b>{category}</b> "
                "— <b>CAMBIATA</b>\n"
            )

            for player in removed:

                message += (
                    "🔴 <b>OUT</b> · "
                    f"{player_text(player)}\n"
                )

            for player in added:

                message += (
                    "🟢 <b>IN</b> · "
                    f"{player_text(player)}\n"
                )

            message += "\n"

        elif status == "unchanged":

            message += (
                f"🟢 <b>{category}</b> "
                "— Nessun cambiamento\n"
            )

        elif status == "first_scan":

            message += (
                f"🆕 <b>{category}</b> "
                "— Prima scansione\n"
            )

        elif status == "incomplete":

            message += (
                f"⚠️ <b>{category}</b> "
                "— Dati incompleti\n"
            )

        elif status == "error":

            error = html.escape(
                result.get(
                    "error",
                    "Errore sconosciuto"
                )
            )

            message += (
                f"🔴 <b>{category}</b> "
                "— ERRORE\n"
                f"<code>{error}</code>\n"
            )

    message += (
        "\n🔄 Controllo automatico "
        "ogni 5 minuti."
    )

    # =========================
    # ALWAYS SEND TELEGRAM
    # =========================
    send_telegram(
        message
    )

    print()
    print(
        "Telegram monitor notification sent."
    )

    print("=" * 50)


# =========================
# START
# =========================
if __name__ == "__main__":
    main()
