import requests
import re

# =========================
# FUT.GG PLAYER GRID JS
# =========================

JS_URL = (
    "https://assets.fut.gg/ts/assets/"
    "PlayersConditionalPromiseGrid-CCQRB6py.js"
)

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
# PRINT IMPORTS
# =========================

imports = re.findall(
    r'["\'](\./[^"\']+\.js)["\']',
    js
)

print()
print("IMPORTED JS FILES:")
print("------------------")

if imports:
    for item in dict.fromkeys(imports):
        print(item)
else:
    print("No JS imports found.")

# =========================
# SEARCH INTERESTING DATA
# =========================

strings = re.findall(
    r'["\']([^"\']{2,1000})["\']',
    js
)

keywords = [
    "api",
    "player",
    "players",
    "trending",
    "price",
    "fetch",
    "axios",
    "promise",
    "query",
    "page",
]

interesting = []

for value in strings:
    if any(k in value.lower() for k in keywords):
        if value not in interesting:
            interesting.append(value)

print()
print("INTERESTING REFERENCES:")
print("-----------------------")

if interesting:
    for value in interesting[:300]:
        print(value)
else:
    print("No interesting references found.")

# =========================
# PRINT BEGINNING OF FILE
# =========================

print()
print("JS PREVIEW:")
print("-----------")
print(js[:10000])
