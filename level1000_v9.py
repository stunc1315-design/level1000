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
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
)
from sklearn.neighbors import NearestNeighbors


# ============================================================
# LEVEL 1000 V9.1 ULTRA FAST GLOBAL AI
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "level1000_data"
CACHE_DIR = DATA_DIR / "cache"
SYMBOLS_FILE = BASE_DIR / "symbols.txt"

PROGRESS_FILE = DATA_DIR / "v91_progress.json"
FAILED_FILE = DATA_DIR / "v91_failed_symbols.txt"

SCAN_FILE = DATA_DIR / "level1000_v91_fast_scan.csv"
TOP_FILE = DATA_DIR / "level1000_v91_fast_top.csv"
LATEST_FILE = DATA_DIR / "level1000_v91_latest_signals.csv"
MODEL_FILE = DATA_DIR / "level1000_v91_model_metrics.csv"


# ============================================================
# HIZ AYARLARI
# ============================================================

YEARS = 2

# Yahoo indirme
BATCH_SIZE = 150
DOWNLOAD_WORKERS = 12

RETRY_COUNT = 1
RETRY_SLEEP = 1.0

MIN_ROWS = 220

# AI
FORWARD_DAYS = 5
TARGET_THRESHOLD = 0.002

TRAIN_RATIO = 0.80
MAX_TRAIN_ROWS = 250000

# Sonuç
TOP_N = 300

# Expected Return artık sadece ilk 500 adayda
PRELIMINARY_TOP = 500

RANDOM_SEED = 42

# Daha hızlı Expected Return
EXPECTED_RETURN_SAMPLE = 20000
NEIGHBORS_PER_QUERY = 40
MIN_EXPECTED_RETURN_SAMPLES = 8

EXPECTED_RETURN_LOW = -0.10
EXPECTED_RETURN_HIGH = 0.10

MODEL_C = 0.5


random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


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
# GENEL
# ============================================================

def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def clean_symbol(symbol):
    return str(symbol).strip().upper()


def load_symbols():

    if not SYMBOLS_FILE.exists():
        raise FileNotFoundError(
            f"symbols.txt bulunamadı: {SYMBOLS_FILE}"
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
# PROGRESS
# ============================================================

def save_progress(completed, failed):

    payload = {
        "completed_symbols": sorted(set(completed)),
        "failed_symbols": sorted(set(failed)),
        "last_update": now_text(),
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

        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def load_progress():

    if not PROGRESS_FILE.exists():
        return set(), set()

    try:

        data = json.loads(
            PROGRESS_FILE.read_text(
                encoding="utf-8"
            )
        )

        completed = set(
            data.get(
                "completed_symbols",
                []
            )
        )

        failed = set(
            data.get(
                "failed_symbols",
                []
            )
        )

        return completed, failed

    except Exception:

        return set(), set()


def save_failed_symbols(failed):

    try:

        FAILED_FILE.write_text(
            "\n".join(sorted(set(failed))),
            encoding="utf-8",
        )

    except Exception:
        pass


# ============================================================
# CACHE
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
# YAHOO FRAME TEMİZLEME
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

                for i, x in enumerate(level1):

                    if x.upper() == symbol.upper():
                        matches.append(i)

                if matches:

                    out = df.iloc[
                        :,
                        matches
                    ].copy()

                    out.columns = (
                        df.columns
                        .get_level_values(0)[matches]
                    )

                else:

                    first_ticker = (
                        df.columns
                        .get_level_values(1)[0]
                    )

                    out = df.xs(
                        first_ticker,
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
# TEK HİSSE İNDİR
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
# HIZLI VERİ TOPLAMA
# ============================================================

def collect_data(symbols):

    old_completed, old_failed = (
        load_progress()
    )

    completed = set(
        old_completed
    )

    failed = set(
        old_failed
    )

    cached = {}

    print()
    print("=" * 78)
    print(" LEVEL 1000 V9.1 ULTRA FAST VERİ")
    print("=" * 78)

    print(
        f"Toplam sembol       : {len(symbols):,}"
    )

    # --------------------------------------------------------
    # EN ÖNEMLİ HIZLANDIRMA
    #
    # Progress dosyasına bakmadan tüm cache'i kontrol ediyoruz.
    # V8/V9 cache de doğrudan kullanılabilir.
    # --------------------------------------------------------

    cache_start = time.time()

    print()
    print(
        "[CACHE] Mevcut veriler taranıyor..."
    )

    for symbol in symbols:

        df = load_cache(symbol)

        if (
            df is not None
            and len(df) >= MIN_ROWS
        ):

            cached[symbol] = df
            completed.add(symbol)
            failed.discard(symbol)

    cache_time = (
        time.time()
        - cache_start
    )

    print(
        f"[CACHE] Hazır veri       : "
        f"{len(cached):,}"
    )

    print(
        f"[CACHE] Kontrol süresi   : "
        f"{cache_time:.1f} sn"
    )

    missing = [
        s
        for s in symbols
        if s not in cached
    ]

    print(
        f"[DOWNLOAD] Eksik         : "
        f"{len(missing):,}"
    )

    print(
        f"[DOWNLOAD] Worker        : "
        f"{DOWNLOAD_WORKERS}"
    )

    # --------------------------------------------------------
    # SADECE EKSİKLERİ İNDİR
    # --------------------------------------------------------

    start_time = time.time()

    new_downloads = 0

    if missing:

        total_batches = (
            len(missing)
            + BATCH_SIZE
            - 1
        ) // BATCH_SIZE

        # Tek executor.
        # Her batch'te yeniden oluşturulmuyor.
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

                batch_number = (
                    batch_start
                    // BATCH_SIZE
                    + 1
                )

                print(
                    f"[DOWNLOAD] "
                    f"Batch "
                    f"{batch_number}/"
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

                        cached[sym] = df
                        completed.add(sym)
                        failed.discard(sym)

                        new_downloads += 1

                    else:

                        failed.add(sym)

                save_progress(
                    completed,
                    failed,
                )

                save_failed_symbols(
                    failed
                )

                print(
                    f"           "
                    f"Cache={len(cached):,} "
                    f"| Failed={len(failed):,}"
                )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    final_data = {}

    for symbol in symbols:

        df = cached.get(
            symbol
        )

        if df is None:
            df = load_cache(
                symbol
            )

        if (
            df is not None
            and len(df) >= MIN_ROWS
        ):

            final_data[
                symbol
            ] = df

    completed = set(
        final_data.keys()
    )

    failed = (
        set(symbols)
        - completed
    )

    save_progress(
        completed,
        failed,
    )

    save_failed_symbols(
        failed
    )

    elapsed = (
        time.time()
        - start_time
    )

    print()
    print("=" * 78)
    print(" VERİ TOPLAMA TAMAMLANDI")
    print("=" * 78)

    print(
        f"Toplam sembol       : "
        f"{len(symbols):,}"
    )

    print(
        f"Kullanılabilir veri : "
        f"{len(final_data):,}"
    )

    print(
        f"Yeni indirilen      : "
        f"{new_downloads:,}"
    )

    print(
        f"Başarısız/eksik     : "
        f"{len(failed):,}"
    )

    print(
        f"İndirme süresi      : "
        f"{elapsed / 60:.1f} dakika"
    )

    return final_data


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

    rsi = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    return rsi.replace(
        [np.inf, -np.inf],
        np.nan,
    )


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

    x["rsi14"] = (
        calculate_rsi(
            close,
            14,
        )
        / 100.0
    )

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
        high - low
    ) / close.replace(
        0,
        np.nan,
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
# TRAIN + SON BAR
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
        return None, None

    ret = train[
        "future_return"
    ]

    train["target"] = np.select(
        [
            ret > TARGET_THRESHOLD,
            ret < -TARGET_THRESHOLD,
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
    # GERÇEK SON BAR
    # --------------------------------------------------------

    latest_valid = feat.dropna(
        subset=FEATURE_COLUMNS
    )

    if latest_valid.empty:
        return train, None

    latest = latest_valid.iloc[-1]

    latest_dict = {
        "Symbol": symbol,
        "Date": pd.to_datetime(
            latest_valid.index[-1]
        ),
        "Close": float(
            latest["Close"]
        ),
    }

    for column in FEATURE_COLUMNS:

        latest_dict[
            column
        ] = float(
            latest[column]
        )

    return (
        train,
        latest_dict,
    )


# ============================================================
# AI DATA
# ============================================================

def prepare_ai_data(data):

    train_parts = []
    latest_rows = []

    print()
    print("=" * 78)
    print(" AI VERİ HAZIRLAMA")
    print("=" * 78)

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
                and len(train)
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

    if (
        not train_parts
        or not latest_rows
    ):

        raise RuntimeError(
            "AI için yeterli veri yok."
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

    # Gerçek global kronolojik sıralama
    train_all = (
        train_all
        .sort_values("Date")
        .reset_index(drop=True)
    )

    # Son 250k
    if len(train_all) > MAX_TRAIN_ROWS:

        train_all = (
            train_all
            .tail(MAX_TRAIN_ROWS)
            .reset_index(drop=True)
        )

    for col in FEATURE_COLUMNS:

        train_all[col] = pd.to_numeric(
            train_all[col],
            errors="coerce",
        )

        latest_df[col] = pd.to_numeric(
            latest_df[col],
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
        f"  BUY  : "
        f"{int(counts.get(1, 0)):,}"
    )

    print(
        f"  HOLD : "
        f"{int(counts.get(0, 0)):,}"
    )

    return (
        train_all,
        latest_df,
    )


# ============================================================
# MODEL
# ============================================================

def build_model():

    return Pipeline(
        [
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "classifier",
                LogisticRegression(
                    max_iter=600,
                    C=MODEL_C,
                    class_weight="balanced",
                    random_state=RANDOM_SEED,
                ),
            ),
        ]
    )


# ============================================================
# MODEL VALIDATION
# ============================================================

def validate_model(
    train_all
):

    if len(train_all) < 500:

        model = build_model()

        model.fit(
            train_all[
                FEATURE_COLUMNS
            ],
            train_all[
                "target"
            ].astype(int),
        )

        return model, {}

    split = int(
        len(train_all)
        * TRAIN_RATIO
    )

    split = max(
        1,
        min(
            split,
            len(train_all) - 1,
        ),
    )

    train_part = train_all.iloc[
        :split
    ]

    valid_part = train_all.iloc[
        split:
    ]

    model = build_model()

    model.fit(
        train_part[
            FEATURE_COLUMNS
        ],
        train_part[
            "target"
        ].astype(int),
    )

    pred = model.predict(
        valid_part[
            FEATURE_COLUMNS
        ]
    )

    y_valid = valid_part[
        "target"
    ].astype(int)

    metrics = {
        "Accuracy":
            accuracy_score(
                y_valid,
                pred,
            ),

        "Precision_Macro":
            precision_score(
                y_valid,
                pred,
                average="macro",
                zero_division=0,
            ),

        "Recall_Macro":
            recall_score(
                y_valid,
                pred,
                average="macro",
                zero_division=0,
            ),

        "F1_Macro":
            f1_score(
                y_valid,
                pred,
                average="macro",
                zero_division=0,
            ),
    }

    for label, name in [
        (-1, "SELL"),
        (0, "HOLD"),
        (1, "BUY"),
    ]:

        metrics[
            f"{name}_Precision"
        ] = precision_score(
            y_valid,
            pred,
            labels=[label],
            average="macro",
            zero_division=0,
        )

        metrics[
            f"{name}_Recall"
        ] = recall_score(
            y_valid,
            pred,
            labels=[label],
            average="macro",
            zero_division=0,
        )

        metrics[
            f"{name}_F1"
        ] = f1_score(
            y_valid,
            pred,
            labels=[label],
            average="macro",
            zero_division=0,
        )

    # --------------------------------------------------------
    # FINAL MODEL
    # --------------------------------------------------------

    final_model = build_model()

    final_model.fit(
        train_all[
            FEATURE_COLUMNS
        ],
        train_all[
            "target"
        ].astype(int),
    )

    return (
        final_model,
        metrics,
    )


# ============================================================
# EXPECTED RETURN CONTEXT
# ============================================================

def prepare_expected_return_context(
    train_all
):

    base = train_all.dropna(
        subset=(
            FEATURE_COLUMNS
            + [
                "future_return",
                "target",
            ]
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

    y = base[
        "target"
    ].to_numpy(
        dtype=np.int8
    )

    future = base[
        "future_return"
    ].to_numpy(
        dtype=np.float32
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

    # --------------------------------------------------------
    # Her sınıf için KNN bir kez oluşturuluyor.
    # 500 adayı tek tek taramak yerine toplu query.
    # --------------------------------------------------------

    for target_class in [
        -1,
        1,
    ]:

        mask = (
            y
            == target_class
        )

        if (
            int(mask.sum())
            >= MIN_EXPECTED_RETURN_SAMPLES
        ):

            class_X = X_scaled[
                mask
            ]

            class_returns = (
                future[mask]
            )

            k = min(
                NEIGHBORS_PER_QUERY,
                len(class_X),
            )

            knn = NearestNeighbors(
                n_neighbors=k,
                metric="euclidean",
                algorithm="auto",
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
                    class_returns,
            }

    return {
        "median": median,
        "iqr": iqr,
        "models": models,
    }


# ============================================================
# TOPLU EXPECTED RETURN
# ============================================================

def calculate_expected_returns_batch(
    candidate_df,
    context,
):

    result = np.zeros(
        len(candidate_df),
        dtype=float,
    )

    if candidate_df.empty:
        return result

    Xq = candidate_df[
        FEATURE_COLUMNS
    ].to_numpy(
        dtype=np.float32
    )

    Xq = (
        Xq
        - context["median"]
    ) / context["iqr"]

    Xq = np.nan_to_num(
        Xq,
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

    for target_class in [
        -1,
        1,
    ]:

        positions = np.where(
            predicted
            == target_class
        )[0]

        if len(positions) == 0:
            continue

        model_info = context[
            "models"
        ].get(
            target_class
        )

        if model_info is None:
            continue

        queries = Xq[
            positions
        ]

        distances, indices = (
            model_info[
                "knn"
            ].kneighbors(
                queries
            )
        )

        returns = model_info[
            "returns"
        ]

        for local_i, global_i in enumerate(
            positions
        ):

            selected = returns[
                indices[
                    local_i
                ]
            ]

            selected = selected[
                np.isfinite(
                    selected
                )
            ]

            if (
                len(selected)
                < MIN_EXPECTED_RETURN_SAMPLES
            ):
                continue

            low = np.percentile(
                selected,
                10,
            )

            high = np.percentile(
                selected,
                90,
            )

            trimmed = selected[
                (selected >= low)
                & (
                    selected
                    <= high
                )
            ]

            if (
                len(trimmed)
                < MIN_EXPECTED_RETURN_SAMPLES
            ):

                trimmed = selected

            value = float(
                np.median(
                    trimmed
                )
            )

            value = float(
                np.clip(
                    value,
                    EXPECTED_RETURN_LOW,
                    EXPECTED_RETURN_HIGH,
                )
            )

            result[
                global_i
            ] = value

    return result


# ============================================================
# CLAMP
# ============================================================

def clamp(
    value,
    low,
    high,
):

    return float(
        max(
            low,
            min(
                high,
                value,
            ),
        )
    )


# ============================================================
# FAST SCORE
# ============================================================

def calculate_fast_score(
    row
):

    ret5 = float(
        row.get(
            "ret5",
            0.0,
        )
    )

    ret20 = float(
        row.get(
            "ret20",
            0.0,
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
            0.0,
        )
    )

    p50 = float(
        row.get(
            "price_vs_sma50",
            0.0,
        )
    )

    volume_ratio = float(
        row.get(
            "volume_ratio",
            1.0,
        )
    )

    score = 50.0

    score += clamp(
        ret5 * 180,
        -20,
        20,
    )

    score += clamp(
        ret20 * 90,
        -20,
        20,
    )

    score += clamp(
        (rsi - 0.5) * 45,
        -15,
        15,
    )

    score += clamp(
        p20 * 80,
        -15,
        15,
    )

    score += clamp(
        p50 * 50,
        -10,
        10,
    )

    score += clamp(
        (volume_ratio - 1)
        * 8,
        -8,
        8,
    )

    return clamp(
        score,
        0,
        100,
    )


# ============================================================
# RİSK
# ============================================================

def calculate_risk_score(
    row
):

    volatility = float(
        row.get(
            "volatility20",
            0.0,
        )
    )

    atr = float(
        row.get(
            "atr_pct",
            0.0,
        )
    )

    high_low = float(
        row.get(
            "high_low_pct",
            0.0,
        )
    )

    raw = (
        volatility * 120
        + atr * 80
        + high_low * 40
    )

    return clamp(
        raw,
        0,
        100,
    )


# ============================================================
# DATA QUALITY
# ============================================================

def calculate_data_quality(
    rows
):

    score = 100.0

    if rows < 500:
        score -= 20

    if rows < 350:
        score -= 20

    if rows < 280:
        score -= 20

    return clamp(
        score,
        0,
        100,
    )


# ============================================================
# AI SCORE
# ============================================================

def calculate_ai_score(
    signal,
    probability,
    expected_return,
    fast_score,
    edge,
    risk,
    quality,
):

    # Model
    probability_component = (
        probability * 55.0
    )

    # Beklenen getiri
    return_component = (
        clamp(
            abs(
                expected_return
            )
            / EXPECTED_RETURN_HIGH,
            0,
            1,
        )
        * 15.0
    )

    # --------------------------------------------------------
    # FAST SCORE YÖNE GÖRE
    # --------------------------------------------------------

    if signal == "BUY":

        fast_alignment = (
            fast_score
            / 100.0
        )

    elif signal == "SELL":

        fast_alignment = (
            (100.0 - fast_score)
            / 100.0
        )

    else:

        fast_alignment = 0.5

    fast_component = (
        clamp(
            fast_alignment,
            0,
            1,
        )
        * 12.0
    )

    # Edge
    edge_component = (
        clamp(
            edge / 100.0,
            0,
            1,
        )
        * 10.0
    )

    # Quality
    quality_component = (
        clamp(
            quality / 100.0,
            0,
            1,
        )
        * 8.0
    )

    # Risk
    risk_penalty = (
        clamp(
            risk / 100.0,
            0,
            1,
        )
        * 10.0
    )

    # --------------------------------------------------------
    # YÖN UYUMLU GETİRİ
    # --------------------------------------------------------

    if signal == "BUY":

        aligned_return = max(
            expected_return,
            0.0,
        )

    elif signal == "SELL":

        aligned_return = max(
            -expected_return,
            0.0,
        )

    else:

        aligned_return = 0.0

    aligned_return_component = (
        clamp(
            aligned_return
            / EXPECTED_RETURN_HIGH,
            0,
            1,
        )
        * 8.0
    )

    score = (
        probability_component
        + return_component
        + fast_component
        + edge_component
        + quality_component
        + aligned_return_component
        - risk_penalty
    )

    return clamp(
        score,
        0,
        100,
    )


# ============================================================
# STRENGTH
# ============================================================

def strength_from_score(
    score,
    probability,
    edge,
):

    if (
        score >= 75
        and probability >= 0.80
        and edge >= 15
    ):
        return "A+"

    if (
        score >= 65
        and probability >= 0.70
        and edge >= 10
    ):
        return "A"

    if (
        score >= 55
        and probability >= 0.60
        and edge >= 7
    ):
        return "B"

    if (
        score >= 45
        and probability >= 0.52
    ):
        return "C"

    return "D"


# ============================================================
# GLOBAL AI
# ============================================================

def run_ai(
    train_all,
    latest_df,
    data,
):

    print()
    print("=" * 78)
    print(" GLOBAL AI MODEL V9.1")
    print("=" * 78)

    model, metrics = (
        validate_model(
            train_all
        )
    )

    print(
        f"Accuracy       : "
        f"{metrics.get('Accuracy', 0) * 100:.2f}%"
    )

    print(
        f"Macro Precision: "
        f"{metrics.get('Precision_Macro', 0) * 100:.2f}%"
    )

    print(
        f"Macro Recall   : "
        f"{metrics.get('Recall_Macro', 0) * 100:.2f}%"
    )

    print(
        f"Macro F1       : "
        f"{metrics.get('F1_Macro', 0) * 100:.2f}%"
    )

    print()
    print("Sınıf F1:")

    print(
        f"  SELL : "
        f"{metrics.get('SELL_F1', 0) * 100:.2f}%"
    )

    print(
        f"  HOLD : "
        f"{metrics.get('HOLD_F1', 0) * 100:.2f}%"
    )

    print(
        f"  BUY  : "
        f"{metrics.get('BUY_F1', 0) * 100:.2f}%"
    )

    # --------------------------------------------------------
    # MODEL TAHMİNİ
    # --------------------------------------------------------

    X_latest = latest_df[
        FEATURE_COLUMNS
    ]

    predictions = model.predict(
        X_latest
    )

    probabilities = (
        model.predict_proba(
            X_latest
        )
    )

    classes = list(
        model
        .named_steps[
            "classifier"
        ]
        .classes_
    )

    rows = []

    for i in range(
        len(latest_df)
    ):

        r = latest_df.iloc[
            i
        ]

        predicted = int(
            predictions[i]
        )

        if predicted == 1:
            signal = "BUY"

        elif predicted == -1:
            signal = "SELL"

        else:
            signal = "HOLD"

        probs = {
            -1: 0.0,
            0: 0.0,
            1: 0.0,
        }

        for j, cls in enumerate(
            classes
        ):

            probs[
                int(cls)
            ] = float(
                probabilities[i][j]
            )

        buy_p = probs[1]
        sell_p = probs[-1]
        hold_p = probs[0]

        if signal == "BUY":

            probability = buy_p

            edge = (
                buy_p
                - max(
                    sell_p,
                    hold_p,
                )
            )

        elif signal == "SELL":

            probability = sell_p

            edge = (
                sell_p
                - max(
                    buy_p,
                    hold_p,
                )
            )

        else:

            probability = hold_p

            edge = (
                hold_p
                - max(
                    buy_p,
                    sell_p,
                )
            )

        fast = calculate_fast_score(
            r
        )

        symbol = r[
            "Symbol"
        ]

        rows_count = len(
            data.get(
                symbol,
                [],
            )
        )

        row = {
            "Symbol": symbol,
            "Date": r["Date"],
            "Close": r["Close"],
            "Signal": signal,

            "AI_Probability":
                probability * 100,

            "BUY_Probability":
                buy_p * 100,

            "SELL_Probability":
                sell_p * 100,

            "HOLD_Probability":
                hold_p * 100,

            "AI_Edge":
                edge * 100,

            "Fast_Score":
                fast,

            "ret1":
                r["ret1"],

            "ret3":
                r["ret3"],

            "ret5":
                r["ret5"],

            "ret10":
                r["ret10"],

            "ret20":
                r["ret20"],

            "volatility10":
                r["volatility10"],

            "volatility20":
                r["volatility20"],

            "rsi14":
                r["rsi14"],

            "atr_pct":
                r["atr_pct"],

            "volume_ratio":
                r["volume_ratio"],

            "price_vs_sma20":
                r["price_vs_sma20"],

            "price_vs_sma50":
                r["price_vs_sma50"],

            "sma20_vs_sma50":
                r["sma20_vs_sma50"],

            "high_low_pct":
                r["high_low_pct"],

            "close_location":
                r["close_location"],

            "Rows":
                rows_count,

            "_predicted_class":
                predicted,

            "_raw_probability":
                probability,
        }

        row["Risk_Score"] = (
            calculate_risk_score(
                row
            )
        )

        row["Data_Quality"] = (
            calculate_data_quality(
                rows_count
            )
        )

        rows.append(
            row
        )

    result = pd.DataFrame(
        rows
    )

    # --------------------------------------------------------
    # ÖN SKOR
    # --------------------------------------------------------

    result["AI_Score"] = result.apply(
        lambda x:
        calculate_ai_score(
            x["Signal"],
            x["_raw_probability"],
            0.0,
            x["Fast_Score"],
            x["AI_Edge"],
            x["Risk_Score"],
            x["Data_Quality"],
        ),
        axis=1,
    )

    # --------------------------------------------------------
    # TOP 500
    # --------------------------------------------------------

    candidate_idx = (
        result[
            result["Signal"] != "HOLD"
        ]
        .sort_values(
            [
                "AI_Score",
                "AI_Probability",
            ],
            ascending=False,
        )
        .head(
            PRELIMINARY_TOP
        )
        .index
    )

    candidate_df = result.loc[
        candidate_idx
    ].copy()

    print()
    print(
        f"[AI] Expected Return "
        f"hesaplanıyor: "
        f"{len(candidate_df):,} aday"
    )

    expected_return_start = (
        time.time()
    )

    context = (
        prepare_expected_return_context(
            train_all
        )
    )

    expected_values = (
        calculate_expected_returns_batch(
            candidate_df,
            context,
        )
    )

    result[
        "Expected_Return_Capped"
    ] = 0.0

    result.loc[
        candidate_idx,
        "Expected_Return_Capped",
    ] = expected_values

    print(
        f"[AI] Expected Return "
        f"tamamlandı: "
        f"{time.time() - expected_return_start:.1f} sn"
    )

    # --------------------------------------------------------
    # FINAL SCORE
    # --------------------------------------------------------

    result["AI_Score"] = result.apply(
        lambda x:
        calculate_ai_score(
            x["Signal"],
            x["_raw_probability"],
            x[
                "Expected_Return_Capped"
            ],
            x["Fast_Score"],
            x["AI_Edge"],
            x["Risk_Score"],
            x["Data_Quality"],
        ),
        axis=1,
    )

    result["Strength"] = result.apply(
        lambda x:
        strength_from_score(
            x["AI_Score"],
            x[
                "AI_Probability"
            ] / 100.0,
            x["AI_Edge"],
        ),
        axis=1,
    )

    result[
        "AI_Predicted_Return"
    ] = (
        result[
            "Expected_Return_Capped"
        ]
        * 100
    )

    result["Ranking_Score"] = (
        result["AI_Score"]
    )

    # HOLD geriye atılır.
    result.loc[
        result["Signal"] == "HOLD",
        "Ranking_Score",
    ] -= 20

    return (
        result,
        metrics,
    )


# ============================================================
# OUTPUT
# ============================================================

def save_outputs(
    result,
    metrics,
):

    output = result.copy()

    internal_columns = [
        "_predicted_class",
        "_raw_probability",
        "Ranking_Score",
    ]

    output = output.drop(
        columns=[
            c
            for c in internal_columns
            if c in output.columns
        ]
    )

    numeric_cols = (
        output
        .select_dtypes(
            include=[np.number]
        )
        .columns
    )

    output[numeric_cols] = (
        output[numeric_cols]
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
    )

    output = (
        output
        .sort_values(
            [
                "AI_Score",
                "AI_Probability",
            ],
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    top = output.head(
        TOP_N
    ).copy()

    latest_columns = [
        "Symbol",
        "Date",
        "Close",
        "Signal",
        "AI_Probability",
        "BUY_Probability",
        "SELL_Probability",
        "HOLD_Probability",
        "AI_Edge",
        "AI_Predicted_Return",
        "Expected_Return_Capped",
        "Fast_Score",
        "AI_Score",
        "Strength",
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

    metrics_out = pd.DataFrame(
        [
            {
                "Metric": key,
                "Value": value,
            }
            for key, value
            in metrics.items()
        ]
    )

    metrics_out.to_csv(
        MODEL_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    return (
        output,
        top,
    )


# ============================================================
# TOP 20
# ============================================================

def print_top(top):

    print()
    print("=" * 78)
    print(" TOP 20 AI V9.1 ADAY")
    print("=" * 78)

    for i, (_, row) in enumerate(
        top.head(20).iterrows(),
        1,
    ):

        print(
            f"{i:2d}. "
            f"{str(row['Symbol']):<10} "
            f"{str(row['Signal']):<5} "
            f"{str(row['Strength']):<3} "
            f"AI=% "
            f"{row['AI_Probability']:5.1f} "
            f"Beklenen=% "
            f"{row['AI_Predicted_Return']:7.2f} "
            f"Fast="
            f"{row['Fast_Score']:6.2f} "
            f"Risk="
            f"{row['Risk_Score']:5.1f} "
            f"Edge="
            f"{row['AI_Edge']:5.1f} "
            f"AI="
            f"{row['AI_Score']:6.2f}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    total_start = time.time()

    print("=" * 78)
    print(" LEVEL 1000 V9.1 ULTRA FAST GLOBAL AI")
    print("=" * 78)

    print(
        "Gerçek para       : HAYIR"
    )

    print(
        "Otomatik emir     : HAYIR"
    )

    print(
        "Veri kaynağı      : Yahoo Finance"
    )

    print(
        "Tarama            : GLOBAL"
    )

    print(
        "Cache kullanımı   : EVET"
    )

    print(
        "Cache tekrar indirme : HAYIR"
    )

    print(
        "Download Worker   : "
        f"{DOWNLOAD_WORKERS}"
    )

    print(
        "Expected Return   : TOP "
        f"{PRELIMINARY_TOP}"
    )

    print(
        "Expected Return CAP : ±10%"
    )

    print(
        "Son bar tahmini   : EVET"
    )

    print(
        "Kronolojik valid. : EVET"
    )

    print()

    symbols = load_symbols()

    print(
        f"[SEMBOL] Toplam: "
        f"{len(symbols):,}"
    )

    data = collect_data(
        symbols
    )

    if len(data) < 10:

        raise RuntimeError(
            "Yeterli sembol verisi yok."
        )

    train_all, latest_df = (
        prepare_ai_data(
            data
        )
    )

    result, metrics = run_ai(
        train_all,
        latest_df,
        data,
    )

    output, top = save_outputs(
        result,
        metrics,
    )

    print_top(
        top
    )

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

    elapsed = (
        time.time()
        - total_start
    )

    print()
    print("=" * 78)
    print(" LEVEL 1000 V9.1 SONUÇ")
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
        f"TOP aday             : "
        f"{min(TOP_N, len(output)):,}"
    )

    print(
        f"Başarısız/eksik      : "
        f"{len(symbols) - len(data):,}"
    )

    print(
        f"Toplam süre          : "
        f"{elapsed / 60:.1f} dakika"
    )

    print()
    print("=" * 78)
    print(" MODEL")
    print("=" * 78)

    print(
        f"Accuracy             : "
        f"{metrics.get('Accuracy', 0) * 100:.2f}%"
    )

    print(
        f"Macro F1             : "
        f"{metrics.get('F1_Macro', 0) * 100:.2f}%"
    )

    print(
        f"BUY F1               : "
        f"{metrics.get('BUY_F1', 0) * 100:.2f}%"
    )

    print(
        f"SELL F1              : "
        f"{metrics.get('SELL_F1', 0) * 100:.2f}%"
    )

    print(
        f"HOLD F1              : "
        f"{metrics.get('HOLD_F1', 0) * 100:.2f}%"
    )

    print()
    print("=" * 78)
    print(" DOSYALAR")
    print("=" * 78)

    print(
        f"SCAN     : {SCAN_FILE}"
    )

    print(
        f"TOP      : {TOP_FILE}"
    )

    print(
        f"LATEST   : {LATEST_FILE}"
    )

    print(
        f"MODEL    : {MODEL_FILE}"
    )

    print(
        f"CACHE    : {CACHE_DIR}"
    )

    print(
        f"PROGRESS : {PROGRESS_FILE}"
    )

    print(
        f"FAILED   : {FAILED_FILE}"
    )

    print()
    print("=" * 78)
    print(" V9.1 TAMAMLANDI")
    print("=" * 78)

    print(
        "Gerçek para kullanılmadı."
    )

    print(
        "Otomatik emir gönderilmedi."
    )


# ============================================================
# ÇALIŞTIR
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print(
            "[DURDURULDU] "
            "V9.1 kullanıcı tarafından durduruldu."
        )

    except Exception as exc:

        print()
        print("=" * 78)
        print(" V9.1 HATA")
        print("=" * 78)

        print(
            type(exc).__name__,
            ":",
            exc,
        )

        raise