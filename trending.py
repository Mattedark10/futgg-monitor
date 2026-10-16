import requests

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

print()
print("FULL TRENDING JS:")
print("=================")
print(js)
