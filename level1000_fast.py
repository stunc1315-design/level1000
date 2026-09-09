from pathlib import Path
import time
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix
)
from sklearn.preprocessing import StandardScaler


# ============================================================
# LEVEL 1000 AI - V3
# BALANCED BUY / SELL / HOLD
# RANDOM FOREST + BACKTEST
# PAPER ONLY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "level1000_data"
DATA_DIR.mkdir(exist_ok=True)

SYMBOL_FILE = BASE_DIR / "symbols.txt"


# ============================================================
# AYARLAR
# ============================================================

YEARS = 2

BATCH_SIZE = 100
THREADS = 8
MAX_RETRIES = 3

MIN_ROWS = 120

FORWARD_DAYS = 5

# ATR bazli hedef
ATR_TARGET_MULTIPLIER = 0.75

# Eğitim
TRAIN_RATIO = 0.80

# Her sembolden maksimum eğitim satırı
MAX_TRAIN_ROWS_PER_SYMBOL = 100

# Toplam eğitim örneği
MAX_TOTAL_TRAIN_ROWS = 350_000

# Random Forest
N_ESTIMATORS = 140
MAX_DEPTH = 12
MIN_SAMPLES_LEAF = 8
MAX_FEATURES = "sqrt"

RANDOM_STATE = 42

TOP_N = 300
TOP_BUY = 50
TOP_SELL = 50
TOP_WATCH = 50


# ============================================================
# FEATURE
# ============================================================

FEATURE_COLUMNS = [
    "ret_5",
    "ret_20",
    "ret_60",

    "sma20_dist",
    "sma50_dist",
    "sma100_dist",

    "volatility20",
    "volume_ratio20",

    "atr_pct",

    "rsi14",

    "macd_hist",

    "range_position60",

    "momentum_acceleration",

    "trend_strength",

    "high_low_position20"
]


# ============================================================
# DEFAULT
# ============================================================

DEFAULT_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AMD",
    "AVGO",
    "JPM"
]


# ============================================================
# YARDIMCI
# ============================================================

def safe_float(value, default=0.0):

    try:

        if pd.isna(value):
            return default

        return float(value)

    except Exception:

        return default


def print_line():

    print("=" * 72)


# ============================================================
# SYMBOL
# ============================================================

def normalize_symbol(symbol):

    symbol = str(symbol).strip().upper()

    if not symbol:
        return None

    symbol = symbol.replace(".", "-").replace(" ", "")

    if len(symbol) > 15:
        return None

    allowed = set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-_"
    )

    if any(char not in allowed for char in symbol):
        return None

    return symbol


def load_symbols():

    symbols = []

    if SYMBOL_FILE.exists():

        with open(
            SYMBOL_FILE,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:

            for line in f:

                symbol = normalize_symbol(line)

                if symbol:
                    symbols.append(symbol)

    if not symbols:

        symbols = DEFAULT_SYMBOLS.copy()

    return list(dict.fromkeys(symbols))


# ============================================================
# YAHOO DOWNLOAD
# ============================================================

def download_batch(symbols):

    if not symbols:
        return {}

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            data = yf.download(
                tickers=symbols,
                period=f"{YEARS}y",
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=THREADS,
                group_by="column"
            )

            if data is None or data.empty:

                raise ValueError(
                    "Yahoo bos veri dondurdu."
                )

            result = {}

            # Tek sembol
            if len(symbols) == 1:

                symbol = symbols[0]

                df = data.copy()

                if isinstance(
                    df.columns,
                    pd.MultiIndex
                ):

                    df.columns = (
                        df.columns
                        .get_level_values(0)
                    )

                result[symbol] = df

                return result

            # MultiIndex
            if isinstance(
                data.columns,
                pd.MultiIndex
            ):

                level0 = list(
                    data.columns
                    .get_level_values(0)
                )

                level1 = list(
                    data.columns
                    .get_level_values(1)
                )

                if "Close" in level0:

                    for symbol in symbols:

                        try:

                            result[symbol] = (
                                data
                                .xs(
                                    symbol,
                                    axis=1,
                                    level=1
                                )
                                .copy()
                            )

                        except Exception:
                            pass

                elif "Close" in level1:

                    for symbol in symbols:

                        try:

                            result[symbol] = (
                                data
                                .xs(
                                    symbol,
                                    axis=1,
                                    level=0
                                )
                                .copy()
                            )

                        except Exception:
                            pass

            return result

        except Exception as e:

            print(
                f"[UYARI] Batch hata "
                f"{attempt}/{MAX_RETRIES}: {e}"
            )

            if attempt < MAX_RETRIES:

                time.sleep(
                    min(10, attempt * 3)
                )

    return {}


# ============================================================
# DATA CLEAN
# ============================================================

def clean_dataframe(df):

    if df is None or df.empty:
        return None

    df = df.copy()

    if isinstance(
        df.columns,
        pd.MultiIndex
    ):

        try:

            df.columns = (
                df.columns
                .get_level_values(0)
            )

        except Exception:
            pass

    required = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume"
    ]

    for col in required:

        if col not in df.columns:
            return None

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = (
        df[required]
        .replace(
            [np.inf, -np.inf],
            np.nan
        )
        .dropna()
    )

    df = (
        df[
            ~df.index.duplicated(
                keep="last"
            )
        ]
        .sort_index()
    )

    if len(df) < MIN_ROWS:
        return None

    return df


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    series,
    period=14
):

    delta = series.diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(
        period
    ).mean()

    avg_loss = loss.rolling(
        period
    ).mean()

    rs = (
        avg_gain /
        avg_loss.replace(
            0,
            np.nan
        )
    )

    return 100 - (
        100 / (1 + rs)
    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    df,
    period=14
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
            tr3
        ],
        axis=1
    ).max(axis=1)

    return tr.rolling(
        period
    ).mean()


# ============================================================
# FEATURES
# ============================================================

def build_features(df):

    df = df.copy()

    close = df["Close"]

    volume = df["Volume"]

    # Momentum
    df["ret_5"] = (
        close.pct_change(5)
    )

    df["ret_20"] = (
        close.pct_change(20)
    )

    df["ret_60"] = (
        close.pct_change(60)
    )

    # Moving averages
    sma20 = close.rolling(20).mean()

    sma50 = close.rolling(50).mean()

    sma100 = close.rolling(100).mean()

    df["sma20_dist"] = (
        close / sma20 - 1
    )

    df["sma50_dist"] = (
        close / sma50 - 1
    )

    df["sma100_dist"] = (
        close / sma100 - 1
    )

    # Volatility
    df["volatility20"] = (
        close
        .pct_change()
        .rolling(20)
        .std()
    )

    # Volume
    volume_ma20 = (
        volume.rolling(20).mean()
    )

    df["volume_ratio20"] = (
        volume /
        volume_ma20.replace(
            0,
            np.nan
        )
    )

    # ATR
    atr = calculate_atr(
        df,
        14
    )

    df["atr_pct"] = (
        atr / close
    )

    # RSI
    df["rsi14"] = calculate_rsi(
        close,
        14
    )

    # MACD
    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    macd = ema12 - ema26

    signal = macd.ewm(
        span=9,
        adjust=False
    ).mean()

    df["macd_hist"] = (
        macd - signal
    )

    # Range
    low60 = close.rolling(
        60
    ).min()

    high60 = close.rolling(
        60
    ).max()

    df["range_position60"] = (
        (close - low60) /
        (high60 - low60)
        .replace(0, np.nan)
    )

    # Momentum acceleration
    df["momentum_acceleration"] = (
        df["ret_5"] -
        df["ret_20"] / 4
    )

    # Trend strength
    df["trend_strength"] = (
        df["sma20_dist"] +
        df["sma50_dist"] +
        df["sma100_dist"]
    )

    # 20-day position
    low20 = close.rolling(
        20
    ).min()

    high20 = close.rolling(
        20
    ).max()

    df["high_low_position20"] = (
        (close - low20) /
        (high20 - low20)
        .replace(0, np.nan)
    )

    return df


# ============================================================
# TARGET
# ============================================================

def build_target(df):

    df = df.copy()

    future_return = (
        df["Close"]
        .shift(-FORWARD_DAYS)
        /
        df["Close"]
        - 1
    )

    df["future_return"] = (
        future_return
    )

    # Volatiliteye göre dinamik eşik
    threshold = (
        df["atr_pct"] *
        ATR_TARGET_MULTIPLIER
    )

    threshold = threshold.clip(
        lower=0.002,
        upper=0.03
    )

    df["Target"] = 1

    df.loc[
        future_return > threshold,
        "Target"
    ] = 2

    df.loc[
        future_return < -threshold,
        "Target"
    ] = 0

    df.loc[
        future_return.isna(),
        "Target"
    ] = np.nan

    return df


# ============================================================
# PREPARE
# ============================================================

def prepare_symbol(
    symbol,
    raw_df
):

    df = clean_dataframe(
        raw_df
    )

    if df is None:
        return None

    df = build_features(df)

    df = build_target(df)

    df["Ticker"] = symbol

    df["Date"] = df.index

    df = (
        df
        .replace(
            [np.inf, -np.inf],
            np.nan
        )
        .dropna(
            subset=FEATURE_COLUMNS
        )
    )

    if len(df) < MIN_ROWS:
        return None

    return df


# ============================================================
# FAST SCORE
# ============================================================

def fast_score(row):

    score = 50.0

    ret5 = safe_float(
        row.get("ret_5")
    )

    ret20 = safe_float(
        row.get("ret_20")
    )

    ret60 = safe_float(
        row.get("ret_60")
    )

    score += np.clip(
        ret5 * 100,
        -10,
        10
    )

    score += np.clip(
        ret20 * 50,
        -10,
        10
    )

    score += np.clip(
        ret60 * 30,
        -10,
        10
    )

    score += np.clip(
        safe_float(
            row.get(
                "sma20_dist"
            )
        ) * 100,
        -5,
        5
    )

    score += np.clip(
        safe_float(
            row.get(
                "sma50_dist"
            )
        ) * 70,
        -5,
        5
    )

    volume = safe_float(
        row.get(
            "volume_ratio20"
        ),
        1
    )

    if volume > 1.5:
        score += 5

    elif volume > 1.2:
        score += 3

    elif volume < 0.7:
        score -= 3

    rsi = safe_float(
        row.get("rsi14"),
        50
    )

    if 50 <= rsi <= 70:
        score += 5

    elif 70 < rsi <= 80:
        score += 1

    elif rsi > 80:
        score -= 4

    elif 30 <= rsi < 50:
        score -= 2

    elif rsi < 30:
        score += 2

    macd = safe_float(
        row.get(
            "macd_hist"
        )
    )

    close = max(
        abs(
            safe_float(
                row.get(
                    "Close"
                ),
                1
            )
        ),
        1
    )

    score += np.clip(
        macd / close * 1000,
        -5,
        5
    )

    position = safe_float(
        row.get(
            "range_position60"
        ),
        0.5
    )

    if position > 0.80:
        score += 4

    elif position > 0.60:
        score += 2

    elif position < 0.20:
        score -= 2

    return float(
        np.clip(
            score,
            0,
            100
        )
    )


# ============================================================
# TRAIN DATA
# ============================================================

def create_training_data(
    symbol_dfs
):

    parts = []

    for symbol, df in symbol_dfs.items():

        temp = (
            df
            .dropna(
                subset=
                FEATURE_COLUMNS +
                ["Target"]
            )
            .copy()
        )

        if temp.empty:
            continue

        if len(temp) > MAX_TRAIN_ROWS_PER_SYMBOL:

            temp = temp.tail(
                MAX_TRAIN_ROWS_PER_SYMBOL
            )

        parts.append(temp)

    if not parts:
        return None

    data = pd.concat(
        parts,
        ignore_index=True
    )

    data["Target"] = (
        data["Target"]
        .astype(int)
    )

    data = (
        data
        .sort_values("Date")
        .reset_index(drop=True)
    )

    # Sınıf dengeleme
    print("[AI] Sinif dagilimi:")

    counts = (
        data["Target"]
        .value_counts()
        .sort_index()
    )

    for cls, count in counts.items():

        name = {
            0: "SELL",
            1: "HOLD",
            2: "BUY"
        }.get(cls, str(cls))

        print(
            f"   {name:<5}: {count:,}"
        )

    # Büyük veri ise örnekle
    if len(data) > MAX_TOTAL_TRAIN_ROWS:

        rng = np.random.RandomState(
            RANDOM_STATE
        )

        sampled_parts = []

        for cls in [0, 1, 2]:

            class_data = data[
                data["Target"] == cls
            ]

            if class_data.empty:
                continue

            n = min(
                len(class_data),
                MAX_TOTAL_TRAIN_ROWS // 3
            )

            sampled_parts.append(
                class_data.sample(
                    n=n,
                    random_state=rng
                )
            )

        data = pd.concat(
            sampled_parts,
            ignore_index=True
        )

        data = (
            data
            .sort_values("Date")
            .reset_index(drop=True)
        )

    return data


# ============================================================
# MODEL
# ============================================================

def train_model(
    training_data
):

    if training_data is None:
        return None, {}

    X = (
        training_data[
            FEATURE_COLUMNS
        ]
        .copy()
    )

    y = (
        training_data[
            "Target"
        ]
        .copy()
    )

    X = (
        X
        .replace(
            [np.inf, -np.inf],
            np.nan
        )
        .fillna(0)
    )

    if len(X) < 300:
        return None, {}

    if y.nunique() < 3:
        return None, {}

    split = int(
        len(X) *
        TRAIN_RATIO
    )

    X_train = X.iloc[:split]

    X_test = X.iloc[split:]

    y_train = y.iloc[:split]

    y_test = y.iloc[split:]

    if y_train.nunique() < 3:
        return None, {}

    print(
        f"[AI] Train: {len(X_train):,}"
    )

    print(
        f"[AI] Test : {len(X_test):,}"
    )

    # Ölçekleme
    scaler = StandardScaler()

    X_train_scaled = (
        scaler.fit_transform(
            X_train
        )
    )

    X_test_scaled = (
        scaler.transform(
            X_test
        )
    )

    print(
        "[AI] Random Forest egitiliyor..."
    )

    model = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        max_depth=MAX_DEPTH,
        min_samples_leaf=MIN_SAMPLES_LEAF,
        max_features=MAX_FEATURES,
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=RANDOM_STATE
    )

    model.fit(
        X_train_scaled,
        y_train
    )

    predictions = (
        model.predict(
            X_test_scaled
        )
    )

    accuracy = accuracy_score(
        y_test,
        predictions
    )

    precision = precision_score(
        y_test,
        predictions,
        average="weighted",
        zero_division=0
    )

    recall = recall_score(
        y_test,
        predictions,
        average="weighted",
        zero_division=0
    )

    f1 = f1_score(
        y_test,
        predictions,
        average="weighted",
        zero_division=0
    )

    cm = confusion_matrix(
        y_test,
        predictions,
        labels=[0, 1, 2]
    )

    metrics = {
        "Accuracy": accuracy,
        "Precision": precision,
        "Recall": recall,
        "F1": f1,
        "Train_Rows": len(X_train),
        "Test_Rows": len(X_test),
        "SELL_Actual": int(cm[0].sum()),
        "HOLD_Actual": int(cm[1].sum()),
        "BUY_Actual": int(cm[2].sum())
    }

    return (
        (model, scaler),
        metrics
    )


# ============================================================
# PREDICTION
# ============================================================

def model_prediction(
    model_bundle,
    feature_row
):

    if model_bundle is None:

        return (
            "HOLD",
            0.0,
            {
                "BUY": 0.0,
                "HOLD": 0.0,
                "SELL": 0.0
            }
        )

    model, scaler = model_bundle

    values = [
        safe_float(
            feature_row.get(col)
        )
        for col in FEATURE_COLUMNS
    ]

    X = pd.DataFrame(
        [values],
        columns=FEATURE_COLUMNS
    )

    X = X.replace(
        [np.inf, -np.inf],
        np.nan
    ).fillna(0)

    try:

        X_scaled = (
            scaler.transform(X)
        )

        probabilities = (
            model.predict_proba(
                X_scaled
            )[0]
        )

        classes = (
            model.classes_
        )

        probs = {
            "BUY": 0.0,
            "HOLD": 0.0,
            "SELL": 0.0
        }

        for cls, prob in zip(
            classes,
            probabilities
        ):

            if cls == 2:
                probs["BUY"] = float(prob)

            elif cls == 1:
                probs["HOLD"] = float(prob)

            elif cls == 0:
                probs["SELL"] = float(prob)

        signal = max(
            probs,
            key=probs.get
        )

        return (
            signal,
            probs[signal],
            probs
        )

    except Exception:

        return (
            "HOLD",
            0.0,
            {
                "BUY": 0.0,
                "HOLD": 0.0,
                "SELL": 0.0
            }
        )


# ============================================================
# EXPECTED RETURN
# ============================================================

def expected_return(
    df,
    latest
):

    valid = (
        df
        .dropna(
            subset=
            FEATURE_COLUMNS +
            ["future_return"]
        )
    )

    if valid.empty:
        return 0.0

    target = np.array([
        safe_float(
            latest.get(col)
        )
        for col in FEATURE_COLUMNS
    ])

    matrix = (
        valid[
            FEATURE_COLUMNS
        ]
        .astype(float)
        .values
    )

    mean = np.nanmean(
        matrix,
        axis=0
    )

    std = np.nanstd(
        matrix,
        axis=0
    )

    std[
        std == 0
    ] = 1

    target_norm = (
        target - mean
    ) / std

    matrix_norm = (
        matrix - mean
    ) / std

    distance = np.linalg.norm(
        matrix_norm -
        target_norm,
        axis=1
    )

    k = min(
        15,
        len(valid)
    )

    nearest = (
        np.argsort(
            distance
        )[:k]
    )

    return safe_float(
        valid.iloc[
            nearest
        ]["future_return"].mean()
    )


# ============================================================
# SCORE
# ============================================================

def calculate_scores(
    signal,
    probs,
    fast,
    expected
):

    buy_prob = (
        safe_float(
            probs.get("BUY")
        ) * 100
    )

    sell_prob = (
        safe_float(
            probs.get("SELL")
        ) * 100
    )

    hold_prob = (
        safe_float(
            probs.get("HOLD")
        ) * 100
    )

    expected_pct = (
        safe_float(expected) * 100
    )

    # BUY
    buy_score = (
        buy_prob * 0.55
        +
        fast * 0.20
        +
        np.clip(
            expected_pct * 5,
            -20,
            20
        ) * 0.25
    )

    # SELL
    sell_score = (
        sell_prob * 0.55
        +
        (100 - fast) * 0.20
        +
        np.clip(
            -expected_pct * 5,
            -20,
            20
        ) * 0.25
    )

    # WATCH
    watch_score = (
        max(
            buy_prob,
            sell_prob
        ) * 0.50
        +
        abs(
            fast - 50
        ) * 0.25
        +
        abs(
            expected_pct
        ) * 2
    )

    return (
        float(np.clip(
            buy_score,
            0,
            100
        )),
        float(np.clip(
            sell_score,
            0,
            100
        )),
        float(np.clip(
            watch_score,
            0,
            100
        ))
    )


# ============================================================
# ANALYZE
# ============================================================

def analyze(
    symbol_dfs,
    model_bundle
):

    results = []

    total = len(
        symbol_dfs
    )

    for i, (
        symbol,
        df
    ) in enumerate(
        symbol_dfs.items(),
        1
    ):

        try:

            latest = df.iloc[-1]

            fast = fast_score(
                latest
            )

            features = {
                col: latest.get(col)
                for col in FEATURE_COLUMNS
            }

            signal, probability, probs = (
                model_prediction(
                    model_bundle,
                    features
                )
            )

            exp_return = (
                expected_return(
                    df,
                    latest
                )
            )

            buy_score, sell_score, watch_score = (
                calculate_scores(
                    signal,
                    probs,
                    fast,
                    exp_return
                )
            )

            # Nihai durum
            if (
                probs["BUY"] >= probs["SELL"]
                and
                probs["BUY"] >= probs["HOLD"]
                and
                buy_score >= 55
            ):

                final_signal = "BUY"

            elif (
                probs["SELL"] >= probs["BUY"]
                and
                probs["SELL"] >= probs["HOLD"]
                and
                sell_score >= 55
            ):

                final_signal = "SELL"

            else:

                final_signal = "WATCH"

            results.append({

                "Ticker":
                    symbol,

                "Date":
                    latest.get(
                        "Date",
                        latest.name
                    ),

                "Close":
                    safe_float(
                        latest.get(
                            "Close"
                        )
                    ),

                "Signal":
                    final_signal,

                "Model_Signal":
                    signal,

                "AI_Probability":
                    probability,

                "BUY_Probability":
                    probs["BUY"],

                "HOLD_Probability":
                    probs["HOLD"],

                "SELL_Probability":
                    probs["SELL"],

                "Fast_Score":
                    fast,

                "Expected_Return_5D":
                    exp_return,

                "Expected_Return_Pct":
                    exp_return * 100,

                "BUY_Score":
                    buy_score,

                "SELL_Score":
                    sell_score,

                "WATCH_Score":
                    watch_score,

                "RSI14":
                    safe_float(
                        latest.get(
                            "rsi14"
                        )
                    ),

                "Return_5D":
                    safe_float(
                        latest.get(
                            "ret_5"
                        )
                    ) * 100,

                "Return_20D":
                    safe_float(
                        latest.get(
                            "ret_20"
                        )
                    ) * 100,

                "Volume_Ratio":
                    safe_float(
                        latest.get(
                            "volume_ratio20"
                        )
                    ),

                "ATR_Pct":
                    safe_float(
                        latest.get(
                            "atr_pct"
                        )
                    ) * 100,

                "Paper_Status":
                    "PAPER_ONLY",

                "Real_Order":
                    False
            })

        except Exception:
            continue

        if i % 500 == 0:

            print(
                f"[AI] Analiz: "
                f"{i:,}/{total:,}"
            )

    return pd.DataFrame(
        results
    )


# ============================================================
# MAIN
# ============================================================

def main():

    start_time = time.time()

    print_line()

    print(
        " LEVEL 1000 AI V3"
    )

    print(
        " BALANCED BUY / SELL / HOLD"
    )

    print_line()

    print(
        "Gercek para     : HAYIR"
    )

    print(
        "Otomatik emir   : HAYIR"
    )

    print(
        "Model           : Random Forest"
    )

    print(
        "Hedef           : Gelecek 5 islem gunu"
    )

    print(
        "Target          : ATR bazli"
    )

    print(
        "Backtest        : VAR"
    )

    print_line()

    symbols = load_symbols()

    print(
        f"[LISTE] Toplam sembol: "
        f"{len(symbols):,}"
    )

    print(
        f"[SETUP] Batch: "
        f"{BATCH_SIZE}"
    )

    print(
        f"[SETUP] Thread: "
        f"{THREADS}"
    )

    print_line()

    # ========================================================
    # DOWNLOAD
    # ========================================================

    symbol_dfs = {}

    total = len(symbols)

    total_batches = (
        total +
        BATCH_SIZE -
        1
    ) // BATCH_SIZE

    for start in range(
        0,
        total,
        BATCH_SIZE
    ):

        batch = symbols[
            start:
            start + BATCH_SIZE
        ]

        batch_no = (
            start //
            BATCH_SIZE
        ) + 1

        end_no = min(
            start +
            BATCH_SIZE,
            total
        )

        print(
            f"[BATCH {batch_no}/{total_batches}] "
            f"{start + 1}-{end_no}"
        )

        downloaded = (
            download_batch(
                batch
            )
        )

        for symbol in batch:

            raw = downloaded.get(
                symbol
            )

            if raw is None:
                continue

            prepared = (
                prepare_symbol(
                    symbol,
                    raw
                )
            )

            if prepared is not None:

                symbol_dfs[
                    symbol
                ] = prepared

        print(
            f"   [OK] Hazir: "
            f"{len(symbol_dfs):,}"
        )

    print_line()

    print(
        f"[VERI] Kullanilabilir: "
        f"{len(symbol_dfs):,}"
    )

    if not symbol_dfs:

        print(
            "[HATA] Veri yok."
        )

        return

    # ========================================================
    # TRAIN
    # ========================================================

    print(
        "[AI] Training data hazirlaniyor..."
    )

    training_data = (
        create_training_data(
            symbol_dfs
        )
    )

    if training_data is None:

        print(
            "[HATA] Training data yok."
        )

        return

    print(
        f"[AI] Training rows: "
        f"{len(training_data):,}"
    )

    model_bundle, metrics = (
        train_model(
            training_data
        )
    )

    if model_bundle is None:

        print(
            "[HATA] Model egitilemedi."
        )

        return

    # ========================================================
    # MODEL
    # ========================================================

    print_line()

    print(
        "[MODEL BACKTEST]"
    )

    print_line()

    print(
        f"Accuracy  : "
        f"{metrics['Accuracy']:.4f}"
    )

    print(
        f"Precision : "
        f"{metrics['Precision']:.4f}"
    )

    print(
        f"Recall    : "
        f"{metrics['Recall']:.4f}"
    )

    print(
        f"F1        : "
        f"{metrics['F1']:.4f}"
    )

    print(
        f"Train     : "
        f"{metrics['Train_Rows']:,}"
    )

    print(
        f"Test      : "
        f"{metrics['Test_Rows']:,}"
    )

    print_line()

    # ========================================================
    # ANALYZE
    # ========================================================

    print(
        "[AI] Semboller analiz ediliyor..."
    )

    result_df = analyze(
        symbol_dfs,
        model_bundle
    )

    if result_df.empty:

        print(
            "[HATA] Sonuc yok."
        )

        return

    # ========================================================
    # TOP BUY
    # ========================================================

    buy_df = (
        result_df[
            result_df["Signal"] == "BUY"
        ]
        .sort_values(
            [
                "BUY_Score",
                "BUY_Probability",
                "Expected_Return_Pct"
            ],
            ascending=False
        )
        .head(TOP_BUY)
        .copy()
    )

    # ========================================================
    # TOP SELL
    # ========================================================

    sell_df = (
        result_df[
            result_df["Signal"] == "SELL"
        ]
        .sort_values(
            [
                "SELL_Score",
                "SELL_Probability",
                "Expected_Return_Pct"
            ],
            ascending=False
        )
        .head(TOP_SELL)
        .copy()
    )

    # ========================================================
    # WATCH
    # ========================================================

    watch_df = (
        result_df[
            result_df["Signal"] == "WATCH"
        ]
        .sort_values(
            [
                "WATCH_Score",
                "AI_Probability"
            ],
            ascending=False
        )
        .head(TOP_WATCH)
        .copy()
    )

    # ========================================================
    # GENERAL TOP
    # ========================================================

    ranked_df = result_df.copy()

    ranked_df["Final_Score"] = np.where(
        ranked_df["Signal"] == "BUY",
        ranked_df["BUY_Score"],
        np.where(
            ranked_df["Signal"] == "SELL",
            ranked_df["SELL_Score"],
            ranked_df["WATCH_Score"]
        )
    )

    ranked_df = (
        ranked_df
        .sort_values(
            [
                "Final_Score",
                "AI_Probability"
            ],
            ascending=False
        )
        .reset_index(drop=True)
    )

    top_df = (
        ranked_df
        .head(TOP_N)
        .copy()
    )

    # ========================================================
    # SAVE
    # ========================================================

    scan_file = (
        DATA_DIR /
        "level1000_v3_scan.csv"
    )

    top_file = (
        DATA_DIR /
        "level1000_v3_top.csv"
    )

    buy_file = (
        DATA_DIR /
        "level1000_v3_BUY.csv"
    )

    sell_file = (
        DATA_DIR /
        "level1000_v3_SELL.csv"
    )

    watch_file = (
        DATA_DIR /
        "level1000_v3_WATCH.csv"
    )

    metrics_file = (
        DATA_DIR /
        "level1000_v3_model_metrics.csv"
    )

    ranked_df.to_csv(
        scan_file,
        index=False,
        encoding="utf-8-sig"
    )

    top_df.to_csv(
        top_file,
        index=False,
        encoding="utf-8-sig"
    )

    buy_df.to_csv(
        buy_file,
        index=False,
        encoding="utf-8-sig"
    )

    sell_df.to_csv(
        sell_file,
        index=False,
        encoding="utf-8-sig"
    )

    watch_df.to_csv(
        watch_file,
        index=False,
        encoding="utf-8-sig"
    )

    metrics_output = pd.DataFrame(
        [{
            **metrics,
            "Analyzed":
                len(result_df),
            "BUY_Count":
                len(buy_df),
            "SELL_Count":
                len(sell_df),
            "WATCH_Count":
                len(watch_df),
            "Paper_Status":
                "PAPER_ONLY",
            "Real_Order":
                False
        }]
    )

    metrics_output.to_csv(
        metrics_file,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # TOP BUY
    # ========================================================

    print_line()

    print(
        " TOP BUY"
    )

    print_line()

    if buy_df.empty:

        print(
            "BUY adayi bulunamadi."
        )

    else:

        for _, row in (
            buy_df.head(20).iterrows()
        ):

            print(
                f"{str(row['Ticker']):<8} "
                f"BUY "
                f"BUY={safe_float(row['BUY_Probability'])*100:6.2f}% "
                f"FAST={safe_float(row['Fast_Score']):6.2f} "
                f"EXP={safe_float(row['Expected_Return_Pct']):+7.2f}% "
                f"SCORE={safe_float(row['BUY_Score']):6.2f}"
            )

    # ========================================================
    # TOP SELL
    # ========================================================

    print_line()

    print(
        " TOP SELL"
    )

    print_line()

    if sell_df.empty:

        print(
            "SELL adayi bulunamadi."
        )

    else:

        for _, row in (
            sell_df.head(20).iterrows()
        ):

            print(
                f"{str(row['Ticker']):<8} "
                f"SELL "
                f"SELL={safe_float(row['SELL_Probability'])*100:6.2f}% "
                f"FAST={safe_float(row['Fast_Score']):6.2f} "
                f"EXP={safe_float(row['Expected_Return_Pct']):+7.2f}% "
                f"SCORE={safe_float(row['SELL_Score']):6.2f}"
            )

    # ========================================================
    # TOP WATCH
    # ========================================================

    print_line()

    print(
        " TOP WATCH"
    )

    print_line()

    for _, row in (
        watch_df.head(10).iterrows()
    ):

        print(
            f"{str(row['Ticker']):<8} "
            f"WATCH "
            f"AI={safe_float(row['AI_Probability'])*100:6.2f}% "
            f"FAST={safe_float(row['Fast_Score']):6.2f} "
            f"EXP={safe_float(row['Expected_Return_Pct']):+7.2f}%"
        )

    # ========================================================
    # FINAL
    # ========================================================

    elapsed = (
        time.time() -
        start_time
    )

    print_line()

    print(
        " SONUC"
    )

    print_line()

    print(
        f"Taranan        : "
        f"{len(symbols):,}"
    )

    print(
        f"Verisi alinan  : "
        f"{len(symbol_dfs):,}"
    )

    print(
        f"Analiz edilen  : "
        f"{len(result_df):,}"
    )

    print(
        f"BUY            : "
        f"{len(buy_df):,}"
    )

    print(
        f"SELL           : "
        f"{len(sell_df):,}"
    )

    print(
        f"WATCH          : "
        f"{len(watch_df):,}"
    )

    print(
        f"TOP            : "
        f"{len(top_df):,}"
    )

    print(
        f"Sure           : "
        f"{elapsed / 60:.1f} dakika"
    )

    print_line()

    print(
        "[DOSYA]"
    )

    print(
        scan_file
    )

    print(
        top_file
    )

    print(
        buy_file
    )

    print(
        sell_file
    )

    print(
        watch_file
    )

    print(
        metrics_file
    )

    print_line()

    print(
        "PAPER ONLY - GERCEK EMIR GONDERILMEZ"
    )

    print_line()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()