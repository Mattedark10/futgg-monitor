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

target = "function tp("
position = js.find(target)

print("STATUS:", response.status_code)
print()
print("TP FUNCTION:")
print("============")

if position == -1:
    print("function tp NOT FOUND")
else:
    print("FOUND AT:", position)
    print()
    
    # Print only from the beginning of the tp function
    print(js[position:position + 8000])
