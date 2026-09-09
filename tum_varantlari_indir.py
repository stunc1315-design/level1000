# ============================================================
# LEVEL 1000 - TÜM BIST VARANTLARI TOPLA + VERİ İNDİR
# ============================================================

from pathlib import Path
import re
import time
import warnings
import requests
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ============================================================
# AYARLAR
# ============================================================

BASE_DIR = Path(r"D:\Level1000Web")
DATA_DIR = BASE_DIR / "turkiye_data"
VARANT_DIR = DATA_DIR / "varant_data"

DATA_DIR.mkdir(parents=True, exist_ok=True)
VARANT_DIR.mkdir(parents=True, exist_ok=True)

BNP_FILE = DATA_DIR / "bist_varantlar.csv"

ALL_CODES_FILE = DATA_DIR / "bist_varantlar_tum.csv"
DOWNLOADED_FILE = DATA_DIR / "bist_varantlar_indirilen.csv"
FAILED_FILE = DATA_DIR / "bist_varantlar_indirilemeyenler.csv"

# ============================================================
# HTTP
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
})


# ============================================================
# VARANT KODU FİLTRESİ
# ============================================================

def temiz_varant_kodlari(text):

    if not text:
        return set()

    text = str(text).upper()

    bulunan = set()

    # 5 karakter + .V
    desen1 = re.findall(
        r"\b[A-Z0-9]{5}\.V\b",
        text
    )

    for kod in desen1:
        bulunan.add(kod)

    # "kısa kod XXXXX" şeklindeki KAP metinleri
    desen2 = re.findall(
        r"(?:KISA\s*KOD|VARANT\s*KISA\s*KOD)\s+([A-Z0-9]{5})\b",
        text,
        flags=re.IGNORECASE
    )

    for kod in desen2:
        kod = kod.upper().strip()

        if re.fullmatch(r"[A-Z0-9]{5}", kod):
            bulunan.add(kod + ".V")

    return bulunan


# ============================================================
# 1 - ESKİ BNP LİSTESİNİ OKU
# ============================================================

def bnp_listesi():

    kodlar = set()

    if not BNP_FILE.exists():
        print("[BNP] Dosya bulunamadı:")
        print(BNP_FILE)
        return kodlar

    try:

        df = pd.read_csv(
            BNP_FILE,
            dtype=str,
            encoding="utf-8-sig"
        )

        for col in df.columns:

            for value in df[col].dropna():

                value = str(value).strip().upper()

                if re.fullmatch(r"[A-Z0-9]{5}\.V", value):
                    kodlar.add(value)

                elif re.fullmatch(r"[A-Z0-9]{5}", value):
                    kodlar.add(value + ".V")

        print(f"[BNP] {len(kodlar):,} kod bulundu.")

    except Exception as e:
        print("[BNP HATA]", e)

    return kodlar


# ============================================================
# 2 - KAP ARAMA
# ============================================================

def kap_arama():

    kodlar = set()

    # KAP'ta 2026 boyunca görülen varant bildirimleri
    # Sayfalar değişebildiği için birden fazla arama yapılır.

    urls = [

        "https://www.kap.org.tr/tr/Bildirim/1621733",
        "https://www.kap.org.tr/tr/Bildirim/1639074",
        "https://www.kap.org.tr/tr/Bildirim/1610884",
        "https://www.kap.org.tr/tr/Bildirim/1576059",
        "https://www.kap.org.tr/tr/Bildirim/1562363",

    ]

    print()
    print("=" * 70)
    print(" KAP VARANT TARAMASI")
    print("=" * 70)

    for i, url in enumerate(urls, 1):

        try:

            print(f"[KAP {i}/{len(urls)}]")

            r = session.get(
                url,
                timeout=30
            )

            if r.status_code != 200:
                print("  HTTP:", r.status_code)
                continue

            yeni = temiz_varant_kodlari(r.text)

            print(
                f"  Bulunan: {len(yeni):,}"
            )

            kodlar.update(yeni)

            time.sleep(0.5)

        except Exception as e:

            print(
                "  HATA:",
                str(e)[:150]
            )

    print(
        f"[KAP TOPLAM] {len(kodlar):,}"
    )

    return kodlar


# ============================================================
# 3 - GENEL WEB TARAMASI
# ============================================================

def web_varant_taramasi():

    kodlar = set()

    urls = [

        # İş Varant
        "https://isvarant.com/varant-nedir/varant-ihraclari",

        # BNP
        "https://www.varant.bnpparibas.com.tr/products/",

        # Ak Yatırım
        "https://varant.akyatirim.com.tr/",

    ]

    print()
    print("=" * 70)
    print(" İHRAÇÇI SİTELERİ TARAMA")
    print("=" * 70)

    for url in urls:

        try:

            print()
            print("[WEB]", url)

            r = session.get(
                url,
                timeout=30
            )

            print(
                " HTTP:",
                r.status_code,
                "|",
                len(r.text),
                "byte"
            )

            if r.status_code != 200:
                continue

            yeni = temiz_varant_kodlari(r.text)

            print(
                " Bulunan:",
                len(yeni)
            )

            kodlar.update(yeni)

        except Exception as e:

            print(
                " HATA:",
                str(e)[:150]
            )

    print()
    print(
        "[WEB TOPLAM]",
        len(kodlar)
    )

    return kodlar


# ============================================================
# 4 - KODLARI BİRLEŞTİR
# ============================================================

print()
print("=" * 70)
print(" LEVEL 1000 - TÜM VARANTLAR")
print("=" * 70)

tum_kodlar = set()

tum_kodlar.update(
    bnp_listesi()
)

tum_kodlar.update(
    kap_arama()
)

tum_kodlar.update(
    web_varant_taramasi()
)

# sadece gerçek 5 karakter + .V
tum_kodlar = {
    x.upper()
    for x in tum_kodlar
    if re.fullmatch(
        r"[A-Z0-9]{5}\.V",
        x.upper()
    )
}

tum_kodlar = sorted(tum_kodlar)

print()
print("=" * 70)
print(" VARANT KOD SONUCU")
print("=" * 70)

print(
    "Toplam benzersiz kod:",
    f"{len(tum_kodlar):,}"
)


# ============================================================
# 5 - TÜM KODLARI CSV
# ============================================================

df_codes = pd.DataFrame({
    "KISA_KOD": tum_kodlar
})

df_codes.to_csv(
    ALL_CODES_FILE,
    index=False,
    encoding="utf-8-sig"
)

print()
print("[OK]",
      ALL_CODES_FILE)


# ============================================================
# 6 - DAHA ÖNCE İNDİRİLENLERİ OKU
# ============================================================

indirilen = set()

if DOWNLOADED_FILE.exists():

    try:

        eski = pd.read_csv(
            DOWNLOADED_FILE,
            dtype=str,
            encoding="utf-8-sig"
        )

        if "KISA_KOD" in eski.columns:

            indirilen = set(
                eski["KISA_KOD"]
                .dropna()
                .astype(str)
                .str.upper()
            )

    except:
        pass


# ============================================================
# 7 - YAHOO VERİ İNDİRME
# ============================================================

basarili = []
basarisiz = []

print()
print("=" * 70)
print(" TARİHSEL VERİ İNDİRME")
print("=" * 70)

print(
    "Başlanacak:",
    f"{len(tum_kodlar):,}"
)

for index, kod in enumerate(tum_kodlar, 1):

    if kod in indirilen:

        print(
            f"[{index}/{len(tum_kodlar)}] "
            f"{kod} -> DAHA ÖNCE İNDİRİLDİ"
        )

        basarili.append(kod)

        continue

    print()
    print("-" * 70)

    print(
        f"[{index}/{len(tum_kodlar)}]",
        kod
    )

    try:

        # Yahoo formatı
        ticker = kod

        df = yf.download(
            ticker,
            period="max",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False
        )

        if df is None or df.empty:

            print(
                "[ATLA] Veri yok"
            )

            basarisiz.append({
                "KISA_KOD": kod,
                "HATA": "Veri yok"
            })

            continue

        # MultiIndex temizle
        if isinstance(df.columns, pd.MultiIndex):

            try:
                df.columns = df.columns.get_level_values(0)
            except:
                pass

        df = df.reset_index()

        # Tarih kolonunu düzelt
        if "Date" in df.columns:

            df["Date"] = pd.to_datetime(
                df["Date"],
                errors="coerce"
            )

        # dosya adı
        temiz_ad = kod.replace(
            ".",
            "_"
        )

        out_file = (
            VARANT_DIR /
            f"{temiz_ad}.csv"
        )

        df.to_csv(
            out_file,
            index=False,
            encoding="utf-8-sig"
        )

        basarili.append(kod)

        print(
            "[OK]",
            len(df),
            "satır"
        )

    except Exception as e:

        hata = str(e)

        print(
            "[HATA]",
            hata[:200]
        )

        basarisiz.append({
            "KISA_KOD": kod,
            "HATA": hata[:500]
        })

    # Yahoo'yu boğmamak için
    time.sleep(0.25)


# ============================================================
# 8 - SONUÇLARI KAYDET
# ============================================================

pd.DataFrame({
    "KISA_KOD": sorted(set(basarili))
}).to_csv(
    DOWNLOADED_FILE,
    index=False,
    encoding="utf-8-sig"
)


pd.DataFrame(
    basarisiz
).to_csv(
    FAILED_FILE,
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# 9 - SONUÇ
# ============================================================

print()
print()
print("=" * 70)
print(" TAMAMLANDI")
print("=" * 70)

print(
    "Toplam varant kodu :",
    f"{len(tum_kodlar):,}"
)

print(
    "İndirilen           :",
    f"{len(set(basarili)):,}"
)

print(
    "İndirilemeyen       :",
    f"{len(basarisiz):,}"
)

print()
print("KOD LİSTESİ:")
print(
    ALL_CODES_FILE
)

print()
print("İNDİRİLEN VERİLER:")
print(
    VARANT_DIR
)

print()
print("İNDİRİLEMEYENLER:")
print(
    FAILED_FILE
)

print()
print("=" * 70)
print(" LEVEL 1000 VARANT TARAMASI BİTTİ")
print("=" * 70)

input(
    "\nKapatmak için ENTER'a bas..."
)