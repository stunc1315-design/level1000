# ============================================================
# LEVEL 1000 AI - PAPER TRADING PERFORMANCE V2
# ============================================================
# GERCEK PARA YOK
# OTOMATIK EMIR YOK
# SADECE PAPER TRADING
#
# Mantik:
# 1. Yeni BUY/SELL sinyali gelirse PAPER pozisyon acilir.
# 2. Pozisyon zaten aciksa tekrar giris yapilmaz.
# 3. Fiyat degistikce acik pozisyonun getirisi hesaplanir.
# 4. BUY  -> fiyat yukselirse kar
# 5. SELL -> fiyat duserse kar
# 6. Signal HOLD olursa mevcut pozisyon korunur.
# 7. BUY -> SELL veya SELL -> BUY degisirse eski pozisyon kapanir,
#    yeni pozisyon acilir.
# ============================================================

from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np


# ============================================================
# DOSYALAR
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "level1000_data"

PAPER_FILE = DATA_DIR / "level1000_paper_signals.csv"

POSITIONS_FILE = DATA_DIR / "paper_open_positions.csv"
TRADES_FILE = DATA_DIR / "paper_closed_trades.csv"
HISTORY_FILE = DATA_DIR / "paper_performance_history.csv"
SUMMARY_FILE = DATA_DIR / "paper_performance_summary.csv"


# ============================================================
# AYARLAR
# ============================================================

# Her paper pozisyonu 1 birim kabul ediyoruz.
POSITION_SIZE = 1.0


# ============================================================
# YARDIMCI
# ============================================================

def clean_number(value, default=np.nan):

    try:

        if pd.isna(value):
            return default

        if isinstance(value, str):

            value = (
                value
                .replace("%", "")
                .replace(",", ".")
                .strip()
            )

        return float(value)

    except Exception:

        return default


def find_column(df, names):

    # Önce direkt isim
    for name in names:

        if name in df.columns:
            return name

    # Sonra küçük/büyük harf bağımsız
    lower_map = {
        str(col).strip().lower(): col
        for col in df.columns
    }

    for name in names:

        key = str(name).strip().lower()

        if key in lower_map:
            return lower_map[key]

    return None


# ============================================================
# PAPER DOSYASINI OKU
# ============================================================

def load_current_paper():

    if not PAPER_FILE.exists():

        print()
        print("[HATA] Paper dosyasi bulunamadi:")
        print(PAPER_FILE)
        print()

        return None

    try:

        df = pd.read_csv(
            PAPER_FILE
        )

    except Exception as e:

        print()
        print("[HATA] Paper CSV okunamadi:")
        print(e)
        print()

        return None

    if df.empty:

        print()
        print("[HATA] Paper CSV bos.")
        print()

        return None

    return df


# ============================================================
# PAPER VERISINI STANDARDIZE ET
# ============================================================

def normalize_current(df):

    ticker_col = find_column(
        df,
        [
            "Ticker",
            "Symbol",
            "Hisse"
        ]
    )

    signal_col = find_column(
        df,
        [
            "Signal",
            "Sinyal"
        ]
    )

    price_col = find_column(
        df,
        [
            "Price",
            "Close",
            "Fiyat"
        ]
    )

    date_col = find_column(
        df,
        [
            "Date",
            "Tarih"
        ]
    )

    if ticker_col is None:

        print("[HATA] Ticker/Symbol kolonu bulunamadi.")
        return None

    if signal_col is None:

        print("[HATA] Signal/Sinyal kolonu bulunamadi.")
        return None

    if price_col is None:

        print("[HATA] Price/Close/Fiyat kolonu bulunamadi.")
        return None

    result = pd.DataFrame()

    result["Ticker"] = (
        df[ticker_col]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    result["Signal"] = (
        df[signal_col]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    result["Price"] = (
        df[price_col]
        .apply(clean_number)
    )

    if date_col is not None:

        result["Date"] = pd.to_datetime(
            df[date_col],
            errors="coerce"
        )

    else:

        result["Date"] = pd.Timestamp.now()

    result = result[
        result["Ticker"].notna()
        & result["Price"].notna()
        & (result["Price"] > 0)
        & result["Signal"].isin(
            [
                "BUY",
                "SELL",
                "HOLD"
            ]
        )
    ].copy()

    # Aynı hisse birden fazla ise son satırı kullan
    result = result.drop_duplicates(
        subset=["Ticker"],
        keep="last"
    )

    return result.reset_index(drop=True)


# ============================================================
# BOS POZISYON TABLOSU
# ============================================================

def empty_positions():

    return pd.DataFrame(
        columns=[
            "Ticker",
            "Signal",
            "Entry_Date",
            "Entry_Price",
            "Quantity",
            "Last_Date",
            "Last_Price",
            "Unrealized_PnL",
            "Return_Pct"
        ]
    )


# ============================================================
# ACIK POZISYONLARI OKU
# ============================================================

def load_positions():

    if not POSITIONS_FILE.exists():

        return empty_positions()

    try:

        df = pd.read_csv(
            POSITIONS_FILE
        )

    except Exception:

        return empty_positions()

    if df.empty:

        return empty_positions()

    expected = [
        "Ticker",
        "Signal",
        "Entry_Date",
        "Entry_Price",
        "Quantity",
        "Last_Date",
        "Last_Price",
        "Unrealized_PnL",
        "Return_Pct"
    ]

    for col in expected:

        if col not in df.columns:

            df[col] = np.nan

    return df[expected].copy()


# ============================================================
# KAPANMIS ISLEMLERI OKU
# ============================================================

def load_closed_trades():

    if not TRADES_FILE.exists():

        return pd.DataFrame(
            columns=[
                "Ticker",
                "Signal",
                "Entry_Date",
                "Entry_Price",
                "Exit_Date",
                "Exit_Price",
                "Quantity",
                "PnL",
                "Return_Pct",
                "Result"
            ]
        )

    try:

        df = pd.read_csv(
            TRADES_FILE
        )

        return df

    except Exception:

        return pd.DataFrame(
            columns=[
                "Ticker",
                "Signal",
                "Entry_Date",
                "Entry_Price",
                "Exit_Date",
                "Exit_Price",
                "Quantity",
                "PnL",
                "Return_Pct",
                "Result"
            ]
        )


# ============================================================
# POZISYON KAYDET
# ============================================================

def save_positions(df):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        POSITIONS_FILE,
        index=False,
        encoding="utf-8-sig"
    )


# ============================================================
# ISLEM KAYDET
# ============================================================

def save_trades(df):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        TRADES_FILE,
        index=False,
        encoding="utf-8-sig"
    )


# ============================================================
# POZISYON AC
# ============================================================

def open_position(
    ticker,
    signal,
    price,
    date
):

    return {
        "Ticker": ticker,
        "Signal": signal,
        "Entry_Date": date,
        "Entry_Price": float(price),
        "Quantity": POSITION_SIZE,
        "Last_Date": date,
        "Last_Price": float(price),
        "Unrealized_PnL": 0.0,
        "Return_Pct": 0.0
    }


# ============================================================
# POZISYON GETIRISI
# ============================================================

def calculate_position_return(
    signal,
    entry_price,
    current_price
):

    if entry_price <= 0:
        return 0.0

    if signal == "BUY":

        return (
            current_price / entry_price - 1.0
        ) * 100.0

    if signal == "SELL":

        return (
            entry_price / current_price - 1.0
        ) * 100.0

    return 0.0


# ============================================================
# POZISYON KAPAT
# ============================================================

def close_position(
    position,
    exit_price,
    exit_date
):

    signal = str(
        position["Signal"]
    ).upper()

    entry_price = float(
        position["Entry_Price"]
    )

    quantity = float(
        position["Quantity"]
    )

    exit_price = float(
        exit_price
    )

    if signal == "BUY":

        pnl = (
            exit_price - entry_price
        ) * quantity

        return_pct = (
            exit_price / entry_price - 1.0
        ) * 100.0

    elif signal == "SELL":

        pnl = (
            entry_price - exit_price
        ) * quantity

        return_pct = (
            entry_price / exit_price - 1.0
        ) * 100.0

    else:

        pnl = 0.0
        return_pct = 0.0

    if return_pct > 0:
        result = "WIN"

    elif return_pct < 0:
        result = "LOSS"

    else:
        result = "FLAT"

    return {
        "Ticker": position["Ticker"],
        "Signal": signal,
        "Entry_Date": position["Entry_Date"],
        "Entry_Price": entry_price,
        "Exit_Date": exit_date,
        "Exit_Price": exit_price,
        "Quantity": quantity,
        "PnL": pnl,
        "Return_Pct": return_pct,
        "Result": result
    }


# ============================================================
# ACIK POZISYONLARI GUNCELLE
# ============================================================

def update_positions(
    positions,
    current
):

    trades = load_closed_trades()

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Mevcut fiyatlar
    current_map = {}

    for _, row in current.iterrows():

        current_map[
            str(row["Ticker"]).upper()
        ] = row

    # Mevcut pozisyon sözlüğü
    position_map = {}

    for _, row in positions.iterrows():

        ticker = str(
            row["Ticker"]
        ).upper()

        position_map[ticker] = row.to_dict()

    # --------------------------------------------------------
    # MEVCUT POZISYONLARI KONTROL ET
    # --------------------------------------------------------

    new_positions = []

    for ticker, position in position_map.items():

        if ticker not in current_map:

            # Güncel veri yoksa pozisyonu koru
            new_positions.append(position)
            continue

        current_row = current_map[ticker]

        new_signal = str(
            current_row["Signal"]
        ).upper()

        current_price = float(
            current_row["Price"]
        )

        current_date = (
            current_row["Date"]
        )

        if pd.isna(current_date):

            current_date = now

        else:

            current_date = str(
                current_date
            )

        old_signal = str(
            position["Signal"]
        ).upper()

        # ----------------------------------------------------
        # SINYAL DEGISTI
        # ----------------------------------------------------

        if (
            new_signal in ["BUY", "SELL"]
            and old_signal != new_signal
        ):

            closed = close_position(
                position,
                current_price,
                current_date
            )

            trades = pd.concat(
                [
                    trades,
                    pd.DataFrame([closed])
                ],
                ignore_index=True
            )

            print(
                f"[KAPAT] {ticker} "
                f"{old_signal} -> "
                f"{new_signal} | "
                f"Getiri: "
                f"{closed['Return_Pct']:+.2f}%"
            )

            # Yeni pozisyon aç
            new_position = open_position(
                ticker,
                new_signal,
                current_price,
                current_date
            )

            new_positions.append(
                new_position
            )

            print(
                f"[AC] {ticker} "
                f"{new_signal} @ "
                f"{current_price:.2f}"
            )

            continue

        # ----------------------------------------------------
        # HOLD GELDI
        # ----------------------------------------------------

        if new_signal == "HOLD":

            # HOLD eski BUY/SELL pozisyonunu kapatmaz.
            # Pozisyon açık kalır.

            return_pct = calculate_position_return(
                old_signal,
                float(position["Entry_Price"]),
                current_price
            )

            entry_price = float(
                position["Entry_Price"]
            )

            quantity = float(
                position["Quantity"]
            )

            if old_signal == "BUY":

                pnl = (
                    current_price - entry_price
                ) * quantity

            elif old_signal == "SELL":

                pnl = (
                    entry_price - current_price
                ) * quantity

            else:

                pnl = 0.0

            position["Last_Date"] = current_date
            position["Last_Price"] = current_price
            position["Unrealized_PnL"] = pnl
            position["Return_Pct"] = return_pct

            new_positions.append(
                position
            )

            continue

        # ----------------------------------------------------
        # AYNI SINYAL
        # ----------------------------------------------------

        return_pct = calculate_position_return(
            old_signal,
            float(position["Entry_Price"]),
            current_price
        )

        entry_price = float(
            position["Entry_Price"]
        )

        quantity = float(
            position["Quantity"]
        )

        if old_signal == "BUY":

            pnl = (
                current_price - entry_price
            ) * quantity

        elif old_signal == "SELL":

            pnl = (
                entry_price - current_price
            ) * quantity

        else:

            pnl = 0.0

        position["Last_Date"] = current_date
        position["Last_Price"] = current_price
        position["Unrealized_PnL"] = pnl
        position["Return_Pct"] = return_pct

        new_positions.append(
            position
        )

    # --------------------------------------------------------
    # YENI BUY / SELL SINYALLERI
    # --------------------------------------------------------

    existing_tickers = set(
        position_map.keys()
    )

    for _, row in current.iterrows():

        ticker = str(
            row["Ticker"]
        ).upper()

        signal = str(
            row["Signal"]
        ).upper()

        price = float(
            row["Price"]
        )

        if signal not in [
            "BUY",
            "SELL"
        ]:
            continue

        if ticker in existing_tickers:
            continue

        date = row["Date"]

        if pd.isna(date):

            date = now

        else:

            date = str(date)

        position = open_position(
            ticker,
            signal,
            price,
            date
        )

        new_positions.append(
            position
        )

        print(
            f"[AC] {ticker} "
            f"{signal} @ "
            f"{price:.2f}"
        )

    positions_result = pd.DataFrame(
        new_positions
    )

    if positions_result.empty:

        positions_result = empty_positions()

    else:

        positions_result = positions_result[
            [
                "Ticker",
                "Signal",
                "Entry_Date",
                "Entry_Price",
                "Quantity",
                "Last_Date",
                "Last_Price",
                "Unrealized_PnL",
                "Return_Pct"
            ]
        ]

    save_positions(
        positions_result
    )

    save_trades(
        trades
    )

    return positions_result, trades


# ============================================================
# PERFORMANS OZETI
# ============================================================

def calculate_summary(
    positions,
    trades
):

    rows = []

    # --------------------------------------------------------
    # KAPANAN ISLEMLER
    # --------------------------------------------------------

    if trades.empty:

        closed_total = 0
        closed_wins = 0
        closed_losses = 0
        closed_flat = 0
        closed_return = 0.0
        closed_pnl = 0.0

    else:

        closed_total = len(trades)

        closed_wins = int(
            (trades["Result"] == "WIN").sum()
        )

        closed_losses = int(
            (trades["Result"] == "LOSS").sum()
        )

        closed_flat = int(
            (trades["Result"] == "FLAT").sum()
        )

        closed_return = float(
            trades["Return_Pct"].sum()
        )

        closed_pnl = float(
            trades["PnL"].sum()
        )

    # --------------------------------------------------------
    # ACIK ISLEMLER
    # --------------------------------------------------------

    if positions.empty:

        open_total = 0
        open_pnl = 0.0
        open_return = 0.0

    else:

        open_total = len(
            positions
        )

        open_pnl = float(
            pd.to_numeric(
                positions["Unrealized_PnL"],
                errors="coerce"
            )
            .fillna(0)
            .sum()
        )

        open_return = float(
            pd.to_numeric(
                positions["Return_Pct"],
                errors="coerce"
            )
            .fillna(0)
            .sum()
        )

    # --------------------------------------------------------
    # TOPLAM
    # --------------------------------------------------------

    total_pnl = (
        closed_pnl
        + open_pnl
    )

    total_return = (
        closed_return
        + open_return
    )

    decided = (
        closed_total
    )

    if decided > 0:

        win_rate = (
            closed_wins
            / decided
            * 100
        )

    else:

        win_rate = 0.0

    rows.append(
        {
            "Timestamp":
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),

            "Closed_Trades":
                closed_total,

            "Wins":
                closed_wins,

            "Losses":
                closed_losses,

            "Flat":
                closed_flat,

            "Win_Rate_Pct":
                win_rate,

            "Open_Positions":
                open_total,

            "Closed_PnL":
                closed_pnl,

            "Open_PnL":
                open_pnl,

            "Total_PnL":
                total_pnl,

            "Closed_Return_Pct":
                closed_return,

            "Open_Return_Pct":
                open_return,

            "Total_Return_Pct":
                total_return
        }
    )

    return pd.DataFrame(rows)


# ============================================================
# HISSE BAZLI PERFORMANS
# ============================================================

def calculate_ticker_performance(
    positions,
    trades
):

    tickers = set()

    if not positions.empty:

        tickers.update(
            positions["Ticker"]
            .astype(str)
            .tolist()
        )

    if not trades.empty:

        tickers.update(
            trades["Ticker"]
            .astype(str)
            .tolist()
        )

    rows = []

    for ticker in sorted(tickers):

        ticker_trades = (
            trades[
                trades["Ticker"].astype(str)
                == ticker
            ]
            if not trades.empty
            else pd.DataFrame()
        )

        ticker_positions = (
            positions[
                positions["Ticker"].astype(str)
                == ticker
            ]
            if not positions.empty
            else pd.DataFrame()
        )

        closed_pnl = 0.0
        open_pnl = 0.0
        wins = 0
        losses = 0

        if not ticker_trades.empty:

            closed_pnl = float(
                pd.to_numeric(
                    ticker_trades["PnL"],
                    errors="coerce"
                )
                .fillna(0)
                .sum()
            )

            wins = int(
                (
                    ticker_trades["Result"]
                    == "WIN"
                ).sum()
            )

            losses = int(
                (
                    ticker_trades["Result"]
                    == "LOSS"
                ).sum()
            )

        if not ticker_positions.empty:

            open_pnl = float(
                pd.to_numeric(
                    ticker_positions[
                        "Unrealized_PnL"
                    ],
                    errors="coerce"
                )
                .fillna(0)
                .sum()
            )

        total_pnl = (
            closed_pnl
            + open_pnl
        )

        rows.append(
            {
                "Ticker": ticker,
                "Closed_Trades":
                    len(ticker_trades),
                "Wins": wins,
                "Losses": losses,
                "Open_Positions":
                    len(ticker_positions),
                "Closed_PnL":
                    closed_pnl,
                "Open_PnL":
                    open_pnl,
                "Total_PnL":
                    total_pnl
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# RAPORU YAZDIR
# ============================================================

def print_report(
    positions,
    trades,
    summary,
    ticker_summary
):

    print()
    print("=" * 70)
    print(" LEVEL 1000 PAPER TRADING PERFORMANS V2")
    print("=" * 70)

    if summary.empty:

        print()
        print("Henüz performans verisi yok.")
        return

    s = summary.iloc[0]

    print()

    print(
        f"KAPANAN ISLEM : "
        f"{int(s['Closed_Trades'])}"
    )

    print(
        f"KAZANAN       : "
        f"{int(s['Wins'])}"
    )

    print(
        f"KAYBEDEN      : "
        f"{int(s['Losses'])}"
    )

    print(
        f"FLAT          : "
        f"{int(s['Flat'])}"
    )

    print(
        f"WIN RATE      : "
        f"{s['Win_Rate_Pct']:.2f}%"
    )

    print()

    print(
        f"ACIK POZISYON  : "
        f"{int(s['Open_Positions'])}"
    )

    print(
        f"KAPALI P&L     : "
        f"{s['Closed_PnL']:+.2f}"
    )

    print(
        f"ACIK P&L       : "
        f"{s['Open_PnL']:+.2f}"
    )

    print(
        f"TOPLAM P&L     : "
        f"{s['Total_PnL']:+.2f}"
    )

    print(
        f"TOPLAM GETIRI  : "
        f"{s['Total_Return_Pct']:+.2f}%"
    )

    # --------------------------------------------------------
    # ACIK POZISYONLAR
    # --------------------------------------------------------

    print()
    print("-" * 70)
    print(" ACIK PAPER POZISYONLARI")
    print("-" * 70)

    if positions.empty:

        print("Açık BUY/SELL pozisyonu yok.")

    else:

        for _, row in positions.iterrows():

            ret = clean_number(
                row["Return_Pct"],
                0.0
            )

            pnl = clean_number(
                row["Unrealized_PnL"],
                0.0
            )

            print(
                f"{str(row['Ticker']):>6} "
                f"{str(row['Signal']):>4} | "
                f"Giriş: "
                f"{float(row['Entry_Price']):>9.2f} | "
                f"Şimdi: "
                f"{float(row['Last_Price']):>9.2f} | "
                f"Getiri: "
                f"{ret:+7.2f}% | "
                f"P&L: "
                f"{pnl:+8.2f}"
            )

    # --------------------------------------------------------
    # HISSE BAZLI
    # --------------------------------------------------------

    print()
    print("-" * 70)
    print(" HISSE BAZLI PERFORMANS")
    print("-" * 70)

    if ticker_summary.empty:

        print("Henüz kapanmış işlem yok.")

    else:

        for _, row in ticker_summary.iterrows():

            print(
                f"{str(row['Ticker']):>6} | "
                f"Kapali: "
                f"{int(row['Closed_Trades']):>3} | "
                f"Win: "
                f"{int(row['Wins']):>3} | "
                f"Loss: "
                f"{int(row['Losses']):>3} | "
                f"Acik: "
                f"{int(row['Open_Positions']):>2} | "
                f"P&L: "
                f"{row['Total_PnL']:+8.2f}"
            )

    print()
    print("=" * 70)


# ============================================================
# DOSYALARI KAYDET
# ============================================================

def save_reports(
    summary,
    ticker_summary
):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # Son özet
    summary.to_csv(
        SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # Geçmiş
    if HISTORY_FILE.exists():

        try:

            old_history = pd.read_csv(
                HISTORY_FILE
            )

        except Exception:

            old_history = pd.DataFrame()

    else:

        old_history = pd.DataFrame()

    history = pd.concat(
        [
            old_history,
            summary
        ],
        ignore_index=True
    )

    history.to_csv(
        HISTORY_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print("[OK]", POSITIONS_FILE)
    print("[OK]", TRADES_FILE)
    print("[OK]", HISTORY_FILE)
    print("[OK]", SUMMARY_FILE)


# ============================================================
# ANA
# ============================================================

def main():

    print()
    print("=" * 70)
    print(" LEVEL 1000 AI - PAPER PERFORMANCE V2")
    print("=" * 70)

    # --------------------------------------------------------
    # GÜNCEL PAPER SİNYALLER
    # --------------------------------------------------------

    raw = load_current_paper()

    if raw is None:
        return

    current = normalize_current(
        raw
    )

    if current is None or current.empty:

        print()
        print("[HATA] Geçerli paper sinyali bulunamadi.")
        return

    print()

    print(
        f"[OK] Güncel hisse: "
        f"{len(current)}"
    )

    print(
        f"[OK] BUY : "
        f"{int((current['Signal'] == 'BUY').sum())}"
    )

    print(
        f"[OK] SELL: "
        f"{int((current['Signal'] == 'SELL').sum())}"
    )

    print(
        f"[OK] HOLD: "
        f"{int((current['Signal'] == 'HOLD').sum())}"
    )

    # --------------------------------------------------------
    # ESKİ POZİSYONLAR
    # --------------------------------------------------------

    positions = load_positions()

    # --------------------------------------------------------
    # POZİSYONLARI GÜNCELLE
    # --------------------------------------------------------

    positions, trades = update_positions(
        positions,
        current
    )

    # --------------------------------------------------------
    # RAPOR
    # --------------------------------------------------------

    summary = calculate_summary(
        positions,
        trades
    )

    ticker_summary = (
        calculate_ticker_performance(
            positions,
            trades
        )
    )

    print_report(
        positions,
        trades,
        summary,
        ticker_summary
    )

    save_reports(
        summary,
        ticker_summary
    )

    print()
    print("GERCEK PARA : YOK")
    print("OTOMATIK EMIR: YOK")
    print("PAPER TRADING: EVET")
    print("=" * 70)
    print()


# ============================================================
# ÇALIŞTIR
# ============================================================

if __name__ == "__main__":

    main()