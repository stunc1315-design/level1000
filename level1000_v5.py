from pathlib import Path
import time
import random
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score
)


# ============================================================
# LEVEL 1000 AI - MACHINE LEARNING SCANNER
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "level1000_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS_FILE = BASE_DIR / "symbols.txt"


# ============================================================
# AYARLAR
# ============================================================

YEARS = 2

# Yahoo rate-limit koruması
BATCH_SIZE = 20
THREADS = 2

BATCH_SLEEP_MIN = 1.5
BATCH_SLEEP_MAX = 3.0

MAX_RETRIES = 3

MIN_ROWS = 220
TOP_N = 300

# Gelecek kaç işlem günü tahmin edilecek?
FORWARD_DAYS = 5

# Sembol başına maksimum eğitim örneği
MAX_TRAIN_ROWS_PER_SYMBOL = 120

# ±0.2% hareketi HOLD kabul ediyoruz
TARGET_THRESHOLD = 0.002

# Eğitim/test oranı
TRAIN_RATIO = 0.80


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


FEATURES = [
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
    "range_pos60"
]


# ============================================================
# SEMBOL YARDIMCILARI
# ============================================================

def normalize_symbol(symbol):

    symbol = str(symbol).strip().upper()

    if not symbol:
        return None

    # Yahoo'da problem çıkarabilen warrant/unit sembolleri
    if "$" in symbol:
        return None

    if symbol.endswith(".W"):
        return None

    if symbol.endswith(".U"):
        return None

    if symbol.endswith(".R"):
        return None

    # BRK.B -> BRK-B
    if "." in symbol:
        symbol = symbol.replace(".", "-")

    return symbol


def load_symbols():

    if not SYMBOLS_FILE.exists():

        print("[UYARI] symbols.txt bulunamadi.")
        print("[INFO] Test listesi kullanilacak.")

        return DEFAULT_SYMBOLS.copy()

    raw = SYMBOLS_FILE.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    symbols = []

    for line in raw.splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        for part in line.split(","):

            symbol = normalize_symbol(part)

            if symbol:
                symbols.append(symbol)

    symbols = list(
        dict.fromkeys(symbols)
    )

    if not symbols:

        print("[UYARI] Gecerli sembol bulunamadi.")
        return DEFAULT_SYMBOLS.copy()

    return symbols


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def add_features(df):

    x = df.copy()

    close = pd.to_numeric(
        x["Close"],
        errors="coerce"
    )

    high = pd.to_numeric(
        x["High"],
        errors="coerce"
    )

    low = pd.to_numeric(
        x["Low"],
        errors="coerce"
    )

    volume = pd.to_numeric(
        x["Volume"],
        errors="coerce"
    )

    # --------------------------------------------------------
    # GETİRİLER
    # --------------------------------------------------------

    x["ret_5"] = close.pct_change(5)

    x["ret_20"] = close.pct_change(20)

    x["ret_60"] = close.pct_change(60)

    # --------------------------------------------------------
    # SMA
    # --------------------------------------------------------

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma100 = close.rolling(100).mean()

    x["dist_sma20"] = (
        close / sma20 - 1
    )

    x["dist_sma50"] = (
        close / sma50 - 1
    )

    x["dist_sma100"] = (
        close / sma100 - 1
    )

    # --------------------------------------------------------
    # VOLATILITY
    # --------------------------------------------------------

    x["volatility20"] = (
        close
        .pct_change()
        .rolling(20)
        .std()
    )

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    volume_mean20 = (
        volume
        .rolling(20)
        .mean()
    )

    x["volume_ratio20"] = (
        volume / volume_mean20
    )

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    previous_close = close.shift(1)

    tr1 = high - low

    tr2 = (
        high - previous_close
    ).abs()

    tr3 = (
        low - previous_close
    ).abs()

    true_range = pd.concat(
        [
            tr1,
            tr2,
            tr3
        ],
        axis=1
    ).max(axis=1)

    x["atr14"] = (
        true_range
        .rolling(14)
        .mean()
    )

    x["atr_pct"] = (
        x["atr14"] / close
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    delta = close.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.rolling(
        14
    ).mean()

    avg_loss = loss.rolling(
        14
    ).mean()

    rs = (
        avg_gain /
        avg_loss.replace(
            0,
            np.nan
        )
    )

    x["rsi14"] = (
        100 -
        (
            100 /
            (1 + rs)
        )
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    macd = ema12 - ema26

    macd_signal = macd.ewm(
        span=9,
        adjust=False
    ).mean()

    x["macd_hist"] = (
        macd -
        macd_signal
    )

    # --------------------------------------------------------
    # RANGE
    # --------------------------------------------------------

    high60 = high.rolling(
        60
    ).max()

    low60 = low.rolling(
        60
    ).min()

    denominator = (
        high60 -
        low60
    )

    x["range_pos60"] = (
        (close - low60) /
        denominator.replace(
            0,
            np.nan
        )
    )

    return x


# ============================================================
# FAST SCORE
# ============================================================

def fast_score(row):

    score = 50.0

    score += (
        5
        if row["ret_5"] > 0
        else -5
    )

    score += (
        8
        if row["ret_20"] > 0
        else -8
    )

    score += (
        10
        if row["ret_60"] > 0
        else -10
    )

    score += (
        5
        if row["dist_sma20"] > 0
        else -5
    )

    score += (
        6
        if row["dist_sma50"] > 0
        else -6
    )

    score += (
        7
        if row["dist_sma100"] > 0
        else -7
    )

    volume_ratio = row[
        "volume_ratio20"
    ]

    if volume_ratio >= 1.50:
        score += 6

    elif volume_ratio >= 1.20:
        score += 4

    elif volume_ratio >= 1.00:
        score += 2

    elif volume_ratio < 0.70:
        score -= 3

    rsi = row["rsi14"]

    if 52 <= rsi <= 68:
        score += 5

    elif 45 <= rsi < 52:
        score += 1

    elif 68 < rsi <= 75:
        score += 2

    elif rsi > 80:
        score -= 7

    elif rsi < 30:
        score -= 6

    score += (
        5
        if row["macd_hist"] > 0
        else -5
    )

    position = row[
        "range_pos60"
    ]

    if position >= 0.80:
        score += 3

    elif position >= 0.60:
        score += 2

    elif position <= 0.20:
        score -= 4

    atr_pct = row["atr_pct"]

    if np.isfinite(atr_pct):

        if atr_pct > 0.15:
            score -= 6

        elif atr_pct > 0.10:
            score -= 2

    return float(
        np.clip(
            score,
            0,
            100
        )
    )


# ============================================================
# YAHOO VERİ İNDİRME
# ============================================================

def download_batch(symbols):

    if not symbols:
        return {}

    clean_symbols = []

    for symbol in symbols:

        normalized = normalize_symbol(
            symbol
        )

        if normalized:
            clean_symbols.append(
                normalized
            )

    clean_symbols = list(
        dict.fromkeys(
            clean_symbols
        )
    )

    if not clean_symbols:
        return {}

    required = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume"
    ]

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            data = yf.download(
                tickers=clean_symbols,
                period=f"{YEARS}y",
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=THREADS,
                group_by="ticker"
            )

            if data is None:
                raise RuntimeError(
                    "Yahoo bos cevap verdi."
                )

            if data.empty:
                raise RuntimeError(
                    "Yahoo bos veri verdi."
                )

            result = {}

            # =================================================
            # TEK SEMBOL
            # =================================================

            if len(clean_symbols) == 1:

                symbol = clean_symbols[0]

                frame = data.copy()

                if not all(
                    col in frame.columns
                    for col in required
                ):
                    return {}

                frame = frame[
                    required
                ].copy()

                frame = (
                    frame
                    .replace(
                        [
                            np.inf,
                            -np.inf
                        ],
                        np.nan
                    )
                    .dropna()
                )

                if len(frame) >= MIN_ROWS:

                    result[symbol] = frame

                return result

            # =================================================
            # ÇOKLU SEMBOL
            # =================================================

            if not isinstance(
                data.columns,
                pd.MultiIndex
            ):

                return result

            level0 = set(
                data.columns
                .get_level_values(0)
            )

            level1 = set(
                data.columns
                .get_level_values(1)
            )

            for symbol in clean_symbols:

                try:

                    if symbol in level0:

                        frame = data[
                            symbol
                        ].copy()

                    elif symbol in level1:

                        frame = data.xs(
                            symbol,
                            axis=1,
                            level=1
                        ).copy()

                    else:

                        continue

                    if not all(
                        col in frame.columns
                        for col in required
                    ):
                        continue

                    frame = frame[
                        required
                    ].copy()

                    frame = (
                        frame
                        .replace(
                            [
                                np.inf,
                                -np.inf
                            ],
                            np.nan
                        )
                        .dropna()
                    )

                    if len(frame) >= MIN_ROWS:

                        result[symbol] = frame

                except Exception:

                    continue

            return result

        except Exception as e:

            error_text = str(e)

            print(
                f"    [YAHOO] "
                f"Deneme {attempt}/{MAX_RETRIES} "
                f"basarisiz: "
                f"{error_text[:160]}"
            )

            if attempt < MAX_RETRIES:

                wait_time = (
                    5 * (2 ** (attempt - 1))
                    + random.uniform(
                        0,
                        2
                    )
                )

                print(
                    f"    [BEKLE] "
                    f"{wait_time:.1f} saniye..."
                )

                time.sleep(
                    wait_time
                )

    return {}


# ============================================================
# TRAINING DATA
# ============================================================

def build_training_data(
    symbol,
    raw
):

    if (
        raw is None
        or raw.empty
        or len(raw) < MIN_ROWS
    ):
        return None

    try:

        data = add_features(
            raw
        )

        # Sayisal kolonlari zorla numeric yap; bozuk/inf degerleri temizle
        for col in FEATURES + ["Close"]:
            data[col] = pd.to_numeric(data[col], errors="coerce")

        # Gelecek 5 günlük getiri
        data[
            "future_return_5d"
        ] = (
            data["Close"]
            .shift(
                -FORWARD_DAYS
            )
            /
            data["Close"]
            - 1
        )

        clean = data.dropna(
            subset=FEATURES + [
                "future_return_5d"
            ]
        ).copy()

        if len(clean) < 20:
            return None

        # Geleceği bilinmeyen son satırlar
        clean = clean.iloc[
            :-FORWARD_DAYS
        ].copy()

        if clean.empty:
            return None

        future_return = clean[
            "future_return_5d"
        ]

        # 1 = BUY
        # 0 = SELL
        # 2 = HOLD

        target = np.where(
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

        clean[
            "Target"
        ] = target

        if len(clean) > MAX_TRAIN_ROWS_PER_SYMBOL:

            clean = clean.tail(
                MAX_TRAIN_ROWS_PER_SYMBOL
            )

        X = (
            clean[FEATURES]
            .replace(
                [
                    np.inf,
                    -np.inf
                ],
                np.nan
            )
            .dropna()
        )

        clean = clean.loc[
            X.index
        ]

        y = clean[
            "Target"
        ].astype(
            int
        )

        if len(X) < 15:
            return None

        return {
            "X": X.values,
            "y": y.values,
            "dates": clean.index,
            "returns": clean[
                "future_return_5d"
            ].values
        }

    except Exception:

        return None


# ============================================================
# LATEST FEATURES
# ============================================================

def get_latest_features(
    symbol,
    raw
):

    try:

        data = add_features(
            raw
        )

        clean = data.dropna(
            subset=FEATURES
        )

        if clean.empty:
            return None

        return clean.iloc[-1]

    except Exception:

        return None


# ============================================================
# MODEL EĞİTİMİ
# ============================================================

def train_model(
    training_sets
):

    if not training_sets:
        return None, {}, None

    X_parts = []
    y_parts = []
    date_parts = []

    for item in training_sets:

        X_parts.append(
            item["X"]
        )

        y_parts.append(
            item["y"]
        )

        date_parts.append(
            np.array(
                item["dates"]
            )
        )

    X = np.vstack(
        X_parts
    )

    y = np.concatenate(
        y_parts
    )

    dates = np.concatenate(
        date_parts
    )

    # --------------------------------------------------------
    # GERÇEK TARİH SIRASI
    # --------------------------------------------------------

    order = np.argsort(
        dates
    )

    X = X[order]
    y = y[order]
    dates = dates[order]

    if len(X) < 300:

        print(
            "[UYARI] Model icin az veri."
        )

        return None, {}, None

    split = int(
        len(X) *
        TRAIN_RATIO
    )

    # Aynı günün örneklerini mümkün olduğunca
    # train/test arasında bölmemek için
    # split'i tarih sınırına taşıyoruz.

    if split >= len(X):
        split = len(X) - 1

    split_date = dates[
        split
    ]

    train_mask = (
        dates <
        split_date
    )

    test_mask = (
        dates >=
        split_date
    )

    X_train = X[
        train_mask
    ]

    y_train = y[
        train_mask
    ]

    X_test = X[
        test_mask
    ]

    y_test = y[
        test_mask
    ]

    if len(X_train) < 100:
        return None, {}, None

    # Eğitim setinde en az 2 sınıf olmalı
    if len(
        np.unique(y_train)
    ) < 2:

        print(
            "[UYARI] Eğitim setinde yeterli sınıf yok."
        )

        return None, {}, None

    # --------------------------------------------------------
    # MODEL
    # --------------------------------------------------------

    model = Pipeline(
        [
            (
                "scaler",
                StandardScaler()
            ),

            (
                "classifier",
                LogisticRegression(
                    max_iter=1000,
                    C=0.5,
                    class_weight="balanced"
                )
            )
        ]
    )

    model.fit(
        X_train,
        y_train
    )

    metrics = {}

    if len(X_test) > 0:

        predictions = model.predict(
            X_test
        )

        metrics[
            "Accuracy"
        ] = float(
            accuracy_score(
                y_test,
                predictions
            )
        )

        metrics[
            "Precision"
        ] = float(
            precision_score(
                y_test,
                predictions,
                average="weighted",
                zero_division=0
            )
        )

        metrics[
            "Recall"
        ] = float(
            recall_score(
                y_test,
                predictions,
                average="weighted",
                zero_division=0
            )
        )

        metrics[
            "F1"
        ] = float(
            f1_score(
                y_test,
                predictions,
                average="weighted",
                zero_division=0
            )
        )

    metrics[
        "Training_Rows"
    ] = int(
        len(X_train)
    )

    metrics[
        "Test_Rows"
    ] = int(
        len(X_test)
    )

    metrics[
        "Train_Start"
    ] = str(
        dates[
            train_mask
        ][0]
    )

    metrics[
        "Train_End"
    ] = str(
        dates[
            train_mask
        ][-1]
    )

    if np.any(test_mask):

        metrics[
            "Test_Start"
        ] = str(
            dates[
                test_mask
            ][0]
        )

        metrics[
            "Test_End"
        ] = str(
            dates[
                test_mask
            ][-1]
        )

    return model, metrics, X


# ============================================================
# MODEL TAHMİNİ
# ============================================================

def model_prediction(
    model,
    latest
):

    if model is None:
        return None

    try:

        values = np.array(
            [
                latest[f]
                for f in FEATURES
            ],
            dtype=float
        ).reshape(
            1,
            -1
        )

        if not np.isfinite(
            values
        ).all():

            return None

        probabilities = (
            model.predict_proba(
                values
            )[0]
        )

        classes = (
            model.named_steps[
                "classifier"
            ].classes_
        )

        probability_map = {
            int(cls): float(prob)
            for cls, prob
            in zip(
                classes,
                probabilities
            )
        }

        buy_prob = probability_map.get(
            1,
            0.0
        )

        sell_prob = probability_map.get(
            0,
            0.0
        )

        hold_prob = probability_map.get(
            2,
            0.0
        )

        probs = {
            "BUY": buy_prob,
            "SELL": sell_prob,
            "HOLD": hold_prob
        }

        signal = max(
            probs,
            key=probs.get
        )

        confidence = probs[
            signal
        ]

        return {
            "signal": signal,
            "confidence": confidence,
            "buy_probability": buy_prob,
            "sell_probability": sell_prob,
            "hold_probability": hold_prob
        }

    except Exception:

        return None


# ============================================================
# TAHMİNİ GETİRİ
# ============================================================

def calculate_expected_return(
    training_sets,
    latest,
    signal
):

    try:

        latest_values = np.array(
            [
                latest[f]
                for f in FEATURES
            ],
            dtype=float
        )

        if not np.isfinite(
            latest_values
        ).all():

            return 0.0

        candidates = []

        # ----------------------------------------------------
        # Feature'ları ölçekle
        # ----------------------------------------------------

        all_x = []

        for item in training_sets:

            if len(item["X"]) > 0:

                all_x.append(
                    item["X"]
                )

        if not all_x:
            return 0.0

        combined_x = np.vstack(
            all_x
        )

        means = np.nanmean(
            combined_x,
            axis=0
        )

        stds = np.nanstd(
            combined_x,
            axis=0
        )

        stds[
            stds < 1e-9
        ] = 1.0

        latest_scaled = (
            latest_values -
            means
        ) / stds

        # ----------------------------------------------------
        # Her eğitim setinden yakın örnekleri bul
        # ----------------------------------------------------

        for item in training_sets:

            X = item["X"]
            y = item["y"]
            returns = item[
                "returns"
            ]

            if len(X) == 0:
                continue

            X_scaled = (
                X -
                means
            ) / stds

            distances = np.mean(
                np.abs(
                    X_scaled -
                    latest_scaled
                ),
                axis=1
            )

            count = min(
                10,
                len(distances)
            )

            indexes = np.argsort(
                distances
            )[:count]

            for idx in indexes:

                target = int(
                    y[idx]
                )

                ret = float(
                    returns[idx]
                )

                if not np.isfinite(
                    ret
                ):
                    continue

                if (
                    signal == "BUY"
                    and target == 1
                ):

                    candidates.append(
                        ret
                    )

                elif (
                    signal == "SELL"
                    and target == 0
                ):

                    candidates.append(
                        -ret
                    )

                elif (
                    signal == "HOLD"
                    and target == 2
                ):

                    candidates.append(
                        0.0
                    )

        if not candidates:
            return 0.0

        values = np.array(
            candidates,
            dtype=float
        )

        values = values[
            np.isfinite(values)
        ]

        if len(values) == 0:
            return 0.0

        # Aşırı uçları sınırla
        if len(values) >= 5:

            lower = np.percentile(
                values,
                10
            )

            upper = np.percentile(
                values,
                90
            )

            values = np.clip(
                values,
                lower,
                upper
            )

        result = float(
            np.median(values)
        )

        # Güvenlik limiti
        result = float(
            np.clip(
                result,
                -0.30,
                0.30
            )
        )

        return result

    except Exception:

        return 0.0


# ============================================================
# ANA PROGRAM
# ============================================================

def main():

    started = time.time()

    print()

    print(
        "=" * 72
    )

    print(
        " LEVEL 1000 AI MACHINE LEARNING SCANNER"
    )

    print(
        "=" * 72
    )

    print(
        "Gercek para     : HAYIR"
    )

    print(
        "Otomatik emir   : HAYIR"
    )

    print(
        "Model           : Logistic Regression"
    )

    print(
        "Hedef           : Gelecek 5 islem gunu"
    )

    print(
        "Olasilik        : Model tahmini"
    )

    print(
        "=" * 72
    )

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

    print()

    rows = []

    training_sets = []

    successful = 0
    failed = 0

    total_batches = (
        len(symbols)
        + BATCH_SIZE
        - 1
    ) // BATCH_SIZE

    # ========================================================
    # VERİ TOPLAMA
    # ========================================================

    for start in range(
        0,
        len(symbols),
        BATCH_SIZE
    ):

        batch = symbols[
            start:
            start + BATCH_SIZE
        ]

        batch_number = (
            start //
            BATCH_SIZE
        ) + 1

        end_number = min(
            start + len(batch),
            len(symbols)
        )

        print(
            f"[BATCH "
            f"{batch_number}/"
            f"{total_batches}] "
            f"{start + 1:,}-"
            f"{end_number:,}"
        )

        downloaded = download_batch(
            batch
        )

        successful += len(
            downloaded
        )

        failed += (
            len(batch)
            -
            len(downloaded)
        )

        # ====================================================
        # SEMBOL ANALİZİ
        # ====================================================

        for symbol, frame in (
            downloaded.items()
        ):

            # ------------------------------------------------
            # Eğitim
            # ------------------------------------------------

            training = build_training_data(
                symbol,
                frame
            )

            if training is not None:

                training_sets.append(
                    training
                )

            # ------------------------------------------------
            # Güncel veri
            # ------------------------------------------------

            latest = get_latest_features(
                symbol,
                frame
            )

            if latest is None:
                continue

            try:

                score = fast_score(
                    latest
                )

                rows.append(
                    {
                        "Ticker": symbol,

                        "Date": str(
                            frame.index[-1]
                        ),

                        "Close": float(
                            latest["Close"]
                        ),

                        "Fast_Score": round(
                            score,
                            2
                        ),

                        "Return_5D": float(
                            latest["ret_5"]
                        ),

                        "Return_20D": float(
                            latest["ret_20"]
                        ),

                        "Return_60D": float(
                            latest["ret_60"]
                        ),

                        "RSI_14": float(
                            latest["rsi14"]
                        ),

                        "Volume_Ratio_20": float(
                            latest[
                                "volume_ratio20"
                            ]
                        ),

                        "ATR_Pct": float(
                            latest[
                                "atr_pct"
                            ]
                        ),

                        "SMA20_Distance": float(
                            latest[
                                "dist_sma20"
                            ]
                        ),

                        "SMA50_Distance": float(
                            latest[
                                "dist_sma50"
                            ]
                        ),

                        "SMA100_Distance": float(
                            latest[
                                "dist_sma100"
                            ]
                        ),

                        "_latest_features": latest
                    }
                )

            except Exception:
                continue

        print(
            f"    veri OK: "
            f"{len(downloaded):,} | "
            f"sonuc: "
            f"{len(rows):,} | "
            f"egitim seti: "
            f"{len(training_sets):,}"
        )

        # ----------------------------------------------------
        # Yahoo'ya nefes aldır
        # ----------------------------------------------------

        if (
            start + BATCH_SIZE
            < len(symbols)
        ):

            sleep_time = random.uniform(
                BATCH_SLEEP_MIN,
                BATCH_SLEEP_MAX
            )

            print(
                f"    [BEKLE] "
                f"{sleep_time:.1f} saniye"
            )

            time.sleep(
                sleep_time
            )

    # ========================================================
    # SONUÇ YOKSA
    # ========================================================

    if not rows:

        print()

        print(
            "[HATA] Kullanilabilir sonuc yok."
        )

        return

    # ========================================================
    # MODEL
    # ========================================================

    print()

    print(
        "=" * 72
    )

    print(
        " MODEL EGITIMI"
    )

    print(
        "=" * 72
    )

    print(
        f"[MODEL] Sembol egitim seti: "
        f"{len(training_sets):,}"
    )

    total_training_rows = sum(
        len(item["X"])
        for item in training_sets
    )

    print(
        f"[MODEL] Toplam egitim ornegi: "
        f"{total_training_rows:,}"
    )

    model, metrics, _ = train_model(
        training_sets
    )

    if model is None:

        print(
            "[UYARI] Model egitilemedi."
        )

    else:

        print(
            f"[MODEL] Accuracy : "
            f"{metrics.get('Accuracy', 0) * 100:.2f}%"
        )

        print(
            f"[MODEL] Precision: "
            f"{metrics.get('Precision', 0) * 100:.2f}%"
        )

        print(
            f"[MODEL] Recall   : "
            f"{metrics.get('Recall', 0) * 100:.2f}%"
        )

        print(
            f"[MODEL] F1       : "
            f"{metrics.get('F1', 0) * 100:.2f}%"
        )

    # ========================================================
    # DATAFRAME
    # ========================================================

    result_df = pd.DataFrame(
        rows
    )

    # _latest_features pandas Series oldugu icin
    # tum DataFrame'e replace uygulamiyoruz.
    numeric_cols = result_df.select_dtypes(
        include=[np.number]
    ).columns

    result_df[numeric_cols] = (
        result_df[numeric_cols]
        .replace(
            [np.inf, -np.inf],
            np.nan
        )
    )

    result_df = (
        result_df
        .dropna(
            subset=["Fast_Score"]
        )
        .sort_values(
            [
                "Fast_Score",
                "Return_20D",
                "Volume_Ratio_20"
            ],
            ascending=[
                False,
                False,
                False
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # FAST RANK
    # ========================================================

    result_df[
        "Rank_Percentile"
    ] = (
        result_df[
            "Fast_Score"
        ]
        .rank(
            method="average",
            pct=True
        )
    )

    # ========================================================
    # FAST SIGNAL
    # ========================================================

    result_df[
        "Fast_Signal"
    ] = np.select(
        [
            result_df[
                "Rank_Percentile"
            ] >= 0.90,

            result_df[
                "Rank_Percentile"
            ] <= 0.10
        ],

        [
            "BUY",
            "SELL"
        ],

        default="HOLD"
    )

    # ========================================================
    # AI TAHMİN
    # ========================================================

    ai_signals = []
    ai_confidences = []

    buy_probs = []
    sell_probs = []
    hold_probs = []

    predicted_returns = []

    for _, row in result_df.iterrows():

        latest = row[
            "_latest_features"
        ]

        prediction = model_prediction(
            model,
            latest
        )

        if prediction is None:

            signal = row[
                "Fast_Signal"
            ]

            confidence = 0.50

            buy_probability = 0.25
            sell_probability = 0.25
            hold_probability = 0.50

        else:

            signal = prediction[
                "signal"
            ]

            confidence = prediction[
                "confidence"
            ]

            buy_probability = prediction[
                "buy_probability"
            ]

            sell_probability = prediction[
                "sell_probability"
            ]

            hold_probability = prediction[
                "hold_probability"
            ]

        expected_return = (
            calculate_expected_return(
                training_sets,
                latest,
                signal
            )
        )

        ai_signals.append(
            signal
        )

        ai_confidences.append(
            confidence
        )

        buy_probs.append(
            buy_probability
        )

        sell_probs.append(
            sell_probability
        )

        hold_probs.append(
            hold_probability
        )

        predicted_returns.append(
            expected_return
        )

    result_df[
        "AI_Signal"
    ] = ai_signals

    result_df[
        "AI_Probability"
    ] = ai_confidences

    result_df[
        "AI_BUY_Probability"
    ] = buy_probs

    result_df[
        "AI_SELL_Probability"
    ] = sell_probs

    result_df[
        "AI_HOLD_Probability"
    ] = hold_probs

    result_df[
        "AI_Predicted_Return"
    ] = predicted_returns

    # ========================================================
    # FINAL SIGNAL
    # ========================================================

    result_df[
        "Signal"
    ] = result_df[
        "AI_Signal"
    ]

    # ========================================================
    # STRENGTH
    # ========================================================

    result_df[
        "Strength"
    ] = np.select(
        [
            result_df[
                "AI_Probability"
            ] >= 0.70,

            result_df[
                "AI_Probability"
            ] >= 0.60,

            result_df[
                "AI_Probability"
            ] >= 0.50
        ],

        [
            "VERY_STRONG",
            "STRONG",
            "POSITIVE"
        ],

        default="NEUTRAL"
    )

    # ========================================================
    # FORMAT
    # ========================================================

    probability_columns = [
        "AI_Probability",
        "AI_BUY_Probability",
        "AI_SELL_Probability",
        "AI_HOLD_Probability"
    ]

    for column in probability_columns:

        result_df[column] = (
            result_df[column]
            .clip(
                0.001,
                0.999
            )
            .round(4)
        )

    result_df[
        "AI_Predicted_Return"
    ] = (
        result_df[
            "AI_Predicted_Return"
        ]
        .clip(
            -0.30,
            0.30
        )
        .round(6)
    )

    # ========================================================
    # GEÇİCİ KOLON
    # ========================================================

    if "_latest_features" in result_df.columns:

        result_df = result_df.drop(
            columns=[
                "_latest_features"
            ]
        )

    # ========================================================
    # DOSYA 1
    # ========================================================

    scan_file = (
        DATA_DIR /
        "level1000_fast_scan.csv"
    )

    result_df.to_csv(
        scan_file,
        index=False
    )

    # ========================================================
    # TOP 300
    # ========================================================

    top_df = (
        result_df
        .sort_values(
            [
                "AI_Probability",
                "Fast_Score"
            ],
            ascending=[
                False,
                False
            ]
        )
        .head(
            TOP_N
        )
        .copy()
    )

    top_file = (
        DATA_DIR /
        "level1000_fast_top.csv"
    )

    top_df.to_csv(
        top_file,
        index=False
    )

    # ========================================================
    # LATEST SIGNALS
    # ========================================================

    latest_columns = [
        "Date",
        "Ticker",
        "Close",
        "AI_Probability",
        "AI_Predicted_Return",
        "Signal",
        "Strength"
    ]

    latest_df = top_df[
        latest_columns
    ].copy()

    latest_file = (
        DATA_DIR /
        "level1000_latest_signals.csv"
    )

    latest_df.to_csv(
        latest_file,
        index=False
    )

    # ========================================================
    # PAPER
    # ========================================================

    paper_df = latest_df.copy()

    paper_df[
        "Paper_Status"
    ] = "PAPER_ONLY"

    paper_df[
        "Real_Order"
    ] = False

    paper_file = (
        DATA_DIR /
        "level1000_paper_signals.csv"
    )

    paper_df.to_csv(
        paper_file,
        index=False
    )

    # ========================================================
    # MODEL METRICS
    # ========================================================

    metrics_df = pd.DataFrame(
        [
            {
                "Model":
                    "LogisticRegression",

                "Target":
                    f"Future_{FORWARD_DAYS}D_Direction",

                "Accuracy":
                    metrics.get(
                        "Accuracy",
                        np.nan
                    ),

                "Precision":
                    metrics.get(
                        "Precision",
                        np.nan
                    ),

                "Recall":
                    metrics.get(
                        "Recall",
                        np.nan
                    ),

                "F1":
                    metrics.get(
                        "F1",
                        np.nan
                    ),

                "Training_Rows":
                    metrics.get(
                        "Training_Rows",
                        0
                    ),

                "Test_Rows":
                    metrics.get(
                        "Test_Rows",
                        0
                    ),

                "Train_Start":
                    metrics.get(
                        "Train_Start",
                        ""
                    ),

                "Train_End":
                    metrics.get(
                        "Train_End",
                        ""
                    ),

                "Test_Start":
                    metrics.get(
                        "Test_Start",
                        ""
                    ),

                "Test_End":
                    metrics.get(
                        "Test_End",
                        ""
                    )
            }
        ]
    )

    metrics_file = (
        DATA_DIR /
        "level1000_model_metrics.csv"
    )

    metrics_df.to_csv(
        metrics_file,
        index=False
    )

    # ========================================================
    # SAYIMLAR
    # ========================================================

    buy_count = int(
        (
            result_df[
                "Signal"
            ] == "BUY"
        ).sum()
    )

    sell_count = int(
        (
            result_df[
                "Signal"
            ] == "SELL"
        ).sum()
    )

    hold_count = int(
        (
            result_df[
                "Signal"
            ] == "HOLD"
        ).sum()
    )

    elapsed = (
        time.time()
        - started
    )

    # ========================================================
    # SONUÇ
    # ========================================================

    print()

    print(
        "=" * 72
    )

    print(
        " SONUC"
    )

    print(
        "=" * 72
    )

    print(
        f"Taranan sembol : "
        f"{len(symbols):,}"
    )

    print(
        f"Verisi alinan : "
        f"{successful:,}"
    )

    print(
        f"Atlanan/hata : "
        f"{failed:,}"
    )

    print(
        f"Analiz edilen : "
        f"{len(result_df):,}"
    )

    print(
        f"BUY : "
        f"{buy_count:,}"
    )

    print(
        f"SELL : "
        f"{sell_count:,}"
    )

    print(
        f"HOLD : "
        f"{hold_count:,}"
    )

    print(
        f"TOP aday : "
        f"{len(top_df):,}"
    )

    print(
        f"Sure : "
        f"{elapsed / 60:.1f} dakika"
    )

    # ========================================================
    # MODEL TEST
    # ========================================================

    print()

    print(
        "=" * 72
    )

    print(
        " MODEL TEST"
    )

    print(
        "=" * 72
    )

    print(
        f"Accuracy : "
        f"{metrics.get('Accuracy', 0) * 100:.2f}%"
    )

    print(
        f"Precision: "
        f"{metrics.get('Precision', 0) * 100:.2f}%"
    )

    print(
        f"Recall   : "
        f"{metrics.get('Recall', 0) * 100:.2f}%"
    )

    print(
        f"F1       : "
        f"{metrics.get('F1', 0) * 100:.2f}%"
    )

    # ========================================================
    # TOP 20
    # ========================================================

    print()

    print(
        "=" * 72
    )

    print(
        " TOP 20 AI"
    )

    print(
        "=" * 72
    )

    display_cols = [
        "Ticker",
        "Signal",
        "Fast_Score",
        "AI_Probability",
        "AI_Predicted_Return"
    ]

    display = (
        top_df
        .head(20)[
            display_cols
        ]
        .copy()
    )

    display[
        "AI_Probability"
    ] = (
        display[
            "AI_Probability"
        ] * 100
    ).round(1)

    display[
        "AI_Predicted_Return"
    ] = (
        display[
            "AI_Predicted_Return"
        ] * 100
    ).round(2)

    print(
        display.to_string(
            index=False
        )
    )

    # ========================================================
    # DOSYALAR
    # ========================================================

    print()

    print(
        "=" * 72
    )

    print(
        " DOSYALAR"
    )

    print(
        "=" * 72
    )

    print(
        "[OK] level1000_fast_scan.csv"
    )

    print(
        "[OK] level1000_fast_top.csv"
    )

    print(
        "[OK] level1000_latest_signals.csv"
    )

    print(
        "[OK] level1000_paper_signals.csv"
    )

    print(
        "[OK] level1000_model_metrics.csv"
    )

    print()

    print(
        "=" * 72
    )

    print(
        " LEVEL 1000 AI TAMAMLANDI"
    )

    print(
        "=" * 72
    )


# ============================================================
# BAŞLAT
# ============================================================

if __name__ == "__main__":
    main()