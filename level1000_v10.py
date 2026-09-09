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
# LEVEL 1000 V10
# GLOBAL AI STOCK SCANNER
#
# GERÇEK PARA   : HAYIR
# OTOMATİK EMİR : HAYIR
# ============================================================


# ============================================================
# KLASÖRLER
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "level1000_data"
CACHE_DIR = DATA_DIR / "cache"
SYMBOLS_FILE = BASE_DIR / "symbols.txt"

PROGRESS_FILE = DATA_DIR / "v10_progress.json"
FAILED_FILE = DATA_DIR / "v10_failed_symbols.txt"

SCAN_FILE = DATA_DIR / "level1000_v10_scan.csv"
TOP_FILE = DATA_DIR / "level1000_v10_top.csv"
LATEST_FILE = DATA_DIR / "level1000_v10_latest.csv"
MODEL_FILE = DATA_DIR / "level1000_v10_model_metrics.csv"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# HIZ
# ============================================================

YEARS = 2

DOWNLOAD_WORKERS = 12
BATCH_SIZE = 150

RETRY_COUNT = 1
RETRY_SLEEP = 0.8

MIN_ROWS = 220

# Target
FORWARD_DAYS = 5

# Daha anlamlı hedef
TARGET_THRESHOLD = 0.003

# Eğitim
MAX_TRAIN_ROWS = 250000

# Sonuç
TOP_N = 300

# Expected Return
EXPECTED_RETURN_SAMPLE = 15000
NEIGHBORS_PER_QUERY = 35

# Sadece ilk bu kadar adayda Expected Return
EXPECTED_RETURN_CANDIDATES = 500

# ±10%
EXPECTED_RETURN_LOW = -0.10
EXPECTED_RETURN_HIGH = 0.10

RANDOM_SEED = 42

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
# YAHOO FRAME TEMİZLE
# ============================================================

def normalize_download_frame(
    df,
    symbol,
):

    if df is None or df.empty:
        return None

    try:

        if isinstance(
            df.columns,
            pd.MultiIndex,
        ):

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

            if any(
                x in wanted
                for x in level0
            ):

                out = df.copy()

                out.columns = (
                    df.columns
                    .get_level_values(0)
                )

            else:

                matches = []

                for i, value in enumerate(level1):

                    if value.upper() == symbol.upper():
                        matches.append(i)

                if matches:

                    out = df.iloc[
                        :,
                        matches,
                    ].copy()

                    out.columns = (
                        df.columns
                        .get_level_values(0)[
                            matches
                        ]
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

        out = out.rename(
            columns=rename
        )

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        if not all(
            c in out.columns
            for c in required
        ):

            return None

        out = out[
            required
        ].copy()

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

        out = out[
            ~out.index.isna()
        ]

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
# TEK SEMBOL İNDİR
# ============================================================

def download_symbol(symbol):

    path = cache_path(symbol)

    for attempt in range(
        RETRY_COUNT + 1
    ):

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
                start=start.strftime(
                    "%Y-%m-%d"
                ),
                end=(
                    end
                    + pd.Timedelta(
                        days=1
                    )
                ).strftime(
                    "%Y-%m-%d"
                ),
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

                clean.to_csv(
                    path
                )

                return (
                    symbol,
                    clean,
                    True,
                )

        except Exception:
            pass

        if attempt < RETRY_COUNT:

            time.sleep(
                RETRY_SLEEP
            )

    return (
        symbol,
        None,
        False,
    )


# ============================================================
# PROGRESS
# ============================================================

def save_progress(
    completed,
    failed,
):

    payload = {
        "completed_symbols":
            sorted(
                set(completed)
            ),

        "failed_symbols":
            sorted(
                set(failed)
            ),

        "updated":
            time.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
    }

    tmp = PROGRESS_FILE.with_suffix(
        ".tmp"
    )

    try:

        tmp.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        tmp.replace(
            PROGRESS_FILE
        )

    except Exception:
        pass


def save_failed(
    failed
):

    try:

        FAILED_FILE.write_text(
            "\n".join(
                sorted(
                    set(failed)
                )
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
    print(" LEVEL 1000 V10 VERİ MOTORU")
    print("=" * 78)

    print(
        f"Toplam sembol       : {len(symbols):,}"
    )

    print(
        "[CACHE] Eski V8/V9/V9.1 cache kullanılacak."
    )

    start = time.time()

    data = {}

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    print()
    print(
        "[CACHE] Cache dosyaları kontrol ediliyor..."
    )

    for symbol in symbols:

        df = load_cache(
            symbol
        )

        if (
            df is not None
            and len(df) >= MIN_ROWS
        ):

            data[symbol] = df

    cache_time = (
        time.time()
        - start
    )

    missing = [
        s
        for s in symbols
        if s not in data
    ]

    print(
        f"[CACHE] Hazır veri   : {len(data):,}"
    )

    print(
        f"[CACHE] Süre         : {cache_time:.1f} sn"
    )

    print(
        f"[DOWNLOAD] Eksik     : {len(missing):,}"
    )

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    if missing:

        download_start = time.time()

        total_batches = (
            len(missing)
            + BATCH_SIZE
            - 1
        ) // BATCH_SIZE

        completed = set(
            data.keys()
        )

        failed = set()

        # Tek executor
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
                    batch_start
                    + BATCH_SIZE
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

                    symbol = futures[
                        future
                    ]

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

                    if (
                        ok
                        and df is not None
                    ):

                        data[sym] = df

                        completed.add(
                            sym
                        )

                    else:

                        failed.add(
                            sym
                        )

                save_progress(
                    completed,
                    failed,
                )

                save_failed(
                    failed
                )

                print(
                    f"           "
                    f"Hazır={len(data):,} "
                    f"| Başarısız={len(failed):,}"
                )

        print(
            f"[DOWNLOAD] Süre: "
            f"{(time.time() - download_start) / 60:.1f} dakika"
        )

    # --------------------------------------------------------
    # FINAL PROGRESS
    # --------------------------------------------------------

    completed = set(
        data.keys()
    )

    failed = (
        set(symbols)
        - completed
    )

    save_progress(
        completed,
        failed,
    )

    save_failed(
        failed
    )

    print()
    print("=" * 78)
    print(" VERİ TOPLAMA TAMAMLANDI")
    print("=" * 78)

    print(
        f"Toplam sembol       : {len(symbols):,}"
    )

    print(
        f"Kullanılabilir veri : {len(data):,}"
    )

    print(
        f"Eksik/başarısız     : {len(failed):,}"
    )

    return data


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
        .replace(
            0,
            np.nan,
        )
    )

    x["ret1"] = (
        close.pct_change(1)
    )

    x["ret3"] = (
        close.pct_change(3)
    )

    x["ret5"] = (
        close.pct_change(5)
    )

    x["ret10"] = (
        close.pct_change(10)
    )

    x["ret20"] = (
        close.pct_change(20)
    )

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

    x["rsi14"] = calculate_rsi(
        close
    )

    tr1 = (
        high - low
    )

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

    atr = (
        tr
        .rolling(14)
        .mean()
    )

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

def make_training_rows(
    symbol,
    df,
):

    feat = build_features(
        df
    )

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
            + [
                "future_return"
            ]
        )
    ).copy()

    if len(train) < 100:

        return (
            None,
            None,
        )

    future = train[
        "future_return"
    ]

    train["target"] = np.select(
        [
            future
            > TARGET_THRESHOLD,

            future
            < -TARGET_THRESHOLD,
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

    # --------------------------------------------------------
    # SON GEÇERLİ BAR
    # --------------------------------------------------------

    valid_latest = feat.dropna(
        subset=FEATURE_COLUMNS
    )

    if valid_latest.empty:

        return (
            train,
            None,
        )

    last = valid_latest.iloc[-1]

    latest = {
        "Symbol": symbol,

        "Date":
            pd.to_datetime(
                valid_latest.index[-1]
            ),

        "Close":
            float(
                last["Close"]
            ),
    }

    for column in FEATURE_COLUMNS:

        latest[column] = float(
            last[column]
        )

    return (
        train,
        latest,
    )


# ============================================================
# AI DATA
# ============================================================

def prepare_ai_data(
    data
):

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

                train_parts.append(
                    train
                )

            if latest is not None:

                latest_rows.append(
                    latest
                )

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

    # --------------------------------------------------------
    # KRONOLOJİK
    # --------------------------------------------------------

    train_all = (
        train_all
        .sort_values(
            "Date"
        )
        .reset_index(
            drop=True
        )
    )

    # --------------------------------------------------------
    # MAX TRAIN
    # --------------------------------------------------------

    if len(train_all) > MAX_TRAIN_ROWS:

        train_all = (
            train_all
            .tail(
                MAX_TRAIN_ROWS
            )
            .reset_index(
                drop=True
            )
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

    counts = (
        train_all["target"]
        .value_counts()
    )

    print()
    print(
        "[AI] Sınıf dağılımı:"
    )

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

    return (
        train_all,
        latest_df,
    )


# ============================================================
# LOGISTIC MODEL
# ============================================================

def build_logistic():

    return LogisticRegression(
        max_iter=500,
        C=0.35,
        class_weight="balanced",
        random_state=RANDOM_SEED,
    )


# ============================================================
# GRADIENT MODEL
# ============================================================

def build_gradient():

    return HistGradientBoostingClassifier(
        learning_rate=0.08,
        max_iter=160,
        max_leaf_nodes=31,
        min_samples_leaf=80,
        l2_regularization=1.0,
        random_state=RANDOM_SEED,
    )


# ============================================================
# WALK FORWARD
# ============================================================

def walk_forward_validation(
    train_all
):

    print()
    print("=" * 78)
    print(" V10 WALK-FORWARD VALIDATION")
    print("=" * 78)

    df = train_all.copy()

    df["Date"] = pd.to_datetime(
        df["Date"]
    )

    df = (
        df
        .sort_values("Date")
        .reset_index(
            drop=True
        )
    )

    unique_dates = (
        df["Date"]
        .dt.year
        .unique()
    )

    unique_dates = sorted(
        unique_dates
    )

    print(
        f"Yıllar: {unique_dates}"
    )

    # --------------------------------------------------------
    # Veri çok kısa ise klasik kronolojik split
    # --------------------------------------------------------

    if len(unique_dates) < 3:

        split = int(
            len(df) * 0.80
        )

        train_part = df.iloc[
            :split
        ]

        test_part = df.iloc[
            split:
        ]

        return evaluate_period(
            train_part,
            test_part,
            "Chronological",
        )

    periods = []

    # Son 2 yılı test olarak kullan,
    # geçmiş tüm dönem eğitimde.
    for i in range(
        2,
        len(unique_dates),
    ):

        train_years = unique_dates[
            :i
        ]

        test_year = unique_dates[
            i
        ]

        # Son 2 dönemi özellikle test
        if (
            i
            >= len(unique_dates) - 2
        ):

            train_mask = (
                df["Date"]
                .dt.year
                .isin(
                    train_years
                )
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
                len(train_part)
                >= 500
                and len(test_part)
                >= 100
            ):

                name = (
                    f"Train<= {train_years[-1]} "
                    f"Test={test_year}"
                )

                periods.append(
                    (
                        train_part,
                        test_part,
                        name,
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

    for (
        train_part,
        test_part,
        name,
    ) in periods:

        result = evaluate_period(
            train_part,
            test_part,
            name,
        )

        metrics.append(
            result
        )

    if not metrics:

        return {}

    avg = {}

    for key in metrics[0].keys():

        if key == "Period":
            continue

        values = [
            m[key]
            for m in metrics
            if isinstance(
                m[key],
                (int, float),
            )
        ]

        if values:

            avg[
                key
            ] = float(
                np.mean(
                    values
                )
            )

    avg[
        "Validation_Periods"
    ] = len(metrics)

    print()
    print(
        "[WALK-FORWARD] Ortalama"
    )

    print(
        f"Accuracy : "
        f"{avg.get('Accuracy', 0) * 100:.2f}%"
    )

    print(
        f"Macro F1 : "
        f"{avg.get('Macro_F1', 0) * 100:.2f}%"
    )

    print(
        f"BUY F1   : "
        f"{avg.get('BUY_F1', 0) * 100:.2f}%"
    )

    print(
        f"SELL F1  : "
        f"{avg.get('SELL_F1', 0) * 100:.2f}%"
    )

    return avg


# ============================================================
# TEK VALIDATION
# ============================================================

def evaluate_period(
    train_part,
    test_part,
    period_name,
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

    y_test = test_part[
        "target"
    ].astype(int)

    # --------------------------------------------------------
    # Logistic
    # --------------------------------------------------------

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

    log_classes = (
        logistic.classes_
    )

    # --------------------------------------------------------
    # Gradient
    # --------------------------------------------------------

    gradient = build_gradient()

    gradient.fit(
        X_train,
        y_train,
    )

    p_grad = gradient.predict_proba(
        X_test
    )

    grad_classes = (
        gradient.classes_
    )

    # --------------------------------------------------------
    # Ensemble
    # --------------------------------------------------------

    probabilities = combine_probabilities(
        p_log,
        log_classes,
        p_grad,
        grad_classes,
    )

    classes = np.array(
        [-1, 0, 1]
    )

    pred = classes[
        np.argmax(
            probabilities,
            axis=1,
        )
    ]

    metrics = {
        "Period":
            period_name,

        "Accuracy":
            accuracy_score(
                y_test,
                pred,
            ),

        "Macro_Precision":
            precision_score(
                y_test,
                pred,
                average="macro",
                zero_division=0,
            ),

        "Macro_Recall":
            recall_score(
                y_test,
                pred,
                average="macro",
                zero_division=0,
            ),

        "Macro_F1":
            f1_score(
                y_test,
                pred,
                average="macro",
                zero_division=0,
            ),

        "BUY_F1":
            f1_score(
                y_test,
                pred,
                labels=[1],
                average="macro",
                zero_division=0,
            ),

        "SELL_F1":
            f1_score(
                y_test,
                pred,
                labels=[-1],
                average="macro",
                zero_division=0,
            ),

        "HOLD_F1":
            f1_score(
                y_test,
                pred,
                labels=[0],
                average="macro",
                zero_division=0,
            ),
    }

    print()
    print(
        f"[WF] {period_name}"
    )

    print(
        f"      Accuracy={metrics['Accuracy'] * 100:.2f}% "
        f"F1={metrics['Macro_F1'] * 100:.2f}%"
    )

    return metrics


# ============================================================
# PROBABILITY COMBINE
# ============================================================

def combine_probabilities(
    p1,
    classes1,
    p2,
    classes2,
):

    output = np.zeros(
        (
            len(p1),
            3,
        ),
        dtype=np.float64,
    )

    class_to_index = {
        -1: 0,
        0: 1,
        1: 2,
    }

    for j, cls in enumerate(
        classes1
    ):

        cls = int(cls)

        if cls in class_to_index:

            output[
                :,
                class_to_index[cls],
            ] += (
                p1[:, j]
                * 0.45
            )

    for j, cls in enumerate(
        classes2
    ):

        cls = int(cls)

        if cls in class_to_index:

            output[
                :,
                class_to_index[cls],
            ] += (
                p2[:, j]
                * 0.55
            )

    sums = output.sum(
        axis=1,
        keepdims=True,
    )

    sums[
        sums == 0
    ] = 1

    return (
        output / sums
    )


# ============================================================
# FINAL MODEL
# ============================================================

def train_final_models(
    train_all
):

    print()
    print("=" * 78)
    print(" V10 FINAL AI MODELLER")
    print("=" * 78)

    X = train_all[
        FEATURE_COLUMNS
    ]

    y = train_all[
        "target"
    ].astype(int)

    # Logistic
    scaler = StandardScaler()

    X_scaled = scaler.fit_transform(
        X
    )

    logistic = build_logistic()

    logistic.fit(
        X_scaled,
        y,
    )

    # Gradient
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

def prepare_expected_context(
    train_all
):

    base = train_all.dropna(
        subset=(
            FEATURE_COLUMNS
            + [
                "future_return",
            ]
        )
    )

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

    iqr[
        iqr < 1e-8
    ] = 1.0

    X_scaled = (
        X - median
    ) / iqr

    X_scaled = np.nan_to_num(
        X_scaled,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    ).astype(
        np.float32
    )

    models = {}

    for target_class in [
        -1,
        1,
    ]:

        mask = (
            target
            == target_class
        )

        if mask.sum() < 30:
            continue

        class_X = X_scaled[
            mask
        ]

        class_return = future[
            mask
        ]

        k = min(
            NEIGHBORS_PER_QUERY,
            len(class_X),
        )

        knn = NearestNeighbors(
            n_neighbors=k,
            metric="euclidean",
            n_jobs=-1,
        )

        knn.fit(
            class_X
        )

        models[
            target_class
        ] = {
            "knn": knn,
            "returns":
                class_return,
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
    ).astype(
        np.float32
    )

    predicted = candidate_df[
        "_predicted_class"
    ].to_numpy(
        dtype=int
    )

    for cls in [
        -1,
        1,
    ]:

        positions = np.where(
            predicted == cls
        )[0]

        if len(positions) == 0:
            continue

        info = context[
            "models"
        ].get(
            cls
        )

        if info is None:
            continue

        query = X[
            positions
        ]

        distances, indexes = (
            info["knn"].kneighbors(
                query
            )
        )

        returns = info[
            "returns"
        ]

        for i, position in enumerate(
            positions
        ):

            vals = returns[
                indexes[i]
            ]

            vals = vals[
                np.isfinite(
                    vals
                )
            ]

            if len(vals) == 0:
                continue

            # Aşırı uçları azalt
            low = np.percentile(
                vals,
                10,
            )

            high = np.percentile(
                vals,
                90,
            )

            trimmed = vals[
                (vals >= low)
                & (vals <= high)
            ]

            if len(trimmed) == 0:
                trimmed = vals

            value = float(
                np.median(
                    trimmed
                )
            )

            result[
                position
            ] = np.clip(
                value,
                EXPECTED_RETURN_LOW,
                EXPECTED_RETURN_HIGH,
            )

    return result


# ============================================================
# FAST SCORE
# ============================================================

def calculate_fast_score(
    row
):

    ret5 = float(
        row.get(
            "ret5",
            0,
        )
    )

    ret20 = float(
        row.get(
            "ret20",
            0,
        )
    )

    rsi = float(
        row.get(
            "rsi14",
            0.5,
        )
    )

    p20 = float(
        row.get(
            "price_vs_sma20",
            0,
        )
    )

    p50 = float(
        row.get(
            "price_vs_sma50",
            0,
        )
    )

    volume_ratio = float(
        row.get(
            "volume_ratio",
            1,
        )
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
        (volume_ratio - 1)
        * 8,
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

def calculate_risk_score(
    row
):

    volatility = float(
        row.get(
            "volatility20",
            0,
        )
    )

    atr = float(
        row.get(
            "atr_pct",
            0,
        )
    )

    high_low = float(
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
    rows
):

    if rows >= 500:
        return 100.0

    if rows >= 400:
        return 90.0

    if rows >= 300:
        return 80.0

    if rows >= 250:
        return 70.0

    return 60.0


# ============================================================
# V10 AI SCORE
# ============================================================

def calculate_v10_score(
    signal,
    probability,
    expected_return,
    fast_score,
    edge,
    risk,
    quality,
):

    # --------------------------------------------------------
    # 1 MODEL CONFIDENCE
    # --------------------------------------------------------

    model_component = (
        probability
        * 45
    )

    # --------------------------------------------------------
    # 2 DIRECTIONAL RETURN
    # --------------------------------------------------------

    if signal == "BUY":

        directional_return = max(
            expected_return,
            0,
        )

    elif signal == "SELL":

        directional_return = max(
            -expected_return,
            0,
        )

    else:

        directional_return = 0

    return_component = (
        np.clip(
            directional_return
            / EXPECTED_RETURN_HIGH,
            0,
            1,
        )
        * 18
    )

    # --------------------------------------------------------
    # 3 FAST ALIGNMENT
    # --------------------------------------------------------

    if signal == "BUY":

        fast_alignment = (
            fast_score
            / 100
        )

    elif signal == "SELL":

        fast_alignment = (
            (100 - fast_score)
            / 100
        )

    else:

        fast_alignment = 0.5

    fast_component = (
        np.clip(
            fast_alignment,
            0,
            1,
        )
        * 12
    )

    # --------------------------------------------------------
    # 4 EDGE
    # --------------------------------------------------------

    edge_component = (
        np.clip(
            abs(edge)
            / 30,
            0,
            1,
        )
        * 10
    )

    # --------------------------------------------------------
    # 5 QUALITY
    # --------------------------------------------------------

    quality_component = (
        quality
        / 100
        * 7
    )

    # --------------------------------------------------------
    # RISK PENALTY
    # --------------------------------------------------------

    risk_penalty = (
        risk
        / 100
        * 12
    )

    score = (
        model_component
        + return_component
        + fast_component
        + edge_component
        + quality_component
        - risk_penalty
    )

    # --------------------------------------------------------
    # HOLD PENALTY
    # --------------------------------------------------------

    if signal == "HOLD":

        score *= 0.65

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
):

    if (
        score >= 80
        and probability >= 0.82
        and edge >= 0.12
    ):

        return "A+"

    if (
        score >= 70
        and probability >= 0.72
        and edge >= 0.08
    ):

        return "A"

    if (
        score >= 60
        and probability >= 0.62
        and edge >= 0.05
    ):

        return "B"

    if (
        score >= 50
        and probability >= 0.55
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
):

    print()
    print("=" * 78)
    print(" LEVEL 1000 V10 AI TAHMİN")
    print("=" * 78)

    # --------------------------------------------------------
    # WALK FORWARD
    # --------------------------------------------------------

    validation = (
        walk_forward_validation(
            train_all
        )
    )

    # --------------------------------------------------------
    # FINAL MODEL
    # --------------------------------------------------------

    scaler, logistic, gradient = (
        train_final_models(
            train_all
        )
    )

    X = latest_df[
        FEATURE_COLUMNS
    ]

    X_scaled = scaler.transform(
        X
    )

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

        r = latest_df.iloc[
            i
        ]

        cls = int(
            predicted[i]
        )

        if cls == 1:
            signal = "BUY"

        elif cls == -1:
            signal = "SELL"

        else:
            signal = "HOLD"

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
                buy_p
                - second
            )

        elif signal == "SELL":

            probability = sell_p

            second = max(
                buy_p,
                hold_p,
            )

            edge = (
                sell_p
                - second
            )

        else:

            probability = hold_p

            second = max(
                sell_p,
                buy_p,
            )

            edge = (
                hold_p
                - second
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

            row[column] = float(
                r[column]
            )

        row["Fast_Score"] = (
            calculate_fast_score(
                row
            )
        )

        rows_count = len(
            data.get(
                r["Symbol"],
                [],
            )
        )

        row["Rows"] = rows_count

        row["Risk_Score"] = (
            calculate_risk_score(
                row
            )
        )

        row["Data_Quality"] = (
            calculate_quality(
                rows_count
            )
        )

        row["AI_Score"] = (
            calculate_v10_score(
                signal,
                probability,
                0,
                row["Fast_Score"],
                edge,
                row["Risk_Score"],
                row["Data_Quality"],
            )
        )

        rows.append(
            row
        )

    result = pd.DataFrame(
        rows
    )

    # --------------------------------------------------------
    # PRELIMINARY
    # --------------------------------------------------------

    candidates = (
        result[
            result["Signal"]
            != "HOLD"
        ]
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
        calculate_v10_score(
            x["Signal"],
            x["_probability"],
            x[
                "AI_Predicted_Return"
            ] / 100,
            x["Fast_Score"],
            x["AI_Edge"] / 100,
            x["Risk_Score"],
            x["Data_Quality"],
        ),
        axis=1,
    )

    result["Strength"] = result.apply(
        lambda x:
        get_strength(
            x["AI_Score"],
            x[
                "AI_Probability"
            ] / 100,
            x["AI_Edge"] / 100,
        ),
        axis=1,
    )

    # --------------------------------------------------------
    # RANKING
    # --------------------------------------------------------

    result["Ranking_Score"] = (
        result["AI_Score"]
    )

    # HOLD geriye
    result.loc[
        result["Signal"] == "HOLD",
        "Ranking_Score",
    ] -= 25

    # --------------------------------------------------------
    # EXPECTED RETURN SINYAL YÖNÜ
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

    return (
        result,
        validation,
    )


# ============================================================
# OUTPUT
# ============================================================

def save_outputs(
    result,
    validation,
):

    output = result.copy()

    # Ranking_Score sıralama için gereklidir; CSV
    # çıktısına yazmadan önce değil, sıralamadan sonra sil.
    if "Ranking_Score" not in output.columns:
        output["Ranking_Score"] = output.get("AI_Score", 0.0)
        if "Signal" in output.columns:
            output.loc[output["Signal"] == "HOLD", "Ranking_Score"] -= 25.0

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
        .reset_index(
            drop=True
        )
    )

    internal = [
        "_predicted_class",
        "_probability",
        "Ranking_Score",
    ]

    output = output.drop(
        columns=[
            c
            for c in internal
            if c in output.columns
        ]
    )

    top = output.head(
        TOP_N
    ).copy()

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
        "Rows",
    ]

    latest = output[
        [
            c
            for c in latest_columns
            if c in output.columns
        ]
    ].copy()

    output.to_csv(
        SCAN_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    top.to_csv(
        TOP_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    latest.to_csv(
        LATEST_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    validation_row = {
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

        "Periods":
            validation.get(
                "Validation_Periods",
                0,
            ),
    }

    pd.DataFrame(
        [validation_row]
    ).to_csv(
        MODEL_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    return (
        output,
        top,
    )


# ============================================================
# TOP 30
# ============================================================

def print_top(
    top
):

    print()
    print("=" * 78)
    print(" LEVEL 1000 V10 TOP 30")
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
    print(" LEVEL 1000 V10")
    print(" GLOBAL AI STOCK SCANNER")
    print("=" * 78)

    print(
        "Gerçek para       : HAYIR"
    )

    print(
        "Otomatik emir     : HAYIR"
    )

    print(
        "Model             : Logistic + Gradient Boosting"
    )

    print(
        "Validation        : Walk-Forward"
    )

    print(
        f"Download Worker   : {DOWNLOAD_WORKERS}"
    )

    print(
        f"Expected Return   : TOP {EXPECTED_RETURN_CANDIDATES}"
    )

    print(
        "Cache              : AKTİF"
    )

    print()

    symbols = load_symbols()

    print(
        f"[SEMBOL] {len(symbols):,}"
    )

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    data = collect_data(
        symbols
    )

    if len(data) < 10:

        raise RuntimeError(
            "Yeterli veri bulunamadı."
        )

    # --------------------------------------------------------
    # AI DATA
    # --------------------------------------------------------

    train_all, latest_df = (
        prepare_ai_data(
            data
        )
    )

    # --------------------------------------------------------
    # AI
    # --------------------------------------------------------

    result, validation = (
        run_predictions(
            train_all,
            latest_df,
            data,
        )
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    output, top = save_outputs(
        result,
        validation,
    )

    # --------------------------------------------------------
    # TOP
    # --------------------------------------------------------

    print_top(
        top
    )

    # --------------------------------------------------------
    # COUNTS
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

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    elapsed = (
        time.time()
        - total_start
    )

    print()
    print("=" * 78)
    print(" LEVEL 1000 V10 SONUÇ")
    print("=" * 78)

    print(
        f"Taranan sembol       : "
        f"{len(symbols):,}"
    )

    print(
        f"Verisi bulunan       : "
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
        f"{min(TOP_N, len(output)):,}"
    )

    print(
        f"Toplam süre          : "
        f"{elapsed / 60:.1f} dakika"
    )

    print()
    print("=" * 78)
    print(" WALK-FORWARD MODEL")
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

    print()
    print("=" * 78)
    print(" DOSYALAR")
    print("=" * 78)

    print(
        f"SCAN   : {SCAN_FILE}"
    )

    print(
        f"TOP    : {TOP_FILE}"
    )

    print(
        f"LATEST : {LATEST_FILE}"
    )

    print(
        f"MODEL  : {MODEL_FILE}"
    )

    print(
        f"CACHE  : {CACHE_DIR}"
    )

    print()
    print("=" * 78)
    print(" V10 TAMAMLANDI")
    print("=" * 78)

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
        print(" V10 HATA")
        print("=" * 78)

        print(
            type(exc).__name__,
            ":",
            exc,
        )

        raise
