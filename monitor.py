import os
import re
import json
import html
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup


# ============================================================
# FUT.GG FEEDS
# ============================================================

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


# ============================================================
# TELEGRAM
# ============================================================

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


# ============================================================
# SETTINGS
# ============================================================

STATE_FILE = "players.json"

# Maximum number of cards for the same player name.
#
# Example:
#
# Cucurella - 88 - Destined for Glory
# Cucurella - 88 - Pristine Holographic
#
# = allowed
#
# Three Cucurella cards
# = third one ignored
#
MAX_SAME_PLAYER = 2


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(value):

    if not value:
        return ""

    value = html.unescape(str(value))

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# ============================================================
# PARSE PLAYER FROM ALT
# ============================================================

def parse_alt(alt):

    alt = normalize_text(alt)

    if not alt:
        return None

    # FUT.GG format:
    #
    # Player - 88 - Card
    #
    match = re.match(
        r"^(.+?)\s*-\s*(\d+)\s*-\s*(.+?)$",
        alt
    )

    if not match:
        return None

    return {
        "name": normalize_text(
            match.group(1)
        ),
        "rating": match.group(2),
        "card": normalize_text(
            match.group(3)
        )
    }


# ============================================================
# GET CARD CONTEXT
# ============================================================

def get_card_context(img):

    """
    FUT.GG can render several images/elements for the
    same card.

    We collect useful information from:
      - image attributes
      - parent link
      - surrounding element
      - data-* attributes

    This gives us a more stable identity for a card.
    """

    data = {}

    # Image attributes
    for key, value in img.attrs.items():

        if value is None:
            continue

        data[key] = str(value)


    # Parent link
    link = img.find_parent("a")

    if link:

        if link.get("href"):
            data["href"] = str(
                link.get("href")
            )

        for key, value in link.attrs.items():

            if value is None:
                continue

            data[f"link_{key}"] = str(value)


    # Parent element
    parent = img.parent

    if parent:

        for key, value in parent.attrs.items():

            if value is None:
                continue

            data[f"parent_{key}"] = str(value)


    return data


# ============================================================
# CARD UNIQUE KEY
# ============================================================

def make_card_key(player, context):

    """
    Primary identity:

        name + rating + card

    This prevents the same FUT.GG image/card from being
    counted multiple times.

    If FUT.GG provides a unique URL/ID, it is also included
    so different variants can be distinguished.
    """

    name = player["name"].lower()
    rating = player["rating"].lower()
    card = player["card"].lower()

    href = context.get("href", "")

    # Normalize URL
    href = href.split("?")[0].lower()

    # Important:
    # If the same exact player/card appears with a different
    # FUT.GG link, keep the link as additional identity.
    #
    # But if there is no useful href, the normal card identity
    # is enough.

    return (
        name,
        rating,
        card,
        href
    )


# ============================================================
# GET FUT.GG PLAYERS
# ============================================================

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


    # ========================================================
    # FIND CHEAPEST LINEUP
    # ========================================================

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


    # ========================================================
    # RESULTS
    # ========================================================

    players = []

    # Exact cards already collected
    seen_cards = set()

    # Count by player name
    player_counts = {}


    # ========================================================
    # WALK THROUGH LINEUP
    # ========================================================

    current = heading.find_next()


    while current:

        # Stop at the next major section
        if (
            current.name in ["h2", "h3"]
            and current != heading
        ):
            break


        if hasattr(current, "find_all"):

            images = current.find_all("img")


            for img in images:

                alt = normalize_text(
                    img.get("alt", "")
                )


                # Ignore placeholder cards
                if (
                    not alt
                    or alt.lower() == "player card"
                ):
                    continue


                # Parse player
                player = parse_alt(alt)


                if not player:
                    continue


                # Get additional HTML context
                context = get_card_context(img)


                # =================================================
                # PLAYER NAME LIMIT
                # =================================================

                name_key = (
                    player["name"]
                    .strip()
                    .lower()
                )

                current_count = player_counts.get(
                    name_key,
                    0
                )


                # Maximum 2 versions for same player
                if current_count >= MAX_SAME_PLAYER:

                    print(
                        f"Skipped third version: "
                        f"{player['name']} "
                        f"{player['rating']} "
                        f"{player['card']}"
                    )

                    continue


                # =================================================
                # DUPLICATE CARD CHECK
                # =================================================

                card_key = make_card_key(
                    player,
                    context
                )


                if card_key in seen_cards:

                    print(
                        f"Skipped duplicate: "
                        f"{player['name']} "
                        f"{player['rating']} "
                        f"{player['card']}"
                    )

                    continue


                # =================================================
                # SAVE CARD
                # =================================================

                player["source"] = url

                # Keep useful identity data.
                #
                # These fields don't affect Telegram output,
                # but they allow us to distinguish variants
                # later if FUT.GG provides them.
                #
                if context.get("href"):
                    player["href"] = context["href"]


                players.append(player)

                seen_cards.add(
                    card_key
                )

                player_counts[name_key] = (
                    current_count + 1
                )


                print(
                    f"Accepted: "
                    f"{player['name']} "
                    f"{player['rating']} "
                    f"{player['card']}"
                )


                # =================================================
                # STOP ONLY WHEN WE HAVE ENOUGH UNIQUE CARDS
                # =================================================

                if len(players) >= expected_players:

                    return players


        current = current.find_next()


    # ========================================================
    # RETURN WHAT WAS FOUND
    # ========================================================

    if players:

        return players


    raise Exception(
        f"Found 0 players on {url}"
    )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    telegram_url = (
        "https://api.telegram.org/"
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


    print(
        "Telegram notification sent successfully."
    )


# ============================================================
# PLAYER TEXT
# ============================================================

def player_text(player):

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
        f"<b>{name}</b> — "
        f"{rating} — "
        f"{card}"
    )


# ============================================================
# REMOVE INTERNAL FIELDS BEFORE SAVE
# ============================================================

def clean_player(player):

    return {
        "name": player["name"],
        "rating": player["rating"],
        "card": player["card"]
    }


# ============================================================
# MAIN
# ============================================================

def main():

    # ========================================================
    # LOAD OLD STATE
    # ========================================================

    if os.path.exists(STATE_FILE):

        try:

            with open(
                STATE_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                old_state = json.load(file)

        except Exception as error:

            print(
                f"Could not read {STATE_FILE}: "
                f"{error}"
            )

            old_state = {}

    else:

        old_state = {}


    # Keep previous data if a feed fails
    new_state = dict(old_state)

    results = []

    any_changes = False


    # ========================================================
    # CHECK ALL FEEDS
    # ========================================================

    for category, config in PAGES.items():

        url = config["url"]

        expected_players = config["players"]


        print("")
        print("=" * 60)

        print(
            f"Checking {category} "
            f"({expected_players} players)..."
        )

        print("=" * 60)


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


        # ====================================================
        # CLEAN DATA
        # ====================================================

        clean_players = [
            clean_player(player)
            for player in players
        ]


        print("")
        print(
            f"Found {len(clean_players)} unique players."
        )


        for player in clean_players:

            print(
                f"- {player['name']} "
                f"{player['rating']} "
                f"{player['card']}"
            )


        # Save current feed
        new_state[category] = clean_players


        # ====================================================
        # FIRST SCAN
        # ====================================================

        old_players = old_state.get(
            category
        )


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


        # ====================================================
        # COMPARE OLD VS NEW
        # ====================================================

        removed = old_players.copy()

        added = clean_players.copy()


        # Remove matching cards one by one.
        #
        # This means:
        #
        # old:
        # Cucurella Base
        #
        # new:
        # Cucurella Base
        # Cucurella Holographic
        #
        # => only Holographic is NEW
        #

        for player in old_players:

            if player in added:

                added.remove(player)


                if player in removed:

                    removed.remove(player)


        # ====================================================
        # NO CHANGE
        # ====================================================

        if not removed and not added:

            print(
                f"{category}: No feed changes."
            )


            results.append({
                "category": category,
                "status": "unchanged"
            })


            continue


        # ====================================================
        # CHANGED
        # ====================================================

        any_changes = True


        results.append({
            "category": category,
            "status": "changed",
            "removed": removed,
            "added": added
        })


    # ========================================================
    # SAVE STATE
    # ========================================================

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


    print("")
    print(
        "Feed state saved successfully."
    )


    # ========================================================
    # TELEGRAM HEADER
    # ========================================================

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%d/%m/%Y %H:%M:%S UTC"
    )


    if any_changes:

        header = (
            "⚡ <b>FUTFLEX FEED UPDATE</b>"
        )

    else:

        header = (
            "🤖 <b>FUTFLEX MONITOR</b>"
        )


    parts = [
        header,
        "",
        "✅ Monitoring check completed",
        f"🕐 {now}",
        ""
    ]


    # ========================================================
    # TELEGRAM RESULTS
    # ========================================================

    for result in results:

        category = html.escape(
            result["category"]
        )


        parts.append(
            "━━━━━━━━━━━━━━"
        )

        parts.append(
            f"<b>{category}</b>"
        )


        status = result["status"]


        # ----------------------------------------------------
        # CHANGED
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # UNCHANGED
        # ----------------------------------------------------

        elif status == "unchanged":

            parts.append(
                "✓ No changes"
            )


        # ----------------------------------------------------
        # FIRST SCAN
        # ----------------------------------------------------

        elif status == "first_scan":

            parts.append(
                "✓ Monitoring initialized"
            )


        # ----------------------------------------------------
        # ERROR
        # ----------------------------------------------------

        elif status == "error":

            parts.append(
                "⚠️ <b>Feed check failed</b>"
            )

            parts.append(
                html.escape(
                    result["error"]
                )
            )


        parts.append("")


    # ========================================================
    # FOOTER
    # ========================================================

    parts.append(
        "━━━━━━━━━━━━━━"
    )

    parts.append(
        "⏱ Automatic monitoring · 5 min"
    )


    # ========================================================
    # SEND
    # ========================================================

    send_telegram(
        "\n".join(parts)
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()