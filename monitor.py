import os
import re
import json
import html
import requests
from datetime import datetime, timezone
from urllib.parse import urljoin
from bs4 import BeautifulSoup


# ============================================================
# FUT.GG FEEDS
# ============================================================

PAGES = {
    "🦸 HEROES": {
        "url": "https://www.fut.gg/fut-gallery/rarities/heroes/",
        "players": 5,
        "distinguish": True,
    },

    "✨ HOLOGRAPHICS": {
        "url": "https://www.fut.gg/fut-gallery/rarities/holographics/",
        "players": 5,
        "distinguish": False,
    },

    "🏆 SEASON 1": {
        "url": "https://www.fut.gg/fut-gallery/rarities/season-1/",
        "players": 10,
        "distinguish": True,
    },
}


# ============================================================
# TELEGRAM
# ============================================================

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


# ============================================================
# SETTINGS
# ============================================================

STATE_FILE = "feed_state.json"
SITE = "https://www.fut.gg"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
}


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    telegram_url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
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

    print("Telegram notification sent successfully.")


# ============================================================
# CARD VERSION
# ============================================================

def get_version(item_url):
    response = requests.get(
        item_url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    h1 = soup.find("h1")

    if not h1:
        raise Exception(
            f"Card title not found: {item_url}"
        )

    title = h1.get_text(
        " ",
        strip=True,
    )

    if re.search(
        r"pristine\s+holographic",
        title,
        re.I,
    ):
        return "Pristine Holographic"

    if re.search(
        r"holographic",
        title,
        re.I,
    ):
        return "Holographic"

    return "Base"


# ============================================================
# FIND CARD LINK
# ============================================================

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
            href=pattern,
        )

        if link:
            return link["href"]

    link = soup.find(
        "a",
        href=pattern,
    )

    if link:
        return link["href"]

    return None


# ============================================================
# GET FUT.GG PLAYERS
# ============================================================

def get_players(
    url,
    expected_players,
    distinguish=False,
    known_versions=None,
):
    known_versions = known_versions or {}

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
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

        if hasattr(current, "find_all"):
            for img in current.find_all("img"):
                alt = img.get(
                    "alt",
                    "",
                ).strip()

                match = re.match(
                    r"(.+?)\s*-\s*(\d+)\s*-\s*(.+)",
                    alt,
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
                        "",
                    )

                    id_match = re.search(
                        r"27-(\d+)",
                        src,
                    )

                    if not id_match:
                        print(
                            f"WARNING: Card ID not found for {alt}"
                        )
                        continue

                    item_id = id_match.group(1)

                    player["item_id"] = item_id

                    if item_id in known_versions:
                        player["version"] = (
                            known_versions[item_id]
                        )

                    else:
                        href = find_card_link(
                            img,
                            soup,
                            item_id,
                        )

                        if href:
                            try:
                                player["version"] = get_version(
                                    urljoin(
                                        SITE,
                                        href,
                                    )
                                )

                            except Exception as error:
                                print(
                                    f"Version detection error: {error}"
                                )

                                player["version"] = "?"

                        else:
                            player["version"] = "?"

                players.append(player)

                if len(players) >= expected_players:
                    return players

        current = current.find_next()

    raise Exception(
        f"Found {len(players)} players instead of "
        f"{expected_players} on {url}"
    )


# ============================================================
# PLAYER TEXT
# ============================================================

def player_text(player):
    tag = ""

    version = player.get("version")

    if version == "Base":
        tag = "⚪ <b>BASE</b> · "

    elif version and version != "?":
        safe_version = html.escape(
            version.upper()
        )

        tag = (
            f"✨ <b>{safe_version}</b> · "
        )

    name = html.escape(
        str(player["name"])
    )

    rating = html.escape(
        str(player["rating"])
    )

    card = html.escape(
        str(player["card"])
    )

    return (
        f"{tag}"
        f"<b>{name}</b> — "
        f"{rating} — "
        f"{card}"
    )


# ============================================================
# LOAD STATE
# ============================================================

def load_state():
    if not os.path.exists(
        STATE_FILE
    ):
        return {}

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception as error:
        print(
            f"Could not load previous feed state: {error}"
        )

        return {}


# ============================================================
# SAVE STATE
# ============================================================

def save_state(state):
    with open(
        STATE_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"{STATE_FILE} saved successfully."
    )


# ============================================================
# COMPARE FEEDS
# ============================================================

def compare_players(
    old_players,
    new_players,
):
    removed = old_players.copy()
    added = new_players.copy()

    for player in old_players:
        if player in added:
            added.remove(player)

            if player in removed:
                removed.remove(player)

    return removed, added


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("FUTFLEX FUT.GG MONITOR")
    print("=" * 60)

    now = datetime.now(
        timezone.utc
    )

    print(
        "Current UTC time:",
        now.isoformat(),
    )

    old_state = load_state()

    new_state = {}
    results = []

    # ========================================================
    # CHECK EVERY FEED
    # ========================================================

    for category, config in PAGES.items():
        print()
        print("=" * 60)
        print(
            f"Checking {category}"
        )
        print("=" * 60)

        url = config["url"]
        expected_players = config["players"]

        distinguish = config.get(
            "distinguish",
            False,
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
                item_id = player.get(
                    "item_id"
                )

                version = player.get(
                    "version"
                )

                if (
                    item_id
                    and version not in [None, "?"]
                ):
                    known_versions[
                        item_id
                    ] = version

        try:
            players = get_players(
                url,
                expected_players,
                distinguish,
                known_versions,
            )

        except Exception as error:
            print(
                f"ERROR while checking {category}: {error}"
            )

            if old_players is not None:
                new_state[
                    category
                ] = old_players

            results.append({
                "category": category,
                "status": "error",
                "error": str(error),
                "url": url,
            })

            continue

        new_state[
            category
        ] = players

        print(
            f"Players found: {len(players)}"
        )

        for player in players:
            version = ""

            if "version" in player:
                version = (
                    f" [{player['version']}]"
                )

            print(
                "-",
                player["name"],
                player["rating"],
                player["card"],
                version,
            )

        # ====================================================
        # FIRST SCAN
        # ====================================================

        if old_players is None:
            results.append({
                "category": category,
                "status": "first_scan",
                "players": players,
                "url": url,
            })

            continue

        # ====================================================
        # INCOMPLETE CARD INFORMATION
        # ====================================================

        incomplete = False

        if distinguish:
            for player in players:
                if (
                    player.get("version")
                    == "?"
                ):
                    incomplete = True
                    break

        if incomplete:
            results.append({
                "category": category,
                "status": "incomplete",
                "players": players,
                "url": url,
            })

            continue

        # ====================================================
        # CHECK FOR CHANGES
        # ====================================================

        if old_players != players:
            removed, added = compare_players(
                old_players,
                players,
            )

            if (
                not removed
                and not added
            ):
                results.append({
                    "category": category,
                    "status": "unchanged",
                    "players": players,
                    "url": url,
                })

                continue

            results.append({
                "category": category,
                "status": "changed",
                "players": players,
                "removed": removed,
                "added": added,
                "url": url,
            })

        else:
            results.append({
                "category": category,
                "status": "unchanged",
                "players": players,
                "url": url,
            })

    # ========================================================
    # SAVE CURRENT STATE
    # ========================================================

    save_state(
        new_state
    )

    # ========================================================
    # BUILD TELEGRAM MESSAGE
    # ========================================================

    has_changes = any(
        result["status"] == "changed"
        for result in results
    )

    if has_changes:
        message = (
            "⚡ <b>FUTFLEX FEED UPDATE</b>\n\n"
        )
    else:
        message = (
            "🤖 <b>FUTFLEX MONITOR</b>\n\n"
        )

    message += (
        "✅ Monitoring check completed\n"
        f"🕐 {now.strftime('%d/%m/%Y %H:%M:%S')} UTC\n"
    )

    for result in results:
        category = result["category"]
        status = result["status"]

        message += (
            "\n━━━━━━━━━━━━━━\n"
            f"<b>{category}</b>\n"
        )

        # ====================================================
        # FEED CHANGED
        # ====================================================

        if status == "changed":
            for player in result["removed"]:
                message += (
                    "❌ <b>GONE</b> · "
                    f"{player_text(player)}\n"
                )

            for player in result["added"]:
                message += (
                    "🆕 <b>NEW</b> · "
                    f"{player_text(player)}\n"
                )

        # ====================================================
        # NO CHANGES
        # ====================================================

        elif status == "unchanged":
            message += (
                "✓ No changes\n"
            )

        # ====================================================
        # FIRST SCAN
        # ====================================================

        elif status == "first_scan":
            message += (
                "✓ First scan saved\n"
            )

        # ====================================================
        # INCOMPLETE DATA
        # ====================================================

        elif status == "incomplete":
            message += (
                "⚠️ Incomplete card version data\n"
            )

        # ====================================================
        # ERROR
        # ====================================================

        elif status == "error":
            error = html.escape(
                result["error"]
            )

            message += (
                "⚠️ Feed check failed\n"
                f"<code>{error}</code>\n"
            )

    message += (
        "\n━━━━━━━━━━━━━━\n"
        "⏱ Automatic monitoring · 10 min"
    )

    # ========================================================
    # ALWAYS SEND TELEGRAM
    # ========================================================

    send_telegram(
        message
    )

    print()
    print("=" * 60)
    print("MONITOR COMPLETED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
