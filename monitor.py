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
        "detect_version": True,
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
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception as error:
        print(f"Could not load previous state: {error}")
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("feed_state.json saved successfully.")


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
# PLAYER DATA
# ============================================================

def parse_player_alt(alt):
    if not alt:
        return None

    alt = alt.strip()

    if alt.lower() == "player card":
        return None

    match = re.match(
        r"^(.+?)\s*-\s*(\d+)\s*-\s*(.+?)$",
        alt,
    )

    if not match:
        return None

    return {
        "name": match.group(1).strip(),
        "rating": match.group(2).strip(),
        "card": match.group(3).strip(),
    }


def extract_item_id(src="", href=""):
    for value in (href, src):
        if not value:
            continue

        match = re.search(
            r"(?:/|^)27-(\d+)(?:/|\.|$)",
            value,
        )

        if match:
            return match.group(1)

    return None


# ============================================================
# LINEUP
# ============================================================

async def wait_for_lineup(page, expected_players):
    await page.wait_for_selector(
        'ul[data-gallery-builder-slots="true"]',
        timeout=30000,
    )

    locator = page.locator(
        'ul[data-gallery-builder-slots="true"] > li'
    )

    last_real = -1
    stable_rounds = 0

    for attempt in range(20):
        # Scroll down to trigger lazy-loaded slots.
        await page.mouse.wheel(0, 1500)

        count = await locator.count()

        real_cards = 0

        for index in range(min(count, expected_players)):
            slot = locator.nth(index)

            images = slot.locator("img")

            if await images.count() == 0:
                continue

            alt = (
                await images.first.get_attribute("alt")
                or ""
            )

            alt = alt.strip()

            if (
                alt
                and alt.lower() != "player card"
            ):
                real_cards += 1

        print(
            f"Rendered lineup: "
            f"{real_cards}/{expected_players} real cards"
        )

        if real_cards == expected_players:
            return True

        if real_cards == last_real:
            stable_rounds += 1
        else:
            stable_rounds = 0

        last_real = real_cards

        # Count has not changed for 4 attempts: stop waiting.
        if stable_rounds >= 4:
            return False

        await page.wait_for_timeout(1000)

    return False


async def get_rendered_slots(page, expected_players):
    locator = page.locator(
        'ul[data-gallery-builder-slots="true"] > li'
    )

    count = await locator.count()

    if count < expected_players:
        raise RuntimeError(
            f"Found {count} lineup slots instead "
            f"of {expected_players}."
        )

    slots = []

    for index in range(expected_players):
        slot = locator.nth(index)

        images = slot.locator("img")

        alt = ""
        src = ""

        if await images.count() > 0:
            image = images.first

            alt = (
                await image.get_attribute("alt")
                or ""
            )

            src = (
                await image.get_attribute("src")
                or ""
            )

        href = ""

        links = slot.locator(
            'a[href*="/players/"]'
        )

        if await links.count() > 0:
            href = (
                await links.first.get_attribute("href")
                or ""
            )

        slots.append(
            {
                "alt": alt.strip(),
                "src": src.strip(),
                "href": href.strip(),
            }
        )

    return slots


async def get_static_slots(context, url, expected_players):
    # The server-rendered HTML already contains the full lineup,
    # even when the browser-rendered page still shows placeholders.
    response = await context.request.get(
        url,
        timeout=30000,
    )

    if not response.ok:
        raise RuntimeError(
            f"Static page returned HTTP {response.status}."
        )

    text = await response.text()

    soup = BeautifulSoup(
        text,
        "html.parser",
    )

    slots = []

    for li in soup.find_all("li"):
        img = li.find("img")

        if img is None:
            continue

        alt = (img.get("alt") or "").strip()

        if parse_player_alt(alt) is None:
            continue

        src = (img.get("src") or "").strip()

        link = li.find(
            "a",
            href=re.compile(r"/players/"),
        )

        href = ""

        if link is not None:
            href = (link.get("href") or "").strip()

        if not href:
            item_id = extract_item_id(src)

            if item_id:
                other = soup.find(
                    "a",
                    href=re.compile(
                        rf"/players/.*27-{item_id}"
                    ),
                )

                if other is not None:
                    href = (other.get("href") or "").strip()

        slots.append(
            {
                "alt": alt,
                "src": src,
                "href": href,
            }
        )

        if len(slots) >= expected_players:
            break

    return slots


# ============================================================
# VERSION DETECTION
# ============================================================

async def detect_card_version(context, href):
    if not href:
        return "?"

    url = urljoin(SITE, href)

    page = await context.new_page()

    try:
        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        await page.wait_for_timeout(1500)

        content = await page.content()

        soup = BeautifulSoup(
            content,
            "html.parser",
        )

        # Only the page title and the main heading are used:
        # meta tags and page text also mention other cards.
        parts = []

        if soup.title:
            parts.append(
                soup.title.get_text(
                    " ",
                    strip=True,
                )
            )

        h1 = soup.find("h1")

        if h1:
            parts.append(
                h1.get_text(
                    " ",
                    strip=True,
                )
            )

        searchable = " ".join(parts).lower()

        if "pristine holographic" in searchable:
            return "Pristine Holographic"

        if "holographic" in searchable:
            return "Holographic"

        return "Base"

    except Exception as error:
        print(
            f"Version detection failed: {error}"
        )

        return "?"

    finally:
        await page.close()


# ============================================================
# CATEGORY SCANNER
# ============================================================

async def scan_category(context, label, config):
    page = await context.new_page()

    try:
        print()
        print("=" * 60)
        print(f"Scanning {label}")
        print(config["url"])
        print("=" * 60)

        await page.goto(
            config["url"],
            wait_until="domcontentloaded",
            timeout=45000,
        )

        # Allow FUT.GG JavaScript to start rendering.
        await page.wait_for_timeout(2000)

        await wait_for_lineup(
            page,
            config["players"],
        )

        try:
            slots = await get_rendered_slots(
                page,
                config["players"],
            )

        except Exception as error:
            print(f"Rendered slots unavailable: {error}")
            slots = []

        rendered_real = sum(
            1
            for slot in slots
            if parse_player_alt(slot["alt"]) is not None
        )

        if rendered_real < config["players"]:
            print(
                f"Rendered page has {rendered_real}/"
                f"{config['players']} cards, "
                f"trying static HTML."
            )

            try:
                static_slots = await get_static_slots(
                    context,
                    config["url"],
                    config["players"],
                )

            except Exception as error:
                print(f"Static HTML failed: {error}")
                static_slots = []

            print(
                f"Static HTML cards found: "
                f"{len(static_slots)}"
            )

            for number, static_slot in enumerate(
                static_slots,
                start=1,
            ):
                print(
                    f"  static {number}: "
                    f"{static_slot['alt']}"
                )

            if len(static_slots) > rendered_real:
                print(
                    f"Using static HTML lineup: "
                    f"{len(static_slots)} cards."
                )

                slots = static_slots

        players = []

        for slot_number, slot in enumerate(
            slots,
            start=1,
        ):
            player = parse_player_alt(
                slot["alt"]
            )

            if player is None:
                print(
                    f"Slot {slot_number}: "
                    f"empty, skipped "
                    f"(alt={slot['alt']!r}, "
                    f"src={slot['src'][-60:]!r})"
                )

                continue

            item_id = extract_item_id(
                slot["src"],
                slot["href"],
            )

            player["item_id"] = item_id

            if config["detect_version"]:
                version = await detect_card_version(
                    context,
                    slot["href"],
                )

                if (
                    label == "✨ HOLOGRAPHICS"
                    and version == "Base"
                ):
                    version = "Holographic"

                player["version"] = version

            else:
                player["version"] = "?"

            players.append(player)

            print(
                f"Slot {slot_number}: "
                f"{player['name']} | "
                f"{player['rating']} | "
                f"{player['card']} | "
                f"{player['version']} | "
                f"{player['item_id'] or '?'}"
            )

        if not players:
            raise RuntimeError(
                "No cards rendered."
            )

        print(
            f"{label}: "
            f"{len(players)}/{config['players']} "
            f"players found."
        )

        return players

    finally:
        await page.close()


# ============================================================
# PLAYER COMPARISON
# ============================================================

def player_identity(player):
    item_id = player.get("item_id")
    version = player.get("version")

    if item_id:
        return (
            str(item_id),
            str(version),
        )

    return (
        player.get("name", ""),
        player.get("rating", ""),
        player.get("card", ""),
        str(version),
    )


def compare_players(old_players, new_players):
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
        identity = player_identity(player)

        if removed_needed[identity] > 0:
            removed.append(player)
            removed_needed[identity] -= 1

    for player in new_players:
        identity = player_identity(player)

        if added_needed[identity] > 0:
            added.append(player)
            added_needed[identity] -= 1

    return removed, added


# ============================================================
# TELEGRAM FORMATTING
# ============================================================

def player_text(player, status):
    name = html.escape(
        str(player.get("name", ""))
    )

    rating = html.escape(
        str(player.get("rating", ""))
    )

    card = html.escape(
        str(player.get("card", ""))
    )

    version = player.get("version")

    if status == "new":
        status_text = "🆕 <b>NEW</b>"
    else:
        status_text = "❌ <b>GONE</b>"

    version_text = None

    if version == "Base":
        version_text = "⚪ <b>BASE</b>"

    elif version == "Holographic":
        version_text = (
            "✨ <b>HOLOGRAPHIC</b>"
        )

    elif version == "Pristine Holographic":
        version_text = (
            "✨ <b>PRISTINE HOLOGRAPHIC</b>"
        )

    elif version and version != "?":
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
        lines.append(version_text)

    lines.append(
        f"⭐ {rating} · {card}"
    )

    return "\n".join(lines)


def build_category_message(label, result):
    lines = [
        "━━━━━━━━━━━━━━",
        f"<b>{label}</b>",
    ]

    if result["error"]:
        lines.append(
            "⚠️ <b>Feed check failed</b>"
        )

        lines.append(
            html.escape(result["error"])
        )

        return "\n".join(lines)

    if result["first_scan"]:
        lines.append(
            "✓ Monitoring initialized"
        )

        return "\n".join(lines)

    removed = result["removed"]
    added = result["added"]

    if not removed and not added:
        lines.append("✓ No changes")
        return "\n".join(lines)

    if removed:
        lines.append("")

        for index, player in enumerate(removed):
            if index > 0:
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
        if not removed:
            lines.append("")

        for index, player in enumerate(added):
            if index > 0:
                lines.append("")

            lines.append(
                player_text(
                    player,
                    "new",
                )
            )

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

async def main():
    old_state = load_state()

    # Preserve previous categories if a scan fails.
    new_state = dict(old_state)

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

                previous = old_state.get(label)

                first_scan = previous is None

                removed = []
                added = []

                if not first_scan:
                    removed, added = compare_players(
                        previous,
                        players,
                    )

                if removed or added:
                    any_changes = True

                results[label] = {
                    "error": None,
                    "first_scan": first_scan,
                    "removed": removed,
                    "added": added,
                }

                new_state[label] = players

            except Exception as error:
                print(
                    f"{label} failed: {error}"
                )

                results[label] = {
                    "error": str(error),
                    "first_scan": False,
                    "removed": [],
                    "added": [],
                }

                # Do not overwrite this category in the state.

        await context.close()
        await browser.close()

    save_state(new_state)

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

    message_parts.extend(
        [
            "━━━━━━━━━━━━━━",
            "⏱ Automatic monitoring · 5 min",
        ]
    )

    message = "\n".join(
        message_parts
    )

    send_telegram(message)


if __name__ == "__main__":
    asyncio.run(main())
