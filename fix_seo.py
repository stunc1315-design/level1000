from pathlib import Path

# ============================================================
# LEVEL 1000 AI - FIX SEO V3
# ============================================================

APP = Path("app.py")

if not APP.exists():
    raise SystemExit(
        "HATA: app.py bulunamadı.\n"
        "fix_seo.py dosyasını app.py ile aynı klasörde çalıştır."
    )

# ============================================================
# APP OKU
# ============================================================

original = APP.read_text(encoding="utf-8")
text = original


# ============================================================
# YEDEK
# ============================================================

backup = Path("app_backup_before_seo_v3.py")

if not backup.exists():

    backup.write_text(
        original,
        encoding="utf-8"
    )

    print(
        "Yedek oluşturuldu:",
        backup.name
    )


# ============================================================
# IMPORT: PlainTextResponse
# ============================================================

if "PlainTextResponse" not in text:

    response_import = "from fastapi.responses import"

    if response_import in text:

        line_start = text.find(
            response_import
        )

        line_end = text.find(
            "\n",
            line_start
        )

        if line_end == -1:
            line_end = len(text)

        old_line = text[
            line_start:line_end
        ]

        new_line = (
            old_line.rstrip()
            + ", PlainTextResponse"
        )

        text = text.replace(
            old_line,
            new_line,
            1
        )

    else:

        raise SystemExit(
            "HATA: fastapi.responses import bulunamadı."
        )


# ============================================================
# IMPORT: escape
# ============================================================

if "from html import escape" not in text:

    text = (
        "from html import escape\n"
        + text
    )


# ============================================================
# IMPORT: quote
# ============================================================

if "from urllib.parse import quote" not in text:

    text = (
        "from urllib.parse import quote\n"
        + text
    )


# ============================================================
# ESKİ SEO BLOĞUNU TEMİZLE
# ============================================================

seo_marker = (
    "# ============================================================\n"
    "# GOOGLE SEO - PUBLIC STOCK PAGES"
)

if seo_marker in text:

    seo_start = text.find(
        seo_marker
    )

    start_marker = (
        "# ============================================================\n"
        "# START"
    )

    start_position = text.find(
        start_marker,
        seo_start
    )

    if start_position == -1:

        raise SystemExit(
            "HATA: Eski SEO bloğu bulundu fakat START bulunamadı."
        )

    text = (
        text[:seo_start]
        + text[start_position:]
    )

    print(
        "Eski SEO bloğu temizlendi."
    )


# ============================================================
# ESKİ ROBOTS ROUTE'LARINI TEMİZLE
# ============================================================

while True:

    robots_start = text.find(
        '@app.get("/robots.txt"'
    )

    if robots_start == -1:

        robots_start = text.find(
            "@app.get('/robots.txt'"
        )

    if robots_start == -1:
        break


    # Bir sonraki route'u bul
    next_get = text.find(
        "@app.get(",
        robots_start + 10
    )

    next_post = text.find(
        "@app.post(",
        robots_start + 10
    )

    next_put = text.find(
        "@app.put(",
        robots_start + 10
    )

    next_delete = text.find(
        "@app.delete(",
        robots_start + 10
    )

    start_marker = text.find(
        "# ============================================================\n# START",
        robots_start + 10
    )


    positions = []

    for position in [
        next_get,
        next_post,
        next_put,
        next_delete,
        start_marker
    ]:

        if position != -1:
            positions.append(position)


    if not positions:
        break


    robots_end = min(
        positions
    )


    text = (
        text[:robots_start]
        + text[robots_end:]
    )

    print(
        "Eski robots route temizlendi."
    )


# ============================================================
# YENİ SEO BLOĞU
# ============================================================

SEO_BLOCK = r'''

# ============================================================
# LEVEL 1000 AI - GOOGLE SEO
# PUBLIC STOCK PAGES
# ============================================================

SEO_BASE_URL = "https://level1000-2.onrender.com"


# ============================================================
# PUBLIC TICKER LIST
# ============================================================

def get_public_tickers():

    result = set()


    # --------------------------------------------------------
    # SIGNAL CSV
    # --------------------------------------------------------

    try:

        signal_file, df = find_signal_file()

        if df is not None and not df.empty:

            df = normalize_signal_dataframe(
                df
            )

            if (
                df is not None
                and not df.empty
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


    # --------------------------------------------------------
    # SYMBOLS.TXT
    # --------------------------------------------------------

    symbols_file = Path(
        "symbols.txt"
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


    # --------------------------------------------------------
    # POPÜLER ABD HİSSELERİ
    # --------------------------------------------------------

    result.update({

        "AAPL",
        "NVDA",
        "MSFT",
        "AMZN",
        "GOOGL",
        "GOOG",
        "META",
        "TSLA",
        "AVGO",
        "NFLX",
        "AMD",
        "INTC",
        "QCOM",
        "MU",
        "AMAT",
        "ADBE",
        "CRM",
        "ORCL",
        "IBM",
        "CSCO",
        "UBER",
        "ABNB",
        "PLTR",
        "COIN",
        "HOOD",
        "MSTR",
        "PYPL",
        "SHOP",
        "SNOW",
        "SOFI",
        "RIVN",
        "LCID",
        "NIO",
        "F",
        "GM",
        "BA",
        "JPM",
        "BAC",
        "WMT",
        "COST",
        "DIS",
        "V",
        "MA",
        "JNJ",
        "PFE",
        "XOM",
        "CVX",
        "CAT",
        "GE",
        "T",
        "VZ"

    })


    # --------------------------------------------------------
    # ETF
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # KRİPTO
    # --------------------------------------------------------

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


    return sorted(
        result
    )


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
            df is None
            or df.empty
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


    # --------------------------------------------------------
    # CSV'DEN SİNYAL
    # --------------------------------------------------------

    data = get_public_signal(
        ticker
    )


    # --------------------------------------------------------
    # CSV'DE YOKSA DA SAYFA AÇ
    # --------------------------------------------------------

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


    probability = data[
        "probability"
    ]


    predicted_return = data[
        "predicted_return"
    ]


    price = data[
        "price"
    ]


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

    return PlainTextResponse(

        f"""User-agent: *
Allow: /

Sitemap: {SEO_BASE_URL}/sitemap.xml
""",

        media_type="text/plain"
    )


'''

# ============================================================
# START BUL
# ============================================================

start_marker = (
    "# ============================================================\n"
    "# START"
)

start_position = text.find(
    start_marker
)

if start_position == -1:

    raise SystemExit(
        "HATA: app.py içinde START bölümü bulunamadı."
    )


# ============================================================
# SEO EKLE
# ============================================================

text = (
    text[:start_position]
    + SEO_BLOCK
    + "\n\n"
    + text[start_position:]
)


# ============================================================
# KAYDET
# ============================================================

APP.write_text(
    text,
    encoding="utf-8"
)


# ============================================================
# SONUÇ
# ============================================================

print()
print("=" * 70)
print(" LEVEL 1000 AI - FIX SEO V3 TAMAMLANDI")
print("=" * 70)
print()
print("SEO sistemi app.py içine eklendi.")
print()
print("Eklenenler:")
print()
print("  /hisse/{ticker}")
print("  /sitemap.xml")
print("  /robots.txt")
print()
print("AAPL / NVDA / TSLA gibi semboller")
print("CSV'de olmasa bile public sayfa açabilir.")
print()
print("symbols.txt sitemap'e dahil edilir.")
print()
print("Yedek:")
print("app_backup_before_seo_v3.py")
print()
print("=" * 70)