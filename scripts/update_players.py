import csv
import io
import json
import os
import urllib.request
from datetime import datetime, timezone

SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    "LakshmiKanth11/EA_FC_ANALYSIS/main/"
    "EA_FC_PLAYERS_DATASET_AND_%20DASHBOARD/data/players.csv"
)

OUTPUT = "docs/players.json"


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
        "image": None
    }


def download_csv():
    print("Downloading FC27 dataset...")

    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 FutFlex/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()

    if not data:
        raise RuntimeError("Downloaded file is empty.")

    print(f"Downloaded {len(data):,} bytes.")

    return data.decode("utf-8-sig")


def main():
    csv_text = download_csv()

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
            f"Only {len(players)} players found. "
            "Database was not written because the download is incomplete."
        )

    players.sort(
        key=lambda player: (
            -player["rating"],
            player["name"].lower()
        )
    )

    result = {
        "version": 1,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(players),
        "source": SOURCE_URL,
        "players": players
    }

    os.makedirs("docs", exist_ok=True)

    with open(OUTPUT, "w", encoding="utf-8") as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            separators=(",", ":")
        )

    print()
    print("=" * 50)
    print(f"SUCCESS: {len(players):,} players")
    print(f"OUTPUT:  {OUTPUT}")
    print("=" * 50)


if __name__ == "__main__":
    main()
