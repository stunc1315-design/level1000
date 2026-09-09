from pathlib import Path
import pandas as pd
import re

# ============================================================
# LEVEL 1000 - VARANT LİSTESİ KONTROL
# ============================================================

FILE = Path(r"D:\Level1000Web\turkiye_data\BIST_TUM_VARANTLAR.csv")

print("=" * 70)
print(" LEVEL 1000 - 5.349 VARANT KONTROL")
print("=" * 70)

df = pd.read_csv(FILE, dtype=str)

# Kolon temizle
df.columns = [str(x).strip().upper() for x in df.columns]

col = "KISA_KOD"

if col not in df.columns:
    print("HATA: KISA_KOD kolonu bulunamadı.")
    print("Kolonlar:", df.columns.tolist())
    raise SystemExit

codes = (
    df[col]
    .dropna()
    .astype(str)
    .str.strip()
    .str.upper()
)

# ============================================================
# FORMAT KONTROL
# ============================================================

pattern = re.compile(r"^[A-Z0-9]{5}\.V$")

valid = []
invalid = []

for code in codes:

    if pattern.fullmatch(code):
        valid.append(code)
    else:
        invalid.append(code)

# ============================================================
# DUPLICATE KONTROL
# ============================================================

unique_codes = sorted(set(valid))

duplicates = len(valid) - len(unique_codes)

# ============================================================
# İSTATİSTİK
# ============================================================

print()
print("=" * 70)
print(" SONUÇ")
print("=" * 70)

print(f"Dosyadaki satır       : {len(codes):,}")
print(f"Geçerli format        : {len(valid):,}")
print(f"Geçersiz format       : {len(invalid):,}")
print(f"Tekrarlanan           : {duplicates:,}")
print(f"Benzersiz geçerli     : {len(unique_codes):,}")

# ============================================================
# İLK / SON KODLAR
# ============================================================

print()
print("İLK 50")

for x in unique_codes[:50]:
    print(x)

print()
print("SON 50")

for x in unique_codes[-50:]:
    print(x)

# ============================================================
# GEÇERSİZLER
# ============================================================

if invalid:

    print()
    print("=" * 70)
    print(" GEÇERSİZ KODLAR")
    print("=" * 70)

    for x in invalid[:100]:
        print(x)

# ============================================================
# TEMİZ LİSTEYİ KAYDET
# ============================================================

OUTPUT = FILE.parent / "BIST_VARANTLAR_TEMIZ.csv"

out = pd.DataFrame({
    "KISA_KOD": unique_codes
})

out.to_csv(
    OUTPUT,
    index=False,
    encoding="utf-8-sig"
)

print()
print("=" * 70)
print("TEMİZ LİSTE KAYDEDİLDİ")
print("=" * 70)

print(OUTPUT)