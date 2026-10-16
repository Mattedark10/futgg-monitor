import csv
import io
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from html import unescape


# ============================================================
# CONFIG
# ============================================================

SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    "LakshmiKanth11/EA_FC_ANALYSIS/main/"
    "EA_FC_PLAYERS_DATASET_AND_%20DASHBOARD/data/players.csv"
)

FUTGG_PLAYERS_URL = "https://www.fut.gg/players/"

OUTPUT = "docs/players.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36 FutFlex/1.0"
)

TIMEOUT = 120

# Number of FUT.GG catalogue pages to inspect.
#
# The public page is dynamically generated, so we use the
# catalogue pages exposed by FUT.GG when available.
#
# 0 = no artificial limit.
MAX_FUTGG_PAGES = 0


# ============================================================
# HELPERS
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


def request_bytes(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=TIMEOUT
    ) as response:
        return response.read()


def download_text(url):
    data = request_bytes(url)

    if not data:
        raise RuntimeError(
            f"Empty response from {url}"
        )

    return data.decode(
        "utf-8",
        errors="replace"
    )


# ============================================================
# EA DATASET
# ============================================================

def make_player(row):
    first = clean(row.get("first_name"))
    last = clean(row.get("last_name"))
    common = clean(row.get("common_name"))

    name = common or f"{first} {last}".strip()

    return {
        "eaId": clean(row.get("player_id")),
        "name": name,
        "rating": number(row.get("overall_rating")),
        "position": clean(row.get("position")),
        "alternatePositions": clean(
            row.get("alternate_positions")
        ),
        "club": clean(row.get("club")),
        "league": clean(row.get("league")),
        "nationality": clean(
            row.get("nationality")
        ),
        "gender": clean(row.get("gender")),
        "preferredFoot": clean(
            row.get("preferred_foot")
        ),
        "skillMoves": number(
            row.get("skill_moves")
        ),
        "weakFoot": number(
            row.get("weak_foot")
        ),
        "height": number(
            row.get("height_cm")
        ),
        "weight": number(
            row.get("weight_kg")
        ),

        "playstyles": [
            x.strip()
            for x in clean(
                row.get("playstyles")
            ).split(",")
            if x.strip()
        ],

        "pace": number(row.get("pace")),
        "shooting": number(
            row.get("shooting")
        ),
        "passing": number(
            row.get("passing")
        ),
        "dribbling": number(
            row.get("dribbling")
        ),
        "defending": number(
            row.get("defending")
        ),
        "physicality": number(
            row.get("physicality")
        ),

        "edition": clean(
            row.get("edition")
        ),
        "snapshotDate": clean(
            row.get("snapshot_date")
        ),

        "price": None,
        "priceChange": 0,

        "image": None,

        # Full FC27 card fields.
        "cardId": "",
        "cardType": "",
        "cardImage": "",
        "cardImageLarge": "",

        "isSpecial": False,

        "source": "ea_dataset"
    }


def download_ea_dataset():
    print("Downloading EA FC27 dataset...")

    csv_text = download_text(SOURCE_URL)

    reader = csv.DictReader(
        io.StringIO(csv_text)
    )

    players = []
    seen = set()

    for row in reader:
        player = make_player(row)

        ea_id = player["eaId"]

        if not ea_id:
            continue

        if ea_id in seen:
            continue

        seen.add(ea_id)
        players.append(player)

    if len(players) < 1000:
        raise RuntimeError(
            f"Only {len(players)} players found."
        )

    print(
        f"EA players loaded: {len(players):,}"
    )

    return players


# ============================================================
# FUT.GG HTML EXTRACTION
# ============================================================

def extract_json_ld(html):
    """
    Extract JSON-LD blocks from the page.
    """

    results = []

    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json'
        r'["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )

    for match in pattern.finditer(html):
        raw = unescape(match.group(1)).strip()

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        results.append(data)

    return results


def recursively_find_cards(value):
    """
    Search arbitrary Next.js / React data for objects that look
    like FUT.GG player cards.

    We intentionally don't assume a single internal structure.
    FUT.GG can change its React/Next.js serialization without
    changing the public player page.
    """

    found = []

    if isinstance(value, dict):
        keys = {
            str(key).lower()
            for key in value.keys()
        }

        has_card_image = any(
            key in keys
            for key in (
                "card_image_url",
                "cardimageurl",
                "cardimage",
                "card_image",
            )
        )

        has_card_id = any(
            key in keys
            for key in (
                "card_id",
                "cardid",
                "item_id",
                "itemid",
            )
        )

        has_player_name = any(
            key in keys
            for key in (
                "name",
                "player_name",
                "playername",
            )
        )

        if (
            has_card_image
            or (has_card_id and has_player_name)
        ):
            found.append(value)

        for child in value.values():
            found.extend(
                recursively_find_cards(child)
            )

    elif isinstance(value, list):
        for child in value:
            found.extend(
                recursively_find_cards(child)
            )

    return found


def extract_next_data(html):
    """
    Extract Next.js __NEXT_DATA__ when present.
    """

    pattern = re.compile(
        r'<script[^>]+id=["\']__NEXT_DATA__["\']'
        r'[^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )

    match = pattern.search(html)

    if not match:
        return None

    raw = unescape(
        match.group(1)
    ).strip()

    if not raw:
        return None

    try:
        return json.loads(raw)
    except Exception:
        return None


def extract_next_flight_json(html):
    """
    Extract JSON-ish objects from React Server Components
    (__next_f.push / self.__next_f.push).

    This is deliberately tolerant because Next.js versions
    serialize these chunks differently.
    """

    objects = []

    pattern = re.compile(
        r'(?:self\.)?__next_f\.push\(\s*'
        r'\[(.*?)\]\s*\)',
        re.DOTALL,
    )

    for match in pattern.finditer(html):
        chunk = match.group(1)

        # Look for JSON-looking objects.
        starts = [
            match.start()
            for match in re.finditer(
                r'(?<!\\)\{',
                chunk
            )
        ]

        for start in starts:
            depth = 0
            in_string = False
            escaped = False

            for index in range(
                start,
                len(chunk)
            ):
                char = chunk[index]

                if escaped:
                    escaped = False
                    continue

                if char == "\\":
                    escaped = True
                    continue

                if char == '"':
                    in_string = not in_string
                    continue

                if in_string:
                    continue

                if char == "{":
                    depth += 1

                elif char == "}":
                    depth -= 1

                    if depth == 0:
                        candidate = chunk[
                            start:index + 1
                        ]

                        try:
                            parsed = json.loads(
                                candidate
                            )
                            objects.append(parsed)
                        except Exception:
                            pass

                        break

    return objects


# ============================================================
# CARD NORMALIZATION
# ============================================================

def get_value(data, *names):
    if not isinstance(data, dict):
        return None

    lower_map = {
        str(key).lower(): value
        for key, value in data.items()
    }

    for name in names:
        value = lower_map.get(
            name.lower()
        )

        if value is not None:
            return value

    return None


def normalize_card(raw):
    if not isinstance(raw, dict):
        return None

    card_id = clean(
        get_value(
            raw,
            "card_id",
            "cardId",
            "item_id",
            "itemId",
        )
    )

    name = clean(
        get_value(
            raw,
            "name",
            "player_name",
            "playerName",
        )
    )

    card_image = clean(
        get_value(
            raw,
            "card_image_url",
            "cardImageUrl",
            "card_image",
            "cardImage",
        )
    )

    if not card_id or not name:
        return None

    rating = number(
        get_value(
            raw,
            "rating",
            "overall",
            "overall_rating",
        )
    )

    position = clean(
        get_value(
            raw,
            "position",
        )
    )

    club = clean(
        get_value(
            raw,
            "club",
        )
    )

    league = clean(
        get_value(
            raw,
            "league",
        )
    )

    nation = clean(
        get_value(
            raw,
            "nation",
            "nationality",
        )
    )

    card_type = clean(
        get_value(
            raw,
            "card_type",
            "cardType",
            "rarity",
            "version",
        )
    )

    ea_id = clean(
        get_value(
            raw,
            "player_id",
            "playerId",
            "eaId",
        )
    )

    price = get_value(
        raw,
        "price",
    )

    try:
        if price is not None:
            price = int(float(price))
    except (
        ValueError,
        TypeError
    ):
        price = None

    alternate_positions = get_value(
        raw,
        "alternatePositions",
        "alternate_positions",
    )

    if not isinstance(
        alternate_positions,
        list
    ):
        alternate_positions = []

    return {
        "cardId": card_id,
        "eaId": ea_id,
        "name": name,
        "rating": rating,
        "position": position,
        "alternatePositions": (
            alternate_positions
        ),
        "club": club,
        "league": league,
        "nationality": nation,

        "cardType": card_type,

        "cardImage": card_image,
        "cardImageLarge": card_image,

        "image": clean(
            get_value(
                raw,
                "image",
                "image_url",
                "player_image_url",
            )
        ),

        "price": price,

        "isSpecial": (
            card_type.lower()
            not in (
                "",
                "rare",
                "common",
                "gold rare",
                "gold common",
                "silver rare",
                "silver common",
                "bronze rare",
                "bronze common",
            )
        ),

        "source": "futgg_public"
    }


def extract_cards_from_html(html):
    candidates = []

    # 1. JSON-LD
    for block in extract_json_ld(html):
        candidates.extend(
            recursively_find_cards(block)
        )

    # 2. __NEXT_DATA__
    next_data = extract_next_data(html)

    if next_data:
        candidates.extend(
            recursively_find_cards(
                next_data
            )
        )

    # 3. React Server Components
    for block in extract_next_flight_json(html):
        candidates.extend(
            recursively_find_cards(block)
        )

    # 4. Direct card_image_url fallback.
    #
    # If FUT.GG serializes the card as a compact string rather
    # than an object, recover the image URL and nearby metadata
    # where possible.
    image_pattern = re.compile(
        r'https://game-assets\.fut\.gg/'
        r'[^"\'\\\s]+'
        r'/2027/'
        r'futgg-player-item-card/'
        r'[^"\'\\\s]+\.webp',
        re.IGNORECASE,
    )

    images = list(
        dict.fromkeys(
            image_pattern.findall(html)
        )
    )

    normalized = []

    for raw in candidates:
        card = normalize_card(raw)

        if card:
            normalized.append(card)

    # Deduplicate exact card IDs.
    cards_by_id = {}

    for card in normalized:
        card_id = card["cardId"]

        if not card_id:
            continue

        old = cards_by_id.get(card_id)

        if old is None:
            cards_by_id[card_id] = card
            continue

        # Prefer the object containing the actual image.
        if (
            not old["cardImage"]
            and card["cardImage"]
        ):
            cards_by_id[card_id] = card

    normalized = list(
        cards_by_id.values()
    )

    # If we found raw images but not structured cards, report them
    # for diagnostics. We do NOT invent player/card associations.
    print(
        f"  Structured card objects: "
        f"{len(normalized):,}"
    )

    print(
        f"  Raw card image URLs found: "
        f"{len(images):,}"
    )

    return normalized


# ============================================================
# FUT.GG CATALOGUE
# ============================================================

def download_futgg_catalogue():
    print()
    print("=" * 60)
    print("Reading public FUT.GG FC27 catalogue")
    print("=" * 60)

    cards = {}

    # First page.
    #
    # FUT.GG's current public player page is the authoritative
    # catalogue entry point.
    urls = [
        FUTGG_PLAYERS_URL
    ]

    # We deliberately keep the scraper conservative.
    #
    # We don't invent private API endpoints. We only process
    # public HTML pages.
    for url in urls:
        print()
        print(f"Downloading: {url}")

        try:
            html = download_text(url)
        except Exception as error:
            print(
                "WARNING: Could not download FUT.GG:"
            )
            print(error)
            continue

        print(
            f"Downloaded HTML: "
            f"{len(html):,} bytes"
        )

        page_cards = extract_cards_from_html(
            html
        )

        for card in page_cards:
            cards[
                card["cardId"]
            ] = card

        print(
            f"Cards recovered from page: "
            f"{len(page_cards):,}"
        )

    result = list(
        cards.values()
    )

    result.sort(
        key=lambda card: (
            -card["rating"],
            normalize_name(card["name"]),
            card["cardId"],
        )
    )

    print()
    print(
        f"Unique FUT.GG cards recovered: "
        f"{len(result):,}"
    )

    return result


# ============================================================
# MERGE
# ============================================================

def merge_cards(
    ea_players,
    futgg_cards
):
    """
    If FUT.GG cards are available, use them as the card
    catalogue.

    If the public HTML does not expose the catalogue in the
    current Next.js build, safely fall back to the EA dataset
    rather than writing a corrupt/empty players.json.
    """

    if not futgg_cards:
        print()
        print(
            "No structured FUT.GG cards were recovered."
        )
        print(
            "Keeping the EA dataset as fallback."
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

    for card in futgg_cards:
        base = None

        if (
            card["eaId"]
            and card["eaId"] in ea_by_id
        ):
            base = ea_by_id[
                card["eaId"]
            ]

        if base is None:
            base = ea_by_name.get(
                normalize_name(
                    card["name"]
                )
            )

        player = {
            "eaId": (
                card["eaId"]
                or (
                    base["eaId"]
                    if base
                    else ""
                )
            ),

            "cardId": card["cardId"],

            "name": card["name"],

            "rating": (
                card["rating"]
                or (
                    base["rating"]
                    if base
                    else 0
                )
            ),

            "position": (
                card["position"]
                or (
                    base["position"]
                    if base
                    else ""
                )
            ),

            "alternatePositions": (
                card["alternatePositions"]
                or (
                    base[
                        "alternatePositions"
                    ]
                    if base
                    else ""
                )
            ),

            "club": (
                card["club"]
                or (
                    base["club"]
                    if base
                    else ""
                )
            ),

            "league": (
                card["league"]
                or (
                    base["league"]
                    if base
                    else ""
                )
            ),

            "nationality": (
                card["nationality"]
                or (
                    base["nationality"]
                    if base
                    else ""
                )
            ),

            "gender": (
                base["gender"]
                if base
                else ""
            ),

            "preferredFoot": (
                base["preferredFoot"]
                if base
                else ""
            ),

            "skillMoves": (
                base["skillMoves"]
                if base
                else 0
            ),

            "weakFoot": (
                base["weakFoot"]
                if base
                else 0
            ),

            "height": (
                base["height"]
                if base
                else 0
            ),

            "weight": (
                base["weight"]
                if base
                else 0
            ),

            "playstyles": (
                base["playstyles"]
                if base
                else []
            ),

            "pace": (
                base["pace"]
                if base
                else 0
            ),

            "shooting": (
                base["shooting"]
                if base
                else 0
            ),

            "passing": (
                base["passing"]
                if base
                else 0
            ),

            "dribbling": (
                base["dribbling"]
                if base
                else 0
            ),

            "defending": (
                base["defending"]
                if base
                else 0
            ),

            "physicality": (
                base["physicality"]
                if base
                else 0
            ),

            "edition": "FC27",

            "snapshotDate": (
                base["snapshotDate"]
                if base
                else ""
            ),

            "price": card["price"],
            "priceChange": 0,

            "image": card["image"],

            "cardImage": card[
                "cardImage"
            ],

            "cardImageLarge": card[
                "cardImageLarge"
            ],

            "cardType": card[
                "cardType"
            ],

            "isSpecial": card[
                "isSpecial"
            ],

            "source": "futgg_public"
        }

        merged.append(player)

    return merged


# ============================================================
# VALIDATION
# ============================================================

def validate(players):
    if len(players) < 1000:
        raise RuntimeError(
            f"Only {len(players)} entries found. "
            "Refusing to overwrite players.json."
        )

    with_images = sum(
        1
        for player in players
        if clean(
            player.get(
                "cardImage"
            )
        )
        or clean(
            player.get(
                "cardImageLarge"
            )
        )
    )

    with_card_id = sum(
        1
        for player in players
        if clean(
            player.get(
                "cardId"
            )
        )
    )

    special = sum(
        1
        for player in players
        if player.get(
            "isSpecial"
        )
    )

    print()
    print("=" * 60)
    print("DATABASE VALIDATION")
    print("=" * 60)

    print(
        f"Entries:              {len(players):,}"
    )

    print(
        f"With card ID:         {with_card_id:,}"
    )

    print(
        f"With full card image: {with_images:,}"
    )

    print(
        f"Special cards:        {special:,}"
    )

    print("=" * 60)

    return (
        with_card_id,
        with_images,
        special,
    )


# ============================================================
# WRITE
# ============================================================

def write_database(players):
    (
        with_card_id,
        with_images,
        special,
    ) = validate(players)

    players.sort(
        key=lambda player: (
            -number(
                player.get(
                    "rating"
                )
            ),
            normalize_name(
                player.get(
                    "name"
                )
            ),
            clean(
                player.get(
                    "cardId"
                )
            ),
        )
    )

    result = {
        "version": 3,

        "updatedAt": datetime.now(
            timezone.utc
        ).isoformat(),

        "count": len(players),

        "cardCount": with_card_id,

        "cardImages": with_images,

        "specialCards": special,

        "source": (
            "FUT.GG public catalogue + "
            "EA FC27 dataset"
        ),

        "players": players,
    }

    os.makedirs(
        "docs",
        exist_ok=True
    )

    temporary = OUTPUT + ".tmp"

    with open(
        temporary,
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
        temporary,
        OUTPUT
    )

    print()
    print("=" * 60)
    print("SUCCESS")
    print("=" * 60)

    print(
        f"Output:              {OUTPUT}"
    )

    print(
        f"Entries:             {len(players):,}"
    )

    print(
        f"Full card images:    {with_images:,}"
    )

    print(
        f"Special cards:       {special:,}"
    )

    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("FutFlex FC27 DATABASE UPDATE")
    print("=" * 60)

    ea_players = download_ea_dataset()

    futgg_cards = (
        download_futgg_catalogue()
    )

    players = merge_cards(
        ea_players,
        futgg_cards
    )

    write_database(players)


if __name__ == "__main__":
    main()
