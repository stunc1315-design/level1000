from pathlib import Path
import pandas as pd

BASE_DIR = Path(r"D:\Level1000Web")
DATA_DIR = BASE_DIR / "level1000_data"

scan_file = DATA_DIR / "level1000_fast_scan.csv"
output_file = DATA_DIR / "level1000_latest_signals.csv"

print("Dosya okunuyor...")

scan = pd.read_csv(scan_file)

columns = [
    "Date",
    "Ticker",
    "Close",
    "AI_Probability",
    "AI_Predicted_Return",
    "Signal",
    "Strength"
]

buy = scan[scan["Signal"] == "BUY"].head(100)
hold = scan[scan["Signal"] == "HOLD"].head(100)
sell = scan[scan["Signal"] == "SELL"].tail(100)

latest = pd.concat(
    [buy, hold, sell],
    ignore_index=True
)

latest = latest[columns]

latest.to_csv(
    output_file,
    index=False,
    encoding="utf-8-sig"
)

print()
print("====================================")
print("İŞLEM TAMAMLANDI")
print("====================================")
print("BUY  :", len(buy))
print("HOLD :", len(hold))
print("SELL :", len(sell))
print()
print("Oluşturulan dosya:")
print(output_file)
print()
input("Kapatmak için Enter'a bas...")