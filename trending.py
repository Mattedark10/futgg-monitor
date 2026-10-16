import requests
import re

JS_URL = "https://assets.fut.gg/ts/assets/index-LtbajdOB.js"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
}

response = requests.get(JS_URL, headers=HEADERS, timeout=30)
response.raise_for_status()

js = response.text

print("STATUS:", response.status_code)
print("JS SIZE:", len(js), "characters")

patterns = [
    r"function tp\(",
    r"tp\s*=\s*\(",
    r"tp\s*=\s*function",
    r"tp\s*=\s*[A-Za-z_$][A-Za-z0-9_$]*\(",
]

print()
print("TP DEFINITION SEARCH:")
print("=====================")

found_positions = []

for pattern in patterns:
    for match in re.finditer(pattern, js):
        position = match.start()

        if position not in found_positions:
            found_positions.append(position)

            print()
            print("PATTERN:", pattern)
            print("FOUND AT:", position)
            print("---------------------")

            start = max(0, position - 3000)
            end = min(len(js), position + 6000)

            print(js[start:end])

if not found_positions:
    print("No direct tp definition found.")
