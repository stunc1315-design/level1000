from pathlib import Path
import json
import time
import random
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
)
from sklearn.neighbors import NearestNeighbors


# ============================================================
# LEVEL 1000 FINAL
# GLOBAL AI STOCK SCANNER
#
# GERÇEK PARA   : HAYIR
# OTOMATİK EMİR : HAYIR
#
# AMAÇ:
#   Tek final sistem
#   Walk Forward
#   Gerçek Forward Return
#   BUY / SELL performans testi
#   5 yıllık veri
#   Sağlam TOP 300
# ============================================================


# ============================================================
# KLASÖRLER
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "level1000_data"
CACHE_DIR = DATA_DIR / "cache"
SYMBOLS_FILE = BASE_DIR / "symbols.txt"

PROGRESS_FILE = DATA_DIR / "final_progress.json"
FAILED_FILE = DATA_DIR / "final_failed_symbols.txt"

SCAN_FILE = DATA_DIR / "level1000_final_scan.csv"
TOP_FILE = DATA_DIR / "level1000_final_top.csv"
LATEST_FILE = DATA_DIR / "level1000_final_latest.csv"
MODEL_FILE = DATA_DIR / "level1000_final_model_metrics.csv"
BACKTEST_FILE = DATA_DIR / "level1000_final_backtest.csv"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# AYARLAR
# ============================================================

YEARS = 5

DOWNLOAD_WORKERS = 12
CACHE_WORKERS = 24

BATCH_SIZE = 150

RETRY_COUNT = 1
RETRY_SLEEP = 0.8

MIN_ROWS = 220

FORWARD_DAYS = 5

# Daha seçici hedef.
TARGET_THRESHOLD = 0.006

MAX_TRAIN_ROWS = 350000

TOP_N = 300

EXPECTED_RETURN_SAMPLE = 25000
NEIGHBORS_PER_QUERY = 35
EXPECTED_RETURN_CANDIDATES = 1500

EXPECTED_RETURN_LOW = -0.20
EXPECTED_RETURN_HIGH = 0.20

RANDOM_SEED = 42

# Minimum sinyal kalitesi
MIN_PROBABILITY = 0.52
MIN_EDGE = 0.015

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)


# ============================================================
# FEATURELER
# ============================================================

FEATURE_COLUMNS = [
    "ret1",
    "ret3",
    "ret5",
    "ret10",
    "ret20",
    "volatility10",
    "volatility20",
    "rsi14",
    "atr_pct",
    "volume_ratio",
    "price_vs_sma20",
    "price_vs_sma50",
    "sma20_vs_sma50",
    "high_low_pct",
    "close_location",
]


# ============================================================
# SEMBOL
# ============================================================

def clean_symbol(symbol):
    return str(symbol).strip().upper()


def load_symbols():

    if not SYMBOLS_FILE.exists():
        raise FileNotFoundError(
            f"symbols.txt bulunamadı:\n{SYMBOLS_FILE}"
        )

    symbols = []
    seen = set()

    text = SYMBOLS_FILE.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    for line in text.splitlines():

        symbol = clean_symbol(line)

        if not symbol:
            continue

        if symbol.startswith("#"):
            continue

        if symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)

    return symbols


# ============================================================
# CACHE PATH
# ============================================================

def cache_path(symbol):

    safe = (
        symbol
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace("*", "_")
        .replace("?", "_")
        .replace('"', "_")
        .replace("<", "_")
        .replace(">", "_")
        .replace("|", "_")
    )

    return CACHE_DIR / f"{safe}.csv"


# ============================================================
# FRAME TEMİZLE
# ============================================================

def normalize_download_frame(df, symbol):

    if df is None or df.empty:
        return None

    try:

        if isinstance(df.columns, pd.MultiIndex):

            level0 = [
                str(x)
                for x in df.columns.get_level_values(0)
            ]

            level1 = [
                str(x)
                for x in df.columns.get_level_values(1)
            ]

            wanted = {
                "Open",
                "High",
                "Low",
                "Close",
                "Adj Close",
                "Volume",
            }

            if any(x in wanted for x in level0):

                out = df.copy()

                out.columns = (
                    df.columns.get_level_values(0)
                )

            else:

                matches = []

                for i, value in enumerate(level1):

                    if value.upper() == symbol.upper():
                        matches.append(i)

                if matches:

                    out = df.iloc[:, matches].copy()

                    out.columns = (
                        df.columns
                        .get_level_values(0)[matches]
                    )

                else:

                    ticker = (
                        df.columns
                        .get_level_values(1)[0]
                    )

                    out = df.xs(
                        ticker,
                        axis=1,
                        level=1,
                        drop_level=True,
                    )

        else:

            out = df.copy()

        rename = {}

        for column in out.columns:

            name = str(column).strip()

            if name.lower() == "adj close":
                rename[column] = "Adj Close"
            else:
                rename[column] = name.title()

        out = out.rename(columns=rename)

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        if not all(c in out.columns for c in required):
            return None

        out = out[required].copy()

        for column in required:

            out[column] = pd.to_numeric(
                out[column],
                errors="coerce",
            )

        out = out.replace(
            [np.inf, -np.inf],
            np.nan,
        )

        out = out.dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close",
            ]
        )

        if out.empty:
            return None

        out.index = pd.to_datetime(
            out.index,
            errors="coerce",
        )

        out = out[~out.index.isna()]

        out = out[
            ~out.index.duplicated(
                keep="last"
            )
        ]

        out = out.sort_index()

        if len(out) < MIN_ROWS:
            return None

        return out

    except Exception:
        return None


# ============================================================
# CACHE OKU
# ============================================================

def load_cache(symbol):

    path = cache_path(symbol)

    if not path.exists():
        return None

    try:

        df = pd.read_csv(
            path,
            index_col=0,
            parse_dates=True,
        )

        return normalize_download_frame(
            df,
            symbol,
        )

    except Exception:

        return None


# ============================================================
# CACHE GERÇEKTEN 5 YIL MI?
# ============================================================

def cache_is_complete(df):

    if df is None or df.empty:
        return False

    try:

        first = pd.Timestamp(df.index.min())
        last = pd.Timestamp(df.index.max())

        span_days = (
            last - first
        ).days

        required_days = int(
            YEARS * 365.25 * 0.88
        )

        return (
            len(df) >= MIN_ROWS
            and span_days >= required_days
        )

    except Exception:

        return False


# ============================================================
# TEK SEMBOL İNDİR
# ============================================================

def download_symbol(symbol):

    path = cache_path(symbol)

    for attempt in range(RETRY_COUNT + 1):

        try:

            end = pd.Timestamp.now(
                tz="UTC"
            ).tz_localize(None)

            start = (
                end
                - pd.DateOffset(
                    years=YEARS
                )
            )

            df = yf.download(
                symbol,
                start=start.strftime("%Y-%m-%d"),
                end=(
                    end
                    + pd.Timedelta(days=1)
                ).strftime("%Y-%m-%d"),
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=False,
                timeout=20,
            )

            clean = normalize_download_frame(
                df,
                symbol,
            )

            if (
                clean is not None
                and len(clean) >= MIN_ROWS
            ):

                clean.to_csv(path)

                return (
                    symbol,
                    clean,
                    True,
                )

        except Exception:
            pass

        if attempt < RETRY_COUNT:
            time.sleep(RETRY_SLEEP)

    return (
        symbol,
        None,
        False,
    )


# ============================================================
# PROGRESS
# ============================================================

def save_progress(completed, failed):

    payload = {
        "completed_symbols":
            sorted(set(completed)),

        "failed_symbols":
            sorted(set(failed)),

        "updated":
            time.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
    }

    tmp = PROGRESS_FILE.with_suffix(".tmp")

    try:

        tmp.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        tmp.replace(PROGRESS_FILE)

    except Exception:
        pass


def save_failed(failed):

    try:

        FAILED_FILE.write_text(
            "\n".join(
                sorted(set(failed))
            ),
            encoding="utf-8",
        )

    except Exception:
        pass


# ============================================================
# VERİ TOPLAMA
# ============================================================

def collect_data(symbols):

    print()
    print("=" * 78)
    print(" LEVEL 1000 FINAL VERİ MOTORU")
    print("=" * 78)

    print(
        f"Toplam sembol       : {len(symbols):,}"
    )

    print(
        "[CACHE] 5 yıllık geçmiş kontrol ediliyor."
    )

    start_time = time.time()

    data = {}

    # --------------------------------------------------------
    # CACHE KONTROL
    # --------------------------------------------------------

    def cache_job(symbol):

        df = load_cache(symbol)

        if cache_is_complete(df):
            return symbol, df, True

        return symbol, None, False

    with ThreadPoolExecutor(
        max_workers=CACHE_WORKERS
    ) as executor:

        futures = [
            executor.submit(
                cache_job,
                symbol,
            )
            for symbol in symbols
        ]

        for future in as_completed(futures):

            try:

                symbol, df, ok = (
                    future.result()
                )

                if ok:
                    data[symbol] = df

            except Exception:
                pass

    missing = [
        s
        for s in symbols
        if s not in data
    ]

    print(
        f"[CACHE] 5 yıllık hazır : "
        f"{len(data):,}"
    )

    print(
        f"[DOWNLOAD] Eksik/eski   : "
        f"{len(missing):,}"
    )

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    failed = set()

    if missing:

        total_batches = (
            len(missing)
            + BATCH_SIZE
            - 1
        ) // BATCH_SIZE

        with ThreadPoolExecutor(
            max_workers=DOWNLOAD_WORKERS
        ) as executor:

            for batch_start in range(
                0,
                len(missing),
                BATCH_SIZE,
            ):

                batch = missing[
                    batch_start:
                    batch_start + BATCH_SIZE
                ]

                batch_no = (
                    batch_start
                    // BATCH_SIZE
                    + 1
                )

                print(
                    f"[DOWNLOAD] "
                    f"Batch {batch_no}/"
                    f"{total_batches} "
                    f"| {len(batch)}"
                )

                futures = {
                    executor.submit(
                        download_symbol,
                        symbol,
                    ): symbol
                    for symbol in batch
                }

                for future in as_completed(
                    futures
                ):

                    symbol = futures[future]

                    try:

                        (
                            sym,
                            df,
                            ok,
                        ) = future.result()

                    except Exception:

                        sym = symbol
                        df = None
                        ok = False

                    if ok and df is not None:

                        data[sym] = df

                    else:

                        failed.add(sym)

                save_progress(
                    data.keys(),
                    failed,
                )

                save_failed(failed)

                print(
                    f"           "
                    f"Hazır={len(data):,} "
                    f"| Başarısız={len(failed):,}"
                )

    failed = (
        set(symbols)
        - set(data.keys())
    )

    save_progress(
        data.keys(),
        failed,
    )

    save_failed(failed)

    print()
    print("=" * 78)
    print(" VERİ TOPLAMA TAMAMLANDI")
    print("=" * 78)

    print(
        f"Taranan sembol       : "
        f"{len(symbols):,}"
    )

    print(
        f"5 yıllık veri        : "
        f"{len(data):,}"
    )

    print(
        f"Eksik/başarısız      : "
        f"{len(failed):,}"
    )

    print(
        f"Veri süresi          : "
        f"{(time.time() - start_time) / 60:.1f} dakika"
    )

    return data


# ============================================================
# RSI
# ============================================================

def calculate_rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False,
    ).mean()

    rs = (
        avg_gain
        / avg_loss.replace(
            0,
            np.nan,
        )
    )

    return (
        100
        - (
            100
            / (1 + rs)
        )
    ) / 100.0


# ============================================================
# FEATURE ENGINE
# ============================================================

def build_features(df):

    x = df.copy()

    close = x["Close"]
    high = x["High"]
    low = x["Low"]

    volume = (
        x["Volume"]
        .replace(0, np.nan)
    )

    x["ret1"] = close.pct_change(1)
    x["ret3"] = close.pct_change(3)
    x["ret5"] = close.pct_change(5)
    x["ret10"] = close.pct_change(10)
    x["ret20"] = close.pct_change(20)

    x["volatility10"] = (
        x["ret1"]
        .rolling(10)
        .std()
    )

    x["volatility20"] = (
        x["ret1"]
        .rolling(20)
        .std()
    )

    x["rsi14"] = calculate_rsi(close)

    tr1 = high - low

    tr2 = (
        high
        - close.shift(1)
    ).abs()

    tr3 = (
        low
        - close.shift(1)
    ).abs()

    tr = pd.concat(
        [
            tr1,
            tr2,
            tr3,
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.rolling(14).mean()

    x["atr_pct"] = (
        atr
        / close.replace(
            0,
            np.nan,
        )
    )

    volume20 = (
        volume
        .rolling(20)
        .mean()
    )

    x["volume_ratio"] = (
        volume
        / volume20.replace(
            0,
            np.nan,
        )
    )

    sma20 = (
        close
        .rolling(20)
        .mean()
    )

    sma50 = (
        close
        .rolling(50)
        .mean()
    )

    x["price_vs_sma20"] = (
        close
        / sma20.replace(
            0,
            np.nan,
        )
        - 1
    )

    x["price_vs_sma50"] = (
        close
        / sma50.replace(
            0,
            np.nan,
        )
        - 1
    )

    x["sma20_vs_sma50"] = (
        sma20
        / sma50.replace(
            0,
            np.nan,
        )
        - 1
    )

    x["high_low_pct"] = (
        (high - low)
        / close.replace(
            0,
            np.nan,
        )
    )

    candle_range = (
        high - low
    ).replace(
        0,
        np.nan,
    )

    x["close_location"] = (
        close - low
    ) / candle_range

    x = x.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    return x


# ============================================================
# TRAINING ROWS
# ============================================================

def make_training_rows(symbol, df):

    feat = build_features(df)

    feat["future_return"] = (
        feat["Close"].shift(
            -FORWARD_DAYS
        )
        / feat["Close"]
        - 1
    )

    train = feat.dropna(
        subset=(
            FEATURE_COLUMNS
            + ["future_return"]
        )
    ).copy()

    if len(train) < 100:
        return None, None

    future = train["future_return"]

    train["target"] = np.select(
        [
            future > TARGET_THRESHOLD,
            future < -TARGET_THRESHOLD,
        ],
        [
            1,
            -1,
        ],
        default=0,
    )

    train["Symbol"] = symbol

    train["Date"] = pd.to_datetime(
        train.index
    )

    valid_latest = feat.dropna(
        subset=FEATURE_COLUMNS
    )

    if valid_latest.empty:
        return train, None

    last = valid_latest.iloc[-1]

    latest = {
        "Symbol": symbol,
        "Date": pd.to_datetime(
            valid_latest.index[-1]
        ),
        "Close": float(
            last["Close"]
        ),
    }

    for column in FEATURE_COLUMNS:

        latest[column] = float(
            last[column]
        )

    latest["History_Start"] = pd.to_datetime(
        df.index.min()
    )

    latest["History_End"] = pd.to_datetime(
        df.index.max()
    )

    return train, latest


# ============================================================
# AI DATA
# ============================================================

def prepare_ai_data(data):

    print()
    print("=" * 78)
    print(" AI VERİ HAZIRLAMA")
    print("=" * 78)

    train_parts = []
    latest_rows = []

    for symbol, df in data.items():

        try:

            train, latest = (
                make_training_rows(
                    symbol,
                    df,
                )
            )

            if (
                train is not None
                and not train.empty
            ):
                train_parts.append(train)

            if latest is not None:
                latest_rows.append(latest)

        except Exception:
            continue

    if not train_parts:
        raise RuntimeError(
            "Eğitim verisi oluşmadı."
        )

    train_all = pd.concat(
        train_parts,
        ignore_index=True,
    )

    latest_df = pd.DataFrame(
        latest_rows
    )

    train_all["Date"] = pd.to_datetime(
        train_all["Date"],
        errors="coerce",
    )

    train_all = train_all.dropna(
        subset=["Date"]
    )

    train_all = (
        train_all
        .sort_values("Date")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # MAX TRAIN
    # --------------------------------------------------------

    if len(train_all) > MAX_TRAIN_ROWS:

        # Zamansal örnekleme.
        # Baştan sona kronolojiyi korur.
        indexes = np.linspace(
            0,
            len(train_all) - 1,
            MAX_TRAIN_ROWS,
        ).astype(int)

        train_all = (
            train_all
            .iloc[indexes]
            .copy()
            .reset_index(drop=True)
        )

    for column in FEATURE_COLUMNS:

        train_all[column] = pd.to_numeric(
            train_all[column],
            errors="coerce",
        )

        latest_df[column] = pd.to_numeric(
            latest_df[column],
            errors="coerce",
        )

    train_all = train_all.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    latest_df = latest_df.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    train_all = train_all.dropna(
        subset=(
            FEATURE_COLUMNS
            + [
                "target",
                "future_return",
            ]
        )
    )

    latest_df = latest_df.dropna(
        subset=FEATURE_COLUMNS
    )

    print(
        f"[AI DATA] Eğitim satırı : "
        f"{len(train_all):,}"
    )

    print(
        f"[AI DATA] Son sinyal    : "
        f"{len(latest_df):,}"
    )

    years = sorted(
        train_all["Date"]
        .dt.year
        .unique()
    )

    print(
        f"[AI DATA] Yıllar       : "
        f"{years}"
    )

    counts = (
        train_all["target"]
        .value_counts()
    )

    print()
    print("[AI] Sınıf dağılımı:")

    print(
        f"  SELL : "
        f"{int(counts.get(-1, 0)):,}"
    )

    print(
        f"  HOLD : "
        f"{int(counts.get(0, 0)):,}"
    )

    print(
        f"  BUY  : "
        f"{int(counts.get(1, 0)):,}"
    )

    return train_all, latest_df


# ============================================================
# MODELLER
# ============================================================

def build_logistic():

    return LogisticRegression(
        max_iter=700,
        C=0.30,
        class_weight="balanced",
        random_state=RANDOM_SEED,
    )


def build_gradient():

    return HistGradientBoostingClassifier(
        learning_rate=0.06,
        max_iter=180,
        max_leaf_nodes=31,
        min_samples_leaf=100,
        l2_regularization=1.5,
        random_state=RANDOM_SEED,
    )


# ============================================================
# PROBABILITY
# ============================================================

def combine_probabilities(
    p1,
    classes1,
    p2,
    classes2,
):

    output = np.zeros(
        (len(p1), 3),
        dtype=np.float64,
    )

    class_to_index = {
        -1: 0,
        0: 1,
        1: 2,
    }

    for j, cls in enumerate(classes1):

        cls = int(cls)

        if cls in class_to_index:

            output[
                :,
                class_to_index[cls],
            ] += (
                p1[:, j] * 0.45
            )

    for j, cls in enumerate(classes2):

        cls = int(cls)

        if cls in class_to_index:

            output[
                :,
                class_to_index[cls],
            ] += (
                p2[:, j] * 0.55
            )

    sums = output.sum(
        axis=1,
        keepdims=True,
    )

    sums[sums == 0] = 1

    return output / sums


# ============================================================
# MODEL PREDICT
# ============================================================

def model_predict(
    train_part,
    test_part,
):

    X_train = train_part[
        FEATURE_COLUMNS
    ]

    y_train = train_part[
        "target"
    ].astype(int)

    X_test = test_part[
        FEATURE_COLUMNS
    ]

    scaler = StandardScaler()

    X_train_scaled = scaler.fit_transform(
        X_train
    )

    X_test_scaled = scaler.transform(
        X_test
    )

    logistic = build_logistic()

    logistic.fit(
        X_train_scaled,
        y_train,
    )

    p_log = logistic.predict_proba(
        X_test_scaled
    )

    gradient = build_gradient()

    gradient.fit(
        X_train,
        y_train,
    )

    p_grad = gradient.predict_proba(
        X_test
    )

    probabilities = combine_probabilities(
        p_log,
        logistic.classes_,
        p_grad,
        gradient.classes_,
    )

    classes = np.array(
        [-1, 0, 1]
    )

    predicted = classes[
        np.argmax(
            probabilities,
            axis=1,
        )
    ]

    return predicted, probabilities


# ============================================================
# FORWARD TEST
# ============================================================

def calculate_forward_metrics(
    test_part,
    predicted,
    probabilities,
    period_name,
):

    actual_return = test_part[
        "future_return"
    ].to_numpy()

    pred = np.asarray(
        predicted
    )

    rows = []

    for i in range(len(pred)):

        signal = int(pred[i])

        ret = float(
            actual_return[i]
        )

        if signal == 1:
            strategy_return = ret

        elif signal == -1:
            strategy_return = -ret

        else:
            strategy_return = 0.0

        rows.append({
            "Period": period_name,
            "Predicted": signal,
            "Actual_Return": ret,
            "Strategy_Return": strategy_return,
            "Probability": float(
                np.max(
                    probabilities[i]
                )
            ),
        })

    bt = pd.DataFrame(rows)

    result = {
        "Period": period_name,
        "Signals": len(bt),
    }

    buy = bt[
        bt["Predicted"] == 1
    ]

    sell = bt[
        bt["Predicted"] == -1
    ]

    active = bt[
        bt["Predicted"] != 0
    ]

    result["BUY_Count"] = len(buy)
    result["SELL_Count"] = len(sell)
    result["HOLD_Count"] = int(
        (bt["Predicted"] == 0).sum()
    )

    if len(buy):

        result["BUY_HitRate"] = float(
            (
                buy["Actual_Return"] > 0
            ).mean()
        )

        result["BUY_AvgReturn"] = float(
            buy["Actual_Return"].mean()
        )

        result["BUY_MedianReturn"] = float(
            buy["Actual_Return"].median()
        )

    else:

        result["BUY_HitRate"] = 0.0
        result["BUY_AvgReturn"] = 0.0
        result["BUY_MedianReturn"] = 0.0

    if len(sell):

        result["SELL_HitRate"] = float(
            (
                sell["Actual_Return"] < 0
            ).mean()
        )

        result["SELL_AvgReturn"] = float(
            -sell["Actual_Return"].mean()
        )

        result["SELL_MedianReturn"] = float(
            -sell["Actual_Return"].median()
        )

    else:

        result["SELL_HitRate"] = 0.0
        result["SELL_AvgReturn"] = 0.0
        result["SELL_MedianReturn"] = 0.0

    if len(active):

        result["Strategy_AvgReturn"] = float(
            active[
                "Strategy_Return"
            ].mean()
        )

        result["Strategy_MedianReturn"] = float(
            active[
                "Strategy_Return"
            ].median()
        )

        result["Strategy_WinRate"] = float(
            (
                active[
                    "Strategy_Return"
                ] > 0
            ).mean()
        )

    else:

        result["Strategy_AvgReturn"] = 0.0
        result["Strategy_MedianReturn"] = 0.0
        result["Strategy_WinRate"] = 0.0

    return result


# ============================================================
# WALK FORWARD
# ============================================================

def walk_forward_validation(train_all):

    print()
    print("=" * 78)
    print(" FINAL WALK-FORWARD + FORWARD TEST")
    print("=" * 78)

    df = (
        train_all
        .copy()
        .sort_values("Date")
        .reset_index(drop=True)
    )

    years = sorted(
        df["Date"]
        .dt.year
        .unique()
    )

    print(
        f"Yıllar: {years}"
    )

    periods = []

    if len(years) >= 3:

        start_index = max(
            2,
            len(years) - 3,
        )

        for i in range(
            start_index,
            len(years),
        ):

            train_years = years[:i]
            test_year = years[i]

            train_mask = (
                df["Date"]
                .dt.year
                .isin(train_years)
            )

            test_mask = (
                df["Date"]
                .dt.year
                == test_year
            )

            train_part = df[
                train_mask
            ]

            test_part = df[
                test_mask
            ]

            if (
                len(train_part) >= 500
                and len(test_part) >= 100
            ):

                periods.append(
                    (
                        train_part,
                        test_part,
                        f"Train<={test_year - 1} "
                        f"Test={test_year}",
                    )
                )

    if not periods:

        split = int(
            len(df) * 0.80
        )

        periods = [
            (
                df.iloc[:split],
                df.iloc[split:],
                "Chronological",
            )
        ]

    metrics = []
    backtests = []

    for (
        train_part,
        test_part,
        period_name,
    ) in periods:

        print()
        print(
            f"[WF] {period_name}"
        )

        predicted, probabilities = (
            model_predict(
                train_part,
                test_part,
            )
        )

        y_test = test_part[
            "target"
        ].astype(int)

        metric = {
            "Period": period_name,

            "Accuracy":
                accuracy_score(
                    y_test,
                    predicted,
                ),

            "Macro_Precision":
                precision_score(
                    y_test,
                    predicted,
                    average="macro",
                    zero_division=0,
                ),

            "Macro_Recall":
                recall_score(
                    y_test,
                    predicted,
                    average="macro",
                    zero_division=0,
                ),

            "Macro_F1":
                f1_score(
                    y_test,
                    predicted,
                    average="macro",
                    zero_division=0,
                ),

            "BUY_F1":
                f1_score(
                    y_test,
                    predicted,
                    labels=[1],
                    average="macro",
                    zero_division=0,
                ),

            "SELL_F1":
                f1_score(
                    y_test,
                    predicted,
                    labels=[-1],
                    average="macro",
                    zero_division=0,
                ),

            "HOLD_F1":
                f1_score(
                    y_test,
                    predicted,
                    labels=[0],
                    average="macro",
                    zero_division=0,
                ),
        }

        forward = calculate_forward_metrics(
            test_part,
            predicted,
            probabilities,
            period_name,
        )

        metric.update(forward)

        metrics.append(metric)

        backtests.append(
            pd.DataFrame({
                "Period": period_name,
                "Date": test_part["Date"].values,
                "Symbol": test_part["Symbol"].values,
                "Predicted": predicted,
                "Actual_Return": test_part[
                    "future_return"
                ].values,
                "Strategy_Return": np.where(
                    predicted == 1,
                    test_part[
                        "future_return"
                    ].values,
                    np.where(
                        predicted == -1,
                        -test_part[
                            "future_return"
                        ].values,
                        0.0,
                    ),
                ),
                "Probability": np.max(
                    probabilities,
                    axis=1,
                ),
            })
        )

        print(
            f"      Accuracy = "
            f"{metric['Accuracy'] * 100:.2f}%"
        )

        print(
            f"      Macro F1 = "
            f"{metric['Macro_F1'] * 100:.2f}%"
        )

        print(
            f"      BUY Hit = "
            f"{metric['BUY_HitRate'] * 100:.2f}% "
            f"| Avg = "
            f"{metric['BUY_AvgReturn'] * 100:.2f}%"
        )

        print(
            f"      SELL Hit = "
            f"{metric['SELL_HitRate'] * 100:.2f}% "
            f"| Avg = "
            f"{metric['SELL_AvgReturn'] * 100:.2f}%"
        )

        print(
            f"      Strategy = "
            f"{metric['Strategy_AvgReturn'] * 100:.2f}%"
        )

    if not metrics:
        return {}, pd.DataFrame()

    numeric_keys = [
        k
        for k in metrics[0].keys()
        if k != "Period"
    ]

    average = {
        key: float(
            np.mean([
                m[key]
                for m in metrics
                if isinstance(
                    m.get(key),
                    (
                        int,
                        float,
                        np.integer,
                        np.floating,
                    ),
                )
            ])
        )
        for key in numeric_keys
    }

    average[
        "Validation_Periods"
    ] = len(metrics)

    backtest_all = pd.concat(
        backtests,
        ignore_index=True,
    )

    print()
    print(
        "=" * 78
    )
    print(" WALK-FORWARD ORTALAMA")
    print("=" * 78)

    print(
        f"Accuracy       : "
        f"{average.get('Accuracy', 0) * 100:.2f}%"
    )

    print(
        f"Macro F1       : "
        f"{average.get('Macro_F1', 0) * 100:.2f}%"
    )

    print(
        f"BUY Hit Rate    : "
        f"{average.get('BUY_HitRate', 0) * 100:.2f}%"
    )

    print(
        f"BUY Avg Return  : "
        f"{average.get('BUY_AvgReturn', 0) * 100:.2f}%"
    )

    print(
        f"SELL Hit Rate   : "
        f"{average.get('SELL_HitRate', 0) * 100:.2f}%"
    )

    print(
        f"SELL Avg Return : "
        f"{average.get('SELL_AvgReturn', 0) * 100:.2f}%"
    )

    print(
        f"Strategy Return : "
        f"{average.get('Strategy_AvgReturn', 0) * 100:.2f}%"
    )

    return average, backtest_all


# ============================================================
# FINAL MODEL
# ============================================================

def train_final_models(train_all):

    print()
    print("=" * 78)
    print(" FINAL AI MODELLER")
    print("=" * 78)

    X = train_all[
        FEATURE_COLUMNS
    ]

    y = train_all[
        "target"
    ].astype(int)

    scaler = StandardScaler()

    X_scaled = scaler.fit_transform(X)

    logistic = build_logistic()

    logistic.fit(
        X_scaled,
        y,
    )

    gradient = build_gradient()

    gradient.fit(
        X,
        y,
    )

    return (
        scaler,
        logistic,
        gradient,
    )


# ============================================================
# EXPECTED RETURN CONTEXT
# ============================================================

def prepare_expected_context(train_all):

    base = train_all.dropna(
        subset=(
            FEATURE_COLUMNS
            + ["future_return"]
        )
    ).copy()

    if len(base) > EXPECTED_RETURN_SAMPLE:

        base = base.sample(
            EXPECTED_RETURN_SAMPLE,
            random_state=RANDOM_SEED,
        )

    X = base[
        FEATURE_COLUMNS
    ].to_numpy(
        dtype=np.float32
    )

    future = base[
        "future_return"
    ].to_numpy(
        dtype=np.float32
    )

    target = base[
        "target"
    ].to_numpy(
        dtype=np.int8
    )

    median = np.nanmedian(
        X,
        axis=0,
    )

    q1 = np.nanpercentile(
        X,
        25,
        axis=0,
    )

    q3 = np.nanpercentile(
        X,
        75,
        axis=0,
    )

    iqr = q3 - q1

    iqr[iqr < 1e-8] = 1.0

    X_scaled = (
        X - median
    ) / iqr

    X_scaled = np.nan_to_num(
        X_scaled,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    ).astype(np.float32)

    models = {}

    for cls in [-1, 1]:

        mask = (
            target == cls
        )

        if mask.sum() < 30:
            continue

        class_X = X_scaled[mask]
        class_return = future[mask]

        k = min(
            NEIGHBORS_PER_QUERY,
            len(class_X),
        )

        knn = NearestNeighbors(
            n_neighbors=k,
            metric="euclidean",
            n_jobs=-1,
        )

        knn.fit(class_X)

        models[cls] = {
            "knn": knn,
            "returns": class_return,
        }

    return {
        "median": median,
        "iqr": iqr,
        "models": models,
    }


# ============================================================
# EXPECTED RETURN
# ============================================================

def calculate_expected_returns(
    candidate_df,
    context,
):

    result = np.zeros(
        len(candidate_df),
        dtype=float,
    )

    if candidate_df.empty:
        return result

    X = candidate_df[
        FEATURE_COLUMNS
    ].to_numpy(
        dtype=np.float32
    )

    X = (
        X
        - context["median"]
    ) / context["iqr"]

    X = np.nan_to_num(
        X,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    ).astype(np.float32)

    predicted = candidate_df[
        "_predicted_class"
    ].to_numpy(
        dtype=int
    )

    for cls in [-1, 1]:

        positions = np.where(
            predicted == cls
        )[0]

        if not len(positions):
            continue

        info = context[
            "models"
        ].get(cls)

        if info is None:
            continue

        distances, indexes = (
            info["knn"].kneighbors(
                X[positions]
            )
        )

        returns = info["returns"]

        for i, position in enumerate(
            positions
        ):

            vals = returns[
                indexes[i]
            ]

            dist = distances[i]

            valid = np.isfinite(vals)

            vals = vals[valid]
            dist = dist[valid]

            if not len(vals):
                continue

            low = np.percentile(
                vals,
                10,
            )

            high = np.percentile(
                vals,
                90,
            )

            mask = (
                (vals >= low)
                & (vals <= high)
            )

            vals = vals[mask]
            dist = dist[mask]

            if not len(vals):
                continue

            weights = (
                1.0
                / (dist + 0.05)
            )

            weights = np.nan_to_num(
                weights,
                nan=1.0,
                posinf=1.0,
                neginf=1.0,
            )

            value = float(
                np.average(
                    vals,
                    weights=weights,
                )
            )

            # Aşırı uçları yumuşat.
            class_median = float(
                np.median(vals)
            )

            value = (
                value * 0.70
                + class_median * 0.30
            )

            result[position] = np.clip(
                value,
                EXPECTED_RETURN_LOW,
                EXPECTED_RETURN_HIGH,
            )

    return result


# ============================================================
# FAST SCORE
# ============================================================

def safe_float(value, default=0.0):

    try:

        value = float(value)

        if not np.isfinite(value):
            return default

        return value

    except Exception:

        return default


def calculate_fast_score(row):

    ret5 = safe_float(
        row.get("ret5", 0),
        0,
    )

    ret20 = safe_float(
        row.get("ret20", 0),
        0,
    )

    rsi = safe_float(
        row.get("rsi14", 0.5),
        0.5,
    )

    p20 = safe_float(
        row.get("price_vs_sma20", 0),
        0,
    )

    p50 = safe_float(
        row.get("price_vs_sma50", 0),
        0,
    )

    volume_ratio = safe_float(
        row.get("volume_ratio", 1),
        1,
    )

    score = 50.0

    score += np.clip(
        ret5 * 180,
        -20,
        20,
    )

    score += np.clip(
        ret20 * 80,
        -15,
        15,
    )

    score += np.clip(
        (rsi - 0.5) * 40,
        -12,
        12,
    )

    score += np.clip(
        p20 * 70,
        -12,
        12,
    )

    score += np.clip(
        p50 * 45,
        -10,
        10,
    )

    score += np.clip(
        (volume_ratio - 1) * 8,
        -8,
        8,
    )

    return float(
        np.clip(
            score,
            0,
            100,
        )
    )


# ============================================================
# RISK
# ============================================================

def calculate_risk_score(row):

    volatility = safe_float(
        row.get(
            "volatility20",
            0,
        )
    )

    atr = safe_float(
        row.get(
            "atr_pct",
            0,
        )
    )

    high_low = safe_float(
        row.get(
            "high_low_pct",
            0,
        )
    )

    risk = (
        volatility * 130
        + atr * 85
        + high_low * 45
    )

    return float(
        np.clip(
            risk,
            0,
            100,
        )
    )


# ============================================================
# QUALITY
# ============================================================

def calculate_quality(
    rows,
    history_years,
):

    score = 50.0

    if rows >= 900:
        score += 20
    elif rows >= 750:
        score += 18
    elif rows >= 600:
        score += 15
    elif rows >= 500:
        score += 12
    elif rows >= 400:
        score += 8

    if history_years >= 4.8:
        score += 30
    elif history_years >= 4.0:
        score += 25
    elif history_years >= 3.0:
        score += 15
    elif history_years >= 2.0:
        score += 5

    return float(
        np.clip(
            score,
            0,
            100,
        )
    )


# ============================================================
# FINAL SCORE
# ============================================================

def calculate_final_score(
    signal,
    probability,
    expected_return,
    fast_score,
    edge,
    risk,
    quality,
):

    probability = safe_float(
        probability,
        0,
    )

    expected_return = safe_float(
        expected_return,
        0,
    )

    fast_score = safe_float(
        fast_score,
        50,
    )

    edge = safe_float(
        edge,
        0,
    )

    risk = safe_float(
        risk,
        50,
    )

    quality = safe_float(
        quality,
        50,
    )

    score = (
        probability * 48
    )

    # --------------------------------------------------------
    # YÖNSEL EXPECTED RETURN
    # --------------------------------------------------------

    if signal == "BUY":

        aligned_return = expected_return

        alignment = (
            fast_score / 100
        )

    elif signal == "SELL":

        aligned_return = -expected_return

        alignment = (
            (100 - fast_score) / 100
        )

    else:

        aligned_return = 0
        alignment = 0.5

    # Beklenen getiri ters yöndeyse ceza.
    if aligned_return > 0:

        return_component = np.clip(
            aligned_return / 0.10,
            0,
            1,
        ) * 18

    else:

        return_component = -np.clip(
            abs(aligned_return) / 0.10,
            0,
            1,
        ) * 20

    # --------------------------------------------------------
    # FAST
    # --------------------------------------------------------

    fast_component = (
        np.clip(
            alignment,
            0,
            1,
        )
        * 14
    )

    # --------------------------------------------------------
    # EDGE
    # --------------------------------------------------------

    edge_component = (
        np.clip(
            max(edge, 0) / 0.10,
            0,
            1,
        )
        * 10
    )

    # --------------------------------------------------------
    # QUALITY
    # --------------------------------------------------------

    quality_component = (
        quality / 100
    ) * 8

    # --------------------------------------------------------
    # RISK
    # --------------------------------------------------------

    risk_penalty = (
        risk / 100
    ) * 14

    # --------------------------------------------------------
    # CONFLICT PENALTY
    # --------------------------------------------------------

    conflict_penalty = 0.0

    if signal == "BUY":

        if expected_return < -0.01:
            conflict_penalty += 8

        if fast_score < 40:
            conflict_penalty += 5

    elif signal == "SELL":

        if expected_return > 0.01:
            conflict_penalty += 8

        if fast_score > 60:
            conflict_penalty += 5

    score = (
        score
        + return_component
        + fast_component
        + edge_component
        + quality_component
        - risk_penalty
        - conflict_penalty
    )

    if signal == "HOLD":
        score *= 0.50

    return float(
        np.clip(
            score,
            0,
            100,
        )
    )


# ============================================================
# STRENGTH
# ============================================================

def get_strength(
    score,
    probability,
    edge,
    expected_return,
    signal,
):

    if signal == "BUY":

        if expected_return <= 0:
            return "D"

    elif signal == "SELL":

        if expected_return >= 0:
            return "D"

    if (
        score >= 82
        and probability >= 0.82
        and edge >= 0.10
    ):
        return "A+"

    if (
        score >= 72
        and probability >= 0.72
        and edge >= 0.06
    ):
        return "A"

    if (
        score >= 62
        and probability >= 0.62
        and edge >= 0.04
    ):
        return "B"

    if (
        score >= 52
        and probability >= 0.52
    ):
        return "C"

    return "D"


# ============================================================
# FINAL PREDICTION
# ============================================================

def run_predictions(
    train_all,
    latest_df,
    data,
    validation,
):

    print()
    print("=" * 78)
    print(" LEVEL 1000 FINAL AI TAHMİN")
    print("=" * 78)

    scaler, logistic, gradient = (
        train_final_models(
            train_all
        )
    )

    X = latest_df[
        FEATURE_COLUMNS
    ]

    X_scaled = scaler.transform(X)

    p_log = logistic.predict_proba(
        X_scaled
    )

    p_grad = gradient.predict_proba(
        X
    )

    probabilities = combine_probabilities(
        p_log,
        logistic.classes_,
        p_grad,
        gradient.classes_,
    )

    classes = np.array(
        [-1, 0, 1]
    )

    predicted = classes[
        np.argmax(
            probabilities,
            axis=1,
        )
    ]

    rows = []

    for i in range(
        len(latest_df)
    ):

        r = latest_df.iloc[i]

        cls = int(
            predicted[i]
        )

        signal = (
            "BUY"
            if cls == 1
            else
            "SELL"
            if cls == -1
            else
            "HOLD"
        )

        sell_p = float(
            probabilities[i][0]
        )

        hold_p = float(
            probabilities[i][1]
        )

        buy_p = float(
            probabilities[i][2]
        )

        if signal == "BUY":

            probability = buy_p

            second = max(
                sell_p,
                hold_p,
            )

            edge = (
                buy_p - second
            )

        elif signal == "SELL":

            probability = sell_p

            second = max(
                buy_p,
                hold_p,
            )

            edge = (
                sell_p - second
            )

        else:

            probability = hold_p

            second = max(
                sell_p,
                buy_p,
            )

            edge = (
                hold_p - second
            )

        row = {
            "Symbol":
                r["Symbol"],

            "Date":
                r["Date"],

            "Close":
                r["Close"],

            "Signal":
                signal,

            "BUY_Probability":
                buy_p * 100,

            "SELL_Probability":
                sell_p * 100,

            "HOLD_Probability":
                hold_p * 100,

            "AI_Probability":
                probability * 100,

            "AI_Edge":
                edge * 100,

            "_predicted_class":
                cls,

            "_probability":
                probability,
        }

        for column in FEATURE_COLUMNS:

            row[column] = safe_float(
                r[column],
                0,
            )

        row["Fast_Score"] = (
            calculate_fast_score(row)
        )

        rows_count = len(
            data.get(
                r["Symbol"],
                [],
            )
        )

        row["Rows"] = rows_count

        history_start = pd.Timestamp(
            r.get(
                "History_Start",
                r["Date"],
            )
        )

        history_end = pd.Timestamp(
            r.get(
                "History_End",
                r["Date"],
            )
        )

        history_years = (
            history_end
            - history_start
        ).days / 365.25

        row["History_Years"] = (
            history_years
        )

        row["Risk_Score"] = (
            calculate_risk_score(
                row
            )
        )

        row["Data_Quality"] = (
            calculate_quality(
                rows_count,
                history_years,
            )
        )

        row["AI_Score"] = (
            calculate_final_score(
                signal,
                probability,
                0,
                row["Fast_Score"],
                edge,
                row["Risk_Score"],
                row["Data_Quality"],
            )
        )

        rows.append(row)

    result = pd.DataFrame(rows)

    # --------------------------------------------------------
    # EXPECTED RETURN ADAYLARI
    # --------------------------------------------------------

    candidates = (
        result[
            result["Signal"] != "HOLD"
        ]
        .copy()
    )

    candidates = candidates[
        candidates["_probability"]
        >= MIN_PROBABILITY
    ]

    candidates = candidates[
        candidates["AI_Edge"]
        >= MIN_EDGE * 100
    ]

    candidates = (
        candidates
        .sort_values(
            [
                "AI_Score",
                "AI_Probability",
            ],
            ascending=False,
        )
        .head(
            EXPECTED_RETURN_CANDIDATES
        )
        .copy()
    )

    print()
    print(
        f"[EXPECTED RETURN] "
        f"{len(candidates):,} aday"
    )

    context = (
        prepare_expected_context(
            train_all
        )
    )

    expected = (
        calculate_expected_returns(
            candidates,
            context,
        )
    )

    result[
        "AI_Predicted_Return"
    ] = 0.0

    result.loc[
        candidates.index,
        "AI_Predicted_Return",
    ] = (
        expected * 100
    )

    # --------------------------------------------------------
    # FINAL SCORE
    # --------------------------------------------------------

    result["AI_Score"] = result.apply(
        lambda x:
        calculate_final_score(
            x["Signal"],
            x["_probability"],
            x["AI_Predicted_Return"] / 100,
            x["Fast_Score"],
            x["AI_Edge"] / 100,
            x["Risk_Score"],
            x["Data_Quality"],
        ),
        axis=1,
    )

    # --------------------------------------------------------
    # RETURN ALIGNMENT
    # --------------------------------------------------------

    result["Return_Alignment"] = np.where(
        result["Signal"] == "BUY",
        result["AI_Predicted_Return"],

        np.where(
            result["Signal"] == "SELL",
            -result["AI_Predicted_Return"],
            0,
        ),
    )

    # --------------------------------------------------------
    # FINAL RANKING
    #
    # V12 HATASI:
    # abs(Return_Alignment)
    #
    # Artık yanlış yöndeki ER ödüllendirilmiyor.
    # --------------------------------------------------------

    aligned = result[
        "Return_Alignment"
    ].clip(
        -20,
        20,
    )

    result["Ranking_Score"] = (
        result["AI_Score"]
        + aligned * 0.90
    )

    # Risk çok yüksekse ekstra ceza.
    result["Ranking_Score"] -= np.where(
        result["Risk_Score"] >= 85,
        8,
        0,
    )

    # Fast yönü ters ise ceza.
    result["Ranking_Score"] -= np.where(
        (
            (result["Signal"] == "BUY")
            & (result["Fast_Score"] < 35)
        )
        |
        (
            (result["Signal"] == "SELL")
            & (result["Fast_Score"] > 65)
        ),
        7,
        0,
    )

    result.loc[
        result["Signal"] == "HOLD",
        "Ranking_Score",
    ] -= 25

    # --------------------------------------------------------
    # GÜÇ
    # --------------------------------------------------------

    result["Strength"] = result.apply(
        lambda x:
        get_strength(
            x["AI_Score"],
            x["AI_Probability"] / 100,
            x["AI_Edge"] / 100,
            x["AI_Predicted_Return"] / 100,
            x["Signal"],
        ),
        axis=1,
    )

    return result


# ============================================================
# OUTPUT
# ============================================================

def save_outputs(
    result,
    validation,
    backtest,
):

    output = result.copy()

    output = (
        output
        .sort_values(
            [
                "Ranking_Score",
                "AI_Score",
                "AI_Probability",
            ],
            ascending=False,
            na_position="last",
        )
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # TOP 300
    # --------------------------------------------------------

    # Önce gerçek güçlü adaylar.
    strong = output[
        (
            output["Signal"].isin(
                ["BUY", "SELL"]
            )
        )
        &
        (
            output["Ranking_Score"] >= 50
        )
    ].copy()

    # BUY ve SELL ayrı ayrı sıralanır.
    buy = strong[
        strong["Signal"] == "BUY"
    ].sort_values(
        "Ranking_Score",
        ascending=False,
    )

    sell = strong[
        strong["Signal"] == "SELL"
    ].sort_values(
        "Ranking_Score",
        ascending=False,
    )

    # Doğal kaliteyi korurken tek yönün TOP'u
    # tamamen doldurmasını engelle.
    buy_limit = int(
        TOP_N * 0.65
    )

    sell_limit = int(
        TOP_N * 0.65
    )

    selected = pd.concat(
        [
            buy.head(buy_limit),
            sell.head(sell_limit),
        ],
        ignore_index=True,
    )

    selected = (
        selected
        .sort_values(
            "Ranking_Score",
            ascending=False,
        )
        .head(TOP_N)
    )

    # Yeterli aday yoksa genel sıralamadan doldur.
    if len(selected) < TOP_N:

        remaining = output[
            ~output.index.isin(
                selected.index
            )
        ]

        selected = pd.concat(
            [
                selected,
                remaining.head(
                    TOP_N - len(selected)
                ),
            ],
            ignore_index=False,
        )

        selected = (
            selected
            .sort_values(
                "Ranking_Score",
                ascending=False,
            )
            .head(TOP_N)
        )

    top = selected.copy()

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    internal = [
        "_predicted_class",
        "_probability",
        "Ranking_Score",
    ]

    output_csv = output.drop(
        columns=[
            c
            for c in internal
            if c in output.columns
        ]
    )

    top_csv = top.drop(
        columns=[
            c
            for c in internal
            if c in top.columns
        ]
    )

    latest_columns = [
        "Symbol",
        "Date",
        "Close",
        "Signal",
        "Strength",
        "AI_Score",
        "AI_Probability",
        "BUY_Probability",
        "SELL_Probability",
        "HOLD_Probability",
        "AI_Edge",
        "AI_Predicted_Return",
        "Return_Alignment",
        "Fast_Score",
        "Risk_Score",
        "Data_Quality",
        "History_Years",
        "Rows",
    ]

    latest = output_csv[
        [
            c
            for c in latest_columns
            if c in output_csv.columns
        ]
    ].copy()

    output_csv.to_csv(
        SCAN_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    top_csv.to_csv(
        TOP_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    latest.to_csv(
        LATEST_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # MODEL METRICS
    # --------------------------------------------------------

    model_row = {
        "Metric":
            "WalkForward",

        "Accuracy":
            validation.get(
                "Accuracy",
                0,
            ),

        "Macro_F1":
            validation.get(
                "Macro_F1",
                0,
            ),

        "BUY_F1":
            validation.get(
                "BUY_F1",
                0,
            ),

        "SELL_F1":
            validation.get(
                "SELL_F1",
                0,
            ),

        "HOLD_F1":
            validation.get(
                "HOLD_F1",
                0,
            ),

        "BUY_HitRate":
            validation.get(
                "BUY_HitRate",
                0,
            ),

        "BUY_AvgReturn":
            validation.get(
                "BUY_AvgReturn",
                0,
            ),

        "SELL_HitRate":
            validation.get(
                "SELL_HitRate",
                0,
            ),

        "SELL_AvgReturn":
            validation.get(
                "SELL_AvgReturn",
                0,
            ),

        "Strategy_AvgReturn":
            validation.get(
                "Strategy_AvgReturn",
                0,
            ),

        "Periods":
            validation.get(
                "Validation_Periods",
                0,
            ),
    }

    pd.DataFrame(
        [model_row]
    ).to_csv(
        MODEL_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    if backtest is not None and not backtest.empty:

        backtest.to_csv(
            BACKTEST_FILE,
            index=False,
            encoding="utf-8-sig",
        )

    return output_csv, top_csv


# ============================================================
# TOP 30
# ============================================================

def print_top(top):

    print()
    print("=" * 78)
    print(" LEVEL 1000 FINAL TOP 30")
    print("=" * 78)

    for i, (_, row) in enumerate(
        top.head(30).iterrows(),
        1,
    ):

        print(
            f"{i:2d}. "
            f"{str(row['Symbol']):<12} "
            f"{str(row['Signal']):<5} "
            f"{str(row['Strength']):<3} "
            f"AI={row['AI_Score']:6.2f} "
            f"P={row['AI_Probability']:6.2f}% "
            f"ER={row['AI_Predicted_Return']:7.2f}% "
            f"Fast={row['Fast_Score']:6.2f} "
            f"Risk={row['Risk_Score']:6.2f}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    total_start = time.time()

    print("=" * 78)
    print(" LEVEL 1000 FINAL")
    print(" GLOBAL AI STOCK SCANNER")
    print("=" * 78)

    print(
        "Gerçek para       : HAYIR"
    )

    print(
        "Otomatik emir     : HAYIR"
    )

    print(
        "Model             : "
        "Logistic + HistGradientBoosting"
    )

    print(
        "Validation        : "
        "Walk-Forward + Forward Return"
    )

    print(
        f"History           : "
        f"{YEARS} yıl"
    )

    print(
        f"Target            : "
        f"{TARGET_THRESHOLD * 100:.2f}% / "
        f"{FORWARD_DAYS} gün"
    )

    print(
        f"Download Worker   : "
        f"{DOWNLOAD_WORKERS}"
    )

    print(
        f"Expected Return   : "
        f"TOP {EXPECTED_RETURN_CANDIDATES}"
    )

    print(
        "Cache              : "
        "5 YIL KONTROLLÜ"
    )

    print()

    symbols = load_symbols()

    print(
        f"[SEMBOL] "
        f"{len(symbols):,}"
    )

    data = collect_data(symbols)

    if len(data) < 10:

        raise RuntimeError(
            "Yeterli veri bulunamadı."
        )

    train_all, latest_df = (
        prepare_ai_data(data)
    )

    validation, backtest = (
        walk_forward_validation(
            train_all
        )
    )

    result = run_predictions(
        train_all,
        latest_df,
        data,
        validation,
    )

    output, top = save_outputs(
        result,
        validation,
        backtest,
    )

    print_top(top)

    # --------------------------------------------------------
    # SAYIM
    # --------------------------------------------------------

    buy_count = int(
        (
            output["Signal"]
            == "BUY"
        ).sum()
    )

    sell_count = int(
        (
            output["Signal"]
            == "SELL"
        ).sum()
    )

    hold_count = int(
        (
            output["Signal"]
            == "HOLD"
        ).sum()
    )

    er = pd.to_numeric(
        output[
            "AI_Predicted_Return"
        ],
        errors="coerce",
    )

    er_valid = er[
        er != 0
    ].dropna()

    elapsed = (
        time.time()
        - total_start
    )

    # --------------------------------------------------------
    # SONUÇ
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print(" LEVEL 1000 FINAL SONUÇ")
    print("=" * 78)

    print(
        f"Taranan sembol       : "
        f"{len(symbols):,}"
    )

    print(
        f"5 yıllık veri        : "
        f"{len(data):,}"
    )

    print(
        f"AI analiz edilen     : "
        f"{len(output):,}"
    )

    print(
        f"BUY                  : "
        f"{buy_count:,}"
    )

    print(
        f"SELL                 : "
        f"{sell_count:,}"
    )

    print(
        f"HOLD                 : "
        f"{hold_count:,}"
    )

    print(
        f"TOP                  : "
        f"{min(TOP_N, len(top)):,}"
    )

    if not er_valid.empty:

        print(
            f"ER minimum          : "
            f"{er_valid.min():.2f}%"
        )

        print(
            f"ER maksimum         : "
            f"{er_valid.max():.2f}%"
        )

        print(
            f"ER ortalama         : "
            f"{er_valid.mean():.2f}%"
        )

    print(
        f"Toplam süre          : "
        f"{elapsed / 60:.1f} dakika"
    )

    # --------------------------------------------------------
    # MODEL
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print(" FINAL MODEL TESTİ")
    print("=" * 78)

    print(
        f"Accuracy             : "
        f"{validation.get('Accuracy', 0) * 100:.2f}%"
    )

    print(
        f"Macro F1             : "
        f"{validation.get('Macro_F1', 0) * 100:.2f}%"
    )

    print(
        f"BUY F1               : "
        f"{validation.get('BUY_F1', 0) * 100:.2f}%"
    )

    print(
        f"SELL F1              : "
        f"{validation.get('SELL_F1', 0) * 100:.2f}%"
    )

    print(
        f"HOLD F1              : "
        f"{validation.get('HOLD_F1', 0) * 100:.2f}%"
    )

    print(
        f"Validation Periods   : "
        f"{validation.get('Validation_Periods', 0)}"
    )

    # --------------------------------------------------------
    # FORWARD
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print(" GERÇEK FORWARD TEST")
    print("=" * 78)

    print(
        f"BUY Hit Rate         : "
        f"{validation.get('BUY_HitRate', 0) * 100:.2f}%"
    )

    print(
        f"BUY Ortalama Getiri : "
        f"{validation.get('BUY_AvgReturn', 0) * 100:.2f}%"
    )

    print(
        f"SELL Hit Rate        : "
        f"{validation.get('SELL_HitRate', 0) * 100:.2f}%"
    )

    print(
        f"SELL Ortalama Getiri: "
        f"{validation.get('SELL_AvgReturn', 0) * 100:.2f}%"
    )

    print(
        f"Strategy Avg Return  : "
        f"{validation.get('Strategy_AvgReturn', 0) * 100:.2f}%"
    )

    print(
        f"Strategy Win Rate    : "
        f"{validation.get('Strategy_WinRate', 0) * 100:.2f}%"
    )

    # --------------------------------------------------------
    # DOSYALAR
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print(" DOSYALAR")
    print("=" * 78)

    print(
        f"SCAN      : "
        f"{SCAN_FILE}"
    )

    print(
        f"TOP       : "
        f"{TOP_FILE}"
    )

    print(
        f"LATEST    : "
        f"{LATEST_FILE}"
    )

    print(
        f"MODEL     : "
        f"{MODEL_FILE}"
    )

    print(
        f"BACKTEST  : "
        f"{BACKTEST_FILE}"
    )

    print(
        f"CACHE     : "
        f"{CACHE_DIR}"
    )

    # --------------------------------------------------------
    # FINAL DURUM
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print(" LEVEL 1000 FINAL TAMAMLANDI")
    print("=" * 78)

    if (
        validation.get(
            "Strategy_AvgReturn",
            0,
        ) > 0
        and
        validation.get(
            "Strategy_WinRate",
            0,
        ) >= 0.50
    ):

        print(
            "MODEL DURUMU : POZİTİF BACKTEST"
        )

    else:

        print(
            "MODEL DURUMU : DAHA TEST EDİLMELİ"
        )

    print()
    print(
        "Gerçek para kullanılmadı."
    )

    print(
        "Otomatik emir gönderilmedi."
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print(
            "[DURDURULDU]"
        )

    except Exception as exc:

        print()
        print("=" * 78)
        print(" FINAL HATA")
        print("=" * 78)

        print(
            type(exc).__name__,
            ":",
            exc,
        )

        raise