import csv
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone


# ============================================================
# CONFIG
# ============================================================

EA_SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    "LakshmiKanth11/EA_FC_ANALYSIS/main/"
    "EA_FC_PLAYERS_DATASET_AND_%20DASHBOARD/data/players.csv"
)

FUTGG_PLAYERS_URL = "https://www.fut.gg/players/"
FUTGG_SITEMAP_URL = "https://www.fut.gg/sitemap.xml"

OUTPUT = "docs/players.json"

MAX_WORKERS = 8

REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0 Safari/537.36 "
    "FutFlex/1.0"
)


# ============================================================
# HTTP
# ============================================================

def http_get(url, timeout=REQUEST_TIMEOUT):
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
            "Pragma": "no-cache",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


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

    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def slug_to_name(url):
    try:
        path = urllib.parse.urlparse(url).path.strip("/")

        if not path:
            return ""

        last = path.split("/")[-1]

        # Remove player ID from URLs such as:
        # 253409-gift-links
        last = re.sub(r"^\d+-", "", last)

        last = last.replace("-", " ")

        return last.strip()

    except Exception:
        return ""


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

        "image": None,

        "cardId": None,
        "cardType": None,
        "cardImage": None,
        "cardImageLarge": None,

        "isSpecial": False,

        "source": "ea",
    }


def download_ea_dataset():
    print("Downloading EA FC27 dataset...")

    data = http_get(EA_SOURCE_URL, timeout=120)

    if not data:
        raise RuntimeError("EA dataset is empty.")

    csv_text = data.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(csv_text))

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
            f"Only {len(players)} EA players found."
        )

    print(f"EA players loaded: {len(players):,}")

    return players


# ============================================================
# SITEMAP
# ============================================================

def extract_sitemap_urls(xml_data):
    urls = []

    try:
        root = ET.fromstring(xml_data)

        for element in root.iter():
            tag = element.tag.lower()

            if tag.endswith("loc"):
                if element.text:
                    urls.append(element.text.strip())

    except ET.ParseError:
        text = xml_data.decode("utf-8", errors="ignore")

        urls = re.findall(
            r"<loc>\s*(.*?)\s*</loc>",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

    return urls


def download_sitemap():
    print()
    print("=" * 60)
    print("READING FUT.GG SITEMAP")
    print("=" * 60)

    try:
        data = http_get(
            FUTGG_SITEMAP_URL,
            timeout=REQUEST_TIMEOUT,
        )

        print(
            f"Downloaded sitemap: "
            f"{len(data):,} bytes"
        )

        urls = extract_sitemap_urls(data)

        print(
            f"Sitemap URLs discovered: "
            f"{len(urls):,}"
        )

        return urls

    except Exception as exc:
        print(
            "Could not download sitemap.xml:"
            f" {type(exc).__name__}: {exc}"
        )

        return []


# ============================================================
# SITEMAP INDEX SUPPORT
# ============================================================

def download_sitemap_children(url):
    try:
        data = http_get(url, timeout=REQUEST_TIMEOUT)
        return extract_sitemap_urls(data)

    except Exception as exc:
        print(
            f"  Sitemap child failed: {url} "
            f"({type(exc).__name__}: {exc})"
        )

        return []


def get_player_urls():
    urls = download_sitemap()

    if not urls:
        return []

    # If sitemap.xml is an index, it will normally contain
    # other sitemap XML files.
    sitemap_children = [
        url
        for url in urls
        if ".xml" in url.lower()
    ]

    if sitemap_children:
        print(
            f"Found {len(sitemap_children):,} "
            "sitemap files."
        )

        all_urls = []

        with ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as executor:

            futures = [
                executor.submit(
                    download_sitemap_children,
                    url
                )
                for url in sitemap_children
            ]

            for future in as_completed(futures):
                try:
                    result = future.result()
                    all_urls.extend(result)

                except Exception as exc:
                    print(
                        "Sitemap worker error:",
                        exc
                    )

        urls = all_urls

    player_urls = []

    seen = set()

    for url in urls:
        if "/players/" not in url:
            continue

        # Ignore category/filter pages.
        if "?" in url:
            continue

        normalized = url.rstrip("/")

        if normalized in seen:
            continue

        seen.add(normalized)
        player_urls.append(normalized)

    print(
        f"FUT.GG player pages found: "
        f"{len(player_urls):,}"
    )

    return player_urls


# ============================================================
# CARD IMAGE EXTRACTION
# ============================================================

CARD_IMAGE_PATTERN = re.compile(
    r'https?://game-assets\.fut\.gg/'
    r'[^"\'<>\s]+/'
    r'2027/'
    r'futgg-player-item-card/'
    r'[^"\'<>\s]+?'
    r'\.(?:webp|png|jpg|jpeg)',
    flags=re.IGNORECASE,
)


CARD_ID_PATTERN = re.compile(
    r'/2027/futgg-player-item-card/'
    r'(?:[^/]+/)?'
    r'27-(\d+)\.',
    flags=re.IGNORECASE,
)


def clean_image_url(url):
    url = url.strip()

    url = url.replace("\\/", "/")
    url = url.replace("\\u0026", "&")

    return url


def extract_card_images(html):
    text = html.decode(
        "utf-8",
        errors="ignore"
    )

    images = set()

    # --------------------------------------------------------
    # Direct URLs
    # --------------------------------------------------------

    for match in CARD_IMAGE_PATTERN.findall(text):
        images.add(clean_image_url(match))

    # --------------------------------------------------------
    # Escaped JSON URLs
    # --------------------------------------------------------

    escaped = text.replace("\\/", "/")

    for match in CARD_IMAGE_PATTERN.findall(escaped):
        images.add(clean_image_url(match))

    return sorted(images)


def extract_card_ids_from_images(images):
    result = []

    for image in images:
        match = CARD_ID_PATTERN.search(image)

        if not match:
            continue

        card_id = match.group(1)

        result.append(
            (
                card_id,
                image
            )
        )

    return result


# ============================================================
# FUT.GG PAGE PARSER
# ============================================================

def extract_field(text, patterns):
    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if match:
            value = clean(match.group(1))

            if value:
                return value

    return ""


def extract_player_id(url):
    path = urllib.parse.urlparse(url).path

    match = re.search(
        r"/players/(\d+)",
        path
    )

    if match:
        return match.group(1)

    return ""


def extract_page_card_metadata(text, card_id):
    metadata = {
        "cardType": "",
        "rating": 0,
        "position": "",
        "name": "",
        "club": "",
        "league": "",
        "nation": "",
    }

    # --------------------------------------------------------
    # JSON-style fields
    # --------------------------------------------------------

    def json_value(key):
        patterns = [
            rf'"{re.escape(key)}"\s*:\s*"([^"]+)"',
            rf'"{re.escape(key)}"\s*:\s*(\d+)',
        ]

        return extract_field(
            text,
            patterns
        )

    metadata["cardType"] = (
        json_value("card_type")
        or json_value("cardType")
        or json_value("rarity")
    )

    metadata["position"] = (
        json_value("position")
    )

    metadata["name"] = (
        json_value("name")
    )

    metadata["club"] = (
        json_value("club")
    )

    metadata["league"] = (
        json_value("league")
    )

    metadata["nation"] = (
        json_value("nation")
        or json_value("nationality")
    )

    rating = (
        json_value("rating")
        or json_value("overall")
        or json_value("overall_rating")
    )

    if rating:
        metadata["rating"] = number(rating)

    # --------------------------------------------------------
    # Item page text fallback
    # --------------------------------------------------------

    if not metadata["cardType"]:
        metadata["cardType"] = extract_field(
            text,
            [
                r'"card_type"\s*:\s*"([^"]+)"',
                r'"item_type"\s*:\s*"([^"]+)"',
                r'"rarity_name"\s*:\s*"([^"]+)"',
            ]
        )

    return metadata


# ============================================================
# FETCH ONE PLAYER PAGE
# ============================================================

def fetch_player_page(url):
    try:
        data = http_get(
            url,
            timeout=REQUEST_TIMEOUT
        )

        text = data.decode(
            "utf-8",
            errors="ignore"
        )

        images = extract_card_images(data)

        cards = []

        page_ea_id = extract_player_id(url)

        page_name = slug_to_name(url)

        metadata = extract_page_card_metadata(
            text,
            ""
        )

        for card_id, image in extract_card_ids_from_images(
            images
        ):
            card = {
                "cardId": card_id,
                "eaId": page_ea_id,

                "name": (
                    metadata["name"]
                    or page_name
                ),

                "rating": metadata["rating"],
                "position": metadata["position"],

                "cardType": metadata["cardType"],

                "club": metadata["club"],
                "league": metadata["league"],
                "nationality": metadata["nation"],

                "cardImage": image,

                "cardImageLarge": image,

                "sourceUrl": url,

                "source": "futgg",
            }

            # Remove duplicate card IDs
            if not any(
                existing["cardId"] == card_id
                for existing in cards
            ):
                cards.append(card)

        return cards

    except urllib.error.HTTPError as exc:
        return []

    except Exception:
        return []


# ============================================================
# CARD COLLECTION
# ============================================================

def collect_futgg_cards(player_urls):
    if not player_urls:
        return []

    print()
    print("=" * 60)
    print("COLLECTING FC27 CARDS FROM FUT.GG PLAYER PAGES")
    print("=" * 60)

    print(
        f"Pages to scan: {len(player_urls):,}"
    )

    cards = {}

    completed = 0

    start_time = time.time()

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                fetch_player_page,
                url
            ): url
            for url in player_urls
        }

        for future in as_completed(futures):
            completed += 1

            try:
                result = future.result()

            except Exception:
                result = []

            for card in result:
                card_id = card["cardId"]

                if not card_id:
                    continue

                # Prefer the first valid full-card image.
                if card_id not in cards:
                    cards[card_id] = card

                else:
                    existing = cards[card_id]

                    if (
                        not existing.get("cardImage")
                        and card.get("cardImage")
                    ):
                        cards[card_id] = card

            if completed % 100 == 0:
                elapsed = time.time() - start_time

                print(
                    f"Progress: {completed:,}/"
                    f"{len(player_urls):,} | "
                    f"Cards: {len(cards):,} | "
                    f"Time: {elapsed:.0f}s"
                )

    print()
    print(
        f"Pages scanned: {completed:,}"
    )

    print(
        f"Unique FUT.GG cards found: "
        f"{len(cards):,}"
    )

    return list(cards.values())


# ============================================================
# FALLBACK DIRECT PLAYER PAGE TEST
# ============================================================

def test_public_players_page():
    print()
    print("=" * 60)
    print("TESTING FUT.GG PUBLIC PLAYERS PAGE")
    print("=" * 60)

    try:
        data = http_get(
            FUTGG_PLAYERS_URL,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"Downloaded HTML: "
            f"{len(data):,} bytes"
        )

        images = extract_card_images(data)

        print(
            f"Card images found on /players/: "
            f"{len(images):,}"
        )

        return images

    except Exception as exc:
        print(
            "Players page test failed:",
            exc
        )

        return []


# ============================================================
# MATCH CARDS WITH EA PLAYERS
# ============================================================

def build_indexes(players):
    by_ea_id = {}

    by_name = {}

    for player in players:
        ea_id = clean(player.get("eaId"))

        if ea_id:
            by_ea_id[ea_id] = player

        name = normalize_name(
            player.get("name")
        )

        if name:
            by_name.setdefault(
                name,
                []
            ).append(player)

    return by_ea_id, by_name


def merge_cards(players, cards):
    print()
    print("=" * 60)
    print("MERGING FUT.GG CARDS WITH EA DATABASE")
    print("=" * 60)

    by_ea_id, by_name = build_indexes(players)

    matched = 0

    unmatched = 0

    special_cards = 0

    output = []

    # --------------------------------------------------------
    # Base EA records
    # --------------------------------------------------------

    for player in players:
        item = dict(player)

        item["cardId"] = (
            item.get("cardId")
            or None
        )

        item["cardImage"] = (
            item.get("cardImage")
            or None
        )

        item["cardImageLarge"] = (
            item.get("cardImageLarge")
            or None
        )

        item["isSpecial"] = bool(
            item.get("isSpecial")
        )

        output.append(item)

    # --------------------------------------------------------
    # Add FUT.GG versions
    # --------------------------------------------------------

    existing_card_ids = set()

    for player in output:
        card_id = clean(
            player.get("cardId")
        )

        if card_id:
            existing_card_ids.add(
                card_id
            )

    for card in cards:
        card_id = clean(
            card.get("cardId")
        )

        if not card_id:
            continue

        if card_id in existing_card_ids:
            continue

        ea_id = clean(
            card.get("eaId")
        )

        target = None

        # ----------------------------------------------------
        # Match by EA player ID
        # ----------------------------------------------------

        if ea_id and ea_id in by_ea_id:
            target = by_ea_id[ea_id]

        # ----------------------------------------------------
        # Match by name
        # ----------------------------------------------------

        if target is None:
            card_name = normalize_name(
                card.get("name")
            )

            candidates = by_name.get(
                card_name,
                []
            )

            if len(candidates) == 1:
                target = candidates[0]

        # ----------------------------------------------------
        # If matched, create full card record.
        # ----------------------------------------------------

        if target is not None:
            base = dict(target)

            base["cardId"] = card_id

            if card.get("cardType"):
                base["cardType"] = card[
                    "cardType"
                ]

            if card.get("cardImage"):
                base["cardImage"] = card[
                    "cardImage"
                ]

            if card.get("cardImageLarge"):
                base["cardImageLarge"] = card[
                    "cardImageLarge"
                ]

            if card.get("rating"):
                base["rating"] = card[
                    "rating"
                ]

            if card.get("position"):
                base["position"] = card[
                    "position"
                ]

            if card.get("club"):
                base["club"] = card[
                    "club"
                ]

            if card.get("league"):
                base["league"] = card[
                    "league"
                ]

            if card.get("nationality"):
                base["nationality"] = card[
                    "nationality"
                ]

            base["isSpecial"] = True

            base["source"] = "futgg"

            base["sourceUrl"] = card.get(
                "sourceUrl"
            )

            output.append(base)

            matched += 1

            if card.get("cardType"):
                card_type = card[
                    "cardType"
                ].lower()

                if (
                    "rare" not in card_type
                    and "common" not in card_type
                    and "gold" not in card_type
                    and "silver" not in card_type
                    and "bronze" not in card_type
                ):
                    special_cards += 1

        else:
            # ------------------------------------------------
            # Keep unmatched FUT.GG cards too.
            # This is important for Icons/Heroes/etc.
            # ------------------------------------------------

            standalone = {
                "eaId": ea_id or None,

                "name": card.get(
                    "name"
                ) or "Unknown",

                "rating": card.get(
                    "rating",
                    0
                ),

                "position": card.get(
                    "position",
                    ""
                ),

                "alternatePositions": "",

                "club": card.get(
                    "club",
                    ""
                ),

                "league": card.get(
                    "league",
                    ""
                ),

                "nationality": card.get(
                    "nationality",
                    ""
                ),

                "gender": "",

                "preferredFoot": "",

                "skillMoves": 0,
                "weakFoot": 0,

                "height": 0,
                "weight": 0,

                "playstyles": [],

                "pace": 0,
                "shooting": 0,
                "passing": 0,
                "dribbling": 0,
                "defending": 0,
                "physicality": 0,

                "edition": "FC27",
                "snapshotDate": "",

                "price": None,
                "priceChange": 0,

                "image": card.get(
                    "cardImage"
                ),

                "cardId": card_id,

                "cardType": card.get(
                    "cardType"
                ),

                "cardImage": card.get(
                    "cardImage"
                ),

                "cardImageLarge": card.get(
                    "cardImageLarge"
                ),

                "isSpecial": True,

                "source": "futgg",

                "sourceUrl": card.get(
                    "sourceUrl"
                ),
            }

            output.append(
                standalone
            )

            unmatched += 1

            special_cards += 1

    print(
        f"Cards matched with EA: "
        f"{matched:,}"
    )

    print(
        f"Standalone FUT.GG cards: "
        f"{unmatched:,}"
    )

    print(
        f"Special cards detected: "
        f"{special_cards:,}"
    )

    return output


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def deduplicate_players(players):
    result = []

    seen_cards = set()

    seen_base = set()

    for player in players:
        card_id = clean(
            player.get("cardId")
        )

        ea_id = clean(
            player.get("eaId")
        )

        # Card records are unique by card ID.
        if card_id:
            key = (
                "card",
                card_id
            )

        else:
            key = (
                "base",
                ea_id
            )

        if key in seen_cards:
            continue

        seen_cards.add(key)

        result.append(player)

    return result


# ============================================================
# SORT
# ============================================================

def sort_players(players):
    return sorted(
        players,
        key=lambda player: (
            -number(
                player.get("rating")
            ),
            normalize_name(
                player.get("name")
            ),
            clean(
                player.get("cardId")
            ),
        )
    )


# ============================================================
# VALIDATION
# ============================================================

def validate(players):
    with_card_id = 0

    with_full_image = 0

    special_cards = 0

    for player in players:
        if player.get("cardId"):
            with_card_id += 1

        if (
            player.get("cardImage")
            or player.get("cardImageLarge")
        ):
            with_full_image += 1

        if player.get("isSpecial"):
            special_cards += 1

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
        f"With full card image: {with_full_image:,}"
    )

    print(
        f"Special cards:        {special_cards:,}"
    )

    return (
        with_card_id,
        with_full_image,
        special_cards,
    )


# ============================================================
# WRITE DATABASE
# ============================================================

def write_database(players):
    os.makedirs(
        os.path.dirname(OUTPUT),
        exist_ok=True
    )

    result = {
        "version": 4,

        "updatedAt": datetime.now(
            timezone.utc
        ).isoformat(),

        "count": len(players),

        "source": {
            "ea": EA_SOURCE_URL,
            "futgg": FUTGG_PLAYERS_URL,
            "sitemap": FUTGG_SITEMAP_URL,
        },

        "players": players,
    }

    temp_output = OUTPUT + ".tmp"

    with open(
        temp_output,
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
        temp_output,
        OUTPUT
    )

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("FutFlex FC27 DATABASE UPDATE")
    print("=" * 60)

    # --------------------------------------------------------
    # EA database
    # --------------------------------------------------------

    players = download_ea_dataset()

    # --------------------------------------------------------
    # First test public catalogue
    # --------------------------------------------------------

    public_images = test_public_players_page()

    print(
        f"Raw card image URLs on public catalogue: "
        f"{len(public_images):,}"
    )

    # --------------------------------------------------------
    # Sitemap
    # --------------------------------------------------------

    player_urls = get_player_urls()

    # --------------------------------------------------------
    # FUT.GG cards
    # --------------------------------------------------------

    futgg_cards = collect_futgg_cards(
        player_urls
    )

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------

    if futgg_cards:

        players = merge_cards(
            players,
            futgg_cards
        )

    else:

        print()
        print(
            "WARNING: No FUT.GG cards were recovered."
        )

        print(
            "Keeping EA dataset."
        )

    # --------------------------------------------------------
    # Deduplicate
    # --------------------------------------------------------

    players = deduplicate_players(
        players
    )

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    players = sort_players(
        players
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    with_card_id, with_full_image, special_cards = (
        validate(players)
    )

    # --------------------------------------------------------
    # Safety check
    # --------------------------------------------------------

    if len(players) < 1000:
        raise RuntimeError(
            "Database validation failed: "
            f"only {len(players)} entries."
        )

    # --------------------------------------------------------
    # Write
    # --------------------------------------------------------

    write_database(players)

    print()
    print("=" * 60)
    print("SUCCESS")
    print("=" * 60)

    print(
        f"Output:              {OUTPUT}"
    )

    print(
        f"Entries:              {len(players):,}"
    )

    print(
        f"Full card images:     {with_full_image:,}"
    )

    print(
        f"Cards with ID:        {with_card_id:,}"
    )

    print(
        f"Special cards:        {special_cards:,}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()
