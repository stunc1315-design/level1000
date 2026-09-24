# ============================================================
# LEVEL 1000 AI - WEB APP
# PUBLIC / UNRESTRICTED VERSION
# ============================================================
# ÜYELİK       : GEREKLİ DEĞİL
# ÖDEME        : GEREKLİ DEĞİL
# FREE/PRO     : NORMAL KULLANICILAR İÇİN YOK
# SCAN LIMIT   : YOK
# SIGNALS      : HERKESE AÇIK
# BACKTEST     : HERKESE AÇIK
# PAPER        : HERKESE AÇIK
# MONTE CARLO  : HERKESE AÇIK
# ADVANCED AI  : HERKESE AÇIK
# ADMIN        : KORUMALI
# LIVE PRICE   : YAHOO / yfinance + CACHE + 429 KORUMASI
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
from html import escape
from urllib.parse import quote

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
    PlainTextResponse,
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

PAPER_SIGNALS = DATA_DIR / "level1000_paper_signals.csv"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="LEVEL 1000 AI",
    version="11.0"
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
# PUBLIC MODE
# ============================================================

PUBLIC_ACCESS = True

PUBLIC_PLAN = {
    "name": "OPEN",
    "level": 999999,
    "display_limit": 999999,
    "scan_limit": 999999,
    "backtest": True,
    "paper": True,
    "advanced_ai": True,
    "all_signals": True,
}


# ============================================================
# SECURITY
# ============================================================

SECRET_KEY = os.environ.get(
    "LEVEL1000_SECRET_KEY"
)

if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(48)

ALGORITHM = "HS256"

password_hash = PasswordHash.recommended()


# ============================================================
# ESKİ PLANLAR
# ============================================================
# Veritabanı uyumluluğu için tutuluyor.
# Normal ziyaretçiye hiçbir erişim kısıtlaması uygulamaz.

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
# YAHOO CANLI FİYAT
# ============================================================

LIVE_PRICE_CACHE_SECONDS = 120

LIVE_INTERVAL = "1m"
LIVE_PERIOD = "1d"

LIVE_DOWNLOAD_LOCK = threading.Lock()

LIVE_LAST_DOWNLOAD_TIME = 0.0

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
# OTOMATİK RENDER ADMIN
# ============================================================

def ensure_env_admin():

    admin_email = os.getenv(
        "LEVEL1000_ADMIN_EMAIL",
        ""
    ).strip().lower()

    admin_password = os.getenv(
        "LEVEL1000_ADMIN_PASSWORD",
        ""
    )

    if not admin_email:
        print(
            "[ADMIN] LEVEL1000_ADMIN_EMAIL bulunamadı."
        )
        return

    if not admin_password:
        print(
            "[ADMIN] LEVEL1000_ADMIN_PASSWORD bulunamadı."
        )
        return

    if "@" not in admin_email:
        print(
            "[ADMIN] Geçersiz admin email:",
            admin_email
        )
        return

    if len(admin_password) < 6:
        print(
            "[ADMIN] Admin şifresi en az 6 karakter olmalıdır."
        )
        return

    conn = get_db()

    try:

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (admin_email,)
        ).fetchone()

        new_hash = password_hash.hash(
            admin_password
        )

        if row:

            conn.execute(
                """
                UPDATE users
                SET
                    password_hash = ?,
                    is_admin = 1,
                    plan = 'MAX PRO'
                WHERE email = ?
                """,
                (
                    new_hash,
                    admin_email
                )
            )

            conn.commit()

            print(
                "[ADMIN] Admin hesabı güncellendi."
            )

        else:

            created_at = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            conn.execute(
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
                (?, ?, ?, 'MAX PRO', 1, 0, ?)
                """,
                (
                    "LEVEL 1000 Admin",
                    admin_email,
                    new_hash,
                    created_at
                )
            )

            conn.commit()

            print(
                "[ADMIN] Yeni admin hesabı oluşturuldu."
            )

        print(
            "[ADMIN] Email:",
            admin_email
        )

        print(
            "[ADMIN] Yetki: ADMIN"
        )

    except Exception as exc:

        print(
            "[ADMIN] Hata:",
            str(exc)
        )

    finally:

        conn.close()


ensure_env_admin()


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


def get_plan_config(user=None):

    # ========================================================
    # ARTIK NORMAL KULLANICIYA HER ŞEY AÇIK
    # ========================================================

    if PUBLIC_ACCESS:
        return PUBLIC_PLAN

    if not user:
        return PUBLIC_PLAN

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

    if auth.startswith("Bearer "):

        return auth[7:].strip()

    return request.cookies.get(
        "access_token"
    )


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
            algorithms=[ALGORITHM]
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
# ADMIN KONTROLÜ
# ============================================================
# Admin endpoint'leri halen korumalıdır.

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
# ESKİ PLAN KONTROLÜ
# ============================================================
# Normal API'lerde artık kullanılmıyor.
# Admin/uyumluluk için bırakıldı.

def require_plan(required_plan):

    async def dependency(
        user=Depends(get_current_user)
    ):

        if PUBLIC_ACCESS:

            return user

        current = get_plan_config(user)

        required = PLANS.get(
            normalize_plan_name(required_plan),
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

        key = str(col).strip()
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
# DISPLAY
# ============================================================

def prepare_display_dataframe(
    df,
    limit=None
):

    if df is None or df.empty:
        return pd.DataFrame()

    work = df.copy()

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

    # ========================================================
    # PUBLIC MODDA LİMİT YOK
    # ========================================================

    if PUBLIC_ACCESS:
        limit = None

    if limit is not None:

        try:
            limit = int(limit)
        except Exception:
            limit = None

    if limit is not None and limit > 0:

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

        if not math.isfinite(value):
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
# YAHOO HELPERS
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


def _get_close_series(frame):

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


def _get_last_price_from_frame(frame):

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


def _get_fast_info_price(symbol):

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

            value = info.get(key)

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

def _download_live_prices(symbols):

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

                                "price": price,

                                "previous_close": None,

                                "change": None,

                                "change_percent": None,

                                "status": "LIVE",

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
                                ] = change_percent

                        except Exception:
                            continue

            except Exception as exc:

                print(
                    "[YAHOO DAILY UYARI]",
                    str(exc)
                )

        # ====================================================
        # FAST INFO FALLBACK
        # ====================================================

        missing = [
            symbol
            for symbol in symbols
            if symbol not in results
        ]

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

                            "price": price,

                            "previous_close": None,

                            "change": None,

                            "change_percent": None,

                            "status": "DELAYED",

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

def get_live_prices(symbols):

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

    with live_price_cache_lock:

        for symbol in symbols:

            item = live_price_cache.get(
                symbol
            )

            if not item:

                missing.append(symbol)
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

                missing.append(symbol)

    if missing:

        fresh = _download_live_prices(
            missing
        )

        with live_price_cache_lock:

            for symbol, item in fresh.items():

                item_copy = dict(item)

                item_copy[
                    "_cached_at"
                ] = time.time()

                live_price_cache[
                    symbol
                ] = item_copy

                output[symbol] = dict(
                    item
                )

    for symbol in symbols:

        if symbol not in output:

            output[symbol] = {

                "price": None,

                "previous_close": None,

                "change": None,

                "change_percent": None,

                "status": "UNAVAILABLE",

                "source":
                    "Yahoo Finance / yfinance",

                "updated_at_utc": None,

                "updated_at_tr": None,
            }

    return output


# ============================================================
# LIVE PRICE → DATAFRAME
# ============================================================

def apply_live_prices_to_dataframe(df):

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

        price_values.append(price)

        change_values.append(change)

        status_values.append(status)

        source_values.append(source)

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

        "live_count": live_count,

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
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport"
                  content="width=device-width,initial-scale=1">
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
# PUBLIC PAGES
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
        <meta name="viewport"
              content="width=device-width,initial-scale=1">
        <title>{escape(title)}</title>
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
        a {{
            color: #93c5fd;
        }}
        </style>
        </head>
        <body>
        <h1>{escape(title)}</h1>
        <p>{escape(text)}</p>
        <p>
            <a href="/">LEVEL 1000 AI Ana Sayfa</a>
        </p>
        </body>
        </html>
        """
    )


@app.get("/about", response_class=HTMLResponse)
async def about():

    return simple_page(
        "LEVEL 1000 AI",
        "Yapay zeka destekli piyasa araştırma ve sinyal analiz platformu."
    )


@app.get("/guide", response_class=HTMLResponse)
async def guide():

    return simple_page(
        "Kullanım Rehberi",
        "Sistem sinyal verilerini analiz eder. BUY, SELL ve HOLD sonuçları yatırım tavsiyesi değildir."
    )


@app.get("/risk", response_class=HTMLResponse)
async def risk():

    return simple_page(
        "Risk Bildirimi",
        "LEVEL 1000 AI finansal danışmanlık veya yatırım garantisi sunmaz. Geçmiş performans gelecekteki sonuçların garantisi değildir."
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy():

    return simple_page(
        "Gizlilik",
        "LEVEL 1000 AI normal kullanım için üyelik zorunluluğu gerektirmez. Admin hesapları güvenlik amacıyla veritabanında tutulabilir."
    )


@app.get("/cookies", response_class=HTMLResponse)
async def cookies():

    return simple_page(
        "Çerezler",
        "Uygulama normal kullanım için üyelik zorunluluğu olmadan çalışır. Teknik çerezler kullanılabilir."
    )


@app.get("/terms", response_class=HTMLResponse)
async def terms():

    return simple_page(
        "Kullanım Şartları",
        "LEVEL 1000 AI yalnızca araştırma ve eğitim amaçlı kullanılmalıdır."
    )


@app.get("/contact", response_class=HTMLResponse)
async def contact():

    return simple_page(
        "İletişim",
        "LEVEL 1000 AI destek kanallarından uygulama yöneticisine ulaşabilirsiniz."
    )


# ============================================================
# REGISTER
# ============================================================
# Eski kullanıcı sistemi tamamen silinmedi.
# Ancak normal site kullanımı için gerekli değildir.

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
        (?, ?, ?, 'MAX PRO', 0, 0, ?)
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

    user = user_dict(row)

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

    env_admin_email = os.getenv(
        "LEVEL1000_ADMIN_EMAIL",
        ""
    ).strip().lower()

    env_admin_password = os.getenv(
        "LEVEL1000_ADMIN_PASSWORD",
        ""
    )

    if (
        not row
        and
        env_admin_email
        and
        env_admin_password
        and
        email == env_admin_email
    ):

        ensure_env_admin()

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

    if (
        not valid
        and
        env_admin_email
        and
        env_admin_password
        and
        email == env_admin_email
        and
        secrets.compare_digest(
            password,
            env_admin_password
        )
    ):

        conn = get_db()

        new_hash = password_hash.hash(
            env_admin_password
        )

        conn.execute(
            """
            UPDATE users
            SET
                password_hash = ?,
                is_admin = 1,
                plan = 'MAX PRO'
            WHERE email = ?
            """,
            (
                new_hash,
                email
            )
        )

        conn.commit()

        row = conn.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        conn.close()

        valid = True

    if not valid:

        raise HTTPException(
            status_code=401,
            detail="E-posta veya şifre hatalı."
        )

    user = user_dict(row)

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
        "user": user,
    }


# ============================================================
# PLAN
# ============================================================
# Artık OPEN döner.

@app.get("/api/plan")
async def plan():

    return {

        "ok": True,

        "plan":
            PUBLIC_PLAN["name"],

        "plan_level":
            PUBLIC_PLAN["level"],

        "features":
            PUBLIC_PLAN,

        "scan_used":
            0,

        "scan_limit":
            999999,

        "scan_remaining":
            999999,
    }


# ============================================================
# LOGOUT
# ============================================================

@app.post("/api/logout")
async def logout():

    return {
        "ok": True,
        "message": "Çıkış yapıldı."
    }


# ============================================================
# SIGNALS
# ============================================================
# HERKESE AÇIK
# ÜYELİK YOK
# PLAN YOK
# DISPLAY LIMIT YOK

@app.get("/api/signals")
async def signals():

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
                999999,

            "min_score":
                MIN_SIGNAL_SCORE,

            "plan":
                "OPEN",

            "plan_level":
                999999,

            "plan_features":
                PUBLIC_PLAN,

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
    # TÜM SİNYALLER
    # ========================================================

    display_df = (
        prepare_display_dataframe(
            df,
            None
        )
    )

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

        predicted = _clean_float(
            row.get(
                "AI_Predicted_Return"
            )
        )

        if predicted is None:
            predicted = 0.0

        price = _clean_float(
            row.get(
                "Price"
            )
        )

        score = _clean_float(
            row.get(
                "AI_Probability"
            )
        )

        if score is None:
            score = 0.0

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

            "predicted_return":
                round(
                    predicted,
                    6
                ),

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
            999999,

        "min_score":
            MIN_SIGNAL_SCORE,

        "plan":
            "OPEN",

        "plan_level":
            999999,

        "plan_features":
            PUBLIC_PLAN,

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
# CANLI FİYAT
# ============================================================

@app.get("/api/live-price/{symbol}")
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

            "symbol": symbol,

            "price": None,

            "previous_close": None,

            "change": None,

            "change_percent": None,

            "status":
                "UNAVAILABLE",

            "source":
                "Yahoo Finance / yfinance",

            "updated_at_utc": None,

            "updated_at_tr": None,
        }

    return {

        "ok": True,

        "symbol": symbol,

        "price":
            _clean_float(
                item.get("price")
            ),

        "previous_close":
            _clean_float(
                item.get("previous_close")
            ),

        "change":
            _clean_float(
                item.get("change")
            ),

        "change_percent":
            _clean_float(
                item.get("change_percent")
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
# HERKESE AÇIK

@app.get("/api/status")
async def status():

    signal_file, df = (
        find_signal_file()
    )

    df = normalize_signal_dataframe(
        df
    )

    historical_total = len(df)

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

    current_df = pd.DataFrame()

    if PAPER_SIGNALS.exists():

        try:

            current_df = normalize_signal_dataframe(
                pd.read_csv(
                    PAPER_SIGNALS,
                    low_memory=False
                )
            )

        except Exception:

            current_df = pd.DataFrame()

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

    strong_df = (
        prepare_display_dataframe(
            df,
            None
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
            "OPEN",

        "plan_level":
            999999,

        "plan_limit":
            999999,

        "plan_features":
            PUBLIC_PLAN,

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
# HERKESE AÇIK

@app.get("/api/paper")
async def paper():

    if not PAPER_SIGNALS.exists():

        return {

            "ok": True,

            "paper": []
        }

    try:

        df = normalize_signal_dataframe(
            pd.read_csv(
                PAPER_SIGNALS,
                low_memory=False
            )
        )

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
# HERKESE AÇIK

@app.get("/api/metrics")
async def metrics():

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
# HERKESE AÇIK

@app.get("/api/backtest")
async def backtest():

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
# LEVEL 1000 PROCESS
# ============================================================

def run_level1000_process():

    run_state["running"] = True

    run_state["started_at"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    run_state["finished_at"] = None

    run_state["error"] = None

    try:

        if not LEVEL1000_FILE.exists():

            run_state["error"] = (
                "level1000.py bulunamadı."
            )

            return

        process = subprocess.Popen(
            [
                sys.executable,
                str(LEVEL1000_FILE)
            ],
            cwd=str(BASE_DIR)
        )

        process.wait()

        if process.returncode != 0:

            run_state["error"] = (
                "LEVEL 1000 hata kodu: "
                + str(
                    process.returncode
                )
            )

    except Exception as exc:

        run_state["error"] = str(exc)

    finally:

        run_state["running"] = False

        run_state["finished_at"] = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )


# ============================================================
# RUN
# ============================================================
# HERKESE AÇIK
# TARAMA LİMİTİ YOK

@app.post("/api/run")
async def run_analysis():

    with run_lock:

        if run_state["running"]:

            return {

                "ok": False,

                "error":
                    "Analiz zaten çalışıyor."
            }

        # ====================================================
        # ARTIK SCAN COUNT YOK
        # ====================================================

        run_state["last_user"] = "PUBLIC"

        thread = threading.Thread(
            target=run_level1000_process,
            daemon=True
        )

        thread.start()

    return {

        "ok": True,

        "message":
            "Analiz başlatıldı.",

        "scan": {

            "used": 0,

            "limit": 999999,

            "remaining": 999999,

            "unlimited": True
        }
    }


# ============================================================
# RUN STATUS
# ============================================================
# HERKESE AÇIK

@app.get("/api/run-status")
async def run_status():

    return {

        "ok": True,

        "running":
            run_state["running"],

        "started_at":
            run_state["started_at"],

        "finished_at":
            run_state["finished_at"],

        "error":
            run_state["error"],

        "last_user":
            run_state["last_user"],
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
        (email,)
    )

    conn.commit()

    changed = cursor.rowcount

    conn.close()

    if changed == 0:

        raise HTTPException(
            status_code=404,
            detail="Kullanıcı bulunamadı."
        )

    return {

        "ok": True,

        "message":
            "Kullanıcı admin yapıldı."
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

        item = user_dict(row)

        item["scan_count"] = int(
            row["scan_count"]
        )

        # Public sistemde limit yok.
        item["scan_limit"] = 999999
        item["scan_remaining"] = 999999

        result.append(item)

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
            "Kullanıcı planı güncellendi."
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

        "public_access":
            True,

        "membership_required":
            False,

        "payment_required":
            False,

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
# HERKESE AÇIK

@app.get("/api/debug/data")
async def debug_data():

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

    strong = (
        prepare_display_dataframe(
            normalized,
            None
        )
    )

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
                    ] == "BUY"
                ).sum()
            ),

        "sell":
            int(
                (
                    normalized[
                        "Signal"
                    ] == "SELL"
                ).sum()
            ),

        "hold":
            int(
                (
                    normalized[
                        "Signal"
                    ] == "HOLD"
                ).sum()
            ),

        "strong_signals":
            len(strong),

        "plan":
            "OPEN",

        "plan_limit":
            999999,

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
# HERKESE AÇIK

@app.get("/api/signal/{ticker}")
async def single_signal(
    ticker: str
):

    signal_file, df = (
        find_signal_file()
    )

    if df.empty:

        raise HTTPException(
            status_code=404,
            detail="Henüz sinyal verisi yok."
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
            detail=f"{ticker} bulunamadı."
        )

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
# HERKESE AÇIK

@app.get("/api/montecarlo")
async def montecarlo():

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

@app.exception_handler(404)
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


@app.exception_handler(500)
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
# SEO
# ============================================================

SEO_BASE_URL = (
    "https://level1000-2.onrender.com"
)


# ============================================================
# PUBLIC TICKERS
# ============================================================

def get_public_tickers():

    result = set()

    try:

        signal_file, df = find_signal_file()

        if df is not None and not df.empty:

            df = normalize_signal_dataframe(
                df
            )

            if (
                not df.empty
                and "Ticker" in df.columns
            ):

                for value in df["Ticker"].tolist():

                    ticker = str(
                        value
                    ).strip().upper()

                    if not ticker:
                        continue

                    if ticker in {
                        "-",
                        "NAN",
                        "NONE",
                        "NULL"
                    }:
                        continue

                    if len(ticker) > 30:
                        continue

                    result.add(ticker)

    except Exception:
        pass

    symbols_file = (
        BASE_DIR / "symbols.txt"
    )

    if symbols_file.exists():

        try:

            lines = symbols_file.read_text(
                encoding="utf-8",
                errors="ignore"
            ).splitlines()

            for line in lines:

                ticker = str(
                    line
                ).strip().upper()

                if not ticker:
                    continue

                if ticker.startswith("#"):
                    continue

                if "," in ticker:

                    ticker = ticker.split(
                        ",",
                        1
                    )[0].strip()

                if ticker in {
                    "-",
                    "NAN",
                    "NONE",
                    "NULL",
                    "SYMBOL",
                    "TICKER"
                }:
                    continue

                if len(ticker) > 30:
                    continue

                result.add(ticker)

        except Exception:
            pass

    result.update({

        "AAPL",
        "NVDA",
        "MSFT",
        "AMZN",
        "GOOGL",
        "META",
        "TSLA",
        "AVGO",
        "AMD",
        "NFLX",
        "PLTR",
        "INTC",
        "QCOM",
        "MU",
        "ARM",
        "ORCL",
        "CRM",
        "ADBE",
        "UBER",
        "SHOP",
        "COIN",
        "MSTR",
        "PYPL",
        "JPM",
        "V",
        "MA",
        "WMT",
        "COST",
        "KO",
        "DIS",
        "BRK-B",
        "LLY",
        "UNH",
        "HD",
        "PG",
        "MRK",
        "ABBV",
        "PEP",
        "TMO",
        "LIN",
        "DHR",
        "NKE",
        "MCD",
        "RTX",
        "C",
        "GS",
        "LOW",
        "SBUX",
        "DE",
        "UPS"

    })

    result.update({

        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "VOO",
        "VTI",
        "VEA",
        "VWO",
        "ARKK",
        "SMH",
        "XLK",
        "XLF",
        "XLE",
        "XLV",
        "XLI",
        "XLP",
        "XLY",
        "GLD",
        "SLV",
        "TLT",
        "HYG",
        "LQD"

    })

    result.update({

        "BTC-USD",
        "ETH-USD",
        "SOL-USD",
        "XRP-USD",
        "DOGE-USD",
        "ADA-USD",
        "AVAX-USD",
        "LINK-USD",
        "DOT-USD",
        "LTC-USD"

    })

    return sorted(result)


# ============================================================
# PUBLIC SIGNAL
# ============================================================

def get_public_signal(ticker):

    ticker = str(
        ticker
    ).strip().upper()

    try:

        signal_file, df = find_signal_file()

        if df is None or df.empty:
            return None

        df = normalize_signal_dataframe(
            df
        )

        if (
            df.empty
            or "Ticker" not in df.columns
        ):
            return None

        result = df[
            df["Ticker"]
            .astype(str)
            .str.strip()
            .str.upper()
            == ticker
        ].copy()

        if result.empty:
            return None

        row = result.iloc[0]

        probability = _clean_float(
            row.get(
                "AI_Probability"
            )
        )

        predicted_return = _clean_float(
            row.get(
                "AI_Predicted_Return"
            )
        )

        price = _clean_float(
            row.get(
                "Price"
            )
        )

        signal = str(
            row.get(
                "Signal",
                "VERİ YOK"
            )
        ).strip().upper()

        if not signal:
            signal = "VERİ YOK"

        date = str(
            row.get(
                "Date",
                "-"
            )
        )

        return {

            "ticker": ticker,

            "signal": signal,

            "probability": probability,

            "predicted_return": predicted_return,

            "price": price,

            "date": date,

            "has_signal": True

        }

    except Exception:

        return None


# ============================================================
# PUBLIC STOCK PAGE
# ============================================================

@app.get(
    "/hisse/{ticker}",
    response_class=HTMLResponse
)
async def public_stock_page(
    ticker: str
):

    ticker = str(
        ticker
    ).strip().upper()

    if not ticker:

        raise HTTPException(
            status_code=404,
            detail="Hisse bulunamadı."
        )

    if len(ticker) > 30:

        raise HTTPException(
            status_code=404,
            detail="Geçersiz sembol."
        )

    data = get_public_signal(
        ticker
    )

    if data is None:

        data = {

            "ticker": ticker,

            "signal": "SİNYAL YOK",

            "probability": None,

            "predicted_return": None,

            "price": None,

            "date": "-",

            "has_signal": False
        }

    safe_ticker = escape(
        data["ticker"]
    )

    safe_signal = escape(
        data["signal"]
    )

    probability = data["probability"]

    predicted_return = data[
        "predicted_return"
    ]

    price = data["price"]

    date = escape(
        str(
            data["date"]
        )
    )

    if probability is not None:

        probability_text = (
            f"{probability:.2f}%"
        )

    else:

        probability_text = "Henüz yok"

    if predicted_return is not None:

        predicted_text = (
            f"{predicted_return:.2f}%"
        )

    else:

        predicted_text = "Henüz yok"

    if price is not None:

        price_text = (
            f"{price:.4f}"
        )

    else:

        price_text = "Henüz yok"

    encoded_ticker = quote(
        ticker,
        safe=".-_"
    )

    canonical = (
        f"{SEO_BASE_URL}/hisse/"
        f"{encoded_ticker}"
    )

    title = (
        f"{safe_ticker} Hisse Senedi Analizi | "
        f"Fiyat ve AI Sinyali | LEVEL 1000 AI"
    )

    description = (
        f"{safe_ticker} hisse senedi analizi, "
        f"fiyat, AI sinyali, AI olasılığı ve "
        f"tahmini getiri bilgilerini inceleyin."
    )

    return HTMLResponse(

        f"""
<!DOCTYPE html>

<html lang="tr">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>{title}</title>

<meta
    name="description"
    content="{escape(description)}"
>

<meta
    name="robots"
    content="index, follow"
>

<link
    rel="canonical"
    href="{canonical}"
>

<meta
    property="og:type"
    content="website"
>

<meta
    property="og:title"
    content="{title}"
>

<meta
    property="og:description"
    content="{escape(description)}"
>

<meta
    property="og:url"
    content="{canonical}"
>

<meta
    property="og:site_name"
    content="LEVEL 1000 AI"
>

<script type="application/ld+json">

{{
    "@context": "https://schema.org",
    "@type": "WebPage",
    "name": "{escape(title)}",
    "description": "{escape(description)}",
    "url": "{canonical}",
    "isPartOf": {{
        "@type": "WebSite",
        "name": "LEVEL 1000 AI",
        "url": "{SEO_BASE_URL}/"
    }}
}}

</script>

<style>

* {{
    box-sizing:
        border-box;
}}

body {{

    margin:
        0;

    background:
        #080d18;

    color:
        #ffffff;

    font-family:
        Arial,
        Helvetica,
        sans-serif;
}}

.container {{

    max-width:
        1100px;

    margin:
        auto;

    padding:
        30px 20px;
}}

.topbar {{

    display:
        flex;

    justify-content:
        space-between;

    align-items:
        center;

    margin-bottom:
        30px;
}}

.logo {{

    font-size:
        24px;

    font-weight:
        900;
}}

.home {{

    color:
        #93c5fd;

    text-decoration:
        none;

    font-weight:
        700;
}}

.card {{

    background:
        #111827;

    border:
        1px solid #26344c;

    border-radius:
        18px;

    padding:
        28px;

    margin-bottom:
        20px;
}}

h1 {{

    font-size:
        38px;

    margin:
        0 0 15px;
}}

h2 {{

    font-size:
        24px;

    margin:
        0 0 15px;
}}

.subtitle {{

    color:
        #94a3b8;

    line-height:
        1.8;
}}

.grid {{

    display:
        grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(190px, 1fr)
        );

    gap:
        15px;

    margin-top:
        25px;
}}

.stat {{

    background:
        #0b1220;

    border:
        1px solid #26344c;

    border-radius:
        14px;

    padding:
        20px;
}}

.stat-title {{

    color:
        #94a3b8;

    font-size:
        14px;

    margin-bottom:
        10px;
}}

.stat-value {{

    font-size:
        24px;

    font-weight:
        900;
}}

.text {{

    color:
        #cbd5e1;

    line-height:
        1.85;
}}

.warning {{

    color:
        #fbbf24;

    line-height:
        1.8;
}}

.button {{

    display:
        inline-block;

    margin-top:
        15px;

    padding:
        12px 20px;

    border-radius:
        10px;

    background:
        #2563eb;

    color:
        white;

    text-decoration:
        none;

    font-weight:
        800;
}}

.links {{

    display:
        flex;

    flex-wrap:
        wrap;

    gap:
        12px;
}}

.links a {{

    color:
        #93c5fd;

    text-decoration:
        none;
}}

footer {{

    color:
        #64748b;

    text-align:
        center;

    margin-top:
        35px;

    line-height:
        1.7;
}}

</style>

</head>

<body>

<div class="container">

<div class="topbar">

    <div class="logo">
        LEVEL 1000 AI
    </div>

    <a
        class="home"
        href="/"
    >
        Ana Sayfa
    </a>

</div>

<div class="card">

    <h1>
        {safe_ticker} Hisse Senedi Analizi
    </h1>

    <p class="subtitle">

        {safe_ticker} için LEVEL 1000 AI
        piyasa analiz ve araştırma sayfası.

    </p>

    <div class="grid">

        <div class="stat">

            <div class="stat-title">
                AI Sinyali
            </div>

            <div class="stat-value">
                {safe_signal}
            </div>

        </div>

        <div class="stat">

            <div class="stat-title">
                AI Olasılığı
            </div>

            <div class="stat-value">
                {probability_text}
            </div>

        </div>

        <div class="stat">

            <div class="stat-title">
                Tahmini Getiri
            </div>

            <div class="stat-value">
                {predicted_text}
            </div>

        </div>

        <div class="stat">

            <div class="stat-title">
                Fiyat
            </div>

            <div class="stat-value">
                {price_text}
            </div>

        </div>

        <div class="stat">

            <div class="stat-title">
                Analiz Tarihi
            </div>

            <div class="stat-value">
                {date}
            </div>

        </div>

    </div>

</div>

<div class="card">

    <h2>
        {safe_ticker} hisse senedi
    </h2>

    <p class="text">

        {safe_ticker} hakkında piyasa verileri,
        AI analiz sonuçları ve teknik araştırma
        bilgileri LEVEL 1000 AI platformunda
        sunulmaktadır.

        Sistem mevcut verilere göre BUY, SELL
        veya HOLD benzeri analiz sonuçları
        üretebilir.

    </p>

</div>

<div class="card">

    <h2>
        LEVEL 1000 AI
    </h2>

    <p class="text">

        LEVEL 1000 AI; hisse senetleri, ETF'ler,
        kripto varlıklar ve farklı piyasa
        sembolleri üzerinde yapay zeka destekli
        piyasa araştırması yapılmasına yardımcı
        olmak amacıyla geliştirilmiştir.

        Platform normal ziyaretçiler için
        üyelik veya satın alma zorunluluğu
        olmadan kullanılabilir.

    </p>

    <div class="links">

        <a href="/hisse/AAPL">AAPL</a>
        <a href="/hisse/NVDA">NVDA</a>
        <a href="/hisse/TSLA">TSLA</a>
        <a href="/hisse/MSFT">MSFT</a>
        <a href="/hisse/AMZN">AMZN</a>
        <a href="/hisse/GOOGL">GOOGL</a>

    </div>

    <br>

    <a
        class="button"
        href="/"
    >
        LEVEL 1000 AI'ı Aç
    </a>

</div>

<div class="card">

    <h2>
        Risk Uyarısı
    </h2>

    <p class="warning">

        LEVEL 1000 AI tarafından sunulan bilgiler
        yatırım tavsiyesi veya finansal danışmanlık
        değildir.

        Geçmiş performans gelecekteki sonuçların
        garantisi değildir.

    </p>

</div>

<footer>

    LEVEL 1000 AI —
    Yapay zeka destekli piyasa araştırma platformu.

</footer>

</div>

</body>

</html>
"""
    )


# ============================================================
# SITEMAP
# ============================================================

@app.get(
    "/sitemap.xml",
    response_class=PlainTextResponse
)
async def sitemap():

    urls = [

        f"{SEO_BASE_URL}/",

        f"{SEO_BASE_URL}/about",

        f"{SEO_BASE_URL}/guide",

        f"{SEO_BASE_URL}/risk",

        f"{SEO_BASE_URL}/privacy",

        f"{SEO_BASE_URL}/cookies",

        f"{SEO_BASE_URL}/terms",

        f"{SEO_BASE_URL}/contact"

    ]

    for ticker in get_public_tickers():

        encoded = quote(
            ticker,
            safe=".-_"
        )

        urls.append(
            f"{SEO_BASE_URL}/hisse/{encoded}"
        )

    urls = list(
        dict.fromkeys(
            urls
        )
    )

    xml = [

        '<?xml version="1.0" encoding="UTF-8"?>',

        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'

    ]

    for url in urls:

        xml.append(
            f"<url>"
            f"<loc>{escape(url)}</loc>"
            f"</url>"
        )

    xml.append(
        "</urlset>"
    )

    return PlainTextResponse(

        "\n".join(xml),

        media_type="application/xml"
    )


# ============================================================
# ROBOTS
# ============================================================

@app.get(
    "/robots.txt",
    response_class=PlainTextResponse
)
async def robots():

    robots_text = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {SEO_BASE_URL}/sitemap.xml\n"
    )

    return PlainTextResponse(

        content=robots_text,

        media_type="text/plain",

        headers={

            "Cache-Control":
                "no-cache, no-store, must-revalidate",

            "Pragma":
                "no-cache",

            "Expires":
                "0",
        },
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
    print(" PUBLIC / ÜYELİKSİZ SİSTEM")
    print(" SATIN ALMA ZORUNLULUĞU YOK")
    print(" TÜM NORMAL ÖZELLİKLER AÇIK")
    print(" ADMIN SİSTEMİ KORUMALI")
    print(" CANLI FİYAT + 429 KORUMASI AKTİF")
    print("=" * 70)

    print(
        "Public Access     :",
        PUBLIC_ACCESS
    )

    print(
        "Membership Required: NO"
    )

    print(
        "Payment Required   : NO"
    )

    print(
        "Signals            : UNLIMITED"
    )

    print(
        "Backtest           : OPEN"
    )

    print(
        "Paper Trading      : OPEN"
    )

    print(
        "Monte Carlo        : OPEN"
    )

    print(
        "Advanced AI        : OPEN"
    )

    print(
        "Kaynak             : Yahoo Finance / yfinance"
    )

    print(
        "Cache              :",
        LIVE_PRICE_CACHE_SECONDS,
        "saniye"
    )

    print(
        "Interval           :",
        LIVE_INTERVAL
    )

    print(
        "Port               :",
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