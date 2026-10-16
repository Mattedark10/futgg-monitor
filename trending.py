import requests
import re

# =========================
# FUT.GG TRENDING PLAYERS
# =========================
URL = "https://www.fut.gg/players/trending/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
}

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()

page_html = response.text

print("STATUS:", response.status_code)
print("HTML SIZE:", len(page_html), "characters")

# =========================
# SEARCH FOR API / JS DATA
# =========================

patterns = [
    r'https?://[^"\']+',
    r'[^"\']*(?:api|trending)[^"\']*',
]

results = []

for pattern in patterns:
    for match in re.findall(pattern, page_html, re.IGNORECASE):
        match = match.strip()

        if (
            "api" in match.lower()
            or "trending" in match.lower()
        ):
            if match not in results:
                results.append(match)

print()
print("POSSIBLE API / TRENDING REFERENCES:")
print("-----------------------------------")

if results:
    for result in results[:100]:
        print(result)
else:
    print("No references found.")

# =========================
# NEXT.JS DATA CHECK
# =========================

next_data = re.search(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    page_html,
    re.DOTALL | re.IGNORECASE
)

print()
print("NEXT.JS DATA:")
print("-------------")

if next_data:
    print(next_data.group(1)[:5000])
else:
    print("No __NEXT_DATA__ found.")
