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

    print(
        "Telegram notification sent successfully."
    )


# ============================================================
# EXTRACT ITEM ID
# ============================================================

def extract_item_id(img):
    """
    Extract the exact FC item ID from the image URL.
    """

    values = []

    for attribute in [
        "src",
        "data-src",
        "srcset",
        "data-srcset",
    ]:
        value = img.get(
            attribute,
            "",
        )

        if value:
            values.append(
                value
            )

    combined = " ".join(
        values
    )

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
    Search only around the current card image.

    This avoids accidentally using the link from another
    copy of the same player.
    """

    pattern = re.compile(
        rf"/players/[^\"']*27-{re.escape(item_id)}"
    )

    # First check if the image itself is inside a link.

    parent_link = img.find_parent(
        "a"
    )

    if parent_link:
        href = parent_link.get(
            "href",
            "",
        )

        if pattern.search(
            href
        ):
            return href

    # Search only in nearby parents.

    parent = img

    for _ in range(6):
        parent = parent.parent

        if parent is None:
            break

        if not hasattr(
            parent,
            "find_all",
        ):
            continue

        links = parent.find_all(
            "a",
            href=True,
        )

        for link in links:
            href = link.get(
                "href",
                "",
            )

            if pattern.search(
                href
            ):
                return href

    return None


# ============================================================
# CARD VERSION
# ============================================================

def get_version(
    item_url,
):
    """
    Detect Base / Holographic / Pristine Holographic
    from the exact FUT.GG card page.
    """

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

    # Prefer the H1.

    h1 = soup.find(
        "h1"
    )

    if h1:
        title = h1.get_text(
            " ",
            strip=True,
        )

    else:
        title_tag = soup.find(
            "title"
        )

        if not title_tag:
            raise Exception(
                f"Card title not found: {item_url}"
            )

        title = title_tag.get_text(
            " ",
            strip=True,
        )

    print(
        f"Card page: {item_url}"
    )

    print(
        f"Card title: {title}"
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
# GET LINEUP IMAGES
# ============================================================

def get_lineup_images(
    soup,
    expected_players,
):
    """
    Get every player image exactly once.

    IMPORTANT:
    The old parser repeatedly called find_all() while walking
    through nested HTML elements. That could add the same card
    more than once.

    This function processes each actual <img> element only once.
    """

    heading = soup.find(
        lambda tag:
        tag.name in [
            "h2",
            "h3",
        ]
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

    seen_elements = set()

    current = heading.next_element

    while current:

        # Stop when reaching the next heading.

        if (
            getattr(
                current,
                "name",
                None,
            )
            in [
                "h2",
                "h3",
            ]
            and current is not heading
        ):
            break

        # Process ONLY the current IMG itself.
        # Do not call current.find_all("img").

        if (
            getattr(
                current,
                "name",
                None,
            )
            == "img"
        ):
            alt = current.get(
                "alt",
                "",
            ).strip()

            match = re.match(
                r"(.+?)\s*-\s*(\d+)\s*-\s*(.+)",
                alt,
            )

            if match:
                element_id = id(
                    current
                )

                if (
                    element_id
                    not in seen_elements
                ):
                    seen_elements.add(
                        element_id
                    )

                    images.append(
                        current
                    )

                    if (
                        len(images)
                        >= expected_players
                    ):
                        break

        current = current.next_element

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
    # PROCESS EACH SLOT ONCE
    # ========================================================

    for slot_number, img in enumerate(
        images,
        start=1,
    ):
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
            "name": (
                match.group(1).strip()
            ),
            "rating": (
                match.group(2).strip()
            ),
            "card": (
                match.group(3).strip()
            ),
        }

        print()
        print(
            f"SLOT {slot_number}"
        )

        print(
            f"Player: {player['name']}"
        )

        print(
            f"Rating: {player['rating']}"
        )

        print(
            f"Card: {player['card']}"
        )

        # ====================================================
        # CARD VERSION
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
                    player[
                        "version"
                    ] = known_versions[
                        item_id
                    ]

                    print(
                        "Version: "
                        f"{player['version']} "
                        "(cached)"
                    )

                # ============================================
                # NEW ITEM
                # ============================================

                else:
                    href = find_exact_card_link(
                        img,
                        item_id,
                    )

                    if href:
                        item_url = urljoin(
                            SITE,
                            href,
                        )

                        try:
                            version = get_version(
                                item_url
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
                            "Exact card link "
                            "not found."
                        )

                        player[
                            "version"
                        ] = "?"

            else:
                print(
                    "Item ID not found."
                )

                player[
                    "version"
                ] = "?"

        players.append(
            player
        )

    if (
        len(players)
        != expected_players
    ):
        raise Exception(
            f"Parsed {len(players)} players "
            f"instead of {expected_players}"
        )

    return players


# ============================================================
# PLAYER IDENTITY
# ============================================================

def player_identity(
    player,
):
    """
    Identity used when comparing two scans.

    Item ID is important because two cards may have:
    - same player
    - same rating
    - same rarity

    but one can be Base and another Holographic.
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
        player.get(
            "name",
            ""
        ),
        player.get(
            "rating",
            ""
        ),
        player.get(
            "card",
            ""
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
    Counter-based comparison.

    This is important because FUT.GG can legitimately contain
    multiple copies of the same player.
    """

    old_counter = Counter(
        player_identity(
            player
        )
        for player in old_players
    )

    new_counter = Counter(
        player_identity(
            player
        )
        for player in new_players
    )

    removed_needed = (
        old_counter
        - new_counter
    )

    added_needed = (
        new_counter
        - old_counter
    )

    removed = []
    added = []

    # Preserve the original display order.

    for player in old_players:
        identity = player_identity(
            player
        )

        if (
            removed_needed[
                identity
            ]
            > 0
        ):
            removed.append(
                player
            )

            removed_needed[
                identity
            ] -= 1

    for player in new_players:
        identity = player_identity(
            player
        )

        if (
            added_needed[
                identity
            ]
            > 0
        ):
            added.append(
                player
            )

            added_needed[
                identity
            ] -= 1

    return (
        removed,
        added,
    )


# ============================================================
# TELEGRAM PLAYER FORMAT
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
            str(
                version
            ).upper()
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
            f"state: {error}"
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
        # LOAD SAVED VERSIONS
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
        # DOWNLOAD CURRENT FEED
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

        new_state[
            category
        ] = players

        # ====================================================
        # PRINT RESULT
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
            version = player.get(
                "version",
                "",
            )

            item_id = player.get(
                "item_id",
                "",
            )

            print(
                f"{index}. "
                f"{player['name']} | "
                f"{player['rating']} | "
                f"{player['card']} | "
                f"{version} | "
                f"ID {item_id}"
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
        # CHECK VERSION DATA
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
                for player in players
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
        result[
            "status"
        ] == "changed"
        for result in results
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
    # TELEGRAM FEEDS
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
            # SEPARATOR
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
        # INCOMPLETE
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
                result[
                    "error"
                ]
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

    # ========================================================
    # SEND TELEGRAM
    # ========================================================

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