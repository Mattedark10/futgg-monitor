import requests

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

# Find definitions of the route builders used by FUT.GG
for term in ["tp=", "ip=", "api.fut.gg", "https://api", "api/"]:
    print()
    print("=" * 60)
    print("SEARCHING FOR:", term)
    print("=" * 60)

    start = 0
    found = 0

    while True:
        position = js.find(term, start)

        if position == -1:
            break

        found += 1

        print()
        print("FOUND AT:", position)

        snippet_start = max(0, position - 1500)
        snippet_end = min(len(js), position + 3000)

        print(js[snippet_start:snippet_end])

        start = position + len(term)

        # Avoid enormous GitHub logs
        if found >= 5:
            break

    if found == 0:
        print("NOT FOUND")
