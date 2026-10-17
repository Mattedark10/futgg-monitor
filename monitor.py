import asyncio
import html
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "feed_state.json"
SITE = "https://www.fut.gg"

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
# STATE
# ============================================================

def load_state():
    if not os.path.exists(STATE_FILE):
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
            f"Could not load previous state: {error}"
        )
        return {}


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


# ============================================================
# PLAYER PARSING
# ============================================================

def parse_player_alt(alt):
    match = re.match(
        r"^(.+?)\s*-\s*(\d+)\s*-\s*(.+?)$",
        alt.strip(),
    )

    if not match:
        return None

    return {
        "name": match.group(1).strip(),
        "rating": match.group(2).strip(),
        "card": match.group(3).strip(),
    }


def extract_item_id(src, href=""):
    values = [
        src or "",
        href or "",
    ]

    patterns = [
        r"/27-(\d+)",
        r"27-(\d+)",
    ]

    for value in values:
        for pattern in patterns:
            match = re.search(
                pattern,
                value,
            )

            if match:
                return match.group(1)

    return None


# ============================================================
# VERSION DETECTION
# ============================================================

async def detect_card_version(
    context,
    href,
):
    if not href:
        return "?"

    url = urljoin(
        SITE,
        href,
    )

    page = await context.new_page()

    try:
        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        try:
            await page.wait_for_load_state(
                "networkidle",
                timeout=8000,
            )
        except Exception:
            pass

        content = await page.content()

        soup = BeautifulSoup(
            content,
            "html.parser",
        )

        searchable_parts = []

        if soup.title:
            searchable_parts.append(
                soup.title.get_text(
                    " ",
                    strip=True,
                )
            )

        h1 = soup.find("h1")

        if h1:
            searchable_parts.append(
                h1.get_text(
                    " ",
                    strip=True,
                )
            )

        for meta in soup.find_all("meta"):
            meta_content = meta.get(
                "content",
                "",
            )

            if meta_content:
                searchable_parts.append(
                    meta_content
                )

        # Page text is included as a fallback because FUT.GG can
        # expose the cosmetic information outside the title.
        searchable_parts.append(
            soup.get_text(
                " ",
                strip=True,
            )[:50000]
        )

        searchable = " ".join(
            searchable_parts
        ).lower()

        if (
            "pristine holographic"
            in searchable
        ):
            return "Pristine Holographic"

        if "holographic" in searchable:
            return "Holographic"

        return "Base"

    except Exception as error:
        print(
            f"Version detection failed for "
            f"{url}: {error}"
        )
        return "?"

    finally:
        await page.close()


# ============================================================
# FUT.GG LINEUP
# ============================================================

async def wait_for_lineup(
    page,
    expected_players,
):
    """
    Wait until FUT.GG has rendered the expected number of
    Gallery Builder slots and as many real player cards as
    possible.
    """

    await page.wait_for_selector(
        'ul[data-gallery-builder-slots="true"]',
        timeout=30000,
    )

    # Give FUT.GG's client-side requests time to replace
    # placeholder cards.
    for attempt in range(20):
        data = await page.locator(
            'ul[data-gallery-builder-slots="true"] > li'
        ).evaluate_all(
            """
            (slots) => slots.map((slot) => {
                const img = slot.querySelector("img");

                return {
                    alt: img?.getAttribute("alt") || "",
                    src: img?.getAttribute("src") || "",
                    html: slot.innerHTML
                };
            })
            """
        )

        if len(data) >= expected_players:
            first_slots = data[
                :expected_players
            ]

            real_cards = sum(
                1
                for slot in first_slots
                if slot["alt"]
                and slot["alt"].toLowerCase()
                != "player card"
            )

            print(
                f"Rendered lineup: "
                f"{real_cards}/"
                f"{expected_players} real cards"
            )

            if real_cards == expected_players:
                return

        await page.wait_for_timeout(
            1000
        )

    print(
        "FUT.GG still has placeholder cards "
        "after waiting."
    )


async def get_rendered_slots(
    page,
    expected_players,
):
    locator = page.locator(
        'ul[data-gallery-builder-slots="true"] > li'
    )

    count = await locator.count()

    if count < expected_players:
        raise Exception(
            f"Found {count} lineup slots instead "
            f"of {expected_players}."
        )

    slots = []

    for index in range(
        expected_players
    ):
        slot = locator.nth(index)

        data = await slot.evaluate(
            """
            (slot) => {
                const img =
                    slot.querySelector("img");

                const links = Array.from(
                    slot.querySelectorAll("a[href]")
                );

                const playerLink =
                    links.find((a) =>
                        a.getAttribute("href")
                            ?.includes("/players/")
                    );

                return {
                    alt:
                        img?.getAttribute("alt")
                        || "",

                    src:
                        img?.getAttribute("src")
                        || "",

                    href:
                        playerLink
                            ?.getAttribute("href")
                        || "",

                    text:
                        slot.innerText || ""
                };
            }
            """
        )

        slots.append(data)

    return slots


async def scan_category(
    context,
    label,
    config,
):
    page = await context.new_page()

    try:
        print()
        print(
            f"Scanning {label}"
        )
        print(
            config["url"]
        )

        await page.goto(
            config["url"],
            wait_until="domcontentloaded",
            timeout=45000,
        )

        try:
            await page.wait_for_load_state(
                "networkidle",
                timeout=10000,
            )
        except Exception:
            # Some sites keep background connections open.
            pass

        await wait_for_lineup(
            page,
            config["players"],
        )

        slots = await get_rendered_slots(
            page,
            config["players"],
        )

        players = []

        for number, slot in enumerate(
            slots,
            start=1,
        ):
            alt = slot["alt"].strip()
            src = slot["src"].strip()
            href = slot["href"].strip()

            player = parse_player_alt(
                alt
            )

            if not player:
                raise Exception(
                    f"Slot {number} is still a "
                    f"placeholder after JavaScript "
                    f"rendering."
                )

            item_id = extract_item_id(
                src,
                href,
            )

            player["item_id"] = item_id

            if (
                label
                == "✨ HOLOGRAPHICS"
            ):
                # Every card in this Gallery set is
                # Holographic by definition. The exact
                # Regular/Pristine type is detected below
                # only when the player page exposes it.
                version = (
                    await detect_card_version(
                        context,
                        href,
                    )
                    if href
                    else "Holographic"
                )

                if version == "Base":
                    version = "Holographic"

                player["version"] = version

            elif config[
                "detect_version"
            ]:
                player["version"] = (
                    await detect_card_version(
                        context,
                        href,
                    )
                )

            else:
                player["version"] = "?"

            players.append(
                player
            )

            print(
                f"Slot {number}: "
                f"{player['name']} | "
                f"{player['rating']} | "
                f"{player['card']} | "
                f"{player['version']} | "
                f"{player['item_id']}"
            )

        if (
            len(players)
            != config["players"]
        ):
            raise Exception(
                f"Found {len(players)} players "
                f"instead of "
                f"{config['players']}."
            )

        return players

    finally:
        await page.close()


# ============================================================
# COMPARISON
# ============================================================

def player_identity(player):
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
            "",
        ),
        player.get(
            "rating",
            "",
        ),
        player.get(
            "card",
            "",
        ),
        str(version),
    )


def compare_players(
    old_players,
    new_players,
):
    old_counter = Counter(
        player_identity(player)
        for player in old_players
    )

    new_counter = Counter(
        player_identity(player)
        for player in new_players
    )

    removed_needed = (
        old_counter - new_counter
    )

    added_needed = (
        new_counter - old_counter
    )

    removed = []
    added = []

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

    return removed, added


# ============================================================
# TELEGRAM FORMATTING
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

    if status == "new":
        status_text = (
            "🆕 <b>NEW</b>"
        )
    else:
        status_text = (
            "❌ <b>GONE</b>"
        )

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
            "✨ <b>PRISTINE "
            "HOLOGRAPHIC</b>"
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


def build_category_message(
    label,
    result,
):
    lines = [
        "━━━━━━━━━━━━━━",
        f"<b>{label}</b>",
    ]

    if result["error"]:
        lines.append(
            "⚠️ <b>Feed check failed</b>"
        )

        lines.append(
            html.escape(
                result["error"]
            )
        )

        return "\n".join(
            lines
        )

    if result["first_scan"]:
        lines.append(
            "✓ Monitoring initialized"
        )

        return "\n".join(
            lines
        )

    removed = result[
        "removed"
    ]

    added = result[
        "added"
    ]

    if (
        not removed
        and not added
    ):
        lines.append(
            "✓ No changes"
        )

        return "\n".join(
            lines
        )

    if removed:
        lines.append("")

        for index, player in enumerate(
            removed
        ):
            if index:
                lines.append("")

            lines.append(
                player_text(
                    player,
                    "gone",
                )
            )

    if removed and added:
        lines.extend(
            [
                "",
                "--------------------",
                "",
            ]
        )

    if added:
        if (
            not removed
        ):
            lines.append("")

        for index, player in enumerate(
            added
        ):
            if index:
                lines.append("")

            lines.append(
                player_text(
                    player,
                    "new",
                )
            )

    return "\n".join(
        lines
    )


# ============================================================
# MAIN
# ============================================================

async def main():
    old_state = load_state()

    new_state = dict(
        old_state
    )

    results = {}

    any_changes = False

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 "
                "Safari/537.36"
            ),
            locale="en-US",
            viewport={
                "width": 1440,
                "height": 1200,
            },
        )

        for label, config in PAGES.items():
            try:
                players = await scan_category(
                    context,
                    label,
                    config,
                )

                previous = old_state.get(
                    label
                )

                first_scan = (
                    previous is None
                )

                removed = []
                added = []

                if not first_scan:
                    removed, added = (
                        compare_players(
                            previous,
                            players,
                        )
                    )

                if removed or added:
                    any_changes = True

                results[label] = {
                    "error": None,
                    "first_scan": first_scan,
                    "removed": removed,
                    "added": added,
                }

                # Only replace the category state after a
                # complete and valid scan.
                new_state[label] = players

            except Exception as error:
                print(
                    f"{label} failed: "
                    f"{error}"
                )

                results[label] = {
                    "error": str(error),
                    "first_scan": False,
                    "removed": [],
                    "added": [],
                }

                # Previous state is intentionally preserved.

        await context.close()
        await browser.close()

    save_state(
        new_state
    )

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

    message_parts = [
        header,
        "",
        "✅ Monitoring check completed",
        f"🕐 {now}",
        "",
    ]

    for label in PAGES:
        message_parts.append(
            build_category_message(
                label,
                results[label],
            )
        )

        message_parts.append("")

    message_parts.append(
        "━━━━━━━━━━━━━━"
    )

    message_parts.append(
        "⏱ Automatic monitoring · 5 min"
    )

    message = "\n".join(
        message_parts
    )

    send_telegram(
        message
    )


if __name__ == "__main__":
    asyncio.run(
        main()
                )
