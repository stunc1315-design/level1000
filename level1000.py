from pathlib import Path
import warnings
import time
import random

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

from concurrent.futures import ThreadPoolExecutor, as_completed

from sklearn.ensemble import (
    RandomForestClassifier,
    ExtraTreesClassifier,
    RandomForestRegressor,
    ExtraTreesRegressor,
)

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
)

# ============================================================
# LEVEL 1000 V6 - BIST MASS AI HISTORY
# ============================================================
#
# AMAÇ:
# 626+ BIST HİSSE
#       ↓
# 5 YILLIK GÜNLÜK VERİ
#       ↓
# GLOBAL AI
#       ↓
# HER HİSSE İÇİN 300 TARİHSEL AI TAHMİNİ
#       ↓
# ~100.000 - 180.000+ GERÇEK KAYIT
#       ↓
# APP.PY
#       ↓
# VİTRİN MAKSİMUM 2.000
#
# GERÇEK PARA YOK
# OTOMATİK EMİR YOK
# PAPER ONLY
# ============================================================


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "level1000_data"
TURKIYE_DIR = BASE_DIR / "turkiye_data"

DATA_DIR.mkdir(exist_ok=True)
TURKIYE_DIR.mkdir(exist_ok=True)


# ============================================================
# AYARLAR
# ============================================================

YEARS = 5

HORIZON = 5

TRAIN_MIN = 252

# EN ÖNEMLİ DEĞİŞİKLİK
# Her hisse için son 300 tarihsel AI tahmini
HISTORICAL_PREDICTION_ROWS = 300

# Backtest de 300 gün
FAST_BACKTEST_ROWS = HISTORICAL_PREDICTION_ROWS

RF_TREES = 30
ET_TREES = 30

RF_DEPTH = 10
ET_DEPTH = 10

INITIAL_CAPITAL = 100000.0

RANDOM_STATE = 42

COST_BPS = 10

# ============================================================
# BIST
# ============================================================

MARKET = "XU100.IS"

MAX_SYMBOLS = 100000

AI_CANDIDATES = None


# ============================================================
# FAST SCAN
# ============================================================

BATCH_SIZE = 100

BATCH_SLEEP = 0.10

# BIST'te düşük fiyatlı hisseleri de kaçırma
MIN_PRICE = 0.01

# Çok düşük hacimli hisseleri tamamen eleme
MIN_DOLLAR_VOLUME = 0


# ============================================================
# AI DOWNLOAD
# ============================================================

AI_DOWNLOAD_WORKERS = 8

AI_CHUNK_SIZE = 50

MIN_HISTORY_ROWS = 300


# ============================================================
# MONTE CARLO
# ============================================================

MONTE_CARLO_RUNS = 1000


# ============================================================
# BIST CSV
# ============================================================

BIST_STOCK_FILE = (
    TURKIYE_DIR /
    "bist_hisseler.csv"
)


# ============================================================
# ÇIKTILAR
# ============================================================

LATEST_SIGNALS = (
    DATA_DIR /
    "level1000_latest_signals.csv"
)

PAPER_SIGNALS = (
    DATA_DIR /
    "level1000_paper_signals.csv"
)

MODEL_METRICS = (
    DATA_DIR /
    "level1000_model_metrics.csv"
)

TRADE_LOG = (
    DATA_DIR /
    "level1000_trade_log.csv"
)

VARIANT_SUMMARY = (
    DATA_DIR /
    "level1000_variant_summary.csv"
)

MONTE_CARLO = (
    DATA_DIR /
    "level1000_monte_carlo.csv"
)

PREDICTIONS = (
    DATA_DIR /
    "level1000_predictions.csv"
)

FAST_UNIVERSE = (
    DATA_DIR /
    "level1000_fast_universe.csv"
)

AI_CANDIDATES_FILE = (
    DATA_DIR /
    "level1000_ai_candidates.csv"
)


# ============================================================
# CACHE
# ============================================================

DATA_CACHE = {}

MARKET_DATA = None

GLOBAL_BACKTEST_MODELS = None

GLOBAL_FINAL_MODELS = None


# ============================================================
# RANDOM
# ============================================================

random.seed(RANDOM_STATE)

np.random.seed(RANDOM_STATE)


# ============================================================
# BIST UNIVERSE
# ============================================================

def load_bist_universe():

    print()
    print("=" * 72)
    print(" BIST UNIVERSE")
    print("=" * 72)

    if not BIST_STOCK_FILE.exists():

        print(
            "[HATA] BIST CSV bulunamadı:"
        )

        print(
            BIST_STOCK_FILE
        )

        return []

    print(
        f"[BIST] Kaynak: "
        f"{BIST_STOCK_FILE}"
    )

    try:

        df = pd.read_csv(
            BIST_STOCK_FILE,
            encoding="utf-8-sig",
        )

    except Exception:

        try:

            df = pd.read_csv(
                BIST_STOCK_FILE,
                encoding="utf-8",
            )

        except Exception as e:

            print(
                "[HATA] BIST CSV okunamadı:",
                e
            )

            return []

    if len(df) == 0:

        print(
            "[HATA] BIST CSV boş."
        )

        return []

    print(
        f"[BIST] CSV satır: "
        f"{len(df):,}"
    )

    symbol_column = None

    possible_columns = [
        "Ticker",
        "ticker",
        "Symbol",
        "symbol",
        "Sembol",
        "sembol",
        "Code",
        "code",
    ]

    for col in possible_columns:

        if col in df.columns:

            symbol_column = col
            break

    if symbol_column is None:

        symbol_column = df.columns[0]

        print(
            f"[BIST] Sembol sütunu otomatik: "
            f"{symbol_column}"
        )

    symbols = []

    allowed = set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789._-"
    )

    for value in df[symbol_column]:

        if pd.isna(value):
            continue

        symbol = str(
            value
        ).strip().upper()

        if not symbol:
            continue

        if symbol.endswith(".IS"):

            yahoo_symbol = symbol

        else:

            yahoo_symbol = (
                symbol + ".IS"
            )

        if not all(
            c in allowed
            for c in yahoo_symbol
        ):
            continue

        symbols.append(
            yahoo_symbol
        )

    symbols = list(
        dict.fromkeys(symbols)
    )

    if MAX_SYMBOLS:

        symbols = symbols[
            :MAX_SYMBOLS
        ]

    print()
    print(
        f"[BIST UNIVERSE] "
        f"{len(symbols):,} hisse"
    )

    if symbols:

        print(
            "[BIST ÖRNEK] "
            + ", ".join(
                symbols[:15]
            )
        )

    return symbols


# ============================================================
# DATA NORMALIZE
# ============================================================

def normalize_single_dataframe(df):

    if df is None:
        return None

    if len(df) == 0:
        return None

    try:

        if isinstance(
            df.columns,
            pd.MultiIndex
        ):

            new_cols = []

            for col in df.columns:

                values = list(col)

                found = None

                for name in [
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Adj Close",
                    "Volume",
                ]:

                    if name in values:

                        found = name
                        break

                if found:

                    new_cols.append(
                        found
                    )

                else:

                    new_cols.append(
                        str(values[-1])
                    )

            df = df.copy()

            df.columns = new_cols

        df = df.copy()

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        for col in required:

            if col not in df.columns:

                return None

        df = df[
            required
        ].copy()

        for col in required:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce",
            )

        df = df.replace(
            [np.inf, -np.inf],
            np.nan,
        )

        df = df.dropna(
            subset=required
        )

        if len(df) < 100:

            return None

        df = df.sort_index()

        return df

    except Exception:

        return None


# ============================================================
# SINGLE DOWNLOAD
# ============================================================

def download_data(
    ticker,
    period=None,
):

    ticker = str(
        ticker
    ).upper()

    if ticker in DATA_CACHE:

        return DATA_CACHE[
            ticker
        ]

    if period is None:

        period = f"{YEARS}y"

    try:

        df = yf.download(
            ticker,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
            timeout=20,
        )

        df = normalize_single_dataframe(
            df
        )

        if df is None:

            return None

        DATA_CACHE[
            ticker
        ] = df

        return df

    except Exception:

        return None


# ============================================================
# BATCH TICKER EXTRACT
# ============================================================

def extract_ticker_from_batch(
    data,
    ticker,
):

    if data is None:
        return None

    if len(data) == 0:
        return None

    try:

        ticker = str(
            ticker
        )

        if not isinstance(
            data.columns,
            pd.MultiIndex
        ):

            return normalize_single_dataframe(
                data
            )

        level0 = list(
            data.columns
            .get_level_values(0)
        )

        level1 = list(
            data.columns
            .get_level_values(1)
        )

        if ticker in set(
            map(str, level0)
        ):

            try:

                sub = data[
                    ticker
                ]

                return normalize_single_dataframe(
                    sub
                )

            except Exception:
                pass

        if ticker in set(
            map(str, level1)
        ):

            try:

                sub = data.xs(
                    ticker,
                    axis=1,
                    level=1,
                )

                return normalize_single_dataframe(
                    sub
                )

            except Exception:
                pass

        for t in set(
            map(str, level0)
        ):

            if (
                t.upper()
                ==
                ticker.upper()
            ):

                try:

                    sub = data[t]

                    return normalize_single_dataframe(
                        sub
                    )

                except Exception:

                    pass

        for t in set(
            map(str, level1)
        ):

            if (
                t.upper()
                ==
                ticker.upper()
            ):

                try:

                    sub = data.xs(
                        t,
                        axis=1,
                        level=1,
                    )

                    return normalize_single_dataframe(
                        sub
                    )

                except Exception:

                    pass

    except Exception:

        pass

    return None


# ============================================================
# FAST SCORE
# ============================================================

def calculate_fast_score(
    ticker,
    df,
):

    try:

        if df is None:
            return None

        if len(df) < 100:
            return None

        close = df["Close"]

        volume = df["Volume"]

        price = float(
            close.iloc[-1]
        )

        if not np.isfinite(price):
            return None

        if price < MIN_PRICE:
            return None

        ret5 = float(
            close.pct_change(5).iloc[-1]
        )

        ret20 = float(
            close.pct_change(20).iloc[-1]
        )

        ret60 = float(
            close.pct_change(60).iloc[-1]
        )

        avg_volume = float(
            volume.tail(20).mean()
        )

        if not np.isfinite(
            avg_volume
        ):

            return None

        volume_ratio = (
            float(volume.iloc[-1])
            /
            avg_volume
            if avg_volume > 0
            else 0
        )

        dollar_volume = (
            price * avg_volume
        )

        if (
            dollar_volume
            <
            MIN_DOLLAR_VOLUME
        ):

            return None

        sma20 = float(
            close.rolling(20).mean().iloc[-1]
        )

        sma50 = float(
            close.rolling(50).mean().iloc[-1]
        )

        if (
            not np.isfinite(sma20)
            or
            not np.isfinite(sma50)
        ):

            return None

        trend = (
            (
                price / sma20
            ) - 1.0
        ) + (
            (
                price / sma50
            ) - 1.0
        )

        volatility = float(
            close
            .pct_change()
            .rolling(20)
            .std()
            .iloc[-1]
        )

        if not np.isfinite(
            volatility
        ):

            volatility = 0.0

        score = 50.0

        score += ret5 * 100
        score += ret20 * 60
        score += ret60 * 30
        score += trend * 80

        if volume_ratio > 1:

            score += min(
                volume_ratio - 1,
                3
            ) * 5

        if volatility > 0:

            score += min(
                volatility * 100,
                10
            )

        score = float(
            np.clip(
                score,
                0,
                100,
            )
        )

        return {

            "Ticker": ticker,

            "Price": price,

            "Return_5D": ret5,

            "Return_20D": ret20,

            "Return_60D": ret60,

            "Volume_Ratio": volume_ratio,

            "Dollar_Volume": dollar_volume,

            "Volatility_20D": volatility,

            "Trend": trend,

            "Fast_Score": score,
        }

    except Exception:

        return None


# ============================================================
# FAST SCAN
# ============================================================

def fast_batch_scan(
    symbols
):

    print()
    print("=" * 72)
    print(
        " LEVEL 1000 - BIST FAST SCAN"
    )
    print("=" * 72)

    results = []

    total = len(symbols)

    start = time.time()

    valid_data_count = 0

    failed_count = 0

    for start_idx in range(
        0,
        total,
        BATCH_SIZE,
    ):

        batch = symbols[
            start_idx:
            start_idx + BATCH_SIZE
        ]

        try:

            data = yf.download(
                batch,
                period="1y",
                interval="1d",
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False,
                timeout=30,
            )

        except Exception as e:

            print(
                f"[BATCH HATA] "
                f"{start_idx + 1}-"
                f"{start_idx + len(batch)}: "
                f"{e}"
            )

            failed_count += len(batch)

            continue

        for ticker in batch:

            df = extract_ticker_from_batch(
                data,
                ticker,
            )

            if df is None:

                failed_count += 1

                continue

            valid_data_count += 1

            score = calculate_fast_score(
                ticker,
                df,
            )

            if score:

                results.append(
                    score
                )

        done = min(
            start_idx + len(batch),
            total,
        )

        elapsed = (
            time.time()
            - start
        )

        speed = (
            done / elapsed
            if elapsed > 0
            else 0
        )

        remaining = (
            total - done
        )

        eta = (
            remaining / speed
            if speed > 0
            else 0
        )

        print(
            f"[FAST] "
            f"{done:,}/{total:,} "
            f"("
            f"{done / total * 100:.1f}%"
            f") | "
            f"uygun={len(results):,} | "
            f"veri={valid_data_count:,} | "
            f"ETA={eta / 60:.1f} dk"
        )

        time.sleep(
            BATCH_SLEEP
        )

    if not results:

        print(
            "[HATA] Fast scan sonuç vermedi."
        )

        return pd.DataFrame()

    universe_df = pd.DataFrame(
        results
    )

    universe_df = (
        universe_df
        .drop_duplicates("Ticker")
        .sort_values(
            "Fast_Score",
            ascending=False,
        )
    )

    universe_df.to_csv(
        FAST_UNIVERSE,
        index=False,
        encoding="utf-8-sig",
    )

    candidates = universe_df.copy()

    candidates.to_csv(
        AI_CANDIDATES_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        f"[FAST OK] "
        f"Verisi bulunan : "
        f"{len(universe_df):,}"
    )

    print(
        f"[AI] Aday       : "
        f"{len(candidates):,}"
    )

    print(
        f"[ATLANAN]       : "
        f"{failed_count:,}"
    )

    return candidates


# ============================================================
# MARKET
# ============================================================

def load_market():

    global MARKET_DATA

    if MARKET_DATA is not None:

        return MARKET_DATA

    print()
    print(
        "[MARKET] XU100.IS indiriliyor..."
    )

    df = download_data(
        MARKET
    )

    if df is None:

        print(
            "[UYARI] XU100.IS alınamadı."
        )

        return None

    MARKET_DATA = df

    print(
        f"[MARKET OK] "
        f"{len(df):,} satır"
    )

    return df


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    close,
    period=14,
):

    delta = close.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = (
        gain
        .rolling(period)
        .mean()
    )

    avg_loss = (
        loss
        .rolling(period)
        .mean()
    )

    rs = (
        avg_gain /
        avg_loss.replace(
            0,
            np.nan,
        )
    )

    return (
        100 -
        (
            100 /
            (1 + rs)
        )
    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    df,
    period=14,
):

    high = df["High"]

    low = df["Low"]

    close = df["Close"]

    prev_close = close.shift(1)

    tr1 = high - low

    tr2 = (
        high - prev_close
    ).abs()

    tr3 = (
        low - prev_close
    ).abs()

    tr = pd.concat(
        [
            tr1,
            tr2,
            tr3,
        ],
        axis=1,
    ).max(axis=1)

    return (
        tr
        .rolling(period)
        .mean()
    )


# ============================================================
# FEATURES
# ============================================================

FEATURE_COLUMNS = [

    "ret_1",
    "ret_2",
    "ret_3",
    "ret_5",
    "ret_10",
    "ret_20",
    "ret_30",
    "ret_60",
    "ret_120",
    "ret_200",

    "sma5_dist",
    "sma10_dist",
    "sma20_dist",
    "sma50_dist",
    "sma100_dist",
    "sma200_dist",

    "ema10_dist",
    "ema20_dist",
    "ema50_dist",

    "volatility_5",
    "volatility_10",
    "volatility_20",
    "volatility_60",

    "atr_pct",
    "rsi",

    "macd",
    "macd_signal",
    "macd_hist",

    "bb_position",

    "stoch_k",

    "roc_10",
    "roc_20",

    "volume_ratio_5",
    "volume_ratio_20",
    "volume_ratio_60",

    "high_distance",
    "low_distance",

    "body",
    "range",
    "upper_shadow",
    "lower_shadow",

    "market_ret_5",
    "market_ret_20",
    "market_ret_50",
]


# ============================================================
# FEATURE ENGINE
# ============================================================

def add_features(
    df,
    market_df=None,
):

    x = df.copy()

    close = x["Close"]
    high = x["High"]
    low = x["Low"]
    volume = x["Volume"]

    for n in [
        1,
        2,
        3,
        5,
        10,
        20,
        30,
        60,
        120,
        200,
    ]:

        x[
            f"ret_{n}"
        ] = close.pct_change(n)

    for n in [
        5,
        10,
        20,
        50,
        100,
        200,
    ]:

        sma = (
            close
            .rolling(n)
            .mean()
        )

        x[
            f"sma{n}_dist"
        ] = (
            close / sma
        ) - 1

    for n in [
        10,
        20,
        50,
    ]:

        ema = (
            close
            .ewm(
                span=n,
                adjust=False,
            )
            .mean()
        )

        x[
            f"ema{n}_dist"
        ] = (
            close / ema
        ) - 1

    returns = close.pct_change()

    for n in [
        5,
        10,
        20,
        60,
    ]:

        x[
            f"volatility_{n}"
        ] = (
            returns
            .rolling(n)
            .std()
        )

    atr = calculate_atr(x)

    x["atr_pct"] = (
        atr / close
    )

    x["rsi"] = calculate_rsi(
        close
    )

    ema12 = (
        close
        .ewm(
            span=12,
            adjust=False,
        )
        .mean()
    )

    ema26 = (
        close
        .ewm(
            span=26,
            adjust=False,
        )
        .mean()
    )

    macd = (
        ema12 - ema26
    )

    signal = (
        macd
        .ewm(
            span=9,
            adjust=False,
        )
        .mean()
    )

    x["macd"] = macd / close

    x["macd_signal"] = (
        signal / close
    )

    x["macd_hist"] = (
        (macd - signal)
        / close
    )

    bb_mid = (
        close
        .rolling(20)
        .mean()
    )

    bb_std = (
        close
        .rolling(20)
        .std()
    )

    upper = (
        bb_mid +
        2 * bb_std
    )

    lower = (
        bb_mid -
        2 * bb_std
    )

    x["bb_position"] = (
        (close - lower)
        /
        (
            upper - lower
        ).replace(
            0,
            np.nan,
        )
    )

    low14 = (
        low
        .rolling(14)
        .min()
    )

    high14 = (
        high
        .rolling(14)
        .max()
    )

    x["stoch_k"] = (
        (close - low14)
        /
        (
            high14 - low14
        ).replace(
            0,
            np.nan,
        )
    )

    x["roc_10"] = (
        close.pct_change(10)
    )

    x["roc_20"] = (
        close.pct_change(20)
    )

    for n in [
        5,
        20,
        60,
    ]:

        avg = (
            volume
            .rolling(n)
            .mean()
        )

        x[
            f"volume_ratio_{n}"
        ] = (
            volume /
            avg.replace(
                0,
                np.nan,
            )
        )

    rolling_high = (
        high
        .rolling(20)
        .max()
    )

    rolling_low = (
        low
        .rolling(20)
        .min()
    )

    x["high_distance"] = (
        close /
        rolling_high
        - 1
    )

    x["low_distance"] = (
        close /
        rolling_low
        - 1
    )

    candle_range = (
        high - low
    ).replace(
        0,
        np.nan,
    )

    x["body"] = (
        (
            x["Close"]
            -
            x["Open"]
        )
        /
        close
    )

    x["range"] = (
        candle_range /
        close
    )

    x["upper_shadow"] = (
        high -
        x[
            ["Open", "Close"]
        ].max(axis=1)
    ) / candle_range

    x["lower_shadow"] = (
        x[
            ["Open", "Close"]
        ].min(axis=1)
        -
        low
    ) / candle_range

    if market_df is not None:

        market_close = (
            market_df["Close"]
        )

        market_features = (
            pd.DataFrame(
                index=market_df.index
            )
        )

        market_features[
            "market_ret_5"
        ] = (
            market_close
            .pct_change(5)
        )

        market_features[
            "market_ret_20"
        ] = (
            market_close
            .pct_change(20)
        )

        market_features[
            "market_ret_50"
        ] = (
            market_close
            .pct_change(50)
        )

        market_features = (
            market_features
            .reindex(
                x.index,
                method="ffill",
            )
        )

        for col in [
            "market_ret_5",
            "market_ret_20",
            "market_ret_50",
        ]:

            x[col] = (
                market_features[col]
            )

    else:

        x[
            "market_ret_5"
        ] = 0.0

        x[
            "market_ret_20"
        ] = 0.0

        x[
            "market_ret_50"
        ] = 0.0

    future_close = (
        close.shift(
            -HORIZON
        )
    )

    x[
        "future_return"
    ] = (
        future_close /
        close
        - 1
    )

    x[
        "target"
    ] = (
        x["future_return"]
        > 0
    ).astype(int)

    x = x.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    return x


# ============================================================
# AI BULK DOWNLOAD
# ============================================================

def download_ai_batch(
    tickers
):

    if not tickers:
        return

    print()
    print("=" * 72)
    print(
        " BIST AI DATA BULK DOWNLOAD"
    )
    print("=" * 72)

    total = len(tickers)

    chunks = [
        tickers[
            i:i + AI_CHUNK_SIZE
        ]
        for i in range(
            0,
            total,
            AI_CHUNK_SIZE,
        )
    ]

    start = time.time()

    def worker(chunk):

        try:

            data = yf.download(
                chunk,
                period=f"{YEARS}y",
                interval="1d",
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False,
                timeout=30,
            )

            output = {}

            for ticker in chunk:

                df = (
                    extract_ticker_from_batch(
                        data,
                        ticker,
                    )
                )

                if (
                    df is not None
                    and
                    len(df)
                    >= MIN_HISTORY_ROWS
                ):

                    output[
                        ticker
                    ] = df

            return output

        except Exception:

            return {}

    completed = 0

    with ThreadPoolExecutor(
        max_workers=
        AI_DOWNLOAD_WORKERS
    ) as executor:

        futures = [
            executor.submit(
                worker,
                chunk,
            )
            for chunk in chunks
        ]

        for future in as_completed(
            futures
        ):

            result = (
                future.result()
            )

            DATA_CACHE.update(
                result
            )

            completed += 1

            elapsed = (
                time.time()
                - start
            )

            print(
                f"[AI DATA] "
                f"{completed}/"
                f"{len(chunks)} batch | "
                f"veri={len(DATA_CACHE):,} | "
                f"geçen="
                f"{elapsed / 60:.1f} dk"
            )


# ============================================================
# MODELS
# ============================================================

def create_classifier(
    seed_offset=0
):

    seed = (
        RANDOM_STATE +
        seed_offset
    )

    rf = RandomForestClassifier(
        n_estimators=RF_TREES,
        max_depth=RF_DEPTH,
        min_samples_leaf=6,
        max_features="sqrt",
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
    )

    et = ExtraTreesClassifier(
        n_estimators=ET_TREES,
        max_depth=ET_DEPTH,
        min_samples_leaf=6,
        max_features="sqrt",
        class_weight="balanced",
        random_state=seed + 1,
        n_jobs=-1,
    )

    return rf, et


def create_regressor(
    seed_offset=0
):

    seed = (
        RANDOM_STATE +
        seed_offset
    )

    rf = RandomForestRegressor(
        n_estimators=RF_TREES,
        max_depth=RF_DEPTH,
        min_samples_leaf=6,
        max_features="sqrt",
        random_state=seed,
        n_jobs=-1,
    )

    et = ExtraTreesRegressor(
        n_estimators=ET_TREES,
        max_depth=ET_DEPTH,
        min_samples_leaf=6,
        max_features="sqrt",
        random_state=seed + 1,
        n_jobs=-1,
    )

    return rf, et


# ============================================================
# TRAIN
# ============================================================

def train_shared_models(
    training_df
):

    if (
        training_df is None
        or
        len(training_df) < TRAIN_MIN
    ):

        return None

    X = training_df[
        FEATURE_COLUMNS
    ].copy()

    y_cls = (
        training_df[
            "target"
        ].astype(int)
    )

    y_reg = (
        training_df[
            "future_return"
        ].astype(float)
    )

    X = X.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    mask = (
        X.notna().all(axis=1)
        &
        y_cls.notna()
        &
        y_reg.notna()
    )

    X = X.loc[mask]

    y_cls = y_cls.loc[mask]

    y_reg = y_reg.loc[mask]

    if len(X) < TRAIN_MIN:

        return None

    print(
        f"[AI TRAIN] "
        f"{len(X):,} satır / "
        f"{len(FEATURE_COLUMNS)} feature"
    )

    start = time.time()

    rf_c, et_c = create_classifier(0)

    rf_r, et_r = create_regressor(10)

    rf_c.fit(X, y_cls)

    et_c.fit(X, y_cls)

    rf_r.fit(X, y_reg)

    et_r.fit(X, y_reg)

    print(
        f"[AI TRAIN OK] "
        f"{(time.time() - start) / 60:.2f} dk"
    )

    return {
        "rf_classifier": rf_c,
        "et_classifier": et_c,
        "rf_regressor": rf_r,
        "et_regressor": et_r,
    }


# ============================================================
# PREDICTION
# ============================================================

def predict_ensemble(
    models,
    X,
):

    if models is None:

        return (
            np.nan,
            np.nan,
        )

    try:

        p1 = (
            models[
                "rf_classifier"
            ]
            .predict_proba(X)[:, 1]
        )

        p2 = (
            models[
                "et_classifier"
            ]
            .predict_proba(X)[:, 1]
        )

        probability = (
            p1 + p2
        ) / 2.0

        r1 = (
            models[
                "rf_regressor"
            ].predict(X)
        )

        r2 = (
            models[
                "et_regressor"
            ].predict(X)
        )

        predicted_return = (
            r1 + r2
        ) / 2.0

        predicted_return = np.clip(
            predicted_return,
            -0.25,
            0.25,
        )

        return (
            probability,
            predicted_return,
        )

    except Exception:

        return (
            np.nan,
            np.nan,
        )


# ============================================================
# SIGNAL
# ============================================================

def strategy_signal(
    probability,
    predicted_return,
):

    if not np.isfinite(
        probability
    ):

        return "HOLD"

    if not np.isfinite(
        predicted_return
    ):

        return "HOLD"

    if (
        probability >= 0.57
        and
        predicted_return >= 0.003
    ):

        return "BUY"

    if (
        probability <= 0.43
        and
        predicted_return <= -0.003
    ):

        return "SELL"

    return "HOLD"


# ============================================================
# BACKTEST
# ============================================================

def backtest_ticker(
    ticker,
    df,
    models,
):

    if models is None:
        return None

    try:

        clean = df.dropna(
            subset=
            FEATURE_COLUMNS
            +
            [
                "target",
                "future_return",
            ]
        ).copy()

        if len(clean) < (
            FAST_BACKTEST_ROWS
            + 50
        ):

            return None

        # ====================================================
        # 300 TARİHSEL KAYIT
        # ====================================================

        test = clean.tail(
            FAST_BACKTEST_ROWS
        ).copy()

        X_test = test[
            FEATURE_COLUMNS
        ]

        (
            probability,
            predicted_return,
        ) = predict_ensemble(
            models,
            X_test,
        )

        test[
            "Probability"
        ] = probability

        test[
            "Predicted_Return"
        ] = predicted_return

        test[
            "Signal"
        ] = [
            strategy_signal(
                p,
                r,
            )
            for p, r in zip(
                probability,
                predicted_return,
            )
        ]

        test[
            "Actual_Return"
        ] = test[
            "future_return"
        ]

        trades = test[
            test["Signal"].isin(
                [
                    "BUY",
                    "SELL",
                ]
            )
        ].copy()

        pred_cls = (
            test["Probability"] >= 0.5
        ).astype(int)

        accuracy = accuracy_score(
            test["target"],
            pred_cls,
        )

        precision = precision_score(
            test["target"],
            pred_cls,
            zero_division=0,
        )

        recall = recall_score(
            test["target"],
            pred_cls,
            zero_division=0,
        )

        f1 = f1_score(
            test["target"],
            pred_cls,
            zero_division=0,
        )

        return {

            "Ticker": ticker,

            "Test_Rows":
                len(test),

            "Trades":
                len(trades),

            "Accuracy":
                accuracy,

            "Precision":
                precision,

            "Recall":
                recall,

            "F1":
                f1,

            "Predictions":
                test,
        }

    except Exception:

        return None


# ============================================================
# BACKTEST RETURN
# ============================================================

def calculate_backtest_return(
    predictions
):

    if (
        predictions is None
        or
        len(predictions) == 0
    ):

        return 0.0

    capital = INITIAL_CAPITAL

    for _, row in predictions.iterrows():

        signal = row.get(
            "Signal",
            "HOLD",
        )

        actual = row.get(
            "Actual_Return",
            0.0,
        )

        if not np.isfinite(actual):
            continue

        if signal == "BUY":

            ret = actual

        elif signal == "SELL":

            ret = -actual

        else:

            ret = 0.0

        ret -= (
            COST_BPS / 10000.0
        )

        capital *= (
            1.0 + ret
        )

    return (
        capital /
        INITIAL_CAPITAL
        - 1
    )


# ============================================================
# MONTE CARLO
# ============================================================

def monte_carlo(
    returns
):

    returns = np.asarray(
        returns,
        dtype=float,
    )

    returns = returns[
        np.isfinite(returns)
    ]

    if len(returns) == 0:

        return {
            "Median": np.nan,
            "P05": np.nan,
            "P95": np.nan,
            "Win_Probability": np.nan,
        }

    rng = np.random.default_rng(
        RANDOM_STATE
    )

    simulations = []

    for _ in range(
        MONTE_CARLO_RUNS
    ):

        sample = rng.choice(
            returns,
            size=len(returns),
            replace=True,
        )

        equity = np.prod(
            1 + sample
        )

        simulations.append(
            equity - 1
        )

    simulations = np.asarray(
        simulations
    )

    return {

        "Median": float(
            np.percentile(
                simulations,
                50,
            )
        ),

        "P05": float(
            np.percentile(
                simulations,
                5,
            )
        ),

        "P95": float(
            np.percentile(
                simulations,
                95,
            )
        ),

        "Win_Probability": float(
            np.mean(
                simulations > 0
            )
        ),
    }


# ============================================================
# PREPARE
# ============================================================

def prepare_ticker(
    args
):

    ticker, market_df = args

    try:

        df = DATA_CACHE.get(
            ticker
        )

        if df is None:

            return (
                ticker,
                None,
            )

        features = add_features(
            df,
            market_df,
        )

        return (
            ticker,
            features,
        )

    except Exception:

        return (
            ticker,
            None,
        )


# ============================================================
# MAIN
# ============================================================

def main():

    global GLOBAL_BACKTEST_MODELS

    global GLOBAL_FINAL_MODELS

    total_start = time.time()

    print()
    print("=" * 72)
    print(
        " LEVEL 1000 V6 - BIST MASS AI"
    )
    print("=" * 72)

    print(
        "Piyasa          : BIST"
    )

    print(
        "Market          : XU100.IS"
    )

    print(
        "Gerçek para     : HAYIR"
    )

    print(
        "Otomatik emir   : HAYIR"
    )

    print(
        "Paper trading   : EVET"
    )

    print(
        "AI aday limiti  : YOK"
    )

    print(
        f"Tarihsel AI     : "
        f"{HISTORICAL_PREDICTION_ROWS:,} / hisse"
    )

    print("=" * 72)

    # ========================================================
    # UNIVERSE
    # ========================================================

    symbols = load_bist_universe()

    if not symbols:

        print(
            "[HATA] BIST hissesi bulunamadı."
        )

        return

    # ========================================================
    # MARKET
    # ========================================================

    market_df = load_market()

    if market_df is None:

        print(
            "[HATA] XU100 market verisi yok."
        )

        return

    # ========================================================
    # FAST
    # ========================================================

    candidates_df = fast_batch_scan(
        symbols
    )

    if (
        candidates_df is None
        or
        len(candidates_df) == 0
    ):

        print(
            "[HATA] Fast Scan sonuç vermedi."
        )

        return

    candidates = (
        candidates_df[
            "Ticker"
        ]
        .astype(str)
        .tolist()
    )

    print()
    print(
        f"[AI CANDIDATE] "
        f"{len(candidates):,}"
    )

    # ========================================================
    # AI DATA
    # ========================================================

    download_ai_batch(
        candidates
    )

    available = [
        t
        for t in candidates
        if t in DATA_CACHE
    ]

    print()
    print(
        f"[AI DATA READY] "
        f"{len(available):,}/"
        f"{len(candidates):,}"
    )

    if not available:

        print(
            "[HATA] AI verisi yok."
        )

        return

    # ========================================================
    # FEATURES
    # ========================================================

    print()
    print("=" * 72)
    print(
        " FEATURE ENGINE"
    )
    print("=" * 72)

    feature_start = time.time()

    feature_data = {}

    worker_count = min(
        12,
        len(available),
    )

    with ThreadPoolExecutor(
        max_workers=worker_count
    ) as executor:

        futures = [
            executor.submit(
                prepare_ticker,
                (
                    ticker,
                    market_df,
                ),
            )
            for ticker in available
        ]

        completed = 0

        for future in as_completed(
            futures
        ):

            ticker, features = (
                future.result()
            )

            if features is not None:

                feature_data[
                    ticker
                ] = features

            completed += 1

            if (
                completed % 25 == 0
                or
                completed == len(available)
            ):

                print(
                    f"[FEATURE] "
                    f"{completed}/"
                    f"{len(available)}"
                )

    print()
    print(
        f"[FEATURE OK] "
        f"{len(feature_data):,} ticker | "
        f"{(time.time() - feature_start) / 60:.2f} dk"
    )

    if not feature_data:

        print(
            "[HATA] Feature datası oluşmadı."
        )

        return

    # ========================================================
    # GLOBAL BACKTEST TRAIN
    # ========================================================

    print()
    print("=" * 72)
    print(
        " GLOBAL AI BACKTEST MODEL"
    )
    print("=" * 72)

    training_parts = []

    for ticker, df in feature_data.items():

        clean = df.dropna(
            subset=
            FEATURE_COLUMNS
            +
            [
                "target",
                "future_return",
            ]
        ).copy()

        if len(clean) < (
            TRAIN_MIN
            +
            FAST_BACKTEST_ROWS
            +
            HORIZON
        ):

            continue

        end_train = -(
            FAST_BACKTEST_ROWS
            +
            HORIZON
        )

        train_part = clean.iloc[
            :end_train
        ].copy()

        if len(train_part) >= TRAIN_MIN:

            training_parts.append(
                train_part[
                    FEATURE_COLUMNS
                    +
                    [
                        "target",
                        "future_return",
                    ]
                ]
            )

    if not training_parts:

        print(
            "[HATA] Global eğitim datası oluşmadı."
        )

        return

    global_train = pd.concat(
        training_parts,
        ignore_index=True,
    )

    if len(global_train) > 1_000_000:

        global_train = global_train.sample(
            n=1_000_000,
            random_state=RANDOM_STATE,
        )

    print(
        f"[GLOBAL TRAIN] "
        f"{len(global_train):,} satır"
    )

    GLOBAL_BACKTEST_MODELS = (
        train_shared_models(
            global_train
        )
    )

    if GLOBAL_BACKTEST_MODELS is None:

        print(
            "[HATA] Backtest modeli eğitilemedi."
        )

        return

    # ========================================================
    # MASS HISTORICAL AI
    # ========================================================

    print()
    print("=" * 72)
    print(
        " MASS HISTORICAL AI PREDICTIONS"
    )
    print("=" * 72)

    print(
        f"Hedef: "
        f"{len(feature_data):,} hisse x "
        f"{HISTORICAL_PREDICTION_ROWS:,} tarih"
    )

    metrics_rows = []

    prediction_rows = []

    trade_rows = []

    monte_rows = []

    total = len(feature_data)

    process_start = time.time()

    for idx, (
        ticker,
        df
    ) in enumerate(
        feature_data.items(),
        1,
    ):

        result = backtest_ticker(
            ticker,
            df,
            GLOBAL_BACKTEST_MODELS,
        )

        if result is None:

            continue

        predictions = (
            result["Predictions"]
        )

        backtest_return = (
            calculate_backtest_return(
                predictions
            )
        )

        metrics_rows.append({

            "Ticker": ticker,

            "Test_Rows":
                result["Test_Rows"],

            "Trades":
                result["Trades"],

            "Accuracy":
                result["Accuracy"],

            "Precision":
                result["Precision"],

            "Recall":
                result["Recall"],

            "F1":
                result["F1"],

            "Backtest_Return":
                backtest_return,
        })

        # ====================================================
        # TARİHSEL AI KAYITLARI
        # ====================================================

        for dt, row in predictions.iterrows():

            try:

                price = float(
                    df.loc[
                        dt,
                        "Close"
                    ]
                )

            except Exception:

                price = np.nan

            prediction_rows.append({

                "Date": dt,

                "Ticker": ticker,

                "Price": price,

                "Probability": float(
                    row["Probability"]
                ),

                "Predicted_Return": float(
                    row["Predicted_Return"]
                ),

                "Signal": row["Signal"],

                "Signal_Type": "AI_HISTORICAL",

                "Paper_Status": "PAPER_ONLY",

                "Real_Order": "NO",

                "Actual_Return": float(
                    row["Actual_Return"]
                ),
            })

            if row["Signal"] in [
                "BUY",
                "SELL",
            ]:

                trade_rows.append({

                    "Date": dt,

                    "Ticker": ticker,

                    "Signal": row["Signal"],

                    "Predicted_Return": float(
                        row["Predicted_Return"]
                    ),

                    "Probability": float(
                        row["Probability"]
                    ),

                    "Actual_Return": float(
                        row["Actual_Return"]
                    ),
                })

        returns = []

        for _, row in predictions.iterrows():

            if row["Signal"] == "BUY":

                returns.append(
                    row["Actual_Return"]
                )

            elif row["Signal"] == "SELL":

                returns.append(
                    -row["Actual_Return"]
                )

        mc = monte_carlo(
            returns
        )

        monte_rows.append({

            "Ticker": ticker,

            **mc,
        })

        elapsed = (
            time.time()
            - process_start
        )

        speed = (
            idx / elapsed
            if elapsed > 0
            else 0
        )

        remaining = (
            total - idx
        )

        eta = (
            remaining / speed
            if speed > 0
            else 0
        )

        current_records = len(
            prediction_rows
        )

        print(
            f"[AI {idx}/{total}] "
            f"{ticker} | "
            f"kayıt={current_records:,} | "
            f"ETA={eta / 60:.1f} dk"
        )

    # ========================================================
    # FINAL MODEL
    # ========================================================

    print()
    print("=" * 72)
    print(
        " GLOBAL AI FINAL MODEL"
    )
    print("=" * 72)

    final_parts = []

    for ticker, df in feature_data.items():

        clean = df.dropna(
            subset=
            FEATURE_COLUMNS
            +
            [
                "target",
                "future_return",
            ]
        ).copy()

        if len(clean) >= TRAIN_MIN:

            final_parts.append(
                clean[
                    FEATURE_COLUMNS
                    +
                    [
                        "target",
                        "future_return",
                    ]
                ]
            )

    if not final_parts:

        print(
            "[HATA] Final eğitim datası yok."
        )

        return

    final_train = pd.concat(
        final_parts,
        ignore_index=True,
    )

    if len(final_train) > 1_000_000:

        final_train = final_train.sample(
            n=1_000_000,
            random_state=RANDOM_STATE,
        )

    print(
        f"[FINAL TRAIN] "
        f"{len(final_train):,} satır"
    )

    GLOBAL_FINAL_MODELS = (
        train_shared_models(
            final_train
        )
    )

    if GLOBAL_FINAL_MODELS is None:

        print(
            "[HATA] Final model eğitilemedi."
        )

        return

    # ========================================================
    # CURRENT SIGNALS
    # ========================================================

    print()
    print("=" * 72)
    print(
        " CURRENT BIST AI SIGNALS"
    )
    print("=" * 72)

    current_signal_rows = []

    for ticker, df in feature_data.items():

        try:

            clean = df.dropna(
                subset=FEATURE_COLUMNS
            ).copy()

            if len(clean) == 0:
                continue

            last = clean.tail(1)

            (
                probability,
                predicted_return,
            ) = predict_ensemble(
                GLOBAL_FINAL_MODELS,
                last[
                    FEATURE_COLUMNS
                ],
            )

            probability = float(
                probability[0]
            )

            predicted_return = float(
                predicted_return[0]
            )

            signal = strategy_signal(
                probability,
                predicted_return,
            )

            price = float(
                last[
                    "Close"
                ].iloc[0]
            )

            current_signal_rows.append({

                "Ticker": ticker,

                "Price": price,

                "Probability": probability,

                "Predicted_Return":
                    predicted_return,

                "Signal": signal,

                "Signal_Type": "AI_CURRENT",

                "Paper_Status":
                    "PAPER_ONLY",

                "Real_Order": "NO",

                "Quantity": 1,

                "Position_Value": price,
            })

        except Exception:

            continue

    # ========================================================
    # DATAFRAMES
    # ========================================================

    historical_df = pd.DataFrame(
        prediction_rows
    )

    current_df = pd.DataFrame(
        current_signal_rows
    )

    paper_df = current_df.copy()

    metrics_df = pd.DataFrame(
        metrics_rows
    )

    predictions_df = historical_df.copy()

    trades_df = pd.DataFrame(
        trade_rows
    )

    monte_df = pd.DataFrame(
        monte_rows
    )

    # ========================================================
    # MASS DATA SORT
    # ========================================================

    if len(historical_df):

        signal_order = {
            "BUY": 0,
            "SELL": 1,
            "HOLD": 2,
        }

        historical_df["_order"] = (
            historical_df[
                "Signal"
            ].map(
                signal_order
            )
        )

        historical_df = (
            historical_df
            .sort_values(
                [
                    "Date",
                    "_order",
                    "Probability",
                    "Predicted_Return",
                ],
                ascending=[
                    False,
                    True,
                    False,
                    False,
                ],
            )
            .drop(
                columns=["_order"]
            )
        )

    # ========================================================
    # CURRENT SORT
    # ========================================================

    if len(current_df):

        signal_order = {
            "BUY": 0,
            "SELL": 1,
            "HOLD": 2,
        }

        current_df["_order"] = (
            current_df[
                "Signal"
            ].map(
                signal_order
            )
        )

        current_df = (
            current_df
            .sort_values(
                [
                    "_order",
                    "Probability",
                    "Predicted_Return",
                ],
                ascending=[
                    True,
                    False,
                    False,
                ],
            )
            .drop(
                columns=["_order"]
            )
        )

    # ========================================================
    # SAVE MASS DATA
    # ========================================================

    historical_df.to_csv(
        LATEST_SIGNALS,
        index=False,
        encoding="utf-8-sig",
    )

    # ========================================================
    # SAVE CURRENT PAPER
    # ========================================================

    paper_df.to_csv(
        PAPER_SIGNALS,
        index=False,
        encoding="utf-8-sig",
    )

    metrics_df.to_csv(
        MODEL_METRICS,
        index=False,
        encoding="utf-8-sig",
    )

    trades_df.to_csv(
        TRADE_LOG,
        index=False,
        encoding="utf-8-sig",
    )

    predictions_df.to_csv(
        PREDICTIONS,
        index=False,
        encoding="utf-8-sig",
    )

    monte_df.to_csv(
        MONTE_CARLO,
        index=False,
        encoding="utf-8-sig",
    )

    # ========================================================
    # VARIANT SUMMARY
    # ========================================================

    if len(historical_df):

        summary = (
            historical_df
            .groupby("Signal")
            .agg(

                Count=(
                    "Ticker",
                    "count",
                ),

                Avg_Probability=(
                    "Probability",
                    "mean",
                ),

                Avg_Predicted_Return=(
                    "Predicted_Return",
                    "mean",
                ),
            )
            .reset_index()
        )

    else:

        summary = pd.DataFrame(
            columns=[
                "Signal",
                "Count",
                "Avg_Probability",
                "Avg_Predicted_Return",
            ]
        )

    summary.to_csv(
        VARIANT_SUMMARY,
        index=False,
        encoding="utf-8-sig",
    )

    # ========================================================
    # FINAL COUNTS
    # ========================================================

    total_elapsed = (
        time.time()
        - total_start
    )

    print()
    print("=" * 72)
    print(
        " LEVEL 1000 V6 TAMAMLANDI"
    )
    print("=" * 72)

    print(
        f"Taranan BIST          : "
        f"{len(symbols):,}"
    )

    print(
        f"Fast uygun            : "
        f"{len(candidates_df):,}"
    )

    print(
        f"AI veri               : "
        f"{len(available):,}"
    )

    print(
        f"Güncel AI sinyal      : "
        f"{len(current_df):,}"
    )

    print(
        f"ARKA PLAN AI KAYDI    : "
        f"{len(historical_df):,}"
    )

    if len(historical_df):

        buy_count = int(
            (
                historical_df[
                    "Signal"
                ] == "BUY"
            ).sum()
        )

        sell_count = int(
            (
                historical_df[
                    "Signal"
                ] == "SELL"
            ).sum()
        )

        hold_count = int(
            (
                historical_df[
                    "Signal"
                ] == "HOLD"
            ).sum()
        )

        print()
        print(
            f"Historical BUY       : "
            f"{buy_count:,}"
        )

        print(
            f"Historical SELL      : "
            f"{sell_count:,}"
        )

        print(
            f"Historical HOLD      : "
            f"{hold_count:,}"
        )

    if len(current_df):

        current_buy = int(
            (
                current_df[
                    "Signal"
                ] == "BUY"
            ).sum()
        )

        current_sell = int(
            (
                current_df[
                    "Signal"
                ] == "SELL"
            ).sum()
        )

        current_hold = int(
            (
                current_df[
                    "Signal"
                ] == "HOLD"
            ).sum()
        )

        print()
        print(
            "GÜNCEL SİNYALLER"
        )

        print(
            f"BUY                 : "
            f"{current_buy:,}"
        )

        print(
            f"SELL                : "
            f"{current_sell:,}"
        )

        print(
            f"HOLD                : "
            f"{current_hold:,}"
        )

    print()

    print(
        f"Toplam süre           : "
        f"{total_elapsed / 60:.2f} dk"
    )

    print()
    print(
        "ÇIKTILAR:"
    )

    print(
        f" - {LATEST_SIGNALS}"
    )

    print(
        f" - {PAPER_SIGNALS}"
    )

    print(
        f" - {MODEL_METRICS}"
    )

    print(
        f" - {TRADE_LOG}"
    )

    print(
        f" - {VARIANT_SUMMARY}"
    )

    print(
        f" - {MONTE_CARLO}"
    )

    print(
        f" - {PREDICTIONS}"
    )

    print(
        f" - {FAST_UNIVERSE}"
    )

    print(
        f" - {AI_CANDIDATES_FILE}"
    )

    print()
    print(
        "ARKA PLAN HEDEFİ    : "
        "100.000+"
    )

    print(
        f"GERÇEK KAYIT        : "
        f"{len(historical_df):,}"
    )

    print(
        "VİTRİN LİMİTİ       : 2.000"
    )

    print(
        "GERÇEK PARA         : HAYIR"
    )

    print(
        "OTOMATİK EMİR       : HAYIR"
    )

    print(
        "PAPER ONLY          : EVET"
    )

    print("=" * 72)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()