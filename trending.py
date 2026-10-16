import requests
import re

# =========================
# FUT.GG TRENDING JS
# =========================

JS_URL = "https://assets.fut.gg/ts/assets/trending-BwWTRUhl.js"

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
# SEARCH INTERESTING STRINGS
# =========================

strings = re.findall(
    r'["\']([^"\']{3,500})["\']',
    js
)

interesting = []

keywords = [
    "api",
    "trending",
    "player",
    "price",
    "fetch",
    "axios",
    "graphql",
    "/v1/",
    "/v2/",
]

for value in strings:
    lower = value.lower()

    if any(keyword in lower for keyword in keywords):
        if value not in interesting:
            interesting.append(value)

print()
print("INTERESTING JS REFERENCES:")
print("--------------------------")

for value in interesting[:200]:
    print(value)

# =========================
# SEARCH URLS
# =========================

urls = re.findall(
    r'https?://[^"\'\s]+',
    js
)

print()
print("URLS FOUND:")
print("-----------")

if urls:
    for url in dict.fromkeys(urls):
        print(url)
else:
    print("No full URLs found.")
