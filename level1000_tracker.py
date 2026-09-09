from pathlib import Path
from datetime import datetime
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "level1000_data"
TOP_FILE = DATA_DIR / "level1000_v2_current_top20.csv"
HISTORY_FILE = DATA_DIR / "TOP20_TAKIP.csv"


def main():
    DATA_DIR.mkdir(exist_ok=True)

    if not TOP_FILE.exists():
        print("TOP20 dosyasi bulunamadi:")
        print(TOP_FILE)
        print("\nOnce level1000_final_v2.py dosyasini calistir.")
        input("\nKapatmak icin Enter...")
        return

    df = pd.read_csv(TOP_FILE)

    ticker_col = next(
        (c for c in ["Ticker", "ticker", "Symbol", "symbol"] if c in df.columns),
        None
    )

    if ticker_col is None:
        print("Ticker sutunu bulunamadi.")
        print("Bulunan sutunlar:", list(df.columns))
        input("\nKapatmak icin Enter...")
        return

    df = df.head(20).copy()
    today = datetime.now().strftime("%Y-%m-%d")

    if HISTORY_FILE.exists():
        old = pd.read_csv(HISTORY_FILE)

        if "Date" in old.columns:
            old = old[old["Date"].astype(str) != today]
    else:
        old = pd.DataFrame(columns=[
            "Date", "Rank", "Ticker", "Score"
        ])

    score_col = next(
        (
            c for c in
            ["Score", "Fast_Score", "score"]
            if c in df.columns
        ),
        None
    )

    rows = []

    for i, (_, row) in enumerate(df.iterrows(), start=1):

        score = ""

        if score_col and pd.notna(row[score_col]):
            try:
                score = float(row[score_col])
            except:
                score = ""

        rows.append({
            "Date": today,
            "Rank": i,
            "Ticker": str(row[ticker_col]),
            "Score": score
        })

    new = pd.DataFrame(rows)

    result = pd.concat(
        [old, new],
        ignore_index=True
    )

    result = result.sort_values(
        ["Date", "Rank"]
    )

    result.to_csv(
        HISTORY_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print("=" * 60)
    print("LEVEL 1000 - GUNLUK TOP20 TAKIP")
    print("=" * 60)

    print("\nTarih:", today)
    print()

    print(
        new[
            ["Rank", "Ticker", "Score"]
        ].to_string(index=False)
    )

    print("\nKaydedildi:")
    print(HISTORY_FILE)

    dates = sorted(
        result["Date"]
        .astype(str)
        .unique()
    )

    if len(dates) >= 2:

        prev_date = dates[-2]

        prev = result[
            result["Date"].astype(str) == prev_date
        ]["Ticker"].astype(str).tolist()

        curr = new[
            "Ticker"
        ].astype(str).tolist()

        entered = [
            x for x in curr
            if x not in prev
        ]

        exited = [
            x for x in prev
            if x not in curr
        ]

        print("\nONCEKI GUN:", prev_date)

        print(
            "GIRENLER :",
            ", ".join(entered)
            if entered else "Yok"
        )

        print(
            "CIKANLAR :",
            ", ".join(exited)
            if exited else "Yok"
        )

    print("\nGercek para / otomatik emir YOK.")

    input("\nKapatmak icin Enter...")


if __name__ == "__main__":
    main()