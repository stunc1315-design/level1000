from pathlib import Path
from datetime import datetime, timedelta, timezone
import os
import secrets
import subprocess
import sys
import threading
import sqlite3

import pandas as pd
import jwt

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer

from pydantic import BaseModel, EmailStr
from pwdlib import PasswordHash


# ============================================================
# LEVEL 1000 AI
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "level1000_data"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = BASE_DIR / "level1000_users.db"
LEVEL1000_FILE = BASE_DIR / "level1000.py"

LATEST_SIGNALS = BASE_DIR / "level1000_latest_signals.csv"
PAPER_SIGNALS = BASE_DIR / "level1000_paper_signals.csv"


# ============================================================
# AYARLAR
# ============================================================

DISPLAY_LIMIT = 300
MIN_SIGNAL_SCORE = 0.65


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


# ============================================================
# PLAN NORMALIZE
# ============================================================

def normalize_plan_name(plan):

    plan = str(plan or "FREE").upper().strip()

    plan = plan.replace("_", " ")
    plan = plan.replace("-", " ")

    if plan == "MAXPRO":
        plan = "MAX PRO"

    if plan == "MAX PRO":
        return "MAX PRO"

    if plan == "PRO":
        return "PRO"

    return "FREE"


# ============================================================
# DATABASE
# ============================================================

def get_db():

    conn = sqlite3.connect(
        DB_FILE,
        timeout=30
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
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'FREE',
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            scan_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    columns = conn.execute(
        "PRAGMA table_info(users)"
    ).fetchall()

    column_names = {
        row["name"]
        for row in columns
    }

    if "scan_count" not in column_names:

        conn.execute(
            """
            ALTER TABLE users
            ADD COLUMN scan_count INTEGER NOT NULL DEFAULT 0
            """
        )

    conn.commit()
    conn.close()


init_db()


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="LEVEL 1000 AI TRADING PRO",
    version="7.7"
)


# ============================================================
# STATIC
# ============================================================

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static"
)


# ============================================================
# SECURITY
# ============================================================

password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/login",
    auto_error=False
)


# ============================================================
# JWT SECRET
# ============================================================

SECRET_FILE = BASE_DIR / ".level1000_secret"

ENV_SECRET = os.environ.get(
    "LEVEL1000_SECRET_KEY"
)

if ENV_SECRET:

    JWT_SECRET = ENV_SECRET.strip()

elif SECRET_FILE.exists():

    try:

        JWT_SECRET = SECRET_FILE.read_text(
            encoding="utf-8"
        ).strip()

        if not JWT_SECRET:
            raise ValueError("Boş secret")

    except Exception:

        JWT_SECRET = secrets.token_hex(32)

else:

    JWT_SECRET = secrets.token_hex(32)

    try:

        SECRET_FILE.write_text(
            JWT_SECRET,
            encoding="utf-8"
        )
    except Exception:
        pass


JWT_ALGORITHM = "HS256"

TOKEN_EXPIRE_MINUTES = 60 * 24 * 7


# ============================================================
# MODELS
# ============================================================

class RegisterRequest(BaseModel):

    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):

    email: EmailStr
    password: str


# ============================================================
# JWT
# ============================================================

def create_token(user):

    expire = (
        datetime.now(timezone.utc)
        +
        timedelta(
            minutes=TOKEN_EXPIRE_MINUTES
        )
    )

    plan = normalize_plan_name(
        user["plan"]
    )

    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "plan": plan,
        "admin": bool(user["is_admin"]),
        "exp": expire,
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )


def decode_token(token):

    try:

        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )

    except Exception:

        return None


# ============================================================
# CURRENT USER
# ============================================================

def get_current_user(
    token: str = Depends(oauth2_scheme)
):

    if not token:

        raise HTTPException(
            status_code=401,
            detail="Giriş yapmanız gerekiyor."
        )

    payload = decode_token(token)

    if not payload:

        raise HTTPException(
            status_code=401,
            detail="Oturum geçersiz veya süresi dolmuş."
        )

    user_id = payload.get("sub")

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Geçersiz kullanıcı."
        )

    conn = get_db()

    user = conn.execute(
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
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Kullanıcı bulunamadı."
        )

    return user


# ============================================================
# PLAN CONFIG
# ============================================================

def get_plan_config(user):

    if bool(user["is_admin"]):

        return PLANS["MAX PRO"]

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

def user_dict(user):

    if not user:
        return None

    plan = (
        "MAX PRO"
        if bool(user["is_admin"])
        else normalize_plan_name(
            user["plan"]
        )
    )

    config = PLANS.get(
        plan,
        PLANS["FREE"]
    )

    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "plan": plan,
        "is_admin": bool(user["is_admin"]),
        "created_at": user["created_at"],
        "plan_level": config["level"],
        "plan_features": config,
        "scan_count": int(
            user["scan_count"]
        ),
    }


# ============================================================
# REQUIRE PLAN
# ============================================================

def require_plan(required_plan):

    required_plan = normalize_plan_name(
        required_plan
    )

    def checker(
        user=Depends(get_current_user)
    ):

        if bool(user["is_admin"]):
            return user

        current = normalize_plan_name(
            user["plan"]
        )

        current_level = PLANS.get(
            current,
            PLANS["FREE"]
        )["level"]

        required_level = PLANS.get(
            required_plan,
            PLANS["FREE"]
        )["level"]

        if current_level < required_level:

            raise HTTPException(
                status_code=403,
                detail=(
                    f"Bu özellik {required_plan} "
                    "ve üzeri plan gerektiriyor."
                )
            )

        return user

    return checker


# ============================================================
# ADMIN
# ============================================================

def require_admin(
    user=Depends(get_current_user)
):

    if not bool(user["is_admin"]):

        raise HTTPException(
            status_code=403,
            detail="Bu işlem sadece admin içindir."
        )

    return user


# ============================================================
# CSV NORMALIZATION
# ============================================================

def normalize_signal_dataframe(df):

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    df.columns = [
        str(c)
        .replace("\ufeff", "")
        .strip()
        for c in df.columns
    ]

    rename_map = {

        "date": "Date",
        "Date": "Date",
        "DATE": "Date",
        "Trade_Date": "Date",

        "symbol": "Ticker",
        "Symbol": "Ticker",
        "SYMBOL": "Ticker",
        "ticker": "Ticker",
        "Ticker": "Ticker",
        "TICKER": "Ticker",
        "Hisse": "Ticker",

        "price": "Price",
        "Price": "Price",
        "PRICE": "Price",
        "close": "Price",
        "Close": "Price",
        "CLOSE": "Price",
        "last": "Price",
        "Last": "Price",

        "signal": "Signal",
        "Signal": "Signal",
        "SIGNAL": "Signal",
        "AI_Signal": "Signal",
        "AI_SIGNAL": "Signal",
        "prediction": "Signal",
        "Prediction": "Signal",

        "score": "AI_Probability",
        "Score": "AI_Probability",
        "SCORE": "AI_Probability",
        "probability": "AI_Probability",
        "Probability": "AI_Probability",
        "AI Probability": "AI_Probability",
        "AI_Probability": "AI_Probability",

        "predicted_return": "AI_Predicted_Return",
        "Predicted_Return": "AI_Predicted_Return",
        "Predicted Return": "AI_Predicted_Return",
        "AI_Predicted_Return": "AI_Predicted_Return",

        "change": "Change",
        "Change": "Change",
        "CHANGE": "Change",
        "change_percent": "Change",
        "Change_Percent": "Change",
    }

    for old, new in rename_map.items():

        if (
            old in df.columns
            and new not in df.columns
        ):

            df[new] = df[old]

    original = list(df.columns)

    if len(original) >= 6:

        if "Date" not in df.columns:
            df["Date"] = df[original[0]]

        if "Ticker" not in df.columns:
            df["Ticker"] = df[original[1]]

        if "Price" not in df.columns:
            df["Price"] = df[original[2]]

        if "AI_Probability" not in df.columns:
            df["AI_Probability"] = df[original[3]]

        if "AI_Predicted_Return" not in df.columns:
            df["AI_Predicted_Return"] = df[original[4]]

        if "Signal" not in df.columns:
            df["Signal"] = df[original[5]]

    defaults = {
        "Ticker": "-",
        "Signal": "HOLD",
        "AI_Probability": 0,
        "AI_Predicted_Return": 0,
        "Date": "-",
        "Price": 0,
        "Change": 0,
    }

    for col, value in defaults.items():

        if col not in df.columns:
            df[col] = value

    df["Ticker"] = (
        df["Ticker"]
        .fillna("-")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["Signal"] = (
        df["Signal"]
        .fillna("HOLD")
        .astype(str)
        .str.upper()
        .str.strip()
        .replace({
            "AL": "BUY",
            "LONG": "BUY",
            "SAT": "SELL",
            "SHORT": "SELL",
            "BEKLE": "HOLD",
            "NEUTRAL": "HOLD",
        })
    )

    for col in [
        "AI_Probability",
        "AI_Predicted_Return",
        "Price",
        "Change",
    ]:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        ).fillna(0)

    df["Date"] = (
        df["Date"]
        .fillna("-")
        .astype(str)
        .str.strip()
    )

    return df


# ============================================================
# FIND SIGNAL FILE
# ============================================================

def find_signal_file():

    candidates = [

        LATEST_SIGNALS,
        PAPER_SIGNALS,

        BASE_DIR / "level1000_v3_signals.csv",
        BASE_DIR / "level1000_fast_top.csv",
        BASE_DIR / "level1000_fast_scan.csv",

        DATA_DIR / "level1000_latest_signals.csv",
        DATA_DIR / "level1000_paper_signals.csv",
        DATA_DIR / "level1000_v3_signals.csv",
        DATA_DIR / "level1000_fast_top.csv",
        DATA_DIR / "level1000_fast_scan.csv",

        BASE_DIR / "level1000_ai_history.csv",
        BASE_DIR / "level1000_ai_historical.csv",
        BASE_DIR / "level1000_history.csv",
        BASE_DIR / "level1000_results.csv",
        BASE_DIR / "level1000_signals.csv",

        DATA_DIR / "level1000_ai_history.csv",
        DATA_DIR / "level1000_ai_historical.csv",
        DATA_DIR / "level1000_history.csv",
        DATA_DIR / "level1000_results.csv",
        DATA_DIR / "level1000_signals.csv",
    ]

    checked = set()

    for path in candidates:

        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)

        if key in checked:
            continue

        checked.add(key)

        if not path.exists():
            continue

        try:

            df = pd.read_csv(
                path,
                low_memory=False
            )

            normalized = normalize_signal_dataframe(
                df
            )

            if normalized.empty:
                continue

            valid = normalized[
                normalized["Signal"].isin(
                    ["BUY", "SELL", "HOLD"]
                )
            ]

            if len(valid):

                return path, normalized

        except Exception:

            continue

    return None, pd.DataFrame()


# ============================================================
# DISPLAY
# ============================================================

def prepare_display_dataframe(
    df,
    limit=DISPLAY_LIMIT
):

    df = normalize_signal_dataframe(df)

    if df.empty:
        return df

    work = df.copy()

    work = work[
        ~work["Ticker"].isin(
            ["", "-", "NAN", "NONE"]
        )
    ].copy()

    work["_score"] = pd.to_numeric(
        work["AI_Probability"],
        errors="coerce"
    ).fillna(0)

    work["_predicted_return"] = pd.to_numeric(
        work["AI_Predicted_Return"],
        errors="coerce"
    ).fillna(0)

    work["Change"] = work["_predicted_return"]

    work["_date"] = pd.to_datetime(
        work["Date"],
        errors="coerce"
    )

    work = work[
        work["Signal"].isin(
            ["BUY", "SELL"]
        )
        &
        (
            work["_score"] >= MIN_SIGNAL_SCORE
        )
    ]

    if work.empty:
        return work

    work = work.sort_values(
        ["_date", "_score"],
        ascending=[False, False],
        na_position="last"
    )

    work = work.drop_duplicates(
        "Ticker",
        keep="first"
    )

    work = work.sort_values(
        "_score",
        ascending=False
    )

    work = work.head(
        min(
            int(limit),
            DISPLAY_LIMIT
        )
    )

    return work.drop(
        columns=[
            "_score",
            "_predicted_return",
            "_date"
        ],
        errors="ignore"
    )


# ============================================================
# JSON
# ============================================================

def dataframe_to_records(df):

    if df is None or df.empty:
        return []

    df = df.replace(
        [float("inf"), float("-inf")],
        None
    )

    df = df.where(
        pd.notnull(df),
        None
    )

    records = df.to_dict(
        orient="records"
    )

    result = []

    for row in records:

        clean = {}

        for key, value in row.items():

            if value is None:

                clean[key] = None
                continue

            try:

                if pd.isna(value):

                    clean[key] = None
                    continue

            except Exception:

                pass

            if hasattr(value, "item"):

                try:

                    clean[key] = value.item()

                except Exception:

                    clean[key] = str(value)

            else:

                clean[key] = value

        result.append(clean)

    return result


# ============================================================
# FALLBACK ANA SAYFA
# ============================================================

def render_fallback_home():

    return """
<!DOCTYPE html>
<html lang="tr">

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <meta
        name="description"
        content="LEVEL 1000 AI finansal piyasa analiz ve yapay zeka platformu."
    >

    <title>LEVEL 1000 AI</title>

    <style>

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;

            display: flex;
            align-items: center;
            justify-content: center;

            padding: 20px;

            font-family:
                Arial,
                Helvetica,
                sans-serif;

            background: #0b1020;
            color: #ffffff;
        }

        .box {
            width: 100%;
            max-width: 900px;

            padding: 55px 35px;

            text-align: center;

            background: #121a2d;

            border:
                1px solid #27304a;

            border-radius: 22px;

            box-shadow:
                0 20px 60px
                rgba(0, 0, 0, 0.35);
        }

        .logo {
            font-size: 40px;
            font-weight: 900;
            margin-bottom: 20px;
        }

        .logo span {
            color: #7ea2ff;
        }

        h1 {
            margin: 0 0 18px;
            font-size: 30px;
        }

        p {
            max-width: 680px;
            margin: 0 auto;

            color: #aeb8cc;

            font-size: 17px;
            line-height: 1.7;
        }

        .online {
            display: inline-block;

            margin-top: 28px;

            padding: 10px 18px;

            background: #17233d;

            border-radius: 8px;

            color: #8fe3a4;

            font-weight: 700;
        }

        .buttons {
            display: flex;

            justify-content: center;

            flex-wrap: wrap;

            gap: 10px;

            margin-top: 30px;
        }

        .buttons a {
            display: inline-block;

            padding:
                11px 18px;

            background: #263657;

            color: #ffffff;

            text-decoration: none;

            border-radius: 9px;

            font-weight: 700;
        }

        .buttons a:hover {
            background: #34496f;
        }

        footer {
            margin-top: 35px;

            color: #69758c;

            font-size: 13px;
        }

    </style>

</head>

<body>

<div class="box">

    <div class="logo">
        LEVEL <span>1000</span> AI
    </div>

    <h1>
        Yapay Zeka Destekli Finansal Analiz
    </h1>

    <p>
        LEVEL 1000 AI; finansal piyasaları,
        yapay zeka ve makine öğrenmesi tabanlı
        analizlerle değerlendiren karar destek platformudur.
    </p>

    <div class="online">
        ● LEVEL 1000 AI ONLINE
    </div>

    <div class="buttons">

        <a href="/about">Hakkımızda</a>
        <a href="/guide">Kullanım Rehberi</a>
        <a href="/risk">Risk Açıklaması</a>
        <a href="/privacy">Gizlilik</a>
        <a href="/contact">İletişim</a>
        <a href="/api/health">Sistem Durumu</a>

    </div>

    <footer>
        © 2026 LEVEL 1000 AI
    </footer>

</div>

</body>

</html>
"""


# ============================================================
# ANA SAYFA
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
async def home():

    index_file = TEMPLATES_DIR / "index.html"

    print("========================================")
    print("LEVEL 1000 ANA SAYFA KONTROL")
    print("INDEX DOSYASI:", str(index_file))
    print("INDEX VAR MI:", index_file.is_file())
    print("========================================")

    if index_file.is_file():

        try:

            html = index_file.read_text(
                encoding="utf-8"
            )

            print(
                "INDEX OKUNDU:",
                len(html),
                "karakter"
            )

            return HTMLResponse(
                content=html,
                status_code=200,
                headers={
                    "Cache-Control":
                        "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                    "Expires": "0",
                }
            )

        except Exception as exc:

            print(
                "INDEX OKUMA HATASI:",
                repr(exc)
            )

    print(
        "INDEX BULUNAMADI:",
        str(index_file)
    )

    return HTMLResponse(
        content=render_fallback_home(),
        status_code=200,
        headers={
            "Cache-Control":
                "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )


# ============================================================
# PUBLIC PAGE TEMPLATE
# ============================================================

def render_public_page(page):

    return f"""
<!DOCTYPE html>
<html lang="tr">

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <meta
        name="description"
        content="LEVEL 1000 AI finansal piyasa analiz ve yapay zeka platformu."
    >

    <title>{page["title"]}</title>

    <style>

        * {{
            box-sizing: border-box;
        }}

        html {{
            scroll-behavior: smooth;
        }}

        body {{
            margin: 0;
            padding: 0;

            font-family:
                Arial,
                Helvetica,
                sans-serif;

            background: #0b1020;
            color: #e8ecf5;

            line-height: 1.7;
        }}

        .container {{
            width: 100%;
            max-width: 1000px;

            margin: 0 auto;

            padding:
                30px 20px 50px;
        }}

        header {{
            padding-bottom: 25px;
            margin-bottom: 30px;

            border-bottom:
                1px solid #27304a;
        }}

        .logo {{
            font-size: 25px;
            font-weight: 800;

            letter-spacing: 0.5px;
        }}

        .logo span {{
            color: #7ea2ff;
        }}

        nav {{
            display: flex;

            flex-wrap: wrap;

            gap: 10px;

            margin-top: 20px;
        }}

        nav a {{
            display: inline-block;

            padding:
                7px 11px;

            color: #aebfff;

            text-decoration: none;

            border-radius: 7px;
        }}

        nav a:hover {{
            background: #1b2640;
            color: #ffffff;
        }}

        main {{
            background: #121a2d;

            border:
                1px solid #27304a;

            border-radius: 16px;

            padding: 40px;

            box-shadow:
                0 15px 45px
                rgba(0, 0, 0, 0.25);
        }}

        h1 {{
            margin-top: 0;
            margin-bottom: 25px;

            font-size: 34px;

            line-height: 1.25;

            color: #ffffff;
        }}

        p {{
            margin: 0;

            white-space: pre-line;

            color: #cbd3e5;

            font-size: 16px;
        }}

        .back {{
            display: inline-block;

            margin-top: 30px;

            padding:
                10px 16px;

            background: #1b2640;

            color: #ffffff;

            border-radius: 8px;

            text-decoration: none;
        }}

        .back:hover {{
            background: #263657;
        }}

        footer {{
            margin-top: 35px;

            padding-top: 25px;

            border-top:
                1px solid #27304a;

            color: #8993aa;

            font-size: 14px;
        }}

        footer a {{
            display: inline-block;

            margin-right: 15px;
            margin-bottom: 8px;

            color: #9db7ff;

            text-decoration: none;
        }}

        footer a:hover {{
            text-decoration: underline;
        }}

        @media (max-width: 600px) {{

            .container {{
                padding:
                    20px 12px 35px;
            }}

            main {{
                padding: 25px 20px;
            }}

            h1 {{
                font-size: 27px;
            }}

            p {{
                font-size: 15px;
            }}

            nav {{
                gap: 5px;
            }}

            nav a {{
                font-size: 14px;
            }}

        }}

    </style>

</head>

<body>

<div class="container">

    <header>

        <div class="logo">
            LEVEL <span>1000</span> AI
        </div>

        <nav>

            <a href="/">Ana Sayfa</a>
            <a href="/about">Hakkımızda</a>
            <a href="/guide">Rehber</a>
            <a href="/risk">Risk</a>
            <a href="/privacy">Gizlilik</a>
            <a href="/cookies">Çerezler</a>
            <a href="/terms">Şartlar</a>
            <a href="/contact">İletişim</a>

        </nav>

    </header>

    <main>

        <h1>{page["heading"]}</h1>

        <p>{page["text"]}</p>

        <a
            class="back"
            href="/"
        >
            ← Ana Sayfaya Dön
        </a>

    </main>

    <footer>

        <a href="/about">Hakkımızda</a>
        <a href="/guide">Kullanım Rehberi</a>
        <a href="/privacy">Gizlilik</a>
        <a href="/cookies">Çerezler</a>
        <a href="/terms">Kullanım Şartları</a>
        <a href="/risk">Risk Açıklaması</a>
        <a href="/contact">İletişim</a>

        <br>
        <br>

        © 2026 LEVEL 1000 AI

    </footer>

</div>

</body>

</html>
"""


# ============================================================
# PUBLIC PAGES
# ============================================================

PUBLIC_PAGES = {

    "/about": {
        "title": "Hakkımızda - LEVEL 1000 AI",
        "heading": "LEVEL 1000 AI Hakkında",
        "text": """
LEVEL 1000 AI, finansal piyasaları analiz etmek için geliştirilmiş
yapay zeka ve makine öğrenmesi tabanlı bir analiz platformudur.

Platform; teknik göstergeler, makine öğrenmesi tahminleri,
sinyal gücü ve geçmiş performans verilerini birlikte değerlendirerek
kullanıcıya karar destek amaçlı piyasa analizleri sunar.

LEVEL 1000 AI yatırım danışmanlığı veya garanti edilmiş getiri hizmeti
değildir. Üretilen sinyaller yalnızca bilgi ve araştırma amacıyla
kullanılmalıdır.
"""
    },

    "/guide": {
        "title": "Kullanım Rehberi - LEVEL 1000 AI",
        "heading": "LEVEL 1000 AI Kullanım Rehberi",
        "text": """
Dashboard üzerinden mevcut piyasa sinyallerini inceleyebilirsiniz.

BUY sinyali yükseliş yönlü,
SELL sinyali düşüş yönlü,
HOLD sinyali ise belirgin bir yön bulunmadığını ifade eder.

AI Probability değeri modelin tahmin güvenini,
Predicted Return ise model tarafından tahmin edilen potansiyel
hareketi gösterir.

Sinyaller yatırım tavsiyesi değildir. Kullanıcıların kendi
araştırmalarını ve risk değerlendirmelerini yapmaları gerekir.
"""
    },

    "/risk": {
        "title": "Risk Açıklaması - LEVEL 1000 AI",
        "heading": "Risk Açıklaması",
        "text": """
Finansal piyasalarda işlem yapmak sermaye kaybı riski içerir.

LEVEL 1000 AI tarafından oluşturulan hiçbir sinyal veya tahmin
gelecekteki fiyat hareketlerini garanti etmez.

Geçmiş performans gelecekteki sonuçların göstergesi değildir.
Piyasa koşulları hızlı şekilde değişebilir ve modeller hatalı
tahminlerde bulunabilir.

Kullanıcı platformdaki bilgileri kendi risk değerlendirmesini
yapmak için kullanmalıdır.
"""
    },

    "/privacy": {
        "title": "Gizlilik Politikası - LEVEL 1000 AI",
        "heading": "Gizlilik Politikası",
        "text": """
LEVEL 1000 AI kullanıcı hesaplarının çalışması için gerekli temel
bilgileri saklayabilir.

Hesap oluştururken ad, e-posta adresi ve güvenli şekilde hashlenmiş
parola bilgisi kullanılmaktadır.

Parolalar düz metin olarak saklanmaz.

Kullanıcı bilgileri yalnızca platformun çalışması, güvenlik,
kimlik doğrulama ve hesap yönetimi gibi gerekli amaçlarla işlenir.
"""
    },

    "/cookies": {
        "title": "Çerez Politikası - LEVEL 1000 AI",
        "heading": "Çerez Politikası",
        "text": """
LEVEL 1000 AI, kullanıcı oturumu ve platformun temel işlevlerinin
çalışması için gerekli teknik mekanizmaları kullanabilir.

Çerezler veya benzeri teknolojiler kullanıldığı durumda bunların
amacı kullanıcı deneyimini geliştirmek, güvenliği sağlamak ve
platformun düzgün çalışmasını sağlamaktır.
"""
    },

    "/terms": {
        "title": "Kullanım Şartları - LEVEL 1000 AI",
        "heading": "Kullanım Şartları",
        "text": """
LEVEL 1000 AI yalnızca bilgi, analiz ve araştırma amaçlı bir
platformdur.

Platform tarafından oluşturulan sinyaller yatırım tavsiyesi,
finansal danışmanlık veya garanti edilmiş kazanç olarak
değerlendirilmemelidir.

Kullanıcı gerçekleştirdiği yatırım işlemlerinden ve aldığı
kararlardan kendisi sorumludur.

Platformun kullanımında yürürlükteki yasalara uyulması gerekir.
"""
    },

    "/contact": {
        "title": "İletişim - LEVEL 1000 AI",
        "heading": "İletişim",
        "text": """
LEVEL 1000 AI hakkında sorularınız, teknik sorunlarınız veya
geri bildirimleriniz varsa platform yöneticisiyle iletişime
geçebilirsiniz.

Destek taleplerinizde mümkün olduğunca sorununuzu, kullandığınız
sayfayı ve karşılaştığınız hata mesajını belirtmeniz çözüm sürecini
hızlandırır.
"""
    },
}


# ============================================================
# PUBLIC PAGE ROUTES
# ============================================================

def create_public_route(
    path,
    data
):

    async def public_page():

        return HTMLResponse(
            content=render_public_page(data),
            status_code=200
        )

    app.add_api_route(
        path,
        public_page,
        methods=["GET"],
        response_class=HTMLResponse,
        name=(
            "public_"
            +
            path.strip("/")
            .replace("/", "_")
        )
    )


for public_path, public_data in PUBLIC_PAGES.items():

    create_public_route(
        public_path,
        public_data
    )


# ============================================================
# SITE BASE URL
# ============================================================

def get_base_url(request: Request):

    forwarded_proto = request.headers.get(
        "x-forwarded-proto"
    )

    forwarded_host = request.headers.get(
        "x-forwarded-host"
    )

    if forwarded_host:

        protocol = (
            forwarded_proto
            or "https"
        )

        return (
            f"{protocol}://"
            f"{forwarded_host}"
        ).rstrip("/")

    return str(
        request.base_url
    ).rstrip("/")


# ============================================================
# ROBOTS
# ============================================================

@app.get(
    "/robots.txt",
    response_class=PlainTextResponse
)
async def robots_txt(
    request: Request
):

    base_url = get_base_url(request)

    return f"""User-agent: *
Allow: /

Sitemap: {base_url}/sitemap.xml
"""


# ============================================================
# SITEMAP
# ============================================================

@app.get(
    "/sitemap.xml"
)
async def sitemap_xml(
    request: Request
):

    urls = [
        "/",
        "/about",
        "/guide",
        "/risk",
        "/privacy",
        "/cookies",
        "/terms",
        "/contact",
    ]

    base_url = get_base_url(request)

    xml_urls = []

    for url in urls:

        xml_urls.append(
            f"""
    <url>
        <loc>{base_url}{url}</loc>
    </url>"""
        )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{"".join(xml_urls)}
</urlset>
"""

    return Response(
        content=xml,
        media_type="application/xml"
    )


# ============================================================
# ERROR PAGE
# ============================================================

def render_error_page(
    code,
    title,
    message
):

    return f"""
<!DOCTYPE html>
<html lang="tr">

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <meta
        name="robots"
        content="noindex, nofollow"
    >

    <title>{code} - LEVEL 1000 AI</title>

    <style>

        * {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            min-height: 100vh;

            display: flex;
            align-items: center;
            justify-content: center;

            padding: 20px;

            font-family:
                Arial,
                Helvetica,
                sans-serif;

            background: #0b1020;
            color: #ffffff;
        }}

        .error-box {{
            width: 100%;
            max-width: 620px;

            padding: 45px 35px;

            text-align: center;

            background: #121a2d;

            border:
                1px solid #27304a;

            border-radius: 20px;

            box-shadow:
                0 20px 60px
                rgba(0, 0, 0, 0.35);
        }}

        .logo {{
            font-size: 23px;
            font-weight: 800;

            margin-bottom: 30px;
        }}

        .logo span {{
            color: #7ea2ff;
        }}

        .code {{
            font-size: 82px;
            font-weight: 900;

            line-height: 1;

            color: #7ea2ff;

            margin-bottom: 20px;
        }}

        h1 {{
            margin: 0 0 15px;

            font-size: 30px;
        }}

        p {{
            margin: 0 auto;

            max-width: 500px;

            color: #aeb8cc;

            font-size: 16px;

            line-height: 1.7;
        }}

        .button {{
            display: inline-block;

            margin-top: 30px;

            padding:
                12px 22px;

            background: #263657;

            color: #ffffff;

            text-decoration: none;

            border-radius: 9px;

            font-weight: 700;
        }}

        .button:hover {{
            background: #34496f;
        }}

        .footer {{
            margin-top: 25px;

            color: #69758c;

            font-size: 13px;
        }}

    </style>

</head>

<body>

    <div class="error-box">

        <div class="logo">
            LEVEL <span>1000</span> AI
        </div>

        <div class="code">
            {code}
        </div>

        <h1>
            {title}
        </h1>

        <p>
            {message}
        </p>

        <a
            class="button"
            href="/"
        >
            ← Ana Sayfaya Dön
        </a>

        <div class="footer">
            LEVEL 1000 AI
        </div>

    </div>

</body>

</html>
"""


# ============================================================
# 404
# ============================================================

@app.exception_handler(404)
async def not_found_handler(
    request: Request,
    exc
):

    return HTMLResponse(
        content=render_error_page(
            404,
            "Sayfa Bulunamadı",
            "Aradığınız sayfa mevcut değil veya taşınmış olabilir."
        ),
        status_code=404
    )


# ============================================================
# 500
# ============================================================

@app.exception_handler(500)
async def server_error_handler(
    request: Request,
    exc
):

    return HTMLResponse(
        content=render_error_page(
            500,
            "Sunucu Hatası",
            "Sunucu tarafında beklenmeyen bir hata oluştu. Lütfen kısa bir süre sonra tekrar deneyin."
        ),
        status_code=500
    )


# ============================================================
# REGISTER
# ============================================================

@app.post("/api/register")
async def register(
    data: RegisterRequest
):

    name = data.name.strip()
    email = str(data.email).lower().strip()
    password = data.password

    if len(name) < 2:

        raise HTTPException(
            status_code=400,
            detail="Ad soyad en az 2 karakter olmalıdır."
        )

    if len(password) < 8:

        raise HTTPException(
            status_code=400,
            detail="Şifre en az 8 karakter olmalıdır."
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
            status_code=409,
            detail="Bu e-posta adresi zaten kayıtlı."
        )

    hashed = password_hash.hash(
        password
    )

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO users
        (
            name,
            email,
            password_hash,
            plan,
            is_admin,
            created_at,
            scan_count
        )
        VALUES (?, ?, ?, 'FREE', 0, ?, 0)
        """,
        (
            name,
            email,
            hashed,
            created_at
        )
    )

    conn.commit()

    user = conn.execute(
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
        WHERE id = ?
        """,
        (cursor.lastrowid,)
    ).fetchone()

    conn.close()

    token = create_token(user)

    return {
        "ok": True,
        "message": "Hesabınız oluşturuldu.",
        "access_token": token,
        "token_type": "bearer",
        "token": token,
        "user": user_dict(user),
    }


# ============================================================
# LOGIN
# ============================================================

@app.post("/api/login")
async def login(
    data: LoginRequest
):

    email = str(data.email).lower().strip()

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE email = ?
        """,
        (email,)
    ).fetchone()

    conn.close()

    if not user:

        raise HTTPException(
            status_code=401,
            detail="E-posta veya şifre hatalı."
        )

    try:

        valid = password_hash.verify(
            data.password,
            user["password_hash"]
        )

    except Exception:

        valid = False

    if not valid:

        raise HTTPException(
            status_code=401,
            detail="E-posta veya şifre hatalı."
        )

    token = create_token(user)

    return {
        "ok": True,
        "message": "Giriş başarılı.",
        "access_token": token,
        "token_type": "bearer",
        "token": token,
        "user": user_dict(user),
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
        "user": user_dict(user)
    }


# ============================================================
# PLAN
# ============================================================

@app.get("/api/plan")
async def current_plan(
    user=Depends(get_current_user)
):

    config = get_plan_config(user)

    return {
        "ok": True,
        "plan": config["name"],
        "level": config["level"],
        "display_limit": config["display_limit"],
        "features": config,
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
# STATUS
# ============================================================

@app.get("/api/status")
async def status(
    user=Depends(get_current_user)
):

    signal_file, df = find_signal_file()

    df = normalize_signal_dataframe(df)

    historical_total = len(df)

    historical_buy = (
        int(
            (df["Signal"] == "BUY").sum()
        )
        if not df.empty
        else 0
    )

    historical_sell = (
        int(
            (df["Signal"] == "SELL").sum()
        )
        if not df.empty
        else 0
    )

    historical_hold = (
        int(
            (df["Signal"] == "HOLD").sum()
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

    current_total = len(current_df)

    current_buy = (
        int(
            (current_df["Signal"] == "BUY").sum()
        )
        if not current_df.empty
        else 0
    )

    current_sell = (
        int(
            (current_df["Signal"] == "SELL").sum()
        )
        if not current_df.empty
        else 0
    )

    current_hold = (
        int(
            (current_df["Signal"] == "HOLD").sum()
        )
        if not current_df.empty
        else 0
    )

    config = get_plan_config(user)

    strong_df = prepare_display_dataframe(
        df,
        config["display_limit"]
    )

    return {
        "ok": True,
        "status": "READY",

        "historical_total": historical_total,
        "historical_buy": historical_buy,
        "historical_sell": historical_sell,
        "historical_hold": historical_hold,

        "current_total": current_total,
        "current_buy": current_buy,
        "current_sell": current_sell,
        "current_hold": current_hold,

        "strong_signals": len(strong_df),
        "top": len(strong_df),

        "min_score": MIN_SIGNAL_SCORE,

        "plan": config["name"],
        "plan_level": config["level"],
        "plan_limit": config["display_limit"],
        "plan_features": config,

        "signal_file": (
            signal_file.name
            if signal_file
            else None
        ),
    }


# ============================================================
# SIGNALS
# ============================================================

@app.get("/api/signals")
async def signals(
    user=Depends(get_current_user)
):

    config = get_plan_config(user)

    signal_file, df = find_signal_file()

    if df.empty:

        return {
            "ok": True,
            "total": 0,
            "buy": 0,
            "sell": 0,
            "hold": 0,
            "top": 0,
            "display_limit": config["display_limit"],
            "min_score": MIN_SIGNAL_SCORE,
            "plan": config["name"],
            "signals": [],
        }

    df = normalize_signal_dataframe(df)

    total = len(df)

    buy = int(
        (df["Signal"] == "BUY").sum()
    )

    sell = int(
        (df["Signal"] == "SELL").sum()
    )

    hold = int(
        (df["Signal"] == "HOLD").sum()
    )

    display_df = prepare_display_dataframe(
        df,
        config["display_limit"]
    )

    raw_records = dataframe_to_records(
        display_df
    )

    records = []

    for row in raw_records:

        try:

            predicted = float(
                row.get(
                    "AI_Predicted_Return",
                    0
                )
            )

        except Exception:

            predicted = 0.0

        try:

            price = float(
                row.get(
                    "Price",
                    0
                )
            )

        except Exception:

            price = 0.0

        try:

            score = float(
                row.get(
                    "AI_Probability",
                    0
                )
            )

        except Exception:

            score = 0.0

        records.append({

            "symbol": str(
                row.get(
                    "Ticker",
                    "-"
                )
            ),

            "signal": str(
                row.get(
                    "Signal",
                    "HOLD"
                )
            ),

            "score": round(
                score,
                4
            ),

            "price": round(
                price,
                4
            ),

            "change": round(
                predicted,
                6
            ),

            "date": str(
                row.get(
                    "Date",
                    "-"
                )
            ),
        })

    return {

        "ok": True,

        "total": total,
        "buy": buy,
        "sell": sell,
        "hold": hold,

        "top": len(records),

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
    }


# ============================================================
# PAPER
# ============================================================

@app.get("/api/paper")
async def paper(
    user=Depends(require_plan("PRO"))
):

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

        return {
            "ok": True,
            "paper":
                dataframe_to_records(df)
        }

    except Exception as exc:

        return {
            "ok": False,
            "error": str(exc),
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

        BASE_DIR / "level1000_metrics.csv",
        BASE_DIR / "metrics.csv",
        DATA_DIR / "metrics.csv",

    ]

    for path in files:

        if not path.exists():
            continue

        try:

            df = pd.read_csv(
                path,
                low_memory=False
            )

            records = dataframe_to_records(
                df
            )

            return {
                "ok": True,
                "count": len(records),
                "metrics": records,
                "data": records,
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
    user=Depends(require_plan("PRO"))
):

    files = [

        BASE_DIR / "level1000_backtest.csv",
        BASE_DIR / "backtest.csv",
        DATA_DIR / "backtest.csv",

    ]

    for path in files:

        if not path.exists():
            continue

        try:

            df = pd.read_csv(
                path,
                low_memory=False
            )

            records = dataframe_to_records(
                df
            )

            return {
                "ok": True,
                "count": len(records),
                "data": records,
            }

        except Exception:

            continue

    return {
        "ok": True,
        "count": 0,
        "data": [],
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
# SCAN HAKKI
# ============================================================

def get_scan_info(user):

    config = get_plan_config(user)

    used = int(
        user["scan_count"]
    )

    limit = int(
        config["scan_limit"]
    )

    if bool(user["is_admin"]):

        remaining = 999999

    else:

        remaining = max(
            0,
            limit - used
        )

    return {

        "used": used,

        "limit": limit,

        "remaining": remaining,

    }


# ============================================================
# SCAN HAKKI KULLAN
# ============================================================

def consume_scan(user):

    if bool(user["is_admin"]):

        return {

            "ok": True,

            "used": 0,

            "limit": 999999,

            "remaining": 999999,

        }

    config = get_plan_config(user)

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
        (user["id"],)
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

        "used": used,

        "limit": limit,

        "remaining": remaining,

    }


# ============================================================
# RUN LEVEL 1000
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
                +
                str(process.returncode)
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

@app.post("/api/run")
async def run_analysis(
    user=Depends(get_current_user)
):

    with run_lock:

        if run_state["running"]:

            return {

                "ok": False,

                "error":
                    "Analiz zaten çalışıyor."

            }

        scan_info = get_scan_info(
            user
        )

        if (
            not bool(user["is_admin"])
            and scan_info["remaining"] <= 0
        ):

            raise HTTPException(

                status_code=403,

                detail=(
                    "Tarama hakkınız bitti. "
                    "FREE plan ile toplam 3 tarama "
                    "kullanabilirsiniz."
                )

            )

        consumed = consume_scan(
            user
        )

        if not consumed["ok"]:

            raise HTTPException(

                status_code=403,

                detail=
                    "Tarama hakkınız kalmadı."

            )

        run_state["last_user"] = (
            user["email"]
        )

        thread = threading.Thread(

            target=
                run_level1000_process,

            daemon=True

        )

        thread.start()

    return {

        "ok": True,

        "message":
            "Analiz başlatıldı."

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
# MAKE ADMIN
# ============================================================

@app.post(
    "/api/admin/make-admin/{email}"
)
async def make_admin(
    email: str,
    user=Depends(require_admin)
):

    email = email.lower().strip()

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

@app.get("/api/admin/users")
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

        config = get_plan_config(
            row
        )

        used = int(
            row["scan_count"]
        )

        if bool(row["is_admin"]):

            item["scan_count"] = used

            item["scan_limit"] = 999999

            item["scan_remaining"] = 999999

        else:

            item["scan_count"] = used

            item["scan_limit"] = (
                config["scan_limit"]
            )

            item["scan_remaining"] = max(
                0,
                config["scan_limit"] - used
            )

        result.append(item)

    return {

        "ok": True,

        "users": result

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

    if plan not in [
        "FREE",
        "PRO",
        "MAX PRO"
    ]:

        raise HTTPException(

            status_code=400,

            detail=(
                "Plan FREE, PRO veya MAX PRO "
                "olmalıdır."
            )

        )

    email = email.lower().strip()

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

        "plan": plan,

        "message":
            f"Kullanıcı planı {plan} yapıldı."

    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
async def health():

    signal_file, df = find_signal_file()

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

    }


# ============================================================
# DEBUG DATA
# ============================================================

@app.get("/api/debug/data")
async def debug_data(
    user=Depends(get_current_user)
):

    signal_file, df = find_signal_file()

    if df.empty:

        return {

            "ok": True,

            "file": None,

            "columns": [],

            "count": 0,

            "sample": [],

        }

    normalized = normalize_signal_dataframe(
        df
    )

    config = get_plan_config(
        user
    )

    strong = prepare_display_dataframe(
        normalized,
        config["display_limit"]
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
            list(normalized.columns),

        "count":
            len(normalized),

        "buy":
            int(
                (
                    normalized["Signal"]
                    == "BUY"
                ).sum()
            ),

        "sell":
            int(
                (
                    normalized["Signal"]
                    == "SELL"
                ).sum()
            ),

        "hold":
            int(
                (
                    normalized["Signal"]
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

    }


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

    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=False
    )