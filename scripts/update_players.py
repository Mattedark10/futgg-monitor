import csv
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


def make_player(row):
    player_id = clean(row.get("player_id"))

    first = clean(row.get("first_name"))
    last = clean(row.get("last_name"))
    common = clean(row.get("common_name"))

    name = common or f"{first} {last}".strip()

    return {
        "eaId": player_id,
        "name": name,
        "rating": int(row["overall_rating"]) if clean(row.get("overall_rating")).isdigit() else 0,
        "position": clean(row.get("position")),
        "alternatePositions": clean(row.get("alternate_positions")),
        "club": clean(row.get("club")),
        "league": clean(row.get("league")),
        "nationality": clean(row.get("nationality")),
        "gender": clean(row.get("gender")),
        "preferredFoot": clean(row.get("preferred_foot")),
        "skillMoves": clean(row.get("skill_moves")),
        "weakFoot": clean(row.get("weak_foot")),
        "height": clean(row.get("height_cm")),
        "weight": clean(row.get("weight_kg")),
        "playstyles": [
            x.strip()
            for x in clean(row.get("playstyles")).split(",")
            if x.strip()
        ],

        "pace": int(row["pace"]) if clean(row.get("pace")).isdigit() else 0,
        "shooting": int(row["shooting"]) if clean(row.get("shooting")).isdigit() else 0,
        "passing": int(row["passing"]) if clean(row.get("passing")).isdigit() else 0,
        "dribbling": int(row["dribbling"]) if clean(row.get("dribbling")).isdigit() else 0,
        "defending": int(row["defending"]) if clean(row.get("defending")).isdigit() else 0,
        "physicality": int(row["physicality"]) if clean(row.get("physicality")).isdigit() else 0,

        "edition": clean(row.get("edition")),
        "snapshotDate": clean(row.get("snapshot_date")),

        # Prezzi/storico vengono aggiunti dal sistema FutFlex
        "price": None,
        "priceChange": 0,
        "image": None
    }


def main():
    print("Downloading FC27 player database...")

    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": "FutFlex/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read().decode("utf-8")

    rows = list(csv.DictReader(content.splitlines()))

    players = []
    seen = set()

    for row in rows:
        player = make_player(row)

        if not player["eaId"]:
            continue

        if player["eaId"] in seen:
            continue

        seen.add(player["eaId"])
        players.append(player)

    players.sort(
        key=lambda p: (
            -p["rating"],
            p["name"].lower()
        )
    )

    output = {
        "version": 1,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(players),
        "source": "EA FC 27 public ratings dataset",
        "players": players
    }

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            separators=(",", ":")
        )

    print(f"Saved {len(players)} players to {OUTPUT}")


if __name__ == "__main__":
    main()
