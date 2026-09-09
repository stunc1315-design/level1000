# ============================================================
# LEVEL 1000 FINAL - WALK-FORWARD TEST
#
# Gerçek para: HAYIR
# Otomatik emir: HAYIR
#
# Girdi:
#   level1000_data/level1000_top20.csv
#
# Çıktı:
#   level1000_data/walk_forward_trades.csv
#   level1000_data/walk_forward_summary.csv
#   level1000_data/walk_forward_periods.csv
# ============================================================

from pathlib import Path
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError:
    print("[HATA] yfinance kurulu değil.")
    print("Şunu çalıştır:")
    print("pip install yfinance pandas numpy")
    raise SystemExit(1)


# ============================================================
# AYARLAR
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "level1000_data"

TOP20_FILE = DATA_DIR / "level1000_top20.csv"

START_DATE = "2018-01-01"
END_DATE = None

REBALANCE_DAYS = 20
HOLD_DAYS = 20
TOP_N = 20

INITIAL_CAPITAL = 100000.0


# ============================================================
# RSI
# ============================================================

def calculate_rsi(series, period=14):

    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    return 100 - (100 / (1 + rs))


# ============================================================
# YÜZDELİK SKOR
# ============================================================

def percentile_score(series, higher=True):

    rank = series.rank(
        pct=True,
        method="average"
    )

    if higher:
        return rank * 100

    return (1 - rank) * 100


# ============================================================
# VERİ İNDİR
# ============================================================

def download_data(ticker):

    try:

        data = yf.download(
            ticker,
            start=START_DATE,
            end=END_DATE,
            auto_adjust=True,
            progress=False,
            threads=False
        )

        if data is None or data.empty:
            return None

        if isinstance(data.columns, pd.MultiIndex):

            try:
                data = data.xs(
                    ticker,
                    axis=1,
                    level=1
                )
            except Exception:

                data.columns = (
                    data.columns
                    .get_level_values(0)
                )

        needed = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        for column in needed:

            if column not in data.columns:
                return None

            data[column] = pd.to_numeric(
                data[column],
                errors="coerce"
            )

        data = data[needed].dropna(
            subset=["Close"]
        )

        return data

    except Exception as e:

        print(
            f"[UYARI] {ticker}: {e}"
        )

        return None


# ============================================================
# TOP20 DOSYASI
# ============================================================

if not TOP20_FILE.exists():

    print()
    print(
        "[HATA] level1000_top20.csv bulunamadı:"
    )

    print(TOP20_FILE)

    print()
    print(
        "Önce şunu çalıştır:"
    )

    print(
        "python level1000_rank.py"
    )

    raise SystemExit(1)


top20 = pd.read_csv(
    TOP20_FILE
)


if "Ticker" not in top20.columns:

    print(
        "[HATA] Ticker kolonu bulunamadı."
    )

    raise SystemExit(1)


tickers = (
    top20["Ticker"]
    .astype(str)
    .str.upper()
    .str.strip()
    .drop_duplicates()
    .tolist()
)


# ============================================================
# BAŞLANGIÇ
# ============================================================

print()
print("=" * 72)
print(" LEVEL 1000 FINAL / WALK-FORWARD TEST")
print("=" * 72)

print(
    f"TOP20 aday : {len(tickers)}"
)

print(
    f"Başlangıç  : {START_DATE}"
)

print(
    f"Rebalance  : {REBALANCE_DAYS} işlem günü"
)

print(
    f"Pozisyon   : {HOLD_DAYS} işlem günü"
)

print("=" * 72)


# ============================================================
# VERİLER
# ============================================================

all_data = {}

print()
print("[VERİ] Geçmiş fiyatlar indiriliyor...")


for number, ticker in enumerate(
    tickers,
    1
):

    print(
        f"[{number}/{len(tickers)}] {ticker}"
    )

    data = download_data(
        ticker
    )

    if (
        data is not None
        and len(data) >= 150
    ):

        all_data[ticker] = data

    else:

        print(
            f"       -> atlandı"
        )


if len(all_data) < 2:

    print()
    print(
        "[HATA] Yeterli veri alınamadı."
    )

    raise SystemExit(1)


print()
print(
    f"[OK] Kullanılabilir sembol: "
    f"{len(all_data)}"
)


# ============================================================
# ORTAK TARİHLER
# ============================================================

common_dates = None


for data in all_data.values():

    dates = pd.DatetimeIndex(
        data.index
    )

    if common_dates is None:

        common_dates = dates

    else:

        common_dates = (
            common_dates
            .intersection(dates)
        )


common_dates = (
    common_dates
    .sort_values()
)


if len(common_dates) < 120:

    print(
        "[HATA] Yeterli ortak tarih yok."
    )

    raise SystemExit(1)


# ============================================================
# FİYAT / HACİM TABLOLARI
# ============================================================

close_df = pd.DataFrame(
    index=common_dates
)

volume_df = pd.DataFrame(
    index=common_dates
)


for ticker, data in all_data.items():

    close_df[ticker] = (
        data["Close"]
        .reindex(common_dates)
        .ffill()
    )

    volume_df[ticker] = (
        data["Volume"]
        .reindex(common_dates)
        .fillna(0)
    )


# ============================================================
# WALK-FORWARD
# ============================================================

trades = []

dates = list(common_dates)

start_index = 100


print()
print("=" * 72)
print(" WALK-FORWARD BAŞLIYOR")
print("=" * 72)


for i in range(
    start_index,
    len(dates) - HOLD_DAYS,
    REBALANCE_DAYS
):

    decision_date = dates[i]

    exit_date = dates[
        i + HOLD_DAYS
    ]


    # --------------------------------------------------------
    # SADECE KARAR TARİHİNE KADAR OLAN VERİ
    # --------------------------------------------------------

    history = close_df.loc[
        :decision_date
    ]


    candidates = []


    for ticker in close_df.columns:

        series = (
            history[ticker]
            .dropna()
        )


        if len(series) < 100:
            continue


        current = float(
            series.iloc[-1]
        )


        price_5 = float(
            series.iloc[-6]
        )

        price_20 = float(
            series.iloc[-21]
        )

        price_60 = float(
            series.iloc[-61]
        )


        return_5 = (
            current / price_5 - 1
        )

        return_20 = (
            current / price_20 - 1
        )

        return_60 = (
            current / price_60 - 1
        )


        sma20 = (
            series.tail(20)
            .mean()
        )

        sma50 = (
            series.tail(50)
            .mean()
        )

        sma100 = (
            series.tail(100)
            .mean()
        )


        sma20_distance = (
            current / sma20 - 1
        )

        sma50_distance = (
            current / sma50 - 1
        )

        sma100_distance = (
            current / sma100 - 1
        )


        rsi_value = float(
            calculate_rsi(series)
            .iloc[-1]
        )


        returns = (
            series
            .pct_change()
            .dropna()
            .tail(20)
        )


        if len(returns) < 10:
            continue


        volatility = float(
            returns.std()
        )


        volume_history = (
            volume_df[ticker]
            .loc[:decision_date]
            .dropna()
        )


        if len(volume_history) >= 20:

            volume_now = float(
                volume_history.iloc[-1]
            )

            volume_average = float(
                volume_history
                .tail(20)
                .mean()
            )

            if volume_average > 0:

                volume_ratio = (
                    volume_now /
                    volume_average
                )

            else:

                volume_ratio = 1.0

        else:

            volume_ratio = 1.0


        candidates.append({

            "Ticker": ticker,

            "Return_5D": return_5,

            "Return_20D": return_20,

            "Return_60D": return_60,

            "SMA20_Distance":
                sma20_distance,

            "SMA50_Distance":
                sma50_distance,

            "SMA100_Distance":
                sma100_distance,

            "RSI_14":
                rsi_value,

            "Volume_Ratio":
                volume_ratio,

            "Volatility":
                volatility

        })


    if len(candidates) < 2:
        continue


    scores = pd.DataFrame(
        candidates
    )


    # ========================================================
    # MOMENTUM
    # ========================================================

    scores["M5"] = percentile_score(
        scores["Return_5D"]
    )

    scores["M20"] = percentile_score(
        scores["Return_20D"]
    )

    scores["M60"] = percentile_score(
        scores["Return_60D"]
    )


    scores["Momentum_Score"] = (

        scores["M5"] * 0.20

        +

        scores["M20"] * 0.40

        +

        scores["M60"] * 0.40

    )


    # ========================================================
    # TREND
    # ========================================================

    scores["T20"] = percentile_score(
        scores["SMA20_Distance"]
    )

    scores["T50"] = percentile_score(
        scores["SMA50_Distance"]
    )

    scores["T100"] = percentile_score(
        scores["SMA100_Distance"]
    )


    scores["Trend_Score"] = (

        scores["T20"] * 0.25

        +

        scores["T50"] * 0.35

        +

        scores["T100"] * 0.40

    )


    # ========================================================
    # HACİM
    # ========================================================

    scores["Volume_Score"] = (
        percentile_score(
            scores["Volume_Ratio"]
        )
    )


    # ========================================================
    # RİSK
    # ========================================================

    scores["Risk_Score"] = (
        percentile_score(
            scores["Volatility"],
            higher=False
        )
    )


    # ========================================================
    # RSI
    # ========================================================

    scores["RSI_Score"] = np.select(

        [

            scores["RSI_14"].between(
                50,
                70
            ),

            scores["RSI_14"].between(
                45,
                75
            ),

            scores["RSI_14"].between(
                40,
                80
            )

        ],

        [

            100,
            75,
            50

        ],

        default=25
    )


    # ========================================================
    # AŞIRI UZAMA
    # ========================================================

    extension = (
        scores["SMA20_Distance"]
        .clip(lower=0)
    )


    scores["Extension_Penalty"] = np.select(

        [

            extension > 0.30,

            extension > 0.20,

            extension > 0.10

        ],

        [

            30,
            18,
            8

        ],

        default=0
    )


    # ========================================================
    # FINAL SCORE
    # ========================================================

    scores["Rank_Score"] = (

        scores["Momentum_Score"]
        * 0.32

        +

        scores["Trend_Score"]
        * 0.28

        +

        scores["Volume_Score"]
        * 0.12

        +

        scores["RSI_Score"]
        * 0.10

        +

        scores["Risk_Score"]
        * 0.18

        -

        scores["Extension_Penalty"]

    )


    scores = (
        scores
        .sort_values(
            "Rank_Score",
            ascending=False
        )
    )


    selected = scores.head(
        TOP_N
    )


    # ========================================================
    # GELECEK GETİRİYİ ÖLÇ
    # ========================================================

    for _, row in selected.iterrows():

        ticker = row["Ticker"]


        entry_price = float(
            close_df.loc[
                decision_date,
                ticker
            ]
        )


        exit_price = float(
            close_df.loc[
                exit_date,
                ticker
            ]
        )


        if entry_price <= 0:
            continue


        forward_return = (
            exit_price /
            entry_price
            - 1
        )


        trades.append({

            "Decision_Date":
                decision_date.strftime(
                    "%Y-%m-%d"
                ),

            "Exit_Date":
                exit_date.strftime(
                    "%Y-%m-%d"
                ),

            "Ticker":
                ticker,

            "Rank_Score":
                round(
                    float(
                        row["Rank_Score"]
                    ),
                    2
                ),

            "Entry_Price":
                round(
                    entry_price,
                    4
                ),

            "Exit_Price":
                round(
                    exit_price,
                    4
                ),

            "Forward_Return":
                forward_return,

            "Historical_Return_20D":
                float(
                    row["Return_20D"]
                ),

            "Historical_RSI":
                float(
                    row["RSI_14"]
                )

        })


    print(
        f"[WF] "
        f"{decision_date.strftime('%Y-%m-%d')} "
        f"-> "
        f"{exit_date.strftime('%Y-%m-%d')} "
        f"| "
        f"{len(selected)} aday"
    )


# ============================================================
# SONUÇ
# ============================================================

if not trades:

    print()
    print(
        "[HATA] Walk-forward işlemi oluşmadı."
    )

    raise SystemExit(1)


trades_df = pd.DataFrame(
    trades
)


trades_df["Forward_Return"] = (
    pd.to_numeric(
        trades_df["Forward_Return"],
        errors="coerce"
    )
)


trades_df = (
    trades_df
    .dropna(
        subset=["Forward_Return"]
    )
)


# ============================================================
# DÖNEM GETİRİLERİ
# ============================================================

period_returns = (

    trades_df
    .groupby(
        "Decision_Date"
    )["Forward_Return"]
    .mean()
    .reset_index()

)


period_returns["Equity_Multiple"] = (

    1 +
    period_returns[
        "Forward_Return"
    ]

).cumprod()


period_returns["Equity"] = (

    INITIAL_CAPITAL
    *
    period_returns[
        "Equity_Multiple"
    ]

)


# ============================================================
# PERFORMANS
# ============================================================

equity = period_returns[
    "Equity"
]

peak = equity.cummax()

drawdown = (
    equity / peak - 1
)


max_drawdown = (
    drawdown.min()
)


win_rate = (
    trades_df[
        "Forward_Return"
    ] > 0
).mean()


average_return = (
    trades_df[
        "Forward_Return"
    ].mean()
)


median_return = (
    trades_df[
        "Forward_Return"
    ].median()
)


best_return = (
    trades_df[
        "Forward_Return"
    ].max()
)


worst_return = (
    trades_df[
        "Forward_Return"
    ].min()
)


final_equity = float(
    period_returns[
        "Equity"
    ].iloc[-1]
)


total_return = (
    final_equity /
    INITIAL_CAPITAL
    - 1
)


period_count = len(
    period_returns
)


if period_count > 0:

    annualized_return = (

        (
            final_equity /
            INITIAL_CAPITAL
        )

        ** (

            252 /
            (
                period_count *
                REBALANCE_DAYS
            )

        )

        - 1

    )

else:

    annualized_return = np.nan


# ============================================================
# ÖZET DOSYASI
# ============================================================

summary = pd.DataFrame([{

    "Initial_Capital":
        INITIAL_CAPITAL,

    "Final_Equity":
        final_equity,

    "Total_Return":
        total_return,

    "Annualized_Return_Est":
        annualized_return,

    "Max_Drawdown":
        max_drawdown,

    "Win_Rate":
        win_rate,

    "Average_20D_Return":
        average_return,

    "Median_20D_Return":
        median_return,

    "Best_20D_Return":
        best_return,

    "Worst_20D_Return":
        worst_return,

    "Periods":
        period_count,

    "Trades":
        len(trades_df),

    "Unique_Tickers":
        trades_df[
            "Ticker"
        ].nunique()

}])


# ============================================================
# KAYDET
# ============================================================

trades_df.to_csv(
    DATA_DIR /
    "walk_forward_trades.csv",
    index=False
)


summary.to_csv(
    DATA_DIR /
    "walk_forward_summary.csv",
    index=False
)


period_returns.to_csv(
    DATA_DIR /
    "walk_forward_periods.csv",
    index=False
)


top20.to_csv(
    DATA_DIR /
    "level1000_final_current_top20.csv",
    index=False
)


# ============================================================
# EKRAN
# ============================================================

print()
print("=" * 72)
print(" FINAL SONUÇ")
print("=" * 72)

print(
    f"Başlangıç sermayesi : "
    f"{INITIAL_CAPITAL:,.2f}"
)

print(
    f"Final sermaye       : "
    f"{final_equity:,.2f}"
)

print(
    f"Toplam getiri       : "
    f"{total_return * 100:.2f}%"
)

print(
    f"Yıllıklandırılmış   : "
    f"{annualized_return * 100:.2f}%"
)

print(
    f"Maksimum düşüş      : "
    f"{max_drawdown * 100:.2f}%"
)

print(
    f"Kazanma oranı       : "
    f"{win_rate * 100:.2f}%"
)

print(
    f"Ortalama 20G        : "
    f"{average_return * 100:.2f}%"
)

print(
    f"Medyan 20G          : "
    f"{median_return * 100:.2f}%"
)

print(
    f"En iyi 20G          : "
    f"{best_return * 100:.2f}%"
)

print(
    f"En kötü 20G         : "
    f"{worst_return * 100:.2f}%"
)

print(
    f"Test dönemi         : "
    f"{period_count}"
)

print(
    f"Toplam işlem        : "
    f"{len(trades_df):,}"
)

print("=" * 72)

print()
print("OLUŞAN DOSYALAR:")

print(
    "[OK] walk_forward_trades.csv"
)

print(
    "[OK] walk_forward_summary.csv"
)

print(
    "[OK] walk_forward_periods.csv"
)

print(
    "[OK] level1000_final_current_top20.csv"
)

print()
print("=" * 72)
print(" LEVEL 1000 FINAL TAMAMLANDI")
print("=" * 72)