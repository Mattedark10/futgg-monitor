import os
import re
import json
import html
import requests
from collections import Counter
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
        "detect_version": True,
    },

    "✨ HOLOGRAPHICS": {
        "url": "https://www.fut.gg/fut-gallery/rarities/holographics/",
        "players": 5,
        "detect_version": False,
    },

    "🏆 SEASON 1": {
        "url": "https://www.fut.gg/fut-gallery/rarities/season-1/",
        "players": 10,
        "detect_version": True,
    },
}


# ============================================================
# SETTINGS
# ============================================================

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

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
            "disable_web_page_preview": True,
        },
        timeout=30,
    )

    response.raise_for_status()

    print("Telegram notification sent successfully.")


# ============================================================
# PLAYER ALT
# ============================================================

def parse_player_alt(alt):
    match = re.match(
        r"(.+?)\s*-\s*(\d+)\s*-\s*(.+)",
        alt.strip(),
    )

    if not match:
        return None

    return {
        "name": match.group(1).strip(),
        "rating": match.group(2).strip(),
        "card": match.group(3).strip(),
    }


# ============================================================
# EXTRACT ITEM ID
# ============================================================

def extract_item_id(img):
    values = []

    for attribute in (
        "src",
        "data-src",
        "srcset",
        "data-srcset",
    ):
        value = img.get(
            attribute,
            "",
        )

        if value:
            values.append(value)

    combined = " ".join(values)

    match = re.search(
        r"27-(\d+)",
        combined,
    )

    if not match:
        return None

    return match.group(1)


# ============================================================
# FIND EXACT CARD LINK
# ============================================================

def find_exact_card_link(
    img,
    item_id,
):
    """
    Search for the card link only around the current image.
    Never search the entire page for the player.
    """

    pattern = re.compile(
        rf"/players/[^\"']*/27-{re.escape(item_id)}/?"
    )

    # Image directly inside a link.

    link = img.find_parent(
        "a",
        href=True,
    )

    if link:
        href = link.get(
            "href",
            "",
        )

        if pattern.search(href):
            return href

    # Search progressively through nearby containers.

    parent = img.parent

    for _ in range(8):
        if parent is None:
            break

        if hasattr(
            parent,
            "find_all",
        ):
            for link in parent.find_all(
                "a",
                href=True,
            ):
                href = link.get(
                    "href",
                    "",
                )

                if pattern.search(href):
                    return href

        parent = parent.parent

    return None


# ============================================================
# DETECT CARD VERSION
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

    # Read as much useful metadata as possible.

    texts = []

    h1 = soup.find("h1")

    if h1:
        texts.append(
            h1.get_text(
                " ",
                strip=True,
            )
        )

    title = soup.find("title")

    if title:
        texts.append(
            title.get_text(
                " ",
                strip=True,
            )
        )

    # Some FUT.GG pages may expose the version elsewhere
    # in their metadata.

    for meta in soup.find_all("meta"):
        content = meta.get(
            "content",
            "",
        )

        if content:
            texts.append(content)

    combined = " ".join(texts)

    print(
        f"Card URL: {item_url}"
    )

    print(
        f"Version metadata: {combined[:500]}"
    )

    if re.search(
        r"pristine\s+holographic",
        combined,
        re.I,
    ):
        return "Pristine Holographic"

    if re.search(
        r"\bholographic\b",
        combined,
        re.I,
    ):
        return "Holographic"

    return "Base"


# ============================================================
# GET LINEUP PLAYER IMAGES
# ============================================================

def get_lineup_images(
    soup,
    expected_players,
):
    """
    Find the Cheapest grade lineup and read every player IMG
    until the Add players heading.

    Important:
    We walk through next_elements rather than stopping at the
    next H2/H3 because FUT.GG uses nested headings/containers.
    """

    heading = soup.find(
        lambda tag:
        tag.name in ["h2", "h3"]
        and "Cheapest grade"
        in tag.get_text(
            " ",
            strip=True,
        )
        and "lineup"
        in tag.get_text(
            " ",
            strip=True,
        )
    )

    if not heading:
        raise Exception(
            "Cheapest grade lineup section not found."
        )

    images = []

    seen_images = set()

    for element in heading.next_elements:

        # ====================================================
        # STOP AT ADD PLAYERS
        # ====================================================

        if (
            getattr(
                element,
                "name",
                None,
            )
            in ["h2", "h3"]
        ):
            heading_text = element.get_text(
                " ",
                strip=True,
            )

            if (
                heading_text.lower()
                == "add players"
            ):
                break

        # ====================================================
        # ONLY PROCESS IMG ELEMENTS
        # ====================================================

        if (
            getattr(
                element,
                "name",
                None,
            )
            != "img"
        ):
            continue

        alt = element.get(
            "alt",
            "",
        ).strip()

        player_data = parse_player_alt(
            alt
        )

        if not player_data:
            continue

        # BeautifulSoup object identity prevents processing
        # the exact same IMG node twice.

        element_identity = id(
            element
        )

        if (
            element_identity
            in seen_images
        ):
            continue

        seen_images.add(
            element_identity
        )

        images.append(
            element
        )

        print(
            "Lineup slot "
            f"{len(images)}: {alt}"
        )

        if (
            len(images)
            == expected_players
        ):
            break

    return images


# ============================================================
# GET PLAYERS
# ============================================================

def get_players(
    url,
    expected_players,
    detect_version=False,
    known_versions=None,
):
    known_versions = (
        known_versions
        or {}
    )

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

    images = get_lineup_images(
        soup,
        expected_players,
    )

    print(
        f"Lineup images found: {len(images)}"
    )

    if (
        len(images)
        != expected_players
    ):
        raise Exception(
            f"Found {len(images)} player slots "
            f"instead of {expected_players} "
            f"on {url}"
        )

    players = []

    # ========================================================
    # PROCESS EACH SLOT
    # ========================================================

    for slot, img in enumerate(
        images,
        start=1,
    ):
        alt = img.get(
            "alt",
            "",
        ).strip()

        player = parse_player_alt(
            alt
        )

        if not player:
            continue

        print()
        print(
            "=" * 40
        )

        print(
            f"SLOT {slot}"
        )

        print(
            f"Name: {player['name']}"
        )

        print(
            f"Rating: {player['rating']}"
        )

        print(
            f"Card: {player['card']}"
        )

        # ====================================================
        # VERSION DETECTION
        # ====================================================

        if detect_version:
            item_id = extract_item_id(
                img
            )

            if item_id:
                player[
                    "item_id"
                ] = item_id

                print(
                    f"Item ID: {item_id}"
                )

                # ============================================
                # CACHED VERSION
                # ============================================

                if (
                    item_id
                    in known_versions
                ):
                    version = (
                        known_versions[
                            item_id
                        ]
                    )

                    player[
                        "version"
                    ] = version

                    print(
                        f"Version: {version} "
                        "(cached)"
                    )

                # ============================================
                # DETECT NEW ITEM
                # ============================================

                else:
                    href = (
                        find_exact_card_link(
                            img,
                            item_id,
                        )
                    )

                    if href:
                        item_url = urljoin(
                            SITE,
                            href,
                        )

                        try:
                            version = (
                                get_version(
                                    item_url
                                )
                            )

                            player[
                                "version"
                            ] = version

                            print(
                                f"Version: {version}"
                            )

                        except Exception as error:
                            print(
                                "Version detection "
                                f"failed: {error}"
                            )

                            player[
                                "version"
                            ] = "?"

                    else:
                        print(
                            "WARNING: Exact card "
                            "link not found."
                        )

                        player[
                            "version"
                        ] = "?"

            else:
                print(
                    "WARNING: Item ID "
                    "not found."
                )

                player[
                    "version"
                ] = "?"

        players.append(
            player
        )

    return players


# ============================================================
# PLAYER IDENTITY
# ============================================================

def player_identity(
    player,
):
    """
    Two copies of the same player are allowed.

    Item ID + version distinguishes Base from Holographic.
    """

    item_id = player.get(
        "item_id"
    )

    version = player.get(
        "version"
    )

    if item_id:
        return (
            str(item_id),
            str(version),
        )

    return (
        str(
            player.get(
                "name",
                "",
            )
        ),
        str(
            player.get(
                "rating",
                "",
            )
        ),
        str(
            player.get(
                "card",
                "",
            )
        ),
        str(version),
    )


# ============================================================
# COMPARE PLAYERS
# ============================================================

def compare_players(
    old_players,
    new_players,
):
    """
    Counter is required because duplicate players are valid.
    """

    old_counter = Counter(
        player_identity(player)
        for player
        in old_players
    )

    new_counter = Counter(
        player_identity(player)
        for player
        in new_players
    )

    removed_counter = (
        old_counter
        - new_counter
    )

    added_counter = (
        new_counter
        - old_counter
    )

    removed = []
    added = []

    # Preserve lineup order.

    for player in old_players:
        identity = player_identity(
            player
        )

        if (
            removed_counter[
                identity
            ]
            > 0
        ):
            removed.append(
                player
            )

            removed_counter[
                identity
            ] -= 1

    for player in new_players:
        identity = player_identity(
            player
        )

        if (
            added_counter[
                identity
            ]
            > 0
        ):
            added.append(
                player
            )

            added_counter[
                identity
            ] -= 1

    return (
        removed,
        added,
    )


# ============================================================
# PLAYER TELEGRAM FORMAT
# ============================================================

def player_text(
    player,
    status,
):
    name = html.escape(
        str(
            player.get(
                "name",
                "",
            )
        )
    )

    rating = html.escape(
        str(
            player.get(
                "rating",
                "",
            )
        )
    )

    card = html.escape(
        str(
            player.get(
                "card",
                "",
            )
        )
    )

    version = player.get(
        "version"
    )

    # ========================================================
    # STATUS
    # ========================================================

    if status == "new":
        status_text = (
            "🆕 <b>NEW</b>"
        )

    else:
        status_text = (
            "❌ <b>GONE</b>"
        )

    # ========================================================
    # VERSION
    # ========================================================

    version_text = None

    if version == "Base":
        version_text = (
            "⚪ <b>BASE</b>"
        )

    elif (
        version
        == "Holographic"
    ):
        version_text = (
            "✨ <b>HOLOGRAPHIC</b>"
        )

    elif (
        version
        == "Pristine Holographic"
    ):
        version_text = (
            "✨ <b>PRISTINE HOLOGRAPHIC</b>"
        )

    elif (
        version
        and version != "?"
    ):
        safe_version = html.escape(
            str(version).upper()
        )

        version_text = (
            f"✨ <b>{safe_version}</b>"
        )

    # ========================================================
    # PLAYER BLOCK
    # ========================================================

    lines = [
        f"👤 <b>{name}</b>",
        status_text,
    ]

    if version_text:
        lines.append(
            version_text
        )

    lines.append(
        f"⭐ {rating} · {card}"
    )

    return "\n".join(
        lines
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
            return json.load(
                file
            )

    except Exception as error:
        print(
            "Could not load previous "
            f"feed state: {error}"
        )

        return {}


# ============================================================
# SAVE STATE
# ============================================================

def save_state(
    state,
):
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
# MAIN
# ============================================================

def main():
    print(
        "=" * 60
    )

    print(
        "FUTFLEX FUT.GG MONITOR"
    )

    print(
        "=" * 60
    )

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
    # CHECK FEEDS
    # ========================================================

    for (
        category,
        config,
    ) in PAGES.items():

        print()
        print(
            "=" * 60
        )

        print(
            f"Checking {category}"
        )

        print(
            "=" * 60
        )

        url = config[
            "url"
        ]

        expected_players = config[
            "players"
        ]

        detect_version = config.get(
            "detect_version",
            False,
        )

        old_players = old_state.get(
            category
        )

        known_versions = {}

        # ====================================================
        # RESTORE CACHED VERSIONS
        # ====================================================

        if (
            old_players
            and detect_version
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
                    and version
                    and version != "?"
                ):
                    known_versions[
                        str(item_id)
                    ] = version

        # ====================================================
        # READ CURRENT FEED
        # ====================================================

        try:
            players = get_players(
                url=url,
                expected_players=expected_players,
                detect_version=detect_version,
                known_versions=known_versions,
            )

        except Exception as error:
            print(
                f"ERROR: {error}"
            )

            if old_players is not None:
                new_state[
                    category
                ] = old_players

            results.append({
                "category": category,
                "status": "error",
                "error": str(error),
            })

            continue

        # ====================================================
        # SAFETY CHECK
        # ====================================================

        if (
            len(players)
            != expected_players
        ):
            error = (
                f"Parsed {len(players)} players "
                f"instead of {expected_players}"
            )

            print(
                f"ERROR: {error}"
            )

            if old_players is not None:
                new_state[
                    category
                ] = old_players

            results.append({
                "category": category,
                "status": "error",
                "error": error,
            })

            continue

        new_state[
            category
        ] = players

        # ====================================================
        # LOG CURRENT LINEUP
        # ====================================================

        print()
        print(
            f"{category}: "
            f"{len(players)} players"
        )

        for index, player in enumerate(
            players,
            start=1,
        ):
            print(
                f"{index}. "
                f"{player['name']} | "
                f"{player['rating']} | "
                f"{player['card']} | "
                f"{player.get('version', '')} | "
                f"ID {player.get('item_id', '')}"
            )

        # ====================================================
        # FIRST SCAN
        # ====================================================

        if old_players is None:
            results.append({
                "category": category,
                "status": "first_scan",
            })

            continue

        # ====================================================
        # VERSION SAFETY
        # ====================================================

        if detect_version:
            incomplete = any(
                player.get(
                    "version"
                )
                in [
                    None,
                    "?",
                ]
                for player
                in players
            )

            if incomplete:
                results.append({
                    "category": category,
                    "status": "incomplete",
                })

                continue

        # ====================================================
        # COMPARE
        # ====================================================

        removed, added = compare_players(
            old_players,
            players,
        )

        if (
            removed
            or added
        ):
            results.append({
                "category": category,
                "status": "changed",
                "removed": removed,
                "added": added,
            })

        else:
            results.append({
                "category": category,
                "status": "unchanged",
            })

    # ========================================================
    # SAVE STATE
    # ========================================================

    save_state(
        new_state
    )

    # ========================================================
    # TELEGRAM HEADER
    # ========================================================

    has_changes = any(
        result["status"]
        == "changed"
        for result
        in results
    )

    if has_changes:
        message = (
            "⚡ <b>FUTFLEX FEED UPDATE</b>\n"
        )

    else:
        message = (
            "🤖 <b>FUTFLEX MONITOR</b>\n"
        )

    message += (
        "\n"
        "✅ Monitoring check completed\n"
        f"🕐 "
        f"{now.strftime('%d/%m/%Y %H:%M:%S')} "
        "UTC\n"
    )

    # ========================================================
    # TELEGRAM RESULTS
    # ========================================================

    for result in results:
        category = result[
            "category"
        ]

        status = result[
            "status"
        ]

        message += (
            "\n"
            "━━━━━━━━━━━━━━\n"
            f"<b>{category}</b>\n"
        )

        # ====================================================
        # CHANGED
        # ====================================================

        if status == "changed":
            removed = result[
                "removed"
            ]

            added = result[
                "added"
            ]

            # ================================================
            # GONE
            # ================================================

            for index, player in enumerate(
                removed
            ):
                if index > 0:
                    message += "\n"

                message += (
                    "\n"
                    f"{player_text(player, 'gone')}\n"
                )

            # ================================================
            # GONE / NEW SEPARATOR
            # ================================================

            if removed and added:
                message += (
                    "\n"
                    "--------------------\n"
                )

            # ================================================
            # NEW
            # ================================================

            for index, player in enumerate(
                added
            ):
                if index > 0:
                    message += "\n"

                message += (
                    "\n"
                    f"{player_text(player, 'new')}\n"
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
        # INCOMPLETE VERSION
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

    # ========================================================
    # FOOTER
    # ========================================================

    message += (
        "\n"
        "━━━━━━━━━━━━━━\n"
        "⏱ Automatic monitoring · 5 min"
    )

    send_telegram(
        message
    )

    print()
    print(
        "=" * 60
    )

    print(
        "MONITOR COMPLETED SUCCESSFULLY"
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":
    main()