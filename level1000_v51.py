# ============================================================
# LEVEL 1000 V5.1
# GLOBAL THOUSANDS SCANNER - MAX SPEED
# PAPER ONLY - NO REAL ORDERS
# ============================================================

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import time
import re
import io
import os

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor
)


# ============================================================
# AYARLAR
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

SYMBOL_FILE = BASE_DIR / "symbols.txt"

DATA_DIR = BASE_DIR / "level1000_cache"
OUTPUT_DIR = BASE_DIR / "level1000_output"

DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

YEARS = 5
FAST_PERIOD = "1y"
INTERVAL = "1d"

HORIZON = 5
TRAIN_MIN = 252

TOP_N = 2000

# HIZ
DOWNLOAD_WORKERS = 10
AI_WORKERS = max(2, min(8, (os.cpu_count() or 4)))

FAST_BATCH_SIZE = 300

MAX_RETRIES = 2
TIMEOUT = 20

# MODEL
ET_CLASS_TREES = 40
ET_REG_TREES = 40

MAX_TRAIN_ROWS = 1_000_000

# FİLTRE
MIN_PRICE = 1.0
MIN_DOLLAR_VOLUME = 100_000

# PİYASA
MARKET = "SPY"

# PAPER
INITIAL_CAPITAL = 100000.0
COST_BPS = 10

# ============================================================
# OTOMATİK GLOBAL EVREN
# ============================================================

NASDAQ_URL = (
    "https://www.nasdaqtrader.com/"
    "dynamic/SymDir/nasdaqlisted.txt"
)

OTHER_URL = (
    "https://www.nasdaqtrader.com/"
    "dynamic/SymDir/otherlisted.txt"
)


# ============================================================
# YARDIMCI
# ============================================================

def clean_symbol(symbol):

    if not symbol:
        return None

    symbol = str(symbol).strip().upper()

    symbol = symbol.replace("$", "")

    if not symbol:
        return None

    # Yahoo özel dönüşümleri
    symbol = symbol.replace("/", "-")

    # Geçersiz karakter
    if not re.fullmatch(r"[A-Z0-9.\-_^=]+", symbol):
        return None

    return symbol


# ============================================================
# NASDAQ + NYSE/AMEX LİSTESİ
# ============================================================

def download_symbol_universe():

    print()
    print("=" * 70)
    print(" GLOBAL SEMBOL EVRENİ OLUŞTURULUYOR")
    print("=" * 70)

    symbols = set()

    # Kullanıcının verdiği temel hisseler
    manual = [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "GOOGL",
        "META",
        "TSLA",
        "AMD",
        "AVGO",
        "JPM",
    ]

    for s in manual:
        s = clean_symbol(s)
        if s:
            symbols.add(s)

    # NASDAQ
    try:

        import urllib.request

        req = urllib.request.Request(
            NASDAQ_URL,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        raw = urllib.request.urlopen(
            req,
            timeout=20
        ).read().decode(
            "utf-8",
            errors="ignore"
        )

        df = pd.read_csv(
            io.StringIO(raw),
            sep="|"
        )

        if "Symbol" in df.columns:

            for s in df["Symbol"].astype(str):

                s = clean_symbol(s)

                if s:
                    symbols.add(s)

        print(
            f"[OK] NASDAQ sembolleri: {len(symbols):,}"
        )

    except Exception as e:

        print(
            f"[UYARI] NASDAQ listesi alınamadı: {e}"
        )

    # NYSE / AMEX / diğer ABD
    try:

        import urllib.request

        req = urllib.request.Request(
            OTHER_URL,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        raw = urllib.request.urlopen(
            req,
            timeout=20
        ).read().decode(
            "utf-8",
            errors="ignore"
        )

        df = pd.read_csv(
            io.StringIO(raw),
            sep="|"
        )

        if "ACT Symbol" in df.columns:

            for s in df["ACT Symbol"].astype(str):

                s = clean_symbol(s)

                if s:
                    symbols.add(s)

        print(
            f"[OK] NYSE/AMEX/OTHER toplamı: "
            f"{len(symbols):,}"
        )

    except Exception as e:

        print(
            f"[UYARI] NYSE/AMEX listesi alınamadı: {e}"
        )

    symbols = sorted(symbols)

    # Son kontrol
    symbols = [
        s for s in symbols
        if s not in {
            "FILE CREATION TIME",
            "ACT SYMBOL",
            "SYMBOL"
        }
    ]

    print()
    print(
        f"[GLOBAL EVREN] {len(symbols):,} sembol"
    )

    return symbols


# ============================================================
# SYMBOLS.TXT
# ============================================================

def load_symbols():

    existing = []

    if SYMBOL_FILE.exists():

        try:

            text = SYMBOL_FILE.read_text(
                encoding="utf-8",
                errors="ignore"
            )

            parts = re.split(
                r"[\s,;]+",
                text
            )

            for p in parts:

                p = clean_symbol(p)

                if p:
                    existing.append(p)

        except Exception:
            pass

    # Eğer kullanıcı sadece kendi listesini koyduysa
    # yine global listeyi tamamla.
    global_symbols = download_symbol_universe()

    symbols = set(existing)

    symbols.update(global_symbols)

    symbols = sorted(symbols)

    # symbols.txt'yi güncelle
    try:

        SYMBOL_FILE.write_text(
            "\n".join(symbols),
            encoding="utf-8"
        )

        print(
            f"[OK] symbols.txt güncellendi: "
            f"{len(symbols):,}"
        )

    except Exception as e:

        print(
            f"[UYARI] symbols.txt yazılamadı: {e}"
        )

    return symbols


# ============================================================
# DATAFRAME NORMALIZE
# ============================================================

def normalize_dataframe(df):

    if df is None or len(df) == 0:
        return None

    try:

        if isinstance(df.columns, pd.MultiIndex):

            # OHLC seviyesini bul
            names = list(df.columns.names)

            for level in range(df.columns.nlevels):

                vals = [
                    str(x).upper()
                    for x in df.columns.get_level_values(level)
                ]

                if "CLOSE" in vals:

                    try:
                        df = df.copy()
                        df.columns = [
                            str(x).upper()
                            for x in df.columns
                        ]
                    except:
                        pass

                    break

        # Eğer MultiIndex kaldıysa
        if isinstance(df.columns, pd.MultiIndex):

            # ilk seviyeyi kullanmayı dene
            try:

                if "Close" in df.columns.get_level_values(0):

                    df = df.copy()

                    df.columns = [
                        x[0] for x in df.columns
                    ]

                elif "Close" in df.columns.get_level_values(1):

                    df = df.copy()

                    df.columns = [
                        x[1] for x in df.columns
                    ]

            except:
                pass

    except:
        pass

    rename = {}

    for c in df.columns:

        cc = str(c).lower().strip()

        if cc == "open":
            rename[c] = "Open"

        elif cc == "high":
            rename[c] = "High"

        elif cc == "low":
            rename[c] = "Low"

        elif cc == "close":
            rename[c] = "Close"

        elif cc == "adj close":
            rename[c] = "Adj Close"

        elif cc == "volume":
            rename[c] = "Volume"

    df = df.rename(columns=rename)

    required = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume"
    ]

    if not all(
        x in df.columns
        for x in required
    ):
        return None

    df = df[
        required
    ].copy()

    for c in required:

        df[c] = pd.to_numeric(
            df[c],
            errors="coerce"
        )

    df = df.replace(
        [np.inf, -np.inf],
        np.nan
    )

    df = df.dropna(
        subset=[
            "Open",
            "High",
            "Low",
            "Close"
        ]
    )

    if len(df) == 0:
        return None

    df = df[~df.index.duplicated(
        keep="last"
    )]

    return df.sort_index()


# ============================================================
# CACHE
# ============================================================

def cache_path(symbol):

    safe = symbol.replace(
        "^", "_"
    ).replace(
        "=", "_"
    )

    return DATA_DIR / f"{safe}.csv"


def load_cache(symbol):

    path = cache_path(symbol)

    if not path.exists():
        return None

    try:

        df = pd.read_csv(
            path,
            index_col=0,
            parse_dates=True
        )

        df = normalize_dataframe(df)

        if df is not None and len(df) >= TRAIN_MIN:

            return df

    except:
        pass

    return None


def save_cache(symbol, df):

    try:

        df.to_csv(
            cache_path(symbol)
        )

    except:
        pass


# ============================================================
# TEK SEMBOL DATA
# ============================================================

def get_data(symbol):

    cached = load_cache(symbol)

    if cached is not None:
        return cached

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            df = yf.download(
                symbol,
                period=f"{YEARS}y",
                interval=INTERVAL,
                auto_adjust=True,
                progress=False,
                threads=False,
                timeout=TIMEOUT,
                repair=True
            )

            df = normalize_dataframe(df)

            if (
                df is not None
                and len(df) >= TRAIN_MIN
            ):

                save_cache(
                    symbol,
                    df
                )

                return df

        except:
            pass

        time.sleep(
            0.5 * attempt
        )

    return None


# ============================================================
# HIZLI BULK DOWNLOAD
# ============================================================

def bulk_fast_download(symbols):

    print()
    print("=" * 70)
    print(" FAST GLOBAL SCAN")
    print("=" * 70)

    results = {}

    total = len(symbols)

    for start in range(
        0,
        total,
        FAST_BATCH_SIZE
    ):

        batch = symbols[
            start:
            start + FAST_BATCH_SIZE
        ]

        print(
            f"[FAST] "
            f"{min(start + len(batch), total):,}/"
            f"{total:,}"
        )

        try:

            raw = yf.download(
                batch,
                period=FAST_PERIOD,
                interval=INTERVAL,
                auto_adjust=True,
                progress=False,
                threads=True,
                group_by="ticker",
                timeout=TIMEOUT,
                repair=True
            )

            if raw is None or len(raw) == 0:
                continue

            for symbol in batch:

                try:

                    if isinstance(
                        raw.columns,
                        pd.MultiIndex
                    ):

                        found = False
                        df = None

                        # ticker -> OHLC
                        for level in range(
                            raw.columns.nlevels
                        ):

                            values = (
                                raw.columns
                                .get_level_values(level)
                            )

                            if symbol in values:

                                try:

                                    df = raw.xs(
                                        symbol,
                                        axis=1,
                                        level=level
                                    )

                                    found = True
                                    break

                                except:
                                    pass

                        if not found:
                            continue

                    else:

                        df = raw.copy()

                    df = normalize_dataframe(
                        df
                    )

                    if (
                        df is not None
                        and len(df) >= 60
                    ):

                        results[symbol] = df

                except:
                    continue

        except Exception as e:

            print(
                f"[FAST UYARI] {e}"
            )

    return results


# ============================================================
# TEKNİK ÖZELLİKLER
# ============================================================

def rsi(series, period=14):

    delta = series.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = avg_gain / (
        avg_loss + 1e-12
    )

    return 100 - (
        100 / (1 + rs)
    )


def make_features(df, market_df=None):

    x = df.copy()

    close = x["Close"]
    high = x["High"]
    low = x["Low"]
    volume = x["Volume"]

    feat = pd.DataFrame(
        index=x.index
    )

    # RETURNS
    for n in [
        1, 2, 3, 5,
        10, 20, 30,
        60, 120, 200
    ]:

        feat[f"ret_{n}"] = (
            close.pct_change(n)
        )

    # SMA
    for n in [
        5, 10, 20,
        50, 100, 200
    ]:

        sma = close.rolling(
            n
        ).mean()

        feat[f"sma_{n}"] = (
            close / sma - 1
        )

    # EMA
    for n in [
        10, 20, 50
    ]:

        ema = close.ewm(
            span=n,
            adjust=False
        ).mean()

        feat[f"ema_{n}"] = (
            close / ema - 1
        )

    # VOLATILITY
    ret1 = close.pct_change()

    for n in [
        5, 10, 20, 60
    ]:

        feat[f"vol_{n}"] = (
            ret1.rolling(n).std()
        )

    # ATR
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ],
        axis=1
    ).max(axis=1)

    atr = tr.rolling(
        14
    ).mean()

    feat["atr_pct"] = (
        atr / close
    )

    # RSI
    feat["rsi"] = rsi(
        close
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

    feat["macd"] = (
        macd / close
    )

    feat["macd_signal"] = (
        signal / close
    )

    feat["macd_hist"] = (
        (macd - signal) / close
    )

    # BOLLINGER
    mid = close.rolling(
        20
    ).mean()

    std = close.rolling(
        20
    ).std()

    upper = mid + (
        2 * std
    )

    lower = mid - (
        2 * std
    )

    feat["bb_pos"] = (
        (close - lower)
        /
        (upper - lower + 1e-12)
    )

    # STOCHASTIC
    lowest = low.rolling(
        14
    ).min()

    highest = high.rolling(
        14
    ).max()

    feat["stoch_k"] = (
        (close - lowest)
        /
        (highest - lowest + 1e-12)
    )

    # ROC
    for n in [
        10, 20
    ]:

        feat[f"roc_{n}"] = (
            close.pct_change(n)
        )

    # VOLUME
    for n in [
        5, 20, 60
    ]:

        avg = volume.rolling(
            n
        ).mean()

        feat[f"volume_ratio_{n}"] = (
            volume / (avg + 1e-12)
        )

    # PRICE RANGE
    feat["high_distance"] = (
        high / close - 1
    )

    feat["low_distance"] = (
        low / close - 1
    )

    # CANDLE
    rng = (
        high - low
    )

    feat["body"] = (
        (close - x["Open"])
        /
        (rng + 1e-12)
    )

    feat["upper_shadow"] = (
        (high - x[["Open", "Close"]].max(axis=1))
        /
        (rng + 1e-12)
    )

    feat["lower_shadow"] = (
        (x[["Open", "Close"]].min(axis=1) - low)
        /
        (rng + 1e-12)
    )

    feat["range_pct"] = (
        rng / close
    )

    # MARKET
    if market_df is not None:

        try:

            mclose = market_df[
                "Close"
            ].reindex(
                feat.index
            ).ffill()

            for n in [
                5, 20, 50
            ]:

                feat[
                    f"market_ret_{n}"
                ] = mclose.pct_change(n)

        except:
            pass

    # TARGET
    future_return = (
        close.shift(-HORIZON)
        /
        close
        - 1
    )

    feat["future_return"] = (
        future_return
    )

    feat["target"] = np.where(
        future_return.notna(),
        (
            future_return > 0
        ).astype(float),
        np.nan
    )

    feat = feat.replace(
        [np.inf, -np.inf],
        np.nan
    )

    return feat


# ============================================================
# GLOBAL MARKET DATA
# ============================================================

def get_market_data():

    try:

        df = yf.download(
            MARKET,
            period=f"{YEARS}y",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
            timeout=TIMEOUT,
            repair=True
        )

        return normalize_dataframe(
            df
        )

    except:

        return None


# ============================================================
# FAST SCAN
# ============================================================

def calculate_fast_row(
    symbol,
    df
):

    try:

        last = df.iloc[-1]

        price = float(
            last["Close"]
        )

        volume = float(
            last["Volume"]
        )

        dollar_volume = (
            price * volume
        )

        if price < MIN_PRICE:
            return None

        if dollar_volume < MIN_DOLLAR_VOLUME:
            return None

        close = df["Close"]

        r5 = (
            close.iloc[-1]
            /
            close.iloc[-6]
            - 1
        )

        r20 = (
            close.iloc[-1]
            /
            close.iloc[-21]
            - 1
        )

        r60 = (
            close.iloc[-1]
            /
            close.iloc[-61]
            - 1
        )

        sma20 = (
            close.rolling(20)
            .mean()
            .iloc[-1]
        )

        sma50 = (
            close.rolling(50)
            .mean()
            .iloc[-1]
        )

        score = (
            r5 * 0.30
            +
            r20 * 0.35
            +
            r60 * 0.20
            +
            (
                price / sma20 - 1
            ) * 0.10
            +
            (
                price / sma50 - 1
            ) * 0.05
        )

        return {
            "Symbol": symbol,
            "Price": price,
            "DollarVolume": dollar_volume,
            "Return5D": r5,
            "Return20D": r20,
            "Return60D": r60,
            "FastScore": score
        }

    except:

        return None


# ============================================================
# GLOBAL TRAIN DATA
# ============================================================

def build_training_data(
    data_map,
    market_df
):

    print()
    print("=" * 70)
    print(" GLOBAL AI EĞİTİM VERİSİ HAZIRLANIYOR")
    print("=" * 70)

    frames = []

    total = len(data_map)

    for i, (
        symbol,
        df
    ) in enumerate(
        data_map.items(),
        1
    ):

        if i % 250 == 0:

            print(
                f"[FEATURE] "
                f"{i:,}/{total:,}"
            )

        try:

            f = make_features(
                df,
                market_df
            )

            f = f.dropna(
                subset=["target"]
            )

            if len(f) < TRAIN_MIN:
                continue

            # Sonraki future target hariç
            f = f.copy()

            f["Symbol"] = symbol

            frames.append(f)

        except:
            continue

    if not frames:
        return None

    train = pd.concat(
        frames,
        axis=0
    )

    del frames

    train = train.replace(
        [np.inf, -np.inf],
        np.nan
    )

    # Symbol model girdisi değildir
    # Tarih de model girdisi değildir
    feature_cols = [
        c for c in train.columns
        if c not in [
            "target",
            "future_return",
            "Symbol"
        ]
    ]

    train = train.dropna(
        subset=feature_cols
    )

    # RAM kontrolü
    if len(train) > MAX_TRAIN_ROWS:

        train = train.sample(
            MAX_TRAIN_ROWS,
            random_state=42
        )

    print(
        f"[TRAIN ROWS] {len(train):,}"
    )

    print(
        f"[FEATURES] {len(feature_cols)}"
    )

    return train, feature_cols


# ============================================================
# GLOBAL MODEL
# ============================================================

def train_global_models(
    train,
    feature_cols
):

    print()
    print("=" * 70)
    print(" GLOBAL AI EĞİTİMİ")
    print("=" * 70)

    X = train[
        feature_cols
    ].astype(
        np.float32
    )

    y_class = train[
        "target"
    ].astype(
        np.int8
    )

    y_reg = train[
        "future_return"
    ].astype(
        np.float32
    )

    classifier = ExtraTreesClassifier(
        n_estimators=ET_CLASS_TREES,
        max_depth=10,
        min_samples_leaf=5,
        max_features="sqrt",
        n_jobs=-1,
        random_state=42,
        class_weight="balanced"
    )

    regressor = ExtraTreesRegressor(
        n_estimators=ET_REG_TREES,
        max_depth=10,
        min_samples_leaf=5,
        max_features="sqrt",
        n_jobs=-1,
        random_state=42
    )

    print(
        "[AI] Classifier eğitiliyor..."
    )

    classifier.fit(
        X,
        y_class
    )

    print(
        "[AI] Regressor eğitiliyor..."
    )

    regressor.fit(
        X,
        y_reg
    )

    print(
        "[AI] GLOBAL MODEL HAZIR"
    )

    return classifier, regressor


# ============================================================
# TEK SEMBOL AI
# ============================================================

def analyze_symbol(
    symbol,
    df,
    market_df,
    classifier,
    regressor,
    feature_cols
):

    try:

        f = make_features(
            df,
            market_df
        )

        f = f.replace(
            [np.inf, -np.inf],
            np.nan
        )

        latest = f.iloc[-1]

        X = pd.DataFrame(
            [latest[feature_cols].values],
            columns=feature_cols
        )

        X = X.astype(
            np.float32
        )

        if X.isna().any().any():
            return None

        probability = float(
            classifier.predict_proba(X)[0][1]
        )

        predicted_return = float(
            regressor.predict(X)[0]
        )

        if (
            probability >= 0.57
            and predicted_return >= 0.003
        ):

            signal = "BUY"

        elif (
            probability <= 0.43
            and predicted_return <= -0.003
        ):

            signal = "SELL"

        else:

            signal = "HOLD"

        # Güç
        prob_edge = abs(
            probability - 0.50
        ) * 2

        ret_strength = min(
            abs(predicted_return) / 0.05,
            1
        )

        direction_agreement = 1

        if (
            probability > 0.5
            and predicted_return > 0
        ) or (
            probability < 0.5
            and predicted_return < 0
        ):

            direction_agreement = 1

        else:

            direction_agreement = 0.25

        strength = (
            prob_edge * 0.40
            +
            ret_strength * 0.40
            +
            direction_agreement * 0.20
        )

        price = float(
            df["Close"].iloc[-1]
        )

        volume = float(
            df["Volume"].iloc[-1]
        )

        dollar_volume = (
            price * volume
        )

        r20 = float(
            df["Close"].pct_change(20).iloc[-1]
        )

        r60 = float(
            df["Close"].pct_change(60).iloc[-1]
        )

        return {
            "Symbol": symbol,
            "Price": price,
            "Signal": signal,
            "Probability": probability,
            "PredictedReturn5D": predicted_return,
            "Strength": strength,
            "Return20D": r20,
            "Return60D": r60,
            "DollarVolume": dollar_volume,
            "Paper_Status": "PAPER_ONLY",
            "Real_Order": "NO"
        }

    except:
        return None


# ============================================================
# AI PARALEL ANALİZ
# ============================================================

def run_ai_analysis(
    data_map,
    market_df,
    classifier,
    regressor,
    feature_cols
):

    print()
    print("=" * 70)
    print(" GLOBAL AI ANALİZİ")
    print("=" * 70)

    results = []

    total = len(data_map)

    with ThreadPoolExecutor(
        max_workers=AI_WORKERS
    ) as executor:

        futures = {}

        for symbol, df in data_map.items():

            futures[
                executor.submit(
                    analyze_symbol,
                    symbol,
                    df,
                    market_df,
                    classifier,
                    regressor,
                    feature_cols
                )
            ] = symbol

        done = 0

        for future in as_completed(
            futures
        ):

            done += 1

            result = future.result()

            if result is not None:

                results.append(
                    result
                )

            if (
                done % 100 == 0
                or done == total
            ):

                print(
                    f"[AI] "
                    f"{done:,}/{total:,} | "
                    f"başarılı={len(results):,}"
                )

    return results


# ============================================================
# RANKING
# ============================================================

def rank_results(df):

    if df.empty:
        return df

    signal_order = {
        "BUY": 0,
        "SELL": 1,
        "HOLD": 2
    }

    df = df.copy()

    df["SignalOrder"] = (
        df["Signal"]
        .map(signal_order)
        .fillna(3)
    )

    df["RankScore"] = (
        df["Strength"] * 0.45
        +
        df["PredictedReturn5D"].abs() * 4 * 0.30
        +
        df["Return20D"].abs() * 2 * 0.10
        +
        df["Return60D"].abs() * 1 * 0.05
        +
        np.log1p(
            df["DollarVolume"]
        ) / 30 * 0.10
    )

    df = df.sort_values(
        [
            "SignalOrder",
            "RankScore"
        ],
        ascending=[
            True,
            False
        ]
    )

    df["Rank"] = np.arange(
        1,
        len(df) + 1
    )

    return df


# ============================================================
# PAPER SİNYALLER
# ============================================================

def create_paper(df):

    if df.empty:
        return df

    out = df.copy()

    out["Paper_Position"] = np.where(
        out["Signal"] == "BUY",
        1,
        np.where(
            out["Signal"] == "SELL",
            -1,
            0
        )
    )

    out["Theoretical_Capital"] = (
        INITIAL_CAPITAL
    )

    out["Real_Trade"] = False

    out["Real_Order"] = "NO"

    out["Paper_Status"] = "PAPER_ONLY"

    return out


# ============================================================
# KAYDET
# ============================================================

def save_outputs(
    fast_df,
    signals_df
):

    print()
    print("=" * 70)
    print(" DOSYALAR KAYDEDİLİYOR")
    print("=" * 70)

    if fast_df is not None:

        fast_df.to_csv(
            OUTPUT_DIR
            / "level1000_fast_universe.csv",
            index=False
        )

    all_df = signals_df.copy()

    all_df.to_csv(
        OUTPUT_DIR
        / "level1000_signals_all.csv",
        index=False
    )

    top_df = all_df.head(
        TOP_N
    ).copy()

    top_df.to_csv(
        OUTPUT_DIR
        / "level1000_top2000.csv",
        index=False
    )

    # Eski sistem uyumluluğu
    all_df.to_csv(
        OUTPUT_DIR
        / "level1000_latest_signals.csv",
        index=False
    )

    paper = create_paper(
        all_df
    )

    paper.to_csv(
        OUTPUT_DIR
        / "level1000_paper_signals.csv",
        index=False
    )

    # Basit tahmin dosyası
    prediction_cols = [
        "Symbol",
        "Signal",
        "Probability",
        "PredictedReturn5D",
        "Strength",
        "Rank"
    ]

    available = [
        c for c in prediction_cols
        if c in all_df.columns
    ]

    all_df[
        available
    ].to_csv(
        OUTPUT_DIR
        / "level1000_predictions.csv",
        index=False
    )

    print(
        "[OK] Tüm sinyaller:"
    )

    print(
        OUTPUT_DIR
        / "level1000_signals_all.csv"
    )

    print(
        "[OK] Top 2000:"
    )

    print(
        OUTPUT_DIR
        / "level1000_top2000.csv"
    )

    print(
        "[OK] Paper:"
    )

    print(
        OUTPUT_DIR
        / "level1000_paper_signals.csv"
    )


# ============================================================
# ANA PROGRAM
# ============================================================

def main():

    start_time = time.time()

    print()
    print("=" * 70)
    print(" LEVEL 1000 V5.1")
    print(" GLOBAL THOUSANDS SCANNER")
    print(" MAX SPEED / PAPER ONLY")
    print("=" * 70)

    print()
    print("[MODE] GERÇEK PARA : HAYIR")
    print("[MODE] OTOMATİK EMİR: HAYIR")
    print("[MODE] PAPER ONLY   : EVET")

    # --------------------------------------------------------
    # 1. EVREN
    # --------------------------------------------------------

    symbols = load_symbols()

    print()
    print(
        f"[UNIVERSE] "
        f"{len(symbols):,} sembol taranacak"
    )

    # --------------------------------------------------------
    # 2. FAST SCAN
    # --------------------------------------------------------

    fast_map = bulk_fast_download(
        symbols
    )

    fast_rows = []

    for symbol, df in fast_map.items():

        row = calculate_fast_row(
            symbol,
            df
        )

        if row is not None:
            fast_rows.append(row)

    fast_df = pd.DataFrame(
        fast_rows
    )

    if not fast_df.empty:

        fast_df = fast_df.sort_values(
            "FastScore",
            ascending=False
        )

        fast_df.to_csv(
            OUTPUT_DIR
            / "level1000_fast_universe.csv",
            index=False
        )

    print()
    print(
        f"[FAST OK] "
        f"{len(fast_map):,} sembol"
    )

    # --------------------------------------------------------
    # 3. 5 YILLIK DATA
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print(" 5 YILLIK VERİ TOPLAMA")
    print("=" * 70)

    data_map = {}

    total = len(symbols)

    # Cache varsa paralel oku
    with ThreadPoolExecutor(
        max_workers=DOWNLOAD_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                get_data,
                symbol
            ): symbol
            for symbol in symbols
        }

        done = 0

        for future in as_completed(
            futures
        ):

            done += 1

            symbol = futures[
                future
            ]

            try:

                df = future.result()

                if df is not None:

                    data_map[
                        symbol
                    ] = df

            except:
                pass

            if (
                done % 100 == 0
                or done == total
            ):

                print(
                    f"[DATA] "
                    f"{done:,}/{total:,} | "
                    f"veri={len(data_map):,}"
                )

    print()
    print(
        f"[DATA TAMAM] "
        f"{len(data_map):,}"
    )

    if len(data_map) == 0:

        print(
            "[HATA] Hiç veri alınamadı."
        )

        return

    # --------------------------------------------------------
    # 4. MARKET
    # --------------------------------------------------------

    market_df = get_market_data()

    # --------------------------------------------------------
    # 5. GLOBAL TRAIN
    # --------------------------------------------------------

    train_result = build_training_data(
        data_map,
        market_df
    )

    if train_result is None:

        print(
            "[HATA] Eğitim verisi oluşmadı."
        )

        return

    train, feature_cols = (
        train_result
    )

    # --------------------------------------------------------
    # 6. GLOBAL AI
    # --------------------------------------------------------

    classifier, regressor = (
        train_global_models(
            train,
            feature_cols
        )
    )

    # Bellek
    del train

    # --------------------------------------------------------
    # 7. TÜM SEMBOLLER AI
    # --------------------------------------------------------

    signals = run_ai_analysis(
        data_map,
        market_df,
        classifier,
        regressor,
        feature_cols
    )

    signals_df = pd.DataFrame(
        signals
    )

    if signals_df.empty:

        print(
            "[HATA] AI sinyali oluşmadı."
        )

        return

    # --------------------------------------------------------
    # 8. RANK
    # --------------------------------------------------------

    signals_df = rank_results(
        signals_df
    )

    # --------------------------------------------------------
    # 9. KAYDET
    # --------------------------------------------------------

    save_outputs(
        fast_df,
        signals_df
    )

    # --------------------------------------------------------
    # 10. ÖZET
    # --------------------------------------------------------

    elapsed = (
        time.time()
        - start_time
    )

    buy_count = int(
        (
            signals_df["Signal"]
            == "BUY"
        ).sum()
    )

    sell_count = int(
        (
            signals_df["Signal"]
            == "SELL"
        ).sum()
    )

    hold_count = int(
        (
            signals_df["Signal"]
            == "HOLD"
        ).sum()
    )

    print()
    print("=" * 70)
    print(" LEVEL 1000 V5.1 SONUÇ")
    print("=" * 70)

    print(
        f"Taranan evren : "
        f"{len(symbols):,}"
    )

    print(
        f"Verisi bulunan : "
        f"{len(data_map):,}"
    )

    print(
        f"AI analiz      : "
        f"{len(signals_df):,}"
    )

    print(
        f"BUY            : "
        f"{buy_count:,}"
    )

    print(
        f"SELL           : "
        f"{sell_count:,}"
    )

    print(
        f"HOLD           : "
        f"{hold_count:,}"
    )

    print(
        f"TOP {TOP_N:,}        : "
        f"{min(TOP_N, len(signals_df)):,}"
    )

    print(
        f"Süre           : "
        f"{elapsed / 60:.1f} dakika"
    )

    print()
    print(
        "ÇIKTI KLASÖRÜ:"
    )

    print(
        OUTPUT_DIR
    )

    print()
    print("=" * 70)
    print(" TOP 30")
    print("=" * 70)

    display_cols = [
        "Rank",
        "Symbol",
        "Signal",
        "Probability",
        "PredictedReturn5D",
        "Strength",
        "Price"
    ]

    display_cols = [
        c for c in display_cols
        if c in signals_df.columns
    ]

    print(
        signals_df[
            display_cols
        ].head(30).to_string(
            index=False
        )
    )

    print()
    print("=" * 70)
    print(" TAMAMLANDI")
    print("=" * 70)


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
            "Cache ve kaydedilmiş CSV dosyaları korundu."
        )

    except Exception as e:

        print()
        print(
            "[KRİTİK HATA]"
        )

        print(
            repr(e)
        )

        input(
            "\nKapatmak için Enter..."
        )