from pathlib import Path
import requests

BASE = Path(r"D:\Level1000Web\turkiye_data")
OUT = BASE / "VARANT_VERI"

OUT.mkdir(exist_ok=True)

URLS = [
    "https://datastore.borsaistanbul.com/",
    "https://download.borsaistanbul.com/",
    "https://www.borsaistanbul.com/veriler/pay-piyasasi-verileri",
]

print("=" * 70)
print(" BIST VARANT VERİ KAYNAĞI TESTİ")
print("=" * 70)

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/140 Safari/537.36"
    )
})

for url in URLS:

    print()
    print("[TEST]", url)

    try:

        r = session.get(
            url,
            timeout=20,
            allow_redirects=True
        )

        print("HTTP :", r.status_code)
        print("URL  :", r.url)
        print("BOYUT:", len(r.content))

        if r.status_code == 200:

            name = (
                "datastore.html"
                if "datastore" in url
                else "download.html"
                if "download" in url
                else "bist.html"
            )

            path = OUT / name

            path.write_bytes(r.content)

            print("[OK] Kaydedildi:", path)

        else:

            print("[ERİŞİM YOK]")

    except Exception as e:

        print("[HATA]", e)


print()
print("=" * 70)
print("TEST TAMAMLANDI")
print("=" * 70)

print()
print("Şimdi klasör:")
print(OUT)