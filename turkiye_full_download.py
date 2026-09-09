# -*- coding: utf-8 -*-

from pathlib import Path
import time
import re
import warnings

warnings.filterwarnings("ignore")

import requests
import pandas as pd
import yfinance as yf


# ============================================================
# AYARLAR
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "turkiye_data"
CACHE_DIR = DATA_DIR / "cache"

DATA_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

UNIVERSE_FILE = DATA_DIR / "bist_hisseler.csv"
FAILED_FILE = DATA_DIR / "failed_symbols.txt"
SUMMARY_FILE = DATA_DIR / "download_summary.csv"

YEARS = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
}


# ============================================================
# EKRAN
# ============================================================

def title(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


# ============================================================
# ESKİ YABANCI EVRENİ KESİNLİKLE KULLANMA
# ============================================================

def clean_old_files():

    old_universe = DATA_DIR / "turkiye_universe.csv"

    if old_universe.exists():
        try:
            old_universe.unlink()
            print("[TEMİZLENDİ] Eski turkiye_universe.csv")
        except Exception:
            pass


# ============================================================
# TRADINGVIEW BIST HİSSE EVRENİ
# ============================================================

def get_bist_stocks():

    title("BIST HİSSE EVRENİ OLUŞTURULUYOR")

    url = "https://scanner.tradingview.com/turkey/scan"

    payload = {
        "filter": [
            {
                "left": "type",
                "operation": "equal",
                "right": "stock"
            }
        ],
        "options": {
            "lang": "tr"
        },
        "symbols": {
            "query": {
                "types": []
            },
            "tickers": []
        },
        "columns": [
            "name",
            "description",
            "exchange",
            "type"
        ],
        "sort": {
            "sortBy": "name",
            "sortOrder": "asc"
        },
        "range": [
            0,
            5000
        ]
    }

    try:

        r = requests.post(
            url,
            json=payload,
            headers=HEADERS,
            timeout=30
        )

        r.raise_for_status()

        data = r.json()

        rows = data.get("data", [])

        symbols = []

        for row in rows:

            d = row.get("d", [])

            if not d:
                continue

            name = d[0]

            if not name:
                continue

            name = str(name).strip().upper()

            # Sadece BIST tarzı hisse kodları
            if not re.fullmatch(r"[A-Z0-9]{2,8}", name):
                continue

            # TradingView'den gelen borsa bilgisi
            exchange = ""

            if len(d) > 2 and d[2]:
                exchange = str(d[2]).upper()

            # Turkey scanner içinden gelen hisseleri al
            symbols.append(name)

        symbols = sorted(set(symbols))

        # Açıkça yabancı/global sembolleri engelle
        bad = {
            "A",
            "AA",
            "AAA",
            "AAAA",
            "AAPL",
            "MSFT",
            "GOOG",
            "GOOGL",
            "AMZN",
            "META",
            "TSLA",
            "NVDA",
            "AMD",
            "INTC",
            "NFLX",
            "COIN",
            "MSTR"
        }

        symbols = [
            x for x in symbols
            if x not in bad
        ]

        if len(symbols) < 100:

            print(
                f"[UYARI] TradingView sadece {len(symbols)} sembol döndürdü."
            )

            return []

        print(
            f"[OK] BIST hisse adayı: {len(symbols)}"
        )

        return symbols

    except Exception as e:

        print(
            "[HATA] BIST hisse evreni alınamadı:",
            e
        )

        return []


# ============================================================
# ALTERNATİF: BIST ANA SAYFASINDAN KODLARI ÇEK
# ============================================================

def get_bist_from_homepage():

    print("[ALTERNATİF] Borsa İstanbul ana sayfası deneniyor...")

    urls = [
        "https://www.borsaistanbul.com/",
        "https://www.borsaistanbul.com/sirketler/islem-goren-sirketler",
    ]

    found = set()

    for url in urls:

        try:

            r = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )

            if r.status_code != 200:
                continue

            text = r.text.upper()

            # BIST'in .E / .V kod yapılarından mümkün olanları yakala
            matches = re.findall(
                r"\b([A-Z0-9]{2,8})\.E\b",
                text
            )

            for x in matches:
                found.add(x)

        except Exception:
            continue

    found = sorted(found)

    if len(found) >= 100:

        print(
            f"[OK] Borsa İstanbul sayfasından {len(found)} kod bulundu."
        )

        return found

    print(
        f"[UYARI] Resmi sayfadan yalnızca {len(found)} kod bulundu."
    )

    return []


# ============================================================
# EVRENİ KAYDET
# ============================================================

def save_universe(symbols):

    df = pd.DataFrame({
        "symbol": symbols,
        "yahoo_symbol": [
            f"{x}.IS" for x in symbols
        ]
    })

    df.to_csv(
        UNIVERSE_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print(
        f"[EVREN KAYDEDİLDİ] {UNIVERSE_FILE}"
    )

    return df


# ============================================================
# CACHE DOSYA ADI
# ============================================================

def cache_file(symbol):

    safe = re.sub(
        r"[^A-Z0-9_-]",
        "_",
        symbol.upper()
    )

    return CACHE_DIR / f"{safe}.csv"


# ============================================================
# TEK HİSSE İNDİR
# ============================================================

def download_stock(symbol):

    yahoo_symbol = f"{symbol}.IS"

    output = cache_file(symbol)

    # Daha önce tamamen indirilmişse atla
    if output.exists():

        try:

            old = pd.read_csv(output)

            if len(old) >= 200:

                return "CACHE", len(old)

        except Exception:
            pass

    try:

        df = yf.download(
            yahoo_symbol,
            period=f"{YEARS}y",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False
        )

        if df is None or df.empty:

            return "EMPTY", 0

        # MultiIndex düzelt
        if isinstance(df.columns, pd.MultiIndex):

            df.columns = [
                c[0] if isinstance(c, tuple) else c
                for c in df.columns
            ]

        df = df.reset_index()

        # Kolonları standartlaştır
        rename = {}

        for c in df.columns:

            cc = str(c).strip().lower()

            if cc == "date":
                rename[c] = "Date"

            elif cc == "open":
                rename[c] = "Open"

            elif cc == "high":
                rename[c] = "High"

            elif cc == "low":
                rename[c] = "Low"

            elif cc == "close":
                rename[c] = "Close"

            elif cc == "adj close":
                rename[c] = "Adj Close"

            elif cc == "volume":
                rename[c] = "Volume"

        df = df.rename(columns=rename)

        required = [
            "Date",
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        for c in required:

            if c not in df.columns:

                if c == "Adj Close":
                    continue

                return "BAD", 0

        df = df[
            [
                c for c in [
                    "Date",
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Adj Close",
                    "Volume"
                ]
                if c in df.columns
            ]
        ]

        df = df.dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close"
            ]
        )

        if len(df) < 50:

            return "SHORT", len(df)

        df["Date"] = pd.to_datetime(
            df["Date"],
            errors="coerce"
        )

        df = df.dropna(
            subset=["Date"]
        )

        df = df.sort_values(
            "Date"
        )

        df["Symbol"] = symbol

        df.to_csv(
            output,
            index=False,
            encoding="utf-8-sig"
        )

        return "OK", len(df)

    except Exception as e:

        return "ERROR", str(e)


# ============================================================
# ANA İNDİRME
# ============================================================

def download_all(symbols):

    title("BIST HİSSELERİ 5 YILLIK VERİ İNDİRME")

    total = len(symbols)

    ok = 0
    cached = 0
    failed = 0

    failed_symbols = []

    for i, symbol in enumerate(symbols, 1):

        status, info = download_stock(symbol)

        if status == "OK":

            ok += 1

            print(
                f"[{i:5d}/{total}] "
                f"{symbol:<10} OK "
                f"({info} satır)"
            )

        elif status == "CACHE":

            cached += 1

            print(
                f"[{i:5d}/{total}] "
                f"{symbol:<10} CACHE "
                f"({info} satır)"
            )

        else:

            failed += 1
            failed_symbols.append(symbol)

            print(
                f"[{i:5d}/{total}] "
                f"{symbol:<10} "
                f"{status}"
            )

        # Yahoo'yu boğmamak için küçük bekleme
        time.sleep(0.08)

    # Hatalıları kaydet
    if failed_symbols:

        with open(
            FAILED_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            for s in failed_symbols:
                f.write(s + "\n")

    summary = pd.DataFrame([
        {
            "total": total,
            "new_download": ok,
            "cache": cached,
            "failed": failed
        }
    ])

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    return ok, cached, failed


# ============================================================
# TOPLU VERİ OLUŞTUR
# ============================================================

def create_combined_file():

    title("BIST VERİLERİ BİRLEŞTİRİLİYOR")

    files = list(
        CACHE_DIR.glob("*.csv")
    )

    all_data = []

    for file in files:

        try:

            df = pd.read_csv(file)

            if not df.empty:
                all_data.append(df)

        except Exception:
            continue

    if not all_data:

        print("[UYARI] Birleştirilecek veri yok.")
        return

    combined = pd.concat(
        all_data,
        ignore_index=True
    )

    combined_file = DATA_DIR / "bist_hisseler_5y.csv"

    combined.to_csv(
        combined_file,
        index=False,
        encoding="utf-8-sig"
    )

    print(
        f"[OK] Toplam satır: {len(combined):,}"
    )

    print(
        f"[OK] Dosya: {combined_file}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    title("LEVEL 1000 - TÜRKİYE BIST VERİ İNDİRİCİ")

    print(
        """
Kapsam:
  BIST Hisseleri

Veri:
  Yahoo Finance (.IS)

Geçmiş:
  5 yıl

Gerçek para:
  HAYIR

Otomatik emir:
  HAYIR
"""
    )

    # Eski yanlış universe dosyasını kullanma
    clean_old_files()

    # Önce TradingView Türkiye evreni
    symbols = get_bist_stocks()

    # Olmazsa BIST sayfası
    if len(symbols) < 100:

        symbols = get_bist_from_homepage()

    if len(symbols) < 100:

        print()
        print(
            "!!! BIST EVRENİ BULUNAMADI !!!"
        )

        print(
            "Eski 10.513 sembollük liste KESİNLİKLE kullanılmayacak."
        )

        return

    # Evreni kaydet
    save_universe(symbols)

    # İndir
    ok, cached, failed = download_all(
        symbols
    )

    # Birleştir
    create_combined_file()

    title("TAMAMLANDI")

    print(
        f"Toplam BIST hissesi : {len(symbols):,}"
    )

    print(
        f"Yeni indirilen      : {ok:,}"
    )

    print(
        f"Cache'den kullanılan : {cached:,}"
    )

    print(
        f"Başarısız            : {failed:,}"
    )

    print()
    print(
        f"Veri klasörü:"
    )

    print(
        DATA_DIR
    )

    print()
    print(
        "Programı tekrar çalıştırırsan mevcut cache dosyalarını"
    )

    print(
        "yeniden indirmez; kaldığı yerden devam eder."
    )


if __name__ == "__main__":
    main()