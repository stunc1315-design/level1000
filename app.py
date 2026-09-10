# ============================================================
# LEVEL 1000 AI - WEB APP
# FULL APP
# LIVE PRICE + AUTH + PLAN + SIGNALS + PAPER + ADMIN
# YAHOO 429 KORUMALI
# ============================================================

from pathlib import Path
from datetime import datetime, timezone
import os
import secrets
import subprocess
import sys
import threading
import sqlite3
import time
import math
import warnings

warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf

from fastapi import (
    FastAPI,
    Request,
    Depends,
    HTTPException,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel

from pwdlib import PasswordHash

import jwt


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "level1000_data"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

LEVEL1000_FILE = BASE_DIR / "level1000.py"

DB_FILE = DATA_DIR / "level1000_users.db"

PAPER_SIGNALS = (
    DATA_DIR /
    "level1000_paper_signals.csv"
)


DATA_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="LEVEL 1000 AI",
    version="10.0"
)


if STATIC_DIR.exists():

    app.mount(
        "/static",
        StaticFiles(
            directory=str(STATIC_DIR)
        ),
        name="static"
    )


templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR)
)


# ============================================================
# SECURITY
# ============================================================

SECRET_KEY = os.environ.get(
    "LEVEL1000_SECRET_KEY"
)

if not SECRET_KEY:

    SECRET_KEY = secrets.token_urlsafe(
        48
    )


ALGORITHM = "HS256"

password_hash = PasswordHash.recommended()


# ============================================================
# PLANLAR
# ============================================================

PLANS = {

    "FREE": {

        "name": "FREE",

        "level": 1,

        "display_limit": 20,

        "scan_limit": 3,

        "backtest": False,

        "paper": False,

        "advanced_ai": False,

        "all_signals": False,
    },

    "PRO": {

        "name": "PRO",

        "level": 2,

        "display_limit": 100,

        "scan_limit": 30,

        "backtest": True,

        "paper": True,

        "advanced_ai": True,

        "all_signals": False,
    },

    "MAX PRO": {

        "name": "MAX PRO",

        "level": 3,

        "display_limit": 300,

        "scan_limit": 999999,

        "backtest": True,

        "paper": True,

        "advanced_ai": True,

        "all_signals": True,
    },
}


MIN_SIGNAL_SCORE = 0


# ============================================================
# YAHOO CANLI FİYAT AYARLARI
# ============================================================

# 429 azaltmak için 30 yerine 120 saniye cache.
LIVE_PRICE_CACHE_SECONDS = 120

LIVE_INTERVAL = "1m"
LIVE_PERIOD = "1d"

# Aynı anda yalnızca tek Yahoo sorgusu.
LIVE_DOWNLOAD_LOCK = threading.Lock()

# Genel cooldown.
LIVE_LAST_DOWNLOAD_TIME = 0.0

# Cache.
live_price_cache = {}

live_price_cache_lock = threading.Lock()


# ============================================================
# DATABASE
# ============================================================

def get_db():

    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            email TEXT UNIQUE NOT NULL,

            password_hash TEXT NOT NULL,

            plan TEXT DEFAULT 'FREE',

            is_admin INTEGER DEFAULT 0,

            scan_count INTEGER DEFAULT 0,

            created_at TEXT NOT NULL

        )
        """
    )

    conn.commit()

    conn.close()


init_db()


# ============================================================
# MODELLER
# ============================================================

class RegisterRequest(BaseModel):

    name: str

    email: str

    password: str


class LoginRequest(BaseModel):

    email: str

    password: str


# ============================================================
# PLAN YARDIMCILARI
# ============================================================

def normalize_plan_name(plan):

    plan = str(
        plan or "FREE"
    ).strip().upper()

    if plan in (
        "MAX",
        "MAXPRO",
        "MAX-PRO",
        "MAX_PRO"
    ):

        return "MAX PRO"

    if plan == "PRO":

        return "PRO"

    return "FREE"


def get_plan_config(user):

    plan = normalize_plan_name(
        user["plan"]
    )

    return PLANS.get(
        plan,
        PLANS["FREE"]
    )


# ============================================================
# USER DICT
# ============================================================

def user_dict(row):

    return {

        "id": int(
            row["id"]
        ),

        "name": row["name"],

        "email": row["email"],

        "plan": normalize_plan_name(
            row["plan"]
        ),

        "is_admin": bool(
            row["is_admin"]
        ),

        "scan_count": int(
            row["scan_count"]
        ),

        "created_at":
            row["created_at"],
    }


# ============================================================
# JWT
# ============================================================

def create_token(user):

    payload = {

        "sub": str(
            user["id"]
        ),

        "email":
            user["email"],

        "iat": int(
            time.time()
        ),

        "exp": int(
            time.time()
        ) + 60 * 60 * 24 * 30,
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def get_token_from_request(request):

    auth = request.headers.get(
        "Authorization",
        ""
    )

    if auth.startswith(
        "Bearer "
    ):

        return auth[7:].strip()

    token = request.cookies.get(
        "access_token"
    )

    return token


# ============================================================
# CURRENT USER
# ============================================================

async def get_current_user(
    request: Request
):

    token = get_token_from_request(
        request
    )

    if not token:

        raise HTTPException(
            status_code=401,
            detail="Giriş yapmanız gerekiyor."
        )

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[
                ALGORITHM
            ]
        )

        user_id = int(
            payload.get("sub")
        )

    except Exception:

        raise HTTPException(
            status_code=401,
            detail="Oturum geçersiz veya süresi dolmuş."
        )

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    if not row:

        raise HTTPException(
            status_code=401,
            detail="Kullanıcı bulunamadı."
        )

    return user_dict(row)


# ============================================================
# PLAN KONTROL
# ============================================================

def require_plan(required_plan):

    required_plan = normalize_plan_name(
        required_plan
    )

    async def dependency(
        user=Depends(get_current_user)
    ):

        current = get_plan_config(
            user
        )

        required = PLANS.get(
            required_plan,
            PLANS["FREE"]
        )

        if bool(user["is_admin"]):

            return user

        if current["level"] < required["level"]:

            raise HTTPException(
                status_code=403,
                detail=(
                    f"Bu özellik {required_plan} "
                    f"planı gerektiriyor."
                )
            )

        return user

    return dependency


async def require_admin(
    user=Depends(get_current_user)
):

    if not bool(
        user["is_admin"]
    ):

        raise HTTPException(
            status_code=403,
            detail="Admin yetkisi gerekiyor."
        )

    return user


# ============================================================
# CSV
# ============================================================

def dataframe_to_records(df):

    if df is None or df.empty:

        return []

    result = df.copy()

    result = result.where(
        pd.notna(result),
        None
    )

    return result.to_dict(
        orient="records"
    )


# ============================================================
# SIGNAL DOSYASI BUL
# ============================================================

def find_signal_file():

    candidates = [

        DATA_DIR /
        "level1000_latest_signals.csv",

        DATA_DIR /
        "level1000_v10_latest.csv",

        DATA_DIR /
        "level1000_latest.csv",

        DATA_DIR /
        "level1000_predictions.csv",

        BASE_DIR /
        "level1000_latest_signals.csv",

        BASE_DIR /
        "level1000_v10_latest.csv",

    ]

    for path in candidates:

        if not path.exists():

            continue

        try:

            df = pd.read_csv(
                path,
                low_memory=False
            )

            if not df.empty:

                return path, df

        except Exception:

            continue

    return None, pd.DataFrame()


# ============================================================
# SIGNAL NORMALIZE
# ============================================================

def normalize_signal_dataframe(df):

    if df is None:

        return pd.DataFrame()

    if df.empty:

        return df.copy()

    result = df.copy()

    rename_map = {}

    for col in result.columns:

        key = str(
            col
        ).strip()

        low = key.lower()

        if low in (
            "symbol",
            "ticker",
            "code"
        ):

            rename_map[col] = "Ticker"

        elif low in (
            "signal",
            "action"
        ):

            rename_map[col] = "Signal"

        elif low in (
            "ai_probability",
            "probability",
            "confidence",
            "confidence_pct"
        ):

            rename_map[col] = "AI_Probability"

        elif low in (
            "ai_predicted_return",
            "predicted_return",
            "expected_return"
        ):

            rename_map[col] = (
                "AI_Predicted_Return"
            )

        elif low in (
            "date",
            "datetime",
            "timestamp"
        ):

            rename_map[col] = "Date"

        elif low in (
            "price",
            "close"
        ):

            # Eski CSV fiyatı daha sonra
            # canlı fiyat tarafından
            # değiştirilecek.
            if "Price" not in result.columns:

                rename_map[col] = "Old_Price"

    if rename_map:

        result = result.rename(
            columns=rename_map
        )

    if "Ticker" not in result.columns:

        result["Ticker"] = "-"

    if "Signal" not in result.columns:

        result["Signal"] = "HOLD"

    if "AI_Probability" not in result.columns:

        result["AI_Probability"] = 0.0

    if "AI_Predicted_Return" not in result.columns:

        result["AI_Predicted_Return"] = 0.0

    if "Date" not in result.columns:

        result["Date"] = "-"

    result["Ticker"] = (
        result["Ticker"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    result["Signal"] = (
        result["Signal"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    result["Signal"] = result[
        "Signal"
    ].replace(
        {
            "AL": "BUY",
            "SAT": "SELL",
            "BEKLE": "HOLD",
        }
    )

    result["AI_Probability"] = pd.to_numeric(
        result["AI_Probability"],
        errors="coerce"
    ).fillna(0)

    result["AI_Predicted_Return"] = pd.to_numeric(
        result["AI_Predicted_Return"],
        errors="coerce"
    ).fillna(0)

    return result


# ============================================================
# DISPLAY FILTER
# ============================================================

def prepare_display_dataframe(
    df,
    limit
):

    if df is None or df.empty:

        return pd.DataFrame()

    work = df.copy()

    # Öncelik:
    # BUY > SELL > HOLD
    order_map = {

        "BUY": 0,

        "SELL": 1,

        "HOLD": 2,
    }

    work["_order"] = (
        work["Signal"]
        .map(order_map)
        .fillna(9)
    )

    work["_score_sort"] = pd.to_numeric(
        work["AI_Probability"],
        errors="coerce"
    ).fillna(0)

    # Güçlü sinyaller.
    strong = work[
        work["Signal"].isin(
            [
                "BUY",
                "SELL"
            ]
        )
    ].copy()

    if strong.empty:

        strong = work.copy()

    strong = strong.sort_values(
        [
            "_order",
            "_score_sort"
        ],
        ascending=[
            True,
            False
        ]
    )

    try:

        limit = int(limit)

    except Exception:

        limit = 20

    if limit < 1:

        limit = 20

    strong = strong.head(
        limit
    )

    strong = strong.drop(
        columns=[
            "_order",
            "_score_sort"
        ],
        errors="ignore"
    )

    return strong


# ============================================================
# FLOAT
# ============================================================

def _clean_float(value):

    try:

        value = float(value)

        if not math.isfinite(
            value
        ):

            return None

        return value

    except Exception:

        return None


# ============================================================
# TIME
# ============================================================

def _utc_now():

    return datetime.now(
        timezone.utc
    )


def _turkey_time_string():

    try:

        from zoneinfo import ZoneInfo

        dt = datetime.now(
            ZoneInfo(
                "Europe/Istanbul"
            )
        )

        return dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    except Exception:

        return datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )


# ============================================================
# YAHOO FRAME HELPERS
# ============================================================

def _extract_ticker_from_download(
    frame,
    symbol
):

    if frame is None or frame.empty:

        return pd.DataFrame()

    result = frame

    if isinstance(
        result.columns,
        pd.MultiIndex
    ):

        # yfinance:
        # (Close, AAPL)
        # veya
        # (AAPL, Close)

        try:

            if symbol in result.columns.get_level_values(0):

                result = result[symbol]

            elif symbol in result.columns.get_level_values(1):

                result = result.xs(
                    symbol,
                    axis=1,
                    level=1
                )

        except Exception:

            pass

    return result


def _get_close_series(
    frame
):

    if frame is None or frame.empty:

        return None

    if isinstance(
        frame.columns,
        pd.MultiIndex
    ):

        try:

            frame = frame.copy()

            frame.columns = [
                str(
                    c[-1]
                    if isinstance(c, tuple)
                    else c
                )
                for c in frame.columns
            ]

        except Exception:

            return None

    for name in (
        "Close",
        "close",
        "Adj Close",
        "adj close",
    ):

        if name in frame.columns:

            series = pd.to_numeric(
                frame[name],
                errors="coerce"
            ).dropna()

            if not series.empty:

                return series

    return None


def _get_last_price_from_frame(
    frame
):

    series = _get_close_series(
        frame
    )

    if series is None:

        return None

    try:

        return float(
            series.iloc[-1]
        )

    except Exception:

        return None


def _get_fast_info_price(
    symbol
):

    try:

        ticker = yf.Ticker(
            symbol
        )

        info = ticker.fast_info

        for key in (
            "last_price",
            "lastPrice",
            "regularMarketPrice",
        ):

            value = info.get(
                key
            )

            value = _clean_float(
                value
            )

            if value is not None:

                return value

    except Exception:

        pass

    return None


# ============================================================
# YAHOO DOWNLOAD
# ============================================================

def _download_live_prices(
    symbols
):

    global LIVE_LAST_DOWNLOAD_TIME

    symbols = list(
        dict.fromkeys(
            str(s)
            .strip()
            .upper()
            for s in symbols
            if str(s).strip()
        )
    )

    if not symbols:

        return {}

    now = time.time()

    # Genel cooldown.
    # Arka arkaya endpoint çağrılarında
    # Yahoo'ya tekrar gitme.
    if (
        now - LIVE_LAST_DOWNLOAD_TIME
        < 2.0
    ):

        return {}

    with LIVE_DOWNLOAD_LOCK:

        now = time.time()

        if (
            now - LIVE_LAST_DOWNLOAD_TIME
            < 2.0
        ):

            return {}

        LIVE_LAST_DOWNLOAD_TIME = now

        results = {}

        utc_now = _utc_now()

        # ====================================================
        # 1M TEK BATCH
        # ====================================================

        try:

            frame = yf.download(
                tickers=symbols,
                period=LIVE_PERIOD,
                interval=LIVE_INTERVAL,
                auto_adjust=False,
                progress=False,
                threads=False,
                group_by="column",
            )

            if (
                frame is not None
                and not frame.empty
            ):

                for symbol in symbols:

                    try:

                        ticker_frame = (
                            _extract_ticker_from_download(
                                frame,
                                symbol
                            )
                        )

                        price = (
                            _get_last_price_from_frame(
                                ticker_frame
                            )
                        )

                        if price is not None:

                            results[symbol] = {

                                "price":
                                    price,

                                "previous_close":
                                    None,

                                "change":
                                    None,

                                "change_percent":
                                    None,

                                "status":
                                    "LIVE",

                                "source":
                                    "Yahoo Finance / yfinance 1m",

                                "updated_at_utc":
                                    utc_now.isoformat(),

                                "updated_at_tr":
                                    _turkey_time_string(),
                            }

                    except Exception:

                        continue

        except Exception as exc:

            print(
                "[YAHOO 1M UYARI]",
                str(exc)
            )

        # ====================================================
        # GÜNLÜK ÖNCEKİ KAPANIŞ
        # ====================================================

        missing_previous = [
            symbol
            for symbol in results
            if results[symbol].get(
                "previous_close"
            ) is None
        ]

        if missing_previous:

            try:

                daily = yf.download(
                    tickers=missing_previous,
                    period="5d",
                    interval="1d",
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                    group_by="column",
                )

                if (
                    daily is not None
                    and not daily.empty
                ):

                    for symbol in missing_previous:

                        try:

                            ticker_frame = (
                                _extract_ticker_from_download(
                                    daily,
                                    symbol
                                )
                            )

                            close_series = (
                                _get_close_series(
                                    ticker_frame
                                )
                            )

                            if (
                                close_series is None
                                or len(close_series) < 2
                            ):

                                continue

                            previous_close = float(
                                close_series.iloc[-2]
                            )

                            price = results[
                                symbol
                            ]["price"]

                            if (
                                previous_close > 0
                                and price is not None
                            ):

                                change = (
                                    price
                                    - previous_close
                                )

                                change_percent = (
                                    change
                                    / previous_close
                                    * 100
                                )

                                results[
                                    symbol
                                ][
                                    "previous_close"
                                ] = previous_close

                                results[
                                    symbol
                                ][
                                    "change"
                                ] = change

                                results[
                                    symbol
                                ][
                                    "change_percent"
                                ] = (
                                    change_percent
                                )

                        except Exception:

                            continue

            except Exception as exc:

                print(
                    "[YAHOO DAILY UYARI]",
                    str(exc)
                )

        # ====================================================
        # FAST_INFO FALLBACK
        # ====================================================

        # Sadece eksik kalanlarda.
        missing = [
            symbol
            for symbol in symbols
            if symbol not in results
        ]

        # 429'u azaltmak için çok fazla
        # fallback yapmıyoruz.
        if missing:

            for symbol in missing[:10]:

                try:

                    price = (
                        _get_fast_info_price(
                            symbol
                        )
                    )

                    if price is not None:

                        results[symbol] = {

                            "price":
                                price,

                            "previous_close":
                                None,

                            "change":
                                None,

                            "change_percent":
                                None,

                            "status":
                                "DELAYED",

                            "source":
                                "Yahoo Finance / yfinance fast_info",

                            "updated_at_utc":
                                utc_now.isoformat(),

                            "updated_at_tr":
                                _turkey_time_string(),
                        }

                except Exception:

                    continue

        return results


# ============================================================
# CACHE
# ============================================================

def get_live_prices(
    symbols
):

    symbols = list(
        dict.fromkeys(
            str(s)
            .strip()
            .upper()
            for s in symbols
            if str(s).strip()
        )
    )

    if not symbols:

        return {}

    now = time.time()

    output = {}

    missing = []

    # ========================================================
    # CACHE
    # ========================================================

    with live_price_cache_lock:

        for symbol in symbols:

            item = live_price_cache.get(
                symbol
            )

            if not item:

                missing.append(
                    symbol
                )

                continue

            cached_at = float(
                item.get(
                    "_cached_at",
                    0
                )
            )

            if (
                now - cached_at
                <= LIVE_PRICE_CACHE_SECONDS
            ):

                output[symbol] = {
                    k: v
                    for k, v in item.items()
                    if k != "_cached_at"
                }

            else:

                missing.append(
                    symbol
                )

    # ========================================================
    # YENİ VERİ
    # ========================================================

    if missing:

        fresh = _download_live_prices(
            missing
        )

        with live_price_cache_lock:

            for symbol, item in fresh.items():

                item_copy = dict(
                    item
                )

                item_copy[
                    "_cached_at"
                ] = time.time()

                live_price_cache[
                    symbol
                ] = item_copy

                output[symbol] = dict(
                    item
                )

    # ========================================================
    # CACHE'DE OLMAYANLAR
    # ========================================================

    for symbol in symbols:

        if symbol not in output:

            output[symbol] = {

                "price": None,

                "previous_close": None,

                "change": None,

                "change_percent": None,

                "status":
                    "UNAVAILABLE",

                "source":
                    "Yahoo Finance / yfinance",

                "updated_at_utc":
                    None,

                "updated_at_tr":
                    None,
            }

    return output


# ============================================================
# DATAFRAME'E CANLI FİYAT
# ============================================================

def apply_live_prices_to_dataframe(
    df
):

    if df is None or df.empty:

        return (
            df.copy()
            if df is not None
            else pd.DataFrame(),
            {
                "live_count": 0,
                "unavailable_count": 0,
                "total_count": 0,
                "updated_at_utc": None,
                "updated_at_tr": None,
            }
        )

    work = df.copy()

    symbols = (
        work["Ticker"]
        .astype(str)
        .str.strip()
        .str.upper()
        .tolist()
    )

    prices = get_live_prices(
        symbols
    )

    live_count = 0
    unavailable_count = 0

    updated_utc = []
    updated_tr = []

    price_values = []
    change_values = []
    status_values = []
    source_values = []

    for symbol in symbols:

        item = prices.get(
            symbol,
            {}
        )

        price = _clean_float(
            item.get("price")
        )

        change = _clean_float(
            item.get("change_percent")
        )

        status = item.get(
            "status",
            "UNAVAILABLE"
        )

        source = item.get(
            "source",
            "Yahoo Finance / yfinance"
        )

        if price is not None:

            live_count += 1

        else:

            unavailable_count += 1

        price_values.append(
            price
        )

        change_values.append(
            change
        )

        status_values.append(
            status
        )

        source_values.append(
            source
        )

        updated_utc.append(
            item.get(
                "updated_at_utc"
            )
        )

        updated_tr.append(
            item.get(
                "updated_at_tr"
            )
        )

    # ========================================================
    # ÖNEMLİ:
    # ESKİ CSV FİYATINA DÖNME.
    # CANLI VERİ YOKSA NONE.
    # ========================================================

    work["Price"] = price_values

    work["Daily_Change_Percent"] = (
        change_values
    )

    work["Price_Status"] = (
        status_values
    )

    work["Price_Source"] = (
        source_values
    )

    work["Price_Updated_UTC"] = (
        updated_utc
    )

    work["Price_Updated_TR"] = (
        updated_tr
    )

    latest_utc = next(
        (
            x
            for x in updated_utc
            if x
        ),
        None
    )

    latest_tr = next(
        (
            x
            for x in updated_tr
            if x
        ),
        None
    )

    meta = {

        "live_count":
            live_count,

        "unavailable_count":
            unavailable_count,

        "total_count":
            len(symbols),

        "updated_at_utc":
            latest_utc,

        "updated_at_tr":
            latest_tr,
    }

    return work, meta


# ============================================================
# ANA SAYFA
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
async def home(
    request: Request
):

    index_file = (
        TEMPLATES_DIR /
        "index.html"
    )

    if index_file.exists():

        return templates.TemplateResponse(
            request=request,
            name="index.html"
        )

    return HTMLResponse(
        """
        <html>
        <head>
        <title>LEVEL 1000 AI</title>
        </head>
        <body>
        <h1>LEVEL 1000 AI</h1>
        <p>Web uygulaması aktif.</p>
        </body>
        </html>
        """
    )


# ============================================================
# PUBLIC SAYFALAR
# ============================================================

def simple_page(
    title,
    text
):

    return HTMLResponse(
        f"""
        <!DOCTYPE html>
        <html lang="tr">
        <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 900px;
            margin: 40px auto;
            padding: 20px;
            background: #0b1020;
            color: #fff;
        }}
        h1 {{
            margin-bottom: 20px;
        }}
        p {{
            line-height: 1.7;
            color: #cbd5e1;
        }}
        </style>
        </head>
        <body>
        <h1>{title}</h1>
        <p>{text}</p>
        </body>
        </html>
        """
    )


@app.get(
    "/about",
    response_class=HTMLResponse
)
async def about():

    return simple_page(
        "LEVEL 1000 AI",
        "Yapay zeka destekli piyasa araştırma ve sinyal analiz platformu."
    )


@app.get(
    "/guide",
    response_class=HTMLResponse
)
async def guide():

    return simple_page(
        "Kullanım Rehberi",
        "Sistem sinyal verilerini analiz eder. BUY, SELL ve HOLD sonuçları yatırım tavsiyesi değildir."
    )


@app.get(
    "/risk",
    response_class=HTMLResponse
)
async def risk():

    return simple_page(
        "Risk Bildirimi",
        "LEVEL 1000 AI finansal danışmanlık veya yatırım garantisi sunmaz. Geçmiş performans gelecekteki sonuçların garantisi değildir."
    )


@app.get(
    "/privacy",
    response_class=HTMLResponse
)
async def privacy():

    return simple_page(
        "Gizlilik",
        "Kullanıcı hesap bilgileri uygulamanın kullanıcı veritabanında tutulur."
    )


@app.get(
    "/cookies",
    response_class=HTMLResponse
)
async def cookies():

    return simple_page(
        "Çerezler",
        "Oturum yönetimi için gerekli teknik çerezler kullanılabilir."
    )


@app.get(
    "/terms",
    response_class=HTMLResponse
)
async def terms():

    return simple_page(
        "Kullanım Şartları",
        "LEVEL 1000 AI yalnızca araştırma ve eğitim amaçlı kullanılmalıdır."
    )


@app.get(
    "/contact",
    response_class=HTMLResponse
)
async def contact():

    return simple_page(
        "İletişim",
        "LEVEL 1000 AI destek kanallarından uygulama yöneticisine ulaşabilirsiniz."
    )


# ============================================================
# REGISTER
# ============================================================

@app.post("/api/register")
async def register(
    data: RegisterRequest
):

    name = str(
        data.name
    ).strip()

    email = str(
        data.email
    ).strip().lower()

    password = str(
        data.password
    )

    if len(name) < 2:

        raise HTTPException(
            status_code=400,
            detail="Ad soyad gerekli."
        )

    if "@" not in email:

        raise HTTPException(
            status_code=400,
            detail="Geçerli e-posta girin."
        )

    if len(password) < 6:

        raise HTTPException(
            status_code=400,
            detail="Şifre en az 6 karakter olmalıdır."
        )

    conn = get_db()

    existing = conn.execute(
        """
        SELECT id
        FROM users
        WHERE email = ?
        """,
        (email,)
    ).fetchone()

    if existing:

        conn.close()

        raise HTTPException(
            status_code=400,
            detail="Bu e-posta zaten kayıtlı."
        )

    hashed = password_hash.hash(
        password
    )

    created = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    cursor = conn.execute(
        """
        INSERT INTO users
        (
            name,
            email,
            password_hash,
            plan,
            is_admin,
            scan_count,
            created_at
        )
        VALUES
        (?, ?, ?, 'FREE', 0, 0, ?)
        """,
        (
            name,
            email,
            hashed,
            created
        )
    )

    conn.commit()

    user_id = cursor.lastrowid

    row = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    user = user_dict(
        row
    )

    token = create_token(
        user
    )

    return {

        "ok": True,

        "message":
            "Kayıt başarılı.",

        "token":
            token,

        "user":
            user,
    }


# ============================================================
# LOGIN
# ============================================================

@app.post("/api/login")
async def login(
    data: LoginRequest
):

    email = str(
        data.email
    ).strip().lower()

    password = str(
        data.password
    )

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM users
        WHERE email = ?
        """,
        (email,)
    ).fetchone()

    conn.close()

    if not row:

        raise HTTPException(
            status_code=401,
            detail="E-posta veya şifre hatalı."
        )

    try:

        valid = password_hash.verify(
            password,
            row["password_hash"]
        )

    except Exception:

        valid = False

    if not valid:

        raise HTTPException(
            status_code=401,
            detail="E-posta veya şifre hatalı."
        )

    user = user_dict(
        row
    )

    token = create_token(
        user
    )

    return {

        "ok": True,

        "message":
            "Giriş başarılı.",

        "token":
            token,

        "user":
            user,
    }


# ============================================================
# ME
# ============================================================

@app.get("/api/me")
async def me(
    user=Depends(get_current_user)
):

    return {

        "ok": True,

        "user":
            user,
    }


# ============================================================
# PLAN
# ============================================================

@app.get("/api/plan")
async def plan(
    user=Depends(get_current_user)
):

    config = get_plan_config(
        user
    )

    used = int(
        user["scan_count"]
    )

    if bool(
        user["is_admin"]
    ):

        remaining = 999999

    else:

        remaining = max(
            0,
            int(config["scan_limit"])
            - used
        )

    return {

        "ok": True,

        "plan":
            config["name"],

        "plan_level":
            config["level"],

        "features":
            config,

        "scan_used":
            used,

        "scan_limit":
            config["scan_limit"],

        "scan_remaining":
            remaining,
    }


# ============================================================
# LOGOUT
# ============================================================

@app.post("/api/logout")
async def logout():

    return {

        "ok": True,

        "message":
            "Çıkış yapıldı."
    }


# ============================================================
# SIGNALS
# ============================================================

@app.get("/api/signals")
async def signals(
    user=Depends(get_current_user)
):

    config = get_plan_config(
        user
    )

    signal_file, df = (
        find_signal_file()
    )

    if df.empty:

        return {

            "ok": True,

            "total": 0,

            "buy": 0,

            "sell": 0,

            "hold": 0,

            "top": 0,

            "display_limit":
                config["display_limit"],

            "min_score":
                MIN_SIGNAL_SCORE,

            "plan":
                config["name"],

            "signals": [],

            "live_prices": True,

            "live_price_count": 0,

            "live_price_unavailable": 0,

            "live_price_total": 0,

            "last_update_utc": None,

            "last_update_tr": None,

            "price_source":
                "Yahoo Finance / yfinance",
        }

    df = normalize_signal_dataframe(
        df
    )

    # ========================================================
    # ÖNCE SAYILAR
    # ========================================================

    total = len(df)

    buy = int(
        (
            df["Signal"] == "BUY"
        ).sum()
    )

    sell = int(
        (
            df["Signal"] == "SELL"
        ).sum()
    )

    hold = int(
        (
            df["Signal"] == "HOLD"
        ).sum()
    )

    # ========================================================
    # ÖNCE TOP LİSTE
    # ========================================================

    display_df = (
        prepare_display_dataframe(
            df,
            config["display_limit"]
        )
    )

    # ========================================================
    # SADECE TOP LİSTEYE CANLI FİYAT
    # ========================================================

    display_df, live_meta = (
        apply_live_prices_to_dataframe(
            display_df
        )
    )

    raw_records = (
        dataframe_to_records(
            display_df
        )
    )

    records = []

    for row in raw_records:

        # ----------------------------------------------------
        # AI TAHMİNİ
        # ----------------------------------------------------

        predicted = _clean_float(
            row.get(
                "AI_Predicted_Return"
            )
        )

        if predicted is None:

            predicted = 0.0

        # ----------------------------------------------------
        # CANLI FİYAT
        # ----------------------------------------------------

        price = _clean_float(
            row.get(
                "Price"
            )
        )

        # ----------------------------------------------------
        # AI SCORE
        # ----------------------------------------------------

        score = _clean_float(
            row.get(
                "AI_Probability"
            )
        )

        if score is None:

            score = 0.0

        # ----------------------------------------------------
        # GERÇEK GÜNLÜK DEĞİŞİM
        # ----------------------------------------------------

        daily_change = _clean_float(
            row.get(
                "Daily_Change_Percent"
            )
        )

        records.append({

            "symbol":
                str(
                    row.get(
                        "Ticker",
                        "-"
                    )
                ),

            "signal":
                str(
                    row.get(
                        "Signal",
                        "HOLD"
                    )
                ),

            "score":
                round(
                    score,
                    4
                ),

            "price":
                (
                    round(
                        price,
                        6
                    )
                    if price is not None
                    else None
                ),

            # SADECE AI TAHMİNİ
            "predicted_return":
                round(
                    predicted,
                    6
                ),

            # SADECE GERÇEK GÜNLÜK DEĞİŞİM
            "change":
                (
                    round(
                        daily_change,
                        6
                    )
                    if daily_change is not None
                    else None
                ),

            "daily_change_percent":
                (
                    round(
                        daily_change,
                        6
                    )
                    if daily_change is not None
                    else None
                ),

            "price_status":
                str(
                    row.get(
                        "Price_Status",
                        "UNAVAILABLE"
                    )
                ),

            "price_source":
                str(
                    row.get(
                        "Price_Source",
                        "Yahoo Finance / yfinance"
                    )
                ),

            "price_updated_utc":
                row.get(
                    "Price_Updated_UTC"
                ),

            "price_updated_tr":
                row.get(
                    "Price_Updated_TR"
                ),

            "date":
                str(
                    row.get(
                        "Date",
                        "-"
                    )
                ),
        })

    return {

        "ok": True,

        "total":
            total,

        "buy":
            buy,

        "sell":
            sell,

        "hold":
            hold,

        "top":
            len(records),

        "display_limit":
            config["display_limit"],

        "min_score":
            MIN_SIGNAL_SCORE,

        "plan":
            config["name"],

        "plan_level":
            config["level"],

        "plan_features":
            config,

        "signal_file":
            (
                signal_file.name
                if signal_file
                else None
            ),

        "signals":
            records,

        "live_prices":
            True,

        "live_price_count":
            live_meta[
                "live_count"
            ],

        "live_price_unavailable":
            live_meta[
                "unavailable_count"
            ],

        "live_price_total":
            live_meta[
                "total_count"
            ],

        "last_update_utc":
            live_meta[
                "updated_at_utc"
            ],

        "last_update_tr":
            live_meta[
                "updated_at_tr"
            ],

        "price_source":
            "Yahoo Finance / yfinance",

        "cache_seconds":
            LIVE_PRICE_CACHE_SECONDS,
    }


# ============================================================
# CANLI FİYAT TEST
# ============================================================

@app.get(
    "/api/live-price/{symbol}"
)
async def live_price(
    symbol: str
):

    symbol = (
        str(symbol)
        .strip()
        .upper()
    )

    if not symbol:

        raise HTTPException(
            status_code=400,
            detail="Sembol gerekli."
        )

    data = get_live_prices(
        [symbol]
    )

    item = data.get(
        symbol
    )

    if not item:

        return {

            "ok": False,

            "symbol":
                symbol,

            "price": None,

            "previous_close": None,

            "change": None,

            "change_percent": None,

            "status":
                "UNAVAILABLE",

            "source":
                "Yahoo Finance / yfinance",

            "updated_at_utc":
                None,

            "updated_at_tr":
                None,
        }

    return {

        "ok": True,

        "symbol":
            symbol,

        "price":
            _clean_float(
                item.get(
                    "price"
                )
            ),

        "previous_close":
            _clean_float(
                item.get(
                    "previous_close"
                )
            ),

        "change":
            _clean_float(
                item.get(
                    "change"
                )
            ),

        "change_percent":
            _clean_float(
                item.get(
                    "change_percent"
                )
            ),

        "status":
            item.get(
                "status",
                "LIVE"
            ),

        "source":
            item.get(
                "source",
                "Yahoo Finance / yfinance"
            ),

        "updated_at_utc":
            item.get(
                "updated_at_utc"
            ),

        "updated_at_tr":
            item.get(
                "updated_at_tr"
            ),
    }


# ============================================================
# STATUS
# ============================================================

@app.get("/api/status")
async def status(
    user=Depends(get_current_user)
):

    signal_file, df = (
        find_signal_file()
    )

    df = normalize_signal_dataframe(
        df
    )

    # ========================================================
    # ÖNEMLİ:
    # STATUS YAHOO'YA GİTMEZ
    # ========================================================

    historical_total = len(
        df
    )

    historical_buy = (
        int(
            (
                df["Signal"] == "BUY"
            ).sum()
        )
        if not df.empty
        else 0
    )

    historical_sell = (
        int(
            (
                df["Signal"] == "SELL"
            ).sum()
        )
        if not df.empty
        else 0
    )

    historical_hold = (
        int(
            (
                df["Signal"] == "HOLD"
            ).sum()
        )
        if not df.empty
        else 0
    )

    # ========================================================
    # PAPER SAYILARI
    # ========================================================

    current_df = (
        pd.DataFrame()
    )

    if PAPER_SIGNALS.exists():

        try:

            current_df = (
                normalize_signal_dataframe(
                    pd.read_csv(
                        PAPER_SIGNALS,
                        low_memory=False
                    )
                )
            )

        except Exception:

            current_df = (
                pd.DataFrame()
            )

    current_total = len(
        current_df
    )

    current_buy = (
        int(
            (
                current_df["Signal"]
                == "BUY"
            ).sum()
        )
        if not current_df.empty
        else 0
    )

    current_sell = (
        int(
            (
                current_df["Signal"]
                == "SELL"
            ).sum()
        )
        if not current_df.empty
        else 0
    )

    current_hold = (
        int(
            (
                current_df["Signal"]
                == "HOLD"
            ).sum()
        )
        if not current_df.empty
        else 0
    )

    config = get_plan_config(
        user
    )

    strong_df = (
        prepare_display_dataframe(
            df,
            config["display_limit"]
        )
    )

    return {

        "ok": True,

        "status":
            "READY"
            if not df.empty
            else "NO_DATA",

        "historical_total":
            historical_total,

        "historical_buy":
            historical_buy,

        "historical_sell":
            historical_sell,

        "historical_hold":
            historical_hold,

        "current_total":
            current_total,

        "current_buy":
            current_buy,

        "current_sell":
            current_sell,

        "current_hold":
            current_hold,

        "strong_signals":
            len(strong_df),

        "top":
            len(strong_df),

        "min_score":
            MIN_SIGNAL_SCORE,

        "plan":
            config["name"],

        "plan_level":
            config["level"],

        "plan_limit":
            config["display_limit"],

        "plan_features":
            config,

        "signal_file":
            (
                signal_file.name
                if signal_file
                else None
            ),

        "live_prices":
            True,

        "live_price_cache_seconds":
            LIVE_PRICE_CACHE_SECONDS,

        # STATUS CANLI FİYAT İNDİRMİYOR
        "live_price_count":
            0,

        "live_price_unavailable":
            0,

        "live_price_total":
            0,

        "last_update_utc":
            None,

        "last_update_tr":
            None,

        "price_source":
            "Yahoo Finance / yfinance",
    }


# ============================================================
# PAPER
# ============================================================

@app.get("/api/paper")
async def paper(
    user=Depends(
        require_plan("PRO")
    )
):

    if not PAPER_SIGNALS.exists():

        return {

            "ok": True,

            "paper": []
        }

    try:

        df = (
            normalize_signal_dataframe(
                pd.read_csv(
                    PAPER_SIGNALS,
                    low_memory=False
                )
            )
        )

        # Paper genelde küçük olduğu için
        # canlı fiyat uygulanabilir.
        df, live_meta = (
            apply_live_prices_to_dataframe(
                df
            )
        )

        return {

            "ok": True,

            "paper":
                dataframe_to_records(
                    df
                ),

            "last_update_utc":
                live_meta[
                    "updated_at_utc"
                ],

            "last_update_tr":
                live_meta[
                    "updated_at_tr"
                ],
        }

    except Exception as exc:

        return {

            "ok": False,

            "error":
                str(exc),

            "paper": []
        }


# ============================================================
# METRICS
# ============================================================

@app.get("/api/metrics")
async def metrics(
    user=Depends(get_current_user)
):

    files = [

        BASE_DIR /
        "level1000_metrics.csv",

        BASE_DIR /
        "metrics.csv",

        DATA_DIR /
        "level1000_metrics.csv",

        DATA_DIR /
        "metrics.csv",

        DATA_DIR /
        "level1000_model_metrics.csv",

    ]

    for path in files:

        if not path.exists():

            continue

        try:

            df = pd.read_csv(
                path,
                low_memory=False
            )

            records = (
                dataframe_to_records(
                    df
                )
            )

            return {

                "ok": True,

                "count":
                    len(records),

                "metrics":
                    records,

                "data":
                    records,
            }

        except Exception:

            continue

    return {

        "ok": True,

        "count": 0,

        "metrics": [],

        "data": [],
    }


# ============================================================
# BACKTEST
# ============================================================

@app.get("/api/backtest")
async def backtest(
    user=Depends(
        require_plan("PRO")
    )
):

    files = [

        BASE_DIR /
        "level1000_backtest.csv",

        BASE_DIR /
        "backtest.csv",

        DATA_DIR /
        "level1000_backtest.csv",

        DATA_DIR /
        "backtest.csv",

        DATA_DIR /
        "level1000_variant_summary.csv",

    ]

    for path in files:

        if not path.exists():

            continue

        try:

            df = pd.read_csv(
                path,
                low_memory=False
            )

            records = (
                dataframe_to_records(
                    df
                )
            )

            return {

                "ok": True,

                "count":
                    len(records),

                "data":
                    records,

                "backtest":
                    records,
            }

        except Exception:

            continue

    return {

        "ok": True,

        "count": 0,

        "data": [],

        "backtest": [],
    }


# ============================================================
# RUN STATE
# ============================================================

run_state = {

    "running": False,

    "started_at": None,

    "finished_at": None,

    "error": None,

    "last_user": None,
}

run_lock = threading.Lock()


# ============================================================
# SCAN INFO
# ============================================================

def get_scan_info(
    user
):

    config = get_plan_config(
        user
    )

    used = int(
        user["scan_count"]
    )

    limit = int(
        config["scan_limit"]
    )

    if bool(
        user["is_admin"]
    ):

        remaining = 999999

    else:

        remaining = max(
            0,
            limit - used
        )

    return {

        "used":
            used,

        "limit":
            limit,

        "remaining":
            remaining,
    }


def consume_scan(
    user
):

    if bool(
        user["is_admin"]
    ):

        return {

            "ok": True,

            "used": 0,

            "limit": 999999,

            "remaining": 999999,
        }

    config = get_plan_config(
        user
    )

    limit = int(
        config["scan_limit"]
    )

    conn = get_db()

    cursor = conn.execute(
        """
        UPDATE users
        SET scan_count = scan_count + 1
        WHERE id = ?
        AND scan_count < ?
        """,
        (
            user["id"],
            limit
        )
    )

    conn.commit()

    changed = cursor.rowcount

    row = conn.execute(
        """
        SELECT scan_count
        FROM users
        WHERE id = ?
        """,
        (
            user["id"],
        )
    ).fetchone()

    conn.close()

    if changed == 0:

        return {

            "ok": False,

            "remaining": 0,
        }

    used = int(
        row["scan_count"]
    )

    remaining = max(
        0,
        limit - used
    )

    return {

        "ok": True,

        "used":
            used,

        "limit":
            limit,

        "remaining":
            remaining,
    }


# ============================================================
# LEVEL 1000 PROCESS
# ============================================================

def run_level1000_process():

    run_state[
        "running"
    ] = True

    run_state[
        "started_at"
    ] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    run_state[
        "finished_at"
    ] = None

    run_state[
        "error"
    ] = None

    try:

        if not LEVEL1000_FILE.exists():

            run_state[
                "error"
            ] = (
                "level1000.py bulunamadı."
            )

            return

        process = subprocess.Popen(
            [
                sys.executable,
                str(
                    LEVEL1000_FILE
                )
            ],
            cwd=str(
                BASE_DIR
            )
        )

        process.wait()

        if process.returncode != 0:

            run_state[
                "error"
            ] = (
                "LEVEL 1000 hata kodu: "
                +
                str(
                    process.returncode
                )
            )

    except Exception as exc:

        run_state[
            "error"
        ] = str(exc)

    finally:

        run_state[
            "running"
        ] = False

        run_state[
            "finished_at"
        ] = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )


# ============================================================
# RUN
# ============================================================

@app.post("/api/run")
async def run_analysis(
    user=Depends(get_current_user)
):

    with run_lock:

        if run_state[
            "running"
        ]:

            return {

                "ok": False,

                "error":
                    "Analiz zaten çalışıyor."
            }

        scan_info = (
            get_scan_info(
                user
            )
        )

        if (
            not bool(
                user["is_admin"]
            )
            and
            scan_info[
                "remaining"
            ] <= 0
        ):

            raise HTTPException(
                status_code=403,
                detail=
                    "Tarama hakkınız bitti."
            )

        consumed = (
            consume_scan(
                user
            )
        )

        if not consumed[
            "ok"
        ]:

            raise HTTPException(
                status_code=403,
                detail=
                    "Tarama hakkınız kalmadı."
            )

        run_state[
            "last_user"
        ] = user["email"]

        thread = threading.Thread(
            target=
                run_level1000_process,
            daemon=True
        )

        thread.start()

    return {

        "ok": True,

        "message":
            "Analiz başlatıldı.",

        "scan":
            consumed,
    }


# ============================================================
# RUN STATUS
# ============================================================

@app.get("/api/run-status")
async def run_status(
    user=Depends(get_current_user)
):

    return {

        "ok": True,

        "running":
            run_state[
                "running"
            ],

        "started_at":
            run_state[
                "started_at"
            ],

        "finished_at":
            run_state[
                "finished_at"
            ],

        "error":
            run_state[
                "error"
            ],

        "last_user":
            run_state[
                "last_user"
            ],
    }


# ============================================================
# ADMIN MAKE
# ============================================================

@app.post(
    "/api/admin/make-admin/{email}"
)
async def make_admin(
    email: str,
    user=Depends(require_admin)
):

    email = (
        email
        .lower()
        .strip()
    )

    conn = get_db()

    cursor = conn.execute(
        """
        UPDATE users
        SET
            is_admin = 1,
            plan = 'MAX PRO'
        WHERE email = ?
        """,
        (
            email,
        )
    )

    conn.commit()

    changed = cursor.rowcount

    conn.close()

    if changed == 0:

        raise HTTPException(
            status_code=404,
            detail=
                "Kullanıcı bulunamadı."
        )

    return {

        "ok": True,

        "message":
            "Kullanıcı admin ve MAX PRO yapıldı."
    }


# ============================================================
# ADMIN USERS
# ============================================================

@app.get(
    "/api/admin/users"
)
async def admin_users(
    user=Depends(require_admin)
):

    conn = get_db()

    users = conn.execute(
        """
        SELECT
            id,
            name,
            email,
            plan,
            is_admin,
            created_at,
            scan_count
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    result = []

    for row in users:

        item = user_dict(
            row
        )

        config = get_plan_config(
            row
        )

        used = int(
            row["scan_count"]
        )

        item[
            "scan_count"
        ] = used

        if bool(
            row["is_admin"]
        ):

            item[
                "scan_limit"
            ] = 999999

            item[
                "scan_remaining"
            ] = 999999

        else:

            item[
                "scan_limit"
            ] = config[
                "scan_limit"
            ]

            item[
                "scan_remaining"
            ] = max(
                0,
                config[
                    "scan_limit"
                ] - used
            )

        result.append(
            item
        )

    return {

        "ok": True,

        "users":
            result,
    }


# ============================================================
# ADMIN PLAN
# ============================================================

@app.post(
    "/api/admin/set-plan/{email}/{plan}"
)
async def set_plan(
    email: str,
    plan: str,
    user=Depends(require_admin)
):

    plan = normalize_plan_name(
        plan
    )

    if plan not in (
        "FREE",
        "PRO",
        "MAX PRO"
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Plan FREE, PRO veya MAX PRO olmalıdır."
            )
        )

    email = (
        email
        .lower()
        .strip()
    )

    conn = get_db()

    cursor = conn.execute(
        """
        UPDATE users
        SET plan = ?
        WHERE email = ?
        """,
        (
            plan,
            email
        )
    )

    conn.commit()

    changed = cursor.rowcount

    conn.close()

    if changed == 0:

        raise HTTPException(
            status_code=404,
            detail=
                "Kullanıcı bulunamadı."
        )

    return {

        "ok": True,

        "plan":
            plan,

        "message":
            f"Kullanıcı planı {plan} yapıldı."
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
async def health():

    signal_file, df = (
        find_signal_file()
    )

    return {

        "ok": True,

        "service":
            "LEVEL 1000",

        "status":
            "ONLINE",

        "signals_available":
            not df.empty,

        "signal_file":
            (
                signal_file.name
                if signal_file
                else None
            ),

        "signal_count":
            len(df),

        "live_price_service":
            True,

        "live_price_cache_seconds":
            LIVE_PRICE_CACHE_SECONDS,

        "live_price_source":
            "Yahoo Finance / yfinance",
    }


# ============================================================
# DEBUG
# ============================================================

@app.get("/api/debug/data")
async def debug_data(
    user=Depends(get_current_user)
):

    signal_file, df = (
        find_signal_file()
    )

    if df.empty:

        return {

            "ok": True,

            "file": None,

            "columns": [],

            "count": 0,

            "sample": [],

            "live_prices": True,

            "last_update_utc": None,

            "last_update_tr": None,
        }

    normalized = (
        normalize_signal_dataframe(
            df
        )
    )

    config = get_plan_config(
        user
    )

    # Önce TOP liste.
    strong = (
        prepare_display_dataframe(
            normalized,
            config["display_limit"]
        )
    )

    # Sadece TOP liste canlı fiyat.
    strong, live_meta = (
        apply_live_prices_to_dataframe(
            strong
        )
    )

    return {

        "ok": True,

        "file":
            (
                signal_file.name
                if signal_file
                else None
            ),

        "columns":
            list(
                normalized.columns
            ),

        "count":
            len(normalized),

        "buy":
            int(
                (
                    normalized[
                        "Signal"
                    ]
                    == "BUY"
                ).sum()
            ),

        "sell":
            int(
                (
                    normalized[
                        "Signal"
                    ]
                    == "SELL"
                ).sum()
            ),

        "hold":
            int(
                (
                    normalized[
                        "Signal"
                    ]
                    == "HOLD"
                ).sum()
            ),

        "strong_signals":
            len(strong),

        "plan":
            config["name"],

        "plan_limit":
            config["display_limit"],

        "min_score":
            MIN_SIGNAL_SCORE,

        "sample":
            dataframe_to_records(
                strong.head(10)
            ),

        "live_prices":
            True,

        "live_price_count":
            live_meta[
                "live_count"
            ],

        "live_price_unavailable":
            live_meta[
                "unavailable_count"
            ],

        "live_price_total":
            live_meta[
                "total_count"
            ],

        "last_update_utc":
            live_meta[
                "updated_at_utc"
            ],

        "last_update_tr":
            live_meta[
                "updated_at_tr"
            ],

        "price_source":
            "Yahoo Finance / yfinance",
    }


# ============================================================
# TEK SİNYAL
# ============================================================

@app.get(
    "/api/signal/{ticker}"
)
async def single_signal(
    ticker: str,
    user=Depends(get_current_user)
):

    signal_file, df = (
        find_signal_file()
    )

    if df.empty:

        raise HTTPException(
            status_code=404,
            detail=
                "Henüz sinyal verisi yok."
        )

    df = normalize_signal_dataframe(
        df
    )

    ticker = (
        str(ticker)
        .strip()
        .upper()
    )

    result = df[
        df["Ticker"]
        .astype(str)
        .str.upper()
        == ticker
    ].copy()

    if result.empty:

        raise HTTPException(
            status_code=404,
            detail=
                f"{ticker} bulunamadı."
        )

    # Tek sembol için canlı fiyat.
    result, live_meta = (
        apply_live_prices_to_dataframe(
            result
        )
    )

    records = (
        dataframe_to_records(
            result
        )
    )

    return {

        "ok": True,

        "symbol":
            ticker,

        "signal":
            records[0]
            if records
            else None,

        "live":
            live_meta,
    }


# ============================================================
# MONTE CARLO
# ============================================================

@app.get(
    "/api/montecarlo"
)
async def montecarlo(
    user=Depends(
        require_plan("PRO")
    )
):

    files = [

        DATA_DIR /
        "level1000_monte_carlo.csv",

        BASE_DIR /
        "level1000_monte_carlo.csv",

    ]

    for path in files:

        if not path.exists():

            continue

        try:

            df = pd.read_csv(
                path,
                low_memory=False
            )

            records = (
                dataframe_to_records(
                    df
                )
            )

            return {

                "ok": True,

                "simulations":
                    len(records),

                "results":
                    records,
            }

        except Exception:

            continue

    return {

        "ok": True,

        "simulations": 0,

        "results": [],
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.exception_handler(
    404
)
async def not_found(
    request: Request,
    exc
):

    if request.url.path.startswith(
        "/api/"
    ):

        return JSONResponse(

            status_code=404,

            content={

                "ok": False,

                "error":
                    "Endpoint bulunamadı.",

                "path":
                    request.url.path,
            }
        )

    return HTMLResponse(
        "<h1>404</h1>",
        status_code=404
    )


@app.exception_handler(
    500
)
async def server_error(
    request: Request,
    exc
):

    if request.url.path.startswith(
        "/api/"
    ):

        return JSONResponse(

            status_code=500,

            content={

                "ok": False,

                "error":
                    "Sunucu hatası.",
            }
        )

    return HTMLResponse(
        "<h1>500 - Sunucu hatası</h1>",
        status_code=500
    )


# ============================================================
# ROBOTS
# ============================================================

@app.get(
    "/robots.txt",
    response_class=HTMLResponse
)
async def robots():

    return HTMLResponse(
        """
User-agent: *
Allow: /
"""
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            "8000"
        )
    )

    host = (
        "0.0.0.0"
        if os.environ.get("PORT")
        else "127.0.0.1"
    )

    print("")
    print("=" * 70)
    print(" LEVEL 1000 AI")
    print(" CANLI FİYAT + 429 KORUMASI AKTİF")
    print("=" * 70)
    print(
        "Kaynak : Yahoo Finance / yfinance"
    )
    print(
        "Cache  :",
        LIVE_PRICE_CACHE_SECONDS,
        "saniye"
    )
    print(
        "Interval:",
        LIVE_INTERVAL
    )
    print(
        "Port   :",
        port
    )
    print("=" * 70)
    print("")

    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=False
    )