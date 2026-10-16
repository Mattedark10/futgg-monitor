import csv
import io
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


# ============================================================
# CONFIG
# ============================================================

SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    "LakshmiKanth11/EA_FC_ANALYSIS/main/"
    "EA_FC_PLAYERS_DATASET_AND_%20DASHBOARD/data/players.csv"
)

OUTPUT = "docs/players.json"

# Optional:
# If FUTGG_API_KEY is available, the script will try to download
# the real FC27 Ultimate Team card catalogue.
#
# The API documented publicly exposes:
# - card_id
# - card_image_url
# - card_type
# - rating
# - position
# - club
# - league
# - nation
# - price
#
# and returns 30 cards per page.
FUTGG_API_URL = "https://api.parse.bot/v1/fut-gg/list_players"

FUTGG_API_KEY = os.getenv("FUTGG_API_KEY", "").strip()

FUTGG_PLATFORM = os.getenv("FUTGG_PLATFORM", "ps").strip().lower()

# Safety limit.
# FUT.GG's catalogue can contain hundreds of pages.
# Set to 0 to download every available page.
MAX_CARD_PAGES = int(os.getenv("FUTGG_MAX_PAGES", "0"))

REQUEST_TIMEOUT = 120


# ============================================================
# GENERIC HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""

    return str(value).strip()


def number(value):
    value = clean(value)

    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0


def normalize_name(value):
    value = clean(value).lower()

    replacements = {
        "á": "a",
        "à": "a",
        "ä": "a",
        "â": "a",
        "ã": "a",
        "å": "a",
        "é": "e",
        "è": "e",
        "ë": "e",
        "ê": "e",
        "í": "i",
        "ì": "i",
        "ï": "i",
        "î": "i",
        "ó": "o",
        "ò": "o",
        "ö": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ù": "u",
        "ü": "u",
        "û": "u",
        "ñ": "n",
        "ç": "c",
        "š": "s",
        "ž": "z",
        "ý": "y",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    return " ".join(value.split())


def parse_price(value):
    """
    Converts prices such as:

        125000
        "125K"
        "1.5M"
        "1.2m"

    into integer coins.
    """

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return int(value)

    text = clean(value).replace(",", "").replace(" ", "")

    if not text:
        return None

    try:
        return int(float(text))
    except ValueError:
        pass

    multiplier = 1

    if text.upper().endswith("K"):
        multiplier = 1_000
        text = text[:-1]

    elif text.upper().endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]

    try:
        return int(float(text) * multiplier)
    except ValueError:
        return None


# ============================================================
# HTTP
# ============================================================

def http_json(url, headers=None, timeout=REQUEST_TIMEOUT):
    request = urllib.request.Request(
        url,
        headers=headers or {
            "User-Agent": "Mozilla/5.0 FutFlex/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()

    if not data:
        raise RuntimeError(f"Empty response from {url}")

    return json.loads(data.decode("utf-8"))


# ============================================================
# EA CSV
# ============================================================

def make_base_player(row):
    first = clean(row.get("first_name"))
    last = clean(row.get("last_name"))
    common = clean(row.get("common_name"))

    name = common or f"{first} {last}".strip()

    return {
        "eaId": clean(row.get("player_id")),
        "name": name,
        "rating": number(row.get("overall_rating")),
        "position": clean(row.get("position")),
        "alternatePositions": clean(row.get("alternate_positions")),
        "club": clean(row.get("club")),
        "league": clean(row.get("league")),
        "nationality": clean(row.get("nationality")),
        "gender": clean(row.get("gender")),
        "preferredFoot": clean(row.get("preferred_foot")),
        "skillMoves": number(row.get("skill_moves")),
        "weakFoot": number(row.get("weak_foot")),
        "height": number(row.get("height_cm")),
        "weight": number(row.get("weight_kg")),

        "playstyles": [
            x.strip()
            for x in clean(row.get("playstyles")).split(",")
            if x.strip()
        ],

        "pace": number(row.get("pace")),
        "shooting": number(row.get("shooting")),
        "passing": number(row.get("passing")),
        "dribbling": number(row.get("dribbling")),
        "defending": number(row.get("defending")),
        "physicality": number(row.get("physicality")),

        "edition": clean(row.get("edition")),
        "snapshotDate": clean(row.get("snapshot_date")),

        "price": None,
        "priceChange": 0,

        # Existing headshot field.
        "image": None,

        # New full-card fields.
        "cardId": "",
        "cardType": "",
        "cardImage": "",
        "cardImageLarge": "",

        # Useful metadata.
        "isSpecial": False,
        "source": "ea_dataset"
    }


def download_csv():
    print("Downloading EA FC27 dataset...")

    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 FutFlex/1.0"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=REQUEST_TIMEOUT
    ) as response:
        data = response.read()

    if not data:
        raise RuntimeError("Downloaded CSV is empty.")

    print(f"Downloaded {len(data):,} bytes.")

    return data.decode("utf-8-sig")


def load_ea_players():
    csv_text = download_csv()

    reader = csv.DictReader(io.StringIO(csv_text))

    players = []
    seen = set()

    for row in reader:
        player = make_base_player(row)

        ea_id = player["eaId"]

        if not ea_id:
            continue

        if ea_id in seen:
            continue

        seen.add(ea_id)
        players.append(player)

    if len(players) < 1000:
        raise RuntimeError(
            f"Only {len(players)} EA players found. "
            "The database was not written."
        )

    players.sort(
        key=lambda player: (
            -player["rating"],
            player["name"].lower()
        )
    )

    print(f"EA dataset players: {len(players):,}")

    return players


# ============================================================
# FUT.GG CARD CATALOGUE
# ============================================================

def futgg_headers():
    if not FUTGG_API_KEY:
        return None

    return {
        "User-Agent": "FutFlex/1.0",
        "Accept": "application/json",
        "X-API-Key": FUTGG_API_KEY
    }


def build_futgg_url(page):
    separator = "&" if "?" in FUTGG_API_URL else "?"

    return (
        f"{FUTGG_API_URL}"
        f"{separator}page={page}"
        f"&platform={FUTGG_PLATFORM}"
    )


def normalize_card(card):
    if not isinstance(card, dict):
        return None

    card_id = clean(
        card.get("card_id")
        or card.get("cardId")
        or card.get("id")
    )

    name = clean(card.get("name"))

    if not card_id or not name:
        return None

    rating = number(
        card.get("rating")
        or card.get("overall_rating")
    )

    position = clean(card.get("position"))

    alternate_positions = card.get(
        "alternatePositions",
        card.get("alternate_positions", [])
    )

    if isinstance(alternate_positions, list):
        alternate_positions = [
            clean(
                item.get("shortLabel")
                if isinstance(item, dict)
                else item
            )
            for item in alternate_positions
        ]

    elif alternate_positions is None:
        alternate_positions = []

    else:
        alternate_positions = [
            x.strip()
            for x in str(alternate_positions).split(",")
            if x.strip()
        ]

    club = clean(card.get("club"))
    league = clean(card.get("league"))

    nation = clean(
        card.get("nation")
        or card.get("nationality")
    )

    card_type = clean(
        card.get("card_type")
        or card.get("cardType")
        or card.get("version")
        or card.get("rarity")
    )

    card_image = clean(
        card.get("card_image_url")
        or card.get("cardImage")
        or card.get("card_image")
    )

    card_image_large = clean(
        card.get("card_image_large_url")
        or card.get("cardImageLarge")
        or card.get("card_image_large")
        or card_image
    )

    headshot = clean(
        card.get("image_large")
        or card.get("image")
        or card.get("image_url")
    )

    price = parse_price(
        card.get("price")
        or card.get("price_ps_coins")
        or card.get("price_ps")
    )

    trend = card.get(
        "trend_ps",
        card.get("priceChange", 0)
    )

    try:
        trend = float(trend)
    except (ValueError, TypeError):
        trend = 0

    is_special = bool(
        card.get("is_special")
        or card.get("isSpecial")
    )

    return {
        "cardId": card_id,
        "eaId": clean(
            card.get("player_id")
            or card.get("eaId")
            or card.get("playerId")
        ),
        "name": name,
        "rating": rating,
        "position": position,
        "alternatePositions": alternate_positions,
        "club": club,
        "league": league,
        "nationality": nation,

        "cardType": card_type,
        "isSpecial": is_special,

        "image": headshot,
        "cardImage": card_image,
        "cardImageLarge": card_image_large,

        "price": price,
        "priceChange": trend,

        "skillMoves": number(card.get("skill_moves")),
        "weakFoot": number(card.get("weak_foot")),

        "source": "futgg"
    }


def download_futgg_cards():
    if not FUTGG_API_KEY:
        print()
        print("FUTGG_API_KEY not configured.")
        print(
            "Skipping FUT.GG card catalogue and "
            "keeping EA dataset as fallback."
        )
        return []

    print()
    print("Downloading FC27 Ultimate Team card catalogue...")
    print(f"Platform: {FUTGG_PLATFORM}")

    cards = []

    page = 1

    while True:
        if MAX_CARD_PAGES > 0 and page > MAX_CARD_PAGES:
            print(
                f"Reached FUTGG_MAX_PAGES={MAX_CARD_PAGES}."
            )
            break

        url = build_futgg_url(page)

        print(f"Downloading card page {page}...")

        try:
            payload = http_json(
                url,
                headers=futgg_headers()
            )

        except urllib.error.HTTPError as error:
            if error.code == 429:
                print(
                    "FUT.GG API rate limit reached (429)."
                )
                break

            if error.code in (401, 403):
                print(
                    "FUT.GG API authentication failed."
                )
                break

            raise

        except Exception as error:
            print(
                f"Could not download FUT.GG page {page}: "
                f"{error}"
            )
            break

        page_cards = (
            payload.get("players")
            or payload.get("results")
            or payload.get("data")
            or []
        )

        if isinstance(payload.get("data"), dict):
            page_cards = (
                payload["data"].get("players")
                or payload["data"].get("results")
                or []
            )

        if not page_cards:
            print("No more cards.")
            break

        added = 0

        for raw_card in page_cards:
            card = normalize_card(raw_card)

            if not card:
                continue

            cards.append(card)
            added += 1

        print(
            f"Page {page}: +{added} cards "
            f"(total {len(cards):,})"
        )

        next_page = payload.get("next_page")

        if isinstance(payload.get("data"), dict):
            next_page = payload["data"].get(
                "next_page",
                next_page
            )

        if next_page is None:
            break

        try:
            next_page = int(next_page)
        except (ValueError, TypeError):
            page += 1
        else:
            if next_page <= page:
                page += 1
            else:
                page = next_page

        # Small delay so we don't hammer the endpoint.
        time.sleep(0.5)

    # Deduplicate by cardId.
    unique = {}
    for card in cards:
        unique[card["cardId"]] = card

    cards = list(unique.values())

    cards.sort(
        key=lambda card: (
            -card["rating"],
            card["name"].lower(),
            card["cardId"]
        )
    )

    print()
    print(
        f"FUT.GG cards downloaded: {len(cards):,}"
    )

    return cards


# ============================================================
# MERGING
# ============================================================

def merge_futgg_cards_with_ea_players(
    ea_players,
    futgg_cards
):
    """
    Important:

    FUT.GG card IDs are card IDs, not necessarily the same
    as the EA dataset player_id.

    Therefore:
      - every FUT.GG card remains a separate entry;
      - we never deduplicate special cards by player name;
      - EA data is used as fallback when available.
    """

    if not futgg_cards:
        print()
        print(
            "No FUT.GG cards available."
        )
        print(
            "Using EA dataset only."
        )

        return ea_players

    ea_by_id = {
        clean(player["eaId"]): player
        for player in ea_players
        if clean(player["eaId"])
    }

    ea_by_name = {
        normalize_name(player["name"]): player
        for player in ea_players
        if normalize_name(player["name"])
    }

    merged = []

    matched = 0

    for card in futgg_cards:
        base = None

        ea_id = clean(card.get("eaId"))

        if ea_id and ea_id in ea_by_id:
            base = ea_by_id[ea_id]

        if base is None:
            name_key = normalize_name(card["name"])
            base = ea_by_name.get(name_key)

        if base:
            matched += 1

        player = {
            "eaId": (
                card["eaId"]
                or (base["eaId"] if base else "")
            ),

            "cardId": card["cardId"],

            "name": card["name"],
            "rating": (
                card["rating"]
                or (base["rating"] if base else 0)
            ),

            "position": (
                card["position"]
                or (base["position"] if base else "")
            ),

            "alternatePositions": (
                card["alternatePositions"]
                or (
                    base["alternatePositions"]
                    if base else ""
                )
            ),

            "club": (
                card["club"]
                or (base["club"] if base else "")
            ),

            "league": (
                card["league"]
                or (base["league"] if base else "")
            ),

            "nationality": (
                card["nationality"]
                or (base["nationality"] if base else "")
            ),

            "gender": (
                base["gender"]
                if base else ""
            ),

            "preferredFoot": (
                base["preferredFoot"]
                if base else ""
            ),

            "skillMoves": (
                card["skillMoves"]
                or (base["skillMoves"] if base else 0)
            ),

            "weakFoot": (
                card["weakFoot"]
                or (base["weakFoot"] if base else 0)
            ),

            "height": (
                base["height"]
                if base else 0
            ),

            "weight": (
                base["weight"]
                if base else 0
            ),

            "playstyles": (
                base["playstyles"]
                if base else []
            ),

            "pace": (
                base["pace"]
                if base else 0
            ),

            "shooting": (
                base["shooting"]
                if base else 0
            ),

            "passing": (
                base["passing"]
                if base else 0
            ),

            "dribbling": (
                base["dribbling"]
                if base else 0
            ),

            "defending": (
                base["defending"]
                if base else 0
            ),

            "physicality": (
                base["physicality"]
                if base else 0
            ),

            "edition": (
                base["edition"]
                if base else "FC27"
            ),

            "snapshotDate": (
                base["snapshotDate"]
                if base else ""
            ),

            "price": card["price"],
            "priceChange": card["priceChange"],

            "image": card["image"],
            "cardImage": card["cardImage"],
            "cardImageLarge": card["cardImageLarge"],

            "cardType": card["cardType"],
            "isSpecial": card["isSpecial"],

            "source": "futgg"
        }

        merged.append(player)

    print()
    print(
        f"Matched FUT.GG cards with EA dataset: "
        f"{matched:,}/{len(futgg_cards):,}"
    )

    return merged


# ============================================================
# VALIDATION
# ============================================================

def validate_players(players):
    if len(players) < 1000:
        raise RuntimeError(
            f"Only {len(players)} cards/players found. "
            "Database was not written."
        )

    card_images = sum(
        1
        for player in players
        if clean(player.get("cardImage"))
        or clean(player.get("cardImageLarge"))
    )

    special_cards = sum(
        1
        for player in players
        if player.get("isSpecial")
    )

    print()
    print("DATABASE VALIDATION")
    print("-" * 50)
    print(f"Total entries:       {len(players):,}")
    print(f"With card image:     {card_images:,}")
    print(f"Special cards:       {special_cards:,}")
    print("-" * 50)

    return card_images


# ============================================================
# WRITE DATABASE
# ============================================================

def write_database(players):
    players.sort(
        key=lambda player: (
            -number(player.get("rating")),
            normalize_name(player.get("name")),
            clean(player.get("cardId"))
        )
    )

    card_images = validate_players(players)

    result = {
        "version": 2,
        "updatedAt": datetime.now(
            timezone.utc
        ).isoformat(),

        "count": len(players),

        "cardCount": len(
            [
                player
                for player in players
                if clean(player.get("cardId"))
            ]
        ),

        "cardImages": card_images,

        "source": (
            "FUT.GG + EA FC dataset"
            if FUTGG_API_KEY
            else SOURCE_URL
        ),

        "platform": FUTGG_PLATFORM,

        "players": players
    }

    os.makedirs("docs", exist_ok=True)

    temporary_output = OUTPUT + ".tmp"

    with open(
        temporary_output,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            separators=(",", ":")
        )

    os.replace(
        temporary_output,
        OUTPUT
    )

    print()
    print("=" * 60)
    print("SUCCESS")
    print("=" * 60)
    print(f"Entries:       {len(players):,}")
    print(f"Card images:   {card_images:,}")
    print(f"Output:        {OUTPUT}")
    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("FutFlex FC27 Player/Card Database")
    print("=" * 60)

    ea_players = load_ea_players()

    futgg_cards = download_futgg_cards()

    players = merge_futgg_cards_with_ea_players(
        ea_players,
        futgg_cards
    )

    write_database(players)


if __name__ == "__main__":
    main()
