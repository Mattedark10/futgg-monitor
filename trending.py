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

# =========================
# DOWNLOAD TRENDING PAGE
# =========================
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
# FIND FC 27 CARD IDs
# =========================
card_ids = re.findall(r"27-(\d+)", page_html)

# Remove duplicates while keeping the original order
card_ids = list(dict.fromkeys(card_ids))

print("CARD IDs FOUND:", len(card_ids))
print("FIRST 30 IDs:", card_ids[:30])
