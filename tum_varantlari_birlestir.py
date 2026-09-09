from pathlib import Path
import re
import pandas as pd

# ============================================================
# LEVEL 1000 - TÜM BIST VARANT KODLARINI BİRLEŞTİR
# ============================================================

BASE_DIR = Path(r"D:\Level1000Web\turkiye_data")
OUTPUT = BASE_DIR / "BIST_TUM_VARANTLAR.csv"

print("=" * 70)
print(" BIST TÜM VARANT KODLARI TOPLAMA")
print("=" * 70)

# Okunacak dosya uzantıları
EXTENSIONS = {
    ".csv",
    ".txt",
    ".html",
    ".htm",
    ".xlsx"
}

# Örnek:
# AB1II.V
# SA1JN.V
# TABCX.V
#
# BIST varant kısa kodu:
# 5 karakter + .V
PATTERN = re.compile(r"\b[A-Z0-9]{5}\.V\b", re.IGNORECASE)

all_codes = set()
source_count = 0

# ============================================================
# TÜM DOSYALARI TARA
# ============================================================

for file in BASE_DIR.rglob("*"):

    if not file.is_file():
        continue

    if file.suffix.lower() not in EXTENSIONS:
        continue

    # Çıktı dosyasını tekrar okuma
    if file.name == OUTPUT.name:
        continue

    print(f"[TARA] {file.name}")

    try:

        # XLSX
        if file.suffix.lower() == ".xlsx":

            try:
                sheets = pd.read_excel(
                    file,
                    sheet_name=None,
                    dtype=str
                )

                text = ""

                for df in sheets.values():
                    text += " ".join(
                        df.fillna("").astype(str).values.flatten()
                    ) + " "

            except Exception as e:
                print(f"   [XLSX HATA] {e}")
                continue

        # CSV / TXT / HTML
        else:

            raw = None

            for encoding in [
                "utf-8",
                "utf-8-sig",
                "cp1254",
                "latin1"
            ]:

                try:
                    raw = file.read_text(
                        encoding=encoding,
                        errors="ignore"
                    )
                    break

                except Exception:
                    pass

            if raw is None:
                print("   [OKUNAMADI]")
                continue

            text = raw

        # ====================================================
        # VARANT KODLARINI BUL
        # ====================================================

        found = PATTERN.findall(text)

        found = {
            x.upper()
            for x in found
        }

        if found:

            before = len(all_codes)

            all_codes.update(found)

            added = len(all_codes) - before

            print(
                f"   Bulunan: {len(found):,} | "
                f"Yeni: {added:,}"
            )

            source_count += 1

        else:
            print("   Varant bulunamadı")

    except Exception as e:

        print(f"   [HATA] {e}")


# ============================================================
# SONUÇ
# ============================================================

codes = sorted(all_codes)

print()
print("=" * 70)
print(" SONUÇ")
print("=" * 70)

print(f"Taranan kaynak : {source_count:,}")
print(f"Toplam benzersiz varant : {len(codes):,}")

# ============================================================
# CSV OLUŞTUR
# ============================================================

df = pd.DataFrame({
    "KISA_KOD": codes
})

df.to_csv(
    OUTPUT,
    index=False,
    encoding="utf-8-sig"
)

print()
print(f"[KAYDEDİLDİ]")
print(OUTPUT)

# ============================================================
# İLK / SON KODLAR
# ============================================================

print()
print("İLK 30:")

for code in codes[:30]:
    print(code)

print()
print("SON 30:")

for code in codes[-30:]:
    print(code)

print()
print("=" * 70)
print("TAMAMLANDI")
print("=" * 70)