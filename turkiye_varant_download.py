# ============================================================
# LEVEL 1000 - VARANT VERİ İNDİRİCİ
# 1.902 GERÇEK BIST VARANTI
# ============================================================

from pathlib import Path
import time
import warnings
import concurrent.futures

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf


# ============================================================
# AYARLAR
# ============================================================

BASE_DIR = Path(r"D:\Level1000Web")
DATA_DIR = BASE_DIR / "turkiye_data"

SYMBOL_FILE = DATA_DIR / "bist_varantlar.csv"

OUTPUT_DIR = DATA_DIR / "varant_data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OK_FILE = DATA_DIR / "bist_varantlar_indirilen.csv"
FAIL_FILE = DATA_DIR / "bist_varantlar_indirilemeyen.csv"

# Yahoo için maksimum paralel istek
WORKERS = 12

# Yahoo'da önce 5 yıllık veri denenir
PERIOD = "5y"

# 1 saatlik değil, günlük veri
INTERVAL = "1d"


# ============================================================
# BAŞLANGIÇ
# ============================================================

print("=" * 70)
print(" LEVEL 1000 - VARANT VERİ İNDİRİCİ")
print("=" * 70)

if not SYMBOL_FILE.exists():
    print()
    print("[HATA] Varant listesi bulunamadı:")
    print(SYMBOL_FILE)
    print()
    input("Enter...")
    raise SystemExit


# ============================================================
# VARANT LİSTESİNİ OKU
# ============================================================

df_symbols = pd.read_csv(SYMBOL_FILE)

print()
print("[OK] CSV bulundu")
print(f"[OK] Satır sayısı: {len(df_symbols):,}")


# CSV'nin ilk sütunundan sembolleri bul
symbols = []

for col in df_symbols.columns:
    vals = (
        df_symbols[col]
        .astype(str)
        .str.upper()
        .str.strip()
        .tolist()
    )

    for value in vals:

        if (
            len(value) == 7
            and value.endswith(".V")
            and value[:5].isalnum()
        ):
            symbols.append(value)


# Tekilleştir
symbols = sorted(set(symbols))

print(f"[OK] Gerçek varant: {len(symbols):,}")


if not symbols:
    print("[HATA] .V formatında varant bulunamadı.")
    input("Enter...")
    raise SystemExit


# ============================================================
# ÖNCEKİ SONUÇLARI OKU
# ============================================================

downloaded = set()

if OK_FILE.exists():

    try:

        old = pd.read_csv(OK_FILE)

        for col in old.columns:

            for x in old[col].astype(str):

                x = x.upper().strip()

                if (
                    len(x) == 7
                    and x.endswith(".V")
                    and x[:5].isalnum()
                ):
                    downloaded.add(x)

    except Exception:
        pass


# ============================================================
# DAHA ÖNCE İNDİRİLENLERİ ATLAMA
# ============================================================

remaining = [
    x for x in symbols
    if x not in downloaded
]

print()
print(f"[OK] Daha önce indirilen: {len(downloaded):,}")
print(f"[OK] Kalan: {len(remaining):,}")


if not remaining:

    print()
    print("Tüm varantlar daha önce indirilmiş.")
    print()
    input("Enter...")
    raise SystemExit


# ============================================================
# TEK VARANT İNDİR
# ============================================================

def download_one(symbol):

    try:

        # ====================================================
        # .V kodunu Yahoo formatında dene
        # ====================================================

        ticker = yf.Ticker(symbol)

        data = ticker.history(
            period=PERIOD,
            interval=INTERVAL,
            auto_adjust=False,
            actions=False
        )

        if data is None:
            return symbol, False, 0, "Boş sonuç"

        if data.empty:
            return symbol, False, 0, "Veri yok"

        # ====================================================
        # Sütunları temizle
        # ====================================================

        data = data.reset_index()

        # Tarih sütunu
        if "Date" in data.columns:
            data["Date"] = pd.to_datetime(
                data["Date"],
                errors="coerce"
            )

        # NaN tarihleri sil
        if "Date" in data.columns:
            data = data.dropna(subset=["Date"])

        if len(data) < 2:
            return symbol, False, len(data), "Yetersiz veri"

        # ====================================================
        # CSV
        # ====================================================

        output_file = OUTPUT_DIR / f"{symbol}.csv"

        data.to_csv(
            output_file,
            index=False,
            encoding="utf-8-sig"
        )

        return symbol, True, len(data), "OK"

    except Exception as e:

        msg = str(e).replace("\n", " ")[:180]

        return symbol, False, 0, msg


# ============================================================
# BAŞLA
# ============================================================

print()
print("=" * 70)
print(" VARANT VERİ İNDİRME BAŞLIYOR")
print("=" * 70)
print()
print(f"Toplam: {len(remaining):,}")
print(f"Paralel işçi: {WORKERS}")
print(f"Periyot: {PERIOD}")
print(f"Aralık: {INTERVAL}")
print()


ok = []
failed = []

start_time = time.time()

completed = 0


# ============================================================
# PARALEL İNDİRME
# ============================================================

with concurrent.futures.ThreadPoolExecutor(
    max_workers=WORKERS
) as executor:

    futures = {
        executor.submit(download_one, symbol): symbol
        for symbol in remaining
    }

    for future in concurrent.futures.as_completed(futures):

        symbol = futures[future]

        try:

            sym, success, rows, message = future.result()

        except Exception as e:

            sym = symbol
            success = False
            rows = 0
            message = str(e)

        completed += 1

        if success:

            ok.append({
                "symbol": sym,
                "rows": rows
            })

            print(
                f"[{completed:04d}/{len(remaining):04d}] "
                f"[OK] {sym:<10} "
                f"{rows:>6,} satır"
            )

        else:

            failed.append({
                "symbol": sym,
                "rows": rows,
                "error": message
            })

            print(
                f"[{completed:04d}/{len(remaining):04d}] "
                f"[ATLA] {sym:<10} "
                f"{message}"
            )


# ============================================================
# SÜRE
# ============================================================

elapsed = time.time() - start_time


# ============================================================
# BAŞARILI LİSTE
# ============================================================

if ok:

    new_ok = pd.DataFrame(ok)

    if OK_FILE.exists():

        try:

            old_ok = pd.read_csv(OK_FILE)

            combined = pd.concat(
                [old_ok, new_ok],
                ignore_index=True
            )

        except Exception:

            combined = new_ok

    else:

        combined = new_ok

    combined = combined.drop_duplicates(
        subset=["symbol"]
    )

    combined.to_csv(
        OK_FILE,
        index=False,
        encoding="utf-8-sig"
    )


# ============================================================
# BAŞARISIZ LİSTE
# ============================================================

if failed:

    fail_df = pd.DataFrame(failed)

    fail_df.to_csv(
        FAIL_FILE,
        index=False,
        encoding="utf-8-sig"
    )


# ============================================================
# SONUÇ
# ============================================================

print()
print("=" * 70)
print(" SONUÇ")
print("=" * 70)

print(f"Toplam varant       : {len(symbols):,}")
print(f"Bu tur indirilen    : {len(ok):,}")
print(f"Bu tur başarısız    : {len(failed):,}")
print(f"Toplam süre         : {elapsed / 60:.1f} dakika")

print()
print(f"Veriler             : {OUTPUT_DIR}")
print(f"Başarılı liste      : {OK_FILE}")
print(f"Başarısız liste     : {FAIL_FILE}")

print()
print("=" * 70)
print(" İLK BAŞARILI VERİLER")
print("=" * 70)

for item in ok[:20]:

    print(
        f"{item['symbol']:<10} "
        f"{item['rows']:>7,} satır"
    )

print()
print("=" * 70)
print(" TAMAMLANDI")
print("=" * 70)

input("Çıkmak için Enter...")