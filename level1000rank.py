from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "level1000_data"

HISTORY_FILE = DATA_DIR / "TOP20_TAKIP.csv"
RANK_FILE = DATA_DIR / "level1000_current_top20.csv"


def find_scan_file():
    candidates = [
        "level1000_v3_scan.csv",
        "level1000_fast_scan.csv",
        "level1000_scan.csv",
        "level1000_latest_signals.csv",
    ]

    for filename in candidates:
        path = DATA_DIR / filename

        if path.exists():
            return path

    return None


def number(value, default=0.0):
    try:
        if pd.isna(value):
            return default

        return float(value)

    except Exception:
        return default


def find_column(df, candidates):
    for column in candidates:
        if column in df.columns:
            return column

    return None


def calculate_rank_score(row):

    buy_prob = number(row.get("BUY_Probability", 0))
    sell_prob = number(row.get("SELL_Probability", 0))
    hold_prob = number(row.get("HOLD_Probability", 0))

    fast_score = number(row.get("Fast_Score", 0))
    buy_score = number(row.get("BUY_Score", 0))
    sell_score = number(row.get("SELL_Score", 0))

    expected = number(row.get("Expected_Return_Pct", 0))

    if 0 < buy_prob <= 1:
        buy_prob *= 100

    if 0 < sell_prob <= 1:
        sell_prob *= 100

    if 0 < hold_prob <= 1:
        hold_prob *= 100

    buy_prob = np.clip(buy_prob, 0, 100)
    sell_prob = np.clip(sell_prob, 0, 100)
    hold_prob = np.clip(hold_prob, 0, 100)

    fast_score = np.clip(fast_score, 0, 100)
    buy_score = np.clip(buy_score, 0, 100)
    sell_score = np.clip(sell_score, 0, 100)

    expected = np.clip(expected, -15, 15)

    direction_probability = max(
        buy_prob,
        sell_prob
    )

    direction_edge = abs(
        buy_prob - sell_prob
    )

    buy_component = (
        buy_prob * 0.45
        + buy_score * 0.30
        + fast_score * 0.15
        + max(expected, 0) * 0.67
    )

    sell_component = (
        sell_prob * 0.45
        + sell_score * 0.30
        + (100 - fast_score) * 0.15
        + max(-expected, 0) * 0.67
    )

    direction_score = max(
        buy_component,
        sell_component
    )

    strength = (
        direction_probability * 0.55
        + direction_edge * 0.25
        + direction_score * 0.20
    )

    return round(
        float(np.clip(strength, 0, 100)),
        2
    )


def determine_signal(row):

    signal = str(
        row.get("Signal", "")
    ).upper().strip()

    model_signal = str(
        row.get("Model_Signal", "")
    ).upper().strip()

    if signal in {
        "BUY",
        "SELL",
        "HOLD",
        "WATCH"
    }:

        if signal == "WATCH":

            if model_signal in {
                "BUY",
                "SELL",
                "HOLD"
            }:
                return model_signal

            return "HOLD"

        return signal

    if model_signal in {
        "BUY",
        "SELL",
        "HOLD"
    }:
        return model_signal

    return "HOLD"


def get_expected_return(row):

    candidates = [
        "Expected_Return_Pct",
        "Expected_Return",
        "AI_Predicted_Return",
        "Predicted_Return",
    ]

    for column in candidates:

        if column in row.index:

            value = number(
                row[column],
                0
            )

            if abs(value) <= 1 and value != 0:
                value *= 100

            value = np.clip(
                value,
                -15,
                15
            )

            return round(
                float(value),
                2
            )

    return 0.0


def main():

    DATA_DIR.mkdir(
        exist_ok=True
    )

    print()
    print("=" * 70)
    print(" LEVEL 1000 AI - TOP 20 RANKING")
    print("=" * 70)
    print()

    scan_file = find_scan_file()

    if scan_file is None:

        print(
            "[HATA] Tarama dosyasi bulunamadi."
        )

        print()
        print("Aranan dosyalar:")
        print(" - level1000_v3_scan.csv")
        print(" - level1000_fast_scan.csv")
        print(" - level1000_scan.csv")
        print(" - level1000_latest_signals.csv")
        print()

        print(
            "Once level1000_fast.py dosyasini calistir."
        )

        return

    print(
        "[OK] Tarama dosyasi:",
        scan_file.name
    )

    try:

        df = pd.read_csv(
            scan_file
        )

    except Exception as e:

        print()
        print(
            "[HATA] CSV okunamadi:"
        )

        print(e)

        return

    if df.empty:

        print()
        print(
            "[HATA] Tarama dosyasi bos."
        )

        return

    print(
        "[OK] Satir sayisi:",
        len(df)
    )

    ticker_col = find_column(
        df,
        [
            "Ticker",
            "ticker",
            "Symbol",
            "symbol"
        ]
    )

    if ticker_col is None:

        print()
        print(
            "[HATA] Ticker kolonu bulunamadi."
        )

        print(
            "Kolonlar:",
            list(df.columns)
        )

        return

    df = df.copy()

    df[ticker_col] = (
        df[ticker_col]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df = df[
        df[ticker_col].notna()
    ]

    df = df[
        df[ticker_col] != ""
    ]

    df = df[
        df[ticker_col] != "NAN"
    ]

    print(
        "[OK] Temizlenen satir:",
        len(df)
    )

    df["Rank_Score"] = df.apply(
        calculate_rank_score,
        axis=1
    )

    df["Rank_Signal"] = df.apply(
        determine_signal,
        axis=1
    )

    df["Rank_Expected_Return"] = df.apply(
        get_expected_return,
        axis=1
    )

    df["Strength"] = df["Rank_Score"]

    df = df.sort_values(
        "Rank_Score",
        ascending=False
    )

    df = df.drop_duplicates(
        subset=[ticker_col],
        keep="first"
    )

    top20 = df.head(20).copy()

    # Mevcut Date kolonunu tamamen kaldır.
    if "Date" in top20.columns:
        top20 = top20.drop(
            columns=["Date"]
        )

    # Mevcut Rank kolonu varsa onu da kaldır.
    if "Rank" in top20.columns:
        top20 = top20.drop(
            columns=["Rank"]
        )

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    top20.insert(
        0,
        "Rank",
        range(
            1,
            len(top20) + 1
        )
    )

    top20.insert(
        1,
        "Date",
        today
    )

    output_columns = [
        "Rank",
        "Date",
        ticker_col,
        "Rank_Signal",
        "Strength",
        "Rank_Score",
        "Rank_Expected_Return",
    ]

    optional_columns = [
        "Close",
        "AI_Probability",
        "BUY_Probability",
        "HOLD_Probability",
        "SELL_Probability",
        "Fast_Score",
        "BUY_Score",
        "SELL_Score",
        "RSI14",
        "Return_5D",
        "Return_20D",
        "Volume_Ratio",
        "ATR_Pct",
        "Model_Signal",
        "Signal",
    ]

    for column in optional_columns:

        if column in top20.columns:
            output_columns.append(
                column
            )

    output_columns = list(
        dict.fromkeys(
            output_columns
        )
    )

    top20_output = top20[
        [
            c
            for c in output_columns
            if c in top20.columns
        ]
    ].copy()

    if ticker_col != "Ticker":

        top20_output = top20_output.rename(
            columns={
                ticker_col: "Ticker"
            }
        )

    top20_output.to_csv(
        RANK_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    history_rows = []

    for _, row in top20_output.iterrows():

        history_rows.append(
            {
                "Date": today,

                "Rank": int(
                    number(
                        row.get(
                            "Rank",
                            0
                        )
                    )
                ),

                "Ticker": str(
                    row.get(
                        "Ticker",
                        ""
                    )
                ),

                "Signal": str(
                    row.get(
                        "Rank_Signal",
                        "HOLD"
                    )
                ),

                "Strength": number(
                    row.get(
                        "Strength",
                        0
                    )
                ),

                "Score": number(
                    row.get(
                        "Rank_Score",
                        0
                    )
                ),

                "Expected_Return": number(
                    row.get(
                        "Rank_Expected_Return",
                        0
                    )
                ),
            }
        )

    new_history = pd.DataFrame(
        history_rows
    )

    if HISTORY_FILE.exists():

        try:
            old_history = pd.read_csv(
                HISTORY_FILE
            )

        except Exception:
            old_history = pd.DataFrame()

    else:
        old_history = pd.DataFrame()

    if (
        not old_history.empty
        and "Date" in old_history.columns
    ):

        old_history = old_history[
            old_history["Date"]
            .astype(str)
            != today
        ]

    history = pd.concat(
        [
            old_history,
            new_history
        ],
        ignore_index=True
    )

    if not history.empty:

        history = history.drop_duplicates(
            subset=[
                "Date",
                "Rank",
                "Ticker"
            ],
            keep="last"
        )

        history = history.sort_values(
            [
                "Date",
                "Rank"
            ]
        )

    history.to_csv(
        HISTORY_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print("-" * 70)
    print(" TOP 20")
    print("-" * 70)

    display_columns = [
        "Rank",
        "Ticker",
        "Rank_Signal",
        "Strength",
        "Rank_Score",
        "Rank_Expected_Return",
    ]

    display_columns = [
        c
        for c in display_columns
        if c in top20_output.columns
    ]

    print(
        top20_output[
            display_columns
        ].to_string(
            index=False
        )
    )

    print()
    print("-" * 70)
    print(" SINYAL OZETI")
    print("-" * 70)

    signal_series = (
        top20_output[
            "Rank_Signal"
        ]
        .astype(str)
        .str.upper()
    )

    buy_count = int(
        (
            signal_series == "BUY"
        ).sum()
    )

    sell_count = int(
        (
            signal_series == "SELL"
        ).sum()
    )

    hold_count = int(
        (
            signal_series == "HOLD"
        ).sum()
    )

    print(
        "BUY :",
        buy_count
    )

    print(
        "SELL:",
        sell_count
    )

    print(
        "HOLD:",
        hold_count
    )

    if not history.empty:

        dates = sorted(
            history["Date"]
            .astype(str)
            .unique()
        )

        if len(dates) >= 2:

            previous_date = dates[-2]

            previous = history[
                history["Date"]
                .astype(str)
                == previous_date
            ]["Ticker"].astype(str).tolist()

            current = top20_output[
                "Ticker"
            ].astype(str).tolist()

            entered = [
                ticker
                for ticker in current
                if ticker not in previous
            ]

            exited = [
                ticker
                for ticker in previous
                if ticker not in current
            ]

            print()
            print("-" * 70)
            print(
                " ONCEKI GUN:",
                previous_date
            )
            print("-" * 70)

            print(
                "GIRENLER:",
                ", ".join(entered)
                if entered
                else "Yok"
            )

            print(
                "CIKANLAR:",
                ", ".join(exited)
                if exited
                else "Yok"
            )

    print()
    print("=" * 70)
    print(" TAMAMLANDI")
    print("=" * 70)
    print()

    print(
        "Current TOP20:"
    )

    print(
        RANK_FILE
    )

    print()

    print(
        "TOP20 gecmisi:"
    )

    print(
        HISTORY_FILE
    )

    print()

    print(
        "Gercek para / otomatik emir YOK."
    )

    print()


if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print(
            "Islem kullanici tarafindan durduruldu."
        )

    except Exception as e:

        print()
        print("=" * 70)
        print(" BEKLENMEYEN HATA")
        print("=" * 70)
        print()

        print(
            type(e).__name__,
            ":",
            e
        )

        print()

        print(
            "Dosya:",
            Path(__file__).name
        )

        print()

        print(
            "Gercek para / otomatik emir YOK."
        )

        print()