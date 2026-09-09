from pathlib import Path
import time
import json
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
)


# ============================================================
# LEVEL 1000 V8 FAST GLOBAL
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "level1000_data"
CACHE_DIR = DATA_DIR / "cache"
SYMBOLS_FILE = BASE_DIR / "symbols.txt"

PROGRESS_FILE = DATA_DIR / "v8_progress.json"
FAILED_FILE = DATA_DIR / "v8_failed_symbols.txt"

SCAN_FILE = DATA_DIR / "level1000_v8_fast_scan.csv"
TOP_FILE = DATA_DIR / "level1000_v8_fast_top.csv"
LATEST_FILE = DATA_DIR / "level1000_v8_latest_signals.csv"
METRICS_FILE = DATA_DIR / "level1000_v8_model_metrics.csv"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# AYARLAR
# ============================================================

YEARS = 2

BATCH_SIZE = 100
DOWNLOAD_WORKERS = 4

RETRY_COUNT = 2
RETRY_SLEEP = 2

MIN_ROWS = 220
CACHE_HOURS = 20

FORWARD_DAYS = 5
TARGET_THRESHOLD = 0.002

TRAIN_RATIO = 0.80
MAX_TRAIN_ROWS = 250000

TOP_N = 300

RANDOM_SEED = 42

EXPECTED_RETURN_SAMPLE = 30000
NEIGHBORS_PER_QUERY = 50
MIN_EXPECTED_RETURN_SAMPLES = 8

MODEL_C = 0.5


# ============================================================
# FEATURES
# ============================================================

FEATURE_COLUMNS = [
    "ret_5",
    "ret_20",
    "ret_60",
    "dist_sma20",
    "dist_sma50",
    "dist_sma100",
    "volatility20",
    "volume_ratio20",
    "atr_pct",
    "rsi14",
    "macd_hist",
    "range_pos60",
]


# ============================================================
# BAŞLANGIÇ
# ============================================================

PROGRAM_START = time.time()

print()
print("=" * 78)
print(" LEVEL 1000 V8 FAST GLOBAL")
print("=" * 78)
print(" Gerçek para       : HAYIR")
print(" Otomatik emir     : HAYIR")
print(" Veri kaynağı      : Yahoo Finance")
print(" Tarama            : GLOBAL")
print(" Kaldığı yerden    : EVET")
print(" Kalıcı cache      : EVET")
print("=" * 78)
print()


# ============================================================
# SEMBOLLER
# ============================================================

def normalize_symbol(symbol):

    if symbol is None:
        return None

    symbol = str(symbol).strip().upper()

    if not symbol:
        return None

    if symbol.startswith("#"):
        return None

    return symbol.replace('"', "").replace("'", "")


def load_symbols():

    symbols = []

    if SYMBOLS_FILE.exists():

        with open(
            SYMBOLS_FILE,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:

            for line in f:

                symbol = normalize_symbol(line)

                if symbol:
                    symbols.append(symbol)

    if not symbols:

        symbols = [
            "AAPL",
            "MSFT",
            "NVDA",
            "AMZN",
            "GOOGL",
            "META",
            "TSLA",
            "AVGO",
            "AMD",
            "NFLX",
            "JPM",
            "V",
            "MA",
            "WMT",
            "COST",
        ]

    return list(dict.fromkeys(symbols))


SYMBOLS = load_symbols()
TOTAL_SYMBOLS = len(SYMBOLS)

print(f"[SEMBOL] Toplam: {TOTAL_SYMBOLS:,}")
print()


# ============================================================
# TARİH
# ============================================================

END_DATE = pd.Timestamp.utcnow()

if END_DATE.tzinfo is not None:
    END_DATE = END_DATE.tz_localize(None)

START_DATE = END_DATE - pd.DateOffset(years=YEARS)


# ============================================================
# CACHE
# ============================================================

def cache_path(symbol):

    safe = (
        symbol
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace(".", "_")
    )

    return CACHE_DIR / f"{safe}.csv"


def load_cache(symbol):

    path = cache_path(symbol)

    if not path.exists():
        return None

    try:

        df = pd.read_csv(path)

        if len(df) < MIN_ROWS:
            return None

        if "Date" not in df.columns:
            return None

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        if not all(
            c in df.columns
            for c in required
        ):
            return None

        df["Date"] = pd.to_datetime(
            df["Date"],
            errors="coerce"
        )

        df = df.dropna(
            subset=["Date"]
        )

        for col in required:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        df = df.dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close",
            ]
        )

        df = df.drop_duplicates(
            subset=["Date"]
        )

        df = df.sort_values("Date")

        if len(df) < MIN_ROWS:
            return None

        return df[
            [
                "Date",
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
            ]
        ]

    except Exception:
        return None


# ============================================================
# PROGRESS
# ============================================================

def load_progress():

    if not PROGRESS_FILE.exists():

        return {
            "completed_symbols": [],
            "failed_symbols": [],
            "last_update": None,
        }

    try:

        with open(
            PROGRESS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        return {
            "completed_symbols":
                data.get(
                    "completed_symbols",
                    []
                ),

            "failed_symbols":
                data.get(
                    "failed_symbols",
                    []
                ),

            "last_update":
                data.get(
                    "last_update"
                ),
        }

    except Exception:

        return {
            "completed_symbols": [],
            "failed_symbols": [],
            "last_update": None,
        }


progress = load_progress()

completed_symbols = set(
    normalize_symbol(x)
    for x in progress["completed_symbols"]
    if normalize_symbol(x)
)

failed_symbols = set(
    normalize_symbol(x)
    for x in progress["failed_symbols"]
    if normalize_symbol(x)
)


def save_progress():

    data = {
        "completed_symbols":
            sorted(completed_symbols),

        "failed_symbols":
            sorted(failed_symbols),

        "last_update":
            time.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
    }

    temp = DATA_DIR / "v8_progress.tmp"

    try:

        with open(
            temp,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

        temp.replace(PROGRESS_FILE)

    except Exception:
        pass


def save_failed_symbols():

    try:

        with open(
            FAILED_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            for symbol in sorted(
                failed_symbols
            ):

                f.write(
                    symbol + "\n"
                )

    except Exception:
        pass


# ============================================================
# CACHE KONTROLÜ
# ============================================================

print("=" * 78)
print(" KALICI CACHE KONTROLÜ")
print("=" * 78)
print()


all_data = {}
download_symbols = []

for symbol in SYMBOLS:

    df = load_cache(symbol)

    if df is not None:

        all_data[symbol] = df
        completed_symbols.add(symbol)

    else:

        download_symbols.append(symbol)


save_progress()

print(
    f"[CACHE] Kullanılabilir: "
    f"{len(all_data):,}"
)

print(
    f"[DOWNLOAD] Eksik/yeni: "
    f"{len(download_symbols):,}"
)

print(
    f"[PROGRESS] Tamamlanan: "
    f"{len(completed_symbols):,}"
)

print()


# ============================================================
# BATCH
# ============================================================

def make_batches(items, size):

    for i in range(
        0,
        len(items),
        size
    ):

        yield items[i:i + size]


batches = list(
    make_batches(
        download_symbols,
        BATCH_SIZE
    )
)

print(
    f"[BATCH] {len(batches):,} batch"
)

print(
    f"[THREAD] {DOWNLOAD_WORKERS} worker"
)

print()


# ============================================================
# YAHOO DOWNLOAD
# ============================================================

def download_batch(batch):

    if not batch:
        return {}

    for attempt in range(
        RETRY_COUNT + 1
    ):

        try:

            data = yf.download(
                tickers=batch,
                start=START_DATE.strftime(
                    "%Y-%m-%d"
                ),
                end=END_DATE.strftime(
                    "%Y-%m-%d"
                ),
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=True,
                group_by="ticker",
                timeout=45,
            )

            if data is None or data.empty:
                raise ValueError(
                    "Yahoo boş veri"
                )

            result = {}

            # ------------------------------------------------
            # TEK SEMBOL
            # ------------------------------------------------

            if len(batch) == 1:

                symbol = batch[0]

                df = data.copy()

                if isinstance(
                    df.columns,
                    pd.MultiIndex
                ):

                    df.columns = (
                        df.columns
                        .get_level_values(-1)
                    )

                    if not all(
                        c in df.columns
                        for c in [
                            "Open",
                            "High",
                            "Low",
                            "Close",
                            "Volume",
                        ]
                    ):

                        df.columns = (
                            data.columns
                            .get_level_values(0)
                        )

                result[symbol] = df

                return result

            # ------------------------------------------------
            # MULTI SYMBOL
            # ------------------------------------------------

            if not isinstance(
                data.columns,
                pd.MultiIndex
            ):

                return {}

            level0 = set(
                data.columns
                .get_level_values(0)
            )

            level1 = set(
                data.columns
                .get_level_values(1)
            )

            for symbol in batch:

                try:

                    if symbol in level0:

                        df = data[symbol].copy()

                    elif symbol in level1:

                        df = data.xs(
                            symbol,
                            axis=1,
                            level=1
                        ).copy()

                    else:

                        continue

                    if df is not None and not df.empty:

                        result[symbol] = df

                except Exception:
                    continue

            return result

        except Exception:

            if attempt < RETRY_COUNT:

                time.sleep(
                    RETRY_SLEEP
                )

    return {}


# ============================================================
# VERİ TEMİZLEME
# ============================================================

def clean_dataframe(df):

    try:

        if df is None or df.empty:
            return None

        df = df.copy()

        if isinstance(
            df.columns,
            pd.MultiIndex
        ):

            # MultiIndex'te fiyat kolonlarını bul
            wanted = {
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
            }

            selected = {}

            for col in df.columns:

                name = str(col[-1])

                if name in wanted:
                    selected[name] = df[col]

            if len(selected) < 5:

                selected = {}

                for col in df.columns:

                    name = str(col[0])

                    if name in wanted:
                        selected[name] = df[col]

            if len(selected) < 5:
                return None

            df = pd.DataFrame(
                selected,
                index=df.index
            )

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        if not all(
            c in df.columns
            for c in required
        ):
            return None

        df = df.reset_index()

        if "Date" not in df.columns:

            if "Datetime" in df.columns:

                df.rename(
                    columns={
                        "Datetime": "Date"
                    },
                    inplace=True
                )

            else:

                return None

        df["Date"] = pd.to_datetime(
            df["Date"],
            errors="coerce"
        )

        for col in required:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        df = df.dropna(
            subset=[
                "Date",
                "Open",
                "High",
                "Low",
                "Close",
            ]
        )

        df = df.drop_duplicates(
            subset=["Date"]
        )

        df = df.sort_values(
            "Date"
        )

        if len(df) < MIN_ROWS:
            return None

        return df[
            [
                "Date",
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
            ]
        ]

    except Exception:

        return None


def save_cache(symbol, df):

    path = cache_path(symbol)
    temp = CACHE_DIR / (
        "." + path.name + ".tmp"
    )

    try:

        df.to_csv(
            temp,
            index=False,
            encoding="utf-8"
        )

        temp.replace(path)

        return True

    except Exception:

        try:

            if temp.exists():
                temp.unlink()

        except Exception:
            pass

        return False


# ============================================================
# DOWNLOAD
# ============================================================

download_start = time.time()

if batches:

    print("=" * 78)
    print(" GLOBAL VERİ İNDİRME")
    print("=" * 78)
    print()

    with ThreadPoolExecutor(
        max_workers=DOWNLOAD_WORKERS
    ) as executor:

        future_map = {
            executor.submit(
                download_batch,
                batch
            ): batch
            for batch in batches
        }

        completed_batches = 0

        for future in as_completed(
            future_map
        ):

            batch = future_map[future]

            try:

                raw = future.result()

            except Exception:

                raw = {}

            batch_ok = 0
            batch_fail = 0

            for symbol in batch:

                df = clean_dataframe(
                    raw.get(symbol)
                )

                if df is not None:

                    if save_cache(
                        symbol,
                        df
                    ):

                        all_data[symbol] = df

                        completed_symbols.add(
                            symbol
                        )

                        failed_symbols.discard(
                            symbol
                        )

                        batch_ok += 1

                    else:

                        failed_symbols.add(
                            symbol
                        )

                        batch_fail += 1

                else:

                    failed_symbols.add(
                        symbol
                    )

                    batch_fail += 1

            completed_batches += 1

            save_progress()
            save_failed_symbols()

            elapsed = (
                time.time() -
                download_start
            )

            print(
                f"[DATA "
                f"{completed_batches:>3}/"
                f"{len(batches):<3}] "
                f"veri={len(all_data):,}/"
                f"{TOTAL_SYMBOLS:,} "
                f"| OK={batch_ok:,} "
                f"| FAIL={batch_fail:,} "
                f"| süre={elapsed/60:.1f} dk"
            )

else:

    print(
        "[CACHE] İndirilecek yeni veri yok."
    )


download_time = (
    time.time() -
    download_start
)


# ============================================================
# DATA SUMMARY
# ============================================================

print()
print("=" * 78)
print(" VERİ TOPLAMA TAMAMLANDI")
print("=" * 78)

print(
    f"Toplam sembol          : "
    f"{TOTAL_SYMBOLS:,}"
)

print(
    f"Kullanılabilir veri    : "
    f"{len(all_data):,}"
)

print(
    f"Başarısız/eksik        : "
    f"{len(failed_symbols):,}"
)

print(
    f"İndirme süresi         : "
    f"{download_time/60:.1f} dakika"
)

print()


if not all_data:

    print(
        "[HATA] Kullanılabilir veri yok."
    )

    raise SystemExit(1)


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def calculate_features(df):

    df = df.copy()

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    # RETURNS
    df["ret_5"] = (
        close.pct_change(5)
    )

    df["ret_20"] = (
        close.pct_change(20)
    )

    df["ret_60"] = (
        close.pct_change(60)
    )

    # MOVING AVERAGES
    sma20 = (
        close.rolling(20)
        .mean()
    )

    sma50 = (
        close.rolling(50)
        .mean()
    )

    sma100 = (
        close.rolling(100)
        .mean()
    )

    df["dist_sma20"] = (
        close / sma20 - 1
    )

    df["dist_sma50"] = (
        close / sma50 - 1
    )

    df["dist_sma100"] = (
        close / sma100 - 1
    )

    # VOLATILITY
    returns = close.pct_change()

    df["volatility20"] = (
        returns.rolling(20)
        .std()
    )

    # VOLUME
    volume_mean = (
        volume.rolling(20)
        .mean()
    )

    df["volume_ratio20"] = (
        volume /
        volume_mean
    )

    # ATR
    previous_close = close.shift(1)

    tr1 = high - low

    tr2 = (
        high -
        previous_close
    ).abs()

    tr3 = (
        low -
        previous_close
    ).abs()

    true_range = pd.concat(
        [
            tr1,
            tr2,
            tr3,
        ],
        axis=1
    ).max(axis=1)

    atr14 = (
        true_range
        .rolling(14)
        .mean()
    )

    df["atr_pct"] = (
        atr14 / close
    )

    # RSI
    delta = close.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = (
        gain.rolling(14)
        .mean()
    )

    avg_loss = (
        loss.rolling(14)
        .mean()
    )

    rs = (
        avg_gain /
        avg_loss.replace(
            0,
            np.nan
        )
    )

    df["rsi14"] = (
        100 -
        100 / (1 + rs)
    )

    # MACD
    ema12 = (
        close.ewm(
            span=12,
            adjust=False
        ).mean()
    )

    ema26 = (
        close.ewm(
            span=26,
            adjust=False
        ).mean()
    )

    macd = (
        ema12 - ema26
    )

    macd_signal = (
        macd.ewm(
            span=9,
            adjust=False
        ).mean()
    )

    df["macd_hist"] = (
        macd -
        macd_signal
    )

    # RANGE POSITION
    low60 = (
        low.rolling(60)
        .min()
    )

    high60 = (
        high.rolling(60)
        .max()
    )

    denominator = (
        high60 - low60
    ).replace(
        0,
        np.nan
    )

    df["range_pos60"] = (
        (close - low60) /
        denominator
    )

    return df


# ============================================================
# FAST SCORE
# ============================================================

def calculate_fast_score(row):

    score = 0.0

    if row["dist_sma20"] > 0:
        score += 10

    if row["dist_sma50"] > 0:
        score += 10

    if row["dist_sma100"] > 0:
        score += 10

    score += np.clip(
        row["ret_5"] * 100,
        -10,
        10
    )

    score += np.clip(
        row["ret_20"] * 50,
        -10,
        10
    )

    score += np.clip(
        row["ret_60"] * 25,
        -10,
        10
    )

    rsi = row["rsi14"]

    if 50 <= rsi <= 70:

        score += 10

    elif 30 <= rsi < 50:

        score += 3

    elif rsi > 80:

        score -= 8

    elif rsi < 20:

        score -= 5

    if row["macd_hist"] > 0:

        score += 8

    else:

        score -= 5

    if row["volume_ratio20"] > 1.2:

        score += 5

    return float(score)


# ============================================================
# AI DATA HAZIRLAMA
# ============================================================

print("=" * 78)
print(" AI VERİ HAZIRLAMA")
print("=" * 78)
print()


training_parts = []
latest_rows = []

feature_start = time.time()

for idx, (
    symbol,
    raw_df
) in enumerate(
    all_data.items(),
    start=1
):

    try:

        df = calculate_features(
            raw_df
        )

        close = df["Close"].astype(
            float
        )

        future_return = (
            close.shift(-FORWARD_DAYS)
            / close
            - 1
        )

        df["future_return"] = (
            future_return
        )

        # 0 SELL
        # 1 BUY
        # 2 HOLD

        df["target"] = np.where(
            future_return >
            TARGET_THRESHOLD,
            1,
            np.where(
                future_return <
                -TARGET_THRESHOLD,
                0,
                2
            )
        )

        clean = df.dropna(
            subset=
            FEATURE_COLUMNS
            + [
                "future_return",
                "target",
            ]
        ).copy()

        if len(clean) < 100:
            continue

        latest = clean.iloc[-1]

        latest_rows.append({

            "Symbol":
                symbol,

            "Date":
                latest["Date"],

            "Close":
                float(latest["Close"]),

            "Fast_Score":
                calculate_fast_score(
                    latest
                ),

            "_features":
                latest[
                    FEATURE_COLUMNS
                ].astype(float).values,
        })

        # Son 120 geçmiş veri
        train_part = (
            clean.iloc[:-1]
            .tail(120)
            .copy()
        )

        if len(train_part) >= 50:

            training_parts.append(
                train_part[
                    FEATURE_COLUMNS
                    + [
                        "future_return",
                        "target",
                        "Date",
                    ]
                ]
            )

        if idx % 500 == 0:

            elapsed = (
                time.time()
                - feature_start
            )

            print(
                f"[AI DATA] "
                f"{idx:,}/"
                f"{len(all_data):,} "
                f"| eğitim parçası="
                f"{len(training_parts):,} "
                f"| süre="
                f"{elapsed/60:.1f} dk"
            )

    except Exception:
        continue


if not training_parts:

    print(
        "[HATA] Eğitim verisi oluşturulamadı."
    )

    raise SystemExit(1)


train_df = pd.concat(
    training_parts,
    ignore_index=True
)


# ============================================================
# MAX TRAIN ROWS
# ============================================================

if len(train_df) > MAX_TRAIN_ROWS:

    train_df = train_df.sample(
        MAX_TRAIN_ROWS,
        random_state=RANDOM_SEED
    ).reset_index(
        drop=True
    )


train_df = train_df.replace(
    [np.inf, -np.inf],
    np.nan
)

train_df = train_df.dropna(
    subset=
    FEATURE_COLUMNS
    + [
        "future_return",
        "target",
    ]
).reset_index(
    drop=True
)


print()
print(
    f"[AI DATA] Eğitim satırı: "
    f"{len(train_df):,}"
)

print(
    f"[AI DATA] Son durum: "
    f"{len(latest_rows):,}"
)


# ============================================================
# CLASS DISTRIBUTION
# ============================================================

print()
print("[AI] Sınıf dağılımı:")

class_counts = (
    train_df["target"]
    .value_counts()
    .sort_index()
)

for cls, count in class_counts.items():

    name = {
        0: "SELL",
        1: "BUY",
        2: "HOLD",
    }.get(
        int(cls),
        "UNKNOWN"
    )

    print(
        f"  {name:<5}: {count:,}"
    )


# ============================================================
# MODEL DATA
# ============================================================

X = train_df[
    FEATURE_COLUMNS
].astype(float)

y = train_df[
    "target"
].astype(int)


split = int(
    len(train_df) *
    TRAIN_RATIO
)

X_train = X.iloc[:split]
X_test = X.iloc[split:]

y_train = y.iloc[:split]
y_test = y.iloc[split:]


# ============================================================
# GLOBAL AI MODEL
# ============================================================

print()
print("=" * 78)
print(" GLOBAL AI MODEL")
print("=" * 78)
print()


model_start = time.time()


# DİKKAT:
# multi_class KULLANILMIYOR.
# Yeni sklearn sürümleriyle uyumludur.

model = Pipeline([
    (
        "scaler",
        StandardScaler()
    ),
    (
        "classifier",
        LogisticRegression(
            max_iter=1000,
            C=MODEL_C,
            class_weight="balanced",
            random_state=RANDOM_SEED
        )
    ),
])


model.fit(
    X_train,
    y_train
)


model_time = (
    time.time() -
    model_start
)


# ============================================================
# MODEL TEST
# ============================================================

test_pred = model.predict(
    X_test
)

accuracy = accuracy_score(
    y_test,
    test_pred
)

precision = precision_score(
    y_test,
    test_pred,
    average="weighted",
    zero_division=0
)

recall = recall_score(
    y_test,
    test_pred,
    average="weighted",
    zero_division=0
)

f1 = f1_score(
    y_test,
    test_pred,
    average="weighted",
    zero_division=0
)


print(
    f"Accuracy  : "
    f"%{accuracy * 100:.2f}"
)

print(
    f"Precision : "
    f"%{precision * 100:.2f}"
)

print(
    f"Recall    : "
    f"%{recall * 100:.2f}"
)

print(
    f"F1        : "
    f"%{f1 * 100:.2f}"
)

print(
    f"Model süre: "
    f"{model_time:.1f} saniye"
)


# ============================================================
# EXPECTED RETURN REFERANSI
# ============================================================

print()
print("=" * 78)
print(" BEKLENEN GETİRİ REFERANSI")
print("=" * 78)
print()


reference_df = train_df[
    FEATURE_COLUMNS
    + [
        "future_return",
        "target",
    ]
].copy()


if len(reference_df) > EXPECTED_RETURN_SAMPLE:

    reference_df = reference_df.sample(
        EXPECTED_RETURN_SAMPLE,
        random_state=RANDOM_SEED
    ).reset_index(
        drop=True
    )


reference_features = (
    reference_df[
        FEATURE_COLUMNS
    ]
    .astype(float)
    .values
)

reference_returns = (
    reference_df[
        "future_return"
    ]
    .astype(float)
    .values
)

reference_targets = (
    reference_df[
        "target"
    ]
    .astype(int)
    .values
)


reference_mean = np.nanmean(
    reference_features,
    axis=0
)

reference_std = np.nanstd(
    reference_features,
    axis=0
)

reference_std[
    reference_std == 0
] = 1


reference_scaled = (
    reference_features -
    reference_mean
) / reference_std


# ============================================================
# EXPECTED RETURN
# ============================================================

def calculate_expected_return(
    feature_vector,
    predicted_class
):

    try:

        x = np.asarray(
            feature_vector,
            dtype=float
        )

        if not np.all(
            np.isfinite(x)
        ):
            return 0.0

        mask = (
            reference_targets ==
            int(predicted_class)
        )

        if (
            mask.sum() <
            MIN_EXPECTED_RETURN_SAMPLES
        ):
            return 0.0

        x_scaled = (
            x -
            reference_mean
        ) / reference_std

        candidates = (
            reference_scaled[mask]
        )

        returns = (
            reference_returns[mask]
        )

        distances = np.sum(
            (
                candidates -
                x_scaled
            ) ** 2,
            axis=1
        )

        k = min(
            NEIGHBORS_PER_QUERY,
            len(distances)
        )

        nearest_idx = np.argpartition(
            distances,
            k - 1
        )[:k]

        nearest_returns = (
            returns[
                nearest_idx
            ]
        )

        nearest_returns = (
            nearest_returns[
                np.isfinite(
                    nearest_returns
                )
            ]
        )

        if len(
            nearest_returns
        ) == 0:

            return 0.0

        if len(
            nearest_returns
        ) >= 10:

            low = np.percentile(
                nearest_returns,
                10
            )

            high = np.percentile(
                nearest_returns,
                90
            )

            filtered = (
                nearest_returns[
                    (nearest_returns >= low)
                    &
                    (nearest_returns <= high)
                ]
            )

            if len(filtered) > 0:

                nearest_returns = (
                    filtered
                )

        return float(
            np.median(
                nearest_returns
            )
        )

    except Exception:

        return 0.0


# ============================================================
# AI SCAN
# ============================================================

print()
print("=" * 78)
print(" AI GLOBAL TARAMA")
print("=" * 78)
print()


# ------------------------------------------------------------
# ÖNCE TÜM SEMBOLLERDE MODEL OLASILIĞI
# ------------------------------------------------------------

preliminary = []

ai_start = time.time()

for idx, item in enumerate(
    latest_rows,
    start=1
):

    try:

        features = np.asarray(
            item["_features"],
            dtype=float
        )

        if not np.all(
            np.isfinite(features)
        ):
            continue

        X_latest = pd.DataFrame(
            [features],
            columns=FEATURE_COLUMNS
        )

        probabilities = (
            model.predict_proba(
                X_latest
            )[0]
        )

        classes = model.classes_

        probability_map = {
            int(cls): float(prob)
            for cls, prob in zip(
                classes,
                probabilities
            )
        }

        buy_probability = (
            probability_map.get(
                1,
                0.0
            )
        )

        sell_probability = (
            probability_map.get(
                0,
                0.0
            )
        )

        hold_probability = (
            probability_map.get(
                2,
                0.0
            )
        )

        predicted_class = int(
            classes[
                np.argmax(
                    probabilities
                )
            ]
        )

        signal = {
            0: "SELL",
            1: "BUY",
            2: "HOLD",
        }.get(
            predicted_class,
            "HOLD"
        )

        ai_probability = float(
            np.max(probabilities)
        )

        fast_score = float(
            item["Fast_Score"]
        )

        if signal == "BUY":

            direction_score = (
                buy_probability * 100
            )

        elif signal == "SELL":

            direction_score = (
                sell_probability * 100
            )

        else:

            direction_score = (
                hold_probability * 100
            )

        fast_component = float(
            np.clip(
                abs(fast_score),
                0,
                100
            )
        )

        preliminary_score = (
            direction_score * 0.70
            +
            fast_component * 0.30
        )

        preliminary.append({

            "Symbol":
                item["Symbol"],

            "Date":
                item["Date"],

            "Close":
                item["Close"],

            "Signal":
                signal,

            "Predicted_Class":
                predicted_class,

            "AI_Probability":
                ai_probability,

            "BUY_Probability":
                buy_probability,

            "SELL_Probability":
                sell_probability,

            "HOLD_Probability":
                hold_probability,

            "Fast_Score":
                fast_score,

            "Preliminary_Score":
                preliminary_score,

            "_features":
                features,
        })

    except Exception:
        continue


# ============================================================
# EXPECTED RETURN SADECE EN İYİ ADAYLARDA
# ============================================================
#
# Bu bölüm V8'i ciddi şekilde hızlandırır.
# 7.000+ sembol için pahalı nearest-neighbor hesabı
# yerine yalnızca ilk 1.000 aday hesaplanır.
# ============================================================

preliminary_df = pd.DataFrame(
    preliminary
)

if preliminary_df.empty:

    print(
        "[HATA] AI sonucu yok."
    )

    raise SystemExit(1)


preliminary_df = (
    preliminary_df
    .sort_values(
        [
            "Preliminary_Score",
            "AI_Probability",
        ],
        ascending=False
    )
    .reset_index(drop=True)
)


EXPECTED_RETURN_CANDIDATES = min(
    1000,
    len(preliminary_df)
)


top_candidates = (
    preliminary_df
    .head(
        EXPECTED_RETURN_CANDIDATES
    )
    .copy()
)


print(
    f"[AI] Ön aday: "
    f"{len(preliminary_df):,}"
)

print(
    f"[AI] Beklenen getiri hesaplanıyor: "
    f"{len(top_candidates):,}"
)

print()


# ============================================================
# EXPECTED RETURN
# ============================================================

final_results = []

expected_start = time.time()

for idx, (_, row) in enumerate(
    top_candidates.iterrows(),
    start=1
):

    try:

        expected_return = (
            calculate_expected_return(
                row["_features"],
                row["Predicted_Class"]
            )
        )

        direction_return = 0.0

        if row["Signal"] == "BUY":

            direction_return = (
                expected_return
            )

        elif row["Signal"] == "SELL":

            direction_return = (
                -expected_return
            )

        # Negatif/ters yönlü getiriyi puanlamaya
        # avantaj olarak vermiyoruz.

        return_component = float(
            np.clip(
                direction_return * 100,
                0,
                25
            )
        )

        direction_score = (
            row["AI_Probability"] *
            100
        )

        fast_component = float(
            np.clip(
                abs(
                    row["Fast_Score"]
                ),
                0,
                100
            )
        )

        ai_score = (
            direction_score * 0.55
            +
            fast_component * 0.20
            +
            return_component
        )

        ai_score = float(
            np.clip(
                ai_score,
                0,
                100
            )
        )

        probability = (
            row["AI_Probability"]
        )

        if probability >= 0.80:

            strength = "EXTREME"

        elif probability >= 0.70:

            strength = "VERY_STRONG"

        elif probability >= 0.60:

            strength = "STRONG"

        elif probability >= 0.52:

            strength = "POSITIVE"

        else:

            strength = "NEUTRAL"

        final_results.append({

            "Symbol":
                row["Symbol"],

            "Date":
                row["Date"],

            "Close":
                row["Close"],

            "Signal":
                row["Signal"],

            "Strength":
                strength,

            "AI_Probability":
                probability,

            "BUY_Probability":
                row[
                    "BUY_Probability"
                ],

            "SELL_Probability":
                row[
                    "SELL_Probability"
                ],

            "HOLD_Probability":
                row[
                    "HOLD_Probability"
                ],

            "Fast_Score":
                row["Fast_Score"],

            "AI_Predicted_Return":
                expected_return,

            "AI_Score":
                ai_score,
        })

        if idx % 100 == 0:

            elapsed = (
                time.time()
                -
                expected_start
            )

            print(
                f"[AI RETURN] "
                f"{idx:,}/"
                f"{len(top_candidates):,} "
                f"| süre="
                f"{elapsed/60:.1f} dk"
            )

    except Exception:
        continue


# ============================================================
# DİĞER SEMBOLLER
# ============================================================
#
# İlk 1.000 aday dışındaki semboller için expected return
# hesaplanmaz. Ancak tarama sonucunda tutulurlar.
# ============================================================

processed_symbols = {
    x["Symbol"]
    for x in final_results
}


for _, row in preliminary_df.iterrows():

    symbol = row["Symbol"]

    if symbol in processed_symbols:
        continue

    probability = row[
        "AI_Probability"
    ]

    if probability >= 0.80:

        strength = "EXTREME"

    elif probability >= 0.70:

        strength = "VERY_STRONG"

    elif probability >= 0.60:

        strength = "STRONG"

    elif probability >= 0.52:

        strength = "POSITIVE"

    else:

        strength = "NEUTRAL"

    ai_score = float(
        np.clip(
            row["Preliminary_Score"],
            0,
            100
        )
    )

    final_results.append({

        "Symbol":
            symbol,

        "Date":
            row["Date"],

        "Close":
            row["Close"],

        "Signal":
            row["Signal"],

        "Strength":
            strength,

        "AI_Probability":
            probability,

        "BUY_Probability":
            row[
                "BUY_Probability"
            ],

        "SELL_Probability":
            row[
                "SELL_Probability"
            ],

        "HOLD_Probability":
            row[
                "HOLD_Probability"
            ],

        "Fast_Score":
            row["Fast_Score"],

        "AI_Predicted_Return":
            0.0,

        "AI_Score":
            ai_score,
    })


# ============================================================
# RESULT DATAFRAME
# ============================================================

result_df = pd.DataFrame(
    final_results
)

if result_df.empty:

    print(
        "[HATA] Final sonuç oluşmadı."
    )

    raise SystemExit(1)


# ============================================================
# CLEAN
# ============================================================

numeric_cols = (
    result_df
    .select_dtypes(
        include=[np.number]
    )
    .columns
)

result_df[numeric_cols] = (
    result_df[numeric_cols]
    .replace(
        [
            np.inf,
            -np.inf
        ],
        np.nan
    )
)

result_df = result_df.dropna(
    subset=[
        "AI_Score"
    ]
)


# ============================================================
# RANK
# ============================================================

result_df = (
    result_df
    .sort_values(
        [
            "AI_Score",
            "AI_Probability",
            "Fast_Score",
        ],
        ascending=[
            False,
            False,
            False,
        ]
    )
    .reset_index(
        drop=True
    )
)


# ============================================================
# TOP 300
# ============================================================

top_df = (
    result_df
    .head(TOP_N)
    .copy()
)


# ============================================================
# SAVE
# ============================================================

result_df.to_csv(
    SCAN_FILE,
    index=False,
    encoding="utf-8-sig"
)

top_df.to_csv(
    TOP_FILE,
    index=False,
    encoding="utf-8-sig"
)

result_df.head(
    1000
).to_csv(
    LATEST_FILE,
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# MODEL METRICS
# ============================================================

metrics_df = pd.DataFrame([{

    "Model":
        "LEVEL1000_V8_Global_LogisticRegression",

    "Accuracy":
        accuracy,

    "Precision":
        precision,

    "Recall":
        recall,

    "F1":
        f1,

    "Training_Rows":
        len(train_df),

    "Training_Rows_Used":
        len(X_train),

    "Test_Rows":
        len(X_test),

    "Symbols_Total":
        TOTAL_SYMBOLS,

    "Symbols_Usable":
        len(all_data),

    "Symbols_AI":
        len(result_df),

    "Failed_Symbols":
        len(failed_symbols),

    "Expected_Return_Reference":
        len(reference_df),

    "Expected_Return_Candidates":
        EXPECTED_RETURN_CANDIDATES,

    "Forward_Days":
        FORWARD_DAYS,

    "Target_Threshold":
        TARGET_THRESHOLD,

    "Model_C":
        MODEL_C,

    "Model_Time_Seconds":
        model_time,

    "Download_Time_Seconds":
        download_time,

    "Total_Time_Seconds":
        time.time() -
        PROGRAM_START,
}])


metrics_df.to_csv(
    METRICS_FILE,
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# FINAL STATISTICS
# ============================================================

buy_count = int(
    (
        result_df["Signal"]
        == "BUY"
    ).sum()
)

sell_count = int(
    (
        result_df["Signal"]
        == "SELL"
    ).sum()
)

hold_count = int(
    (
        result_df["Signal"]
        == "HOLD"
    ).sum()
)

total_time = (
    time.time()
    -
    PROGRAM_START
)


# ============================================================
# FINAL
# ============================================================

print()
print()
print("=" * 78)
print(" LEVEL 1000 V8 SONUÇ")
print("=" * 78)

print(
    f"Taranan sembol       : "
    f"{TOTAL_SYMBOLS:,}"
)

print(
    f"Verisi bulunan       : "
    f"{len(all_data):,}"
)

print(
    f"AI analiz edilen     : "
    f"{len(result_df):,}"
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
    f"{len(top_df):,}"
)

print(
    f"Başarısız/eksik      : "
    f"{len(failed_symbols):,}"
)

print(
    f"Toplam süre          : "
    f"{total_time/60:.1f} dakika"
)


# ============================================================
# TOP 20
# ============================================================

print()
print("=" * 78)
print(" TOP 20 AI ADAY")
print("=" * 78)
print()


for i, (_, row) in enumerate(
    top_df.head(20).iterrows(),
    start=1
):

    print(
        f"{i:>2}. "
        f"{str(row['Symbol']):<10} "
        f"{str(row['Signal']):<5} "
        f"{str(row['Strength']):<12} "
        f"AI=%"
        f"{row['AI_Probability'] * 100:5.1f} "
        f"Beklenen=%"
        f"{row['AI_Predicted_Return'] * 100:7.2f} "
        f"Fast="
        f"{row['Fast_Score']:7.2f} "
        f"AI="
        f"{row['AI_Score']:7.2f}"
    )


# ============================================================
# DOSYALAR
# ============================================================

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
    f"MODEL    : {METRICS_FILE}"
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


# ============================================================
# RESUME BİLGİSİ
# ============================================================

print()
print("=" * 78)
print(" KALICI DEVAM SİSTEMİ")
print("=" * 78)

print(
    f"Cache sembolü       : "
    f"{len(all_data):,}"
)

print(
    f"Progress tamamlanan : "
    f"{len(completed_symbols):,}"
)

print(
    f"Failed kayıt        : "
    f"{len(failed_symbols):,}"
)

print()
print(
    "Bilgisayar kapanırsa cache verileri korunur."
)

print(
    "Tekrar çalıştırıldığında hazır veriler yeniden indirilmez."
)

print()
print("=" * 78)
print(" V8 TARAMA TAMAMLANDI")
print("=" * 78)
print()