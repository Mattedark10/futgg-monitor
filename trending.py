import requests

JS_URL = "https://assets.fut.gg/ts/assets/index-LtbajdOB.js"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
}

response = requests.get(
    JS_URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()

js = response.text

print("STATUS:", response.status_code)
print("JS SIZE:", len(js), "characters")

# =========================
# FIND Rm DEFINITION
# =========================

search_terms = [
    "Rm=",
    "searchByGameSlug",
    "searchCardImages",
]

for term in search_terms:
    print()
    print("=" * 60)
    print("SEARCHING FOR:", term)
    print("=" * 60)

    position = js.find(term)

    if position == -1:
        print("NOT FOUND")
        continue

    print("FOUND AT:", position)

    start = max(0, position - 5000)
    end = min(len(js), position + 10000)

    print(js[start:end])
