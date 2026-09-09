from pathlib import Path
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = Path(r"D:\Level1000Web\turkiye_data\VARANT_VERI")
BASE.mkdir(exist_ok=True)

URL = "https://www.borsaistanbul.com/veriler/pay-piyasasi-verileri"

print("=" * 70)
print(" BIST AÇIK VERİ DOSYALARINI TESPİT ET")
print("=" * 70)

session = requests.Session()

session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/140.0.0.0 Safari/537.36"
})

try:

    r = session.get(URL, timeout=30)

    print("HTTP:", r.status_code)
    print("Boyut:", len(r.content))

    r.raise_for_status()

    html = r.text

    (BASE / "pay_piyasasi.html").write_text(
        html,
        encoding="utf-8"
    )

    soup = BeautifulSoup(html, "html.parser")

    print()
    print("LINKLER")
    print("-" * 70)

    links = []

    for a in soup.find_all("a"):

        href = a.get("href")

        if not href:
            continue

        text = a.get_text(" ", strip=True)

        full = urljoin(URL, href)

        item = (text, full)

        if item not in links:
            links.append(item)

    for text, link in links:

        low = (text + " " + link).lower()

        if any(x in low for x in [
            ".csv",
            ".zip",
            ".xls",
            ".xlsx",
            "bülten",
            "bulletin",
            "veri",
            "data",
            "pay"
        ]):

            print()
            print("ADI :", text[:150])
            print("URL :", link)

    print()
    print("=" * 70)
    print("FORM VE BUTONLAR")
    print("=" * 70)

    for i, form in enumerate(soup.find_all("form")):

        print()
        print("FORM", i)

        print(
            str(form)[:5000]
        )

    print()
    print("=" * 70)
    print("TAMAMLANDI")
    print("=" * 70)

    print()
    print("HTML:")
    print(BASE / "pay_piyasasi.html")

except Exception as e:

    print()
    print("[HATA]")
    print(e)