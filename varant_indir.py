from pathlib import Path
import requests
import pandas as pd
import re
import zipfile
import io
import time
from datetime import datetime, timedelta


# ============================================================
# LEVEL 1000
# BIST TÜM VARANT VERİ TOPLAYICI
# ============================================================

BASE = Path(r"D:\Level1000Web\turkiye_data")

VARANT_FILE = BASE / "BIST_VARANTLAR_TEMIZ.csv"

OUT_DIR = BASE / "VARANT_VERI"
DAILY_DIR = OUT_DIR / "GUNLUK"

RESULT = OUT_DIR / "BIST_VARANT_TUM_VERI.csv"

DAILY_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# AYARLAR
# ============================================================

# Başlangıç tarihi
START_DATE = datetime(2015, 12, 1)

# Bitiş tarihi = bugün
END_DATE = datetime.now()

# BIST günlük bülten arşivi
ARCHIVE_URL = (
    "https://www.borsaistanbul.com/"
    "veriler/gunluk-bulten/gunluk-bulten-arsiv"
)


# ============================================================
# VARANT LİSTESİ
# ============================================================

if not VARANT_FILE.exists():

    print()
    print("[HATA] Varant listesi bulunamadı:")
    print(VARANT_FILE)
    raise SystemExit


df_codes = pd.read_csv(
    VARANT_FILE,
    dtype=str
)

df_codes.columns = [
    str(x).strip().upper()
    for x in df_codes.columns
]

if "KISA_KOD" not in df_codes.columns:

    print("[HATA] KISA_KOD kolonu yok.")
    print(df_codes.columns.tolist())
    raise SystemExit


codes = set(
    df_codes["KISA_KOD"]
    .dropna()
    .astype(str)
    .str.strip()
    .str.upper()
)

print("=" * 75)
print(" LEVEL 1000 - BIST TÜM VARANT VERİ TOPLAYICI")
print("=" * 75)

print()
print("Varant sayısı :", len(codes))
print("Başlangıç     :", START_DATE.strftime("%d.%m.%Y"))
print("Bitiş         :", END_DATE.strftime("%d.%m.%Y"))


# ============================================================
# SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
})


# ============================================================
# VARANT KOD REGEX
# ============================================================

VARANT_REGEX = re.compile(
    r"\b[A-Z0-9]{5}\.V\b",
    re.IGNORECASE
)


# ============================================================
# DOSYADAN VARANT BUL
# ============================================================

def extract_codes(text):

    found = VARANT_REGEX.findall(text)

    return {
        x.upper()
        for x in found
        if x.upper() in codes
    }


# ============================================================
# CSV İÇERİĞİ OKU
# ============================================================

def parse_text(text, source_date):

    rows = []

    # Satırlara ayır
    lines = text.splitlines()

    for line in lines:

        line = line.strip()

        if not line:
            continue

        found = VARANT_REGEX.findall(line)

        if not found:
            continue

        for code in found:

            code = code.upper()

            if code not in codes:
                continue

            # Noktalı virgül / virgül / tab
            if ";" in line:

                parts = [
                    x.strip()
                    for x in line.split(";")
                ]

            elif "\t" in line:

                parts = [
                    x.strip()
                    for x in line.split("\t")
                ]

            else:

                parts = [
                    x.strip()
                    for x in line.split(",")
                ]

            rows.append({
                "TARIH": source_date.strftime("%Y-%m-%d"),
                "KISA_KOD": code,
                "HAM_VERI": line
            })

    return rows


# ============================================================
# ZIP OKU
# ============================================================

def read_zip(content, source_date):

    rows = []

    try:

        z = zipfile.ZipFile(
            io.BytesIO(content)
        )

        names = z.namelist()

        for name in names:

            if name.endswith("/"):
                continue

            try:

                raw = z.read(name)

                text = raw.decode(
                    "utf-8",
                    errors="ignore"
                )

                rows.extend(
                    parse_text(
                        text,
                        source_date
                    )
                )

            except Exception:
                continue

    except Exception:
        pass

    return rows


# ============================================================
# TARİH ARALIĞI
# ============================================================

date = START_DATE

all_rows = []

total_days = (
    END_DATE - START_DATE
).days + 1

day_number = 0


# ============================================================
# ANA DÖNGÜ
# ============================================================

while date <= END_DATE:

    day_number += 1

    date_str = date.strftime(
        "%Y%m%d"
    )

    print()
    print(
        f"[{day_number}/{total_days}] "
        f"{date.strftime('%d.%m.%Y')}"
    )

    # Hafta sonu
    if date.weekday() >= 5:

        print("  [ATLA] Hafta sonu")

        date += timedelta(days=1)

        continue


    # --------------------------------------------------------
    # BIST günlük bülten için olası dosya yolları
    # --------------------------------------------------------

    candidates = [

        f"https://www.borsaistanbul.com/"
        f"files/{date_str}.zip",

        f"https://www.borsaistanbul.com/"
        f"files/gunlukbulten_{date_str}.zip",

        f"https://www.borsaistanbul.com/"
        f"files/bulten_{date_str}.zip",

        f"https://www.borsaistanbul.com/"
        f"files/{date_str}.csv",

    ]


    found_file = False


    # --------------------------------------------------------
    # ADAY URL'LERİ DENE
    # --------------------------------------------------------

    for url in candidates:

        try:

            r = session.get(
                url,
                timeout=15
            )

            if r.status_code != 200:
                continue

            content = r.content

            if len(content) < 500:
                continue

            found_file = True

            print(
                "  [DOSYA]",
                url
            )

            # ZIP
            if content[:2] == b"PK":

                rows = read_zip(
                    content,
                    date
                )

            else:

                text = content.decode(
                    "utf-8",
                    errors="ignore"
                )

                rows = parse_text(
                    text,
                    date
                )


            if rows:

                print(
                    "  [VARANT]",
                    len(rows)
                )

                all_rows.extend(rows)

            else:

                print(
                    "  [VARANT YOK]"
                )

            break

        except Exception:
            continue


    if not found_file:

        print(
            "  [DOSYA YOK / ERİŞİM GEREKLİ]"
        )


    # --------------------------------------------------------
    # HER 20 GÜNDE BİR ARA KAYDET
    # --------------------------------------------------------

    if day_number % 20 == 0:

        if all_rows:

            temp = pd.DataFrame(
                all_rows
            )

            temp.drop_duplicates(
                inplace=True
            )

            temp.to_csv(
                RESULT,
                index=False,
                encoding="utf-8-sig"
            )

            print(
                "  [ARA KAYIT]",
                len(temp)
            )


    date += timedelta(days=1)

    time.sleep(0.2)


# ============================================================
# SONUÇ
# ============================================================

print()
print("=" * 75)
print(" SONUÇ")
print("=" * 75)


if all_rows:

    result_df = pd.DataFrame(
        all_rows
    )

    result_df.drop_duplicates(
        inplace=True
    )

    result_df.sort_values(
        ["KISA_KOD", "TARIH"],
        inplace=True
    )

    result_df.to_csv(
        RESULT,
        index=False,
        encoding="utf-8-sig"
    )

    print(
        "Toplam kayıt :",
        len(result_df)
    )

    print(
        "Varant sayısı:",
        result_df["KISA_KOD"].nunique()
    )

    print(
        "Tarih sayısı :",
        result_df["TARIH"].nunique()
    )

    print()
    print("DOSYA:")
    print(RESULT)

else:

    print()
    print("Hiç veri indirilemedi.")
    print()
    print(
        "BIST günlük dosyaları erişim/URL "
        "nedeniyle indirilememiş olabilir."
    )

print()
print("=" * 75)
print("TAMAMLANDI")
print("=" * 75)