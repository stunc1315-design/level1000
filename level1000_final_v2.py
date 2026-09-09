from pathlib import Path
from datetime import datetime
import warnings
import math

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")


# ============================================================
# LEVEL 1000 FINAL V2
# WALK-FORWARD BACKTEST
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "level1000_data"
CACHE_DIR = DATA_DIR / "history_cache"

INPUT_FILE = DATA_DIR / "level1000_fast_top.csv"

START_DATE = "2018-01-01"
END_DATE = None

TOP_N = 20
REBALANCE_DAYS = 20
HOLD_DAYS = 20

INITIAL_CAPITAL = 100_000.0

# 10 basis point = %0.10
COST_BPS = 10

BENCHMARK = "SPY"

MIN_HISTORY = 120


# ============================================================
# KLASÖRLER
# ============================================================

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# YARDIMCI
# ============================================================

def clean_ticker(ticker):
    return str(ticker).strip().upper()


def safe_float(x):
    try:
        return float(x)
    except Exception:
        return np.nan


# ============================================================
# RSI
# ============================================================

def rsi(series, period=14):

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

    out = 100 - (100 / (1 + rs))

    return out


# ============================================================
# ATR
# ============================================================

def atr_pct(df, period=14):

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr = tr.rolling(period).mean()

    return atr / close * 100


# ============================================================
# YAHOO DATA
# ============================================================

def download_history(ticker):

    cache_file = CACHE_DIR / f"{ticker.replace('/', '_')}.csv"

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    if cache_file.exists():

        try:

            df = pd.read_csv(
                cache_file,
                index_col=0,
                parse_dates=True
            )

            if len(df) >= MIN_HISTORY:

                df.columns = [
                    str(c).strip()
                    for c in df.columns
                ]

                needed = [
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Volume"
                ]

                if all(c in df.columns for c in needed):

                    return df[needed].sort_index()

        except Exception:
            pass

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    try:

        print(f"[VERI] {ticker} indiriliyor...")

        df = yf.download(
            ticker,
            start=START_DATE,
            end=END_DATE,
            auto_adjust=True,
            progress=False,
            threads=False
        )

        if df is None or df.empty:
            return None

        # MultiIndex temizle
        if isinstance(df.columns, pd.MultiIndex):

            try:
                df.columns = df.columns.get_level_values(0)
            except Exception:

                df.columns = [
                    c[0] if isinstance(c, tuple) else c
                    for c in df.columns
                ]

        df.columns = [
            str(c).strip()
            for c in df.columns
        ]

        needed = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        if not all(c in df.columns for c in needed):
            return None

        df = df[needed].copy()

        for c in needed:

            df[c] = pd.to_numeric(
                df[c],
                errors="coerce"
            )

        df = df.dropna(
            subset=["Close"]
        )

        df = df.sort_index()

        if len(df) < MIN_HISTORY:
            return None

        df.to_csv(cache_file)

        print(
            f"[OK] {ticker} | "
            f"{df.index.min().date()} -> "
            f"{df.index.max().date()} | "
            f"{len(df)} gün"
        )

        return df

    except Exception as e:

        print(
            f"[HATA] {ticker}: {str(e)[:120]}"
        )

        return None


# ============================================================
# TEKNİK GÖSTERGELER
# ============================================================

def calculate_features(df):

    x = df.copy()

    close = x["Close"]
    volume = x["Volume"]

    x["Return_5D"] = (
        close / close.shift(5) - 1
    )

    x["Return_20D"] = (
        close / close.shift(20) - 1
    )

    x["Return_60D"] = (
        close / close.shift(60) - 1
    )

    x["RSI_14"] = rsi(
        close,
        14
    )

    volume_avg = volume.rolling(20).mean()

    x["Volume_Ratio_20"] = (
        volume / volume_avg
    )

    x["ATR_Pct"] = atr_pct(
        x,
        14
    )

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma100 = close.rolling(100).mean()

    x["SMA20_Distance"] = (
        close / sma20 - 1
    )

    x["SMA50_Distance"] = (
        close / sma50 - 1
    )

    x["SMA100_Distance"] = (
        close / sma100 - 1
    )

    return x


# ============================================================
# SKOR
# ============================================================

def calculate_score(row):

    values = [
        row.get("Return_5D"),
        row.get("Return_20D"),
        row.get("Return_60D"),
        row.get("RSI_14"),
        row.get("Volume_Ratio_20"),
        row.get("ATR_Pct"),
        row.get("SMA20_Distance"),
        row.get("SMA50_Distance"),
        row.get("SMA100_Distance")
    ]

    if any(pd.isna(v) for v in values):
        return np.nan

    # ========================================================
    # MOMENTUM
    # ========================================================

    momentum_raw = (
        0.20 * row["Return_5D"] +
        0.35 * row["Return_20D"] +
        0.45 * row["Return_60D"]
    )

    # Aşırı değerlerin skoru 100'e yapıştırmasını engeller
    momentum_score = (
        50 +
        50 * np.tanh(
            momentum_raw / 0.50
        )
    )

    # ========================================================
    # TREND
    # ========================================================

    trend_raw = (
        0.40 * row["SMA20_Distance"] +
        0.35 * row["SMA50_Distance"] +
        0.25 * row["SMA100_Distance"]
    )

    trend_score = (
        50 +
        50 * np.tanh(
            trend_raw / 0.30
        )
    )

    # ========================================================
    # HACİM
    # ========================================================

    volume_raw = row["Volume_Ratio_20"]

    volume_score = (
        50 +
        50 * np.tanh(
            (volume_raw - 1) / 2
        )
    )

    # ========================================================
    # RSI
    # ========================================================

    rsi_value = row["RSI_14"]

    # En iyi bölge yaklaşık 62.5
    rsi_score = (
        100 -
        abs(rsi_value - 62.5) * 2.2
    )

    rsi_score = np.clip(
        rsi_score,
        0,
        100
    )

    # ========================================================
    # RİSK
    # ========================================================

    atr = max(
        float(row["ATR_Pct"]),
        0
    )

    # ATR yükseldikçe risk puanı azalır
    risk_score = (
        100 /
        (1 + atr / 8)
    )

    # ========================================================
    # AŞIRI UZAMA CEZASI
    # ========================================================

    extension_penalty = 0

    if row["SMA20_Distance"] > 0.20:

        extension_penalty = (
            row["SMA20_Distance"] - 0.20
        ) * 50

    # ========================================================
    # FINAL SCORE
    # ========================================================

    score = (
        0.35 * momentum_score +
        0.30 * trend_score +
        0.15 * volume_score +
        0.10 * rsi_score +
        0.10 * risk_score -
        extension_penalty
    )

    return float(
        np.clip(
            score,
            0,
            100
        )
    )


# ============================================================
# EVRENİ OKU
# ============================================================

def load_universe():

    candidates = []

    if INPUT_FILE.exists():

        try:

            df = pd.read_csv(
                INPUT_FILE
            )

            if "Ticker" in df.columns:

                candidates = (
                    df["Ticker"]
                    .dropna()
                    .astype(str)
                    .map(clean_ticker)
                    .drop_duplicates()
                    .tolist()
                )

        except Exception as e:

            print(
                f"[UYARI] {INPUT_FILE} okunamadı: {e}"
            )

    # Fallback
    if not candidates:

        fallback = (
            DATA_DIR /
            "level1000_ranked_top300.csv"
        )

        if fallback.exists():

            df = pd.read_csv(
                fallback
            )

            if "Ticker" in df.columns:

                candidates = (
                    df["Ticker"]
                    .dropna()
                    .astype(str)
                    .map(clean_ticker)
                    .drop_duplicates()
                    .tolist()
                )

    return candidates


# ============================================================
# TÜM ADAYLARI PUANLA
# ============================================================

def score_universe(
    histories,
    date
):

    rows = []

    for ticker, df in histories.items():

        if df is None or df.empty:
            continue

        df2 = df[
            df.index <= date
        ]

        if len(df2) < MIN_HISTORY:
            continue

        features = calculate_features(
            df2
        )

        if features.empty:
            continue

        row = features.iloc[-1]

        score = calculate_score(
            row
        )

        if pd.isna(score):
            continue

        rows.append({

            "Ticker":
                ticker,

            "Score":
                score,

            "Close":
                safe_float(
                    row["Close"]
                ),

            "Return_5D":
                safe_float(
                    row["Return_5D"]
                ),

            "Return_20D":
                safe_float(
                    row["Return_20D"]
                ),

            "Return_60D":
                safe_float(
                    row["Return_60D"]
                ),

            "RSI_14":
                safe_float(
                    row["RSI_14"]
                ),

            "Volume_Ratio_20":
                safe_float(
                    row["Volume_Ratio_20"]
                ),

            "ATR_Pct":
                safe_float(
                    row["ATR_Pct"]
                ),

            "SMA20_Distance":
                safe_float(
                    row["SMA20_Distance"]
                ),

            "SMA50_Distance":
                safe_float(
                    row["SMA50_Distance"]
                ),

            "SMA100_Distance":
                safe_float(
                    row["SMA100_Distance"]
                )

        })

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(
        rows
    )

    result = result.sort_values(
        "Score",
        ascending=False
    )

    result["Rank"] = np.arange(
        1,
        len(result) + 1
    )

    return result


# ============================================================
# GET CLOSE
# ============================================================

def get_close_on_or_after(
    df,
    date
):

    future = df[
        df.index > date
    ]

    if future.empty:
        return None, None

    idx = future.index[0]

    return idx, safe_float(
        future.iloc[0]["Close"]
    )


def get_close_after_n_days(
    df,
    entry_date,
    days
):

    future = df[
        df.index >= entry_date
    ]

    if len(future) <= days:
        return None, None

    idx = future.index[days]

    return idx, safe_float(
        future.iloc[days]["Close"]
    )


# ============================================================
# METRİKLER
# ============================================================

def max_drawdown(equity):

    if equity.empty:
        return np.nan

    peak = equity.cummax()

    drawdown = (
        equity / peak - 1
    )

    return drawdown.min()


def calculate_metrics(
    returns,
    equity
):

    returns = pd.Series(
        returns
    ).dropna()

    if returns.empty:
        return {}

    total_return = (
        equity.iloc[-1] /
        equity.iloc[0] - 1
    )

    n_periods = len(returns)

    periods_per_year = (
        252 / REBALANCE_DAYS
    )

    years = (
        n_periods /
        periods_per_year
    )

    if years > 0:

        cagr = (
            (1 + total_return)
            ** (1 / years)
            - 1
        )

    else:

        cagr = np.nan

    volatility = (
        returns.std(ddof=1)
        * math.sqrt(
            periods_per_year
        )
    )

    if returns.std(ddof=1) > 0:

        sharpe = (
            returns.mean() /
            returns.std(ddof=1)
        ) * math.sqrt(
            periods_per_year
        )

    else:

        sharpe = np.nan

    wins = returns[
        returns > 0
    ]

    losses = returns[
        returns < 0
    ]

    win_rate = (
        len(wins) /
        len(returns)
    )

    if len(losses) > 0:

        profit_factor = (
            wins.sum() /
            abs(losses.sum())
        )

    else:

        profit_factor = np.inf

    return {

        "Total_Return":
            total_return,

        "CAGR":
            cagr,

        "Volatility":
            volatility,

        "Sharpe":
            sharpe,

        "Max_Drawdown":
            max_drawdown(
                equity
            ),

        "Win_Rate":
            win_rate,

        "Profit_Factor":
            profit_factor,

        "Average_Period_Return":
            returns.mean(),

        "Median_Period_Return":
            returns.median(),

        "Best_Period":
            returns.max(),

        "Worst_Period":
            returns.min(),

        "Periods":
            len(returns)

    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print("=" * 70)
    print(" LEVEL 1000 FINAL V2")
    print(" WALK-FORWARD BACKTEST")
    print("=" * 70)

    print(
        f" Başlangıç          : {START_DATE}"
    )

    print(
        f" Rebalance          : {REBALANCE_DAYS} işlem günü"
    )

    print(
        f" Pozisyon           : {HOLD_DAYS} işlem günü"
    )

    print(
        f" TOP N              : {TOP_N}"
    )

    print(
        f" İşlem maliyeti     : {COST_BPS} bps"
    )

    print(
        f" Başlangıç sermaye  : "
        f"{INITIAL_CAPITAL:,.2f}"
    )

    print()

    universe = load_universe()

    print(
        f"[UNIVERSE] Aday sembol: "
        f"{len(universe)}"
    )

    print(
        "[UYARI] Bu test mevcut TOP300 evrenini kullanır."
    )

    print(
        "[UYARI] Tam geçmiş 13.000 sembol evreni değildir."
    )

    print(
        "[UYARI] Survivorship bias bulunmaktadır."
    )

    print()

    # --------------------------------------------------------
    # HISTORICAL DATA
    # --------------------------------------------------------

    histories = {}

    for i, ticker in enumerate(
        universe,
        1
    ):

        print(
            f"[{i}/{len(universe)}] {ticker}"
        )

        df = download_history(
            ticker
        )

        if df is not None:

            histories[ticker] = df

    print()

    print(
        f"[OK] Kullanılabilir sembol: "
        f"{len(histories)}"
    )

    if len(histories) < TOP_N:

        print(
            "[HATA] TOP20 oluşturacak kadar veri yok."
        )

        return

    # --------------------------------------------------------
    # TAKVİM
    # --------------------------------------------------------

    benchmark_df = download_history(
        BENCHMARK
    )

    if benchmark_df is None:

        print(
            "[HATA] SPY benchmark verisi alınamadı."
        )

        return

    calendar = benchmark_df.index[
        benchmark_df.index >=
        pd.Timestamp(START_DATE)
    ]

    if END_DATE:

        calendar = calendar[
            calendar <=
            pd.Timestamp(END_DATE)
        ]

    if len(calendar) <= (
        MIN_HISTORY +
        HOLD_DAYS
    ):

        print(
            "[HATA] Yeterli takvim verisi yok."
        )

        return

    decision_dates = []

    pos = MIN_HISTORY

    while pos < (
        len(calendar) -
        HOLD_DAYS
    ):

        decision_dates.append(
            calendar[pos]
        )

        pos += REBALANCE_DAYS

    print()

    print(
        f"[WALK-FORWARD] Test dönemi: "
        f"{len(decision_dates)}"
    )

    print()

    # --------------------------------------------------------
    # BACKTEST
    # --------------------------------------------------------

    capital = INITIAL_CAPITAL

    previous_weights = {}

    period_rows = []
    position_rows = []
    equity_rows = []

    for period_no, decision_date in enumerate(
        decision_dates,
        1
    ):

        # ----------------------------------------------
        # SCORE
        # ----------------------------------------------

        ranking = score_universe(
            histories,
            decision_date
        )

        if ranking.empty:
            continue

        selected = ranking.head(
            TOP_N
        ).copy()

        if len(selected) < TOP_N:
            continue

        # ----------------------------------------------
        # ENTRY
        # ----------------------------------------------

        valid_positions = []

        for _, row in selected.iterrows():

            ticker = row["Ticker"]

            df = histories[ticker]

            entry_date, entry_price = (
                get_close_on_or_after(
                    df,
                    decision_date
                )
            )

            if (
                entry_date is None or
                entry_price is None or
                entry_price <= 0
            ):

                continue

            exit_date, exit_price = (
                get_close_after_n_days(
                    df,
                    entry_date,
                    HOLD_DAYS
                )
            )

            if (
                exit_date is None or
                exit_price is None or
                exit_price <= 0
            ):

                continue

            valid_positions.append({

                "Ticker":
                    ticker,

                "Score":
                    row["Score"],

                "Rank":
                    row["Rank"],

                "Entry_Date":
                    entry_date,

                "Exit_Date":
                    exit_date,

                "Entry_Price":
                    entry_price,

                "Exit_Price":
                    exit_price,

                "Return":
                    (
                        exit_price /
                        entry_price - 1
                    )

            })

        if not valid_positions:
            continue

        # ----------------------------------------------
        # WEIGHTS
        # ----------------------------------------------

        n = len(
            valid_positions
        )

        new_weights = {

            p["Ticker"]:
                1 / n

            for p in valid_positions

        }

        # ----------------------------------------------
        # TURNOVER
        # ----------------------------------------------

        all_tickers = set(
            previous_weights
        ).union(
            new_weights
        )

        turnover = sum(

            abs(

                new_weights.get(
                    t,
                    0
                )

                -

                previous_weights.get(
                    t,
                    0
                )

            )

            for t in all_tickers

        )

        transaction_cost = (
            turnover *
            COST_BPS /
            10000
        )

        # ----------------------------------------------
        # PORTFOLIO RETURN
        # ----------------------------------------------

        gross_return = np.mean([

            p["Return"]

            for p in valid_positions

        ])

        net_return = (
            gross_return -
            transaction_cost
        )

        old_capital = capital

        capital *= (
            1 + net_return
        )

        # ----------------------------------------------
        # BENCHMARK
        # ----------------------------------------------

        bench_entry_date, bench_entry = (
            get_close_on_or_after(
                benchmark_df,
                decision_date
            )
        )

        bench_exit_date = None
        bench_exit = None

        if bench_entry_date is not None:

            bench_exit_date, bench_exit = (
                get_close_after_n_days(
                    benchmark_df,
                    bench_entry_date,
                    HOLD_DAYS
                )
            )

        if (
            bench_entry is not None and
            bench_exit is not None and
            bench_entry > 0
        ):

            benchmark_return = (
                bench_exit /
                bench_entry - 1
            )

        else:

            benchmark_return = np.nan

        # ----------------------------------------------
        # PERIOD
        # ----------------------------------------------

        period_rows.append({

            "Period":
                period_no,

            "Decision_Date":
                decision_date.strftime(
                    "%Y-%m-%d"
                ),

            "Entry_Date":
                min(
                    p["Entry_Date"]
                    for p in valid_positions
                ).strftime(
                    "%Y-%m-%d"
                ),

            "Exit_Date":
                max(
                    p["Exit_Date"]
                    for p in valid_positions
                ).strftime(
                    "%Y-%m-%d"
                ),

            "Positions":
                len(valid_positions),

            "Gross_Return":
                gross_return,

            "Transaction_Cost":
                transaction_cost,

            "Net_Return":
                net_return,

            "Benchmark_Return":
                benchmark_return,

            "Start_Capital":
                old_capital,

            "End_Capital":
                capital,

            "Turnover":
                turnover

        })

        # ----------------------------------------------
        # POSITIONS
        # ----------------------------------------------

        for p in valid_positions:

            position_rows.append({

                "Period":
                    period_no,

                "Decision_Date":
                    decision_date.strftime(
                        "%Y-%m-%d"
                    ),

                "Ticker":
                    p["Ticker"],

                "Rank":
                    p["Rank"],

                "Score":
                    p["Score"],

                "Entry_Date":
                    p["Entry_Date"].strftime(
                        "%Y-%m-%d"
                    ),

                "Exit_Date":
                    p["Exit_Date"].strftime(
                        "%Y-%m-%d"
                    ),

                "Entry_Price":
                    p["Entry_Price"],

                "Exit_Price":
                    p["Exit_Price"],

                "Return":
                    p["Return"]

            })

        equity_rows.append({

            "Date":
                max(
                    p["Exit_Date"]
                    for p in valid_positions
                ),

            "Equity":
                capital

        })

        previous_weights = new_weights

        print(

            f"[{period_no:03d}] "
            f"{decision_date.date()} -> "
            f"{max(p['Exit_Date'] for p in valid_positions).date()} | "
            f"TOP {len(valid_positions)} | "
            f"Net: {net_return * 100:7.2f}% | "
            f"Sermaye: {capital:,.2f}"

        )

    # --------------------------------------------------------
    # DATAFRAMES
    # --------------------------------------------------------

    periods_df = pd.DataFrame(
        period_rows
    )

    positions_df = pd.DataFrame(
        position_rows
    )

    equity_df = pd.DataFrame(
        equity_rows
    )

    if periods_df.empty:

        print(
            "[HATA] Backtest sonucu oluşmadı."
        )

        return

    equity_df = equity_df.sort_values(
        "Date"
    )

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    portfolio_equity = pd.Series(

        periods_df[
            "End_Capital"
        ].values,

        index=pd.to_datetime(
            periods_df[
                "Exit_Date"
            ]
        )

    )

    benchmark_equity = (

        INITIAL_CAPITAL *

        (
            1 +

            periods_df[
                "Benchmark_Return"
            ].fillna(0)

        ).cumprod()

    )

    metrics = calculate_metrics(

        periods_df[
            "Net_Return"
        ],

        portfolio_equity

    )

    benchmark_metrics = calculate_metrics(

        periods_df[
            "Benchmark_Return"
        ].dropna(),

        pd.Series(
            benchmark_equity.values
        )

    )

    # --------------------------------------------------------
    # MONTHLY
    # --------------------------------------------------------

    monthly = periods_df.copy()

    monthly["Exit_Date"] = pd.to_datetime(
        monthly["Exit_Date"]
    )

    monthly["YearMonth"] = (

        monthly["Exit_Date"]
        .dt.to_period("M")
        .astype(str)

    )

    monthly_df = (

        monthly

        .groupby("YearMonth")

        .agg(

            Portfolio_Return=(

                "Net_Return",

                lambda x:
                    (1 + x).prod() - 1

            ),

            Benchmark_Return=(

                "Benchmark_Return",

                lambda x:
                    (
                        1 +
                        x.fillna(0)
                    ).prod() - 1

            )

        )

        .reset_index()

    )

    # --------------------------------------------------------
    # YEARLY
    # --------------------------------------------------------

    yearly = periods_df.copy()

    yearly["Exit_Date"] = pd.to_datetime(
        yearly["Exit_Date"]
    )

    yearly["Year"] = (
        yearly["Exit_Date"]
        .dt.year
    )

    yearly_df = (

        yearly

        .groupby("Year")

        .agg(

            Portfolio_Return=(

                "Net_Return",

                lambda x:
                    (1 + x).prod() - 1

            ),

            Benchmark_Return=(

                "Benchmark_Return",

                lambda x:
                    (
                        1 +
                        x.fillna(0)
                    ).prod() - 1

            )

        )

        .reset_index()

    )

    # --------------------------------------------------------
    # CURRENT TOP20
    # --------------------------------------------------------

    latest_date = max(

        df.index.max()

        for df in histories.values()

        if df is not None
        and not df.empty

    )

    current_ranking = score_universe(

        histories,
        latest_date

    )

    current_top20 = (

        current_ranking

        .head(TOP_N)

        .copy()

    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary_rows = [

        {
            "Metric":
                "Initial_Capital",

            "Portfolio":
                INITIAL_CAPITAL,

            "Benchmark":
                INITIAL_CAPITAL

        },

        {
            "Metric":
                "Final_Capital",

            "Portfolio":
                portfolio_equity.iloc[-1],

            "Benchmark":
                benchmark_equity.iloc[-1]

        },

        {
            "Metric":
                "Total_Return",

            "Portfolio":
                metrics.get(
                    "Total_Return",
                    np.nan
                ),

            "Benchmark":
                benchmark_metrics.get(
                    "Total_Return",
                    np.nan
                )

        },

        {
            "Metric":
                "CAGR",

            "Portfolio":
                metrics.get(
                    "CAGR",
                    np.nan
                ),

            "Benchmark":
                benchmark_metrics.get(
                    "CAGR",
                    np.nan
                )

        },

        {
            "Metric":
                "Volatility",

            "Portfolio":
                metrics.get(
                    "Volatility",
                    np.nan
                ),

            "Benchmark":
                benchmark_metrics.get(
                    "Volatility",
                    np.nan
                )

        },

        {
            "Metric":
                "Sharpe",

            "Portfolio":
                metrics.get(
                    "Sharpe",
                    np.nan
                ),

            "Benchmark":
                benchmark_metrics.get(
                    "Sharpe",
                    np.nan
                )

        },

        {
            "Metric":
                "Max_Drawdown",

            "Portfolio":
                metrics.get(
                    "Max_Drawdown",
                    np.nan
                ),

            "Benchmark":
                benchmark_metrics.get(
                    "Max_Drawdown",
                    np.nan
                )

        },

        {
            "Metric":
                "Win_Rate",

            "Portfolio":
                metrics.get(
                    "Win_Rate",
                    np.nan
                ),

            "Benchmark":
                np.nan

        },

        {
            "Metric":
                "Profit_Factor",

            "Portfolio":
                metrics.get(
                    "Profit_Factor",
                    np.nan
                ),

            "Benchmark":
                np.nan

        },

        {
            "Metric":
                "Average_Period_Return",

            "Portfolio":
                metrics.get(
                    "Average_Period_Return",
                    np.nan
                ),

            "Benchmark":
                np.nan

        },

        {
            "Metric":
                "Median_Period_Return",

            "Portfolio":
                metrics.get(
                    "Median_Period_Return",
                    np.nan
                ),

            "Benchmark":
                np.nan

        },

        {
            "Metric":
                "Best_Period",

            "Portfolio":
                metrics.get(
                    "Best_Period",
                    np.nan
                ),

            "Benchmark":
                np.nan

        },

        {
            "Metric":
                "Worst_Period",

            "Portfolio":
                metrics.get(
                    "Worst_Period",
                    np.nan
                ),

            "Benchmark":
                np.nan

        },

        {
            "Metric":
                "Periods",

            "Portfolio":
                metrics.get(
                    "Periods",
                    0
                ),

            "Benchmark":
                benchmark_metrics.get(
                    "Periods",
                    0
                )

        }

    ]

    summary_df = pd.DataFrame(
        summary_rows
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    periods_file = (
        DATA_DIR /
        "level1000_v2_periods.csv"
    )

    positions_file = (
        DATA_DIR /
        "level1000_v2_positions.csv"
    )

    equity_file = (
        DATA_DIR /
        "level1000_v2_equity.csv"
    )

    summary_file = (
        DATA_DIR /
        "level1000_v2_summary.csv"
    )

    monthly_file = (
        DATA_DIR /
        "level1000_v2_monthly.csv"
    )

    yearly_file = (
        DATA_DIR /
        "level1000_v2_yearly.csv"
    )

    current_file = (
        DATA_DIR /
        "level1000_v2_current_top20.csv"
    )

    periods_df.to_csv(
        periods_file,
        index=False
    )

    positions_df.to_csv(
        positions_file,
        index=False
    )

    equity_df.to_csv(
        equity_file,
        index=False
    )

    summary_df.to_csv(
        summary_file,
        index=False
    )

    monthly_df.to_csv(
        monthly_file,
        index=False
    )

    yearly_df.to_csv(
        yearly_file,
        index=False
    )

    current_top20.to_csv(
        current_file,
        index=False
    )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    print()

    print("=" * 70)
    print(" FINAL V2")
    print("=" * 70)

    print(
        f"Başlangıç sermayesi : "
        f"{INITIAL_CAPITAL:,.2f}"
    )

    print(
        f"Final sermayesi     : "
        f"{portfolio_equity.iloc[-1]:,.2f}"
    )

    print(
        f"Toplam getiri       : "
        f"{metrics['Total_Return'] * 100:.2f}%"
    )

    print(
        f"CAGR                : "
        f"{metrics['CAGR'] * 100:.2f}%"
    )

    print(
        f"Sharpe              : "
        f"{metrics['Sharpe']:.2f}"
    )

    print(
        f"Maksimum düşüş      : "
        f"{metrics['Max_Drawdown'] * 100:.2f}%"
    )

    print(
        f"Kazanma oranı       : "
        f"{metrics['Win_Rate'] * 100:.2f}%"
    )

    print(
        f"Profit Factor       : "
        f"{metrics['Profit_Factor']:.2f}"
    )

    print(
        f"Ortalama 20G        : "
        f"{metrics['Average_Period_Return'] * 100:.2f}%"
    )

    print(
        f"Medyan 20G          : "
        f"{metrics['Median_Period_Return'] * 100:.2f}%"
    )

    print(
        f"En iyi dönem        : "
        f"{metrics['Best_Period'] * 100:.2f}%"
    )

    print(
        f"En kötü dönem       : "
        f"{metrics['Worst_Period'] * 100:.2f}%"
    )

    print(
        f"Test dönemi         : "
        f"{metrics['Periods']}"
    )

    print()

    print(
        f"SPY toplam getiri   : "
        f"{benchmark_metrics.get('Total_Return', np.nan) * 100:.2f}%"
    )

    print(
        f"SPY CAGR            : "
        f"{benchmark_metrics.get('CAGR', np.nan) * 100:.2f}%"
    )

    print()

    print("GÜNCEL TOP20:")

    if not current_top20.empty:

        print(
            current_top20[
                [
                    "Rank",
                    "Ticker",
                    "Score"
                ]
            ].to_string(
                index=False
            )
        )

    print()

    print("DOSYALAR:")

    print(
        periods_file
    )

    print(
        positions_file
    )

    print(
        equity_file
    )

    print(
        summary_file
    )

    print(
        monthly_file
    )

    print(
        yearly_file
    )

    print(
        current_file
    )

    print()
    print("=" * 70)
    print(" TAMAMLANDI")
    print("=" * 70)


if __name__ == "__main__":
    main()