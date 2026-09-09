import io
from pathlib import Path
import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent
OUT_FILE = BASE_DIR / "symbols.txt"

URLS = [
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
]

symbols = set()

headers = {
    "User-Agent": "Mozilla/5.0"
}

for url in URLS:
    print(f"İndiriliyor: {url}")

    r = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    r.raise_for_status()

    text = r.text

    df = pd.read_csv(
        io.StringIO(text),
        sep="|"
    )

    for col in ["Symbol", "ACT Symbol"]:
        if col in df.columns:
            for value in df[col].dropna():
                symbol = str(value).strip().upper()

                if (
                    symbol
                    and symbol != "FILE CREATION TIME"
                    and not symbol.startswith("TEST")
                ):
                    symbols.add(symbol)

symbols = sorted(symbols)

OUT_FILE.write_text(
    "\n".join(symbols),
    encoding="utf-8"
)

print()
print("=" * 60)
print(f"TOPLAM SEMBOL: {len(symbols):,}")
print(f"Dosya: {OUT_FILE}")
print("=" * 60)